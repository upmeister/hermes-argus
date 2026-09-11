#!/usr/bin/env python3
"""ai-deep-check.py — C2 deep check: real chat calls (max_tokens=1) to AI providers.

BUTTON-ONLY, never scheduled (plan §11: regular models-check stays free and
background; deep check is user-triggered, invoked from the monitoring bot
/deepcheck). Paid chat calls are ON by default since the C2 review
(Vlad, 2026-09-07): chat = max_tokens=1 "ping", negligible cost. Model
priority: registry free_models -> :free-suffixed catalog ids -> first catalog
model. DEEP_CHECK_ALLOW_PAID=OFF in ~/.hermes/.env or --no-paid restores
conservative behavior (catalog-only checks).

Levels per live provider (from the discover snapshot):
  catalog — GET {base}/models with Bearer token: key valid, egress ok
  chat    — POST {base}/chat/completions, max_tokens=1: end-to-end proof

Output: JSON report to --out + human lines on stdout; exit 0 ok / 1 failures.
Token values and request bodies are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERMES_DIR = Path(os.environ.get("HERMES_DIR", Path.home() / ".hermes"))
DEFAULT_SNAPSHOT = HERMES_DIR / "state" / "integration-snapshot.json"
DEFAULT_ENV = HERMES_DIR / ".env"
DEFAULT_REGISTRY = HERMES_DIR / "state" / "registry.yaml"
DEFAULT_OUT = HERMES_DIR / "state" / "ai-deep-check-report.json"

FREE_RE = re.compile(r"(?:^|[:\-_/])free(?:$|[:\-_/.])", re.IGNORECASE)
HTTP_TIMEOUT = 20
CHAT_TIMEOUT = 45


def curl_json(url: str, token: str, payload: dict | None, timeout: int,
              attempts: int = 2) -> tuple[int, dict | None]:
    """GET/POST with Bearer auth. Returns (http_code, parsed_json_or_None)."""
    cmd = ["curl", "-s", "-w", "\n%{http_code}", "--max-time", str(timeout),
           "-H", f"Authorization: Bearer {token}"]
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json",
                "-d", json.dumps(payload), url]
    else:
        cmd.append(url)
    code, body = "000", ""
    for attempt in range(attempts):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
            body, _, code = r.stdout.rpartition("\n")
            code = code.strip() or "000"
        except subprocess.TimeoutExpired:
            code = "000"
        if code != "000":
            break
        if attempt < attempts - 1:
            time.sleep(5)
    try:
        return int(code), (json.loads(body) if body else None)
    except json.JSONDecodeError:
        return int(code or 0), None


def api_endpoints(base: str) -> tuple[str, str]:
    """(models_url, chat_url) from a provider base_url; /v1 appended when absent."""
    b = base.rstrip("/")
    if b.endswith("/v1"):
        return b + "/models", b + "/chat/completions"
    return b + "/v1/models", b + "/v1/chat/completions"


def free_chat_model(provider: str, catalog_ids: list[str],
                    free_models: dict) -> str | None:
    """Known free model for this provider: registry data first, then the
    provider's own catalog filtered by the free-regex. None = no free model."""
    for key, models in free_models.items():
        if (provider == key or provider.startswith(key)) and models:
            return models[0]
    for mid in catalog_ids:
        if FREE_RE.search(mid):
            return mid
    return None


def redact_error(text: str, *secrets: str) -> str:
    """Scrub known secret values and sk-style keys from upstream error text."""
    out = text or ""
    for sec in filter(None, secrets):
        out = out.replace(sec, "***")
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", out)


def allow_paid(env: dict, no_paid: bool) -> bool:
    """Paid chat calls ON by default; DEEP_CHECK_ALLOW_PAID (quotes tolerated)
    or --no-paid disables."""
    if no_paid:
        return False
    raw = (env.get("DEEP_CHECK_ALLOW_PAID") or "ON").strip().strip(chr(34) + chr(39)).upper()
    return raw != "OFF"


def active_model_by_provider(snapshot: dict, provider: str) -> str | None:
    """Configured active model for this provider (activemodel entities), if any."""
    for e in (snapshot.get("entities") or {}).values():
        if e.get("type") == "activemodel" and e.get("provider") == provider:
            return e.get("model") or None
    return None


def count_statuses(checks: list) -> tuple:
    """Split checks into (ok, fail, unconfigured, skipped) — statuses never
    collapse into ok (review probe deep_skipped_counted_ok)."""
    oks = [c for c in checks if c.get("status") == "ok"]
    fails = [c for c in checks if c.get("status") == "fail"]
    unconf = [c for c in checks if c.get("status") == "unconfigured"]
    skipped = [c for c in checks if c.get("status") not in ("ok", "fail", "unconfigured")]
    return oks, fails, unconf, skipped


