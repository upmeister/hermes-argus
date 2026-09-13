#!/usr/bin/env python3
"""bridge.py — C0 bridge child entrypoint (experimental compatibility seam).

Runs inside a short-lived child process with an explicit HERMES_HOME and an
allowlisted environment built by harness.py. It prints exactly one allowlisted
JSON envelope to stdout and nothing else. Facets are independent: one facet's
failure must not invalidate others, and a facet that cannot be obtained safely
reports an explicit unsupported/degraded state instead of guessed data (C0
experiment contract section 5).

Step 1 (containment): no Hermes import happens here yet — the harness probes
use fake children, and this entrypoint only proves the envelope contract.
Hermes-backed facet loaders are added in step 2+ behind the same registry.

Forbidden as the primary safety mechanism (contract section 5):
json.dumps(config) / vars(runtime) / repr(runtime) — the boundary is
allowlist extraction, never broad serialization followed by redaction.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BRIDGE_SCHEMA = 1
BRIDGE_REVISION = "step2-hermes-facets"

EFFECTS_AUDIT_LIMIT = 50

# Facet loaders are registered here; each returns a facet dict:
# {"state": ..., "authority": ..., "api": ..., "reason_code": ..., "data": {...}}
FACET_LOADERS: dict[str, object] = {}


def install_effects_audit() -> dict:
    """Install a Python audit hook and record process-boundary effects.

    Captures socket.connect, subprocess.Popen and write-mode file opens made
    by this child (including everything the Hermes seams do), so "no side
    effect" claims carry in-process evidence. Paths are relativized against
    HERMES_HOME. The hook itself never raises.
    """
    effects: dict = {"network": [], "process_spawn": [], "writes": [],
                     "truncated": False}
    state = {"seen": 0}
    home = os.environ.get("HERMES_HOME", "")

    def _rel(path) -> str:
        try:
            text = str(path)
        except Exception:
            return "<unprintable>"
        if home and text.startswith(home):
            return "{HERMES_HOME}" + text[len(home):]
        return text

    def _hook(event, args):
        if state["seen"] >= EFFECTS_AUDIT_LIMIT:
            effects["truncated"] = True
            return
        try:
            if event == "socket.connect":
                effects["network"].append(_rel(args[1]) if args else "<unknown>")
                state["seen"] += 1
            elif event == "subprocess.Popen":
                effects["process_spawn"].append(_rel(args[0]) if args else "<unknown>")
                state["seen"] += 1
            elif event == "open":
                path = args[0] if args else None
                mode = args[1] if len(args) > 1 else None
                flags = args[2] if len(args) > 2 else None
                write_mode = isinstance(mode, str) and any(c in mode for c in "wax+")
                write_flags = isinstance(flags, int) and (flags & (
                    os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC))
                if write_mode or write_flags:
                    effects["writes"].append(_rel(path))
                    state["seen"] += 1
        except Exception:
            pass

    sys.addaudithook(_hook)
    return effects


def _facet_unsupported(reason_code: str, authority: str = "unknown") -> dict:
    return {"state": "unsupported", "authority": authority,
            "reason_code": reason_code, "data": {}}


def _hermes_version_from_source() -> str | None:
    """Read the version from the selected source tree's own pyproject manifest.
    api: pyproject.toml::project.version (authority: hermes manifest)."""
    src = os.environ.get("C0_HERMES_SRC", "")
    if not src:
        return None
    try:
        import tomllib
        with open(Path(src) / "pyproject.toml", "rb") as f:
            return tomllib.load(f).get("project", {}).get("version")
    except Exception:
        return None


def facet_identity(profile_id: str) -> dict:
    """Hermes identity metadata from the selected source manifest."""
    version = _hermes_version_from_source()
    if version is None:
        return _facet_unsupported("hermes_source_not_declared", "argus")
    return {"state": "ok", "authority": "hermes",
            "api": "pyproject.toml::project.version", "reason_code": "ok",
            "data": {"hermes_version": version}}


def facet_config_health(profile_id: str) -> dict:
    """Distinguish 'loader returned data' from 'parse failure / fallback'.

    api: hermes_cli.config.load_config_readonly + read_user_config_raw.
    load_config_readonly() may silently serve a last-known-good config or
    defaults when config.yaml is broken; read_user_config_raw() raises on a
    broken YAML, which is the canonical raw-parse probe. Only allowlisted,
    non-secret fields are emitted (primary model identity, booleans).
    """
    api = "hermes_cli.config.load_config_readonly + read_user_config_raw"
    try:
        from hermes_cli import config as hc
    except Exception as exc:
        return {"state": "compatibility_degraded", "authority": "hermes",
                "api": api, "reason_code": "hermes_import_failed",
                "data": {"exception_class": type(exc).__name__}}
    try:
        cfg_path = Path(hc.get_config_path())
    except Exception:
        cfg_path = Path(os.environ.get("HERMES_HOME", "")) / "config.yaml"
    present = cfg_path.exists()
    raw_parse_ok = None
    note = ""
    if present:
        try:
            raw = hc.read_user_config_raw()
            raw_parse_ok = isinstance(raw, dict) and bool(raw)
            if not raw:
                note = "raw file empty or non-dict root"
        except Exception as exc:
            raw_parse_ok = False
            note = f"raw parse failed ({type(exc).__name__})"
    try:
        loaded = hc.load_config_readonly()
    except Exception as exc:
        return {"state": "error", "authority": "hermes", "api": api,
                "reason_code": "load_config_raised",
                "data": {"exception_class": type(exc).__name__}}
    load_ok = isinstance(loaded, dict) and bool(loaded)
    # Allowlist extraction only; `loaded` (and everything nested) is never
    # mutated — it may be the loader's in-process cache object.
    model = loaded.get("model") if isinstance(loaded, dict) else None
    primary = None
    if isinstance(model, dict):
        value = model.get("default", model.get("model"))
        primary = value if isinstance(value, str) else None
    if not present:
        state, reason = "ok", "config_absent_defaults"
    elif raw_parse_ok:
        state, reason = "ok", "config_parsed"
    elif raw_parse_ok is False:
        # Loader served last-known-good or defaults while the raw file is
        # broken — exactly what config_health must make visible.
        state, reason = "partial", "config_parse_fallback"
    else:
        state, reason = "error", "raw_parse_unknown"
    if not load_ok:
        state, reason = "error", "load_failed"
    return {"state": state, "authority": "hermes", "api": api,
            "reason_code": reason,
            "data": {"config_file_present": present, "raw_parse_ok": raw_parse_ok,
                     "load_ok": load_ok, "primary_model": primary, "note": note}}


def facet_effective_config(profile_id: str) -> dict:
    """Allowlisted effective-config fields for the coverage comparison
    (step 3). Never broad serialization; never secret values."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


