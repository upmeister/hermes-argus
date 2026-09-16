#!/usr/bin/env python3
"""hermes-discovery-shadow.py — C1a parent: containment + reconciliation.

Runs the short-lived Hermes discovery child (`hermes-discovery-bridge.py`)
in strictly shadow mode and records the results SEPARATELY from the legacy
static discovery state:

- `$HERMES_HOME/state/hermes-discovery-shadow.json` — compatibility state +
  last validated bridge envelope (atomic writes);
- `$HERMES_HOME/state/hermes-discovery-reconciliation.json` — mapped
  semantic comparison against the static snapshot (six relation classes).

ADR 0002 boundaries enforced here:
- this parent NEVER imports Hermes modules; Hermes runs only through the
  short-lived child;
- shadow output MUST NOT change health verdicts, Telegram alerts, the legacy
  `integration-snapshot.json`, or `/integrations` authority — the caller
  (integration-discover-wrapper.sh) is responsible for isolation; this
  script itself only writes the two state files above;
- effect budget: network = [], additional_process_spawn = [], and writes
  limited to `bounded_hermes_bootstrap_only` classes inside the selected
  Hermes home (SOUL.md, audio_cache/**, backups/config/**). Any newly
  observed write class marks the observation `compatibility_degraded`
  (review stop), it never widens the allowlist;
- fail closed: truncated output, duplicate JSON keys, empty facets, missing
  effects, profile mismatch, unsafe profile id, timeout/crash all produce an
  explicit degraded observation, never a silent last-good-as-current.

Stdlib only; runs under the system python3 (no Hermes imports here).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SHADOW_SCHEMA = 1
RECONCILIATION_SCHEMA = 1
FACET_STATES = ("ok", "partial", "unsupported", "compatibility_degraded",
                "error")
ACCEPTED_FACETS = ("identity", "config_health", "effective_config")
ACCEPTED_FACET_SET = frozenset(ACCEPTED_FACETS)
MAX_STRING_LEN = 512
MAX_COLLECTION_ITEMS = 50
import re
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

BASE_ENV_ALLOWLIST = (
    "PATH", "TEMP", "TMP", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC",
    "PATHEXT", "WINDIR", "LC_ALL", "LANG",
)
BRIDGE_ENV = {
    "PYTHONIOENCODING": "utf-8",
    "PYTHONDONTWRITEBYTECODE": "1",
}
RESERVED_ENV_KEYS = frozenset(BASE_ENV_ALLOWLIST) | frozenset(BRIDGE_ENV) | {
    "HERMES_HOME", "HOME", "PYTHONPATH", "C1A_HERMES_SRC", "C1A_HERMES_REV",
}

DEFAULT_TIMEOUT_S = 180
DEFAULT_OUTPUT_CAP = 256 * 1024
KILL_GRACE_S = 5

ALLOWED_WRITE_PREFIXES = ("{HERMES_HOME}/SOUL.md",
                          "{HERMES_HOME}/audio_cache/",
                          "{HERMES_HOME}/backups/config/")

RELATIONS = ("equal", "bridge_gain", "static_retained",
             "semantic_difference", "not_comparable", "degraded")


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def build_child_env(profile_home: Path, hermes_src: str,
                    extra: dict | None = None, rev: str = "") -> dict:
    """Allowlisted child environment: explicit HOME+HERMES_HOME (isolation
    from the maintainer home — without HOME, posix expanduser falls back to
    the passwd entry), reserved keys cannot be overridden, declared fixture
    variables only."""
    env = {k: v for k, v in os.environ.items() if k in BASE_ENV_ALLOWLIST}
    env.update(BRIDGE_ENV)
    env["HERMES_HOME"] = str(profile_home)
    env["HOME"] = str(profile_home)
    env["PYTHONPATH"] = hermes_src
    env["C1A_HERMES_SRC"] = hermes_src
    if rev:
        env["C1A_HERMES_REV"] = str(rev)
    env["C1A_HERMES_REV"] = rev
    for raw_key, value in (extra or {}).items():
        key = str(raw_key)
        if key in RESERVED_ENV_KEYS:
            raise ValueError(f"extra cannot override reserved environment key: {key}")
        if not key.isidentifier():
            raise ValueError(f"invalid declared environment variable: {key}")
        env[key] = str(value)
    return env


def _terminate(proc: subprocess.Popen) -> None:
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


def run_child(bridge_entrypoint: str, argv: list[str] | None = None,
              env: dict | None = None, timeout_s: int = DEFAULT_TIMEOUT_S,
              output_cap: int = DEFAULT_OUTPUT_CAP,
              python_executable: str | None = None) -> dict:
    """Run one bridge child; never raise for child failures."""
    if env is None:
        # Fail-closed: a missing explicit environment would inherit the
        # parent's full environment (notification credentials, proxies).
        return {"status": "invalid_env", "exit_code": None,
                "elapsed_s": 0.0, "argv": [], "stdout": "",
                "stdout_truncated": False,
                "stderr": "explicit child environment is required",
                "stderr_truncated": False,
                "error_kind": "env_required", "timed_out": False,
                "output_limited": False}
    child_argv = [str(a) for a in (argv or [])]
    started = time.monotonic()
    status, exit_code, error_kind = "ok", None, None
    output: dict = {}
    stream_overflow = {"stdout": False, "stderr": False}
    overflow = threading.Event()
    try:
        proc = subprocess.Popen(
            [python_executable or sys.executable, str(bridge_entrypoint),
             *child_argv],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        return {"status": "spawn_error", "exit_code": None,
                "elapsed_s": round(time.monotonic() - started, 3),
                "argv": [], "stdout": "", "stdout_truncated": False,
                "stderr": type(exc).__name__, "stderr_truncated": False,
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
    deadline = started + timeout_s
    try:
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
    result = {"status": status, "exit_code": exit_code,
              "elapsed_s": round(elapsed, 3), "timed_out": status == "timeout",
              "argv": [str(bridge_entrypoint), *child_argv],
              "stdout": output.get("stdout", b"").decode("utf-8",
                                                         errors="replace"),
              "stdout_truncated": stream_overflow["stdout"],
              "stderr": output.get("stderr", b"").decode("utf-8",
                                                         errors="replace"),
              "stderr_truncated": stream_overflow["stderr"],
              "output_limited": status == "output_limit"}
    if error_kind:
        result["error_kind"] = error_kind
    return result


def _reject_json_constant(constant):
    raise ValueError(f"invalid JSON constant {constant}")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


MAX_STRING_LEN = MAX_STRING_LEN


def _v_str(value, max_len: int = MAX_STRING_LEN) -> bool:
    return isinstance(value, str) and len(value) <= max_len


def _v_safe_name(value) -> bool:
    return isinstance(value, str) and bool(SAFE_NAME_RE.fullmatch(value))


def _v_bool(value) -> bool:
    return isinstance(value, bool)


def _v_tristate(value) -> bool:
    return value is None or _v_bool(value)


def _v_model_record(value) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    if value.get("ref") is True:
        return (_v_safe_name(value.get("var"))
                and _v_bool(value.get("expanded"))
                and _v_bool(value.get("present"))
                and set(value) <= {"ref", "var", "expanded", "present"})
    return (set(value) <= {"value", "source"}
            and (value.get("value") is None or _v_str(value.get("value"), 256))
            and value.get("source") in ("default", "user", "canonicalized"))


def _validate_facet_data(name: str, data) -> str:
    """Recursive allowlist validation of facet data (C1a contract section 7):
    only declared fields, declared types, bounded strings. NaN/Infinity are
    rejected at JSON parse time."""
    if not isinstance(data, dict):
        return f"facet {name!r}: data must be an object"
    if name == "identity":
        if set(data) != {"hermes_version"} or not _v_str(data["hermes_version"], 64):
            return "identity.data must contain only a bounded hermes_version"
        return ""
    if name == "config_health":
        expected = {"config_file_present", "raw_parse_ok", "load_ok",
                    "primary_model", "note"}
        if set(data) != expected:
            return "config_health.data has unexpected or missing fields"
        if not _v_bool(data["config_file_present"]) or not _v_bool(data["load_ok"]):
            return "config_health.data flag fields must be boolean"
        if not _v_tristate(data["raw_parse_ok"]):
            return "config_health.data.raw_parse_ok must be tri-state"
        if not _v_model_record_or_none(data["primary_model"]):
            return "config_health.data.primary_model is malformed"
        if not _v_str(data["note"], 512):
            return "config_health.data.note must be a bounded string"
        return ""
    if name == "effective_config":
        expected = {"model_primary", "fallback_providers", "providers",
                    "mcp_servers", "auxiliary"}
        if set(data) != expected:
            return "effective_config.data has unexpected or missing fields"
        if not _v_model_record(data["model_primary"]):
            return "effective_config.model_primary is malformed"
        fb = data["fallback_providers"]
        if not isinstance(fb, list) or len(fb) > MAX_COLLECTION_ITEMS:
            return "effective_config.fallback_providers must be a bounded list"
        for entry in fb:
            if not isinstance(entry, dict) or set(entry) != {"name", "base_url_identity"}:
                return "effective_config.fallback_providers entry is malformed"
            if entry["name"] is not None and not _v_safe_name(entry["name"]):
                return "effective_config.fallback_providers.name must be a safe identifier"
            if entry["base_url_identity"] is not None \
                    and not _v_str(entry["base_url_identity"], 256):
                return "effective_config.fallback_providers.base_url_identity is malformed"
        prov = data["providers"]
        if not isinstance(prov, dict) or len(prov) > MAX_COLLECTION_ITEMS:
            return "effective_config.providers must be a bounded object"
        for key, entry in prov.items():
            if not _v_safe_name(key):
                return "effective_config.providers keys must be safe identifiers"
            if not isinstance(entry, dict) \
                    or set(entry) != {"base_url_identity", "auth",
                                      "credential_present"}:
                return f"effective_config.providers[{key!r}] is malformed"
            if entry["base_url_identity"] is not None \
                    and not _v_str(entry["base_url_identity"], 256):
                return f"effective_config.providers[{key!r}].base_url_identity is malformed"
            if entry["auth"] not in ("none", "inline_key", "key_env", "key_cmd"):
                return f"effective_config.providers[{key!r}].auth is not canonical"
            if not _v_bool(entry["credential_present"]):
                return f"effective_config.providers[{key!r}].credential_present must be boolean"
        mcp = data["mcp_servers"]
        if not isinstance(mcp, dict) or len(mcp) > MAX_COLLECTION_ITEMS:
            return "effective_config.mcp_servers must be a bounded object"
        for key, entry in mcp.items():
            if not _v_safe_name(key):
                return "effective_config.mcp_servers keys must be safe identifiers"
            if not isinstance(entry, dict) \
                    or set(entry) - {"transport", "url_identity",
                                     "command_basename", "args_count"} \
                    or entry.get("transport") not in ("stdio", "http", "unknown"):
                return f"effective_config.mcp_servers[{key!r}] is malformed"
            if "url_identity" in entry and entry["url_identity"] is not None \
                    and not _v_str(entry["url_identity"], 256):
                return f"effective_config.mcp_servers[{key!r}].url_identity is malformed"
            if "command_basename" in entry \
                    and not _v_safe_name(entry.get("command_basename")):
                return f"effective_config.mcp_servers[{key!r}].command_basename must be a safe identifier"
            if "args_count" in entry and not _is_count(entry["args_count"]):
                return f"effective_config.mcp_servers[{key!r}].args_count must be an integer"
        aux = data["auxiliary"]
        if not isinstance(aux, dict) or len(aux) > MAX_COLLECTION_ITEMS:
            return "effective_config.auxiliary must be a bounded object"
        for task, entry in aux.items():
            if not _v_safe_name(task):
                return "effective_config.auxiliary task keys must be safe identifiers"
            if not isinstance(entry, dict) \
                    or set(entry) != {"model", "credential_present"}:
                return f"effective_config.auxiliary[{task!r}] is malformed"
            if not _v_model_record(entry["model"]):
                return f"effective_config.auxiliary[{task!r}].model is malformed"
            if not _v_bool(entry["credential_present"]):
                return f"effective_config.auxiliary[{task!r}].credential_present must be boolean"
        return ""
    return f"facet {name!r} has no declared data schema"


def _v_model_record_or_none(value) -> bool:
    # config_health emits the raw identity string; only effective_config
    # wraps it into a value/ref record.
    return value is None or isinstance(value, str) or _v_model_record(value)

def parse_envelope(run_result: dict, expected_profile_id: str = "",
                   expected_facets: frozenset = ACCEPTED_FACET_SET
                   ) -> tuple[dict | None, str]:
    """Fail-closed parse of the child's stdout as a bridge envelope."""
    if run_result.get("status") != "ok":
        return None, f"child did not finish cleanly ({run_result.get('status')})"
    if run_result.get("exit_code") != 0:
        return None, f"child exit code {run_result.get('exit_code')!r}"
    if (run_result.get("stdout_truncated")
            or run_result.get("stderr_truncated")
            or run_result.get("output_limited")):
        return None, "child output truncated beyond the cap - untrusted"
    text = (run_result.get("stdout") or "").strip()
    if not text:
        return None, "empty child stdout"
    try:
        envelope = json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                              parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        return None, f"stdout is not JSON ({exc.msg} at {exc.lineno}:{exc.colno})"
    except ValueError:
        return None, "stdout contains duplicate JSON object keys"
    if not isinstance(envelope, dict):
        return None, "envelope is not an object"
    schema = envelope.get("schema")
    if not _is_count(schema) or schema != SHADOW_SCHEMA:
        return None, f"unsupported envelope schema {schema!r}"
    source = envelope.get("source")
    if not isinstance(source, dict):
        return None, "missing source"
    for field in ("hermes_revision", "bridge_revision", "profile_id"):
        if not isinstance(source.get(field), str) or not source[field]:
            return None, f"source.{field} must be a non-empty string"
    if expected_profile_id and source["profile_id"] != expected_profile_id:
        return None, (f"source.profile_id {source['profile_id']!r} does not "
                      f"match the requested {expected_profile_id!r}")
    facets = envelope.get("facets")
    if not isinstance(facets, dict) or not facets:
        return None, "facets must be a non-empty object"
    if set(facets) != set(expected_facets):
        return None, (f"facet set {sorted(facets)} does not match the accepted "
                      f"facet set {sorted(expected_facets)}")
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
        data_reason = _validate_facet_data(name, facet.get("data", {}))
        if data_reason:
            return None, data_reason
    effects = envelope.get("effects")
    if not isinstance(effects, dict):
        return None, "effects must be an object (evidence envelope)"
    for key in ("network", "process_spawn", "writes"):
        if not isinstance(effects.get(key), list):
            return None, f"effects.{key} must be a list"
    if not isinstance(effects.get("truncated"), bool):
        return None, "effects.truncated must be a boolean"
    return envelope, ""


