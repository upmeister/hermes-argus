#!/usr/bin/env python3
"""probes.py — C0 containment probes (handoff step 1).

These probes exercise harness containment with synthetic fake children:
no Hermes import, no network, no credentials, no persistent writes outside
the probe temp dir. Probe names carry the contract test class (C0 contract
section 6): MUST-PASS gates block the design; OBSERVATION probes record
facts where RED may be the correct outcome.

Run: python3 experiments/c0-runtime-bridge/probes.py

Works on POSIX and Windows; the same file is re-run on peetna-aws before any
Hermes-backed facet is attempted. Not wired into tests/probes.py or CI by
design (experiment scope).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harness  # noqa: E402

PASS, FAIL = [], []

CANARY_SECRET = "C0_DUMMY_CANARY_SECRET"
PARENT_TOKEN_VAR = "C0_PARENT_TOKEN"


def check(probe_id: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(probe_id)
    print(f"[{'PASS' if ok else 'FAIL'}] {probe_id}" + (f" — {detail}" if detail else ""))


def _write_child(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8", newline="\n")
    return p


def _home(tmp: Path, name: str) -> Path:
    home = tmp / name
    home.mkdir(parents=True, exist_ok=True)
    return home


def _snapshot(tree: Path) -> dict:
    out = {}
    for path in sorted(tree.rglob("*")):
        stat = path.stat()
        out[str(path.relative_to(tree))] = (stat.st_size, stat.st_mtime_ns)
    return out


def probe_env_allowlist_no_inheritance(tmp: Path):
    """MUST-PASS (contract section 10): unrelated parent secrets are not
    inherited; declared fixture variables and bridge flags are."""
    child = _write_child(tmp, "env_dump_child.py",
                         "import json, os\nprint(json.dumps(dict(os.environ)))\n")
    home = _home(tmp, "profile-env")
    os.environ[PARENT_TOKEN_VAR] = CANARY_SECRET
    try:
        env = harness.build_child_env(home, extra={"C0_CANARY_ENV": "declared-value"})
        result = harness.run_child(child, env=env, timeout_s=15)
    finally:
        del os.environ[PARENT_TOKEN_VAR]
    child_env = json.loads(result["stdout"]) if result["status"] == "ok" else {}
    leaks = harness.scan_canaries([CANARY_SECRET], result["stdout"], result["stderr"])
    ok = (result["status"] == "ok"
          and not leaks
          and PARENT_TOKEN_VAR not in child_env
          and child_env.get("HERMES_HOME") == str(home)
          and child_env.get("PYTHONDONTWRITEBYTECODE") == "1"
          and child_env.get("C0_CANARY_ENV") == "declared-value")
    check("mustpass_env_allowlist_no_inheritance", ok,
          f"leaks={leaks} hermes_home_ok={child_env.get('HERMES_HOME') == str(home)}")


def probe_timeout_bounded_cleanup(tmp: Path):
    """MUST-PASS gate 3: child timeout is bounded and cleanup is deterministic."""
    child = _write_child(tmp, "sleep_child.py", "import time; time.sleep(60)\n")
    env = harness.build_child_env(_home(tmp, "profile-timeout"))
    start = time.monotonic()
    result = harness.run_child(child, env=env, timeout_s=2)
    elapsed = time.monotonic() - start
    ok = (result["status"] == "timeout" and result["timed_out"]
          and result.get("error_kind") is None
          and elapsed < harness.DEFAULT_TIMEOUT_S)
    check("mustpass_timeout_bounded_cleanup", ok,
          f"elapsed={elapsed:.1f}s status={result['status']}")


def probe_malformed_output_fail_closed(tmp: Path):
    """MUST-PASS gate 4: malformed/partial/empty output fails closed."""
    env = harness.build_child_env(_home(tmp, "profile-garbage"))
    garbage = _write_child(tmp, "garbage_child.py", "print('not json')\n")
    envelope, reason = harness.parse_envelope(
        harness.run_child(garbage, env=env, timeout_s=15))
    ok_garbage = envelope is None and "not JSON" in reason

    two = _write_child(tmp, "two_envelopes_child.py",
                       "print('{}'); print('{}')\n")
    envelope, reason = harness.parse_envelope(
        harness.run_child(two, env=env, timeout_s=15))
    ok_two = envelope is None and "not JSON" in reason

    empty = _write_child(tmp, "empty_child.py", "import sys; sys.stdout.write('')\n")
    envelope, reason = harness.parse_envelope(
        harness.run_child(empty, env=env, timeout_s=15))
    ok_empty = envelope is None and "empty child stdout" in reason
    check("mustpass_malformed_output_fail_closed",
          ok_garbage and ok_two and ok_empty,
          f"garbage={ok_garbage} two={ok_two} empty={ok_empty}")


def probe_child_crash_containment(tmp: Path):
    """MUST-PASS gate 5: child crash/import error does not crash the harness."""
    env = harness.build_child_env(_home(tmp, "profile-crash"))
    hard_exit = _write_child(tmp, "hard_exit_child.py", "import os; os._exit(3)\n")
    result = harness.run_child(hard_exit, env=env, timeout_s=15)
    envelope, reason = harness.parse_envelope(result)
    ok_exit = (result["status"] == "ok" and result["exit_code"] == 3
               and envelope is None and "exit code 3" in reason)

    crash = _write_child(tmp, "crash_child.py",
                         "raise RuntimeError('dummy bridge crash before envelope')\n")
    result = harness.run_child(crash, env=env, timeout_s=15)
    envelope, reason = harness.parse_envelope(result)
    ok_crash = (result["status"] == "ok" and envelope is None
                and result["exit_code"] == 1 and "exit code 1" in reason
                and "dummy bridge crash" in (result["stderr"] or ""))
    check("mustpass_child_crash_containment", ok_exit and ok_crash,
          f"exit={ok_exit} crash={ok_crash}")


def probe_output_cap_enforced(tmp: Path):
    """MUST-PASS gate 6: the output-size limit is enforced on both streams."""
    env = harness.build_child_env(_home(tmp, "profile-flood"))
    cap = 64 * 1024
    flood_out = _write_child(tmp, "flood_stdout_child.py",
                             "import os, sys; sys.stdout.write('C0' * 4 * 1024 * 1024); sys.stdout.flush(); "
                             "open(os.path.join(os.environ['HERMES_HOME'], 'stdout-after-flood'), 'w').write('reached')\n")
    result = harness.run_child(flood_out, env=env, timeout_s=30, output_cap=cap)
    ok_out = (result["status"] == "output_limit" and result["output_limited"]
              and result["stdout_truncated"]
              and not (Path(env["HERMES_HOME"]) / "stdout-after-flood").exists()
              and len(result["stdout"]) == cap)
    flood_err = _write_child(tmp, "flood_stderr_child.py",
                             "import os, sys; sys.stderr.write('C0' * 4 * 1024 * 1024); sys.stderr.flush(); "
                             "open(os.path.join(os.environ['HERMES_HOME'], 'stderr-after-flood'), 'w').write('reached')\n")
    result = harness.run_child(flood_err, env=env, timeout_s=30, output_cap=cap)
    ok_err = (result["status"] == "output_limit" and result["output_limited"]
              and result["stderr_truncated"]
              and not (Path(env["HERMES_HOME"]) / "stderr-after-flood").exists()
              and len(result["stderr"]) == cap)
    check("mustpass_output_cap_enforced", ok_out and ok_err,
          f"stdout={ok_out} stderr={ok_err}")


def probe_canary_scan_selfcheck(tmp: Path):
    """MUST-PASS gate 2 (mechanism): the canary leak scan flags a leaking
    child and stays silent on a clean one."""
    env = harness.build_child_env(_home(tmp, "profile-leak"))
    leaker = _write_child(tmp, "leak_child.py",
                          f"print('endpoint said {CANARY_SECRET} at 12:00')\n")
    result = harness.run_child(leaker, env=env, timeout_s=15)
    found = harness.scan_canaries([CANARY_SECRET], result["stdout"], result["stderr"])
    clean = _write_child(tmp, "clean_child.py", "print('nothing to see')\n")
    result = harness.run_child(clean, env=env, timeout_s=15)
    clean_found = harness.scan_canaries([CANARY_SECRET], result["stdout"],
                                        result["stderr"])
    check("mustpass_canary_scan_selfcheck",
          found == [CANARY_SECRET] and clean_found == [],
          f"leak_found={found} clean_found={clean_found}")


def probe_profile_home_passthrough(tmp: Path):
    """MUST-PASS gate 7 (harness level): the requested HERMES_HOME is what the
    child sees, and sequential runs for distinct profiles do not bleed."""
    child = _write_child(tmp, "home_echo_child.py",
                         "import os; print(os.environ.get('HERMES_HOME', ''))\n")
    home_a = _home(tmp, "profile-a")
    home_b = _home(tmp, "profile-b")
    seen_a = ""
    seen_b = ""
    for home, store in ((home_a, "a"), (home_b, "b")):
        result = harness.run_child(child, env=harness.build_child_env(home),
                                   timeout_s=15)
        value = result["stdout"].strip() if result["status"] == "ok" else ""
        if store == "a":
            seen_a = value
        else:
            seen_b = value
    check("mustpass_profile_home_passthrough",
          seen_a == str(home_a) and seen_b == str(home_b),
          f"a={seen_a!r} b={seen_b!r}")


def probe_reserved_env_and_missing_env_fail_closed(tmp: Path):
    """MUST-PASS: reserved containment keys cannot be overridden and omitting
    an explicit environment never falls back to parent inheritance."""
    home = _home(tmp, "profile-env-boundary")
    rejected = False
    try:
        harness.build_child_env(home, extra={"HOME": str(tmp / "wrong")})
    except ValueError:
        rejected = True
    child = _write_child(tmp, "parent_env_child.py",
                         "import os; print(os.environ.get('C0_PARENT_TOKEN', ''))\n")
    old = os.environ.get(PARENT_TOKEN_VAR)
    os.environ[PARENT_TOKEN_VAR] = CANARY_SECRET
    try:
        result = harness.run_child(child, timeout_s=15)
    finally:
        if old is None:
            os.environ.pop(PARENT_TOKEN_VAR, None)
        else:
            os.environ[PARENT_TOKEN_VAR] = old
    ok = (rejected and result["status"] == "invalid_env"
          and not result["stdout"]
          and result.get("error_kind") == "env_required")
    check("mustpass_reserved_env_and_missing_env_fail_closed", ok,
          f"reserved_rejected={rejected} status={result['status']}")


def probe_write_detector_selfcheck(tmp: Path):
    """OBSERVATION mechanism self-check: the write detector notices a child
    that persists state inside HERMES_HOME and silence from a clean one.
    The real no-write gate applies to Hermes facets in step 2+."""
    home = _home(tmp, "profile-write")
    env = harness.build_child_env(home)
    clean = _write_child(tmp, "quiet_child.py", "print('ok')\n")
    before = _snapshot(home)
    harness.run_child(clean, env=env, timeout_s=15)
    unchanged = _snapshot(home) == before

    writer = _write_child(tmp, "writing_child.py",
                          "import os\n"
                          "p = os.path.join(os.environ['HERMES_HOME'], 'marker.txt')\n"
                          "open(p, 'w').write('C0_DUMMY_MARKER')\n"
                          "print('wrote')\n")
    harness.run_child(writer, env=env, timeout_s=15)
    after = _snapshot(home)
    detected = "marker.txt" in after and after != before
    check("observation_write_detector_selfcheck", unchanged and detected,
          f"clean_unchanged={unchanged} write_detected={detected}")


def probe_bridge_envelope_contract(tmp: Path):
    """The real bridge entrypoint emits a contract-valid envelope under
    containment: caller-supplied profile label (never derived from the home
    path), requested facet unsupported (no Hermes yet), unknown facet fails
    closed inside the envelope, no crash before JSON."""
    env = harness.build_child_env(_home(tmp, "profile-bridge"))
    result = harness.run_child(HERE / "bridge.py",
                               ["--facets", "identity",
                                "--profile-id", "probe-label"],
                               env=env, timeout_s=30)
    envelope, reason = harness.parse_envelope(result)
    ok_identity = (envelope is not None
                   and envelope["source"]["profile_id"] == "probe-label"
                   and envelope["facets"]["identity"]["state"] == "unsupported")
    result = harness.run_child(HERE / "bridge.py",
                               ["--facets", "nonexistent_facet",
                                "--profile-id", "probe-label"], env=env,
                               timeout_s=30)
    envelope, reason = harness.parse_envelope(result)
    ok_unknown = (envelope is not None
                  and envelope["facets"]["nonexistent_facet"]["state"] == "error"
                  and envelope["facets"]["nonexistent_facet"]["reason_code"]
                  == "unknown_facet")
    check("mustpass_bridge_envelope_contract", ok_identity and ok_unknown,
          f"identity={ok_identity} unknown={ok_unknown} reason={reason}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="c0-probes-"))
    probe_env_allowlist_no_inheritance(tmp)
    probe_timeout_bounded_cleanup(tmp)
    probe_malformed_output_fail_closed(tmp)
    probe_child_crash_containment(tmp)
    probe_output_cap_enforced(tmp)
    probe_canary_scan_selfcheck(tmp)
    probe_profile_home_passthrough(tmp)
    probe_reserved_env_and_missing_env_fail_closed(tmp)
    probe_write_detector_selfcheck(tmp)
    probe_bridge_envelope_contract(tmp)
    print(f"\nc0-probes: {len(PASS)} pass, {len(FAIL)} fail")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
