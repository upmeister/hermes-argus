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

CANARIES = [fixtures.CANARY_SECRET, "C0_DUMMY_INLINE_KEY",
            "C0_DUMMY_QUERY_TOKEN", "C0_DUMMY_AUX_MODEL_VALUE"]


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
    home = fixtures.profile_a(home_root / "identity")
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
    home_a = fixtures.profile_a(home_root / "ab")
    home_b = fixtures.profile_b(home_root / "ab")
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
    home = fixtures.profile_a(home_root / "explicit")
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
    home = fixtures.profile_malformed(home_root / "malformed")
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
    """MUST-PASS gate 2: canary secrets never reach stdout/stderr/envelope —
    the .env dotenv canary (metadata mode does not load it), the inline
    api_key, the MCP URL query token and the declared ${ENV} value."""
    home_dotenv = fixtures.profile_a(home_root / "secrets")
    home_envref = fixtures.profile_envref(home_root / "secrets")
    home_full = fixtures.profile_full_effective(home_root / "secrets")
    envelope_a, res_a, _ = _run_facets(home_dotenv, "config_health", hp, src, rev)
    envelope_b, res_b, _ = _run_facets(home_envref, "effective_config", hp, src, rev,
                                       extra={fixtures.CANARY_ENV_VAR:
                                              fixtures.CANARY_ENV_VALUE})
    envelope_c, res_c, _ = _run_facets(home_full, "effective_config", hp, src, rev,
                                       extra={"C0_AUX_MODEL_VAR":
                                              "C0_DUMMY_AUX_MODEL_VALUE"})
    blobs = [json.dumps(e, ensure_ascii=False) if e else "" for e in
             (envelope_a, envelope_b, envelope_c)]
    leaks = harness.scan_canaries(
        CANARIES, *blobs,
        res_a["stdout"], res_a["stderr"],
        res_b["stdout"], res_b["stderr"],
        res_c["stdout"], res_c["stderr"])
    ok = (envelope_a is not None and envelope_b is not None
          and envelope_c is not None and leaks == [])
    check("mustpass_secret_nondisclosure_canary", ok, f"leaks={leaks}")


def probe_import_drift_fail_closed(home_root: Path, hp: str, src: Path, rev: str):
    """MUST-PASS gate 5 + OBSERVATION (imports): a missing Hermes module must
    yield an explicit compatibility_degraded facet, never a crash."""
    home = fixtures.profile_a(home_root / "drift")
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


def probe_effective_config_allowlist(home_root: Path, hp: str, src: Path, rev: str):
    """MUST-PASS (facet C contract): only allowlisted fields are emitted;
    a ${VAR} value stays in the child as a ref descriptor; credential values
    and MCP env blocks never cross; URLs are sanitized."""
    home = fixtures.profile_full_effective(home_root / "effcfg")
    extra = {fixtures.CANARY_ENV_VAR: fixtures.CANARY_ENV_VALUE,
             "C0_AUX_MODEL_VAR": "C0_DUMMY_AUX_MODEL_VALUE"}
    envelope, result, reason = _run_facets(home, "effective_config", hp, src,
                                           rev, extra=extra)
    ok, detail = False, reason
    if envelope:
        data = envelope["facets"]["effective_config"]["data"]
        blob = json.dumps(envelope, ensure_ascii=False)
        leaks = harness.scan_canaries(CANARIES, blob, result["stdout"],
                                      result["stderr"])
        aux = data["auxiliary"].get("title_generation", {}).get("model", {})
        ok = (
            data["model_primary"] == {"value": "alpha-provider/model-a",
                                      "source": "user"}
            and data["fallback_providers"] == [{"name": "beta-provider"}]
            and data["providers"]["alpha"] == {"base_url_identity":
                                               "https://alpha.invalid/v1",
                                               "auth": "key_env",
                                               "credential_present": False}
            and data["providers"]["inline"]["auth"] == "inline_key"
            and data["providers"]["inline"]["credential_present"] is True
            and data["mcp_servers"]["time"] == {"transport": "stdio",
                                                "command_basename": "uvx",
                                                "args_count": 1}
            and data["mcp_servers"]["notion"]["transport"] == "http"
            and data["mcp_servers"]["notion"]["url_identity"] \
                == "https://mcp.notion.invalid/mcp"
            and aux.get("ref") is True and aux.get("var") == "C0_AUX_MODEL_VAR"
            and aux.get("expanded") is True and aux.get("present") is True
            and leaks == []
        )
        detail = f"leaks={leaks} primary={data['model_primary']} aux={aux}"
    check("mustpass_effective_config_allowlist", ok, detail)


