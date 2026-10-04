"""Opt-in, fast-forward-only Sayuri updater. Only the owner's GitHub repository."""
from __future__ import annotations
import re
import shutil
import subprocess
import threading
import json
import os
import tempfile
import urllib.request
import urllib.error
import zipfile
import stat
from pathlib import Path

REMOTE="https://github.com/Aspksa/Sayuri.git"
API_URL="https://api.github.com/repos/Aspksa/Sayuri/commits/main"
ZIP_BASE="https://codeload.github.com/Aspksa/Sayuri/zip/"
SOURCE_MARKER=".sayuri-source.json"
UPDATE_LOCK=threading.Lock()

class UpdateError(Exception):
    pass

def _git(root: Path,*args: str,timeout: int=30) -> str:
    try:
        p=subprocess.run(["git",*args],cwd=root,text=True,encoding="utf-8",
                         errors="replace",capture_output=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise UpdateError("Git недоступен или истекло время ожидания") from exc
    if p.returncode:
        raise UpdateError("Команда Git не выполнена: "+(" ".join(args[:2])))
    return p.stdout.strip()

def _validate_checkout(root: Path) -> None:
    if not (root/".git").exists():
        raise UpdateError("Это ZIP-копия, не Git-клон. Скачайте новую версию с GitHub вручную, сохранив .env и данные.")
    actual=_git(root,"remote","get-url","origin")
    # Only HTTPS to the exact repository prevents updates from an altered origin.
    if actual.rstrip("/").removesuffix(".git").lower()!=REMOTE.removesuffix(".git").lower():
        raise UpdateError("Origin Git не совпадает с github.com/Aspksa/Sayuri")
    if _git(root,"branch","--show-current")!="main":
        raise UpdateError("Обновление доступно только из ветки main")
    if _git(root,"rev-parse","--show-toplevel").replace("\\","/").casefold()!=str(root.resolve()).replace("\\","/").casefold():
        raise UpdateError("Корневой каталог Git не совпадает с каталогом приложения")

def _revision(root: Path) -> str:
    return _git(root,"rev-parse","HEAD")

def git_update_status(root: Path) -> dict:
    _validate_checkout(root)
    local=_revision(root)
    remote=_git(root,"ls-remote","--heads","origin","main",timeout=25)
    match=re.fullmatch(r"([0-9a-fA-F]{40})\s+refs/heads/main",remote)
    if not match:
        raise UpdateError("В GitHub не найдена ветка main")
    head=match.group(1)
    clean=not bool(_git(root,"status","--porcelain","--untracked-files=no"))
    return {"local":local[:12],"latest":head[:12],
            "update_available":local!=head,"clean":clean,
            "repository":"https://github.com/Aspksa/Sayuri"}

def apply_git_update(root: Path) -> dict:
    if not UPDATE_LOCK.acquire(blocking=False):
        raise UpdateError("Другое обновление уже выполняется")
    try:
        _validate_checkout(root)
        if _git(root,"status","--porcelain","--untracked-files=no"):
            raise UpdateError("Обнаружены локальные изменения кода. Обновление не выполняется.")
        old=_revision(root)
        _git(root,"fetch","origin","main",timeout=120)
        new=_git(root,"rev-parse","FETCH_HEAD")
        if new==old:
            return {"updated":False,"restart_required":False,"version":old[:12]}
        # exit status 1 => no fast-forward; never merge or overwrite edits.
        _git(root,"merge-base","--is-ancestor",old,new)
        # Snapshot must complete BEFORE any code change.
        from backup import main as create_backup
        if create_backup()!=0:
            raise UpdateError("Не удалось создать резервную копию; обновление отменено")
        _git(root,"merge","--ff-only",new,timeout=120)
        return {"updated":True,"restart_required":True,
                "version":new[:12],"message":"Обновление загружено. Перезапустите Sayuri.bat."}
    finally:
        UPDATE_LOCK.release()

def _github_head() -> str:
    request=urllib.request.Request(
        API_URL,headers={"User-Agent":"Sayuri-local-updater/2.0","Accept":"application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(request,timeout=25) as response:
            data=json.load(response)
    except (urllib.error.URLError,TimeoutError,ValueError,OSError) as exc:
        raise UpdateError("Не удалось связаться с GitHub") from exc
    sha=data.get("sha")
    if not isinstance(sha,str) or not re.fullmatch(r"[0-9a-fA-F]{40}",sha):
        raise UpdateError("GitHub вернул неверную ревизию")
    return sha.lower()


def _installed_sha(root: Path) -> str | None:
    try:
        info=json.loads((root/SOURCE_MARKER).read_text(encoding="utf-8"))
        sha=info.get("sha")
        if isinstance(sha,str) and re.fullmatch(r"[0-9a-fA-F]{40}",sha):
            return sha.lower()
    except (OSError,ValueError):
        pass
    return None


def update_status(root: Path) -> dict:
    if (root/".git").exists():
        result=git_update_status(root)
        result["mode"]="git"
        result["supported"]=True
        return result
    installed=_installed_sha(root)
    head=_github_head()
    return {"mode":"zip","supported":True,"local":installed[:12] if installed else "ZIP (неизвестна)",
            "latest":head[:12],"update_available":installed!=head,
            "clean":True,"repository":"https://github.com/Aspksa/Sayuri",
            "note":"ZIP обновляется в новой папке. Текущая программа и история не заменяются."}


def _download_archive(sha: str, destination: Path) -> None:
    request=urllib.request.Request(
        ZIP_BASE+sha,headers={"User-Agent":"Sayuri-local-updater/2.0"}
    )
    total=0
    try:
        with urllib.request.urlopen(request,timeout=75) as src, destination.open("wb") as out:
            if src.geturl().startswith("http://"):
                raise UpdateError("Небезопасная переадресация архива")
            while True:
                chunk=src.read(1024*1024)
                if not chunk:break
                total+=len(chunk)
                if total>40*1024*1024:
                    raise UpdateError("Архив GitHub превышает ограничение 40 МБ")
                out.write(chunk)
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise UpdateError("Не удалось скачать ZIP с GitHub") from exc


def _extract_checked(archive: Path, destination: Path, sha: str) -> None:
    """No traversal, symlinks, device entries, hidden secrets or unbounded ZIP files."""
    allowed_root=destination.resolve()
    expanded=0
    with zipfile.ZipFile(archive) as zip_file:
        entries=zip_file.infolist()
        if len(entries)>3000:raise UpdateError("Слишком много файлов в ZIP")
        for entry in entries:
            full=entry.filename.replace("\\","/")
            pieces=full.rstrip("/").split("/")
            if len(pieces)==1 and pieces[0]=="Sayuri-"+sha and entry.is_dir():
                continue
            if len(pieces)<2 or pieces[0] != "Sayuri-"+sha:
                # Pinned GitHub archives normally use Sayuri-<SHA>.
                raise UpdateError("Неожиданная структура ZIP")
            relative=Path(*pieces[1:])
            if not relative.parts or any(p in (".","..","") for p in relative.parts):
                raise UpdateError("Недопустимый путь файла")
            if relative.parts[0] in {".git",".venv","data","__pycache__"} or relative.name==".env":
                raise UpdateError("Архив содержит приватные каталоги или ключи")
            mode=entry.external_attr>>16
            if stat.S_ISLNK(mode):
                raise UpdateError("В ZIP запрещены символические ссылки")
            expanded+=entry.file_size
            if expanded>150*1024*1024 or entry.file_size>15*1024*1024:
                raise UpdateError("ZIP содержит слишком большие файлы")
            target=(destination/relative).resolve()
            if not target.is_relative_to(allowed_root):
                raise UpdateError("Недопустимый путь ZIP")
            if entry.is_dir():
                target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with zip_file.open(entry) as src, target.open("wb") as out:
                    shutil.copyfileobj(src,out,1024*1024)
    if not (destination/"Sayuri.bat").is_file() or not (destination/"server"/"app.py").is_file():
        raise UpdateError("В ZIP отсутствуют обязательные файлы Sayuri")


def _transfer_local_state(root: Path, destination: Path) -> None:
    """Copy only known user state. Reject links rather than following private targets."""
    for name in (".env","data"):
        source=root/name
        if not source.exists():continue
        if source.is_symlink():
            raise UpdateError("Локальные настройки нельзя переносить через ссылки")
        if name==".env":
            if not source.is_file():raise UpdateError("Неверный локальный .env")
            shutil.copy2(source,destination/name)
            continue
        if not source.is_dir():
            raise UpdateError("Неверный локальный каталог data")
        for child in source.rglob("*"):
            if child.is_symlink():
                raise UpdateError("В локальных данных обнаружена ссылка: перенос остановлен")
        shutil.copytree(source,destination/name,symlinks=False)
    # External SAYURI_DATA_DIR and SAYURI_PROJECTS_DIR stay referenced by copied .env.


def prepare_zip_update(root: Path) -> dict:
    """Safe ZIP update: create a sibling runnable folder, never overwrite a live server."""
    root=root.resolve()
    if not UPDATE_LOCK.acquire(blocking=False):
        raise UpdateError("Обновление уже выполняется")
    try:
        if (root/".git").exists():
            return apply_git_update(root)
        head=_github_head()
        if _installed_sha(root)==head:
            return {"updated":False,"restart_required":False,"version":head[:12]}
        output=root.parent/(root.name+"-new-"+head[:12])
        if output.exists():
            raise UpdateError("Папка новой версии уже существует: "+output.name)
        # Make an independent backup of the currently used SQLite and attachments.
        from backup import main as backup
        if backup()!=0:
            raise UpdateError("Сначала создайте базу/архив через Sayuri-backup.bat")
        with tempfile.TemporaryDirectory(prefix="sayuri-zip-",dir=root.parent) as work:
            archive=Path(work)/"source.zip"
            stage=Path(work)/"new"
            stage.mkdir()
            _download_archive(head,archive)
            # GitHub's ZIP prefix is Sayuri-<full 40 char SHA>.
            _extract_checked(archive,stage,head)
            _transfer_local_state(root,stage)
            (stage/SOURCE_MARKER).write_text(json.dumps({
                "sha":head,"repository":"https://github.com/Aspksa/Sayuri",
                "installation":"zip"
            }),encoding="utf-8")
            os.replace(stage,output)
        return {"updated":True,"restart_required":True,"mode":"zip",
                "version":head[:12],"new_folder":str(output),
                "message":"Новая Sayuri подготовлена рядом с текущей. Закройте старую программу и запустите Sayuri.bat в новой папке."}
    except (OSError,zipfile.BadZipFile,shutil.Error) as exc:
        raise UpdateError("Не удалось подготовить ZIP-обновление") from exc
    finally:
        UPDATE_LOCK.release()


def apply_update(root: Path) -> dict:
    if (root/".git").exists():
        return apply_git_update(root)
    return prepare_zip_update(root)
