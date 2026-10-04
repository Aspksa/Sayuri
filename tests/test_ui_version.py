"""Runtime build reports the real launched copy, not a guessed ZIP directory."""
from pathlib import Path
from fastapi.testclient import TestClient
import server.app as service


def test_running_build_is_private_and_matches_deployed_files():
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35613)) as client:
        assert client.get("/api/build/info").status_code == 401
        login=client.post("/api/auth/local")
        assert login.status_code == 200
        auth={"Authorization":"Bearer "+login.json()["token"]}
        response=client.get("/api/build/info",headers=auth)
        assert response.status_code == 200
        info=response.json()
        assert info["ui_version"] == "4.11.0"
        assert info["persona_version"] == "2.0.0"
        assert info["project_version"] == "4.11.0"
        assert info["core_version"] == "3.3.0"
        assert info["memory_version"] == "3.0.0"
        assert info["knowledge_version"] == "3.1.0"
        assert info["instinct_version"] == "3.2.0"
        assert info["teacher_understanding_version"] == "3.3.0"
        assert (Path(info["running_folder"])/"web"/"index.html").is_file()
        assert info["installation"] in ("zip","git")
