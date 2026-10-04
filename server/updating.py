"""Opt-in, fast-forward-only Sayuri updater. Only the owner's GitHub repository."""
from __future__ import annotations
import re
import shutil
import subprocess
import threading
from pathlib import Path

REMOTE="https://github.com/Aspksa/Sayuri.git"
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

def update_status(root: Path) -> dict:
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

def apply_update(root: Path) -> dict:
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
