"""Sayuri local drive: isolated cloud storage and authentic development diary."""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import server.app as sayuri
from server.drive import drive_path, DriveError


def _client_session(client):
    r=client.post("/api/auth/local")
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}


def test_drive_cloud_folders_and_private_separation(tmp_path,monkeypatch):
    root=tmp_path/"Облако"/"Sayuri"
    root.mkdir(parents=True)
    # Never expose secrets or the personal SQLite DB via drive routes.
    (root/"sayuri.sqlite3").write_bytes(b"private")
    (root/".env").write_text("CLOUD_RU_API_KEY=private",encoding="utf-8")
    monkeypatch.setattr(sayuri,"PROJECT_ROOT",root)
    with TestClient(sayuri.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",34567)) as client:
        h=_client_session(client)
        folders=client.get("/api/drive/list",headers=h)
        assert folders.status_code==200,folders.text
        assert folders.json()["items"]==[]
        created=client.post("/api/drive/folder",headers=h,json={"name":"Книги","parent":""})
        assert created.status_code==200,created.text
        data={"path":"Книги"}
        upload=client.post("/api/drive/upload",headers=h,data=data,
            files={"file":("notes.txt",b"Hello Sayuri","text/plain")})
        assert upload.status_code==200,upload.text
        listing=client.get("/api/drive/list",params={"path":"Книги"},headers=h)
        assert [f["name"] for f in listing.json()["items"]]==["notes.txt"]
        search=client.get("/api/drive/search",params={"q":"note"},headers=h)
        assert len(search.json()["items"])==1
        downloaded=client.get("/api/drive/download",params={"path":"Книги/notes.txt"},headers=h)
        assert downloaded.status_code==200 and downloaded.content==b"Hello Sayuri"
        rename=client.post("/api/drive/rename",headers=h,
                            json={"path":"Книги/notes.txt","new_name":"study.txt"})
        assert rename.status_code==200
        assert client.delete("/api/drive/item",params={"path":"Книги"},headers=h).status_code==409
        assert client.delete("/api/drive/item",params={"path":"Книги/study.txt"},headers=h).status_code==200
        assert client.delete("/api/drive/item",params={"path":"Книги"},headers=h).status_code==200
        assert client.get("/api/drive/download",params={"path":"../.env"},headers=h).status_code==400
        assert client.get("/api/drive/download",params={"path":"../sayuri.sqlite3"},headers=h).status_code==400


def test_drive_blocks_path_escape_and_symlinks(tmp_path):
    root=tmp_path/"files"
    root.mkdir()
    for path in ("../secrets",".env","folder/../hidden","C:/Windows/system.ini","CON","file\\..\\secret"):
        with pytest.raises(DriveError):
            drive_path(root,path,allow_root=False)
    outside=tmp_path/"outside"
    outside.mkdir()
    link=root/"link"
    try:link.symlink_to(outside,target_is_directory=True)
    except (OSError,NotImplementedError):pytest.skip("Symlinks require permissions")
    with pytest.raises(DriveError):drive_path(root,"link/secret.txt")


def test_development_summary_is_real_counts():
    with TestClient(sayuri.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",34568)) as client:
        headers=_client_session(client)
        before=client.get("/api/development/summary",headers=headers)
        assert before.status_code==200,before.text
        assert "assessment" in before.json()
        assert "messages" in before.json()["counts"]
        assert isinstance(before.json()["history"],list)
