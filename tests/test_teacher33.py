"""Tests for automatic Teacher Understanding 3.3."""
import json
import sqlite3
from contextlib import contextmanager

import pytest

from server import teacher33
import server.app as service


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
    db=_db_for(path)
    teacher33.migrate(db)
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS memory_candidates (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created INTEGER NOT NULL
        )""")
    return db


def _analysis(*, understood, topic="Тема", summary="Краткое объяснение",
              unclear=None, question=None, confidence=.8, owner_facts=None):
    return json.dumps({
        "topic":topic,
        "summary":summary,
        "concepts":[{"name":"Понятие","explanation":"Объяснение"}],
        "claims":["Утверждение наставника"],
        "examples":["Пример"],
        "methods":["Метод"],
        "unclear":unclear or [],
        "owner_facts":owner_facts or [],
        "confidence":confidence,
        "understood":understood,
        "clarification_question":question,
    },ensure_ascii=False)


def test_parse_analysis_never_calls_unclear_lesson_understood():
    parsed=teacher33.parse_analysis(_analysis(
        understood=True,unclear=["Неясна причинная связь"],question=None))
    assert parsed["understood"] is False
    assert parsed["clarification_question"].startswith("Пожалуйста, уточните")


@pytest.mark.asyncio
async def test_auto_teacher_learning_understands_after_one_question(tmp_path,monkeypatch):
    db=_prepare(tmp_path/"teacher.sqlite3")
    monkeypatch.setattr(service,"db",db)
    monkeypatch.setattr(service,"stamp",lambda:100)
    monkeypatch.setenv("CLOUD_RU_TEACHER_MODEL","teacher-model")
    monkeypatch.setenv("CLOUD_RU_MODEL","sayuri-model")

    calls=[]
    async def fake_cloud(messages,model_override=None):
        calls.append((model_override,messages))
        if model_override=="teacher-model":
            return "Потому что механизм сначала сохраняет контекст, а затем использует его при продолжении."
        analyses=sum(1 for model,_ in calls if model=="sayuri-model")
        if analyses==1:
            return _analysis(
                understood=False,unclear=["Почему контекст сохраняется перед продолжением?"],
                question="Почему контекст нужно сохранять до продолжения задачи?",confidence=.55)
        return _analysis(
            understood=True,summary="Контекст сохраняется до продолжения, чтобы восстановить состояние.",
            confidence=.94,owner_facts=["Владелец хочет автоматическое обучение у учителя."])
    monkeypatch.setattr(service,"cloud_chat",fake_cloud)

    await service.auto_learn_teacher_exchange(
        "owner","teacher-chat","Объясни восстановление задач.",
        "Нужно сохранять контекст до продолжения.")

    with db() as c:
        lessons=c.execute("SELECT * FROM teacher_lessons").fetchall()
        assert len(lessons)==1
        row=dict(lessons[0])
        assert row["status"]=="understood"
        assert row["clarification_rounds"]==1
        assert row["confidence"]==pytest.approx(.94)
        turns=c.execute("SELECT * FROM teacher_lesson_turns ORDER BY round_no").fetchall()
        assert len(turns)==1
        assert "Почему контекст" in turns[0]["question"]
        candidate=c.execute("SELECT * FROM memory_candidates").fetchone()
        assert candidate is not None
        assert candidate["status"]=="pending"
        assert "автоматическое обучение" in candidate["text"]

    teacher_calls=[model for model,_ in calls if model=="teacher-model"]
    sayuri_calls=[model for model,_ in calls if model=="sayuri-model"]
    assert len(teacher_calls)==1
    assert len(sayuri_calls)==2


@pytest.mark.asyncio
async def test_auto_teacher_learning_stops_after_two_clarifications(tmp_path,monkeypatch):
    db=_prepare(tmp_path/"teacher.sqlite3")
    monkeypatch.setattr(service,"db",db)
    counter={"now":200}
    monkeypatch.setattr(service,"stamp",lambda:counter["now"])
    monkeypatch.setenv("CLOUD_RU_TEACHER_MODEL","teacher-model")
    monkeypatch.setenv("CLOUD_RU_MODEL","sayuri-model")

    counts={"teacher":0,"sayuri":0}
    async def fake_cloud(messages,model_override=None):
        if model_override=="teacher-model":
            counts["teacher"]+=1
            return "Дополнительное объяснение "+str(counts["teacher"])
        counts["sayuri"]+=1
        return _analysis(
            understood=False,
            unclear=["Всё ещё неясен критерий выбора."],
            question="Какой точный критерий выбора используется?",
            confidence=.45)
    monkeypatch.setattr(service,"cloud_chat",fake_cloud)

    await service.auto_learn_teacher_exchange(
        "owner","teacher-chat","Объясни критерий.","Исходное объяснение.")

    assert counts["teacher"]==teacher33.MAX_CLARIFICATION_ROUNDS
    assert counts["sayuri"]==teacher33.MAX_CLARIFICATION_ROUNDS+1
    with db() as c:
        row=dict(c.execute("SELECT * FROM teacher_lessons").fetchone())
        assert row["status"]=="partial"
        assert row["clarification_rounds"]==2
        turns=c.execute("SELECT COUNT(*) n FROM teacher_lesson_turns").fetchone()["n"]
        assert turns==2


@pytest.mark.asyncio
async def test_auto_teacher_learning_does_not_ask_when_understood(tmp_path,monkeypatch):
    db=_prepare(tmp_path/"teacher.sqlite3")
    monkeypatch.setattr(service,"db",db)
    monkeypatch.setattr(service,"stamp",lambda:300)
    monkeypatch.setenv("CLOUD_RU_TEACHER_MODEL","teacher-model")
    monkeypatch.setenv("CLOUD_RU_MODEL","sayuri-model")

    models=[]
    async def fake_cloud(messages,model_override=None):
        models.append(model_override)
        return _analysis(understood=True,confidence=.97)
    monkeypatch.setattr(service,"cloud_chat",fake_cloud)

    await service.auto_learn_teacher_exchange(
        "owner","teacher-chat","Что такое граф знаний?","Это система связей между знаниями.")

    assert models==["sayuri-model"]
    with db() as c:
        row=dict(c.execute("SELECT * FROM teacher_lessons").fetchone())
        assert row["status"]=="understood"
        assert row["clarification_rounds"]==0
