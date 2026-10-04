"""Offline tests: teacher never learns without the owner's approval."""
import json
import os
from fastapi.testclient import TestClient
import server.app as sayuri

def test_teacher_requires_review(monkeypatch):
    monkeypatch.setenv("CLOUD_RU_TEACHER_MODEL", "teacher-test-model")
    async def fake_cloud(messages, model_override=None):
        assert model_override == "teacher-test-model"
        assert messages[0]["role"] == "system"
        return json.dumps({"facts":["Пользователь предпочитает короткие ответы."]})
    monkeypatch.setattr(sayuri, "cloud_chat", fake_cloud)
    with TestClient(sayuri.app) as client:
        client.post("/api/auth/setup", json={"password":"correct-horse-1234"})
        login=client.post("/api/auth/login",json={"password":"correct-horse-1234"})
        assert login.status_code==200
        headers={"Authorization":"Bearer "+login.json()["token"]}
        new=client.post("/api/chats",json={"title":"test teacher"},headers=headers)
        assert new.status_code==200
        chat_id=new.json()["id"]
        empty=client.post("/api/learning/analyze/"+chat_id,headers=headers)
        assert empty.status_code==400
        with sayuri.db() as connection:
            connection.execute("INSERT INTO messages VALUES (?,?,?,?,?)",(
                "test-"+chat_id,chat_id,"user","Я люблю короткие ответы.",sayuri.stamp()
            ))
        before=client.get("/api/memory",headers=headers).json()
        analyzed=client.post("/api/learning/analyze/"+chat_id,headers=headers)
        assert analyzed.status_code==200,analyzed.text
        proposed=analyzed.json()["candidates"]
        assert len(proposed)==1
        assert client.get("/api/memory",headers=headers).json()==before
        review=client.get("/api/learning/candidates",headers=headers).json()
        assert any(p["id"]==proposed[0]["id"] for p in review)
        accepted=client.post("/api/learning/candidates/"+proposed[0]["id"]+"/approve",headers=headers)
        assert accepted.status_code==200
        assert len(client.get("/api/memory",headers=headers).json())==len(before)+1
        assert client.post("/api/learning/candidates/"+proposed[0]["id"]+"/approve",headers=headers).status_code==404
