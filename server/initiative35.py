"""Sayuri Initiative 3.5: guarded proactive interaction with continuity and commitments."""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Callable

from fastapi import HTTPException
from pydantic import BaseModel, Field

INITIATIVE_VERSION="3.5.0"

REACTIONS=("accepted","dismissed","less","resolved")
KINDS=("problem","commitment","continuity","teacher_topic","greeting","project_help","social")

_TASK_RE=re.compile(
    r"\b(сделай|делай|продолж|исправ|добав|проверь|создай|реализ|настрой|"
    r"нужно|надо|остал|незаверш|следующ\w*\s+шаг)\w*",
    re.I
)
_CLOSE_RE=re.compile(r"\b(готово|закрыли|завершили|не\s+надо|отмена|отмени|забудь)\b",re.I)
_COMMITMENT_RE=re.compile(
    r"\bя\s+(проверю|сделаю|напомню|подготовлю|продолжу|уточню|"
    r"исправлю|добавлю|сохраню|покажу|вернусь)\b",
    re.I
)
_COMPLETION_RE=re.compile(
    r"\b(готово|проверила|сделала|исправила|добавила|сохранила|"
    r"завершила|выполнила)\b",
    re.I
)


class InitiativeReaction(BaseModel):
    reaction: str = Field(pattern="^(accepted|dismissed|less|resolved)$")