def validate_effects(envelope: dict, profile_home: Path
                     ) -> tuple[bool, list[str], list[str]]:
    """Validate the observed effect classes against the ADR 0002 budget.

    Returns (within_budget, unexpected_writes, network_or_spawn). Writes are
    allowed only inside the declared `bounded_hermes_bootstrap_only` classes
    relativized against HERMES_HOME; anything else is an unexpected write
    class (compatibility_degraded + review stop). Any network connection or
    additional process spawn is out of budget outright."""
    effects = (envelope or {}).get("effects") or {}
    network = effects.get("network") or []
    spawn = effects.get("process_spawn") or []
    writes = effects.get("writes") or []
    unexpected: list[str] = []
    home_real = os.path.realpath(profile_home)
    prefix = "{HERMES_HOME}/"
    for w in writes:
        if not w.startswith(prefix):
            unexpected.append(w)
            continue
        rel = w[len(prefix):]
        if not rel or ".." in Path(rel).parts:
            unexpected.append(w)
            continue
        allowed = (rel == "SOUL.md"
                   or rel.startswith("audio_cache/")
                   or rel.startswith("backups/config/"))
        if not allowed:
            unexpected.append(w)
            continue
        real_target = os.path.realpath(profile_home / rel)
        if os.path.commonpath([real_target, home_real]) != home_real:
            unexpected.append(w)
    if effects.get("truncated"):
        unexpected.append("audit_truncated_effects_incomplete")
    out_of_budget = bool(network or spawn or unexpected)
    return (not out_of_budget), unexpected, list(network) + list(spawn)


