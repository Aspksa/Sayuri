"""Scoped, local-only Sayuri cloud-style file manager (not a remote cloud sync)."""
from __future__ import annotations
from pathlib import Path, PurePosixPath
import os

MAX_UPLOAD_BYTES=25*1024*1024

class DriveError(ValueError):
    pass

def drive_root(project_root: Path) -> Path:
    base=project_root/"Мои файлы"
    if base.is_symlink():
        raise DriveError("Каталог документов не должен быть ссылкой")
    base.mkdir(parents=True,exist_ok=True)
    return base.resolve()

def _component(name: str) -> bool:
    if (not name or name in (".","..") or name.strip()!=name or
        name.endswith(".") or name.endswith(" ") or name.startswith(".")):
        return False
    if any(x in name for x in '/\\:<>|?*"\0'):
        return False
    if len(name)>150:
        return False
    base=name.split(".")[0].upper()
    if base in {"CON","PRN","AUX","NUL"} or
        (len(base)==4 and base[:3] in ("COM","LPT") and base[3:].isdigit()):
        return False
    return True

def drive_path(root: Path, relative: str="", *, allow_root=True) -> Path:
    if not isinstance(relative,str) or len(relative)>900:
        raise DriveError("Недопустимый путь")
    if relative in ("","."):
        if not allow_root: raise DriveError("Нельзя изменить корень")
        return root
    normalized=relative.replace("\\","/")
    path=PurePosixPath(normalized)
    if path.is_absolute() or not all(_component(part) for part in path.parts):
        raise DriveError("Недопустимый путь")
    current=root
    for part in path.parts:
        current=current/part
        if current.is_symlink():
            raise DriveError("Доступ через ссылки запрещён")
    target=current.resolve()
    if not target.is_relative_to(root.resolve()):
        raise DriveError("Доступ за пределы хранилища запрещён")
    return target

def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()

def list_folder(root: Path, relative: str) -> dict:
    directory=drive_path(root,relative)
    if not directory.is_dir(): raise FileNotFoundError("Папка не найдена")
    items=[]
    for item in sorted(directory.iterdir(),key=lambda p:(not p.is_dir(),p.name.casefold())):
        if item.is_symlink() or item.name.startswith("."):
            continue
        if not item.is_dir() and not item.is_file():
            continue
        items.append({"name":item.name,"path":relative_path(root,item),
                      "is_dir":item.is_dir(),"size":item.stat().st_size if item.is_file() else None})
        if len(items)>=500:break
    return {"path":relative,"items":items}

def search_files(root: Path, query: str) -> list[dict]:
    q=query.casefold().strip()
    if not q or len(q)>100:return []
    out=[]
    count=0
    for directory,subdirs,files in os.walk(root,followlinks=False):
        base=Path(directory)
        subdirs[:]=[d for d in subdirs if not d.startswith(".") and not (base/d).is_symlink()]
        for name in subdirs+files:
            target=base/name
            if name.startswith(".") or target.is_symlink():continue
            count+=1
            if q in name.casefold():
                out.append({"name":name,"path":relative_path(root,target),"is_dir":target.is_dir()})
            if count>=2000 or len(out)>=100:break
        if count>=2000 or len(out)>=100:break
    return out
