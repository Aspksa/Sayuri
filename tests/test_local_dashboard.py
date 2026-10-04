"""Password-free access is allowed only for local Windows use."""
import os
from fastapi.testclient import TestClient
from server.app import app

def test_local_dashboard_passwordless_session():
    os.environ["SAYURI_LOCAL_ACCESS"]="1"
    with TestClient(app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",51515)) as client:
        page=client.get("/")
        assert page.status_code==200
        assert 'id="gate"' not in page.text
        assert 'id="accountView"' in page.text
        assert 'id="newTeacher"' not in page.text
        assert 'id="threads"' not in page.text
        token=client.post("/api/auth/local",headers={"Origin":"http://127.0.0.1:8765"})
        assert token.status_code==200,token.text
        headers={"Authorization":"Bearer "+token.json()["token"]}
        assert client.get("/api/memory",headers=headers).status_code==200
        assert client.get("/api/chats",headers=headers).status_code==200
        denied=client.post("/api/auth/local",headers={"Origin":"https://other.example"})
        assert denied.status_code==403
        assert client.post("/api/auth/local",headers={"Sec-Fetch-Site":"cross-site"}).status_code==403