def _read_git_rev(checkout: Path) -> str | None:
    """Read the checked-out revision from .git without spawning processes."""
    git = checkout / ".git"
    try:
        if git.is_file():
            line = git.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir:"):
                return None
            gitdir = Path(line.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = checkout / gitdir
        else:
            gitdir = git
        head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head or None
        ref = head[5:].strip()
        ref_file = gitdir / ref
        if ref_file.exists():
            return ref_file.read_text(encoding="utf-8").strip() or None
        packed = gitdir / "packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + ref):
                    return line.split(" ", 1)[0]
        return None
    except Exception:
        return None


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                     dir=str(path.parent), delete=False)
    try:
        json.dump(payload, fd, ensure_ascii=False, indent=1)
        fd.write("\n")
        fd.close()
        os.replace(fd.name, path)
    finally:
        if os.path.exists(fd.name):
            os.unlink(fd.name)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _static_url_identity(value) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if not parts.scheme or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.hostname}{parts.path.rstrip('/')}"


def reconcile(static_entities: dict, envelope: dict,
             profile_id: str = "") -> dict:
    """Mapped semantic comparison: nine families, six relation classes.

    Every record preserves provenance. This is evidence for the C1b
    authority decision — never a whole-snapshot percentage."""
    records: list[dict] = []
    facets = (envelope or {}).get("facets") or {}
    eff = facets.get("effective_config", {}).get("data", {}) \
        if isinstance(facets.get("effective_config"), dict) else {}
    ch = facets.get("config_health", {}).get("data", {}) \
        if isinstance(facets.get("config_health"), dict) else {}

    def add(key: str, field: str, hermes, static, relation: str,
            reason: str) -> None:
        records.append({
            "profile_id": profile_id,
            "semantic_key": key, "field": field,
            "hermes_value_or_descriptor": hermes,
            "static_value_or_descriptor": static,
            "hermes_authority": "hermes-effective",
            "static_authority": "argus-static",
            "relation": relation, "reason_code": reason,
        })

    def static_entity(prefix: str, name: str):
        return static_entities.get(f"{prefix}:{name}")

    # 1. primary model/provider
    bridge_primary = eff.get("model_primary") or {}
    sm = static_entities.get("model:primary") or {}
    static_primary = "/".join(x for x in (sm.get("provider"), sm.get("model"))
                              if x) or sm.get("model") or None
    if isinstance(bridge_primary, dict) and bridge_primary.get("ref"):
        add("model.primary", "identity", bridge_primary, static_primary,
            "not_comparable", "env_ref_descriptor_value_not_crossed")
    elif bridge_primary.get("value") and static_primary:
        relation = "equal" if bridge_primary["value"] == static_primary \
            else "semantic_difference"
        add("model.primary", "identity", bridge_primary["value"],
            static_primary, relation, "compared")
    elif bridge_primary.get("value"):
        add("model.primary", "identity", bridge_primary["value"], None,
            "bridge_gain", "static_has_no_primary_model_entity")
    # 2. fallback refs
    bridge_fb = eff.get("fallback_providers") or []
    static_fb = static_entities.get("model:fallback")
    if bridge_fb and static_fb is None:
        add("model.fallback", "refs", bridge_fb, None, "bridge_gain",
            "static_has_no_fallback_model_entity")
    elif static_fb is not None:
        # Normalized comparison: static entity carries a concrete model,
        # bridge carries fallback provider names - comparable only when one
        # of the names is contained in the static model identity.
        static_model = static_fb.get("model") or ""
        bridge_names = [e.get("name") for e in bridge_fb
                        if isinstance(e, dict)]
        comparable = any(isinstance(n, str) and n and n in static_model
                         for n in bridge_names)
        relation = "equal" if comparable else "not_comparable"
        reason = "compared" if comparable \
            else "different_fallback_representations"
        add("model.fallback", "refs", bridge_fb, static_fb, relation, reason)
    # 3. auxiliary task refs
    bridge_aux = eff.get("auxiliary") or {}
    static_aux_roles = {k.split(":", 1)[1]: v for k, v in
                        static_entities.items() if k.startswith("model:")}
    def bridge_model_value(record):
        # Normalized comparison source: plain value for value-records, None
        # for ref-descriptors (materialized values never cross the boundary).
        return record.get("value") if isinstance(record, dict) else None

    for task, record in bridge_aux.items():
        static_task = static_aux_roles.get(task)
        if static_task is not None:
            bridge_value = bridge_model_value(record.get("model"))
            static_value = static_task.get("model")
            if isinstance(record.get("model"), dict) \
                    and record["model"].get("ref"):
                add(f"auxiliary.{task}", "model", record["model"],
                    static_task, "not_comparable",
                    "env_ref_descriptor_value_not_crossed")
            elif bridge_value is not None and bridge_value == static_value:
                add(f"auxiliary.{task}", "model", record["model"],
                    static_task.get("model"), "equal", "compared")
            else:
                add(f"auxiliary.{task}", "model", bridge_value,
                    static_value, "semantic_difference", "compared")
        else:
            add(f"auxiliary.{task}", "model", record.get("model"), None,
                "bridge_gain", "static_has_no_auxiliary_role_entity")
    for role in ("vision", "compression"):
        if role in static_aux_roles and role not in bridge_aux:
            add(f"auxiliary.{role}", "model", None,
                static_aux_roles[role], "semantic_difference",
                "static_aux_role_not_in_bridge_allowlist")
    # 4. declared MCP servers
    bridge_mcp = eff.get("mcp_servers") or {}
    static_mcp = {k.split(":", 1)[1]: v for k, v in static_entities.items()
                  if k.startswith("mcp:")}
    for name in sorted(set(bridge_mcp) | set(static_mcp)):
        b = bridge_mcp.get(name)
        s = static_mcp.get(name)
        if b and s:
            relation = "equal" if b.get("transport") == s.get("transport") \
                else "semantic_difference"
            add(f"mcp.{name}", "transport", b.get("transport"),
                s.get("transport"), relation, "compared")
        elif b:
            add(f"mcp.{name}", "transport", b.get("transport"), None,
                "bridge_gain", "static_has_no_mcp_declaration")
        else:
            add(f"mcp.{name}", "transport", None, s,
                "semantic_difference", "static_mcp_not_in_bridge_allowlist")
    # 5. named/custom providers
    bridge_prov = eff.get("providers") or {}
    static_prov = {k.split(":", 1)[1]: v for k, v in static_entities.items()
                   if k.startswith("provider:")}
    for name in sorted(set(bridge_prov) | set(static_prov)):
        b = bridge_prov.get(name)
        s = static_prov.get(name)
        if b and s:
            same_endpoint = (b.get("base_url_identity")
                             == _static_url_identity(s.get("base_url")))
            add(f"provider.{name}", "identity",
                {"base_url_identity": b.get("base_url_identity"),
                 "auth": b.get("auth")},
                {"base_url": s.get("base_url"), "key_present": s.get("key_present")},
                "equal" if same_endpoint else "semantic_difference",
                "compared_endpoint_presence_semantics_differ")
        elif b:
            add(f"provider.{name}", "identity", b, None, "bridge_gain",
                "static_has_no_provider_declaration")
        else:
            add(f"provider.{name}", "identity", None, s,
                "semantic_difference", "static_provider_not_in_bridge_allowlist")
    # 6. env references (declared/presence semantics; values forbidden)
    bridge_envref = bridge_primary if isinstance(bridge_primary, dict) \
        and bridge_primary.get("ref") else None
    static_envref = {k.split(":", 1)[1]: v for k, v in static_entities.items()
                     if k.startswith("envref:")}
    for var, s in sorted(static_envref.items()):
        if bridge_envref and bridge_envref.get("var") == var:
            add(f"envref.{var}", "expansion",
                {"expanded": bridge_envref.get("expanded"),
                 "present": bridge_envref.get("present")},
                {"key_present": s.get("key_present")},
                "equal", "canonical_expansion_fact_vs_static_presence")
        else:
            add(f"envref.{var}", "presence",
                None, {"key_present": s.get("key_present")},
                "static_retained", "envref_not_on_bridge_allowlist_path")
    # 7. OAuth metadata — static_retained (bridge intentionally excludes it)
    for key, entity in sorted(static_entities.items()):
        if key.startswith("oauth:"):
            add(key, "metadata", None, entity, "static_retained",
                "oauth_runtime_resolution_out_of_c1a_scope")
    # 8. plugin manifests — static_retained (executable discovery prohibited)
    for key, entity in sorted(static_entities.items()):
        if key.startswith("plugin-provider:"):
            add(key, "manifest", None, entity, "static_retained",
                "executable_provider_discovery_prohibited_adr0002")
    # 9. registry-only tool/env integrations — static_retained
    for key, entity in sorted(static_entities.items()):
        if key.startswith(("envkey:", "local:", "kit:")):
            add(key, "declaration", None, entity, "static_retained",
                "argus_owned_registry_coverage")
    # degraded marker for degraded facets
    if ch.get("state") == "partial":
        add("config.parse", "health", ch.get("reason_code"),
            None, "degraded", "raw_config_parse_fallback_observed")
    counts: dict[str, int] = {}
    for r in records:
        counts[r["relation"]] = counts.get(r["relation"], 0) + 1
    return {"schema": RECONCILIATION_SCHEMA, "records": records,
            "counts": counts}


