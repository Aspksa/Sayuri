"""ZIP downloads from the official GitHub repo never overwrite live Sayuri."""
import json
import sqlite3
import stat
import zipfile
from pathlib import Path
import pytest
from server import updating


SHA="0123456789abcdef0123456789abcdef01234567"


def _fake_zip(sha, destination):
    prefix="Sayuri-"+sha+"/"
    with zipfile.ZipFile(destination,"w") as archive:
        archive.writestr(prefix,"")
        archive.writestr(prefix+"Sayuri.bat","@echo off\necho new version\n")
        archive.writestr(prefix+"server/app.py","print('new version')\n")
        archive.writestr(prefix+"web/index.html","<title>Sayuri</title>")


def test_zip_update_prepares_sibling_and_preserves_owner(tmp_path,monkeypatch):
    root=tmp_path/"Sayuri-main"
    root.mkdir()
    (root/".env").write_text("CLOUD_RU_API_KEY=private-test-key\n",encoding="utf-8")
    db_dir=root/"data"
    db_dir.mkdir()
    db_path=db_dir/"sayuri.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE notes (value TEXT)")
        conn.execute("INSERT INTO notes VALUES ('owner memory')")
    (db_dir/"uploads").mkdir()
    (db_dir/"uploads"/"photo.txt").write_text("personal data")
    monkeypatch.delenv("SAYURI_DATA_DIR",raising=False)
    monkeypatch.delenv("SAYURI_PROJECTS_DIR",raising=False)
    monkeypatch.setattr(updating,"_github_head",lambda:SHA)
    monkeypatch.setattr(updating,"_download_archive",_fake_zip)
    status=updating.update_status(root)
    assert status["mode"]=="zip"
    assert status["update_available"]
    result=updating.apply_update(root)
    assert result["updated"] and result["mode"]=="zip"
    installed=Path(result["new_folder"])
    assert installed.is_dir()
    assert (installed/"server/app.py").read_text().startswith("print")
    assert (installed/".env").read_text()==(root/".env").read_text()
    assert (installed/"data/uploads/photo.txt").read_text()=="personal data"
    with sqlite3.connect(installed/"data/sayuri.sqlite3") as conn:
        assert conn.execute("SELECT value FROM notes").fetchone()[0]=="owner memory"
    assert (root/"data/sayuri.sqlite3").is_file()
    assert updating._installed_sha(installed)==SHA
    assert not updating.update_status(installed)["update_available"]
    again=updating.apply_update(root)
    assert again["new_folder"]==result["new_folder"]


def test_zip_rejects_escape_paths(tmp_path):
    zip_path=tmp_path/"archive.zip"
    with zipfile.ZipFile(zip_path,"w") as archive:
        archive.writestr("Sayuri-"+SHA+"/../outside.txt","malicious")
    dest=tmp_path/"new"
    dest.mkdir()
    with pytest.raises(updating.UpdateError):
        updating._extract_checked(zip_path,dest,SHA)
    assert not (tmp_path/"outside.txt").exists()


def test_zip_rejects_symlink(tmp_path):
    zip_path=tmp_path/"archive.zip"
    info=zipfile.ZipInfo("Sayuri-"+SHA+"/secretlink")
    info.create_system=3
    info.external_attr=(stat.S_IFLNK | 0o777)<<16
    with zipfile.ZipFile(zip_path,"w") as archive:
        archive.writestr(info,"../outside")
    dest=tmp_path/"new"
    dest.mkdir()
    with pytest.raises(updating.UpdateError):
        updating._extract_checked(zip_path,dest,SHA)
