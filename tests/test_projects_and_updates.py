"""Local folder access and safe GitHub updater checks (no live network)."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import server.app as service
import server.paths as paths
import server.updating as updates

def test_cloud_folder_layout_and_legacy_memory(tmp_path,monkeypatch):
    home=tmp_path/"Documents"
    home.mkdir()
    monkeypatch.setenv("SAYURI_DOCUMENTS_DIR",str(home))
    monkeypatch.delenv("SAYURI_PROJECTS_DIR",raising=False)
    monkeypatch.delenv("SAYURI_DATA_DIR",raising=False)
    root=paths.cloud_root()
    assert root==home/"Облако"/"Sayuri"
    paths.ensure_project_folders(root)
    assert (root/"Рабочие проекты").is_dir()
    assert (root/"Домашние проекты").is_dir()
    repo=tmp_path/"repo"
    (repo/"data").mkdir(parents=True)
    (repo/"data"/"sayuri.sqlite3").write_bytes(b"existing-history")
    assert paths.data_root(repo)==repo/"data"

def test_project_folder_browsing_and_traversal(tmp_path,monkeypatch):
    root=tmp_path/"Документы"/"Облако"/"Sayuri"
    paths.ensure_project_folders(root)
    (root/"Рабочие проекты"/"note.txt").write_text("work",encoding="utf-8")
    (root/"Домашние проекты"/"ideas.txt").write_text("home",encoding="utf-8")
    monkeypatch.setattr(service,"PROJECT_ROOT",root)
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",32001)) as client:
        login=client.post("/api/auth/local")
        assert login.status_code==200,login.text
        h={"Authorization":"Bearer "+login.json()["token"]}
        project=client.get("/api/projects",headers=h)
        assert project.status_code==200
        assert all(item["available"] for item in project.json()["categories"])
        work=client.get("/api/projects/work/list",headers=h)
        assert any(x["name"]=="note.txt" for x in work.json()["items"])
        response=client.get("/api/projects/home/file",params={"path":"ideas.txt"},headers=h)
        assert response.status_code==200
        assert response.content==b"home"
        forbidden=client.get("/api/projects/work/file",params={"path":"../../private.txt"},headers=h)
        assert forbidden.status_code==403
        assert client.get("/api/projects/work/list",params={"path":"../"},headers=h).status_code==403

def test_updates_do_not_run_when_local_changes(tmp_path,monkeypatch):
    (tmp_path/".git").mkdir()
    calls=[]
    def fake_git(root,*args,**kwargs):
        calls.append(args)
        values={
            ("remote","get-url","origin"):"https://github.com/Aspksa/Sayuri.git",
            ("branch","--show-current"):"main",
            ("rev-parse","--show-toplevel"):str(root),
            ("status","--porcelain","--untracked-files=no"):" M web/index.html"
        }
        if args in values:return values[args]
        raise AssertionError("Unexpected command: "+repr(args))
    monkeypatch.setattr(updates,"_git",fake_git)
    with pytest.raises(updates.UpdateError,match="локальные изменения"):
        updates.apply_update(tmp_path)
    assert not any(call[0] in ("fetch","merge") for call in calls)
