"""Teacher chats are separate and produce owner-reviewed learning candidates."""
import json
from fastapi.testclient import TestClient
import server.app as sayuri

def test_direct_mentor_chat_and_observation(monkeypatch):
    monkeypatch.setenv("CLOUD_RU_TEACHER_MODEL", "test-deepseek-mentor")
    monkeypatch.setenv("SAYURI_AUTO_OBSERVE", "1")
    calls=[]
    async def cloud(messages, model_override=None):
        calls.append((messages,model_override))
        if "внутренний анализатор понимания Sayuri" in messages[0]["content"]:
            return json.dumps({
                "topic":"Стиль ответов владельцу",
                "summary":"Владелец явно сообщил предпочтение коротких ответов.",
                "concepts":[],"claims":[],"examples":[],"methods":[],"unclear":[],
                "owner_facts":["Пользователь предпочитает короткие ответы."],
                "confidence":0.98,"understood":True,"clarification_question":None
            },ensure_ascii=False)
        return "Я наставник. Ответ принят."
    monkeypatch.setattr(sayuri,"cloud_chat",cloud)
    with TestClient(sayuri.app) as client:
        created=client.post("/api/auth/setup",json={"password":"correct-horse-1234"})
        assert created.status_code in (200,409)
        login=client.post("/api/auth/login",json={"password":"correct-horse-1234"})
        assert login.status_code==200
        h={"Authorization":"Bearer "+login.json()["token"]}
        chat=client.post("/api/chats",json={"title":"DeepSeek учитель","kind":"teacher"},headers=h)
        assert chat.status_code==200
        cid=chat.json()["id"]
        listing=client.get("/api/chats",headers=h).json()
        assert any(c["id"]==cid and c["kind"]=="teacher" for c in listing)
        before=client.get("/api/memory",headers=h).json()
        sent=client.post("/api/chats/"+cid+"/send",json={"text":"Я предпочитаю короткие ответы."},headers=h)
        assert sent.status_code==200,sent.text
        assert sent.json()["kind"]=="teacher"
        assert all(model=="test-deepseek-mentor" for _,model in calls)
        messages=client.get("/api/chats/"+cid+"/messages",headers=h).json()
        assert [m["role"] for m in messages]==["user","assistant"]
        candidates=client.get("/api/learning/candidates",headers=h).json()
        assert any(c["text"]=="Пользователь предпочитает короткие ответы." for c in candidates)
        assert client.get("/api/memory",headers=h).json()==before
