#!/usr/bin/env python3
"""hermes-discovery-bridge.py — C1a Hermes discovery/sync child (shadow mode).

Short-lived child process: one explicit profile per invocation, started by
`hermes-discovery-shadow.py` with an allowlisted environment and an explicit
`HERMES_HOME`/`HOME`. Prints exactly one allowlisted JSON envelope to stdout.

Architecture boundary (ADR 0002): the child exposes ONLY the three accepted
facets — `identity`, `config_health`, `effective_config`. There is no
callable path to `runtime_route`, `provider_registry`, credential resolvers
or plugin discovery: those facets are excluded from automatic discovery/sync
and their code is intentionally absent from this file.

Effects are captured by an audit hook installed BEFORE any Hermes import and
reported in the envelope (`effects`); the parent validates them against the
ADR 0002 effect budget.

Security boundary is allowlist extraction (never serialize-then-redact):
`${VAR}` model values are emitted as ref descriptors, credentials are never
serialized, MCP commands are reduced to basename + arg count, URLs are
sanitized to scheme://host[:port]/path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BRIDGE_SCHEMA = 1
BRIDGE_REVISION = "c1a-shadow-1"

EFFECTS_AUDIT_LIMIT = 50

# Facet loaders: ONLY the three ADR 0002 accepted facets. The registry
# deliberately has no entries (and no code paths) for runtime_route,
# provider_registry or credential resolution.
FACET_LOADERS: dict[str, object] = {}


def install_effects_audit() -> dict:
    """Capture process-boundary effects (network/spawn/writes) of this child,
    including everything the Hermes seams do. Paths are relativized against
    HERMES_HOME. The hook never raises."""
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


def _hermes_version_from_source() -> str | None:
    """Hermes version from the selected source tree's own pyproject manifest."""
    src = os.environ.get("C1A_HERMES_SRC", "")
    if not src:
        return None
    try:
        import tomllib
        with open(Path(src) / "pyproject.toml", "rb") as f:
            return tomllib.load(f).get("project", {}).get("version")
    except Exception:
        return None


def facet_identity(profile_id: str) -> dict:
    """Bounded Hermes identity metadata (ADR 0002: no paths, no hostnames)."""
    version = _hermes_version_from_source()
    if version is None:
        return {"state": "unsupported", "authority": "argus",
                "reason_code": "hermes_source_not_declared", "data": {}}
    return {"state": "ok", "authority": "hermes",
            "api": "pyproject.toml::project.version", "reason_code": "ok",
            "data": {"hermes_version": version}}


