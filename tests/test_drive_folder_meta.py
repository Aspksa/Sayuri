"""Folder Identity metadata follows local folder operations."""
import sqlite3
from fastapi.testclient import TestClient
import server.app as service


def _prepare_db(path):
    conn=sqlite3.connect(path)
    try:
        conn.executescript("""
        CREATE TABLE users (id TEXT PRIMARY KEY, salt TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE tokens (hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE drive_folder_meta (
            user_id TEXT NOT NULL,
            path TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT 'folder',
            color TEXT NOT NULL DEFAULT 'violet',
            description TEXT NOT NULL DEFAULT '',
            updated INTEGER NOT NULL,
            PRIMARY KEY (user_id,path)
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _headers(client):
    login=client.post("/api/auth/local")
    assert login.status_code==200,login.text
    return {"Authorization":"Bearer "+login.json()["token"]}


def test_folder_identity_survives_rename_and_move(tmp_path,monkeypatch):
    root=tmp_path/"drive";root.mkdir()
    db_path=tmp_path/"meta.sqlite3";_prepare_db(db_path)
    monkeypatch.setattr(service,"DB",db_path)
    monkeypatch.setattr(service,"managed_root",lambda:root)

    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35624)) as client:
        headers=_headers(client)
        for parent,name in (("","A"),("A","Nested"),("","B")):
            response=client.post("/api/drive/folder",headers=headers,
                                 json={"parent":parent,"name":name})
            assert response.status_code==200,response.text

        meta={"path":"A","icon":"project","color":"blue","description":"Главный проект"}
        saved=client.put("/api/drive/folder-meta",headers=headers,json=meta)
        assert saved.status_code==200,saved.text
        nested=client.put("/api/drive/folder-meta",headers=headers,json={
            "path":"A/Nested","icon":"research","color":"green","description":"Исследования"})
        assert nested.status_code==200,nested.text

        listing=client.get("/api/drive/list",headers=headers)
        a=next(item for item in listing.json()["items"] if item["name"]=="A")
        assert a["folder_meta"]["icon"]=="project"
        assert a["folder_meta"]["color"]=="blue"

        renamed=client.post("/api/drive/rename",headers=headers,
                            json={"path":"A","new_name":"Alpha"})
        assert renamed.status_code==200,renamed.text
        assert client.get("/api/drive/folder-meta",headers=headers,
                          params={"path":"Alpha"}).json()["description"]=="Главный проект"
        assert client.get("/api/drive/folder-meta",headers=headers,
                          params={"path":"Alpha/Nested"}).json()["icon"]=="research"

        moved=client.post("/api/drive/move",headers=headers,
                          json={"path":"Alpha","destination":"B"})
        assert moved.status_code==200,moved.text
        current=client.get("/api/drive/folder-meta",headers=headers,
                           params={"path":"B/Alpha/Nested"})
        assert current.status_code==200,current.text
        assert current.json()["color"]=="green"

        deleted=client.delete("/api/drive/item",headers=headers,
                              params={"path":"B/Alpha/Nested"})
        assert deleted.status_code==200,deleted.text
        with service.db() as conn:
            assert conn.execute(
                "SELECT 1 FROM drive_folder_meta WHERE user_id='owner' AND path='B/Alpha/Nested'"
            ).fetchone() is None


def test_folder_identity_rejects_invalid_values(tmp_path,monkeypatch):
    root=tmp_path/"drive";root.mkdir();(root/"Folder").mkdir()
    db_path=tmp_path/"meta.sqlite3";_prepare_db(db_path)
    monkeypatch.setattr(service,"DB",db_path)
    monkeypatch.setattr(service,"managed_root",lambda:root)

    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35625)) as client:
        headers=_headers(client)
        bad=client.put("/api/drive/folder-meta",headers=headers,json={
            "path":"Folder","icon":"danger","color":"blue","description":""})
        assert bad.status_code==422
        missing=client.put("/api/drive/folder-meta",headers=headers,json={
            "path":"Missing","icon":"folder","color":"violet","description":""})
        assert missing.status_code==404
