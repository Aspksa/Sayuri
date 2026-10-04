"""Live sidebar telemetry must reflect measured backend state only."""
import asyncio
import json
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from server import runtime
import server.app as service


def test_status_never_invents_usage_cost_or_tasks():
    snap=runtime.status_snapshot(cloud_configured=False,model=None)
    assert snap["event"]=="runtime_status"
    assert snap["sayuri"]["active_jobs"]==0
    assert snap["sayuri"]["progress_percent"] is None
    assert snap["cloud_ru"]["cost_rub"] is None
    assert snap["cloud_ru"]["token_usage"] is None
    assert snap["cloud_ru"]["state"]=="unknown"
    assert snap["features"]["knowledge_graph"] is False


def test_actual_task_events_without_sensitive_payloads():
    with runtime.operation("studying","Анализ документа"):
        state=runtime.status_snapshot(cloud_configured=False)
        assert state["sayuri"]["state"]=="studying"
        assert state["sayuri"]["active_jobs"]>=1
    after=runtime.status_snapshot(cloud_configured=False)
    assert after["sayuri"]["state"] in ("completed","ready")
    assert "Анализ документа" in json.dumps(after["recent_events"],ensure_ascii=False)


def test_cloud_error_classifications():
    for status,expected in ((401,"auth_error"),(403,"auth_error"),
                            (402,"insufficient_balance"),(429,"rate_limited"),
                            (503,"degraded")):
        assert runtime._classify_error(status,"http")==expected
    assert runtime._classify_error(None,"timeout")=="timeout"


def test_runtime_is_owner_authenticated():
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",36100)) as client:
        assert client.get("/api/runtime/status").status_code==401
        assert client.get("/api/runtime/events").status_code==401


def test_sse_is_correctly_framed_and_never_exposes_key(monkeypatch):
    async def fake_refresh(**kwargs):
        return None
    monkeypatch.setattr(runtime,"refresh_probes",fake_refresh)
    class RequestMock:
        async def is_disconnected(self): return False
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",36100)) as client:
        session=client.post("/api/auth/local")
        assert session.status_code==200
        authorization="Bearer "+session.json()["token"]
        async def first_sse():
            response=await service.runtime_events(RequestMock(),authorization)
            iterator=response.body_iterator
            try:
                return await iterator.__anext__()
            finally:
                await iterator.aclose()
        frame=asyncio.run(first_sse())
        assert frame.startswith("event: runtime_status\\ndata: ")
        assert frame.endswith("\\n\\n")
        body=json.loads(frame.split("data: ",1)[1])
        assert body["event"]=="runtime_status"
        assert authorization not in frame
        assert "CLOUD_RU_API_KEY" not in frame


def test_probed_model_must_exist_in_cloud_catalog(monkeypatch):
    class DummyResponse:
        status_code=200
        def json(self):
            return {"data":[{"id":"deepseek-ai/DeepSeek-V4-Flash"}]}
    class DummyClient:
        def __init__(self,*a,**k): pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,*a,**k):return DummyResponse()
    monkeypatch.setattr(runtime.httpx,"AsyncClient",DummyClient)
    monkeypatch.setattr(runtime,"_CLOUD_NEXT",0.0)
    asyncio.run(runtime._probe_cloud("dummy-key","https://foundation-models.api.cloud.ru/v1","not-available/V4.1"))
    status=runtime.status_snapshot(cloud_configured=True,model="not-available/V4.1")
    assert status["cloud_ru"]["state"]=="degraded"
    assert "отсутствует" in status["cloud_ru"]["last_error"]