def facet_config_health(profile_id: str) -> dict:
    """Distinguish 'loader returned data' from 'parse failure / fallback'.

    api: hermes_cli.config.load_config_readonly + read_user_config_raw.
    A successfully returned config object is NOT proof that the current user
    config parsed successfully: read_user_config_raw raises on broken YAML
    while the loader silently serves last-known-good/defaults.
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
    # Allowlist extraction only; never mutate `loaded` (loader cache object).
    model = loaded.get("model") if isinstance(loaded, dict) else None
    loaded_primary = None
    if isinstance(model, dict):
        value = model.get("default", model.get("model"))
        loaded_primary = value if isinstance(value, str) else None
    raw_cfg: dict = {}
    if present and raw_parse_ok:
        try:
            raw_cfg = hc.read_user_config_raw()
        except Exception:
            raw_cfg = {}
        raw_cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
    raw_model = raw_cfg.get("model") if isinstance(raw_cfg.get("model"), dict) else {}
    raw_primary = raw_model.get("default", raw_model.get("model"))
    if not present:
        state, reason = "ok", "config_absent_defaults"
        primary = None
    elif raw_parse_ok:
        state, reason = "ok", "config_parsed"
        primary = _safe_model_identity(raw_primary, loaded_primary)
    elif raw_parse_ok is False:
        state, reason = "partial", "config_parse_fallback"
        primary = None
    else:
        state, reason = "error", "raw_parse_unknown"
        primary = None
    if not load_ok:
        state, reason = "error", "load_failed"
    return {"state": state, "authority": "hermes", "api": api,
            "reason_code": reason,
            "data": {"config_file_present": present, "raw_parse_ok": raw_parse_ok,
                     "load_ok": load_ok, "primary_model": primary, "note": note}}


def facet_effective_config(profile_id: str) -> dict:
    """Allowlisted effective-config fields (ADR 0002 accepted boundary).

    A ${VAR} template in the raw file is emitted as a ref descriptor (var
    name + expanded/present booleans) — the materialized value never leaves
    the child even when expansion succeeded.
    """
    api = "hermes_cli.config.load_config_readonly + read_user_config_raw"
    try:
        from hermes_cli import config as hc
    except Exception as exc:
        return {"state": "compatibility_degraded", "authority": "hermes",
                "api": api, "reason_code": "hermes_import_failed",
                "data": {"exception_class": type(exc).__name__}}
    try:
        loaded = hc.load_config_readonly()
    except Exception as exc:
        return {"state": "error", "authority": "hermes", "api": api,
                "reason_code": "load_config_raised",
                "data": {"exception_class": type(exc).__name__}}
    if not isinstance(loaded, dict):
        return {"state": "error", "authority": "hermes", "api": api,
                "reason_code": "load_failed", "data": {}}
    raw_parse_ok = True
    raw_error = None
    try:
        raw = hc.read_user_config_raw()
    except Exception as exc:
        # Broken raw file means the loader is serving fallback/defaults:
        # never present that as a canonical ok.
        raw = {}
        raw_parse_ok = False
        raw_error = type(exc).__name__
    if not isinstance(raw, dict):
        raw = {}
        raw_parse_ok = False
        raw_error = raw_error or "non_dict_root"

    if not raw_parse_ok:
        return {"state": "partial", "authority": "hermes", "api": api,
                "reason_code": "config_parse_fallback",
                "data": {"raw_parse_ok": False, "load_ok": True,
                         "exception_class": raw_error}}

    data = {
        "model_primary": _emit_field(raw, loaded, ("model", "default"),
                                     ("model", "model")),
        "fallback_providers": _emit_fallback(loaded.get("fallback_providers")),
        "providers": _emit_providers(loaded.get("providers")),
        "mcp_servers": _emit_mcp_servers(loaded.get("mcp_servers")),
        "auxiliary": _emit_auxiliary(raw, loaded),
    }
    return {"state": "ok", "authority": "hermes", "api": api,
            "reason_code": "allowlist_extracted", "data": data}


MAX_COLLECTION_ITEMS = 50

# Upstream placeholder: the resolver/loader reports "no key found" as the
# literal "no-key-required" (normalized by upstream model_switch.py and
# config_migrations.py). Known placeholders are classified, never counted
# as materialized credentials.
NO_KEY_PLACEHOLDERS = {"no-key-required", "no-key"}


def _template_var(value) -> str | None:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return value[2:-1]
    return None


def _safe_model_identity(raw_value, loaded_value):
    """Keep materialized ${VAR} model values inside the child."""
    var = _template_var(raw_value)
    if var is not None:
        expanded = loaded_value != raw_value
        return {"ref": True, "var": var, "expanded": expanded,
                "present": expanded and bool(loaded_value)}
    return loaded_value if isinstance(loaded_value, str) else None


def _emit_field(raw: dict, loaded: dict, *paths) -> dict:
    """Emit one allowlisted field, comparing the raw template with the loaded
    value so materialized env expansion never crosses the boundary."""
    raw_val, loaded_val = None, None
    for path in paths:
        node = loaded
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if node is not None:
            loaded_val = node
            break
    for path in paths:
        node = raw
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if node is not None:
            raw_val = node
            break
    var = _template_var(raw_val)
    if var is not None:
        expanded = loaded_val != raw_val
        return {"ref": True, "var": var, "expanded": expanded,
                "present": expanded and bool(loaded_val)}
    if raw_val is None:
        return {"value": loaded_val if isinstance(loaded_val, str) else None,
                "source": "default"}
    if raw_val == loaded_val:
        return {"value": loaded_val if isinstance(loaded_val, str) else None,
                "source": "user"}
    return {"value": loaded_val if isinstance(loaded_val, str) else None,
            "source": "canonicalized"}


def _sanitize_url(value) -> str | None:
    """scheme://host[:port]/path identity — no userinfo, query or fragment."""
    if not isinstance(value, str) or not value:
        return None
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<unparseable>"
    if not parts.scheme or not parts.hostname:
        return "<unparseable>"
    netloc = parts.hostname
    if ":" in netloc and not netloc.startswith("["):
        netloc = f"[{netloc}]"
    if parts.port:
        netloc += f":{parts.port}"
    return f"{parts.scheme}://{netloc}{parts.path.rstrip('/')}"


def _emit_fallback(fallback) -> list:
    """Fallback provider identities: names for strings; sanitized endpoint
    identity for mapping entries."""
    out = []
    if isinstance(fallback, list):
        for entry in fallback[:MAX_COLLECTION_ITEMS]:
            if isinstance(entry, str):
                out.append({"name": entry})
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("provider")
                out.append({"name": name if isinstance(name, str) else None,
                            "base_url_identity": _sanitize_url(entry.get("base_url"))})
    return out


