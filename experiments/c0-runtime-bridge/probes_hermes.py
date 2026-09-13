#!/usr/bin/env python3
"""probes_hermes.py — C0 Hermes-dependent probes (handoff steps 2+).

Requires a prepared experiment environment (declared variables, no ambient
secrets reach the children either way — the harness allowlist strips them):

  C0_HERMES_PYTHON  dedicated Hermes venv python
  C0_HERMES_SRC     Hermes source checkout pinned to the tested revision
  C0_HERMES_REV     that revision, recorded in every envelope

Without them the runner exits 2 — nothing is silently skipped. These probes
never touch the production ~/.hermes; every run gets a synthetic fixture home
in a temp dir. Not wired into tests/probes.py or CI (experiment scope).

Run: C0_HERMES_PYTHON=... C0_HERMES_SRC=... C0_HERMES_REV=... \\
     python3 experiments/c0-runtime-bridge/probes_hermes.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "fixtures"))

import build as fixtures  # noqa: E402
import harness  # noqa: E402

PASS, FAIL = [], []

CANARIES = [fixtures.CANARY_SECRET, fixtures.CANARY_ENV_VALUE]


def check(probe_id: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(probe_id)
    print(f"[{'PASS' if ok else 'FAIL'}] {probe_id}" + (f" — {detail}" if detail else ""))


def _run_facets(home: Path, facets: str, hermes_python: str, hermes_src: Path,
                hermes_rev: str, timeout_s: int = 60,
                extra: dict | None = None) -> tuple[dict | None, dict, str]:
    env = harness.build_hermes_env(home, hermes_src,
                                   extra={"C0_HERMES_REV": hermes_rev,
                                          **(extra or {})})
    result = harness.run_child(HERE / "bridge.py", ["--facets", facets],
                               env=env, timeout_s=timeout_s,
                               python_executable=hermes_python,
                               workdir=hermes_src)
    envelope, reason = harness.parse_envelope(result)
    return envelope, result, reason


def probe_identity_facet(home_root: Path, hp: str, src: Path, rev: str):
    """MUST-PASS: identity facet reports the Hermes manifest version and the
    recorded source revision; no absolute home paths are serialized."""
    home = fixtures.profile_a(home_root)
    envelope, result, reason = _run_facets(home, "identity", hp, src, rev)
    blob = json.dumps(envelope, ensure_ascii=False) if envelope else ""
    ok = (envelope is not None
          and envelope["source"]["hermes_revision"] == rev
          and envelope["facets"]["identity"]["state"] == "ok"
          and isinstance(envelope["facets"]["identity"]["data"].get("hermes_version"), str)
          and bool(envelope["facets"]["identity"]["data"]["hermes_version"])
          and str(home) not in blob
          and harness.scan_canaries(CANARIES, blob, result["stderr"]) == [])
    check("mustpass_hermes_identity_facet", ok,
          f"version={envelope['facets']['identity']['data'].get('hermes_version') if envelope else '-'}")


def probe_profile_isolation_ab_sequential(home_root: Path, hp: str, src: Path,
                                          rev: str):
    """MUST-PASS gate 1: sequential children for profiles A and B see only
    their own explicit home; no cross-profile bleed."""
    home_a = fixtures.profile_a(home_root)
    home_b = fixtures.profile_b(home_root)
    env_a, res_a, _ = _run_facets(home_a, "config_health", hp, src, rev)
    env_b, res_b, _ = _run_facets(home_b, "config_health", hp, src, rev)
    ok = False
    detail = ""
    if env_a and env_b:
        a = env_a["facets"]["config_health"]["data"].get("primary_model")
        b = env_b["facets"]["config_health"]["data"].get("primary_model")
        ok = (a == "alpha-provider/model-a" and b == "beta-provider/model-b")
        detail = f"A={a!r} B={b!r}"
    else:
        detail = f"reasons: {_short(res_a)} / {_short(res_b)}"
    check("mustpass_profile_isolation_ab_sequential", ok, detail)


def probe_explicit_home_respected(home_root: Path, hp: str, src: Path, rev: str):
    """MUST-PASS gate 7: the child sees only the requested HERMES_HOME —
    the allowlisted environment strips any ambient configuration source."""
    home = fixtures.profile_a(home_root)
    envelope, result, reason = _run_facets(home, "config_health", hp, src, rev)
    ok = (envelope is not None
          and envelope["facets"]["config_health"]["state"] == "ok"
          and envelope["facets"]["config_health"]["data"].get("primary_model")
          == "alpha-provider/model-a")
    check("mustpass_explicit_home_respected", ok,
          f"state={envelope['facets']['config_health']['state'] if envelope else '-'} {_short(result)}")


def probe_malformed_config_not_ok(home_root: Path, hp: str, src: Path, rev: str):
    """MUST-PASS (facet B contract): a broken config.yaml must NOT surface as
    a false canonical ok — the loader's silent fallback becomes visible."""
    home = fixtures.profile_malformed(home_root)
    envelope, result, reason = _run_facets(home, "config_health", hp, src, rev)
    facet = envelope["facets"]["config_health"] if envelope else {}
    ok = (envelope is not None
          and facet.get("state") != "ok"
          and facet.get("data", {}).get("raw_parse_ok") is False
          and facet.get("data", {}).get("primary_model") is None)
    check("mustpass_malformed_config_not_ok", ok,
          f"state={facet.get('state')} reason={facet.get('reason_code')} "
          f"note={facet.get('data', {}).get('note')}")


