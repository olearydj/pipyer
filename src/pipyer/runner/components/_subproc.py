"""Bounded, process-group-owning subprocess execution for component executors.

Born from the first live acceptance run (2026-06-11): a SIGINT to the runner
orphaned in-flight test-harness children, and with the parent dead nobody
enforced timeouts - student submissions with infinite loops grew unbounded
(the same bug family as the original GradeBot's six-months-broken timeout).

Two guarantees this module owns:

1. No orphans. Every child runs in its own process group; the group is killed
   on timeout, on completion (stray grandchildren included), and - via
   `kill_active_children()` - when the engine is interrupted or exits.
2. Bounded capture. stdout/stderr are drained with a byte cap; a flooding
   child cannot balloon the runner's memory. Truncation is recorded, never
   silent.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from typing import IO

# Explicit, boring bound (Principle V). Component outputs are JSON summaries;
# anything near this size is pathological and the truncation flag says so.
MAX_CAPTURE_BYTES = 1_048_576
SECRET_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "CO_API_KEY",
    }
)

_active_pgids: set[int] = set()
_active_lock = threading.Lock()


class CaptureTimeout(Exception):
    """Raised when the child (and its whole process group) hit timeout_s."""


@dataclass
class CompletedCapture:
    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool


def kill_active_children() -> int:
    """Kill every live child process group. Returns the number killed.

    Called by the engine on interrupt and at run end; idempotent and safe to
    call from signal/except paths (ESRCH is tolerated).
    """
    with _active_lock:
        pgids = list(_active_pgids)
    killed = 0
    for pgid in pgids:
        if _killpg(pgid):
            killed += 1
    return killed


def _killpg(pgid: int) -> bool:
    try:
        os.killpg(pgid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - foreign group, never ours
        return False


def _drain(stream: IO[bytes], sink: list[bytes], truncated: list[bool]) -> None:
    captured = 0
    while True:
        chunk = stream.read(65536)
        if not chunk:
            return
        if captured < MAX_CAPTURE_BYTES:
            keep = chunk[: MAX_CAPTURE_BYTES - captured]
            sink.append(keep)
            captured += len(keep)
            if len(keep) < len(chunk):
                truncated[0] = True
        else:
            truncated[0] = True  # keep reading so the child never blocks on a full pipe


def _write_stdin(stream: IO[bytes], data: bytes, errors: list[BaseException]) -> None:
    try:
        stream.write(data)
        stream.close()
    except (BrokenPipeError, ValueError):
        pass  # child exited or the timeout path closed the pipe
    except OSError as error:
        errors.append(error)


def _scrub_env(env: dict[str, str] | None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {key: value for key, value in source.items() if key not in SECRET_ENV_KEYS}


def run_captured(
    argv: list[str],
    *,
    input_text: str,
    cwd: object,
    env: dict[str, str] | None = None,
    timeout_s: int | None = None,
) -> CompletedCapture:
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        env=_scrub_env(env),
        start_new_session=True,  # own process group: the kill boundary
    )
    pgid = proc.pid  # start_new_session makes the child its own group leader
    with _active_lock:
        _active_pgids.add(pgid)

    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    out_trunc = [False]
    err_trunc = [False]
    assert proc.stdout is not None and proc.stderr is not None and proc.stdin is not None
    readers = [
        threading.Thread(target=_drain, args=(proc.stdout, out_chunks, out_trunc), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err_chunks, err_trunc), daemon=True),
    ]
    for t in readers:
        t.start()
    stdin_errors: list[BaseException] = []
    writer = threading.Thread(
        target=_write_stdin,
        args=(proc.stdin, input_text.encode("utf-8"), stdin_errors),
        daemon=True,
    )
    writer.start()

    try:
        try:
            exit_code = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _killpg(pgid)
            proc.wait()
            raise CaptureTimeout from None
    finally:
        # Group kill on every exit path: a finished child may have left
        # grandchildren behind, and those are exactly the orphans this
        # module exists to prevent.
        _killpg(pgid)
        with _active_lock:
            _active_pgids.discard(pgid)
        try:
            proc.stdin.close()
        except OSError:
            pass
        writer.join(timeout=5)
        for t in readers:
            t.join(timeout=5)

    if stdin_errors:
        raise stdin_errors[0]

    return CompletedCapture(
        exit_code=exit_code,
        stdout=b"".join(out_chunks).decode("utf-8", errors="replace"),
        stderr=b"".join(err_chunks).decode("utf-8", errors="replace"),
        stdout_truncated=out_trunc[0],
        stderr_truncated=err_trunc[0],
    )