def main(argv: list[str] | None = None) -> int:
    default_bridge = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "hermes-discovery-bridge.py")
    ap = argparse.ArgumentParser(
        description="C1a shadow bridge parent (containment + reconciliation)")
    ap.add_argument("--hermes-python", required=True,
                    help="absolute path to the Hermes venv python")
    ap.add_argument("--bridge", default=default_bridge,
                    help="absolute path to hermes-discovery-bridge.py")
    ap.add_argument("--profile-home", required=True,
                    help="explicit Hermes home of the monitored profile")
    ap.add_argument("--profile-id", default="production")
    ap.add_argument("--hermes-rev", default="",
                    help="installed Hermes revision (recorded in the envelope)")
    ap.add_argument("--hermes-src", default="",
                    help="Hermes source checkout (default: derived from the "
                         "venv python path as <checkout>/venv/bin/python)")
    ap.add_argument("--static-snapshot",
                    default=os.path.join(os.path.expanduser("~"), ".hermes",
                                         "state",
                                         "integration-snapshot.json"))
    ap.add_argument("--state-dir",
                    default=os.path.join(os.path.expanduser("~"), ".hermes",
                                         "state"))
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--output-cap", type=int, default=DEFAULT_OUTPUT_CAP)
    args = ap.parse_args(argv)

    hermes_python = os.path.abspath(args.hermes_python)
    if not os.path.isfile(hermes_python):
        print(f"hermes-discovery-shadow: Hermes python not found: "
              f"{hermes_python}", file=sys.stderr)
        return 2
    bridge = os.path.abspath(args.bridge)
    if not os.path.isfile(bridge):
        print(f"hermes-discovery-shadow: bridge not found: {bridge}",
              file=sys.stderr)
        return 2
    hermes_src = args.hermes_src or str(
        Path(hermes_python).parent.parent.parent)
    pyproject = Path(hermes_src) / "pyproject.toml"
    if not pyproject.is_file():
        print("hermes-discovery-shadow: cannot locate Hermes source checkout "
              f"from {hermes_python} (pass --hermes-src)", file=sys.stderr)
        return 2
    # Interpreter/source binding (review finding): the configured python must
    # be the venv python of the selected Hermes checkout. realpath of the
    # interpreter itself would resolve the venv symlink to the system python,
    # so the binding is checked through the venv directory: <checkout>/venv
    # with its own pyvenv.cfg, inside the selected checkout.
    real_src = os.path.realpath(hermes_src)
    venv_root = os.path.realpath(str(Path(hermes_python).parent.parent))
    if os.path.commonpath([venv_root, real_src]) != real_src             or not os.path.isfile(
                os.path.join(venv_root, "pyvenv.cfg")):
        print("hermes-discovery-shadow: configured interpreter is not the "
              "venv python of the selected Hermes checkout", file=sys.stderr)
        return 2
    try:
        import tomllib
        manifest_name = tomllib.loads(pyproject.read_text(
            encoding="utf-8")).get("project", {}).get("name")
    except Exception:
        manifest_name = None
    if manifest_name != "hermes-agent":
        print("hermes-discovery-shadow: selected checkout pyproject name is "
              f"{manifest_name!r}, expected 'hermes-agent'", file=sys.stderr)
        return 2
    profile_home = Path(args.profile_home).resolve()
    # The revision must describe the selected checkout, not a caller-provided
    # string: read it from the checkout's .git and refuse a mismatch (review
    # finding: the wrapper never passed --hermes-rev, so envelopes carried
    # "unrecorded"; a caller string was trusted instead of the source).
    rev_computed = _read_git_rev(Path(hermes_src)) or "unrecorded"
    if args.hermes_rev and rev_computed != "unrecorded" \
            and args.hermes_rev != rev_computed:
        print(f"hermes-discovery-shadow: hermes revision mismatch: declared "
              f"{args.hermes_rev!r}, selected checkout is {rev_computed!r}",
              file=sys.stderr)
        return 2
    rev = rev_computed

    env = build_child_env(profile_home, hermes_src,
                          extra={"C1A_PROFILE_ID": args.profile_id}, rev=rev)
    result = run_child(bridge, ["--facets", "identity,config_health,"
                                "effective_config",
                                "--profile-id", args.profile_id],
                       env=env, timeout_s=args.timeout,
                       output_cap=args.output_cap,
                       python_executable=hermes_python)
    envelope, reason = parse_envelope(result,
                                      expected_profile_id=args.profile_id)

    state_dir = Path(args.state_dir)
    shadow_path = state_dir / "hermes-discovery-shadow.json"
    recon_path = state_dir / "hermes-discovery-reconciliation.json"

    if envelope is None:
        # C9: keep the last-good shadow only if explicitly marked stale; the
        # current degradation observation is stored separately.
        previous = _load_json(shadow_path)
        observation = {
            "schema": SHADOW_SCHEMA,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "profile_id": args.profile_id,
            "compatibility": "degraded",
            "reason": reason,
            "run_result": {k: result.get(k) for k in
                           ("status", "exit_code", "elapsed_s", "timed_out",
                            "output_limited")},
            "previous_stale": previous if isinstance(previous, dict) else None,
        }
        _atomic_write(shadow_path, observation)
        print(f"hermes-discovery-shadow: degraded ({reason})", file=sys.stderr)
        return 0

    within_budget, unexpected_writes, out_of_budget_effects = \
        validate_effects(envelope, profile_home)
    facets = envelope["facets"]
    compatibility = "ok" if within_budget else "degraded"
    if any(f.get("state") in ("error", "compatibility_degraded")
           for f in facets.values()):
        compatibility = "degraded"
    shadow = {
        "schema": SHADOW_SCHEMA,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "profile_id": args.profile_id,
        "compatibility": compatibility,
        "unexpected_writes": unexpected_writes,
        "out_of_budget_effects": out_of_budget_effects,
        "bridge": envelope,
    }
    _atomic_write(shadow_path, shadow)

    static_entities = {}
    snapshot = _load_json(Path(args.static_snapshot))
    if isinstance(snapshot, dict):
        static_entities = snapshot.get("entities") or {}
    recon = reconcile(static_entities, envelope, args.profile_id)
    recon["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    recon["profile_id"] = args.profile_id
    recon["compatibility"] = compatibility
    _atomic_write(recon_path, recon)

    print(f"hermes-discovery-shadow: compatibility={compatibility} "
          f"relations={recon['counts']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