def probe_secret_nondisclosure(home_root: Path, hp: str, src: Path, rev: str):
    """MUST-PASS gate 2: the .env canary and the declared ${ENV} value never
    reach stdout/stderr/envelope; metadata mode does not hydrate .env."""
    home = fixtures.profile_envref(home_root)
    # .env canary: profile_envref has no .env — use profile A for the dotenv
    # canary and the envref profile for ${ENV}; both scans must be clean.
    home_dotenv = fixtures.profile_a(home_root / ".." / "profile-a-canary")
    envelope_a, res_a, _ = _run_facets(home_dotenv, "config_health", hp, src, rev)
    env_extra = {fixtures.CANARY_ENV_VAR: fixtures.CANARY_ENV_VALUE}
    envelope_b, res_b, _ = _run_facets(home, "config_health", hp, src, rev,
                                       extra=env_extra)
    blob_a = json.dumps(envelope_a, ensure_ascii=False) if envelope_a else ""
    blob_b = json.dumps(envelope_b, ensure_ascii=False) if envelope_b else ""
    leaks = harness.scan_canaries(CANARIES, blob_a, res_a["stdout"], res_a["stderr"],
                                  blob_b, res_b["stdout"], res_b["stderr"])
    ok = (envelope_a is not None and envelope_b is not None and leaks == [])
    check("mustpass_secret_nondisclosure_canary", ok, f"leaks={leaks}")


def probe_import_drift_fail_closed(home_root: Path, hp: str, src: Path, rev: str):
    """MUST-PASS gate 5 + OBSERVATION (imports): a missing Hermes module must
    yield an explicit compatibility_degraded facet, never a crash."""
    home = fixtures.profile_a(home_root)
    env = harness.build_child_env(home, extra={"C0_HERMES_REV": rev})
    env["PYTHONPATH"] = str(home_root / "empty-src")
    env["C0_HERMES_SRC"] = str(home_root / "empty-src")
    result = harness.run_child(HERE / "bridge.py",
                               ["--facets", "config_health,identity"],
                               env=env, timeout_s=60,
                               python_executable=hp, workdir=src)
    envelope, reason = harness.parse_envelope(result)
    ok = False
    detail = reason
    if envelope:
        ch = envelope["facets"]["config_health"]
        ident = envelope["facets"]["identity"]
        ok = (ch.get("state") == "compatibility_degraded"
              and ch.get("reason_code") == "hermes_import_failed"
              and ident.get("state") == "unsupported")
        detail = f"config_health={ch.get('state')}/{ch.get('reason_code')} identity={ident.get('state')}"
    check("mustpass_import_drift_fail_closed", ok, detail)


def probe_write_effects_bounded(home_root: Path, hp: str, src: Path, rev: str):
    """Gate 9 evidence + OBSERVATION: record exactly what a config load
    persists. Writes must stay inside the fixture home (bounded); the fact
    list itself feeds the effect budget decision."""
    home = fixtures.profile_a(home_root)
    before = _snapshot(home)
    envelope, result, reason = _run_facets(home, "config_health", hp, src, rev)
    after = _snapshot(home)
    created = sorted(set(after) - set(before))
    writes = envelope["effects"]["writes"] if envelope else []
    outside = [w for w in writes
               if not w.startswith("{HERMES_HOME}")
               and not w.startswith(str(home_root))]
    ok = (envelope is not None and outside == [])
    check("observation_config_load_write_effects_bounded", ok,
          f"created={created[:5]} audit_writes={writes[:5]} outside={outside}")


def _snapshot(tree: Path) -> dict:
    out = {}
    for path in sorted(tree.rglob("*")):
        stat = path.stat()
        out[str(path.relative_to(tree))] = (stat.st_size, stat.st_mtime_ns)
    return out


def _short(result: dict) -> str:
    return f"status={result.get('status')} rc={result.get('exit_code')} stderr={(result.get('stderr') or '')[-80:]!r}"


def main() -> int:
    hp = os.environ.get("C0_HERMES_PYTHON", "")
    src = os.environ.get("C0_HERMES_SRC", "")
    rev = os.environ.get("C0_HERMES_REV", "")
    if not (hp and src and rev):
        print("c0-hermes-probes: set C0_HERMES_PYTHON, C0_HERMES_SRC, "
              "C0_HERMES_REV (nothing is silently skipped)")
        return 2
    home_root = Path(tempfile.mkdtemp(prefix="c0-hermes-probes-"))
    (home_root / "empty-src").mkdir()
    probe_identity_facet(home_root, hp, Path(src), rev)
    probe_profile_isolation_ab_sequential(home_root, hp, Path(src), rev)
    probe_explicit_home_respected(home_root, hp, Path(src), rev)
    probe_malformed_config_not_ok(home_root, hp, Path(src), rev)
    probe_secret_nondisclosure(home_root, hp, Path(src), rev)
    probe_import_drift_fail_closed(home_root, hp, Path(src), rev)
    probe_write_effects_bounded(home_root, hp, Path(src), rev)
    print(f"\nc0-hermes-probes: {len(PASS)} pass, {len(FAIL)} fail")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
