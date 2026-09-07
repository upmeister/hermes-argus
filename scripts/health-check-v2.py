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
  http-alive — GET url, any non-000 response passes (API roots: 401 = alive)
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
    """Key -> raw value. Values stay in memory and are never printed/reported."""
    out = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^([A-Z_0-9]+)=", line)
            if m:
                out[m.group(1)] = line.split("=", 1)[1].strip()
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
        if token:
            cmd += ["-H", f"Authorization: Bearer {token}"]
        cmd.append(url)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return r.stdout.strip() or "000"
    except subprocess.TimeoutExpired:
        return "000"


def check_http(url: str, alive_only: bool, retries: int, token: str = "") -> tuple[bool, str]:
    """GET url. http: 2xx/3xx pass. http-alive: any non-000 passes (401 = alive)."""
    code = "000"
    for attempt in range(retries):
        code = curl_code(url, HTTP_TIMEOUT, token=token)
        ok = (code != "000") if alive_only else (code.startswith("2") or code.startswith("3"))
        if ok:
            return True, f"HTTP {code}"
        if attempt < retries - 1:
            time.sleep(HTTP_RETRY_DELAY)
    return False, f"HTTP {code}"


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
            checks.append({"id": eid, "entity": eid, "primitive": "env",
                           "key_env": key_env, "label": f"provider {ent.get('name')}",
                           "registry_key": key_env})
            base_url = (ent.get("base_url") or "").strip()
            if base_url.startswith("http"):
                checks.append({"id": f"{eid}#http", "entity": eid,
                               "primitive": "http-alive", "url": base_url,
                               "label": f"provider {ent.get('name')} root"})
        elif etype == "mcp":
            checks.append({"id": eid, "entity": eid, "primitive": "mcp-test",
                           "mcp_name": ent.get("name", ""), "label": f"mcp {ent.get('name')}"})
        elif etype == "envref":
            key = ent.get("name", "")
            checks.append({"id": eid, "entity": eid, "primitive": "env",
                           "key_env": key, "label": f"envref {key}"})
        elif etype == "envkey":
            # discover v2 layer 2: registry key set in .env = configured integration
            checks.append({"id": eid, "entity": eid, "primitive": "env",
                           "key_env": ent.get("name", ""),
                           "label": ent.get("name", ""),
                           "category": ent.get("category", "setting"),
                           "check_url": ent.get("check_url", ""),
                           "check_auth": ent.get("check_auth", ""),
                           "check_mode": ent.get("check_mode", ""),
                           "required": False})
        elif etype == "activemodel":
            # informational: rendered by /integrations from report["active_models"]
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
    return checks


def run_check(c: dict, hermes_bin: str, env: dict) -> tuple[str, str]:
    """Returns (status, detail): ok | fail | unconfigured."""
    prim = c["primitive"]
    if prim == "env":
        if not (bool(c.get("key_env")) and bool(env.get(c["key_env"], ""))):
            if c.get("required"):
                return "fail", f"key_env {c.get('key_env')}: empty or unset"
            return "unconfigured", f"key_env {c.get('key_env')}: not configured (optional)"
        # value-level check: registry may carry a real endpoint for this key
        c_url = c.get("check_url", "")
        if c_url:
            mode = c.get("check_mode", "alive")
            tok = env.get(c["key_env"], "").strip().strip('"\'') \
                if c.get("check_auth") == "bearer" else ""
            ok2, d2 = check_http(c_url, alive_only=(mode == "alive"), retries=2, token=tok)
            return ("ok" if ok2 else "fail"), f"key set; endpoint {d2}"
        return "ok", f"key_env {c.get('key_env')}: set"
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
        ok, detail = check_http(c["url"], alive_only=False, retries=HTTP_RETRIES)
        return ("ok" if ok else "fail"), detail
    if prim == "http-alive":
        ok, detail = check_http(c["url"], alive_only=True, retries=HTTP_RETRIES)
        return ("ok" if ok else "fail"), detail
    if prim == "mcp-test":
        ok, detail = check_mcp(hermes_bin, c["mcp_name"])
        return ("ok" if ok else "fail"), detail
    return "fail", f"unknown primitive {prim}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Registry-driven integration health engine")
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument("--env", type=Path, default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--hermes-bin", default=str(DEFAULT_HERMES_BIN))
    ap.add_argument("--skip", default="", help="comma-separated check ids to skip")
    args = ap.parse_args()

    env = load_env(args.env)
    registry = load_registry(args.registry)
    if not registry:
        print("health-check-v2: registry.yaml missing/empty — run gen-registry.py + deploy", file=sys.stderr)
        sys.exit(2)
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot.exists() else {}
    except json.JSONDecodeError:
        snapshot = {}

    checks = [c for c in build_checks(registry, snapshot, env)
              if c["id"] not in set(filter(None, args.skip.split(",")))]

    results = []
    for c in checks:
        status, detail = run_check(c, args.hermes_bin, env)
        results.append({"id": c["id"], "label": c["label"], "primitive": c["primitive"],
                        "status": status, "detail": detail,
                        "category": c.get("category", ""),
                        "registry": c.get("registry", {})})

    fails = [r for r in results if r["status"] == "fail"]
    unconf = [r for r in results if r["status"] == "unconfigured"]
    active_models = [
        {"role": e.get("role"), "provider": e.get("provider"), "model": e.get("model")}
        for e in (snapshot.get("entities") or {}).values()
        if e.get("type") == "activemodel"
    ]
    report = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "total": len(results), "ok": len(results) - len(fails) - len(unconf),
        "fail": len(fails), "unconfigured": len(unconf),
        "checks": results,
        "active_models": active_models,
        "free_models": registry.get("free_models", {}),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8",
                        newline="\n")

    marks = {"ok": "OK  ", "fail": "FAIL", "unconfigured": "SKIP"}
    for r in results:
        print(f"[{marks.get(r['status'], '????')}] {r['label']}: {r['detail']}")
    print(f"health-check-v2: {report['ok']}/{report['total']} ok, "
          f"{report['fail']} fail, {report['unconfigured']} unconfigured")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
