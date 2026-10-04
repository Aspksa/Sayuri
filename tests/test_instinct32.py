"""Sayuri Instinct Engine 3.2 priorities, overrides and deterministic reactions."""
import sqlite3
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from server import instinct32


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
    instinct32.migrate(db)
    return db


def test_instinct32_base_rules_and_override_precedence(tmp_path):
    db=_prepare(tmp_path/"instinct.sqlite3")
    with db() as conn:
        base=instinct32.effective_instincts(conn,user_id="owner")
        by_id={item["id"]:item for item in base}
        assert by_id["data_protection"]["immutable"] is True
        assert by_id["data_protection"]["strength"]==5
        assert by_id["initiative"]["strength"]==2
        assert by_id["initiative"]["source"]=="base"

        owner=instinct32.save_override(
            conn,user_id="owner",instinct_id="initiative",
            body=instinct32.InstinctOverride(strength=4,enabled=True),
            now=100)
        assert owner["strength"]==4
        assert owner["source"]=="owner"

        project=instinct32.save_override(
            conn,user_id="owner",instinct_id="initiative",
            body=instinct32.InstinctOverride(
                strength=1,enabled=False,project_id="work:Sayuri"),
            now=101)
        assert project["strength"]==1
        assert project["enabled"] is False
        assert project["source"]=="project"

        other={item["id"]:item for item in instinct32.effective_instincts(
            conn,user_id="owner",project_id="work:Other")}
        assert other["initiative"]["strength"]==4
        assert other["initiative"]["enabled"] is True
        assert other["initiative"]["source"]=="owner"

        reset=instinct32.reset_override(
            conn,user_id="owner",instinct_id="initiative",
            project_id="work:Sayuri")
        assert reset["strength"]==4
        assert reset["source"]=="owner"


def test_immutable_instinct_cannot_be_changed(tmp_path):
    db=_prepare(tmp_path/"instinct.sqlite3")
    with db() as conn:
        with pytest.raises(HTTPException) as exc:
            instinct32.save_override(
                conn,user_id="owner",instinct_id="truthfulness",
                body=instinct32.InstinctOverride(strength=1,enabled=False),
                now=100)
        assert exc.value.status_code==403


def test_destructive_external_action_requires_confirmation(tmp_path):
    db=_prepare(tmp_path/"instinct.sqlite3")
    with db() as conn:
        result=instinct32.evaluate(
            conn,user_id="owner",
            body=instinct32.InstinctEvaluate(
                text="Удали старые файлы проекта и отправь архив в облако.",
                project_id="work:Sayuri"),
            now=200)
        assert result["version"]=="3.2.0"
        assert result["level"]=="confirm"
        assert result["requires_confirmation"] is True
        ids={item["id"] for item in result["triggers"]}
        assert {"data_protection","owner_priority","context_preservation","task_completion"} <= ids
        protection=next(item for item in result["triggers"] if item["id"]=="data_protection")
        assert protection["strength"]==5
        assert protection["action"]=="confirm"

        text=instinct32.context_text(result)
        assert "Инстинкт 3.2" in text
        assert "явного подтверждения" in text
        assert "не эмоции" in text


def test_sources_and_conflicts_force_verification(tmp_path):
    db=_prepare(tmp_path/"instinct.sqlite3")
    with db() as conn:
        result=instinct32.evaluate(
            conn,user_id="owner",
            body=instinct32.InstinctEvaluate(
                text="Что точно написано в документе architecture.pdf?",
                project_id="work:Sayuri",pending_conflicts=2),
            now=300)
        assert result["level"]=="verify"
        assert result["needs_verification"] is True
        assert result["requires_confirmation"] is False
        ids={item["id"] for item in result["triggers"]}
        assert {"truthfulness","source_first","conflict_check","context_preservation"} <= ids
        conflict=next(item for item in result["triggers"] if item["id"]=="conflict_check")
        assert "2" in conflict["reason"]


def test_disabled_configurable_instinct_does_not_trigger(tmp_path):
    db=_prepare(tmp_path/"instinct.sqlite3")
    with db() as conn:
        instinct32.save_override(
            conn,user_id="owner",instinct_id="source_first",
            body=instinct32.InstinctOverride(strength=4,enabled=False),
            now=100)
        result=instinct32.evaluate(
            conn,user_id="owner",
            body=instinct32.InstinctEvaluate(
                text="Что написано в этом документе?"),
            now=101)
        ids={item["id"] for item in result["triggers"]}
        assert "source_first" not in ids
        assert "truthfulness" in ids


def test_summary_and_event_log(tmp_path):
    db=_prepare(tmp_path/"instinct.sqlite3")
    with db() as conn:
        instinct32.evaluate(
            conn,user_id="owner",
            body=instinct32.InstinctEvaluate(text="Предложи следующий шаг."),
            now=400)
        summary=instinct32.summary(conn,user_id="owner")
        assert summary["version"]=="3.2.0"
        assert summary["total"]==9
        assert summary["immutable"]==3
        assert summary["configurable"]==6
        assert summary["last"]["level"] in {"guided","verify","confirm","normal"}

        events=instinct32.recent_events(conn,user_id="owner",limit=10)
        assert len(events)==1
        assert events[0]["operation"]=="conversation"
        assert any(item["id"]=="initiative" for item in events[0]["triggers"])