def probe_env_expansion_behavior(home_root: Path, hp: str, src: Path, rev: str):
    """OBSERVATION (contract section 6): ${ENV} behavior on an allowlisted
    path — declared vs undeclared variable. The materialized value must stay
    in the child in both cases; only the ref descriptor is emitted."""
    home = fixtures.profile_envref(home_root / "envexp")
    declared, res_d, _ = _run_facets(home, "effective_config", hp, src, rev,
                                     extra={fixtures.CANARY_ENV_VAR:
                                            fixtures.CANARY_ENV_VALUE})
    undeclared, res_u, _ = _run_facets(home, "effective_config", hp, src, rev)
    ok, detail = False, ""
    if declared and undeclared:
        ref_d = declared["facets"]["effective_config"]["data"]["model_primary"]
        ref_u = undeclared["facets"]["effective_config"]["data"]["model_primary"]
        blob_d = json.dumps(declared, ensure_ascii=False)
        blob_u = json.dumps(undeclared, ensure_ascii=False)
        leaks = harness.scan_canaries(CANARIES, blob_d, blob_u,
                                      res_d["stdout"], res_d["stderr"],
                                      res_u["stdout"], res_u["stderr"])
        ok = (ref_d.get("ref") is True and ref_d.get("expanded") is True
              and ref_d.get("present") is True
              and ref_u.get("ref") is True and ref_u.get("expanded") is False
              and ref_u.get("present") is False
              and leaks == [])
        detail = (f"declared={ref_d} undeclared={ref_u} leaks={leaks}")
    else:
        detail = f"declared={_short(res_d)} undeclared={_short(res_u)}"
    check("observation_env_expansion_behavior", ok, detail)


def probe_runtime_route_metadata_allowlist(home_root: Path, hp: str, src: Path,
                                           rev: str):
    """MUST-PASS (facet D contract): the canonical resolver runs under
    containment; only allowlisted non-secret metadata is emitted; the
    materialized credential value never crosses the boundary."""
    home = fixtures.profile_full_effective(home_root / "route-meta")
    envelope, result, reason = _run_facets(home, "runtime_route", hp, src, rev)
    ok, detail = False, reason
    if envelope:
        facet = envelope["facets"]["runtime_route"]
        routes = facet.get("data", {}).get("routes", {})
        blob = json.dumps(envelope, ensure_ascii=False)
        leaks = harness.scan_canaries(CANARIES, blob, result["stdout"],
                                      result["stderr"])
        inline = routes.get("inline", {})
        alpha = routes.get("alpha", {})
        ok = (
            facet.get("state") in ("ok", "partial")
            and inline.get("state") == "ok"
            and inline.get("provider") == "custom"
            and inline.get("requested_provider") == "inline"
            and inline.get("credential_present") == "yes"
            and inline.get("credential_source") == "pool:custom:inline"
            and inline.get("base_url_identity") == "https://inline.invalid/v1"
            and isinstance(inline.get("api_mode"), str)
            and bool(inline["api_mode"])
            and alpha.get("credential_present") == "placeholder"
            and leaks == []
        )
        detail = (f"state={facet.get('state')} inline={inline} "
                  f"alpha_cred={alpha.get('credential_present')} leaks={leaks}")
    check("mustpass_runtime_route_metadata_allowlist", ok, detail)


def probe_runtime_route_env_ref_nondisclosure(home_root: Path, hp: str,
                                               src: Path, rev: str):
    """MUST-PASS gate 2: runtime routing must not serialize a materialized
    environment value used as the model identity."""
    home = home_root / "route-env-ref"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(
        'model:\n  default: "${C0_CANARY_ENV}"\n'
        'providers:\n  alpha:\n    base_url: "https://alpha.invalid/v1"\n',
        encoding="utf-8", newline="\n")
    envelope, result, reason = _run_facets(
        home, "runtime_route", hp, src, rev,
        extra={fixtures.CANARY_ENV_VAR: fixtures.CANARY_ENV_VALUE})
    blob = json.dumps(envelope, ensure_ascii=False) if envelope else ""
    leaks = harness.scan_canaries(CANARIES, blob, result["stdout"],
                                  result["stderr"])
    check("mustpass_runtime_route_env_ref_nondisclosure",
          envelope is not None and leaks == [],
          f"leaks={leaks} reason={reason}")


def probe_runtime_route_effects_observed(home_root: Path, hp: str, src: Path,
                                         rev: str):
    """OBSERVATION (handoff step 4): the facts the facet decision needs —
    did resolver execution spawn processes, touch the network, write state?
    Effects are captured by the child audit hook; a RED here is the correct
    result for regular-safety and narrows the facet, not the rules."""
    home = fixtures.profile_full_effective(home_root / "route-fx")
    envelope, result, reason = _run_facets(home, "runtime_route", hp, src, rev)
    ok, detail = False, reason
    if envelope:
        effects = envelope.get("effects", {})
        facet = envelope["facets"]["runtime_route"]
        routes = facet.get("data", {}).get("routes", {})
        ok = (isinstance(effects.get("network"), list)
              and isinstance(effects.get("process_spawn"), list)
              and isinstance(effects.get("writes"), list)
              and isinstance(routes, dict) and bool(routes))
        detail = (f"network={effects.get('network')} "
                  f"spawn={effects.get('process_spawn')} "
                  f"writes={effects.get('writes')} "
                  f"routes={sorted(routes)} "
                  f"alpha_cred={routes.get('alpha', {}).get('credential_present')}")
    check("observation_runtime_route_effects_observed", ok, detail)


def _write_sentinel(home: Path, name: str, body: str) -> None:
    plugin_dir = home / "plugins" / "model-providers" / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text(body, encoding="utf-8", newline="\n")


