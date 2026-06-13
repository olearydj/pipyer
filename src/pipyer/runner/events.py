"""Single-writer event-log appender (R18; run-directory contract).

The lock file (`events.jsonl.lock`) is acquired with O_CREAT|O_EXCL - atomic on
local filesystems, dependency-free. A live lock (its pid alive) rejects the
second writer; a stale lock (pid dead) is reclaimed and the reclaim is flagged
so the resume diff records it. Within the process, exactly one thread writes:
worker threads hand results to the owning thread, which appends and flushes
line by line so a crash can tear at most the trailing line (the recovery case
`parse_event_log` already handles).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from pipyer.records.run import Event, event_line


class RunLockedError(RuntimeError):
    """The run directory's event log is held by a live writer."""


class EventLog:
    """Append-only writer for one run's events.jsonl, guarded by the lock file."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "events.jsonl"
        self.lock_path = run_dir / "events.jsonl.lock"
        self.lock_reclaimed = False
        self._fh: TextIO | None = None
        self._lines = 0

    # ------------------------------------------------------------------ lock

    def acquire(self) -> None:
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            self._handle_existing_lock()
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as error:
                raise RunLockedError(
                    f"event log {self.path} lock was reclaimed by another writer; "
                    "a run directory has exactly one writer"
                ) from error
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(
                {"pid": os.getpid(), "started_at": datetime.now(UTC).isoformat()},
                fh,
            )
        if self.path.exists():
            self._truncate_corrupt_trailing_line()
            self._lines = sum(
                1 for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        self._fh = self.path.open("a", encoding="utf-8")

    def _truncate_corrupt_trailing_line(self) -> None:
        """The documented recovery: a torn trailing line from an interrupted
        write is dropped before this writer appends (parse_event_log's
        corrupt-trailing contract; anything else mid-file still raises there)."""
        text = self.path.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return
        try:
            json.loads(lines[-1])
        except json.JSONDecodeError:
            self.path.write_text("".join(line + "\n" for line in lines[:-1]), encoding="utf-8")

    def _handle_existing_lock(self) -> None:
        try:
            holder = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(holder["pid"])
        except (OSError, ValueError, KeyError):
            pid = None  # unreadable lock: treat as stale, reclaim loudly
        if pid is not None and _pid_alive(pid):
            raise RunLockedError(
                f"event log {self.path} is locked by a live writer (pid {pid}); "
                "a run directory has exactly one writer"
            )
        self.lock_path.unlink(missing_ok=True)
        self.lock_reclaimed = True

    def release(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        self.lock_path.unlink(missing_ok=True)

    # ---------------------------------------------------------------- append

    def append(self, event: Event) -> int:
        """Append one event; returns its zero-based line index (the event_ref)."""
        assert self._fh is not None, "EventLog.append before acquire()"
        self._fh.write(event_line(event) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())
        index = self._lines
        self._lines += 1
        return index

    def __enter__(self) -> EventLog:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True
