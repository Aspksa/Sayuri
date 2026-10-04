import os
os.environ["SAYURI_DATA_DIR"]="/tmp/sayuri_test_"+str(os.getpid())
from fastapi.testclient import TestClient
from server.app import app
def test_auth_chat_and_memory():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code==200
        assert client.post("/api/auth/setup",json={"password":"correct-horse-1234"}).status_code in (200,409)
        token=client.post("/api/auth/login",json={"password":"correct-horse-1234"}).json()["token"]
        h={"Authorization":"Bearer "+token}
        ch=client.post("/api/chats",json={"title":"Тест"},headers=h)
        assert ch.status_code==200
        cid=ch.json()["id"]
        assert client.get(f"/api/chats/{cid}/messages",headers=h).json()==[]
        mid=client.post("/api/memory",json={"text":"Предпочитаю кратко"},headers=h).json()["id"]
        assert client.get("/api/memory",headers=h).json()[0]["id"]==mid
        assert client.delete("/api/memory/"+mid,headers=h).status_code==200
        assert client.delete("/api/chats/"+cid,headers=h).status_code==200
        assert client.get("/api/chats",headers=h).json()==[]