def facet_runtime_route(profile_id: str) -> dict:
    """Canonical route resolution metadata (step 4); regular-safe only if the
    resolver provably stays inside the regular-mode effect budget."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


def facet_provider_registry(profile_id: str) -> dict:
    """Negative control (step 5): plugin discovery is NOT presumed safe;
    a RED observation here is the correct outcome for regular mode."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


FACET_LOADERS.update({
    "identity": facet_identity,
    "config_health": facet_config_health,
    "effective_config": facet_effective_config,
    "runtime_route": facet_runtime_route,
    "provider_registry": facet_provider_registry,
})


def build_envelope(facets: dict, profile_id: str, hermes_revision: str,
                   effects: dict) -> dict:
    return {
        "schema": BRIDGE_SCHEMA,
        "source": {
            "hermes_revision": hermes_revision,
            "bridge_revision": BRIDGE_REVISION,
            "profile_id": profile_id,
        },
        "facets": facets,
        "effects": effects,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C0 bridge child (experiment)")
    ap.add_argument("--facets", default="",
                    help="comma-separated facet names; empty = all registered")
    args = ap.parse_args(argv)

    effects = install_effects_audit()
    hermes_home = os.environ.get("HERMES_HOME", "")
    # The child must not infer a profile when an explicit home is supplied —
    # and must not run at all without one (harness always provides it).
    if not hermes_home:
        envelope = build_envelope(
            {"bridge": {"state": "error", "authority": "argus",
                        "reason_code": "missing_explicit_hermes_home",
                        "data": {}}},
            profile_id="unspecified", hermes_revision="unknown",
            effects=effects)
        json.dump(envelope, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    requested = [f.strip() for f in args.facets.split(",") if f.strip()]
    names = requested or list(FACET_LOADERS)
    profile_id = os.path.basename(os.path.normpath(hermes_home)) or "profile"

    facets = {}
    for name in names:
        loader = FACET_LOADERS.get(name)
        if loader is None:
            facets[name] = {"state": "error", "authority": "argus",
                            "reason_code": "unknown_facet", "data": {}}
            continue
        try:
            facets[name] = loader(profile_id)
        except Exception as exc:  # fail-closed: an unknown facet error must
            # stay inside the envelope, never become a crash before JSON.
            facets[name] = {"state": "error", "authority": "argus",
                            "reason_code": "facet_crashed",
                            "data": {"exception_class": type(exc).__name__}}
    envelope = build_envelope(facets, profile_id,
                              hermes_revision=os.environ.get("C0_HERMES_REV",
                                                             "unknown"),
                              effects=effects)
    json.dump(envelope, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