def probe_provider_registry_code_executes(home_root: Path, hp: str, src: Path,
                                          rev: str):
    """OBSERVATION (facet E negative control, contract section 7): does
    provider discovery import user plugin code? A marker-writing sentinel
    answers it. RED is the correct outcome for the regular-mode decision."""
    home = fixtures.profile_a(home_root / "pr-marker")
    _write_sentinel(home, "c0-sentinel",
                    "import os\n"
                    "with open(os.path.join(os.environ['HERMES_HOME'],\n"
                    "                       'c0-plugin-marker.txt'), 'w') as f:\n"
                    "    f.write('C0_PLUGIN_CODE_EXECUTED\\n')\n"
                    "from providers import register_provider\n"
                    "from providers.base import ProviderProfile\n"
                    "register_provider(ProviderProfile(name='c0-sentinel'))\n")
    envelope, result, reason = _run_facets(home, "provider_registry", hp, src,
                                           rev, timeout_s=180)
    marker = home / "c0-plugin-marker.txt"
    facet = envelope["facets"]["provider_registry"] if envelope else {}
    code_executed = marker.exists()
    ok = (envelope is not None and facet.get("state") == "ok"
          and code_executed is True)
    check("observation_provider_registry_code_executes", ok,
          f"code_executed={code_executed} state={facet.get('state')} "
          f"sentinel_registered={facet.get('data', {}).get('sentinel_registered')} "
          f"count={facet.get('data', {}).get('provider_count')}")


def probe_provider_registry_hang_containment(home_root: Path, hp: str,
                                             src: Path, rev: str):
    """OBSERVATION (gate 3 on the real plugin path): a hanging user plugin
    must be killed by the bounded timeout without crashing the harness."""
    home = fixtures.profile_a(home_root / "pr-hang")
    _write_sentinel(home, "c0-hang",
                    "import os, time\n"
                    "with open(os.path.join(os.environ['HERMES_HOME'],\n"
                    "                       'c0-plugin-marker.txt'), 'w') as f:\n"
                    "    f.write('started\\n')\n"
                    "time.sleep(600)\n")
    import time as _time
    start = _time.monotonic()
    envelope, result, reason = _run_facets(home, "provider_registry", hp, src,
                                           rev, timeout_s=20)
    elapsed = _time.monotonic() - start
    marker = home / "c0-plugin-marker.txt"
    ok = (result["status"] == "timeout" and result.get("error_kind") is None
          and elapsed < 60 and marker.exists())
    check("observation_provider_registry_hang_containment", ok,
          f"status={result['status']} elapsed={elapsed:.1f}s marker={marker.exists()}")


def probe_provider_registry_raise_degrades(home_root: Path, hp: str,
                                           src: Path, rev: str):
    """OBSERVATION: a raising user plugin must degrade explicitly (facet
    error or documented discovery continuation), never crash before JSON."""
    home = fixtures.profile_a(home_root / "pr-raise")
    _write_sentinel(home, "c0-raiser",
                    "import os\n"
                    "with open(os.path.join(os.environ['HERMES_HOME'],\n"
                    "                       'c0-plugin-marker.txt'), 'w') as f:\n"
                    "    f.write('started\\n')\n"
                    "raise RuntimeError('C0 sentinel plugin failure')\n")
    envelope, result, reason = _run_facets(home, "provider_registry", hp, src,
                                           rev, timeout_s=180)
    marker = home / "c0-plugin-marker.txt"
    facet = envelope["facets"]["provider_registry"] if envelope else {}
    ok = (envelope is not None
          and facet.get("state") in ("ok", "partial", "error")
          and marker.exists())
    check("observation_provider_registry_raise_degrades", ok,
          f"state={facet.get('state')} reason={facet.get('reason_code')} "
          f"marker={marker.exists()} envelope_valid={envelope is not None}")


def probe_write_effects_bounded(home_root: Path, hp: str, src: Path, rev: str):
    """Gate 9 evidence + OBSERVATION: record exactly what a config load
    persists. Writes must stay inside the fixture home (bounded); the fact
    list itself feeds the effect budget decision."""
    home = fixtures.profile_a(home_root / "we")
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
          f"reason={reason} status={result.get('status')} rc={result.get('exit_code')} "
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
    probe_effective_config_allowlist(home_root, hp, Path(src), rev)
    probe_env_expansion_behavior(home_root, hp, Path(src), rev)
    probe_runtime_route_metadata_allowlist(home_root, hp, Path(src), rev)
    probe_runtime_route_env_ref_nondisclosure(home_root, hp, Path(src), rev)
    probe_runtime_route_effects_observed(home_root, hp, Path(src), rev)
    probe_provider_registry_code_executes(home_root, hp, Path(src), rev)
    probe_provider_registry_raise_degrades(home_root, hp, Path(src), rev)
    probe_provider_registry_hang_containment(home_root, hp, Path(src), rev)
    probe_write_effects_bounded(home_root, hp, Path(src), rev)
    print(f"\nc0-hermes-probes: {len(PASS)} pass, {len(FAIL)} fail")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