def catalog_verdict(url: str, token: str) -> tuple:
    """Catalog probe verdict: ok only for a JSON 2xx carrying a models list.
    HTML/captcha/WAF 200 is not proof of a catalog (probe deep_html200_green)."""
    code, data = curl_json(url, token, None, HTTP_TIMEOUT)
    if code in (401, 403):
        return "fail", f"key rejected at catalog (HTTP {code})", None
    if code == 0 or code >= 500:
        return "fail", f"catalog unreachable (HTTP {code})", None
    if code >= 400:
        return "fail", f"catalog HTTP {code}", None
    if not isinstance(data, dict) or not isinstance(
            data.get("data") or data.get("models"), list):
        return "fail", "catalog: non-JSON 2xx response", None
    return "ok", "catalog ok", data


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C2 deep check: chat max_tokens=1 per provider")
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument("--env", type=Path, default=DEFAULT_ENV)
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-paid", action="store_true",
                    help="conservative manual run: chat only against known free models")
    args = ap.parse_args(argv)

    # --allow-paid is the DEFAULT since C2 review (Vlad, 2026-09-07): paid chat
    # calls are max_tokens=1 "ping" (negligible cost). DEEP_CHECK_ALLOW_PAID=OFF
    # in .env restores the conservative behavior; --no-paid overrides per run.

    env = {}
    try:
        for line in args.env.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^([A-Z_0-9]+)=", line)
            if m:
                env[m.group(1)] = line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass

    free_models = {}
    try:
        import yaml
        reg = yaml.safe_load(args.registry.read_text(encoding="utf-8")) or {}
        free_models = reg.get("free_models", {}) or {}
    except Exception:
        pass

    try:
        snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        sys.exit("FATAL: discover snapshot missing/invalid — run integration-discover first")

    results = []
    for eid, ent in (snap.get("entities") or {}).items():
        if ent.get("type") != "provider":
            continue
        name = ent.get("name", eid)
        token = (env.get(ent.get("key_env", "")) or "").strip().strip('"\'')
        base = (ent.get("base_url") or "").strip()
        rec = {"id": eid, "provider": name, "status": "skipped", "detail": "", "latency_ms": None}

        if not token:
            rec["status"], rec["detail"] = "unconfigured", "key empty or unset"
            results.append(rec)
            continue
        if not base.startswith("http"):
            rec["status"], rec["detail"] = "skipped", "no base_url in config"
            results.append(rec)
            continue

        models_url, chat_url = api_endpoints(base)
        status, detail, data = catalog_verdict(models_url, token)
        if status == "fail":
            rec["status"], rec["detail"] = "fail", detail
            results.append(rec)
            continue

        catalog_ids = [m.get("id", "") for m in (data.get("data") or data.get("models") or [])
                       if isinstance(m, dict)] if isinstance(data, dict) else []

        chat_model = (active_model_by_provider(snap, name)
                      or free_chat_model(name, catalog_ids, free_models))
        allow_paid = ((env.get("DEEP_CHECK_ALLOW_PAID") or "ON").strip().upper() != "OFF") \
            and not args.no_paid
        if chat_model is None and allow_paid and catalog_ids:
            chat_model = catalog_ids[0]

        if chat_model is None:
            rec["status"] = "ok"
            rec["detail"] = (f"key ok, catalog {len(catalog_ids)} models; "
                             "chat skipped — no known free model (paid checks disabled)")
            results.append(rec)
            continue

        t0 = time.monotonic()
        code, data = curl_json(chat_url, token,
                               {"model": chat_model,
                                "messages": [{"role": "user", "content": "ping"}],
                                "max_tokens": 1},
                               CHAT_TIMEOUT)
        latency = int((time.monotonic() - t0) * 1000)
        rec["latency_ms"] = latency
        err = ""
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            err = redact_error(str(data["error"].get("message", ""))[:120], token)
        if code == 200 and isinstance(data, dict) and data.get("choices"):
            rec["status"] = "ok"
            rec["detail"] = f"chat ok via {chat_model} ({latency}ms)"
        elif code == 429:
            rec["status"] = "fail"
            rec["detail"] = f"chat rate-limited via {chat_model} (429){': ' + err if err else ''}"
        elif code in (401, 403):
            rec["status"] = "fail"
            rec["detail"] = f"chat key rejected via {chat_model} (HTTP {code})"
        else:
            rec["status"] = "fail"
            rec["detail"] = f"chat failed via {chat_model} (HTTP {code}){': ' + err if err else ''}"
        results.append(rec)

    fails = [r for r in results if r["status"] == "fail"]
    oks = [r for r in results if r["status"] == "ok"]
    report = {"updated": datetime.now(timezone.utc).isoformat(),
              "total": len(results), "ok": len(oks),
              "fail": len(fails), "checks": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                        encoding="utf-8", newline="\n")

    marks = {"ok": "OK  ", "fail": "FAIL", "skipped": "SKIP", "unconfigured": "SKIP"}
    for r in results:
        print(f"[{marks.get(r['status'], '????')}] {r['provider']}: {r['detail']}")
    print(f"ai-deep-check: {report['ok']}/{report['total']} ok, {report['fail']} fail")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
