"""Bounded, process-group-owning subprocess execution (acceptance-run finding).

Three guarantees: timeout kills the whole group (grandchildren included),
kill_active_children() reaps in-flight groups on interrupt paths, and a
flooding child cannot balloon captured output past the cap.
"""

from __future__ import annotations

import os
import sys
import textwrap
import threading
import time

import pytest

from pipyer.runner.components._subproc import (
    MAX_CAPTURE_BYTES,
    CaptureTimeout,
    kill_active_children,
    run_captured,
)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _wait_dead(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


def test_timeout_kills_entire_process_group(tmp_path):
    """An infinite-loop child that spawned a grandchild leaves no survivors."""
    grandchild_pid_file = tmp_path / "grandchild.pid"
    script = tmp_path / "looper.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import subprocess, sys, time
            g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
            open({str(grandchild_pid_file)!r}, "w").write(str(g.pid))
            while True:
                time.sleep(0.1)
            """
        )
    )
    with pytest.raises(CaptureTimeout):
        run_captured(
            [sys.executable, str(script)],
            input_text="{}",
            cwd=tmp_path,
            timeout_s=1,
        )
    grandchild = int(grandchild_pid_file.read_text())
    assert _wait_dead(grandchild), "grandchild survived the group kill"


def test_timeout_applies_while_child_ignores_large_stdin(tmp_path):
    script = tmp_path / "ignore_stdin.py"
    script.write_text("import time\ntime.sleep(3)\n")
    started = time.monotonic()
    with pytest.raises(CaptureTimeout):
        run_captured(
            [sys.executable, str(script)],
            input_text="x" * (2 * MAX_CAPTURE_BYTES),
            cwd=tmp_path,
            timeout_s=1,
        )
    assert time.monotonic() - started < 2.5


def test_kill_active_children_reaps_in_flight_groups(tmp_path):
    """The engine's interrupt path can kill children another thread is waiting on."""
    pid_file = tmp_path / "child.pid"
    script = tmp_path / "sleeper.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, time
            open({str(pid_file)!r}, "w").write(str(os.getpid()))
            time.sleep(300)
            """
        )
    )
    result: dict = {}

    def worker():
        try:
            run_captured(
                [sys.executable, str(script)], input_text="{}", cwd=tmp_path, timeout_s=None
            )
        except Exception as e:  # noqa: BLE001 - recording whatever happens
            result["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    child = int(pid_file.read_text())

    killed = kill_active_children()
    assert killed >= 1
    assert _wait_dead(child), "in-flight child survived kill_active_children"
    t.join(timeout=5)
    assert not t.is_alive(), "worker thread stayed blocked after group kill"


def test_flooding_child_is_capped_not_buffered(tmp_path):
    """A child writing far past the cap completes, with truncation recorded."""
    script = tmp_path / "flood.py"
    script.write_text(
        "import sys\n"
        "chunk = 'x' * 65536\n"
        f"for _ in range({(5 * MAX_CAPTURE_BYTES) // 65536}):\n"
        "    sys.stdout.write(chunk)\n"
        "print()\n"
    )
    proc = run_captured([sys.executable, str(script)], input_text="{}", cwd=tmp_path, timeout_s=60)
    assert proc.exit_code == 0
    assert proc.stdout_truncated is True
    assert len(proc.stdout.encode()) <= MAX_CAPTURE_BYTES
    assert proc.stderr_truncated is False


def test_normal_round_trip_unaffected(tmp_path):
    script = tmp_path / "echo.py"
    script.write_text("import sys, json; print(json.dumps(json.load(sys.stdin)))")
    proc = run_captured(
        [sys.executable, str(script)], input_text='{"a": 1}', cwd=tmp_path, timeout_s=30
    )
    assert proc.exit_code == 0
    assert proc.stdout_truncated is False
    assert '"a": 1' in proc.stdout
