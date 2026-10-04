"""Sayuri 2.0 integration and safe Cloud.ru configuration checks."""
from __future__ import annotations
import os
from fastapi.testclient import TestClient
import server.app as service
from server.persona import load_persona

def test_persona_v2_full_bundle():
    p=load_persona()
    assert p["persona_version"]=="2.0.0"
    assert len(p)==55
    assert len(p["dialogues"])==100
    assert sum(len(x["messages"]) for x in p["dialogues"])==540
    assert len(p["phrase_library"]["groups"])==50
    assert sum(len(x["phrases"]) for x in p["phrase_library"]["groups"])==400
    assert len(p["behavior_rules"])==60
    assert len(p["acceptance_scenarios"])==60
    assert len(p["lore_chapters"]["chapters"])==9
    assert len(p["ritual_engine"]["records"])==18

def test_cloud_key_saved_privately(tmp_path,monkeypatch):
    monkeypatch.setattr(service,"ROOT",tmp_path)
    monkeypatch.setenv("SAYURI_LOCAL_ACCESS","1")
    secret="test-secret-do-not-print-12"
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",43210)) as client:
        session=client.post("/api/auth/local")
        assert session.status_code==200
        h={"Authorization":"Bearer "+session.json()["token"],"Origin":"http://127.0.0.1:8765"}
        saved=client.put("/api/cloud/config",headers=h,json={
            "api_key":secret,"mentor_model":"org/DeepSeek-Test",
            "sayuri_model":""})
        assert saved.status_code==200,saved.text
        status=client.get("/api/cloud/config",headers=h)
        assert status.status_code==200
        assert status.json()["key_configured"] is True
        assert secret not in status.text
        assert secret in (tmp_path/".env").read_text(encoding="utf-8")
        remote=client.put("/api/cloud/config",
            headers={**h,"Origin":"https://other.example"},
            json={"api_key":"test-secret-elsewhere"})
        assert remote.status_code==403
    monkeypatch.delenv("CLOUD_RU_API_KEY",raising=False)
    monkeypatch.delenv("CLOUD_RU_TEACHER_MODEL",raising=False)
    monkeypatch.delenv("CLOUD_RU_BASE_URL",raising=False)