def migrate(db: Callable):
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS initiative_profile (
            user_id TEXT PRIMARY KEY,
            engagement REAL NOT NULL DEFAULT 0,
            ignored_streak INTEGER NOT NULL DEFAULT 0,
            last_seen INTEGER,
            last_delivery INTEGER,
            last_social INTEGER
        );
        CREATE TABLE IF NOT EXISTS initiative_threads (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            project_id TEXT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            source_ref TEXT,
            created INTEGER NOT NULL,
            updated INTEGER NOT NULL,
            last_offered INTEGER
        );
        CREATE TABLE IF NOT EXISTS initiative_commitments (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            chat_id TEXT,
            project_id TEXT,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            source_ref TEXT,
            reminders INTEGER NOT NULL DEFAULT 0,
            created INTEGER NOT NULL,
            updated INTEGER NOT NULL,
            last_offered INTEGER
        );
        CREATE TABLE IF NOT EXISTS initiative_problems (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            problem_key TEXT NOT NULL,
            project_id TEXT,
            title TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            severity INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'open',
            source_ref TEXT,
            created INTEGER NOT NULL,
            updated INTEGER NOT NULL,
            last_offered INTEGER,
            UNIQUE(user_id,problem_key)
        );
        CREATE TABLE IF NOT EXISTS initiative_deliveries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            source_id TEXT,
            project_id TEXT,
            text TEXT NOT NULL,
            reason TEXT NOT NULL,
            score REAL NOT NULL,
            target_view TEXT,
            status TEXT NOT NULL DEFAULT 'offered',
            created INTEGER NOT NULL,
            responded INTEGER
        );
        CREATE TABLE IF NOT EXISTS initiative_mutes (
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            until INTEGER NOT NULL,
            PRIMARY KEY(user_id,kind)
        );
        CREATE INDEX IF NOT EXISTS idx_initiative_threads
            ON initiative_threads(user_id,status,updated DESC);
        CREATE INDEX IF NOT EXISTS idx_initiative_commitments
            ON initiative_commitments(user_id,status,updated DESC);
        CREATE INDEX IF NOT EXISTS idx_initiative_problems
            ON initiative_problems(user_id,status,severity DESC,updated DESC);
        CREATE INDEX IF NOT EXISTS idx_initiative_deliveries
            ON initiative_deliveries(user_id,created DESC);
        """)


def _profile(c,user_id: str) -> dict:
    row=c.execute("SELECT * FROM initiative_profile WHERE user_id=?",(user_id,)).fetchone()
    if not row:
        c.execute("INSERT INTO initiative_profile(user_id) VALUES(?)",(user_id,))
        row=c.execute("SELECT * FROM initiative_profile WHERE user_id=?",(user_id,)).fetchone()
    return dict(row)


def _clamp(value,low,high):
    return max(low,min(high,value))


def _snippet(text: str,limit: int=180) -> str:
    clean=" ".join((text or "").split()).strip()
    if not clean:return ""
    sentence=re.split(r"(?<=[.!?])\s+",clean,1)[0]
    return sentence[:limit]


def _hash_key(*parts: str) -> str:
    raw="\0".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def _muted(c,user_id: str,kind: str,now: int) -> bool:
    row=c.execute("""SELECT until FROM initiative_mutes
                     WHERE user_id=? AND kind=?""",(user_id,kind)).fetchone()
    if not row:return False
    if row["until"]<=now:
        c.execute("DELETE FROM initiative_mutes WHERE user_id=? AND kind=?",(user_id,kind))
        return False
    return True


def _recent_delivery(c,user_id: str,kind: str,now: int,window: int,
                     project_id: str | None=None) -> bool:
    clauses=["user_id=?","kind=?","created>?"]
    params=[user_id,kind,now-window]
    if project_id is not None:
        clauses.append("COALESCE(project_id,'')=?")
        params.append(project_id)
    return c.execute(
        "SELECT 1 FROM initiative_deliveries WHERE "+" AND ".join(clauses)+" LIMIT 1",
        params).fetchone() is not None


def settle_ignored(c,*,user_id: str,now: int):
    stale=c.execute("""SELECT id FROM initiative_deliveries
                       WHERE user_id=? AND status='offered' AND created<=?""",
                    (user_id,now-1800)).fetchall()
    if not stale:return
    ids=[row["id"] for row in stale]
    marks=",".join("?" for _ in ids)
    c.execute(f"""UPDATE initiative_deliveries SET status='ignored',responded=?
                  WHERE id IN ({marks})""",[now,*ids])
    p=_profile(c,user_id)
    engagement=_clamp(float(p["engagement"])-.04*len(ids),-1.0,1.0)
    ignored=min(12,int(p["ignored_streak"])+len(ids))
    c.execute("""UPDATE initiative_profile SET engagement=?,ignored_streak=?
                 WHERE user_id=?""",(engagement,ignored,user_id))


def note_turn(c,*,user_id: str,chat_id: str,kind: str,owner_text: str,
              assistant_text: str,project_id: str | None,now: int):
    """Extract only explicit unfinished-work and Sayuri promise signals."""
    if _CLOSE_RE.search(owner_text):
        c.execute("""UPDATE initiative_threads SET status='closed',updated=?
                     WHERE id=(SELECT id FROM initiative_threads
                       WHERE user_id=? AND status='open'
                       AND (? IS NULL OR COALESCE(project_id,'')=COALESCE(?, ''))
                       ORDER BY updated DESC LIMIT 1)""",
                  (now,user_id,project_id,project_id))

    if _TASK_RE.search(owner_text) and not _CLOSE_RE.search(owner_text):
        title=_snippet(owner_text,190)
        if title:
            recent=c.execute("""SELECT * FROM initiative_threads
                                WHERE user_id=? AND chat_id=? AND status='open'
                                AND COALESCE(project_id,'')=COALESCE(?, '')
                                AND updated>? ORDER BY updated DESC LIMIT 1""",
                             (user_id,chat_id,project_id,now-21600)).fetchone()
            if recent:
                c.execute("""UPDATE initiative_threads SET title=?,source_ref=?,
                             updated=? WHERE id=?""",
                          (title,"chat:"+chat_id,now,recent["id"]))
            else:
                c.execute("""INSERT INTO initiative_threads
                             (id,user_id,chat_id,project_id,title,source_ref,created,updated)
                             VALUES(?,?,?,?,?,?,?,?)""",
                          (uuid.uuid4().hex,user_id,chat_id,project_id,title,
                           "chat:"+chat_id,now,now))

    # Commitments are only Sayuri's own future-tense statements, never mentor output.
    if kind=="sayuri":
        sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",assistant_text or "") if x.strip()]
        future=[]
        for sentence in sentences:
            if _COMMITMENT_RE.search(sentence):
                future.append(sentence[:360])
        for sentence in future[:3]:
            duplicate=c.execute("""SELECT 1 FROM initiative_commitments
                                   WHERE user_id=? AND status='open' AND text=?""",
                                (user_id,sentence)).fetchone()
            if duplicate:continue
            c.execute("""INSERT INTO initiative_commitments
                         (id,user_id,chat_id,project_id,text,source_ref,created,updated)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (uuid.uuid4().hex,user_id,chat_id,project_id,sentence,
                       "chat:"+chat_id,now,now))
        if _COMPLETION_RE.search(assistant_text or "") and not future:
            row=c.execute("""SELECT id FROM initiative_commitments
                             WHERE user_id=? AND status='open'
                             AND COALESCE(chat_id,'')=? ORDER BY updated DESC LIMIT 1""",
                          (user_id,chat_id)).fetchone()
            if row:
                c.execute("""UPDATE initiative_commitments SET status='completed',
                             updated=? WHERE id=?""",(now,row["id"]))


