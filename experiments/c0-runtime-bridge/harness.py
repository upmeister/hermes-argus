#!/usr/bin/env python3
"""harness.py — parent-side containment for the C0 runtime bridge experiment.

Runs one bridge child at a time with an explicit allowlisted environment, one
explicit HERMES_HOME per child, a hard timeout with deterministic kill/reap,
byte caps on stdout/stderr, fail-closed envelope parsing and a canary leak
scan (C0 experiment contract sections 5, 6 and 10).

Containment is implemented BEFORE any Hermes import is attempted (C0 handoff
step 1). The harness never imports Hermes modules and never passes unrelated
parent environment through to the child; both properties are probed in
probes.py. This is experiment code: it must never be wired into deploy.sh,
cron, systemd or normal Argus health/discovery execution.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time

# Environment allowlist: only what a Python child needs to operate, plus
# explicitly declared fixture variables. Everything else (tokens, proxies,
# credentials, notification variables) is deliberately NOT inherited.
BASE_ENV_ALLOWLIST = (
    "PATH", "TEMP", "TMP", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC",
    "PATHEXT", "WINDIR", "LC_ALL", "LANG",
)
BRIDGE_ENV = {
    "PYTHONIOENCODING": "utf-8",
    "PYTHONDONTWRITEBYTECODE": "1",
}
RESERVED_ENV_KEYS = frozenset(BASE_ENV_ALLOWLIST) | frozenset(BRIDGE_ENV) | {
    "HERMES_HOME", "HOME", "PYTHONPATH", "C0_HERMES_SRC",
}

DEFAULT_TIMEOUT_S = 30
DEFAULT_OUTPUT_CAP = 256 * 1024  # bytes per stream
KILL_GRACE_S = 5

ENVELOPE_SCHEMA = 1
FACET_STATES = ("ok", "partial", "unsupported", "compatibility_degraded",
                "error")


def build_child_env(hermes_home, extra: dict | None = None) -> dict:
    """Build the child environment from the allowlist + declared variables.

    `hermes_home` is always explicit: the child must never infer a profile
    from ambient state. HOME is pointed at the fixture home deliberately:
    without HOME, posix Path.home()/expanduser fall back to the passwd entry
    (the real maintainer home), which would defeat profile isolation for any
    Hermes code that resolves "~" (observed in step 4). `extra` carries
    declared fixture variables (for example C0_CANARY_ENV); it cannot remove
    HERMES_HOME, HOME or the bridge flags.
    """
    env = {k: v for k, v in os.environ.items() if k in BASE_ENV_ALLOWLIST}
    env.update(BRIDGE_ENV)
    env["HERMES_HOME"] = str(hermes_home)
    env["HOME"] = str(hermes_home)
    for raw_key, value in (extra or {}).items():
        key = str(raw_key)
        if key in RESERVED_ENV_KEYS:
            raise ValueError(f"extra cannot override reserved environment key: {key}")
        if not key.isidentifier():
            raise ValueError(f"invalid declared environment variable: {key}")
        env[key] = str(value)
    return env


def _terminate(proc: subprocess.Popen) -> None:
    """Deterministic cleanup: terminate, then kill the whole process group."""
    try:
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError):
                pass
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


def build_hermes_env(hermes_home, hermes_src, extra: dict | None = None) -> dict:
    """Child environment for Hermes-backed runs: the allowlisted base plus the
    declared Hermes source selection (PYTHONPATH + C0_HERMES_SRC)."""
    env = build_child_env(hermes_home, extra=extra)
    env["PYTHONPATH"] = str(hermes_src)
    env["C0_HERMES_SRC"] = str(hermes_src)
    return env


def _capture_stream(stream, cap: int, output: dict, key: str,
                   stream_overflow: dict, overflow: threading.Event) -> None:
    """Capture a pipe in bounded chunks and stop at the byte boundary."""
    data = bytearray()
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            remaining = cap - len(data)
            if remaining <= 0 or len(chunk) > remaining:
                if remaining > 0:
                    data.extend(chunk[:remaining])
                stream_overflow[key] = True
                overflow.set()
                break
            data.extend(chunk)
    finally:
        output[key] = bytes(data)


def run_child(bridge_entrypoint, argv: list[str] | None = None, env: dict | None = None,
              timeout_s: int = DEFAULT_TIMEOUT_S,
              output_cap: int = DEFAULT_OUTPUT_CAP,
              workdir=None, python_executable=None) -> dict:
    """Run one bridge child; never raise for child failures.

    `python_executable` selects the interpreter for the child (the dedicated
    Hermes venv python for Hermes-backed runs); defaults to the harness's own
    interpreter. stdout/stderr are captured through bounded pipe readers; the
    child is terminated as soon as either stream exceeds the byte cap, so an
    oversized dump cannot fill a temporary file or block the harness.
    """
    if env is None:
        return {"status": "invalid_env", "exit_code": None,
                "elapsed_s": 0.0, "stdout": "", "stdout_truncated": False,
                "stderr": "explicit child environment is required",
                "stderr_truncated": False, "error_kind": "env_required",
                "timed_out": False, "output_limited": False}
    argv = [str(a) for a in (argv or [])]
    started = time.monotonic()
    status, exit_code, error_kind = "ok", None, None
    output = {}
    stream_overflow = {"stdout": False, "stderr": False}
    overflow = threading.Event()
    try:
        proc = subprocess.Popen(
            [python_executable or sys.executable, str(bridge_entrypoint), *argv],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            cwd=str(workdir) if workdir else None,
            start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        elapsed = time.monotonic() - started
        return {"status": "spawn_error", "exit_code": None,
                "elapsed_s": round(elapsed, 3), "stdout": "", "stdout_truncated": False,
                "stderr": f"{type(exc).__name__}", "stderr_truncated": False,
                "error_kind": "spawn_error", "timed_out": False,
                "output_limited": False}
    readers = [
        threading.Thread(target=_capture_stream,
                         args=(proc.stdout, output_cap, output, "stdout",
                               stream_overflow, overflow), daemon=True),
        threading.Thread(target=_capture_stream,
                         args=(proc.stderr, output_cap, output, "stderr",
                               stream_overflow, overflow), daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        deadline = started + timeout_s
        while proc.poll() is None:
            if overflow.wait(timeout=0.05):
                status, error_kind = "output_limit", "output_limit"
                _terminate(proc)
                break
            if time.monotonic() >= deadline:
                status = "timeout"
                _terminate(proc)
                break
        if status == "ok":
            exit_code = proc.returncode
        else:
            try:
                exit_code = proc.wait(timeout=KILL_GRACE_S)
            except subprocess.TimeoutExpired:
                error_kind = "unreapable_child"
    finally:
        for reader in readers:
            reader.join(timeout=KILL_GRACE_S)
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        elapsed = time.monotonic() - started
    if status == "ok" and overflow.is_set():
        status, error_kind = "output_limit", "output_limit"
    stdout = output.get("stdout", b"").decode("utf-8", errors="replace")
    stderr = output.get("stderr", b"").decode("utf-8", errors="replace")
    result = {"status": status, "exit_code": exit_code,
              "elapsed_s": round(elapsed, 3), "timed_out": status == "timeout",
              "stdout": stdout, "stdout_truncated": stream_overflow["stdout"],
              "stderr": stderr, "stderr_truncated": stream_overflow["stderr"],
              "output_limited": status == "output_limit"}
    if error_kind:
        result["error_kind"] = error_kind
    return result


def parse_envelope(run_result: dict) -> tuple[dict | None, str]:
    """Fail-closed parse of the child's stdout as a bridge envelope.

    Mirrors the D0a consumer lesson: exact integer schema, required shapes,
    canonical facet states. Any violation rejects the whole output — a partial
    envelope is never trusted.
    """
    if run_result.get("status") != "ok":
        return None, f"child did not finish cleanly ({run_result.get('status')})"
    if run_result.get("exit_code") != 0:
        return None, f"child exit code {run_result.get('exit_code')!r}"
    text = (run_result.get("stdout") or "").strip()
    if not text:
        return None, "empty child stdout"
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"stdout is not JSON ({exc.msg} at {exc.lineno}:{exc.colno})"
    if not isinstance(envelope, dict):
        return None, "envelope is not an object"
    schema = envelope.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool) \
            or schema != ENVELOPE_SCHEMA:
        return None, f"unsupported envelope schema {schema!r}"
    source = envelope.get("source")
    if not isinstance(source, dict):
        return None, "missing source"
    for field in ("hermes_revision", "bridge_revision", "profile_id"):
        if not isinstance(source.get(field), str) or not source[field]:
            return None, f"source.{field} must be a non-empty string"
    facets = envelope.get("facets")
    if not isinstance(facets, dict):
        return None, "facets is not an object"
    for name, facet in facets.items():
        if not isinstance(name, str) or not name:
            return None, "facet name must be a non-empty string"
        if not isinstance(facet, dict):
            return None, f"facet {name!r} is not an object"
        if facet.get("state") not in FACET_STATES:
            return None, f"facet {name!r}: state {facet.get('state')!r} is not canonical"
        if facet.get("authority") not in ("hermes", "argus", "unknown"):
            return None, f"facet {name!r}: authority {facet.get('authority')!r} is not canonical"
        if not isinstance(facet.get("reason_code", ""), str):
            return None, f"facet {name!r}: reason_code must be a string"
        data = facet.get("data", {})
        if not isinstance(data, dict):
            return None, f"facet {name!r}: data must be an object"
    effects = envelope.get("effects")
    if effects is not None:
        if not isinstance(effects, dict):
            return None, "effects must be an object"
        for key in ("network", "process_spawn", "writes"):
            if not isinstance(effects.get(key), list):
                return None, f"effects.{key} must be a list"
        if not isinstance(effects.get("truncated"), bool):
            return None, "effects.truncated must be a boolean"
    return envelope, ""


def scan_canaries(canaries, *texts) -> list[str]:
    """Return the canaries found in any of the given texts (sorted, unique)."""
    found = set()
    for canary in canaries:
        for text in texts:
            if text and canary in text:
                found.add(canary)
    return sorted(found)
