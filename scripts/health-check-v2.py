#!/usr/bin/env python3
"""health-check-v2.py — registry-driven integration health engine (plan §10 v2).

Replaces the hardcoded full-mode checks of health-check-integrations.sh with
data-driven primitives. Reads the discover snapshot (~/.hermes/state/
integration-snapshot.json) to know what is LIVE, and registry.yaml to know how
to check it. The legacy --quick mode stays the watchdog L1 contract until this
engine proves out (PR-3 note).

Primitives (mapped from snapshot entity types):
  env        — key present and non-empty in ~/.hermes/.env
  tcp        — TCP connect to host:port (kit proxy entries)
  http       — GET url, 2xx/3xx expected (local self-hosted services)
  mcp-test   — `hermes mcp test <name>`, parse stdout (exit code is always 0)

Output: JSON report to --out (machine-readable, consumed by
health-check-v2-wrapper.sh and /integrations) + short human summary on stdout.
Exit codes: 0 = all ok, 1 = at least one failure. Values from .env are never
printed — only key names.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

HERMES_DIR = Path(os.environ.get("HERMES_DIR", Path.home() / ".hermes"))
DEFAULT_REGISTRY = HERMES_DIR / "state" / "registry.yaml"
DEFAULT_SNAPSHOT = HERMES_DIR / "state" / "integration-snapshot.json"
DEFAULT_ENV = HERMES_DIR / ".env"
DEFAULT_OUT = HERMES_DIR / "state" / "health-check-v2-report.json"
DEFAULT_HERMES_BIN = HERMES_DIR / "hermes-agent" / "venv" / "bin" / "hermes"

HTTP_RETRIES = 3
HTTP_RETRY_DELAY = 10  # seconds; conventions: 3 attempts / 10s pause
HTTP_TIMEOUT = 15
TCP_TIMEOUT = 5

CONNECTED_RE = re.compile(r"✓ Connected \((\d+)ms\)")
FAILED_RE = re.compile(r"✗ Connection failed")
TOOLS_RE = re.compile(r"✓ Tools discovered: (\d+)")


def proxy_url(env: dict) -> str:
    """Telegram egress proxy from .env; tolerate inline comments/quotes."""
    raw = (env.get("TELEGRAM_PROXY") or "").strip().strip('"\'')
    m = re.search(r"https?://\S+", raw)
    return m.group(0).rstrip('"\'') if m else "http://127.0.0.1:8444"


def check_tg_getme(token: str, proxy: str) -> tuple[bool, str]:
    """getMe for a Telegram bot token (C3). Distinguishes an invalid/revoked
    token (401/404 — fail fast, no retries) from network unavailability
    (000/timeout — retried 3x10s per repo conventions). Never prints the token."""
    try:
        r = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", "--connect-timeout", "8",
             "--max-time", "25", "--proxy", proxy,
             f"https://api.telegram.org/bot{token}/getMe"],
            capture_output=True, text=True, timeout=35)
        body, _, code = r.stdout.rpartition("\n")
        code = code.strip() or "000"
    except subprocess.TimeoutExpired:
        return False, "unreachable (timeout via proxy)"
    if code == "401" or code == "404":
        return False, f"token invalid/revoked (HTTP {code})"
    try:
        d = json.loads(body)
    except json.JSONDecodeError:
        d = {}
    if d.get("ok"):
        name = (d.get("result", {}).get("username") or "").strip()
        return True, f"bot @{name} ok" if name else "getMe ok"
    if code.startswith("2"):
        return False, f"unexpected API response (HTTP {code})"
    return False, f"unreachable via proxy (HTTP {code})"


def load_env(path: Path) -> dict:
    """Key -> value; outer dotenv quotes are removed, values stay in memory."""
    out = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^([A-Z_0-9]+)=", line)
            if m:
                value = line.split("=", 1)[1].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                out[m.group(1)] = value
    except FileNotFoundError:
        pass
    return out


def load_registry(path: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {}
    except ImportError:
        sys.exit("FATAL: PyYAML not available (same dependency as integration-discover.py)")


def curl_code(url: str, timeout: int, token: str = "") -> str:
    try:
        cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
               "--max-time", str(timeout)]
        header_input = None
        if token:
            # Read Authorization from stdin so it never appears in argv/ps.
            cmd += ["-H", "@-"]
            header_input = f"Authorization: Bearer {token}\n"
        cmd.append(url)
        r = subprocess.run(cmd, input=header_input, capture_output=True,
                           text=True, timeout=timeout + 5)
        return r.stdout.strip() or "000"
    except subprocess.TimeoutExpired:
        return "000"


def curl_json(url: str, timeout: int, token: str = "") -> tuple[str, object | None]:
    """GET JSON without exposing the response body to logs or reports.

    The body remains in this process only long enough for schema validation;
    callers receive a status code and parsed object, never a curl command or
    raw response text.  This matters for queue/status because future Honcho
    versions may include identifiers in the response.
    """
    try:
        cmd = ["curl", "-sS", "-w", chr(10) + "%{http_code}",
               "--max-time", str(timeout)]
        header_input = None
        if token:
            # Keep credentials in the pipe, not in the child process argv.
            cmd += ["-H", "@-"]
            header_input = f"Authorization: Bearer {token}\n"
        cmd.append(url)
        r = subprocess.run(cmd, input=header_input, capture_output=True,
                           text=True, timeout=timeout + 5)
        body, _, code = r.stdout.rpartition(chr(10))
        code = code.strip() or "000"
    except (subprocess.TimeoutExpired, OSError):
        return "000", None
    if not code.isdigit():
        return "000", None
    try:
        return code, json.loads(body)
    except json.JSONDecodeError:
        return code, None


def check_http(url: str, retries: int, token: str = "", mode: str = "200") -> tuple[bool, str]:
    """GET url; generic checks require a normal 2xx/3xx response.

    Authentication failures are never retried.  Semantic JSON checks use
    :func:`check_http_json` below instead of treating an API root's 404 as a
    successful auth handshake.
    """
    del mode  # retained for registry/API compatibility; semantic mode is separate
    code = "000"
    for attempt in range(retries):
        code = curl_code(url, HTTP_TIMEOUT, token=token)
        if code.startswith("2") or code.startswith("3"):
            return True, f"HTTP {code}"
        if code in ("401", "403"):
            return False, f"key rejected (HTTP {code})"
        if attempt < retries - 1:
            time.sleep(HTTP_RETRY_DELAY)
    return False, f"HTTP {code}"


def _validate_json_object(payload: object | None, required_int_keys: list[str]) -> tuple[bool, str]:
    """Validate only the stable, non-sensitive fields declared by registry."""
    if not isinstance(payload, dict):
        return False, "expected JSON object"
    for key in required_int_keys:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return False, f"JSON field {key} missing or not integer"
    return True, f"JSON schema ok ({len(required_int_keys)} integer fields)"


def check_http_json(url: str, retries: int, token: str = "",
                    required_int_keys: list[str] | None = None) -> tuple[bool, str]:
    """GET an authenticated JSON endpoint and require HTTP 200 plus schema."""
    required_int_keys = required_int_keys or []
    code = "000"
    for attempt in range(retries):
        code, payload = curl_json(url, HTTP_TIMEOUT, token=token)
        if code == "200":
            ok, detail = _validate_json_object(payload, required_int_keys)
            return ok, f"HTTP 200; {detail}"
        if code in ("401", "403"):
            return False, f"key rejected (HTTP {code})"
        if code == "429":
            return False, "rate-limited (HTTP 429) — not proof of key validity"
        if attempt < retries - 1:
            time.sleep(HTTP_RETRY_DELAY)
    return False, f"expected HTTP 200, got {code}"


def _runtime_value(env: dict, key: str) -> str:
    """Prefer the parsed protected env file, then an explicitly exported value."""
    return (env.get(key) or os.environ.get(key) or "").strip().strip("\"'")


def _safe_base_url(raw: str) -> str | None:
    """Return a credential-free HTTP(S) base URL, or None when malformed."""
    raw = (raw or "").strip().strip("\"'").rstrip("/")
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    try:
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not hostname:
        return None
    # urlsplit.hostname strips userinfo for validation; reject it rather than
    # accidentally carrying credentials into a health-check URL.
    if parts.username is not None or parts.password is not None:
        return None
    if parts.query or parts.fragment:
        return None
    netloc = hostname
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]"
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def _honcho_route_url(template: str, env: dict) -> tuple[str | None, str]:
    """Resolve a Honcho workspace route without allowing path injection."""
    base = _safe_base_url(_runtime_value(env, "HONCHO_BASE_URL")
                          or _runtime_value(env, "HONCHO_URL")
                          or "https://api.honcho.dev")
    if not base:
        return None, "invalid Honcho base URL"
    workspace = _runtime_value(env, "HONCHO_WORKSPACE_ID")
    config_path = HERMES_DIR / "honcho.json"
    if not workspace:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            workspace = str(config.get("workspace") or "").strip()
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            workspace = ""
    if not workspace:
        return None, "Honcho workspace is empty or not configured"
    if "/" in workspace or "\\" in workspace or workspace in (".", ".."):
        return None, "Honcho workspace contains a path separator"
    workspace_path = quote(workspace, safe="")
    try:
        return template.format(base=base, workspace=workspace_path), ""
    except (KeyError, ValueError):
        return None, "invalid Honcho route template"


def resolve_check_url(c: dict, env: dict) -> tuple[str | None, str]:
    """Resolve registry URL templates; fixed URLs pass through unchanged."""
    template = c.get("check_url", "")
    if c.get("check_context") == "honcho":
        return _honcho_route_url(template, env)
    return template, "" if template else "check URL is empty"


def check_tcp(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT):
            return True, f"tcp {host}:{port} connected"
    except OSError as e:
        return False, f"tcp {host}:{port}: {e}"


def check_mcp(hermes_bin: str, name: str) -> tuple[bool, str]:
    try:
        r = subprocess.run([hermes_bin, "mcp", "test", name],
                           capture_output=True, text=True, timeout=90)
        out = (r.stdout or "") + (r.stderr or "")
        # exit code is always 0 — parse stdout only (plan §10)
        if FAILED_RE.search(out):
            return False, "mcp: connection failed"
        m = CONNECTED_RE.search(out)
        if not m:
            return False, "mcp: no Connected marker in output"
        detail = f"mcp: connected in {m.group(1)}ms"
        t = TOOLS_RE.search(out)
        if t:
            detail += f", tools={t.group(1)}"
        return True, detail
    except subprocess.TimeoutExpired:
        return False, "mcp: timeout 90s"


def parse_host_port(value: str, default: str = "127.0.0.1:8444") -> tuple[str, int]:
    """Extract host:port; tolerate scheme, quotes and inline .env comments."""
    raw = (value or "").strip().strip('"\'')
    m = re.search(r"([A-Za-z0-9._-]+):(\d{1,5})", raw)
    if m:
        return m.group(1), int(m.group(2))
    return "127.0.0.1", 8444


def parse_expiry(v: str):
    """expires_at from auth.json: epoch float or ISO — tolerant parse, None if unknown."""
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def build_checks(registry: dict, snapshot: dict, env: dict) -> list[dict]:
    checks = []
    entries = {e["key"]: e for e in registry.get("entries", [])}

    # 1. kit entries: deployed config keys, primitive from registry.
    #    required=False + missing key = "unconfigured" (feature-scoped, not a fail)
    for kit in registry.get("kit_entries", []):
        key = kit.get("key", "")
        prim = kit.get("check", "env")
        cid = f"kit:{key}"
        label = kit.get("label", key)
        if prim == "env":
            checks.append({"id": cid, "entity": "kit", "primitive": "env",
                           "key_env": key, "label": label,
                           "required": kit.get("required", False)})
        elif prim == "tg-getme":
            checks.append({"id": cid, "entity": "kit", "primitive": "tg-getme",
                           "key_env": key, "label": label,
                           "required": kit.get("required", False)})
        elif prim == "tcp":
            host, port = parse_host_port(env.get("TELEGRAM_PROXY", ""),
                                         "127.0.0.1:8444")
            checks.append({"id": cid, "entity": "kit", "primitive": "tcp",
                           "host": host, "port": port, "label": label,
                           "required": kit.get("required", False)})

    # 2. live entities from the discover snapshot
    for eid, ent in (snapshot.get("entities") or {}).items():
        etype = ent.get("type")
        if etype == "provider":
            key_env = ent.get("key_env", "")
            # snapshot provider = explicit configuration: missing key is a FAIL,
            # not "unconfigured" (review probe missing_required_provider_key)
            checks.append({"id": eid, "entity": eid, "primitive": "env",
                           "key_env": key_env, "label": f"provider {ent.get('name')}",
                           "registry_key": key_env, "required": True,
                           "key_present": bool(ent.get("key_present"))})
            base_url = (ent.get("base_url") or "").strip()
            if base_url.startswith("http"):
                # api-catalog instead of root http-alive: API roots 404 by design;
                # /models with the provider key proves key + egress + route
                checks.append({"id": f"{eid}#catalog", "entity": eid,
                               "primitive": "api-catalog", "base": base_url,
                               "key_env": key_env,
                               "label": f"provider {ent.get('name')} (catalog)"})
        elif etype == "mcp":
            checks.append({"id": eid, "entity": eid, "primitive": "mcp-test",
                           "mcp_name": ent.get("name", ""), "label": f"mcp {ent.get('name')}"})
        elif etype == "envref":
            key = ent.get("name", "")
            # registry enrichment: the referenced key may carry a real endpoint
            checks.append({"id": eid, "entity": eid, "primitive": "env",
                           "key_env": key, "label": f"envref {key}",
                           "registry_key": key})
        elif etype == "oauth":
            checks.append({"id": eid, "entity": eid, "primitive": "oauth",
                           "name": ent.get("name", ""),
                           "label": f"oauth {ent.get('name')}",
                           "expires_at": ent.get("expires_at", ""),
                           "status": ent.get("status", ""),
                           "required": False})
        elif etype == "envkey":
            # discover v2 layer 2: registry key set in .env = configured integration
            key = ent.get("name", "")
            checks.append({"id": eid, "entity": eid, "primitive": "env",
                           "key_env": key,
                           "label": key,
                           "category": ent.get("category", "setting"),
                           "registry_key": key,
                           "required": False})
        elif etype == "activemodel":
            # informational: rendered by /integrations from report["active_models"]
            continue
        elif etype == "plugin-provider":
            # informational: community model-provider plugins (clinepass case);
            # rendered by /integrations from report["plugin_providers"]
            continue
        elif etype == "local":
            url = ent.get("url", "")
            if url:
                checks.append({"id": eid, "entity": eid, "primitive": "http",
                               "url": url, "label": f"local {ent.get('name')}"})

    # enrich provider checks with registry metadata (url/free) for the report
    for c in checks:
        rk = c.get("registry_key")
        if rk and rk in entries:
            e = entries[rk]
            c["registry"] = {"url": e.get("url"), "free": e.get("free", False)}
            # envref/provider checks inherit a real endpoint from the registry
            if c.get("primitive") == "env" and e.get("check_url"):
                c["check_url"] = e["check_url"]
                c["check_auth"] = e.get("check_auth", "none")
                c["check_context"] = e.get("check_context", "")
                c["check_mode"] = e.get("check_mode", "200")
                c["check_json_int_keys"] = e.get("check_json_int_keys", [])
    return checks


def run_check(c: dict, hermes_bin: str, env: dict) -> tuple[str, str]:
    """Returns (status, detail): ok | fail | unconfigured."""
    prim = c["primitive"]
    if prim == "env":
        key_env = c.get("key_env", "")
        if not key_env:
            if c.get("key_present"):
                return "ok", "inline key configured (endpoint check unavailable)"
            if c.get("required"):
                return "fail", "provider key empty or unset"
            return "unconfigured", "key_env empty (optional)"
        if not env.get(key_env, ""):
            if c.get("required"):
                return "fail", f"key_env {key_env}: empty or unset"
            return "unconfigured", f"key_env {key_env}: not configured (optional)"
        # value-level check: registry may carry a real endpoint for this key
        c_url = c.get("check_url", "")
        if c_url:
            tok = env.get(c["key_env"], "").strip().strip('"\'') \
                if c.get("check_auth") == "bearer" else ""
            resolved_url, resolve_error = resolve_check_url(c, env)
            if not resolved_url:
                return "fail", f"key set; endpoint unavailable ({resolve_error})"
            if c.get("check_mode") == "200-json":
                ok2, d2 = check_http_json(
                    resolved_url,
                    retries=HTTP_RETRIES,
                    token=tok,
                    required_int_keys=c.get("check_json_int_keys", []),
                )
            else:
                ok2, d2 = check_http(
                    resolved_url, retries=HTTP_RETRIES, token=tok,
                    mode=c.get("check_mode", "200"),
                )
            return ("ok" if ok2 else "fail"), f"key set; endpoint {d2}"
        return "ok", f"key_env {c.get('key_env')}: set"
    if prim == "api-catalog":
        token = env.get(c.get("key_env"), "").strip().strip('"\'')
        base = c.get("base", "").rstrip("/")
        candidates = [base + "/models"] if base.endswith("/v1") \
            else [base + "/v1/models", base + "/models"]
        last = "000"
        for url in candidates:
            code = curl_code(url, HTTP_TIMEOUT, token=token)
            if code.startswith("2"):
                return "ok", f"catalog HTTP {code}"
            if code in ("401", "403"):
                # fail fast on ANY candidate: a public fallback catalog does not
                # prove the key is valid (review probe catalog_401_then_public200)
                return "fail", f"key rejected (HTTP {code})"
            if code == "429":
                # Rate limiting is degradation, not proof that the key is valid;
                # fail fast so a public fallback cannot turn it green.
                return "fail", "catalog rate-limited (429) — not proof of key validity"
            if code != "000":
                last = code
        if last == "404":
            return "fail", "no catalog route (404 on both /v1/models and /models)"
        if last == "429":
            return "fail", "catalog rate-limited (429) — not proof of key validity"
        return "fail", f"unreachable (HTTP {last})"
    if prim == "oauth":
        name = c.get("name", "")
        if c.get("status") == "pat-only":
            return ("unconfigured",
                    "classic GitHub PAT is rejected by Copilot — run the device-flow "
                    "login to store COPILOT_GITHUB_TOKEN")
        # Static check only: auth.json access tokens rotate via the refresh flow
        # (expires_at may be past between runs — that is normal, NOT a failure).
        exp_ts = parse_expiry(c.get("expires_at", ""))
        if exp_ts and exp_ts <= time.time():
            return "ok", "logged in (access token past expiry — refresh flow renews it)"
        if exp_ts:
            return "ok", f"logged in (valid until {c.get('expires_at', '')[:19]})"
        return "ok", "logged in"
    if prim == "tg-getme":
        token = (env.get(c.get("key_env", "")) or "").strip().strip('"\'')
        if not token:
            if c.get("required"):
                return "fail", "token empty or unset"
            return "unconfigured", "token not configured (optional)"
        ok, detail = check_tg_getme(token, proxy_url(env))
        return ("ok" if ok else "fail"), detail
    if prim == "tcp":
        ok, detail = check_tcp(c["host"], c["port"])
        return ("ok" if ok else "fail"), detail
    if prim == "http":
        ok, detail = check_http(c["url"], retries=HTTP_RETRIES)
        return ("ok" if ok else "fail"), detail
    if prim == "mcp-test":
        ok, detail = check_mcp(hermes_bin, c["mcp_name"])
        return ("ok" if ok else "fail"), detail
    return "fail", f"unknown primitive {prim}"


def run(argv: list[str] | None = None) -> int:
    """Engine entry, returns the process exit code (testable without os.exit)."""
    ap = argparse.ArgumentParser(description="Registry-driven integration health engine")
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument("--env", type=Path, default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--hermes-bin", default=str(DEFAULT_HERMES_BIN))
    ap.add_argument("--skip", default="", help="comma-separated check ids to skip")
    args = ap.parse_args(argv)

    env = load_env(args.env)
    registry = load_registry(args.registry)
    if not registry:
        print("health-check-v2: registry.yaml missing/empty — run gen-registry.py + deploy", file=sys.stderr)
        return 2
    # Discover snapshot is the SOURCE of what is live: missing/corrupt snapshot
    # is an error state (review probe snapshot_missing_green/corrupt), not a
    # silent kit-only green.
    if not args.snapshot.exists():
        print("health-check-v2: discover snapshot missing — run integration-discover first", file=sys.stderr)
        return 2
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"health-check-v2: snapshot corrupt ({e}) — run integration-discover first", file=sys.stderr)
        return 2

    checks = [c for c in build_checks(registry, snapshot, env)
              if c["id"] not in set(filter(None, args.skip.split(",")))]

    results = []
    for c in checks:
        status, detail = run_check(c, args.hermes_bin, env)
        results.append({"id": c["id"], "label": c["label"], "primitive": c["primitive"],
                        "status": status, "detail": detail,
                        "category": c.get("category", ""),
                        "registry": c.get("registry", {})})

    oks = [r for r in results if r["status"] == "ok"]
    fails = [r for r in results if r["status"] == "fail"]
    unconf = [r for r in results if r["status"] == "unconfigured"]
    skipped = [r for r in results
               if r["status"] not in ("ok", "fail", "unconfigured")]
    active_models = [
        {"role": e.get("role"), "provider": e.get("provider"), "model": e.get("model")}
        for e in (snapshot.get("entities") or {}).values()
        if e.get("type") == "activemodel"
    ]
    plugin_providers = [
        {"name": e.get("name"), "description": e.get("description", "")}
        for e in (snapshot.get("entities") or {}).values()
        if e.get("type") == "plugin-provider"
    ]
    report = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "total": len(results), "ok": len(oks), "fail": len(fails),
        "unconfigured": len(unconf), "skipped": len(skipped),
        "checks": results,
        "active_models": active_models,
        "plugin_providers": plugin_providers,
        "free_models": registry.get("free_models", {}),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8",
                        newline="\n")

    marks = {"ok": "OK  ", "fail": "FAIL", "unconfigured": "SKIP"}
    for r in results:
        print(f"[{marks.get(r['status'], '????')}] {r['label']}: {r['detail']}")
    print(f"health-check-v2: {report['ok']}/{report['total']} ok, "
          f"{report['fail']} fail, {report['unconfigured']} unconfigured, "
          f"{report['skipped']} skipped")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