def register_problem(c,*,user_id: str,problem_key: str,title: str,detail: str="",
                     severity: int=3,project_id: str | None=None,
                     source_ref: str | None=None,now: int):
    severity=max(1,min(5,int(severity)))
    existing=c.execute("""SELECT id,status FROM initiative_problems
                          WHERE user_id=? AND problem_key=?""",
                       (user_id,problem_key)).fetchone()
    if existing:
        c.execute("""UPDATE initiative_problems SET project_id=?,title=?,detail=?,
                     severity=?,status='open',source_ref=?,updated=?
                     WHERE id=?""",
                  (project_id,title[:240],detail[:700],severity,source_ref,now,existing["id"]))
        return existing["id"]
    pid=uuid.uuid4().hex
    c.execute("""INSERT INTO initiative_problems
                 (id,user_id,problem_key,project_id,title,detail,severity,source_ref,created,updated)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (pid,user_id,problem_key,project_id,title[:240],detail[:700],
               severity,source_ref,now,now))
    return pid


def resolve_problem(c,*,user_id: str,problem_key: str,now: int):
    c.execute("""UPDATE initiative_problems SET status='resolved',updated=?
                 WHERE user_id=? AND problem_key=?""",(now,user_id,problem_key))


def _teacher_topic(c,user_id: str,project_id: str | None):
    # Teacher Understanding is an optional upstream module. Missing table means no candidate.
    try:
        if project_id:
            return c.execute("""SELECT id,topic,summary,updated FROM teacher_lessons
                                WHERE user_id=? AND status IN ('understood','partial')
                                AND (project_id IS NULL OR project_id='' OR project_id=?)
                                AND topic!='' ORDER BY updated DESC LIMIT 1""",
                             (user_id,project_id)).fetchone()
        return c.execute("""SELECT id,topic,summary,updated FROM teacher_lessons
                            WHERE user_id=? AND status IN ('understood','partial')
                            AND topic!='' ORDER BY updated DESC LIMIT 1""",
                         (user_id,)).fetchone()
    except Exception:
        return None


def _candidate(kind: str,score: float,text: str,reason: str,source_id=None,
               project_id=None,target_view=None,actions=None):
    return {
        "kind":kind,"score":score,"text":text,"reason":reason,
        "source_id":source_id,"project_id":project_id,"target_view":target_view,
        "actions":actions or ["accepted","dismissed","less"]
    }


def next_initiative(c,*,user_id: str,now: int,trigger: str="periodic",
                    project_id: str | None=None,module: str | None=None):
    settle_ignored(c,user_id=user_id,now=now)
    p=_profile(c,user_id)
    previous_seen=p["last_seen"]
    gap=(now-int(previous_seen)) if previous_seen else None
    engagement=float(p["engagement"])
    ignored=int(p["ignored_streak"])

    # Record presence even when no intervention is allowed.
    c.execute("UPDATE initiative_profile SET last_seen=? WHERE user_id=?",(now,user_id))

    min_gap=int(_clamp(1800-600*max(0,engagement)+1200*max(0,-engagement)+ignored*600,
                       1200,7200))
    if p["last_delivery"] and now-int(p["last_delivery"])<min_gap:
        return {"version":INITIATIVE_VERSION,"item":None,"reason":"global_cooldown"}

    threshold=_clamp(60-8*engagement+3*ignored,54,82)
    candidates=[]

    if not _muted(c,user_id,"problem",now):
        problem=c.execute("""SELECT * FROM initiative_problems
                             WHERE user_id=? AND status='open'
                             AND (? IS NULL OR project_id IS NULL OR project_id=?)
                             ORDER BY severity DESC,updated DESC LIMIT 1""",
                          (user_id,project_id,project_id)).fetchone()
        if problem and (not problem["last_offered"] or
                        now-int(problem["last_offered"])>max(3600,21600-int(problem["severity"])*3000)):
            text="Я обнаружила проблему: "+problem["title"]+"."
            if problem["detail"]:text+=" "+problem["detail"][:240]
            candidates.append(_candidate(
                "problem",min(99,78+int(problem["severity"])*4),text,
                "Есть подтверждённый открытый сигнал проблемы.",
                source_id=problem["id"],project_id=problem["project_id"],
                target_view="account",
                actions=["accepted","resolved","dismissed"]))

    if not _muted(c,user_id,"commitment",now):
        commitment=c.execute("""SELECT * FROM initiative_commitments
                                WHERE user_id=? AND status='open' AND reminders<3
                                AND created<=?
                                AND (? IS NULL OR project_id IS NULL OR project_id=?)
                                ORDER BY updated DESC LIMIT 1""",
                             (user_id,now-1800,project_id,project_id)).fetchone()
        if commitment and (not commitment["last_offered"] or
                           now-int(commitment["last_offered"])>=86400):
            candidates.append(_candidate(
                "commitment",83,
                "Я помню своё обещание: "+commitment["text"][:300]+" Вернуться к нему?",
                "Есть незакрытое обещание Sayuri.",
                source_id=commitment["id"],project_id=commitment["project_id"],
                target_view="chat",
                actions=["accepted","resolved","dismissed","less"]))

    if not _muted(c,user_id,"continuity",now):
        should_continue=(trigger=="project") or (trigger in ("session","focus") and gap is not None and gap>=14400)
        if should_continue:
            thread=c.execute("""SELECT * FROM initiative_threads
                                WHERE user_id=? AND status='open'
                                AND (? IS NULL OR project_id IS NULL OR project_id=?)
                                ORDER BY updated DESC LIMIT 1""",
                             (user_id,project_id,project_id)).fetchone()
            if thread and (not thread["last_offered"] or now-int(thread["last_offered"])>=43200):
                target=("work" if str(thread["project_id"] or "").startswith("work:") else
                        "home" if str(thread["project_id"] or "").startswith("home:") else "chat")
                candidates.append(_candidate(
                    "continuity",75,
                    "У нас осталось незавершённое: "+thread["title"][:240]+" Продолжим?",
                    "Сохранена незавершённая задача или открытая тема.",
                    source_id=thread["id"],project_id=thread["project_id"],target_view=target))

    if not _muted(c,user_id,"teacher_topic",now) and trigger in ("session","focus"):
        if gap is not None and gap>=21600:
            topic=_teacher_topic(c,user_id,project_id)
            if topic and now-int(topic["updated"])>=3600 and not _recent_delivery(
                    c,user_id,"teacher_topic",now,43200,project_id):
                candidates.append(_candidate(
                    "teacher_topic",68,
                    "В прошлый раз мы разбирали «"+str(topic["topic"])[:180]+"». Продолжим эту тему?",
                    "Есть сохранённый урок предыдущего разговора с учителем.",
                    source_id=topic["id"],project_id=project_id,target_view="chat"))

    if not _muted(c,user_id,"greeting",now) and trigger in ("session","focus"):
        # Fresh installs already have a static welcome. Proactive greeting starts on a real return.
        if gap is not None and gap>=21600:
            if not _recent_delivery(c,user_id,"greeting",now,21600):
                candidates.append(_candidate(
                    "greeting",64,
                    "Рада снова вас видеть. Я рядом, если хотите продолжить работу.",
                    "Достаточно долгая пауза с последнего присутствия.",
                    target_view=None))

    if project_id and trigger=="project" and not _muted(c,user_id,"project_help",now):
        if not _recent_delivery(c,user_id,"project_help",now,21600,project_id):
            label=project_id.split(":",1)[-1].replace("__root__","раздел проектов")
            target="work" if project_id.startswith("work:") else "home"
            candidates.append(_candidate(
                "project_help",60,
                "Контекст проекта «"+label[:120]+"» активен. Могу помочь продолжить с текущего места.",
                "Открыт проект, по которому давно не было инициативного предложения.",
                project_id=project_id,target_view=target))

    if not _muted(c,user_id,"social",now) and trigger in ("session","focus"):
        last_social=int(p["last_social"] or 0)
        if engagement>=.18 and gap is not None and gap>=64800 and now-last_social>=86400:
            lines=[
                "Рада вас видеть. Как сегодня идёт работа?",
                "Я здесь. Хотите немного поговорить перед продолжением?",
                "Давно не разговаривали просто так. Как вы?"
            ]
            text=lines[(now//86400)%len(lines)]
            candidates.append(_candidate(
                "social",55+engagement*10,text,
                "Редкая социальная инициатива разрешена предыдущей положительной реакцией."))

    available=[item for item in candidates if not _muted(c,user_id,item["kind"],now)]
    if not available:
        return {"version":INITIATIVE_VERSION,"item":None,"reason":"no_candidate","threshold":round(threshold,2)}
    available.sort(key=lambda item:item["score"],reverse=True)
    chosen=available[0]
    if chosen["score"]<threshold:
        return {"version":INITIATIVE_VERSION,"item":None,"reason":"below_threshold","threshold":round(threshold,2)}

    delivery_id=uuid.uuid4().hex
    c.execute("""INSERT INTO initiative_deliveries
                 (id,user_id,kind,source_id,project_id,text,reason,score,target_view,created)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (delivery_id,user_id,chosen["kind"],chosen["source_id"],chosen["project_id"],
               chosen["text"],chosen["reason"],chosen["score"],chosen["target_view"],now))
    c.execute("UPDATE initiative_profile SET last_delivery=? WHERE user_id=?",(now,user_id))
    if chosen["kind"]=="social":
        c.execute("UPDATE initiative_profile SET last_social=? WHERE user_id=?",(now,user_id))
    if chosen["source_id"]:
        table={
            "problem":"initiative_problems",
            "commitment":"initiative_commitments",
            "continuity":"initiative_threads"
        }.get(chosen["kind"])
        if table:
            c.execute(f"UPDATE {table} SET last_offered=? WHERE id=?",(now,chosen["source_id"]))
            if chosen["kind"]=="commitment":
                c.execute("""UPDATE initiative_commitments SET reminders=reminders+1
                             WHERE id=?""",(chosen["source_id"],))
    chosen["id"]=delivery_id
    chosen["score"]=round(chosen["score"],2)
    chosen["threshold"]=round(threshold,2)
    return {"version":INITIATIVE_VERSION,"item":chosen,"reason":"offer"}


