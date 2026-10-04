"""Find a *reachable* Documents directory; never assume OneDrive is mounted."""
from __future__ import annotations

import os
from pathlib import Path


def _usable(path: Path) -> bool:
    """Only adopt existing directories; don't create a missing OneDrive tree."""
    try:
        return path.is_dir() and not path.is_symlink()
    except OSError:
        return False


def documents_directory() -> Path:
    configured = os.getenv("SAYURI_DOCUMENTS_DIR", "").strip()
    if configured:
        # Explicit owner choice: fail visibly on a bad path rather than redirect silently.
        return Path(configured).expanduser().resolve()

    home = Path.home()
    choices = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                location, _ = winreg.QueryValueEx(key, "Personal")
                choices.append(Path(os.path.expandvars(location)).expanduser())
        except (OSError, ValueError):
            pass
    choices += [home / "Documents", home / "Документы"]
    for candidate in choices:
        if _usable(candidate):
            return candidate.resolve()
    # A missing redirected OneDrive folder is NOT a reason to create it.
    # Use local user Documents if it is not present yet.
    return (home / "Documents").resolve()


def cloud_root() -> Path:
    configured = os.getenv("SAYURI_PROJECTS_DIR", "").strip()
    return (Path(configured).expanduser() if configured else documents_directory() / "Облако" / "Sayuri").resolve()


def data_root(repo_root: Path) -> Path:
    selected = os.getenv("SAYURI_DATA_DIR", "").strip()
    if selected:
        return Path(selected).expanduser().resolve()
    cloud = cloud_root()
    legacy = (repo_root / "data").resolve()
    # The original profile remains authoritative for existing installations.
    # Never switch between databases just because a cloud folder later appears.
    if (legacy / "sayuri.sqlite3").is_file():
        return legacy
    if (cloud / "sayuri.sqlite3").is_file():
        return cloud
    # On first launch make only the intended path; server.app may fall back if
    # file access is denied or the directory disappears during startup.
    return cloud


def prepare_data_dir(repo_root: Path) -> Path:
    root = data_root(repo_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError:
        if os.getenv("SAYURI_DATA_DIR", "").strip():
            raise  # Do not redirect an explicitly selected private data path.
        fallback = (repo_root / "data").resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def ensure_project_folders(root: Path) -> None:
    if root.is_symlink():
        raise OSError("Проектный каталог не может быть символической ссылкой")
    root.mkdir(parents=True, exist_ok=True)
    for folder in ("Рабочие проекты", "Домашние проекты"):
        candidate = root / folder
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
            raise OSError("Небезопасная папка проекта: " + str(candidate))
        candidate.mkdir(parents=True, exist_ok=True)


def prepare_project_root(repo_root: Path) -> Path:
    """Make scoped project folders, never force creation in a missing OneDrive tree."""
    wanted = cloud_root()
    try:
        ensure_project_folders(wanted)
        return wanted
    except OSError:
        if os.getenv("SAYURI_PROJECTS_DIR", "").strip():
            raise  # An explicitly configured location must not be silently ignored.
        fallback = (repo_root / "data" / "projects").resolve()
        ensure_project_folders(fallback)
        return fallback
