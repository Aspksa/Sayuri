"""Sayuri Knowledge Engine 3.1 local search, graph and conflict review."""
import sqlite3
from contextlib import contextmanager

from server import memory3, knowledge31


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


def _prepare(path):
    conn=sqlite3.connect(path)
    try:
        conn.execute("""CREATE TABLE memories (
            id TEXT PRIMARY KEY,user_id TEXT NOT NULL,scope TEXT NOT NULL,
            text TEXT NOT NULL,source TEXT,created INTEGER NOT NULL
        )""")
        conn.commit()
    finally:
        conn.close()
    db=_db_for(path)
    memory3.migrate(db)
    knowledge31.migrate(db)
    return db


def _add(conn,mid,text,*,scope="personal",project_id=None,source="user_confirmed",
         source_ref=None,priority=3,confidence=1.0,created=100):
    memory3.create_memory(
        conn,memory_id=mid,user_id="owner",text=text,scope=scope,
        memory_type="fact",project_id=project_id,priority=priority,
        confidence=confidence,source=source,source_ref=source_ref,created=created
    )


def test_local_semantic_search_and_graph_expansion(tmp_path):
    db=_prepare(tmp_path/"knowledge.sqlite3")
    with db() as conn:
        _add(conn,"memory-project",
             "Проектная память используется только внутри соответствующего проекта.",
             priority=5)
        _add(conn,"memory-backup",
             "Перед обновлением программы создаётся резервная копия базы данных.",
             priority=3)
        _add(conn,"memory-related",
             "Контекст проекта имеет стабильный идентификатор work:Sayuri.",
             priority=4)
        memories=knowledge31.knowledge_memories(
            conn,user_id="owner",now=200,project_id=None,limit=500)
        direct=knowledge31.semantic_search(
            conn,user_id="owner",memories=memories,
            query="память конкретного проекта",now=200,limit=10)
        assert direct
        assert direct[0]["id"]=="memory-project"
        assert direct[0]["source_info"]["kind"]=="user"

        body=knowledge31.KnowledgeLinkCreate(
            left_memory_id="memory-project",right_memory_id="memory-related",
            relation="related",confidence=1.0,note="Один проектный контекст")
        knowledge31.add_link(
            conn,user_id="owner",link_id="link-1",body=body,created=201)
        expanded=knowledge31.semantic_search(
            conn,user_id="owner",memories=memories,
            query="память конкретного проекта",now=202,limit=10)
        related=next(row for row in expanded if row["id"]=="memory-related")
        assert related["graph_boost"]>0


def test_project_knowledge_isolation_and_sources(tmp_path):
    db=_prepare(tmp_path/"knowledge.sqlite3")
    with db() as conn:
        _add(conn,"a","Решение проекта Альфа",scope="project",project_id="work:Alpha")
        _add(conn,"b","Решение проекта Бета",scope="project",project_id="work:Beta")
        _add(conn,"global","Общее правило Sayuri",scope="personal",
             source="teacher_reviewed",source_ref="chat:123",confidence=.9)
        alpha=knowledge31.knowledge_memories(
            conn,user_id="owner",now=200,project_id="work:Alpha",limit=500)
        ids={row["id"] for row in alpha}
        assert {"a","global"} <= ids
        assert "b" not in ids
        source=knowledge31.source_info(next(row for row in alpha if row["id"]=="global"))
        assert source["kind"]=="mentor_review"
        assert source["ref"]=="chat:123"
        assert source["trust"]==.9


def test_conflict_candidates_require_review(tmp_path):
    db=_prepare(tmp_path/"knowledge.sqlite3")
    with db() as conn:
        _add(conn,"days30","Резервная копия проекта хранится 30 дней.",priority=5)
        _add(conn,"days90","Резервная копия проекта хранится 90 дней.",priority=5)
        _add(conn,"cloud-yes","Sayuri может отправлять файлы в облако.",priority=4)
        _add(conn,"cloud-no","Sayuri не может отправлять файлы в облако.",priority=4)
        memories=knowledge31.knowledge_memories(
            conn,user_id="owner",now=300,project_id=None,limit=500)
        conflicts=knowledge31.detect_conflicts(
            conn,user_id="owner",memories=memories,now=300,limit=100)
        assert conflicts
        numeric=next(item for item in conflicts if {item["left"]["id"],item["right"]["id"]}=={"days30","days90"})
        assert numeric["status"]=="pending"
        assert "числовые" in numeric["reason"]
        polarity=next(item for item in conflicts if {item["left"]["id"],item["right"]["id"]}=={"cloud-yes","cloud-no"})
        assert polarity["status"]=="pending"

        review=knowledge31.ConflictReview(status="resolved",note="Проверено по источнику")
        knowledge31.review_conflict(
            conn,user_id="owner",key=numeric["key"],body=review,now=301)
        again=knowledge31.detect_conflicts(
            conn,user_id="owner",memories=memories,now=302,limit=100)
        numeric_again=next(item for item in again if item["key"]==numeric["key"])
        assert numeric_again["status"]=="resolved"
        assert numeric_again["note"]=="Проверено по источнику"


def test_explicit_contradiction_link_creates_candidate(tmp_path):
    db=_prepare(tmp_path/"knowledge.sqlite3")
    with db() as conn:
        _add(conn,"left","Основной режим работы Sayuri — локальный.",priority=5)
        _add(conn,"right","Основной режим работы Sayuri — локальный и изолированный.",priority=5)
        body=knowledge31.KnowledgeLinkCreate(
            left_memory_id="left",right_memory_id="right",
            relation="contradicts",confidence=.8,note="Требуется проверка")
        knowledge31.add_link(conn,user_id="owner",link_id="link-c",body=body,created=200)
        memories=knowledge31.knowledge_memories(
            conn,user_id="owner",now=201,project_id=None,limit=500)
        conflicts=knowledge31.detect_conflicts(
            conn,user_id="owner",memories=memories,now=201,limit=100)
        candidate=next(item for item in conflicts if {item["left"]["id"],item["right"]["id"]}=={"left","right"})
        assert candidate["reason"]=="Явная связь «противоречит»"
        assert candidate["status"]=="pending"
