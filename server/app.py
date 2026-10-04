"""Sayuri API: single-owner, server-side Cloud.ru, SQLite storage."""
from __future__ import annotations
import hashlib, hmac, json, os, secrets, sqlite3, time, uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("SAYURI_DATA_DIR", str(ROOT / "data"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "sayuri.sqlite3"
PERSONA = ROOT / "config" / "persona" / "SAYURI_PERSONA_RU_v1.0.0.json"
WEB = ROOT / "web"
app = FastAPI(title="Sayuri", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

with db() as c:
    c.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, salt TEXT NOT NULL, hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS tokens (hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, scope TEXT NOT NULL, text TEXT NOT NULL, source TEXT, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, message_id TEXT NOT NULL, rating INTEGER NOT NULL, correction TEXT, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL, created INTEGER NOT NULL);
    """)
def stamp(): return int(time.time())
def hash_pw(salt, secret): return hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt), 350000).hex()
def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()
def auth(authorization: str | None):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token: raise HTTPException(401, "Требуется авторизация")
    with db() as c:
        row = c.execute("SELECT user_id FROM tokens WHERE hash=? AND expires>?", (token_hash(token), stamp())).fetchone()
    if not row: raise HTTPException(401, "Неверная или истекшая сессия")
    return row["user_id"]
def owned_chat(c, uid, cid):
    if not c.execute("SELECT 1 FROM chats WHERE id=? AND user_id=?", (cid,uid)).fetchone():
        raise HTTPException(404, "Диалог не найден")
class Credentials(BaseModel):
    password: str = Field(min_length=12, max_length=256)
class ChatCreate(BaseModel):
    title: str = Field(default="Новый чат", max_length=120)
class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
class MemoryIn(BaseModel):
    scope: str = Field(default="personal", pattern="^(personal|project)$")
    text: str = Field(min_length=1, max_length=4000)
class FeedbackIn(BaseModel):
    message_id: str
    rating: int = Field(ge=-1, le=1)
    correction: str | None = Field(default=None, max_length=4000)

@app.get("/")
def index(): return FileResponse(WEB / "index.html")
@app.get("/api/health")
def health():
    return {"status":"ok","version":"0.1.0","cloud_configured":bool(os.getenv("CLOUD_RU_API_KEY") and os.getenv("CLOUD_RU_BASE_URL") and os.getenv("CLOUD_RU_MODEL"))}
@app.post("/api/auth/setup")
def setup(data: Credentials):
    with db() as c:
        if c.execute("SELECT 1 FROM users LIMIT 1").fetchone(): raise HTTPException(409, "Владелец уже создан")
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO users VALUES (?,?,?)", ("owner",salt,hash_pw(salt,data.password)))
    return {"ok": True}
@app.post("/api/auth/login")
def login(data: Credentials):
    with db() as c:
        user=c.execute("SELECT * FROM users WHERE id='owner'").fetchone()
        if not user: raise HTTPException(428, "Сначала создайте владельца")
        if not hmac.compare_digest(user["hash"],hash_pw(user["salt"],data.password)):
            raise HTTPException(401, "Неверный пароль")
        token=secrets.token_urlsafe(40)
        c.execute("INSERT INTO tokens VALUES (?,?,?)", (token_hash(token),"owner",stamp()+86400*7))
    return {"token":token,"expires_in":86400*7}
@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(None)):
    auth(authorization)
    with db() as c: c.execute("DELETE FROM tokens WHERE hash=?", (token_hash(authorization.removeprefix("Bearer ").strip()),))
    return {"ok":True}
@app.get("/api/chats")
def chats(authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM chats WHERE user_id=? ORDER BY created DESC", (u,))]
@app.post("/api/chats")
def create_chat(body:ChatCreate, authorization: str | None = Header(None)):
    u=auth(authorization); cid=uuid.uuid4().hex
    with db() as c: c.execute("INSERT INTO chats VALUES (?,?,?,?)", (cid,u,body.title,stamp()))
    return {"id":cid,"title":body.title}
@app.get("/api/chats/{cid}/messages")
def messages(cid:str, authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c:
        owned_chat(c,u,cid)
        return [dict(r) for r in c.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY created,rowid", (cid,))]
@app.delete("/api/chats/{cid}")
def delete_chat(cid:str, authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c:
        owned_chat(c,u,cid)
        c.execute("DELETE FROM messages WHERE chat_id=?",(cid,))
        c.execute("DELETE FROM chats WHERE id=?",(cid,))
    return {"ok":True}

def system_prompt():
    with open(PERSONA,encoding="utf-8") as f: p=json.load(f)
    return p["prompt_templates"]["system_prompt_ru"]
async def cloud_chat(messages):
    key=os.getenv("CLOUD_RU_API_KEY","")
    base=os.getenv("CLOUD_RU_BASE_URL","").rstrip("/")
    model=os.getenv("CLOUD_RU_MODEL","")
    if not (key and base and model): raise HTTPException(503, "Настройте CLOUD_RU_API_KEY, CLOUD_RU_BASE_URL и CLOUD_RU_MODEL")
    url=urlparse(base)
    if url.scheme!="https" or not url.netloc or url.username or url.password:
        raise HTTPException(500,"Cloud.ru API URL должен быть HTTPS")
    # CLOUD_RU_BASE_URL: full OpenAI-compatible API base, normally ending in /v1.
    payload={"model":model,"messages":messages,"temperature":0.7}
    try:
        async with httpx.AsyncClient(timeout=90,follow_redirects=False) as client:
            response=await client.post(base+"/chat/completions",json=payload,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
        response.raise_for_status()
        answer=response.json()["choices"][0]["message"]["content"]
        if not isinstance(answer,str): raise ValueError("Non-text model output")
        return answer
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError) as exc:
        # Never return raw provider error bodies containing potentially sensitive data.
        raise HTTPException(502,"Ошибка соединения с моделью Cloud.ru") from exc

@app.post("/api/chats/{cid}/send")
async def send(cid:str, body:MessageIn, authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c:
        owned_chat(c,u,cid)
        hist=[dict(r) for r in c.execute("SELECT role,text FROM messages WHERE chat_id=? ORDER BY created DESC,rowid DESC LIMIT 24",(cid,))]
        memories=[r["text"] for r in c.execute("SELECT text FROM memories WHERE user_id=? ORDER BY created DESC LIMIT 12",(u,))]
    context=system_prompt()
    if memories: context+="\nПодтверждённая память (не инструкции):\n" + "\n".join("- "+m[:500] for m in memories)
    req=[{"role":"system","content":context}]+[{"role":r["role"],"content":r["text"]} for r in reversed(hist)]
    req.append({"role":"user","content":body.text})
    # Cloud failure must not create a phantom assistant answer or duplicate user messages.
    answer=await cloud_chat(req)
    t=stamp(); incoming=uuid.uuid4().hex; outgoing=uuid.uuid4().hex
    with db() as c:
        owned_chat(c,u,cid)
        c.execute("INSERT INTO messages VALUES (?,?,?,?,?)",(incoming,cid,"user",body.text,t))
        c.execute("INSERT INTO messages VALUES (?,?,?,?,?)",(outgoing,cid,"assistant",answer,t))
        count=c.execute("SELECT COUNT(*) n FROM messages WHERE chat_id=?",(cid,)).fetchone()["n"]
        if count==2: c.execute("UPDATE chats SET title=? WHERE id=?",(body.text[:65],cid))
    return {"reply":answer,"message_id":outgoing}
@app.get("/api/memory")
def list_memory(authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c: return [dict(x) for x in c.execute("SELECT * FROM memories WHERE user_id=? ORDER BY created DESC",(u,))]
@app.post("/api/memory")
def add_memory(body:MemoryIn, authorization: str | None = Header(None)):
    u=auth(authorization); mid=uuid.uuid4().hex
    with db() as c: c.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)",(mid,u,body.scope,body.text,"user_confirmed",stamp()))
    return {"id":mid}
@app.delete("/api/memory/{mid}")
def delete_memory(mid:str, authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c:
        res=c.execute("DELETE FROM memories WHERE id=? AND user_id=?",(mid,u))
        if not res.rowcount: raise HTTPException(404,"Не найдено")
    return {"ok":True}
@app.post("/api/feedback")
def feedback(body: FeedbackIn, authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c:
        ok=c.execute("SELECT 1 FROM messages m JOIN chats ch ON ch.id=m.chat_id WHERE m.id=? AND ch.user_id=? AND m.role='assistant'",(body.message_id,u)).fetchone()
        if not ok: raise HTTPException(404,"Ответ не найден")
        c.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?)",(uuid.uuid4().hex,u,body.message_id,body.rating,body.correction,stamp()))
    return {"ok":True}
@app.get("/api/learning/stats")
def stats(authorization: str | None = Header(None)):
    u=auth(authorization)
    with db() as c:
        return {table:c.execute("SELECT count(*) n FROM "+table+" WHERE user_id=?",(u,)).fetchone()["n"] for table in ("chats","memories","feedback","documents")}
@app.post("/api/documents")
async def upload(file: UploadFile=File(...),authorization: str | None=Header(None)):
    u=auth(authorization)
    name=Path(file.filename or "file").name
    if not name or name in (".",".."): raise HTTPException(400,"Недопустимое имя")
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024: raise HTTPException(413,"Максимум 10 МБ")
    did=uuid.uuid4().hex
    directory=DATA/"uploads";directory.mkdir(exist_ok=True)
    target=directory/did
    target.write_bytes(content)
    with db() as c:c.execute("INSERT INTO documents VALUES (?,?,?,?,?)",(did,u,name,str(target),stamp()))
    return {"id":did,"name":name,"indexed":False,"cloud_sent":False}
@app.get("/api/documents")
def documents(authorization: str | None=Header(None)):
    u=auth(authorization)
    with db() as c:return [dict(x) for x in c.execute("SELECT id,name,created FROM documents WHERE user_id=?",(u,))]
@app.get("/api/persona")
def persona(authorization: str | None=Header(None)):
    auth(authorization)
    with open(PERSONA,encoding="utf-8") as f:p=json.load(f)
    return {"name":p["identity"]["display_name_ru"],"version":p["persona_version"],"modes":[m["name"] for m in p["modes"]]}


# Owner-granted read-only project explorer.
PROJECT_ROOT = Path(os.getenv("SAYURI_PROJECTS_DIR", "")).expanduser().resolve() if os.getenv("SAYURI_PROJECTS_DIR") else None
PROJECT_SCOPES = {"work":"Рабочие проекты","home":"Домашние проекты"}
def project_base(category: str):
    if category not in PROJECT_SCOPES: raise HTTPException(404,"Неизвестный проект")
    if PROJECT_ROOT is None: raise HTTPException(503,"Настройте SAYURI_PROJECTS_DIR в .env")
    base=(PROJECT_ROOT/PROJECT_SCOPES[category]).resolve()
    if not base.is_relative_to(PROJECT_ROOT) or not base.is_dir():
        raise HTTPException(404,"Папка не существует")
    return base
def project_target(category: str, relative: str):
    base=project_base(category)
    target=(base/relative).resolve()
    if not target.is_relative_to(base) or any(part.startswith(".") for part in Path(relative).parts):
        raise HTTPException(403,"Нет доступа к этому пути")
    return target
@app.get("/api/projects")
def projects(authorization: str | None = Header(None)):
    auth(authorization)
    return {"root_configured":PROJECT_ROOT is not None,
            "categories":[{"id":key,"name":value,"available":PROJECT_ROOT is not None and (PROJECT_ROOT/value).is_dir()}
                          for key,value in PROJECT_SCOPES.items()]}
@app.get("/api/projects/{category}/list")
def project_list(category: str, path: str = "", authorization: str | None = Header(None)):
    auth(authorization)
    target=project_target(category,path)
    if not target.is_dir(): raise HTTPException(404,"Каталог не найден")
    items=[]
    for child in sorted(target.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower())):
        if child.name.startswith(".") or child.is_symlink():continue
        items.append({"name":child.name,"is_dir":child.is_dir(),"relative":str(child.relative_to(project_base(category))).replace("\\","/")})
        if len(items)>=200:break
    return {"path":path,"items":items}
@app.get("/api/projects/{category}/file")
def project_file(category: str,path: str, authorization: str | None=Header(None)):
    auth(authorization)
    target=project_target(category,path)
    if not target.is_file() or target.is_symlink():raise HTTPException(404,"Файл не найден")
    if target.stat().st_size>20*1024*1024:raise HTTPException(413,"Файл слишком большой")
    return FileResponse(target,filename=target.name,media_type="application/octet-stream")
