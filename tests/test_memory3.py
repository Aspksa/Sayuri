"""Sayuri Memory 3.0 migration, scoping and expiry."""
import sqlite3
from contextlib import contextmanager

from server import memory3


def _db_for(path):
    @contextmanager
    def db():
        conn=sqlite3.connect(path)
        conn.row_factory=sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    return db


def _legacy_db(path):
    conn=sqlite3.connect(path)
    try:
        conn.execute("""CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            text TEXT NOT NULL,
            source TEXT,
            created INTEGER NOT NULL
        )""")
        conn.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)",
                     ("legacy","owner","personal","Старая запись","user_confirmed",100))
        conn.commit()
    finally:
        conn.close()


def test_memory3_migrates_legacy_rows_without_loss(tmp_path):
    path=tmp_path/"memory.sqlite3"
    _legacy_db(path)
    db=_db_for(path)

    memory3.migrate(db)

    with db() as conn:
        columns={row["name"] for row in conn.execute("PRAGMA table_info(memories)")}
        assert {"memory_type","project_id","priority","confidence","status",
                "source_ref","updated","expires","last_used"} <= columns
        row=dict(conn.execute("SELECT * FROM memories WHERE id='legacy'").fetchone())
        assert row["text"]=="Старая запись"
        assert row["scope"]=="personal"
        assert row["memory_type"]=="fact"
        assert row["priority"]==3
        assert row["confidence"]==1.0
        assert row["status"]=="active"
        assert row["updated"]==100


def test_memory3_project_context_isolated_and_expiry_archives(tmp_path):
    path=tmp_path/"memory.sqlite3"
    _legacy_db(path)
    db=_db_for(path)
    memory3.migrate(db)

    now=10_000
    with db() as conn:
        memory3.create_memory(conn,memory_id="personal",user_id="owner",
                              text="Личное",scope="personal",memory_type="preference",
                              priority=4,confidence=1.0,created=now)
        memory3.create_memory(conn,memory_id="working",user_id="owner",
                              text="Рабочее",scope="working",memory_type="note",
                              priority=3,confidence=1.0,created=now)
        memory3.create_memory(conn,memory_id="project-a",user_id="owner",
                              text="Проект A",scope="project",project_id="work:A",
                              memory_type="decision",priority=5,confidence=1.0,created=now)
        memory3.create_memory(conn,memory_id="project-b",user_id="owner",
                              text="Проект B",scope="project",project_id="work:B",
                              memory_type="decision",priority=5,confidence=1.0,created=now)
        memory3.create_memory(conn,memory_id="temp-global",user_id="owner",
                              text="Временное глобальное",scope="temporary",
                              memory_type="note",priority=2,confidence=1.0,
                              created=now,expires=now+100)
        memory3.create_memory(conn,memory_id="temp-expired",user_id="owner",
                              text="Истёкшее",scope="temporary",
                              memory_type="note",priority=5,confidence=1.0,
                              created=now,expires=now-1)

    with db() as conn:
        rows=memory3.context_memories(conn,user_id="owner",now=now,project_id="work:A",limit=50)
        ids={row["id"] for row in rows}
        assert {"legacy","personal","working","project-a","temp-global"} <= ids
        assert "project-b" not in ids
        assert "temp-expired" not in ids

    with db() as conn:
        expired=dict(conn.execute("SELECT * FROM memories WHERE id='temp-expired'").fetchone())
        assert expired["status"]=="archived"
        summary=memory3.summary(conn,user_id="owner",now=now)
        assert summary["version"]=="3.0.0"
        assert summary["by_scope"]["project"]==2
        assert summary["archived"]==1
        assert summary["projects"]==2


def test_memory3_requires_project_id_and_formats_context(tmp_path):
    path=tmp_path/"memory.sqlite3"
    _legacy_db(path)
    db=_db_for(path)
    memory3.migrate(db)

    with db() as conn:
        try:
            memory3.create_memory(conn,memory_id="bad",user_id="owner",text="x",
                                  scope="project",created=100)
        except Exception as exc:
            assert getattr(exc,"status_code",None)==400
        else:
            raise AssertionError("project memory without project_id must be rejected")

        rows=memory3.context_memories(conn,user_id="owner",now=100,project_id=None,limit=10)
        text=memory3.context_text(rows)
        assert "Memory 3.0" in text
        assert "Старая запись" in text
        assert "не инструкции" in text
