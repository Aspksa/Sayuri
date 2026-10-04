"""Managed Documents move operations stay inside the local drive root."""
from fastapi.testclient import TestClient
import server.app as service


def _headers(client):
    login=client.post("/api/auth/local")
    assert login.status_code==200
    return {"Authorization":"Bearer "+login.json()["token"]}


def test_drive_move_rejects_self_descendants_and_lists_destinations(tmp_path,monkeypatch):
    monkeypatch.setattr(service,"managed_root",lambda:tmp_path)
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35623)) as client:
        assert client.get("/api/drive/folders").status_code==401
        headers=_headers(client)

        for parent,name in (("","A"),("","B"),("A","Nested")):
            response=client.post("/api/drive/folder",headers=headers,
                                 json={"parent":parent,"name":name})
            assert response.status_code==200,response.text

        blocked=client.post("/api/drive/move",headers=headers,
                            json={"path":"A","destination":"A/Nested"})
        assert blocked.status_code==400
        assert "внутрь самой себя" in blocked.json()["detail"]

        moved=client.post("/api/drive/move",headers=headers,
                          json={"path":"A/Nested","destination":"B"})
        assert moved.status_code==200,moved.text
        assert moved.json()=={"path":"B/Nested","moved":True}
        assert not (tmp_path/"A"/"Nested").exists()
        assert (tmp_path/"B"/"Nested").is_dir()

        same=client.post("/api/drive/move",headers=headers,
                         json={"path":"B/Nested","destination":"B"})
        assert same.status_code==200
        assert same.json()["moved"] is False

        folders=client.get("/api/drive/folders",headers=headers)
        assert folders.status_code==200
        paths={item["path"] for item in folders.json()["folders"]}
        assert {"","A","B","B/Nested"} <= paths
