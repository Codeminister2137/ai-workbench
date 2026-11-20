import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from investor.profiles import default_profiles
from investor.replay import Observation, Proposal, assess, decisions, record_decision, replay
from storage import ConversationStore

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def record(store, profile, callback, tick=0, observations=None):
    return record_decision(
        store,
        "run",
        profile,
        observations or [Observation(NOW, "fixture:7", {"AAA": 100.0, "BBB": 100.0})],
        NOW + timedelta(days=tick),
        callback,
        profile_version="v1",
        prompt_version="v1",
    )


def test_lifecycle_and_replay(tmp_path):
    path = tmp_path / "council.sqlite3"
    store = ConversationStore(path)
    conversation = store.get_or_create_conversation("existing")
    store.add_message(conversation, "user", "kept")
    profiles = default_profiles()
    seen = []
    observations = [
        Observation(NOW, "fixture:7", {"AAA": 100.0, "BBB": 100.0}),
        Observation(NOW + timedelta(days=1), "future", {"AAA": 200.0}),
    ]

    def deliberate(profile, visible):
        seen.append(visible)
        visible[0].prices["AAA"] = 999
        return Proposal({"AAA": 0.2}, "buy", "high", ("cash",))

    ids = [record(store, p, deliberate, observations=observations) for p in profiles]
    assert all(len(v) == 1 for v in seen)
    original = decisions(store, "run")
    assert all(r["observations"][0]["prices"]["AAA"] == 100 for r in original)
    for p in profiles:
        record(
            store,
            p,
            lambda *_: Proposal({}, "hold", "high"),
            tick=1,
            observations=[
                Observation(NOW + timedelta(days=1), "fixture:8", {"AAA": 110.0, "BBB": 100.0})
            ],
        )
    result = replay(store, "run")
    assert len(result) == 3
    assert all(r.total_return == pytest.approx(0.02) for r in result.values())
    before = decisions(store, "run")
    assess(store, ids[0], NOW + timedelta(days=2), "gain", "test lesson")
    assert decisions(store, "run") == before
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "UPDATE investor_decisions SET record = '{}' WHERE id = ?", (ids[0],)
        )
    store.connection.rollback()
    store.close()
    store = ConversationStore(path)
    assert replay(store, "run") == result
    assert store.list_messages(conversation)[0]["content"] == "kept"
    assert store.connection.execute("SELECT count(*) FROM investor_outcomes").fetchone()[0] == 1
    store.close()


@pytest.mark.parametrize("weights", [{"AAA": 0.26}, {"OTHER": 0.1}, {"AAA": -0.1}, {"AAA": 1.1}])
def test_rejection(tmp_path, weights):
    store = ConversationStore(tmp_path / "test.db")
    record(store, default_profiles()[0], lambda *_: Proposal(weights, "test", "high"))
    assert decisions(store, "run")[0]["status"] == "rejected"
    assert replay(store, "run")["contrarian"].turnover == 0
    store.close()


def test_failure_and_overallocation(tmp_path):
    from dataclasses import replace

    store = ConversationStore(tmp_path / "test.db")

    def fail(*_):
        raise RuntimeError("private message")

    record(store, default_profiles()[0], fail)
    record(
        store,
        replace(default_profiles()[1], max_position_pct=100),
        lambda *_: Proposal({"AAA": 0.6, "BBB": 0.6}, "test", "high"),
        tick=1,
    )
    rows = decisions(store, "run")
    assert [r["status"] for r in rows] == ["failed", "rejected"]
    assert rows[0]["reason"] == "RuntimeError"
    assert "private message" not in str(rows)
    with pytest.raises(ValueError):
        assess(store, rows[0]["id"], NOW - timedelta(days=1), "early", "invalid")
    store.close()


def test_targets_close_omitted_positions_and_replay_rejects_mismatched_evidence(tmp_path):
    store = ConversationStore(tmp_path / "test.db")
    profile = default_profiles()[0]
    record(store, profile, lambda *_: Proposal({"AAA": 0.2}, "buy", "high"))
    record(store, profile, lambda *_: Proposal({"BBB": 0.2}, "rotate", "high"), tick=1)
    assert replay(store, "run")[profile.name].turnover == pytest.approx(6000)
    record(
        store,
        default_profiles()[1],
        lambda *_: Proposal({}, "hold", "high"),
        tick=1,
        observations=[Observation(NOW, "different", {"AAA": 100.0, "BBB": 100.0})],
    )
    with pytest.raises(ValueError, match="identical fixture"):
        replay(store, "run")
    store.close()


def test_time_validation_and_future_only_refusal(tmp_path):
    store = ConversationStore(tmp_path / "test.db")
    with pytest.raises(ValueError, match="timezone"):
        record(
            store,
            default_profiles()[0],
            lambda *_: Proposal({}, "", ""),
            observations=[Observation(datetime(2026, 1, 1), "bad", {"AAA": 100.0})],
        )
    with pytest.raises(ValueError, match="visible observations"):
        record(
            store,
            default_profiles()[0],
            lambda *_: Proposal({}, "", ""),
            observations=[Observation(NOW + timedelta(days=1), "future", {"AAA": 100.0})],
        )
    assert decisions(store, "run") == []
    store.close()
