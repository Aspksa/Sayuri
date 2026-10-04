"""Owner-private floating assistant appearance and preferences.

Images are stored exclusively under data/appearance, never in the GitHub repo.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import io
import zipfile
import re
import shutil
from pathlib import Path, PurePosixPath

from fastapi import File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

VALID_KINDS = frozenset({"portrait", "full"})
MAX_IMAGE_BYTES = 9 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ANIMATION_STATES = ("idle", "walk", "think", "read", "work", "happy", "attention", "sleep")
ANIMATION_FPS = {"idle": 4, "walk": 10, "think": 6, "read": 6, "work": 8,
                 "happy": 10, "attention": 10, "sleep": 3}
MAX_ANIMATION_PACK_BYTES = 40 * 1024 * 1024
MAX_ANIMATION_UNPACKED_BYTES = 80 * 1024 * 1024
MAX_ANIMATION_FRAMES_PER_STATE = 24
MAX_ANIMATION_TOTAL_FRAMES = 96
ANIMATION_FRAME_RE = re.compile(r"^[0-9]{3}\.png$")


class CompanionSettings(BaseModel):
    mode: str = Field(default="compact", pattern="^(compact|floating|expanded)$")
    quiet: bool = False
    enabled: bool = True
    behavior: str = Field(default="stationary", pattern="^(stationary|wander|follow|event)$")
    presence: str = Field(default="normal", pattern="^(calm|normal|lively)$")
    voice_important: bool = True
    scale: float = Field(default=1.0, ge=0.7, le=1.4)
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)


def init_companion_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS companion_settings "
        "(user_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated INTEGER NOT NULL)"
    )


def image_path(data_root: Path, owner: str, kind: str) -> Path:
    if kind not in VALID_KINDS:
        raise HTTPException(404, "Вид изображения не поддерживается")
    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]
    return (data_root / "appearance" / (digest + "-" + kind + ".png")).resolve()


def animation_root(data_root: Path, owner: str) -> Path:
    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]
    return (data_root / "appearance" / (digest + "-animation")).resolve()


def animation_metadata(data_root: Path, owner: str) -> dict:
    root = animation_root(data_root, owner)
    states = {}
    if root.is_dir():
        for state in ANIMATION_STATES:
            folder = root / state
            frames = sorted(folder.glob("*.png")) if folder.is_dir() else []
            if frames:
                states[state] = {"frames": len(frames), "fps": ANIMATION_FPS[state]}
    return {"installed": bool(states), "states": states}


def check_png(content: bytes) -> tuple[int, int]:
    """Signature and IHDR dimensions, not an image decoder or HTML sanitizer."""
    if len(content) < 33 or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Изображение должно быть PNG до 9 МБ")
    if content[:8] != PNG_SIGNATURE or content[12:16] != b"IHDR":
        raise HTTPException(400, "Поддерживается только PNG")
    width, height = struct.unpack(">II", content[16:24])
    if not (128 <= width <= 4096 and 128 <= height <= 4096):
        raise HTTPException(400, "Размер изображения должен быть от 128 до 4096 пикселей")
    if content[25] not in (2, 3, 4, 6, 0):
        raise HTTPException(400, "Неподдерживаемый формат PNG")
    return width, height


def register_companion_routes(app, *, auth, db, data_root: Path, stamp):
    from fastapi import Header

    @app.get("/api/build/info")
    def read_local_build(authorization: str | None = Header(None)):
        auth(authorization)
        app_root = Path(__file__).resolve().parents[1]
        try:
            info = json.loads((app_root / "web" / "build.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        return {
            "ui_version": info.get("ui_version", "неизвестно"),
            "persona_version": info.get("persona_version", "2.0.0"),
            "running_folder": str(app_root),
            "installation": "git" if (app_root / ".git").exists() else "zip",
        }

    @app.get("/api/companion/settings")
    def read_companion_settings(authorization: str | None = Header(None)):
        owner = auth(authorization)
        with db() as conn:
            init_companion_table(conn)
            row = conn.execute(
                "SELECT payload FROM companion_settings WHERE user_id=?", (owner,)
            ).fetchone()
        settings = json.loads(row["payload"]) if row else CompanionSettings().model_dump()
        return {
            "settings": CompanionSettings.model_validate(settings).model_dump(),
            "images": {kind: image_path(data_root, owner, kind).is_file() for kind in VALID_KINDS},
        }

    @app.put("/api/companion/settings")
    def write_companion_settings(
        settings: CompanionSettings, authorization: str | None = Header(None)
    ):
        owner = auth(authorization)
        with db() as conn:
            init_companion_table(conn)
            conn.execute(
                "INSERT INTO companion_settings(user_id,payload,updated) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload, updated=excluded.updated",
                (owner, settings.model_dump_json(), stamp()),
            )
        return {"settings": settings.model_dump()}

    @app.post("/api/companion/image/{kind}")
    async def upload_companion_image(
        kind: str, image: UploadFile = File(...), authorization: str | None = Header(None)
    ):
        owner = auth(authorization)
        path = image_path(data_root, owner, kind)
        # Bounded read; reject oversized files before writing to disk.
        payload = await image.read(MAX_IMAGE_BYTES + 1)
        width, height = check_png(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("wb") as output:
                output.write(payload)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {"kind": kind, "width": width, "height": height}

    @app.post("/api/companion/pack")
    async def upload_companion_pack(
        pack: UploadFile = File(...), authorization: str | None = Header(None)
    ):
        owner = auth(authorization)
        # Only the two expected names may be present; no paths, links or code.
        content = await pack.read(18 * 1024 * 1024 + 1)
        if len(content) > 18 * 1024 * 1024:
            raise HTTPException(413, "Комплект Саюри больше 18 МБ")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = [item.filename for item in archive.infolist()
                         if not item.is_dir()]
                if sorted(names) not in (
                    ["full.png", "portrait.png"],
                    ["README.txt", "full.png", "portrait.png"]
                ):
                    raise HTTPException(400, "В архиве нужны portrait.png и full.png")
                images = {}
                for kind in ("portrait", "full"):
                    item = archive.getinfo(kind + ".png")
                    if item.file_size > MAX_IMAGE_BYTES:
                        raise HTTPException(413, "Изображение превышает 9 МБ")
                    payload = archive.read(item)
                    check_png(payload)
                    images[kind] = payload
        except (zipfile.BadZipFile, KeyError) as exc:
            raise HTTPException(400, "Некорректный ZIP-комплект") from exc
        # Validate both before writing. Existing appearance files remain intact
        # if the supplied ZIP is corrupt.
        for kind, payload in images.items():
            path = image_path(data_root, owner, kind)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            try:
                with temporary.open("wb") as output:
                    output.write(payload)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return {"ok": True, "images": ["portrait", "full"]}

    @app.get("/api/companion/image/{kind}")
    def get_companion_image(kind: str, authorization: str | None = Header(None)):
        owner = auth(authorization)
        path = image_path(data_root, owner, kind)
        if not path.is_file():
            raise HTTPException(404, "Изображение ещё не загружено")
        return FileResponse(path, media_type="image/png",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


    @app.get("/api/companion/animation")
    def read_animation_pack(authorization: str | None = Header(None)):
        owner = auth(authorization)
        return animation_metadata(data_root, owner)

    @app.post("/api/companion/animation-pack")
    async def upload_animation_pack(
        pack: UploadFile = File(...), authorization: str | None = Header(None)
    ):
        owner = auth(authorization)
        content = await pack.read(MAX_ANIMATION_PACK_BYTES + 1)
        if len(content) > MAX_ANIMATION_PACK_BYTES:
            raise HTTPException(413, "Пакет анимаций больше 40 МБ")
        frames: dict[str, list[tuple[str, bytes]]] = {}
        total_frames = 0
        total_unpacked = 0
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    raw = item.filename.replace("\\", "/")
                    if raw == "README.txt":
                        continue
                    path = PurePosixPath(raw)
                    if path.is_absolute() or ".." in path.parts or len(path.parts) != 2:
                        raise HTTPException(400, "Недопустимый путь в пакете анимаций")
                    state, filename = path.parts
                    if state not in ANIMATION_STATES or not ANIMATION_FRAME_RE.fullmatch(filename):
                        raise HTTPException(
                            400, "Кадры должны иметь вид idle/001.png, walk/001.png и т. д."
                        )
                    bucket = frames.setdefault(state, [])
                    if len(bucket) >= MAX_ANIMATION_FRAMES_PER_STATE:
                        raise HTTPException(400, "Не больше 24 кадров на одно состояние")
                    total_frames += 1
                    total_unpacked += item.file_size
                    if total_frames > MAX_ANIMATION_TOTAL_FRAMES:
                        raise HTTPException(400, "В пакете не должно быть больше 96 кадров")
                    if total_unpacked > MAX_ANIMATION_UNPACKED_BYTES:
                        raise HTTPException(413, "Распакованный пакет анимаций больше 80 МБ")
                    if item.file_size > MAX_IMAGE_BYTES:
                        raise HTTPException(413, "Один кадр анимации превышает 9 МБ")
                    payload = archive.read(item)
                    check_png(payload)
                    bucket.append((filename, payload))
        except (zipfile.BadZipFile, KeyError) as exc:
            raise HTTPException(400, "Некорректный ZIP-пакет анимаций") from exc
        if not frames:
            raise HTTPException(400, "В пакете нет кадров анимации")

        target = animation_root(data_root, owner)
        temporary = target.with_name(target.name + ".tmp")
        backup = target.with_name(target.name + ".bak")
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        temporary.mkdir(parents=True, exist_ok=True)
        try:
            for state, items in frames.items():
                folder = temporary / state
                folder.mkdir(parents=True, exist_ok=True)
                for index, (_, payload) in enumerate(sorted(items), start=1):
                    (folder / f"{index:03d}.png").write_bytes(payload)
            if target.exists():
                os.replace(target, backup)
            os.replace(temporary, target)
            shutil.rmtree(backup, ignore_errors=True)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        return animation_metadata(data_root, owner)

    @app.get("/api/companion/animation/{state}/{frame}")
    def get_animation_frame(
        state: str, frame: int, authorization: str | None = Header(None)
    ):
        owner = auth(authorization)
        if state not in ANIMATION_STATES or frame < 1 or frame > MAX_ANIMATION_FRAMES_PER_STATE:
            raise HTTPException(404, "Кадр анимации не найден")
        path = animation_root(data_root, owner) / state / f"{frame:03d}.png"
        if not path.is_file():
            raise HTTPException(404, "Кадр анимации не найден")
        return FileResponse(path, media_type="image/png",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