def react(c,*,user_id: str,delivery_id: str,reaction: str,now: int):
    if reaction not in REACTIONS:
        raise HTTPException(400,"Неизвестная реакция")
    row=c.execute("""SELECT * FROM initiative_deliveries
                     WHERE id=? AND user_id=?""",(delivery_id,user_id)).fetchone()
    if not row:raise HTTPException(404,"Инициативная реплика не найдена")
    if row["status"]!="offered":
        return dict(row)

    p=_profile(c,user_id)
    engagement=float(p["engagement"]);ignored=int(p["ignored_streak"])
    if reaction=="accepted":
        engagement=_clamp(engagement+.12,-1,1);ignored=0
    elif reaction=="resolved":
        engagement=_clamp(engagement+.06,-1,1);ignored=max(0,ignored-1)
    elif reaction=="dismissed":
        engagement=_clamp(engagement-.06,-1,1);ignored=min(12,ignored+1)
    elif reaction=="less":
        engagement=_clamp(engagement-.15,-1,1);ignored=min(12,ignored+2)
        c.execute("""INSERT INTO initiative_mutes(user_id,kind,until)
                     VALUES(?,?,?)
                     ON CONFLICT(user_id,kind) DO UPDATE SET until=excluded.until""",
                  (user_id,row["kind"],now+7*86400))

    if reaction=="resolved" and row["source_id"]:
        table={
            "problem":"initiative_problems",
            "commitment":"initiative_commitments",
            "continuity":"initiative_threads"
        }.get(row["kind"])
        if table:
            status={"problem":"resolved","commitment":"completed","continuity":"closed"}[row["kind"]]
            c.execute(f"UPDATE {table} SET status=?,updated=? WHERE id=?",
                      (status,now,row["source_id"]))

    c.execute("""UPDATE initiative_deliveries SET status=?,responded=?
                 WHERE id=?""",(reaction,now,delivery_id))
    c.execute("""UPDATE initiative_profile SET engagement=?,ignored_streak=?
                 WHERE user_id=?""",(engagement,ignored,user_id))
    return {
        "ok":True,"reaction":reaction,"kind":row["kind"],
        "target_view":row["target_view"],
        "engagement":round(engagement,3),"ignored_streak":ignored
    }


def status(c,*,user_id: str,now: int):
    settle_ignored(c,user_id=user_id,now=now)
    p=_profile(c,user_id)
    counts={}
    for table,name in [
        ("initiative_threads","open_threads"),
        ("initiative_commitments","open_commitments"),
        ("initiative_problems","open_problems")
    ]:
        counts[name]=c.execute(
            f"SELECT COUNT(*) n FROM {table} WHERE user_id=? AND status='open'",
            (user_id,)).fetchone()["n"]
    mutes=[dict(row) for row in c.execute(
        "SELECT kind,until FROM initiative_mutes WHERE user_id=? AND until>? ORDER BY kind",
        (user_id,now)).fetchall()]
    return {
        "version":INITIATIVE_VERSION,
        "engagement":round(float(p["engagement"]),3),
        "ignored_streak":int(p["ignored_streak"]),
        **counts,
        "mutes":mutes,
        "last_seen":p["last_seen"],
        "last_delivery":p["last_delivery"],
    }
