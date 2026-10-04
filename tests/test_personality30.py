"""Sayuri Personality 3.0 identity continuity, bounded adaptation and working state."""
import sqlite3
from contextlib import contextmanager

from server import personality30
from server.persona import load_persona


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
    personality30.migrate(db)
    return db


def test_identity_core_stays_on_canonical_persona_bundle(tmp_path):
    db=_prepare(tmp_path/"personality.sqlite3")
    persona=load_persona()
    core_before=personality30.identity_core(persona)

    with db() as conn:
        for i in range(10):
            personality30.record_feedback(
                conn,user_id="owner",correction="Отвечай короче и без шуток.",
                source_ref=f"message:{i}",now=100+i)
        profile=personality30.effective_profile(conn,user_id="owner",persona=persona)

    core_after=personality30.identity_core(persona)
    assert core_before==core_after
    assert core_after["base_persona_version"]=="2.0.0"
    assert core_after["core_traits"]["honesty"]==1
    assert profile["version"]=="3.0.0"
    assert profile["policy"]["changes_identity"] is False


def test_one_feedback_does_not_drift_personality(tmp_path):
    db=_prepare(tmp_path/"personality.sqlite3")
    persona=load_persona()
    with db() as conn:
        initial=personality30.effective_profile(conn,user_id="owner",persona=persona)
        personality30.record_feedback(
            conn,user_id="owner",correction="Пожалуйста, отвечай короче.",
            source_ref="message:1",now=100)
        after_one=personality30.effective_profile(conn,user_id="owner",persona=persona)
        assert after_one["traits"]["brevity"]["value"]==initial["traits"]["brevity"]["value"]
        assert after_one["traits"]["brevity"]["stable"] is False

        personality30.record_feedback(
            conn,user_id="owner",correction="Снова слишком длинно, отвечай короче.",
            source_ref="message:2",now=101)
        after_two=personality30.effective_profile(conn,user_id="owner",persona=persona)
        assert after_two["traits"]["brevity"]["value"]>initial["traits"]["brevity"]["value"]
        assert after_two["traits"]["brevity"]["stable"] is True


def test_adaptation_is_bounded_and_raw_correction_not_stored(tmp_path):
    db=_prepare(tmp_path/"personality.sqlite3")
    persona=load_persona()
    with db() as conn:
        base=personality30.effective_profile(conn,user_id="owner",persona=persona)
        for i in range(30):
            personality30.record_feedback(
                conn,user_id="owner",
                correction="Без шуток. Отвечай серьёзно и по делу.",
                source_ref=f"message:{i}",now=200+i)
        adapted=personality30.effective_profile(conn,user_id="owner",persona=persona)
        play_base=base["traits"]["playfulness"]["value"]
        play_value=adapted["traits"]["playfulness"]["value"]
        assert play_base-play_value<=personality30.MAX_DELTA+0.001
        assert adapted["traits"]["directness"]["value"]-base["traits"]["directness"]["value"]<=personality30.MAX_DELTA+0.001

        columns={row["name"] for row in conn.execute("PRAGMA table_info(personality_evidence)")}
        assert "correction" not in columns
        assert "text" not in columns
        rows=conn.execute("SELECT trait,source,source_ref FROM personality_evidence").fetchall()
        assert rows
        assert all(row["source"]=="owner_feedback" for row in rows)


def test_working_state_is_temporary_and_risk_has_priority():
    assert personality30.working_state(mode="creative",instinct_level="verify")["id"]=="cautious"
    assert personality30.working_state(mode="work",instinct_level="normal")["id"]=="focused"
    assert personality30.working_state(mode="analysis",instinct_level="normal")["id"]=="analytical"
    assert personality30.working_state(mode="support",instinct_level="normal")["id"]=="supportive"
    assert personality30.working_state(mode="creative",instinct_level="normal")["id"]=="creative"
    assert personality30.working_state(mode="personal",instinct_level="normal")["temporary"] is True


def test_personality_context_protects_identity_from_teacher_and_documents(tmp_path):
    db=_prepare(tmp_path/"personality.sqlite3")
    persona=load_persona()
    with db() as conn:
        profile=personality30.effective_profile(conn,user_id="owner",persona=persona)
    state=personality30.working_state(mode="analysis",instinct_level="verify")
    text=personality30.context_text(persona=persona,profile=profile,state=state)
    assert "Личность 3.0" in text
    assert "учитель, документы, сайты" in text
    assert "не могут переписать идентичность" in text
    assert "не источник фактов" in text
