"""Single-writer lock behavior (R18): rejection, stale reclaim, clean release."""

import json
import os
from datetime import UTC, datetime

import pytest

from pipyer.records.run import RunHaltedEvent
from pipyer.runner.events import EventLog, RunLockedError


def _event(run_id="r1"):
    return RunHaltedEvent(schema_version="1", run_id=run_id, reason="test", at=datetime.now(UTC))


def test_second_writer_rejected_while_lock_live(tmp_path):
    first = EventLog(tmp_path)
    first.acquire()
    try:
        second = EventLog(tmp_path)
        with pytest.raises(RunLockedError, match="live writer"):
            second.acquire()
    finally:
        first.release()


def test_stale_lock_reclaimed_and_flagged(tmp_path):
    # A lock held by a dead pid: write one with an unlikely-to-exist pid.
    dead_pid = 2**22 + 12345
    (tmp_path / "events.jsonl.lock").write_text(
        json.dumps({"pid": dead_pid, "started_at": "2026-01-01T00:00:00+00:00"})
    )
    log = EventLog(tmp_path)
    log.acquire()
    try:
        assert log.lock_reclaimed is True
    finally:
        log.release()


def test_unreadable_lock_treated_as_stale(tmp_path):
    (tmp_path / "events.jsonl.lock").write_text("not json")
    log = EventLog(tmp_path)
    log.acquire()
    try:
        assert log.lock_reclaimed is True
    finally:
        log.release()


def test_stale_lock_reclaim_race_reports_run_locked(tmp_path, monkeypatch):
    (tmp_path / "events.jsonl.lock").write_text(
        json.dumps({"pid": 2**22 + 45678, "started_at": "2026-01-01T00:00:00+00:00"})
    )

    def another_writer_wins(log):
        log.lock_path.write_text(json.dumps({"pid": os.getpid(), "started_at": "now"}))

    monkeypatch.setattr(EventLog, "_handle_existing_lock", another_writer_wins)
    with pytest.raises(RunLockedError, match="another writer"):
        EventLog(tmp_path).acquire()


def test_clean_release_removes_lock(tmp_path):
    log = EventLog(tmp_path)
    log.acquire()
    log.append(_event())
    log.release()
    assert not (tmp_path / "events.jsonl.lock").exists()
    assert (tmp_path / "events.jsonl").read_text().count("\n") == 1


def test_lock_records_holder_pid(tmp_path):
    with EventLog(tmp_path) as log:
        holder = json.loads((tmp_path / "events.jsonl.lock").read_text())
        assert holder["pid"] == os.getpid()
        assert log.lock_reclaimed is False


def test_append_returns_sequential_refs_across_sessions(tmp_path):
    with EventLog(tmp_path) as log:
        assert log.append(_event()) == 0
        assert log.append(_event()) == 1
    with EventLog(tmp_path) as log:  # resume session appends to the same file
        assert log.append(_event()) == 2
