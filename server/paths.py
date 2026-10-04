"""Windows Documents/Облако/Sayuri location; supports redirected Documents folders."""
from __future__ import annotations
import os
from pathlib import Path

def documents_directory() -> Path:
    configured=os.getenv("SAYURI_DOCUMENTS_DIR","").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name=="nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                value,_=winreg.QueryValueEx(k,"Personal")
                return Path(os.path.expandvars(value)).expanduser().resolve()
        except (OSError,ValueError):
            pass
    home=Path.home()
    for name in ("Documents","Документы"):
        candidate=home/name
        if candidate.is_dir():
            return candidate.resolve()
    return (home/"Documents").resolve()

def cloud_root() -> Path:
    manual=os.getenv("SAYURI_PROJECTS_DIR","").strip()
    if manual:
        return Path(manual).expanduser().resolve()
    return (documents_directory()/"Облако"/"Sayuri").resolve()

def data_root(repo_root: Path) -> Path:
    explicit=os.getenv("SAYURI_DATA_DIR","").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    cloud=cloud_root()
    # Never hide an existing owner's conversations or force a destructive migration.
    legacy=(repo_root/"data").resolve()
    if (legacy/"sayuri.sqlite3").exists() and not (cloud/"sayuri.sqlite3").exists():
        return legacy
    return cloud

def ensure_project_folders(root: Path) -> None:
    for folder in ("Рабочие проекты","Домашние проекты"):
        base=root/folder
        if base.exists() and (base.is_symlink() or not base.is_dir()):
            raise RuntimeError("Небезопасная папка проекта: "+str(base))
        base.mkdir(parents=True,exist_ok=True)
