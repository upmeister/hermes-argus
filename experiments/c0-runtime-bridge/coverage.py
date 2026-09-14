#!/usr/bin/env python3
"""coverage.py — C0 coverage comparison (handoff step 6).

For each scenario: build the synthetic fixture, run static Argus discovery
(`scripts/integration-discover.py` at the recorded Argus revision, pointed at
the fixture via HERMES_DIR), run the bridge facets under containment, and
record the comparison against hand-coded expected facts.

The output is a facts table — gain/no-gain/regression labels here are
evidence for the receipt, not decisions (the GO/MODIFY/DROP call belongs to
the analyst/Питна). No production credentials, no network, no writes outside
the fixture/temp dirs.

Requires declared variables (nothing silently skipped):
  C0_HERMES_PYTHON  dedicated Hermes venv python
  C0_HERMES_SRC     Hermes source checkout (tested revision)
  C0_HERMES_REV     that revision
  C0_STATIC_DISCOVER path to scripts/integration-discover.py (Argus checkout)
  C0_ARGUS_REV      Argus revision of that checkout
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


def check(scenario: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(scenario)
    print(f"[{'EXECUTED' if ok else 'INCOMPLETE'}] {scenario}"
          + (f" — {detail}" if detail else ""))


def _run_static(home: Path, discover: Path, hermes_python: str,
                rev: str) -> tuple[dict | None, dict]:
    env = harness.build_child_env(home, extra={
        "HERMES_DIR": str(home), "C0_ARGUS_REV": rev})
    (home / "state").mkdir(parents=True, exist_ok=True)
    result = harness.run_child(discover, [], env=env, timeout_s=60,
                               python_executable=hermes_python)
    snapshot_path = home / "state" / "integration-snapshot.json"
    snapshot = None
    if snapshot_path.exists():
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            snapshot = None
    return snapshot, result


def _run_bridge(home: Path, facets: str, hp: str, src: Path, rev: str,
                extra: dict | None = None):
    env = harness.build_hermes_env(home, src,
                                   extra={"C0_HERMES_REV": rev,
                                          **(extra or {})})
    result = harness.run_child(HERE / "bridge.py", ["--facets", facets],
                               env=env, timeout_s=120,
                               python_executable=hp, workdir=src)
    envelope, reason = harness.parse_envelope(result)
    return envelope, result, reason


def _entity_names(snapshot) -> set:
    return set((snapshot or {}).get("entities") or {})


def scenario_providers_named(root, hp, src, rev, discover, argus_rev):
    """Named custom providers: endpoints + auth class, both views."""
    home = fixtures.profile_full_effective(root / "providers")
    snapshot, static_res = _run_static(home, discover, hp, argus_rev)
    envelope, bridge_res, reason = _run_bridge(home, "effective_config", hp,
                                               src, rev)
    static_names = {k for k in _entity_names(snapshot)
                    if k.startswith("provider:")}
    bridge = (envelope or {})["facets"]["effective_config"]["data"]
    bridge_names = set(bridge.get("providers", {}))
    facts = {
        "expected": {"alpha": "key_env + https://alpha.invalid/v1",
                     "inline": "inline api_key + https://inline.invalid/v1"},
        "static_entities": sorted(static_names),
        "static_key_present": {k.split(":")[1]:
                               (snapshot or {})["entities"].get(k, {}).get("key_present")
                               for k in sorted(static_names)},
        "bridge_providers": bridge.get("providers", {}),
        "bridge_runtime_route_credential": "see step-4 receipt rows "
                                           "(alpha=placeholder via no-key-required, inline=yes)",
    }
    ok = (static_names == {"provider:alpha", "provider:inline"}
          and bridge_names == {"alpha", "inline"}
          and bridge["providers"]["alpha"]["base_url_identity"]
          == "https://alpha.invalid/v1"
          and bridge["providers"]["inline"]["credential_present"] is True)
    label = "parity (both see both providers, sanitized; presence semantics differ - see facts)"
    return ok, facts, label


def scenario_model_refs(root, hp, src, rev, discover, argus_rev):
    """Primary / fallback_providers / auxiliary model references."""
    home = fixtures.profile_full_effective(root / "modelrefs")
    snapshot, static_res = _run_static(home, discover, hp, argus_rev)
    envelope, bridge_res, reason = _run_bridge(home, "effective_config", hp,
                                               src, rev)
    entities = (snapshot or {}).get("entities") or {}
    static_models = sorted(k for k in entities if k.startswith("model:"))
    data = (envelope or {})["facets"]["effective_config"]["data"]
    facts = {
        "expected": {"primary": "alpha-provider/model-a",
                     "fallback_providers": ["beta-provider"],
                     "auxiliary_title_generation": "${C0_AUX_MODEL_VAR} ref"},
        "static_model_entities": static_models,
        "bridge_primary": data.get("model_primary"),
        "bridge_fallback": data.get("fallback_providers"),
        "bridge_auxiliary": data.get("auxiliary"),
        "static_run": {"status": static_res["status"],
                       "rc": static_res["exit_code"]},
    }
    ok = (envelope is not None
          and data.get("model_primary", {}).get("value") == "alpha-provider/model-a"
          and data.get("fallback_providers") == [{"name": "beta-provider"}])
    label = ("bridge_gain: fallback_providers (list) and auxiliary."
             "title_generation are not surfaced by static discovery"
             if static_models == ["model:primary"] else "check static output")
    return ok, facts, label


def scenario_mcp(root, hp, src, rev, discover, argus_rev):
    """MCP declarations: stdio command and http URL (token sanitized)."""
    home = fixtures.profile_full_effective(root / "mcp")
    snapshot, static_res = _run_static(home, discover, hp, argus_rev)
    envelope, bridge_res, reason = _run_bridge(home, "effective_config", hp,
                                               src, rev)
    entities = (snapshot or {}).get("entities") or {}
    static_mcp = {k: v for k, v in entities.items() if k.startswith("mcp:")}
    data = (envelope or {})["facets"]["effective_config"]["data"]
    facts = {
        "expected": {"time": "stdio/uvx", "notion": "http, token sanitized"},
        "static_mcp": static_mcp,
        "bridge_mcp": data.get("mcp_servers", {}),
    }
    ok = (set(static_mcp) == {"mcp:time", "mcp:notion"}
          and data.get("mcp_servers", {}).get("time", {}).get("transport") == "stdio"
          and data.get("mcp_servers", {}).get("notion", {}).get("url_identity")
          == "https://mcp.notion.invalid/mcp")
    label = "parity (both sanitize the URL token)"
    return ok, facts, label


def scenario_env_ref(root, hp, src, rev, discover, argus_rev):
    """${ENV} reference: entity presence + expansion fact (undeclared var)."""
    home = fixtures.profile_envref(root / "envref")
    snapshot, static_res = _run_static(home, discover, hp, argus_rev)
    envelope, bridge_res, reason = _run_bridge(home, "effective_config", hp,
                                               src, rev)
    entities = (snapshot or {}).get("entities") or {}
    static_envref = {k: v for k, v in entities.items()
                     if k.startswith("envref:")}
    ref = (envelope or {})["facets"]["effective_config"]["data"].get(
        "model_primary", {})
    facts = {
        "expected": {"ref": "C0_CANARY_ENV on model.default, undeclared",
                     "expansion": "template preserved"},
        "static_envref": static_envref,
        "bridge_ref": ref,
    }
    ok = (envelope is not None
          and ref.get("ref") is True and ref.get("expanded") is False)
    label = "parity (bridge adds the canonical expansion fact)"
    return ok, facts, label


def scenario_malformed_config(root, hp, src, rev, discover, argus_rev):
    """Broken config.yaml: static crashes unstructured; bridge reports the
    canonical degradation (config_health)."""
    home = fixtures.profile_malformed(root / "malformed")
    snapshot, static_res = _run_static(home, discover, hp, argus_rev)
    envelope, bridge_res, reason = _run_bridge(home, "config_health", hp,
                                               src, rev)
    facet = (envelope or {})["facets"]["config_health"] if envelope else {}
    facts = {
        "expected": "parse failure visible, no false ok",
        "static_run": {"status": static_res["status"],
                       "rc": static_res["exit_code"],
                       "snapshot_exists": (home / "state" /
                                           "integration-snapshot.json").exists()},
        "bridge_facet": {"state": facet.get("state"),
                         "reason_code": facet.get("reason_code"),
                         "raw_parse_ok": facet.get("data", {}).get("raw_parse_ok")},
    }
    ok = (envelope is not None
          and facet.get("state") == "partial"
          and static_res["exit_code"] != 0)
    label = ("bridge_gain: canonical partial/config_parse_fallback vs an "
             "unstructured static-discover crash")
    return ok, facts, label


def scenario_user_plugin(root, hp, src, rev, discover, argus_rev):
    """User model-provider plugin: runtime registration (bridge, executes
    plugin code) vs static plugin.yaml manifest view."""
    home = fixtures.profile_a(root / "plugin")
    plugin_dir = home / "plugins" / "model-providers" / "c0-sentinel"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text(
        "from providers import register_provider\n"
        "from providers.base import ProviderProfile\n"
        "register_provider(ProviderProfile(name='c0-sentinel', "
        "display_name='C0 Sentinel'))\n",
        encoding="utf-8", newline="\n")
    snapshot, static_res = _run_static(home, discover, hp, argus_rev)
    envelope, bridge_res, reason = _run_bridge(home, "provider_registry", hp,
                                               src, rev)
    entities = (snapshot or {}).get("entities") or {}
    static_plugins = sorted(k for k in entities
                            if k.startswith("plugin-provider:"))
    facet = (envelope or {})["facets"]["provider_registry"] if envelope else {}
    facts = {
        "expected": {"sentinel": "registered at runtime by user plugin code"},
        "static_plugin_entities": static_plugins,
        "bridge": {"state": facet.get("state"),
                   "sentinel_registered":
                       facet.get("data", {}).get("sentinel_registered"),
                   "provider_count": facet.get("data", {}).get("provider_count")},
        "caveat": "bridge gain requires plugin code execution (facet E RED "
                  "for regular mode)",
    }
    ok = (envelope is not None
          and facet.get("data", {}).get("sentinel_registered") is True)
    label = ("bridge_gain: runtime-registered user provider is visible only "
             "to the bridge; static sees only plugin.yaml manifests")
    return ok, facts, label


def scenario_oauth_metadata(root, hp, src, rev, discover, argus_rev):
    """OAuth metadata: static reads auth.json; the bridge has no OAuth facet
    in C0 scope (honest static gain)."""
    home = fixtures.profile_a(root / "oauth")
    (home / "auth.json").write_text(json.dumps({
        "providers": {"nous": {"access_token": "C0_DUMMY_OAUTH_TOKEN"}},
        "active_provider": "nous"}), encoding="utf-8", newline="\n")
    snapshot, static_res = _run_static(home, discover, hp, argus_rev)
    entities = (snapshot or {}).get("entities") or {}
    static_oauth = {k: v for k, v in entities.items() if k.startswith("oauth:")}
    facts = {
        "expected": {"nous": "oauth flow with token present"},
        "static_oauth": static_oauth,
        "bridge": "no OAuth facet in C0 scope (contract section 3 out-of-scope)",
    }
    ok = "oauth:nous" in static_oauth
    label = "static_gain: OAuth metadata is static-only in C0 scope"
    return ok, facts, label


def main() -> int:
    hp = os.environ.get("C0_HERMES_PYTHON", "")
    src = os.environ.get("C0_HERMES_SRC", "")
    rev = os.environ.get("C0_HERMES_REV", "")
    discover = os.environ.get("C0_STATIC_DISCOVER", "")
    argus_rev = os.environ.get("C0_ARGUS_REV", "")
    missing = [name for name, value in (
        ("C0_HERMES_PYTHON", hp), ("C0_HERMES_SRC", src),
        ("C0_HERMES_REV", rev), ("C0_STATIC_DISCOVER", discover),
        ("C0_ARGUS_REV", argus_rev)) if not value]
    if missing:
        print("c0-coverage: set " + ", ".join(missing)
              + " (nothing is silently skipped)")
        return 2

    root = Path(tempfile.mkdtemp(prefix="c0-coverage-"))
    scenarios = [
        ("providers_named", scenario_providers_named),
        ("model_refs", scenario_model_refs),
        ("mcp_declarations", scenario_mcp),
        ("env_ref", scenario_env_ref),
        ("malformed_config", scenario_malformed_config),
        ("user_plugin", scenario_user_plugin),
        ("oauth_metadata", scenario_oauth_metadata),
    ]
    report = {"argus_static_rev": argus_rev, "hermes_rev": rev,
              "scenarios": {}}
    for name, fn in scenarios:
        ok, facts, label = fn(root, hp, Path(src), rev, Path(discover),
                              argus_rev)
        check(name, ok, label)
        report["scenarios"][name] = {"executed": ok, "label": label,
                                     "facts": facts}
    counts = {"static_gain": 0, "bridge_gain": 0, "parity": 0}
    for s in report["scenarios"].values():
        for key in counts:
            if s["label"].startswith(key.split("_")[0]) and key in s["label"]:
                counts[key] += 1
                break
    report["label_counts"] = counts
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nc0-coverage: {len(PASS)} executed, {len(FAIL)} incomplete")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
