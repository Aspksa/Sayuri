"""Owner-private floating assistant appearance and preferences.

Images are stored exclusively under data/appearance, never in the GitHub repo.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

from fastapi import File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

VALID_KINDS = frozenset({"portrait", "full"})
MAX_IMAGE_BYTES = 9 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class CompanionSettings(BaseModel):
    mode: str = Field(default="compact", pattern="^(compact|floating|expanded)$")
    quiet: bool = False
    enabled: bool = True
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

    @app.get("/api/companion/image/{kind}")
    def get_companion_image(kind: str, authorization: str | None = Header(None)):
        owner = auth(authorization)
        path = image_path(data_root, owner, kind)
        if not path.is_file():
            raise HTTPException(404, "Изображение ещё не загружено")
        return FileResponse(path, media_type="image/png",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
