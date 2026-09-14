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
    """Allowlisted effective-config fields for the coverage comparison.

    api: hermes_cli.config.load_config_readonly + read_user_config_raw.
    The safety boundary is allowlist extraction (contract section 5): no broad
    serialization, and a value that was a ${VAR} template in the raw file is
    emitted as a ref descriptor (var name + expansion fact) — the materialized
    value never leaves the child even when expansion succeeded.
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
    try:
        raw = hc.read_user_config_raw()
    except Exception:
        raw = None  # broken raw file: everything loaded came from fallback
    if not isinstance(raw, dict):
        raw = {}

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

# Upstream placeholder: the resolver reports "no key found" as the literal
# "no-key-required" (hermes_cli/model_switch.py, config_migrations.py at the
# tested revision). Known placeholders are classified as such, not counted
# as materialized credentials. The credential value is inspected in the
# child for this classification only and is never serialized.
NO_KEY_PLACEHOLDERS = {"no-key-required", "no-key"}


def _credential_tri_state(api_key) -> str:
    if not (isinstance(api_key, str) and api_key.strip()):
        return "no"
    if api_key in NO_KEY_PLACEHOLDERS:
        return "placeholder"
    return "yes"


def _template_var(value) -> str | None:
    """Variable name when the value is a ${VAR} template, else None."""
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
    """Fallback provider identities: names only for strings; sanitized
    endpoint identity for mapping entries."""
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
    """Named providers: sanitized endpoint identity + credential metadata
    (source class and presence only — never key values)."""
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
    values are never emitted (they routinely carry tokens)."""
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
            model_record = {"ref": True, "var": var,
                            "expanded": expanded,
                            "present": expanded and bool(model_loaded)}
        else:
            model_record = {"value": model_loaded if isinstance(model_loaded, str) else None,
                            "source": "user" if model_raw == model_loaded and model_raw else
                                      ("default" if model_raw is None else "canonicalized")}
        out[task] = {"model": model_record,
                     "credential_present": bool(task_loaded.get("api_key"))}
    return out


def facet_runtime_route(profile_id: str) -> dict:
    """Experimental canonical route resolution (contract section 5, facet D).

    api: hermes_cli.runtime_provider.resolve_runtime_provider. Called only
    with an explicit requested provider name from the effective config — a
    blind "auto" resolution could walk the OAuth/credential ladder and is out
    of the regular experiment budget. Emits only the allowlisted non-secret
    fields; the resolver's returned credential value is inspected in the
    child solely to record the materialization fact and is then discarded —
    it never crosses the boundary. Resolver effects are captured by the child
    audit hook and recorded in the envelope.
    """
    api = "hermes_cli.runtime_provider.resolve_runtime_provider"
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider
    except Exception as exc:
        return {"state": "compatibility_degraded", "authority": "hermes",
                "api": api, "reason_code": "hermes_import_failed",
                "data": {"exception_class": type(exc).__name__}}
    try:
        from hermes_cli import config as hc
        loaded = hc.load_config_readonly()
    except Exception as exc:
        return {"state": "error", "authority": "hermes", "api": api,
                "reason_code": "effective_config_unavailable",
                "data": {"exception_class": type(exc).__name__}}
    if not isinstance(loaded, dict):
        return {"state": "error", "authority": "hermes", "api": api,
                "reason_code": "load_failed", "data": {}}
    try:
        raw = hc.read_user_config_raw()
    except Exception:
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    model_cfg = loaded.get("model") if isinstance(loaded.get("model"), dict) else {}
    raw_model_cfg = (raw.get("model") if isinstance(raw, dict)
                     and isinstance(raw.get("model"), dict) else {})
    target_model = str(model_cfg.get("default") or model_cfg.get("model") or "") or None
    raw_target_model = raw_model_cfg.get("default", raw_model_cfg.get("model"))
    providers = loaded.get("providers") if isinstance(loaded.get("providers"), dict) else {}
    if not providers:
        return {"state": "unsupported", "authority": "hermes", "api": api,
                "reason_code": "no_named_providers", "data": {}}

    def _s(value) -> str | None:
        return value if isinstance(value, str) else None

    routes: dict = {}
    ok_count = 0
    error_count = 0
    for name in list(providers)[:MAX_COLLECTION_ITEMS]:
        try:
            runtime = resolve_runtime_provider(requested=str(name),
                                               target_model=target_model)
        except Exception as exc:
            routes[str(name)] = {"state": "error",
                                 "exception_class": type(exc).__name__}
            error_count += 1
            continue
        if not isinstance(runtime, dict):
            routes[str(name)] = {"state": "error",
                                 "exception_class": "NonDictRuntime"}
            error_count += 1
            continue
        # The resolver result may carry a credential value or an upstream
        # no-key placeholder. Classification happens in the child; the value
        # itself is discarded and never serialized.
        credential_present = _credential_tri_state(runtime.get("api_key"))
        routes[str(name)] = {
            "state": "ok",
            "provider": _s(runtime.get("provider")),
            "requested_provider": _s(runtime.get("requested_provider")),
            "model": _safe_model_identity(raw_target_model, target_model),
            "api_mode": _s(runtime.get("api_mode")),
            "base_url_identity": _sanitize_url(runtime.get("base_url")),
            "credential_present": credential_present,
            "credential_source": _s(runtime.get("source")),
        }
        ok_count += 1
    if ok_count and error_count:
        state = "partial"
    elif error_count:
        state = "error"
    else:
        state = "ok"
    return {"state": state, "authority": "hermes", "api": api,
            "reason_code": "resolver_called",
            "data": {"routes": routes}}


def facet_provider_registry(profile_id: str) -> dict:
    """Negative control (contract section 5, facet E): provider discovery is
    NOT presumed safe for regular mode. First registry access imports
    bundled/user/pip provider plugin code — `providers._discover_providers`
    documents the import steps. The call itself is the experiment: effects
    are captured by the child audit hook, fixture sentinels prove code
    execution. A RED here is the correct outcome for the regular-mode
    decision and narrows the facet, not the rules.
    """
    api = "providers.list_providers"
    try:
        from providers import list_providers
    except Exception as exc:
        return {"state": "compatibility_degraded", "authority": "hermes",
                "api": api, "reason_code": "hermes_import_failed",
                "data": {"exception_class": type(exc).__name__}}
    try:
        profiles = list_providers()
    except Exception as exc:
        return {"state": "error", "authority": "hermes", "api": api,
                "reason_code": "discovery_raised",
                "data": {"exception_class": type(exc).__name__}}
    names = sorted({p.name for p in profiles
                    if isinstance(getattr(p, "name", None), str)})
    return {"state": "ok", "authority": "hermes", "api": api,
            "reason_code": "discovery_executed",
            "data": {"provider_count": len(profiles),
                     "names_sample": names[:20],
                     "truncated": len(names) > 20,
                     "sentinel_registered": "c0-sentinel" in names}}


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
