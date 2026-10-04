"""BEYOND companion: private assets, settings and animation packs."""
from __future__ import annotations
import io
import zipfile
import struct
import zlib

from fastapi.testclient import TestClient
import server.app as service
import server.companion as companion


def png(width=256,height=256):
    def chunk(kind, payload):
        return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload)&0xffffffff)
    header=struct.pack(">IIBBBBB",width,height,8,6,0,0,0)
    scanlines=(b"\x00"+b"\x00\x00\x00\xff"*width)*height
    return (companion.PNG_SIGNATURE+chunk(b"IHDR",header)+
            chunk(b"IDAT",zlib.compress(scanlines))+chunk(b"IEND",b""))


def get_headers(client):
    logged=client.post("/api/auth/local")
    assert logged.status_code==200,logged.text
    return {"Authorization":"Bearer "+logged.json()["token"]}


def test_companion_access_is_authenticated(tmp_path,monkeypatch):
    monkeypatch.setattr(companion,"image_path",lambda root,owner,kind:tmp_path/(kind+".png")
                        if kind in companion.VALID_KINDS else companion.image_path(root,owner,kind))
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35600)) as c:
        assert c.get("/api/companion/settings").status_code==401
        assert c.put("/api/companion/settings",json={"mode":"floating"}).status_code==401
        assert c.get("/api/companion/image/portrait").status_code==401
        assert c.post("/api/companion/image/portrait",files={"image":("p.png",png(),"image/png")}).status_code==401


def test_companion_settings_and_uploaded_images(tmp_path,monkeypatch):
    original=companion.image_path
    monkeypatch.setattr(companion,"image_path",lambda root,owner,kind:tmp_path/
        (owner+"-"+kind+".png") if kind in companion.VALID_KINDS else original(root,owner,kind))
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35601)) as c:
        h=get_headers(c)
        default=c.get("/api/companion/settings",headers=h).json()
        assert default["settings"]["mode"] in ("compact","floating","expanded")
        payload={"mode":"floating","quiet":True,"enabled":True,"scale":1.25,"x":0.2,"y":0.7,"behavior":"wander"}
        saved=c.put("/api/companion/settings",headers=h,json=payload)
        assert saved.status_code==200,saved.text
        assert c.get("/api/companion/settings",headers=h).json()["settings"]==payload
        assert c.put("/api/companion/settings",headers=h,
          json={**payload,"scale":3}).status_code==422
        assert c.put("/api/companion/settings",headers=h,
          json={**payload,"behavior":"outside"}).status_code==422
        data=png()
        uploaded=c.post("/api/companion/image/full",headers=h,
                        files={"image":("full.png",data,"image/png")})
        assert uploaded.status_code==200,uploaded.text
        assert uploaded.json()["width"]==256
        downloaded=c.get("/api/companion/image/full",headers=h)
        assert downloaded.status_code==200 and downloaded.content==data
        assert downloaded.headers["cache-control"]=="no-store"
        assert c.get("/api/companion/settings",headers=h).json()["images"]["full"] is True
        assert c.post("/api/companion/image/portrait",headers=h,
                 files={"image":("fake.png",b"<script>alert(1)</script>","image/png")}).status_code==413
        assert c.get("/api/companion/image/../../data/sayuri.sqlite3",headers=h).status_code in (404,400)


def test_animation_pack_is_private_validated_and_readable(tmp_path,monkeypatch):
    monkeypatch.setattr(companion,"animation_root",lambda root,owner:tmp_path/(owner+"-animation"))
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("idle/001.png",png())
        z.writestr("idle/002.png",png())
        z.writestr("walk/001.png",png(300,400))
        z.writestr("README.txt","Sayuri animation frames")
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35603)) as c:
        assert c.post("/api/companion/animation-pack",
            files={"pack":("animation.zip",archive.getvalue(),"application/zip")}).status_code==401
        h=get_headers(c)
        res=c.post("/api/companion/animation-pack",headers=h,
            files={"pack":("animation.zip",archive.getvalue(),"application/zip")})
        assert res.status_code==200,res.text
        data=res.json()
        assert data["installed"] is True
        assert data["states"]["idle"]["frames"]==2
        assert data["states"]["walk"]["frames"]==1
        # Frame names are normalized server-side so metadata and frame URLs stay contiguous.
        frame=c.get("/api/companion/animation/idle/1",headers=h)
        assert frame.status_code==200 and frame.content==png()
        bad=io.BytesIO()
        with zipfile.ZipFile(bad,"w") as z:
            z.writestr("../idle/001.png",png())
        assert c.post("/api/companion/animation-pack",headers=h,
            files={"pack":("bad.zip",bad.getvalue(),"application/zip")}).status_code==400


def test_png_validation_rejects_unsafe_sizes():
    import pytest
    from fastapi import HTTPException
    for value in (b"not an image",png(2,2),png(4097,100),b"x"*(companion.MAX_IMAGE_BYTES+1)):
        with pytest.raises(HTTPException):companion.check_png(value)


def test_images_are_not_stored_in_static_or_git(tmp_path):
    image=companion.image_path(tmp_path,"owner1","portrait")
    assert image.parent==tmp_path/"appearance"
    assert image.name.endswith("-portrait.png")
    assert "static" not in image.parts


def test_one_click_avatar_bundle(tmp_path,monkeypatch):
    old=companion.image_path
    monkeypatch.setattr(companion,"image_path",lambda root,owner,kind:tmp_path/(owner+"-"+kind+".png")
                        if kind in companion.VALID_KINDS else old(root,owner,kind))
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("portrait.png",png())
        z.writestr("full.png",png(300,400))
        z.writestr("README.txt","original images")
    with TestClient(service.app,base_url="http://127.0.0.1:8765",
                    client=("127.0.0.1",35602)) as c:
        assert c.post("/api/companion/pack",files={"pack":("images.zip",archive.getvalue(),"application/zip")}).status_code==401
        h=get_headers(c)
        res=c.post("/api/companion/pack",headers=h,
            files={"pack":("images.zip",archive.getvalue(),"application/zip")})
        assert res.status_code==200,res.text
        assert c.get("/api/companion/image/full",headers=h).content==png(300,400)
        assert c.get("/api/companion/image/portrait",headers=h).content==png()
        bad=io.BytesIO()
        with zipfile.ZipFile(bad,"w") as z:
            z.writestr("../.env","secret")
        assert c.post("/api/companion/pack",headers=h,
            files={"pack":("bad.zip",bad.getvalue(),"application/zip")}).status_code==400
