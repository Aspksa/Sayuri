"""Sayuri Initiative 3.5 scoring, continuity, commitments and reaction adaptation."""
import sqlite3
from contextlib import contextmanager

from server import initiative35


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
    initiative35.migrate(db)
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS teacher_lessons (
            id TEXT PRIMARY KEY,user_id TEXT NOT NULL,chat_id TEXT NOT NULL,
            project_id TEXT,topic TEXT NOT NULL DEFAULT '',summary TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'understood',updated INTEGER NOT NULL
        )""")
    return db


def test_note_turn_tracks_open_work_and_only_sayuri_promises(tmp_path):
    db=_prepare(tmp_path/"initiative.sqlite3")
    with db() as c:
        initiative35.note_turn(
            c,user_id="owner",chat_id="sayuri-1",kind="sayuri",
            owner_text="Продолжай настройку памяти проекта и проверь миграцию.",
            assistant_text="Я проверю миграцию после изменения схемы.",
            project_id="work:Sayuri",now=100)
        thread=dict(c.execute("SELECT * FROM initiative_threads").fetchone())
        commitment=dict(c.execute("SELECT * FROM initiative_commitments").fetchone())
        assert thread["status"]=="open"
        assert thread["project_id"]=="work:Sayuri"
        assert "Продолжай настройку" in thread["title"]
        assert "Я проверю миграцию" in commitment["text"]

        # The mentor may say "я проверю", but that is not Sayuri's own promise.
        initiative35.note_turn(
            c,user_id="owner",chat_id="teacher-1",kind="teacher",
            owner_text="Объясни ещё один пример.",
            assistant_text="Я проверю это позже.",
            project_id=None,now=101)
        assert c.execute("SELECT COUNT(*) n FROM initiative_commitments").fetchone()["n"]==1


def test_first_launch_is_silent_but_return_can_greet(tmp_path):
    db=_prepare(tmp_path/"initiative.sqlite3")
    with db() as c:
        first=initiative35.next_initiative(
            c,user_id="owner",now=10_000,trigger="session")
        assert first["item"] is None
        assert first["reason"]=="no_candidate"

        # Simulate a real return after more than six hours.
        c.execute("UPDATE initiative_profile SET last_seen=?,last_delivery=NULL WHERE user_id=?",
                  (10_000-7*3600,"owner"))
        returned=initiative35.next_initiative(
            c,user_id="owner",now=10_000,trigger="session")
        assert returned["item"]["kind"]=="greeting"
        assert returned["item"]["score"]>=returned["item"]["threshold"]


def test_real_problem_outranks_greeting_and_can_be_resolved(tmp_path):
    db=_prepare(tmp_path/"initiative.sqlite3")
    with db() as c:
        c.execute("INSERT INTO initiative_profile(user_id,last_seen) VALUES(?,?)",
                  ("owner",20_000-9*3600))
        problem_id=initiative35.register_problem(
            c,user_id="owner",problem_key="conflict:alpha",
            project_id="work:Alpha",title="есть непроверенное противоречие",
            detail="Две записи дают разные значения.",severity=5,
            source_ref="knowledge:conflicts",now=19_900)
        result=initiative35.next_initiative(
            c,user_id="owner",now=20_000,trigger="session",project_id="work:Alpha")
        item=result["item"]
        assert item["kind"]=="problem"
        assert item["source_id"]==problem_id
        assert "противоречие" in item["text"]

        reaction=initiative35.react(
            c,user_id="owner",delivery_id=item["id"],reaction="resolved",now=20_001)
        assert reaction["reaction"]=="resolved"
        problem=dict(c.execute("SELECT * FROM initiative_problems WHERE id=?",(problem_id,)).fetchone())
        assert problem["status"]=="resolved"


def test_less_reaction_mutes_kind_for_seven_days_and_lowers_engagement(tmp_path):
    db=_prepare(tmp_path/"initiative.sqlite3")
    with db() as c:
        initiative35.note_turn(
            c,user_id="owner",chat_id="c1",kind="sayuri",
            owner_text="Продолжай реализацию автоматической инициативы.",
            assistant_text="Принято.",
            project_id="work:Sayuri",now=100)
        c.execute("""INSERT INTO initiative_profile(user_id,engagement,ignored_streak,last_seen)
                     VALUES(?,?,?,?)""",("owner",.25,0,100))
        result=initiative35.next_initiative(
            c,user_id="owner",now=100+13*3600,trigger="session",
            project_id="work:Sayuri")
        item=result["item"]
        assert item["kind"]=="continuity"
        reaction=initiative35.react(
            c,user_id="owner",delivery_id=item["id"],reaction="less",
            now=100+13*3600+1)
        assert reaction["engagement"]<.25
        mute=dict(c.execute("""SELECT * FROM initiative_mutes
                              WHERE user_id='owner' AND kind='continuity'""").fetchone())
        assert mute["until"]==100+13*3600+1+7*86400


def test_ignored_offers_reduce_future_frequency(tmp_path):
    db=_prepare(tmp_path/"initiative.sqlite3")
    with db() as c:
        c.execute("""INSERT INTO initiative_profile(user_id,engagement,ignored_streak,last_seen)
                     VALUES(?,?,?,?)""",("owner",0,0,1))
        c.execute("""INSERT INTO initiative_deliveries
                     (id,user_id,kind,text,reason,score,status,created)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  ("old","owner","greeting","Привет","test",64,"offered",100))
        initiative35.settle_ignored(c,user_id="owner",now=2000)
        profile=dict(c.execute("SELECT * FROM initiative_profile WHERE user_id='owner'").fetchone())
        delivery=dict(c.execute("SELECT * FROM initiative_deliveries WHERE id='old'").fetchone())
        assert delivery["status"]=="ignored"
        assert profile["engagement"]<0
        assert profile["ignored_streak"]==1