def _emit_providers(providers) -> dict:
    """Named providers: sanitized endpoint identity + declarative auth/source
    class and inline-key presence only — never key values, never resolved
    credential truth."""
    out = {}
    if isinstance(providers, dict):
        for name, entry in list(providers.items())[:MAX_COLLECTION_ITEMS]:
            if not isinstance(entry, dict):
                out[str(name)] = {"entry_class": "non_mapping"}
                continue
            auth, present = "none", False
            if entry.get("api_key"):
                auth, present = "inline_key", True
            elif entry.get("key_env"):
                auth = "key_env"
            elif entry.get("key_cmd"):
                auth = "key_cmd"
            out[str(name)] = {"base_url_identity": _sanitize_url(entry.get("base_url")),
                              "auth": auth, "credential_present": present}
    return out


def _emit_mcp_servers(servers) -> dict:
    """Declared MCP servers: name + transport class + bounded command
    metadata. Command lines are reduced to the basename; env blocks and args
    values are never emitted (they routinely carry tokens). Extraction
    neither connects to nor executes the server."""
    out = {}
    if isinstance(servers, dict):
        for name, entry in list(servers.items())[:MAX_COLLECTION_ITEMS]:
            if not isinstance(entry, dict):
                out[str(name)] = {"transport": "unknown"}
                continue
            record: dict = {}
            if entry.get("url"):
                record["transport"] = "http"
                record["url_identity"] = _sanitize_url(entry.get("url"))
            elif entry.get("command"):
                command = str(entry.get("command"))
                record["transport"] = "stdio"
                record["command_basename"] = command.rsplit("/", 1)[-1]
                record["args_count"] = len(entry["args"]) \
                    if isinstance(entry.get("args"), list) else 0
            else:
                record["transport"] = "unknown"
            out[str(name)] = record
    return out


AUXILIARY_TASKS = ("title_generation", "compression", "vision", "embedding")


def _emit_auxiliary(raw: dict, loaded: dict) -> dict:
    """Allowlisted auxiliary-task model fields (with ${VAR} ref handling);
    api_key presence only, never values."""
    out = {}
    aux_loaded = loaded.get("auxiliary") if isinstance(loaded.get("auxiliary"), dict) else {}
    aux_raw = raw.get("auxiliary") if isinstance(raw.get("auxiliary"), dict) else {}
    for task in AUXILIARY_TASKS:
        task_loaded = aux_loaded.get(task) if isinstance(aux_loaded.get(task), dict) else {}
        task_raw = aux_raw.get(task) if isinstance(aux_raw.get(task), dict) else {}
        if not task_loaded and not task_raw:
            continue
        model_loaded = task_loaded.get("model")
        model_raw = task_raw.get("model")
        var = _template_var(model_raw)
        if var is not None:
            expanded = model_loaded != model_raw
            model_record = {"ref": True, "var": var, "expanded": expanded,
                            "present": expanded and bool(model_loaded)}
        else:
            model_record = {"value": model_loaded if isinstance(model_loaded, str) else None,
                            "source": "user" if model_raw == model_loaded and model_raw else
                                      ("default" if model_raw is None else "canonicalized")}
        out[task] = {"model": model_record,
                     "credential_present": bool(task_loaded.get("api_key"))}
    return out


FACET_LOADERS.update({
    "identity": facet_identity,
    "config_health": facet_config_health,
    "effective_config": facet_effective_config,
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


def _safe_profile_id(value) -> str | None:
    """Accept only a short, non-sensitive caller label."""
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return None
    return value if all(c.isalnum() or c in ".-_" for c in value) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C1a Hermes discovery bridge child")
    ap.add_argument("--facets", default="",
                    help="comma-separated facet names; empty = all registered")
    ap.add_argument("--profile-id", default="unspecified",
                    help="caller-supplied safe profile label; never derived "
                         "from the HERMES_HOME path")
    args = ap.parse_args(argv)

    effects = install_effects_audit()
    hermes_home = os.environ.get("HERMES_HOME", "")
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

    profile_id = _safe_profile_id(args.profile_id)
    if profile_id is None:
        envelope = build_envelope(
            {"bridge": {"state": "error", "authority": "argus",
                        "reason_code": "invalid_profile_id", "data": {}}},
            profile_id="unspecified", hermes_revision="unknown",
            effects=effects)
        json.dump(envelope, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    requested = [f.strip() for f in args.facets.split(",") if f.strip()]
    names = requested or list(FACET_LOADERS)

    facets = {}
    for name in names:
        loader = FACET_LOADERS.get(name)
        if loader is None:
            facets[name] = {"state": "error", "authority": "argus",
                            "reason_code": "unknown_facet", "data": {}}
            continue
        try:
            facets[name] = loader(profile_id)
        except Exception as exc:  # fail-closed: facet errors stay inside the
            # envelope, never become a crash before JSON.
            facets[name] = {"state": "error", "authority": "argus",
                            "reason_code": "facet_crashed",
                            "data": {"exception_class": type(exc).__name__}}
    envelope = build_envelope(facets, profile_id,
                              hermes_revision=os.environ.get("C1A_HERMES_REV",
                                                             "unknown"),
                              effects=effects)
    json.dump(envelope, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
