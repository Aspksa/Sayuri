"""Create an offline SQLite-safe backup of Sayuri's database and uploads."""
from __future__ import annotations
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATA = Path(os.getenv("SAYURI_DATA_DIR") or ROOT / "data").expanduser().resolve()

def main():
    database=DATA / "sayuri.sqlite3"
    if not database.is_file():
        print("Sayuri: база данных ещё не создана")
        return 1
    dest=DATA / "backups"
    dest.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output=dest / ("sayuri-backup-"+stamp+".zip")
    # Online backup API safely copies SQLite WAL changes.
    with tempfile.TemporaryDirectory() as tmp:
        snapshot=Path(tmp)/"sayuri.sqlite3"
        source=sqlite3.connect(database)
        target=sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            archive.write(snapshot,"sayuri.sqlite3")
            uploads=DATA/"uploads"
            if uploads.exists():
                for f in uploads.rglob("*"):
                    if f.is_file() and not f.is_symlink():
                        archive.write(f,"uploads/"+f.relative_to(uploads).as_posix())
    print("Резервная копия создана:",output)
    print("Важно: архив не зашифрован. Храните его как личные данные.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