def test_social_initiative_requires_positive_history_and_long_pause(tmp_path):
    db=_prepare(tmp_path/"initiative.sqlite3")
    now=500_000
    with db() as c:
        c.execute("""INSERT INTO initiative_profile
                     (user_id,engagement,ignored_streak,last_seen,last_delivery,last_social)
                     VALUES(?,?,?,?,?,?)""",
                  ("owner",.6,0,now-20*3600,None,now-3*86400))
        # Suppress greeting so the lower-priority social candidate can be evaluated.
        c.execute("INSERT INTO initiative_mutes(user_id,kind,until) VALUES(?,?,?)",
                  ("owner","greeting",now+86400))
        result=initiative35.next_initiative(
            c,user_id="owner",now=now,trigger="session")
        assert result["item"]["kind"]=="social"
        assert result["item"]["score"]>=result["item"]["threshold"]


def test_commitment_reminders_are_bounded(tmp_path):
    db=_prepare(tmp_path/"initiative.sqlite3")
    with db() as c:
        initiative35.note_turn(
            c,user_id="owner",chat_id="c1",kind="sayuri",
            owner_text="Проверь обновление.",
            assistant_text="Я проверю обновление после перезапуска.",
            project_id=None,now=100)
        commitment=c.execute("SELECT id FROM initiative_commitments").fetchone()["id"]
        c.execute("""INSERT INTO initiative_profile(user_id,last_seen)
                     VALUES(?,?)""",("owner",100))
        # Three reminder opportunities across separate days.
        for index in range(3):
            now=100+(index+1)*90000
            c.execute("UPDATE initiative_profile SET last_delivery=NULL WHERE user_id='owner'")
            c.execute("UPDATE initiative_commitments SET last_offered=NULL WHERE id=?",(commitment,))
            result=initiative35.next_initiative(
                c,user_id="owner",now=now,trigger="periodic")
            assert result["item"]["kind"]=="commitment"
            initiative35.react(
                c,user_id="owner",delivery_id=result["item"]["id"],
                reaction="dismissed",now=now+1)
        row=dict(c.execute("SELECT * FROM initiative_commitments WHERE id=?",(commitment,)).fetchone())
        assert row["reminders"]==3
        c.execute("UPDATE initiative_profile SET last_delivery=NULL WHERE user_id='owner'")
        c.execute("UPDATE initiative_commitments SET last_offered=NULL WHERE id=?",(commitment,))
        fourth=initiative35.next_initiative(
            c,user_id="owner",now=400_000,trigger="periodic")
        assert fourth["item"] is None or fourth["item"]["kind"]!="commitment"
