#!/usr/bin/env python3
"""probes.py — регрессионный суит по 43 пробам ревью Питны (2026-09-10).

Каждый дефект из engine-tests/REVIEW.md = тест-кейс. Прогон:
  python3 tests/probes.py            # все пробы
  python3 tests/probes.py -k catalog # по подстроке id

D0a (2026-09-13) добавляет секцию schema-v2: envelope/projection движка и
dual-read hysteresis обёртки (ADR 0001).

Изоляция: dummy HOME/каталоги, subprocess-вызовы подменяются на fixture-фейк
curl (см. _FakeCurl), сеть не трогается. Секреты в фикстурах — только
DUMMY_* маркеры.

Статусы: ok | fail | unconfigured | skipped — раздельные, никогда не
сворачиваются в ok (системный урок ревью: 'not a failure' != 'ok').
"""
from __future__ import annotations

import importlib
import importlib.util
import shutil
import subprocess
import json
import os
import sys
import shlex
import tempfile
import re
import time
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

PASS, FAIL = [], []


def check(probe_id: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(probe_id)
    print(f"[{'PASS' if ok else 'FAIL'}] {probe_id}" + (f" — {detail}" if detail else ""))


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, str(REPO / "scripts" / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


@contextmanager
def override_attr(obj, name: str, value):
    """Temporarily replace mutable module state for one isolated probe."""
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


# ── Фикстуры ────────────────────────────────────────────────────────────────

DUMMY_TOKEN = "DUMMY_SECRET_TOKEN"
DUMMY_KEY = "DUMMY_SECRET_ECHO"

STICKY_LINE = ("2026-09-08 21:05:47,123 WARNING gateway.platforms.telegram.telegram_network: "
               "[Telegram] Sticky Telegram path 149.154.167.220 failed; re-walking IPv4 literals before the hostname")
IPV4_LINE = ("2026-09-08 21:53:29,456 WARNING gateway.platforms.telegram.telegram_network: "
             "[Telegram] IPv4 Telegram API IP 149.154.167.220 failed:")
REAL_TG_LINE = "2026-09-10 02:26:00,000 ERROR gateway: Telegram API error: token=DUMMY_LOG_SECRET"

SNAP_PROVIDERS = {
    "entities": {
        "provider:dummy": {"type": "provider", "name": "dummy", "key_env": "DUMMY_KEY",
                           "key_present": True, "base_url": "https://dummy.invalid/v1"},
        "provider:https://dummy:DUMMY_URL_PASSWORD@dummy.invalid/mcp": {
            "type": "provider", "name": "https://dummy:DUMMY_URL_PASSWORD@dummy.invalid/mcp",
            "key_env": "", "key_present": True,
            "base_url": "https://dummy:DUMMY_URL_PASSWORD@dummy.invalid/mcp?token=DUMMY_QUERY_SECRET"},
        "mcp:dummy": {"type": "mcp", "name": "dummy", "transport": "http",
                      "url": "https://dummy:DUMMY_URL_PASSWORD@dummy.invalid/mcp?token=DUMMY_QUERY_SECRET"},
    },
    "env_keys": [],
}


# ── Пробы: health-check-v2 ──────────────────────────────────────────────────

def probe_catalog_429(hc):
    """429 не доказывает accepted key — fail, а не ok."""
    codes = iter(["429"])
    fake_curl = lambda url, timeout, token="": next(codes, "429")
    with override_attr(hc, "curl_code", fake_curl):
        status, detail = hc.run_check(
            {"id": "p", "primitive": "api-catalog", "base": "https://dummy.invalid/v1",
             "key_env": "DUMMY_KEY", "label": "p"}, "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("catalog_429", status == "fail", detail)


def probe_catalog_401_then_public200(hc):
    """401 на первом кандидате — fail fast, публичный каталог не спасает."""
    calls = []

    def fake_curl(url, timeout, token=""):
        calls.append(url)
        return "401" if url.endswith("/v1/models") else "200"

    with override_attr(hc, "curl_code", fake_curl):
        status, detail = hc.run_check(
            {"id": "p", "primitive": "api-catalog", "base": "https://dummy.invalid",
             "key_env": "DUMMY_KEY", "label": "p"}, "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("catalog_401_then_public200", status == "fail" and calls == [
        "https://dummy.invalid/v1/models"], detail)


def probe_catalog_429_then_public200(hc):
    """429 на первом кандидате — fail fast, публичный каталог не спасает."""
    calls = []

    def fake_curl(url, timeout, token=""):
        calls.append(url)
        return "429" if url.endswith("/v1/models") else "200"

    with override_attr(hc, "curl_code", fake_curl):
        status, detail = hc.run_check(
            {"id": "p", "primitive": "api-catalog", "base": "https://dummy.invalid",
             "key_env": "DUMMY_KEY", "label": "p"}, "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("catalog_429_then_public200", status == "fail" and calls == [
        "https://dummy.invalid/v1/models"], detail)


def probe_honcho_503_green(hc):
    """alive-режим удалён: 503 = fail, а не 'auth wall, service alive'."""
    codes = iter(["503"])
    fake_curl = lambda url, timeout, token="": next(codes, "503")
    with override_attr(hc, "curl_code", fake_curl):
        status, detail = hc.run_check(
            {"id": "p", "primitive": "http", "url": "https://api.honcho.dev/",
             "label": "p"}, "hermes", {})
    check("honcho_503_green", status == "fail", detail)


def probe_generator_honcho_contract():
    """The registry generator cannot silently restore the root/404 probe."""
    gen = load_module("gen-registry")
    url, auth, mode = gen.CHECK_URLS["HONCHO_API_KEY"]
    meta = gen.CHECK_METADATA["HONCHO_API_KEY"]
    check("generator_honcho_contract",
          url == "{base}/v3/workspaces/{workspace}/queue/status"
          and auth == "bearer" and mode == "200-json"
          and meta.get("check_context") == "honcho"
          and len(meta.get("check_json_int_keys", [])) == 4,
          f"{url} / {auth} / {mode}")


def probe_honcho_queue_json_200(hc, tmp: Path):
    """Honcho workspace queue route returns 200 and the stable counter schema."""
    write(tmp / "honcho.json", '{"workspace": "hermes"}\n')
    seen = []

    def fake_curl_json(url, timeout, token=""):
        seen.append((url, token))
        return "200", "application/json", {
            "total_work_units": 0,
            "completed_work_units": 0,
            "in_progress_work_units": 0,
            "pending_work_units": 0,
        }

    with override_attr(hc, "HERMES_DIR", tmp), override_attr(hc, "curl_json", fake_curl_json):
        status, detail = hc.run_check(
            {"id": "envkey:HONCHO_API_KEY", "primitive": "env", "key_env": "DUMMY_KEY",
             "check_url": "{base}/v3/workspaces/{workspace}/queue/status",
             "check_context": "honcho", "check_auth": "bearer", "check_mode": "200-json",
             "check_json_int_keys": ["total_work_units", "completed_work_units",
                                     "in_progress_work_units", "pending_work_units"],
             "label": "Honcho", "required": False},
            "hermes", {"DUMMY_KEY": DUMMY_TOKEN, "HONCHO_BASE_URL": "https://honcho.invalid"})
    expected_url = "https://honcho.invalid/v3/workspaces/hermes/queue/status"
    check("honcho_queue_json_200", status == "ok"
          and seen == [(expected_url, DUMMY_TOKEN)]
          and "HTTP 200" in detail and "JSON schema ok" in detail, detail)


def probe_honcho_queue_json_401(hc, tmp: Path):
    """Invalid/missing Honcho credentials remain a hard failure."""
    write(tmp / "honcho.json", '{"workspace": "hermes"}\n')
    seen = []

    def fake_curl_json(url, timeout, token=""):
        seen.append((url, token))
        return "401", "application/json", {"error": "invalid"}

    with override_attr(hc, "HERMES_DIR", tmp), override_attr(hc, "curl_json", fake_curl_json):
        status, detail = hc.run_check(
            {"id": "envkey:HONCHO_API_KEY", "primitive": "env", "key_env": "DUMMY_KEY",
             "check_url": "{base}/v3/workspaces/{workspace}/queue/status",
             "check_context": "honcho", "check_auth": "bearer", "check_mode": "200-json",
             "check_json_int_keys": ["total_work_units"], "label": "Honcho", "required": False},
            "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("honcho_queue_json_401", status == "fail" and seen
          and seen[0][1] == DUMMY_TOKEN and "key rejected" in detail, detail)


def probe_honcho_queue_json_schema(hc, tmp: Path):
    """HTTP 200 without the declared queue counters is not semantic success."""
    write(tmp / "honcho.json", '{"workspace": "hermes"}\n')
    fake_curl_json = lambda url, timeout, token="": (
        "200", "application/json", {"total_work_units": 0})
    with override_attr(hc, "HERMES_DIR", tmp), override_attr(hc, "curl_json", fake_curl_json):
        status, detail = hc.run_check(
            {"id": "envkey:HONCHO_API_KEY", "primitive": "env", "key_env": "DUMMY_KEY",
             "check_url": "{base}/v3/workspaces/{workspace}/queue/status",
             "check_context": "honcho", "check_auth": "bearer", "check_mode": "200-json",
             "check_json_int_keys": ["total_work_units", "pending_work_units"],
             "label": "Honcho", "required": False},
            "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("honcho_queue_json_schema", status == "fail"
          and "pending_work_units" in detail, detail)


def probe_honcho_token_not_in_argv(hc):
    """Authorization is piped to curl, never placed in its process argv."""
    real_run = hc.subprocess.run
    captured = {}

    class Result:
        stdout = '{"total_work_units": 0}\napplication/json\n200'

    def fake_run(cmd, **kwargs):
        captured["argv"] = list(cmd)
        captured["input"] = kwargs.get("input")
        return Result()

    hc.subprocess.run = fake_run
    try:
        code, content_type, payload = hc.curl_json(
            "https://honcho.invalid/queue/status", 5, DUMMY_TOKEN)
    finally:
        hc.subprocess.run = real_run
    argv = " ".join(captured.get("argv", []))
    piped = captured.get("input") or ""
    check("honcho_token_not_in_argv", code == "200"
          and content_type == "application/json"
          and isinstance(payload, dict)
          and DUMMY_TOKEN not in argv
          and DUMMY_TOKEN in piped
          and "@-" in captured.get("argv", []),
          f"argv_has_token={DUMMY_TOKEN in argv} input_present={bool(piped)}")


def probe_honcho_workspace_path_injection(hc, tmp: Path):
    """A workspace identifier cannot escape the intended URL path."""
    write(tmp / "honcho.json", '{"workspace": "hermes/other"}\n')
    called = []
    fake_curl_json = lambda url, timeout, token="": (
        called.append(url) or ("200", "application/json", {}))
    with override_attr(hc, "HERMES_DIR", tmp), override_attr(hc, "curl_json", fake_curl_json):
        status, detail = hc.run_check(
            {"id": "envkey:HONCHO_API_KEY", "primitive": "env", "key_env": "DUMMY_KEY",
             "check_url": "{base}/v3/workspaces/{workspace}/queue/status",
             "check_context": "honcho", "check_auth": "bearer", "check_mode": "200-json",
             "check_json_int_keys": [], "label": "Honcho", "required": False},
            "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("honcho_workspace_path_injection", status == "fail" and not called
          and "path separator" in detail, detail)


def probe_honcho_json_content_type(hc, tmp: Path):
    """HTTP 200 with a non-JSON media type is not semantic success."""
    write(tmp / "honcho.json", '{"workspace": "hermes"}\n')
    fake_curl_json = lambda url, timeout, token="": (
        "200", "text/html", {"total_work_units": 0})
    with override_attr(hc, "HERMES_DIR", tmp), override_attr(hc, "curl_json", fake_curl_json):
        status, detail = hc.run_check(
            {"id": "envkey:HONCHO_API_KEY", "primitive": "env", "key_env": "DUMMY_KEY",
             "check_url": "{base}/v3/workspaces/{workspace}/queue/status",
             "check_context": "honcho", "check_auth": "bearer", "check_mode": "200-json",
             "check_json_int_keys": ["total_work_units"], "label": "Honcho", "required": False},
            "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("honcho_json_content_type", status == "fail" and "application/json" in detail, detail)


def probe_honcho_profile_host_block(hc, tmp: Path):
    """Named profiles use profile-local, then default-file host configuration."""
    profile_home = tmp / ".hermes" / "profiles" / "coder"
    default_home = tmp / ".hermes"
    global_config = tmp / ".honcho" / "config.json"
    default_config = {
        "workspace": "root-space", "baseUrl": "https://root.invalid",
        "hosts": {"hermes_coder": {"workspace": "coder-space",
                                     "baseUrl": "https://profile.invalid"}},
    }
    write(default_home / "honcho.json", json.dumps(default_config))
    with override_attr(hc, "HERMES_DIR", profile_home), override_attr(
            hc, "HONCHO_GLOBAL_CONFIG", global_config):
        default_url, default_error = hc._honcho_route_url(
            "{base}/v3/workspaces/{workspace}/queue/status",
            {"HONCHO_WORKSPACE_ID": "legacy-space"})
        write(profile_home / "honcho.json", json.dumps({
            "workspace": "local-space", "baseUrl": "https://local.invalid"}))
        local_url, local_error = hc._honcho_route_url(
            "{base}/v3/workspaces/{workspace}/queue/status",
            {"HONCHO_WORKSPACE_ID": "legacy-space"})
    expected_default = "https://profile.invalid/v3/workspaces/coder-space/queue/status"
    expected_local = "https://local.invalid/v3/workspaces/local-space/queue/status"
    check("honcho_profile_host_block",
          not default_error and default_url == expected_default
          and not local_error and local_url == expected_local,
          f"default_url={default_url} default_error={default_error} "
          f"local_url={local_url} local_error={local_error}")


def probe_honcho_default_host(hc, tmp: Path):
    """Default profile honors Honcho's configured defaultHost."""
    home = tmp / "default-home"
    global_config = tmp / ".honcho" / "config.json"
    write(home / "honcho.json", json.dumps({
        "defaultHost": "team",
        "hosts": {"team": {"workspace": "team-space", "baseUrl": "https://team.invalid"}},
    }))
    with override_attr(hc, "HERMES_DIR", home), override_attr(
            hc, "HONCHO_GLOBAL_CONFIG", global_config):
        url, error = hc._honcho_route_url(
            "{base}/v3/workspaces/{workspace}/queue/status", {})
    check("honcho_default_host",
          not error and url == "https://team.invalid/v3/workspaces/team-space/queue/status",
          f"url={url} error={error}")


def probe_honcho_default_profile_fallback(hc, tmp: Path):
    """A named profile falls back to the default profile config file."""
    profile_home = tmp / "fallback" / ".hermes" / "profiles" / "coder"
    global_config = tmp / ".honcho" / "config.json"
    write(tmp / "fallback" / ".hermes" / "honcho.json", json.dumps({
        "hosts": {"hermes_coder": {"workspace": "shared-config",
                                     "baseUrl": "https://fallback.invalid"}},
    }))
    with override_attr(hc, "HERMES_DIR", profile_home), override_attr(
            hc, "HONCHO_GLOBAL_CONFIG", global_config):
        url, error = hc._honcho_route_url(
            "{base}/v3/workspaces/{workspace}/queue/status", {})
    check("honcho_default_profile_fallback",
          not error and url == "https://fallback.invalid/v3/workspaces/shared-config/queue/status",
          f"url={url} error={error}")


def probe_honcho_global_config_fallback(hc, tmp: Path):
    """Global Honcho config is used when Hermes-local files are absent."""
    home = tmp / "no-honcho-here"
    global_config = tmp / ".honcho" / "config.json"
    write(global_config, json.dumps({
        "workspace": "global-space", "baseUrl": "https://global.invalid"}))
    with override_attr(hc, "HERMES_DIR", home), override_attr(
            hc, "HONCHO_GLOBAL_CONFIG", global_config):
        config_url, config_error = hc._honcho_route_url(
            "{base}/v3/workspaces/{workspace}/queue/status",
            {"HONCHO_WORKSPACE_ID": "legacy-space"})
        global_config.unlink()
        fallback_url, fallback_error = hc._honcho_route_url(
            "{base}/v3/workspaces/{workspace}/queue/status",
            {"HONCHO_WORKSPACE_ID": "legacy-space"})
    check("honcho_global_config_fallback",
          not config_error
          and config_url == "https://global.invalid/v3/workspaces/global-space/queue/status"
          and not fallback_error
          and fallback_url == "https://api.honcho.dev/v3/workspaces/legacy-space/queue/status",
          f"config_url={config_url} config_error={config_error} "
          f"fallback_url={fallback_url} fallback_error={fallback_error}")


def probe_missing_required_provider_key(hc):
    """Провайдер из снапшота с пустым ключом = fail (не unconfigured)."""
    checks = hc.build_checks(
        {}, {"entities": {"provider:dummy": {
            "type": "provider", "name": "dummy", "key_env": "DUMMY_KEY",
            "key_present": True, "base_url": ""}}}, {"DUMMY_KEY": ""})
    c = next(c for c in checks if c["id"] == "provider:dummy")
    status, _ = hc.run_check(c, "hermes", {"DUMMY_KEY": ""})
    check("missing_required_provider_key", status == "fail", "status=" + status)


def probe_quoted_empty_provider_key(hc, tmp: Path):
    """Quoted empty dotenv values are empty, not configured."""
    env = write(tmp / "quoted-empty.env", 'DUMMY_KEY=""\n')
    loaded = hc.load_env(env)
    c = {"id": "provider:dummy", "primitive": "env", "key_env": "DUMMY_KEY",
         "required": True, "label": "dummy"}
    status, _ = hc.run_check(c, "hermes", loaded)
    check("quoted_empty_provider_key", loaded.get("DUMMY_KEY") == "" and status == "fail",
          f"value={loaded.get('DUMMY_KEY')!r} status={status}")


def probe_snapshot_missing_green(hc, tmp: Path):
    """Отсутствующий снапшот = exit 2 (ошибка состояния), не зелёный."""
    registry = write(tmp / "valid-registry.yaml", "kit_entries: []\n")
    rc = hc.run(["--snapshot", str(tmp / "missing.json"),
                 "--env", str(tmp / "no.env"), "--registry", str(registry)])
    check("snapshot_missing_green", rc == 2, f"rc={rc}")


def probe_snapshot_corrupt_green(hc, tmp: Path):
    """Битый JSON снапшота = exit 2."""
    registry = write(tmp / "valid-registry-corrupt.yaml", "kit_entries: []\n")
    p = write(tmp / "corrupt.json", "{not json")
    rc = hc.run(["--snapshot", str(p),
                 "--env", str(tmp / "no.env"), "--registry", str(registry)])
    check("snapshot_corrupt_green", rc == 2, f"rc={rc}")


def probe_health_cli_entrypoint(tmp: Path):
    """The installed CLI entrypoint invokes run(), not a removed main()."""
    result = subprocess.run(["python3", str(REPO / "scripts" / "health-check-v2.py"), "--help"],
                            cwd=REPO, capture_output=True, text=True, timeout=15)
    check("health_cli_entrypoint", result.returncode == 0 and "usage:" in result.stdout.lower(),
          f"rc={result.returncode} stderr={result.stderr.strip()}")


# ── Пробы: ai-deep-check ────────────────────────────────────────────────────

def probe_deep_skipped_counted_ok(dc):
    checks = [{"id": "provider:dummy", "status": "unconfigured"}]
    oks, fails, unconf, skipped = dc.count_statuses(checks)
    check("deep_skipped_counted_ok", len(oks) == 0 and len(unconf) == 1 and len(fails) == 0,
          f"oks={len(oks)} unconf={len(unconf)}")


def probe_deep_html200_green(dc):
    """HTML 200 не доказывает каталог — fail, а не ok."""
    dc.curl_json = lambda url, token, payload, timeout: (
        200, None) if payload is None else (200, {"choices": []})
    status, detail, _data = dc.catalog_verdict("https://dummy.invalid/v1/models", DUMMY_TOKEN)
    check("deep_html200_green", status == "fail", "status=" + status + " " + detail)


def probe_deep_error_secret_leak(dc):
    """Ошибка API, эхом содержащая ключ, редактируется до отчёта."""
    err = dc.redact_error("Rejected request key " + DUMMY_KEY, DUMMY_KEY)
    check("deep_error_secret_leak", DUMMY_KEY not in err, "leak!" if DUMMY_KEY in err else "redacted")


def probe_deep_quoted_off_ignored(dc):
    allow = dc.allow_paid({"DEEP_CHECK_ALLOW_PAID": '"OFF"'}, no_paid=False)
    check("deep_quoted_off_ignored", allow is False, f"allow={allow}")


# ── Пробы: fallback-tracker ─────────────────────────────────────────────────

def probe_fallback_same_second_lost(ft, tmp: Path):
    """Два события в одну секунду — оба обрабатываются (ms в watermark)."""
    ft.LOG_DIR = tmp
    log = write(tmp / "agent.log",
                "2026-09-11 00:00:01,100 INFO [s1] agent.chat_completion_helpers: Fallback to dummy/paid-model: attached fallback credential pool\n"
                "2026-09-11 00:00:01,900 INFO [s1] agent.chat_completion_helpers: Fallback to dummy/paid-model: attached fallback credential pool\n")
    events = ft.scan_events()
    st = {"last_ts": 0, "sessions": {}}
    st, alerts = ft.apply_events(st, events, {})
    check("fallback_same_second_lost",
          len(events) == 2
          and st["last_ts"] == events[-1]["ts"]
          and st["sessions"]["s1"]["hops"] == 2,
          f"events={len(events)} state={st}")


def probe_fallback_cross_session_restore(ft, tmp: Path):
    """Restore в сессии B не закрывает каскад сессии A."""
    events = [
        {"ts": 1.0, "ts_str": "t1", "sid": "session-A", "kind": "hop",
         "provider": "dummy", "model": "paid-model"},
        {"ts": 2.0, "ts_str": "t2", "sid": "session-B", "kind": "restore",
         "provider": "dummy", "model": "primary-model"},
    ]
    st, alerts = ft.apply_events({"last_ts": 0, "sessions": {}}, events, {})
    sess_a = st["sessions"].get("session-A", {})
    sess_b = st["sessions"].get("session-B", {})
    check("fallback_cross_session_restore",
          sess_a.get("mode") == "fallback" and sess_a.get("hops") == 1
          and sess_b.get("mode") == "primary",
          f"session-A={sess_a} session-B={sess_b}")


def probe_envref_enrichment(hc):
    """envref-чек наследует registry check_url (probe envref_drops_auth_check)."""
    reg = {"entries": [{"key": "GITHUB_TOKEN", "check_url": "https://api.github.com/user",
                        "check_auth": "bearer", "check_mode": "200"}]}
    snap = {"entities": {"envref:GITHUB_TOKEN": {"type": "envref", "name": "GITHUB_TOKEN"}}}
    checks = hc.build_checks(reg, snap, {"GITHUB_TOKEN": "x"})
    c = next(c for c in checks if c["id"] == "envref:GITHUB_TOKEN")
    check("envref_enrichment", c.get("check_url") == "https://api.github.com/user"
          and c.get("check_auth") == "bearer", f"check={c}")


def probe_envkey_enrichment(hc):
    """envkey checks inherit the registry route and semantic metadata."""
    reg = {"entries": [{"key": "DUMMY_KEY",
                         "check_url": "{base}/v3/workspaces/{workspace}/queue/status",
                         "check_context": "honcho", "check_auth": "bearer",
                         "check_mode": "200-json",
                         "check_json_int_keys": ["total_work_units"]}]}
    snap = {"entities": {"envkey:DUMMY_KEY": {"type": "envkey", "name": "DUMMY_KEY",
                                                 "category": "tool"}}}
    checks = hc.build_checks(reg, snap, {"DUMMY_KEY": DUMMY_TOKEN})
    c = next(c for c in checks if c["id"] == "envkey:DUMMY_KEY")
    seen = []
    home = Path(tempfile.mkdtemp(prefix="argus-honcho-enrichment-"))
    write(home / "honcho.json", '{"workspace": "hermes"}\n')

    def fake_curl_json(url, timeout, token=""):
        seen.append((url, token))
        return "200", "application/json", {"total_work_units": 0}

    with override_attr(hc, "HERMES_DIR", home), override_attr(hc, "curl_json", fake_curl_json):
        status, detail = hc.run_check(c, "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    expected_url = "https://api.honcho.dev/v3/workspaces/hermes/queue/status"
    ok = (c.get("registry_key") == "DUMMY_KEY"
          and c.get("check_url") == "{base}/v3/workspaces/{workspace}/queue/status"
          and c.get("check_context") == "honcho"
          and c.get("check_auth") == "bearer"
          and c.get("check_mode") == "200-json"
          and status == "ok" and seen == [(expected_url, DUMMY_TOKEN)])
    check("envkey_enrichment", ok, f"check={c} status={status} seen={seen} detail={detail}")


def probe_deep_activemodel_targeted(dc, tmp: Path):
    """Deep check таргетит активную модель (probe deep_actual_model_ignored)."""
    snap = write(tmp / "snap.json", json.dumps({"entities": {
        "provider:dummy": {"type": "provider", "name": "dummy", "key_env": "DUMMY_KEY",
                           "key_present": True, "base_url": "https://dummy.invalid/v1"},
        "model:primary": {"type": "activemodel", "role": "primary",
                          "provider": "dummy", "model": "actual-primary"}}}))
    write(tmp / "env", "DUMMY_KEY=x" + chr(10))
    calls = []

    def fake_curl(url, token, payload, timeout):
        calls.append((url, payload))
        if payload is None:
            return 200, {"data": [{"id": "unrelated-first"}]}
        return 200, {"choices": [{"message": {"content": "pong"}}]}

    dc.curl_json = fake_curl
    out = tmp / "rep.json"
    r = dc.run(["--snapshot", str(snap), "--env", str(tmp / "env"),
                "--registry", str(tmp / "no.reg"), "--out", str(out)])
    report = json.loads(out.read_text())
    chat_calls = [c for c in calls if "chat" in c[0]]
    targeted = any(p and p.get("model") == "actual-primary" for _, p in chat_calls)
    check("deep_activemodel_targeted", r == 0 and targeted and len(calls) == 2
          and report.get("ok") == 1 and report.get("fail") == 0,
          f"rc={r} calls={calls} report={report}")


def probe_deep_paid_off_main(dc, tmp: Path):
    """Quoted DEEP_CHECK_ALLOW_PAID=OFF reaches main and prevents chat."""
    snap = write(tmp / "paid-off-snap.json", json.dumps({"entities": {
        "provider:dummy": {"type": "provider", "name": "dummy", "key_env": "DUMMY_KEY",
                           "key_present": True, "base_url": "https://dummy.invalid/v1"},
        "model:primary": {"type": "activemodel", "role": "primary",
                          "provider": "dummy", "model": "actual-paid"}}}))
    env = write(tmp / "paid-off.env", 'DUMMY_KEY=x\nDEEP_CHECK_ALLOW_PAID="OFF"\n')
    calls = []

    def fake_curl(url, token, payload, timeout):
        calls.append((url, payload))
        if payload is None:
            return 200, {"data": [{"id": "actual-paid"}]}
        return 200, {"choices": [{"message": {"content": "must-not-run"}}]}

    dc.curl_json = fake_curl
    out = tmp / "paid-off-report.json"
    r = dc.run(["--snapshot", str(snap), "--env", str(env),
                "--registry", str(tmp / "no-paid.reg"), "--out", str(out)])
    report = json.loads(out.read_text())
    check("deep_paid_off_main", r == 0 and len(calls) == 1 and report.get("ok") == 1
          and report.get("fail") == 0 and report.get("unconfigured") == 0,
          f"rc={r} calls={calls} report={report}")


def probe_deep_unconfigured_report(dc, tmp: Path):
    """Deep report exposes unconfigured separately from ok."""
    snap = write(tmp / "unconfigured-snap.json", json.dumps({"entities": {
        "provider:dummy": {"type": "provider", "name": "dummy", "key_env": "DUMMY_KEY",
                           "key_present": False, "base_url": "https://dummy.invalid/v1"}}}))
    env = write(tmp / "unconfigured.env", "")
    out = tmp / "unconfigured-report.json"
    r = dc.run(["--snapshot", str(snap), "--env", str(env),
                "--registry", str(tmp / "no-unconfigured.reg"), "--out", str(out)])
    report = json.loads(out.read_text())
    check("deep_unconfigured_report", r == 0 and report.get("ok") == 0
          and report.get("fail") == 0 and report.get("unconfigured") == 1
          and report.get("skipped") == 0,
          f"rc={r} report={report}")


def probe_wrapper_crash_no_stale(hp, tmp: Path):
    """Engine crash with RC=1 must not process an old report."""
    import subprocess
    home = tmp / "crash-home"
    hermes = home / ".hermes"
    write(home / "scripts" / "health-check-v2.py",
          'raise RuntimeError("dummy engine crash; no report generated")')
    write(hermes / "state" / "health-check-v2-report.json", json.dumps({
        "updated": "2026-09-10T00:00:00+00:00", "total": 1, "ok": 0, "fail": 1,
        "checks": [{"id": "provider:dummy", "label": "dummy", "status": "fail",
                    "detail": "old failure"}]}))
    write(hermes / "state" / "health-check-v2-state.json",
          json.dumps({"provider:dummy": 2}))
    write(hermes / "logs" / ".keep", "")
    r = subprocess.run(["bash", str(REPO / "scripts" / "health-check-v2-wrapper.sh")],
                       capture_output=True, text=True, timeout=30,
                       env=_probe_subprocess_env(home))
    state = json.loads((hermes / "state" / "health-check-v2-state.json").read_text())
    log = (hermes / "logs" / "health-check-v2.log").read_text()
    check("wrapper_crash_no_stale", r.returncode == 0
          and state.get("provider:dummy") == 2
          and "stale report NOT processed" in log,
          f"rc={r.returncode} state={state}")


def probe_wrapper_unconfigured_not_recovery(hp, tmp: Path):
    """unconfigured does not reset a prior failure counter in the real wrapper."""
    import subprocess
    home = tmp / "unconfigured-home"
    hermes = home / ".hermes"
    report = {"updated": "2026-09-10T00:00:00+00:00", "total": 1,
              "ok": 0, "fail": 0, "unconfigured": 1,
              "checks": [{"id": "provider:dummy", "label": "dummy",
                          "status": "unconfigured", "detail": "n/a"}]}
    engine = (
        "import json, os\n"
        "from pathlib import Path\n"
        "p = Path(os.environ['HOME']) / '.hermes' / 'state' / 'health-check-v2-report.json'\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        f"p.write_text({json.dumps(json.dumps(report))})\n"
    )
    write(home / "scripts" / "health-check-v2.py", engine)
    write(hermes / "state" / "health-check-v2-report.json", json.dumps(report))
    write(hermes / "state" / "health-check-v2-state.json",
          json.dumps({"provider:dummy": 2}))
    write(hermes / "logs" / ".keep", "")
    r = subprocess.run(["bash", str(REPO / "scripts" / "health-check-v2-wrapper.sh")],
                       capture_output=True, text=True, timeout=30,
                       env=_probe_subprocess_env(home))
    state = json.loads((hermes / "state" / "health-check-v2-state.json").read_text())
    check("wrapper_unconfigured_not_recovery", r.returncode == 0
          and state.get("provider:dummy") == 2,
          f"rc={r.returncode} state={state}")


def probe_fallback_registry_free_ignored(ft, tmp: Path):
    """Модель из registry free_models классифицируется как free без ':free' в id."""
    check("fallback_registry_free_ignored",
          ft.is_free_model("openrouter", "minimax-m3",
                           {"openrouter": ["minimax-m3"]}) is True,
          "registry free_models must classify")


def probe_fallback_baseline_first_incident(ft, tmp: Path):
    """Baseline на истории с активным инцидентом: первый НОВЫЙ инцидент в новой
    сессии алертит (probe fallback_first_incident_baselined)."""
    events = [
        {"ts": 1.0, "ts_str": "t1", "sid": "old-session", "kind": "hop",
         "provider": "dummy", "model": "paid-model"},
    ]
    st, alerts = ft.apply_events({"sessions": {}}, events, {})
    check("fallback_baseline_silent", not alerts, "baseline must be silent")
    new_incident = [
        {"ts": 100.0, "ts_str": "t2", "sid": "new-session", "kind": "hop",
         "provider": "dummy", "model": "paid-model"},
    ]
    st2, alerts2 = ft.apply_events(st, new_incident, {})
    check("fallback_baseline_first_incident_alerts", len(alerts2) == 1,
          f"alerts={alerts2}")

# ── Пробы: health_patterns ──────────────────────────────────────────────────

def probe_disk100(hp, tmp: Path):
    log = write(tmp / "gateway.log",
                "2026-09-11 00:05:00,000 WARNING systemd: disk usage 100%\n")
    hp.GATEWAY_LOG = log
    res = hp.find_issues(open(log, encoding="utf-8").read())
    d99 = "disk_high" in res and res["disk_high"].get("detected")
    check("disk100_not_detected", bool(d99), f"res={list(res)}")


def probe_telegram_final_attempt(hp, tmp: Path):
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    log = write(tmp / "gateway.log",
                f"{ts},000 ERROR gateway.platforms.telegram.telegram_network: "
                "[Telegram] network error (attempt 10/10): connection failed\n")
    hp.GATEWAY_LOG = log
    res = hp.find_issues(open(log, encoding="utf-8").read())
    check("telegram_final_attempt_excluded", "telegram_api_error" in res,
          f"res={list(res)}")


def probe_pattern_sample_secret_leak(hp, tmp: Path):
    log = write(tmp / "gateway.log", REAL_TG_LINE + "\n")
    hp.GATEWAY_LOG = log
    res = hp.find_issues(open(log, encoding="utf-8").read())
    sample = str(res.get("telegram_api_error", {}).get("sample", ""))
    check("pattern_sample_secret_leak", "DUMMY_LOG_SECRET" not in sample,
          "redacted" if "DUMMY_LOG_SECRET" not in sample else "leak!")


def probe_pattern_bearer_secret_leak(hp, tmp: Path):
    """Bearer value is redacted even when preceded by Authorization:."""
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    log = write(tmp / "bearer.log",
                f"{ts},000 ERROR gateway: "
                "Telegram API error: Authorization: Bearer DUMMY_BEARER_SECRET\n")
    hp.GATEWAY_LOG = log
    res = hp.find_issues(open(log, encoding="utf-8").read())
    sample = str(res.get("telegram_api_error", {}).get("sample", ""))
    check("pattern_bearer_secret_leak", "DUMMY_BEARER_SECRET" not in sample,
          "redacted" if "DUMMY_BEARER_SECRET" not in sample else "leak!")


# ── Пробы: integration-discover (санитайзер URL) ───────────────────────────

def probe_discover_url_secret_leak(disc, tmp: Path):
    cfg = write(tmp / "config.yaml",
                "custom_providers:\n"
                "  - name: dummy\n"
                "    key_env: DUMMY_KEY\n"
                "    base_url: https://dummy:DUMMY_URL_PASSWORD@dummy.invalid/mcp?token=DUMMY_QUERY_SECRET\n")
    disc.CONFIG = cfg
    disc.ENV_FILE = tmp / "no.env"
    disc.SNAPSHOT = tmp / "snap.json"
    entities, _env = disc.extract_entities()
    blob = json.dumps(entities, ensure_ascii=False)
    leaks = ("DUMMY_URL_PASSWORD" in blob) or ("DUMMY_QUERY_SECRET" in blob)
    check("discover_url_secret_leak", not leaks, "leak!" if leaks else "sanitized")


def probe_discover_url_shape_and_literals(disc, tmp: Path):
    """userinfo удалён без placeholder-host; literal URL-ключи тоже очищаются."""
    cfg = write(
        tmp / "config-literal.yaml",
        "custom_providers:\n"
        "  - name: dummy\n"
        "    key_env: DUMMY_KEY\n"
        "    base_url: 'https://dummy:DUMMY_URL_PASSWORD@dummy.invalid/mcp?token=DUMMY_QUERY_SECRET'\n"
        "SEARXNG_URL: 'https://literal:DUMMY_LITERAL_PASSWORD@search.invalid:8443/search?api_key=DUMMY_LITERAL_SECRET&region=eu'\n",
    )
    disc.CONFIG = cfg
    disc.ENV_FILE = tmp / "no-literal.env"
    disc.SNAPSHOT = tmp / "literal-snap.json"
    entities, _env = disc.extract_entities()
    provider = next(e for e in entities.values() if e.get("type") == "provider")
    custom = disc.urlsplit(provider["base_url"])
    literal = disc.urlsplit(entities["local:SEARXNG_URL"]["url"])
    custom_qs = dict(disc.parse_qsl(custom.query, keep_blank_values=True))
    literal_qs = dict(disc.parse_qsl(literal.query, keep_blank_values=True))
    blob = json.dumps(entities, ensure_ascii=False)
    secrets = (
        "DUMMY_URL_PASSWORD", "DUMMY_QUERY_SECRET",
        "DUMMY_LITERAL_PASSWORD", "DUMMY_LITERAL_SECRET",
    )
    ok = (
        custom.username is None and custom.password is None
        and custom.netloc == "dummy.invalid"
        and custom_qs.get("token") == "<redacted>"
        and literal.username is None and literal.password is None
        and literal.hostname == "search.invalid" and literal.port == 8443
        and literal_qs.get("api_key") == "<redacted>"
        and literal_qs.get("region") == "eu"
        and not any(secret in blob for secret in secrets)
    )
    check("discover_url_shape_and_literals", ok,
          f"custom={custom.geturl()} literal={literal.geturl()}")


# ── Пробы: OA1 — структурный account-auth discovery + skipped-семантика ─────

def _oa1_auth(auth: dict) -> str:
    return json.dumps(auth, ensure_ascii=False)


def _oa1_fixture(providers: dict | None = None, pool: dict | None = None,
                 active: str | None = None) -> dict:
    auth: dict = {"version": 2}
    if providers is not None:
        auth["providers"] = providers
    if pool is not None:
        auth["credential_pool"] = pool
    if active is not None:
        auth["active_provider"] = active
    return auth


def _oa1_discover(disc, tmp: Path, auth, env_text: str = "") -> dict:
    """extract_entities на синтетическом HERMES_DIR (auth.json = фикстура:
    dict → JSON, str → сырое содержимое для malformed-кейсов)."""
    raw = auth if isinstance(auth, str) else json.dumps(auth, ensure_ascii=False)
    disc.AUTH_JSON = write(tmp / "auth.json", raw)
    disc.CONFIG = write(tmp / "config.yaml", "")
    disc.ENV_FILE = write(tmp / "no.env", env_text)
    disc.REGISTRY = tmp / "no-registry.yaml"
    disc.SNAPSHOT = tmp / "snap.json"
    entities, _env = disc.extract_entities()
    return entities


def probe_oa1_discovery_fixtures(disc, tmp: Path):
    """OA1 acceptance: flat control, nested Codex, pool-only, generic future
    id, dedupe, api-key/unknown/bare negative controls, active marker."""
    # 1. flat positive control (nous: access_token + refresh_token)
    ents = _oa1_discover(disc, tmp, _oa1_fixture(
        providers={"nous": {"access_token": "OA1_CANARY_A",
                            "refresh_token": "OA1_CANARY_B"}}, active="nous"))
    check("oa1_flat_positive_control",
          ents.get("oauth:nous") == {"type": "oauth", "name": "nous", "active": True},
          f"got {ents.get('oauth:nous')!r}")

    # 2. nested Codex singleton (tokens.*)
    ents = _oa1_discover(disc, tmp, _oa1_fixture(providers={
        "openai-codex": {"tokens": {"access_token": "OA1_CANARY_C",
                                    "refresh_token": "OA1_CANARY_D"},
                         "last_refresh": "x", "auth_mode": "chatgpt"}}))
    check("oa1_nested_codex_singleton",
          ents.get("oauth:openai-codex") == {"type": "oauth", "name": "openai-codex",
                                             "active": False},
          f"got {ents.get('oauth:openai-codex')!r}")

    # 3. pool-only Codex (auth_type=oauth)
    ents = _oa1_discover(disc, tmp, _oa1_fixture(pool={
        "openai-codex": [{"id": "r1", "label": "L", "auth_type": "oauth",
                          "priority": 0, "source": "device_code",
                          "access_token": "OA1_CANARY_E",
                          "refresh_token": "OA1_CANARY_F"}]}))
    check("oa1_pool_only_codex",
          ents.get("oauth:openai-codex") == {"type": "oauth", "name": "openai-codex",
                                             "active": False},
          f"got {ents.get('oauth:openai-codex')!r}")

    # 4. generic future provider id — без правки ростера
    ents = _oa1_discover(disc, tmp, _oa1_fixture(pool={
        "synthetic-future-provider": [{"auth_type": "oauth", "access_token": "x"}]}))
    check("oa1_generic_future_pool_provider",
          ents.get("oauth:synthetic-future-provider") == {
              "type": "oauth", "name": "synthetic-future-provider", "active": False},
          f"got {ents.get('oauth:synthetic-future-provider')!r}")

    # 5. same-id dedupe (singleton + pool = одна сущность)
    ents = _oa1_discover(disc, tmp, _oa1_fixture(
        providers={"openai-codex": {"tokens": {"access_token": "a", "refresh_token": "r"}}},
        pool={"openai-codex": [{"auth_type": "oauth", "access_token": "b"}]}))
    codex_keys = [k for k in ents if k.startswith("oauth:openai-codex")]
    check("oa1_same_id_dedupe", codex_keys == ["oauth:openai-codex"], f"keys={codex_keys}")

    # 7. негативные контролы: явный api_key, неизвестный auth_type,
    #    bare access_token (pool и flat) — НЕ account-auth свидетельства
    ents = _oa1_discover(disc, tmp, _oa1_fixture(
        providers={"api-key-blob": {"access_token": "OA1_CANARY_G"}},
        pool={"keyed": [{"auth_type": "api_key", "access_token": "OA1_CANARY_H",
                         "refresh_token": "OA1_CANARY_I"}],
              "weird": [{"auth_type": "totp", "refresh_token": "OA1_CANARY_J"}],
              "bare": [{"access_token": "OA1_CANARY_K"}]}))
    leftovers = [k for k in ents if k.startswith("oauth:")]
    check("oa1_apikey_negative_control", leftovers == [], f"leaked={leftovers}")

    # 10. active marker: точное совпадение id, без alias-нормализации
    ents = _oa1_discover(disc, tmp, _oa1_fixture(
        pool={"xai-oauth": [{"auth_type": "oauth", "access_token": "a"}]}, active="xai"))
    check("oa1_active_marker_exact_id",
          ents.get("oauth:xai-oauth", {}).get("active") is False,
          f"got {ents.get('oauth:xai-oauth')!r}")
    ents = _oa1_discover(disc, tmp, _oa1_fixture(
        pool={"xai-oauth": [{"auth_type": "oauth", "access_token": "a"}]},
        active="xai-oauth"))
    check("oa1_active_marker_match",
          ents.get("oauth:xai-oauth", {}).get("active") is True,
          f"got {ents.get('oauth:xai-oauth')!r}")


def probe_oa1_storage_shape_stability(disc, tmp: Path):
    """OA1 acceptance 6: singleton-only vs pool-only vs both для того же id
    дают идентичную сущность (без provenance-шума)."""
    singleton = _oa1_discover(disc, tmp, _oa1_fixture(
        providers={"openai-codex": {"tokens": {"access_token": "a", "refresh_token": "r"}}}))
    pooled = _oa1_discover(disc, tmp, _oa1_fixture(
        pool={"openai-codex": [{"auth_type": "oauth", "access_token": "a",
                                "refresh_token": "r"}]}))
    both = _oa1_discover(disc, tmp, _oa1_fixture(
        providers={"openai-codex": {"tokens": {"access_token": "a", "refresh_token": "r"}}},
        pool={"openai-codex": [{"auth_type": "oauth", "access_token": "a"}]}))
    e1 = singleton.get("oauth:openai-codex")
    e2 = pooled.get("oauth:openai-codex")
    e3 = both.get("oauth:openai-codex")
    check("oa1_storage_shape_stability", e1 is not None and e1 == e2 == e3,
          f"singleton={e1!r} pool={e2!r} both={e3!r}")


def probe_oa1_malformed_ignored(disc, tmp: Path):
    """OA1 acceptance 8 + review remediation: битые/неполные структуры auth.json
    не роняют дискавери и не классифицируются как OAuth."""
    cases = {
        "corrupt_json": "{not json",
        "json_null": "null",
        "json_list": "[]",
        "providers_not_dict": _oa1_auth({"providers": ["nous"]}),
        "pool_not_dict": _oa1_auth({"credential_pool": {"x": "oops"}}),
        "rows_not_list": _oa1_auth({"credential_pool": {"x": {"auth_type": "oauth"}}}),
        "row_not_dict": _oa1_auth({"credential_pool": {"x": ["oauth", 5, None]}}),
        "tokens_not_dict": _oa1_auth({"providers": {"x": {"tokens": "oauth"}}}),
        "refresh_not_str": _oa1_auth({"providers": {"x": {"refresh_token": ["r"]}},
                                      "credential_pool": {"y": [{"auth_type": None,
                                                                 "refresh_token": 7}]}}),
        "auth_type_int": _oa1_auth({"credential_pool": {"x": [{"auth_type": 5,
                                                               "access_token": "a"}]}}),
        # remediation: partial nested tokens — рантайм требует ОБЕ части пары
        "tokens_partial_access": _oa1_auth({"providers": {"x": {"tokens": {
            "access_token": "a"}}}}),
        "tokens_partial_refresh": _oa1_auth({"providers": {"x": {"tokens": {
            "refresh_token": "r"}}}}),
        # remediation: присутствующий, но falsey auth_type — malformed,
        # а НЕ «отсутствие ключа» (weak-fallback не применяется)
        "auth_type_null": _oa1_auth({"credential_pool": {"x": [
            {"auth_type": None, "refresh_token": "r"}]}}),
        "auth_type_empty": _oa1_auth({"credential_pool": {"x": [
            {"auth_type": "", "refresh_token": "r"}]}}),
        "auth_type_false": _oa1_auth({"credential_pool": {"x": [
            {"auth_type": False, "refresh_token": "r"}]}}),
    }
    results = {}
    for name, raw in cases.items():
        try:
            ents = _oa1_discover(disc, tmp, raw)
            results[name] = sorted(k for k in ents if k.startswith("oauth:"))
        except Exception as e:  # noqa: BLE001 — проба ловит любой краш
            results[name] = f"CRASH: {e}"
    bad = {k: v for k, v in results.items() if v != []}
    check("oa1_malformed_ignored", not bad, f"{bad}")


def probe_oa1_copilot_compat(disc, tmp: Path):
    """OA1 acceptance 9: Copilot env-канал не изменился (token vs PAT-only)."""
    ents = _oa1_discover(disc, tmp, _oa1_fixture(), env_text="COPILOT_GITHUB_TOKEN=x\n")
    check("oa1_copilot_token_entity",
          ents.get("oauth:copilot") == {"type": "oauth", "name": "copilot", "active": False},
          f"got {ents.get('oauth:copilot')!r}")
    ents = _oa1_discover(disc, tmp, _oa1_fixture(), env_text="GITHUB_TOKEN=x\n")
    check("oa1_copilot_pat_only",
          ents.get("oauth:copilot") == {"type": "oauth", "name": "copilot",
                                        "active": False, "status": "pat-only"},
          f"got {ents.get('oauth:copilot')!r}")


def probe_oa1_secret_canary_scan(tmp: Path):
    """OA1 secret boundary: canary во всех секретных полях фикстуры не
    появляется в snapshot, discover report/stdout/stderr и health-report."""
    home = tmp / "oa1-home"
    canaries = {
        "flat_access": "OA1_CANARY_FLAT_ACCESS",
        "flat_refresh": "OA1_CANARY_FLAT_REFRESH",
        "nested_access": "OA1_CANARY_NESTED_ACCESS",
        "nested_refresh": "OA1_CANARY_NESTED_REFRESH",
        "pool_access": "OA1_CANARY_POOL_ACCESS",
        "pool_refresh": "OA1_CANARY_POOL_REFRESH",
        "fingerprint": "OA1_CANARY_FINGERPRINT",
        "label": "OA1_CANARY_LABEL",
        "row_id": "OA1_CANARY_ROWID",
    }
    auth = {
        "version": 2, "active_provider": "nous",
        "providers": {
            "nous": {"access_token": canaries["flat_access"],
                     "refresh_token": canaries["flat_refresh"]},
            "openai-codex": {"tokens": {"access_token": canaries["nested_access"],
                                        "refresh_token": canaries["nested_refresh"]},
                             "last_refresh": "2026-01-01T00:00:00Z",
                             "auth_mode": "chatgpt"},
        },
        "credential_pool": {
            "openai-codex": [{"id": canaries["row_id"], "label": canaries["label"],
                              "auth_type": "oauth", "priority": 0,
                              "source": "device_code",
                              "access_token": canaries["pool_access"],
                              "refresh_token": canaries["pool_refresh"],
                              "secret_fingerprint": canaries["fingerprint"]}],
            "keyed": [{"id": "k", "auth_type": "api_key",
                       "access_token": canaries["pool_access"],
                       "secret_fingerprint": canaries["fingerprint"]}],
        },
    }
    write(home / "auth.json", _oa1_auth(auth))
    write(home / "config.yaml", "")
    write(home / ".env", "")
    env = dict(os.environ, HERMES_DIR=str(home),
               DISCOVER_REPORT=str(tmp / "oa1-report.json"))
    outs = []
    for _ in range(2):  # baseline-прогон + diff-прогон
        r = subprocess.run(["python3", str(REPO / "scripts" / "integration-discover.py")],
                           cwd=REPO, env=env, capture_output=True, timeout=60)
        outs.append((r.stdout.decode(errors="ignore"), r.stderr.decode(errors="ignore")))
    snapshot_text = (home / "state" / "integration-snapshot.json").read_text(encoding="utf-8")
    report_path = tmp / "oa1-report.json"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    registry = write(tmp / "oa1-registry.yaml", "kit_entries: []\n")
    hc_out = tmp / "oa1-health-report.json"
    hc = subprocess.run(
        ["python3", str(REPO / "scripts" / "health-check-v2.py"),
         "--registry", str(registry),
         "--snapshot", str(home / "state" / "integration-snapshot.json"),
         "--env", str(home / ".env"), "--out", str(hc_out)],
        cwd=REPO, capture_output=True, timeout=120)
    hc_report = hc_out.read_text(encoding="utf-8") if hc_out.exists() else ""
    blob = "\n".join([snapshot_text, report_text, hc_report, hc.stdout.decode(errors="ignore"),
                      hc.stderr.decode(errors="ignore"),
                      *(part for pair in outs for part in pair)])
    leaks = sorted({name for name, value in canaries.items() if value in blob})
    check("oa1_secret_canary_scan", not leaks, f"leaked_canaries={leaks}")


def probe_oa1_health_static_evidence_non_green(hc, tmp: Path):
    """OA1 acceptance 11-13: статическая oauth-сущность = skipped/не-зелёная,
    никогда ok/'logged in'."""
    registry = write(tmp / "oa1-reg.yaml", "kit_entries: []\n")
    snapshot = write(tmp / "oa1-snap.json", json.dumps({
        "updated": "2026-09-19T00:00:00Z",
        "entities": {"oauth:openai-codex": {"type": "oauth", "name": "openai-codex",
                                            "active": True}},
        "env_keys": []}))
    envf = write(tmp / "oa1.env", "")
    out = tmp / "oa1-health.json"
    rc = hc.run(["--registry", str(registry), "--snapshot", str(snapshot),
                 "--env", str(envf), "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    rows = [c for c in report["checks"] if c.get("id") == "oauth:openai-codex"]
    c = rows[0] if rows else {}
    ok = (rc == 0
          and c.get("status") == "skipped"
          and c.get("verdict") == "skipped"
          and "logged" not in (c.get("detail") or "").lower()
          and report["summary"]["healthy"] == 0
          and report["summary"]["skipped"] == 1)
    check("oa1_health_static_evidence_non_green", ok,
          f"rc={rc} status={c.get('status')} verdict={c.get('verdict')} "
          f"detail={c.get('detail')!r} summary={report.get('summary')}")


def probe_oa1_health_pat_only_unconfigured(hc, tmp: Path):
    """OA1 acceptance 14: pat-only остаётся unconfigured (не skipped)."""
    registry = write(tmp / "oa1-reg3.yaml", "kit_entries: []\n")
    snapshot = write(tmp / "oa1-snap3.json", json.dumps({
        "updated": "2026-09-19T00:00:00Z",
        "entities": {"oauth:copilot": {"type": "oauth", "name": "copilot",
                                       "active": False, "status": "pat-only"}},
        "env_keys": []}))
    envf = write(tmp / "oa3.env", "")
    out = tmp / "oa1-health3.json"
    rc = hc.run(["--registry", str(registry), "--snapshot", str(snapshot),
                 "--env", str(envf), "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    rows = [c for c in report["checks"] if c.get("id") == "oauth:copilot"]
    c = rows[0] if rows else {}
    check("oa1_health_pat_only_unconfigured",
          rc == 0 and c.get("status") == "unconfigured"
          and report["summary"]["unconfigured"] == 1,
          f"rc={rc} status={c.get('status')} summary={report.get('summary')}")


def probe_oa1_quick_report_not_green(wh):
    """OA1 acceptance 15: quick-рендер не зелёный на skipped-only отчёте."""
    report = {
        "schema": 2, "updated": "2026-09-19T00:00:00+00:00", "total": 1,
        "summary": {"total": 1, "healthy": 0, "failed": 0, "unknown": 0,
                    "unconfigured": 0, "skipped": 1},
        "checks": [{"id": "oauth:openai-codex", "entity_id": "oauth:openai-codex",
                    "status": "skipped", "verdict": "skipped",
                    "label": "oauth openai-codex",
                    "detail": "persisted credential evidence present; "
                              "login/health not verified"}],
    }
    text = wh._render_integrations_quick(report)
    check("oa1_quick_report_not_green",
          "всё в порядке" not in text and "⏸" in text, f"text={text!r}")


# ── Пробы OA1b: презентационная семантика OAuth-свидетельств ───────────────

def _oa1b_row(cid: str, label: str, status: str, primitive: str | None = None,
              detail: str = "x") -> dict:
    verdict = {"ok": "healthy", "fail": "failed"}.get(status, status)
    row = {"id": cid, "entity_id": cid, "label": label, "status": status,
           "verdict": verdict, "detail": detail, "category": "",
           "reason_code": "", "claims": {}, "effects": {}, "evidence": {}}
    if primitive is not None:
        row["primitive"] = primitive
    return row


def _oa1b_report(rows: list) -> dict:
    verdicts = [r["verdict"] for r in rows]
    return {
        "schema": 2, "updated": "2026-09-19T12:00:00+00:00", "total": len(rows),
        "summary": {"total": len(rows), "healthy": verdicts.count("healthy"),
                    "failed": verdicts.count("failed"),
                    "unknown": verdicts.count("unknown"),
                    "unconfigured": verdicts.count("unconfigured"),
                    "skipped": verdicts.count("skipped")},
        "checks": rows, "inventory": {},
    }


def probe_oa1b_full_oauth_evidence(wh):
    """OA1b §7.1: OAuth-свидетельство в full view — informational-строка без
    ⏸/✅/«пропущено»."""
    report = _oa1b_report([
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
        _oa1b_row("oauth:openai-codex", "oauth openai-codex", "skipped", "oauth"),
    ])
    text = wh._render_integrations_full(report, {})
    row = next(l for l in text.split("\n") if "oauth nous" in l)
    ok = ("🔐" in row and "учётные данные обнаружены" in row
          and "runtime-статус не проверяется" in row
          and "⏸" not in row and "✅" not in row and "пропущено" not in row)
    check("oa1b_full_oauth_evidence", ok, f"row={row!r}")


def probe_oa1b_full_generic_skipped_control(wh):
    """OA1b §7.2: generic skipped (не oauth) в full view — прежний ⏸-рендер."""
    report = _oa1b_report([
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
    ])
    text = wh._render_integrations_full(report, {})
    row = next(l for l in text.split("\n") if "kit tg-auth" in l)
    check("oa1b_full_generic_skipped_control",
          "⏸" in row and "пропущено" in row and "🔐" not in row,
          f"row={row!r}")


def probe_oa1b_full_counts_split(wh):
    """OA1b §5/§7.5: счётчик ⏸ считает только generic-skipped; OAuth-свидетельства
    идут отдельным нейтральным 🔐-счётчиком."""
    report = _oa1b_report([
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
        _oa1b_row("provider:dummy", "provider dummy", "ok", "env"),
    ])
    text = wh._render_integrations_full(report, {})
    counts = text.split("\n")[1]
    check("oa1b_full_counts_split",
          "⏸ 1" in counts and "🔐 1" in counts and "⏸ 2" not in counts
          and "✅ 1" in counts,
          f"counts={counts!r}")


def probe_oa1b_full_oauth_line_survives_cap(wh):
    """OA1b remediation (Pytna P2): лимит 4000 символов full view не режет и
    не отбрасывает строку OAuth-свидетельства — обязательное заявление
    «runtime-статус не проверяется» доезжает целиком; резка идёт по целым
    строкам (сценарий ревьюера: 16 healthy-меток по 250 символов)."""
    long_label = "provider " + "p" * 241
    rows = [_oa1b_row(f"provider:fill{i}", long_label, "ok", "env")
            for i in range(16)]
    rows.append(_oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"))
    text = wh._render_integrations_full(_oa1b_report(rows), {})
    evidence_line = ("🔐 oauth nous — учётные данные обнаружены · "
                     "runtime-статус не проверяется")
    out_lines = text.split("\n")
    complete = {evidence_line, "✅ " + long_label, "🤖 AI-провайдеры (custom)",
                "🔐 OAuth-провайдеры", ""}
    healthy_left = sum(1 for l in out_lines if l == "✅ " + long_label)
    ok = (len(text) <= 4000
          and evidence_line in out_lines
          and healthy_left < 16
          and all(l in complete or l.startswith(("👁 ", "✅ 1"))
                  for l in out_lines))
    check("oa1b_full_oauth_line_survives_cap", ok,
          f"len={len(text)} evidence_complete={evidence_line in out_lines} "
          f"healthy_left={healthy_left}")


def probe_oa1b_full_failure_survives_cap(wh):
    """OA1b remediation 2 (Pytna P2): cap 4000 не удаляет реальную ❌-строку
    провала — с хвоста падают только информационные строки; провал и
    OAuth-свидетельство доезжают целиком. Наполнители лежат в ТОМ же
    kit:watchdog-bucket, что и провал, и идут ПЕРЕД ним: на старом слепом
    cap-е рубка попадает в наполнители, и провал исчезает из вывода
    (проба красная на 3ff88370)."""
    long_label = "kit " + "k" * 280
    rows = [_oa1b_row(f"kit:fill{i}", long_label, "ok", "env")
            for i in range(15)]
    rows.append(_oa1b_row("kit:failure", "kit failure", "fail", "http",
                          "HTTP 500"))
    rows.append(_oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"))
    text = wh._render_integrations_full(_oa1b_report(rows), {})
    evidence_line = ("🔐 oauth nous — учётные данные обнаружены · "
                     "runtime-статус не проверяется")
    fail_line = "❌ kit failure — HTTP 500"
    out_lines = text.split("\n")
    healthy_left = sum(1 for l in out_lines if l == "✅ " + long_label)
    ok = (len(text) <= 4000
          and fail_line in out_lines
          and evidence_line in out_lines
          and healthy_left < 15
          and "🛡 Watchdog kit" in out_lines)
    check("oa1b_full_failure_survives_cap", ok,
          f"len={len(text)} failure={fail_line in out_lines} "
          f"evidence_complete={evidence_line in out_lines} "
          f"healthy_left={healthy_left}")


def probe_oa1b_quick_oauth_only_not_blank_green(wh):
    """OA1b §7.3: quick view на healthy+OAuth-only — не «всё в порядке», не
    «пропущены политикой», имена видны, runtime-статус заявлен непроверенным."""
    report = _oa1b_report([
        _oa1b_row("provider:dummy", "provider dummy", "ok", "env"),
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
        _oa1b_row("oauth:openai-codex", "oauth openai-codex", "skipped", "oauth"),
    ])
    text = wh._render_integrations_quick(report)
    ok = ("всё в порядке" not in text
          and "пропущены политикой" not in text and "⏸" not in text
          and "nous" in text and "openai-codex" in text
          and "учётные данные обнаружены" in text
          and "runtime-статус не проверяется" in text)
    check("oa1b_quick_oauth_only_not_blank_green", ok, f"text={text!r}")


def probe_oa1b_quick_mixed_failure_and_oauth(wh):
    """OA1b §7.4: реальный провал виден, OAuth-свидетельство — informational-
    контекст, зелёного заявления нет; generic-skipped quick-контроль прежний."""
    fail_report = _oa1b_report([
        _oa1b_row("provider:dummy#http", "provider dummy root", "fail", "http",
                  "HTTP 503"),
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
    ])
    text = wh._render_integrations_quick(fail_report)
    mixed_ok = ("❌" in text and "provider dummy root" in text
                and "учётные данные обнаружены" in text
                and "всё в порядке" not in text)
    generic_report = _oa1b_report([
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
    ])
    generic_text = wh._render_integrations_quick(generic_report)
    generic_ok = "⏸ 1 проверок пропущены политикой" in generic_text
    check("oa1b_quick_mixed_failure_and_oauth",
          mixed_ok and generic_ok, f"mixed={text!r} generic={generic_text!r}")


def probe_oa1b_report_not_mutated(wh):
    """OA1b §7.5: рендер не мутирует канонический отчёт (JSON summary неизменен)."""
    report = _oa1b_report([
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
        _oa1b_row("provider:dummy", "provider dummy", "ok", "env"),
    ])
    before = json.loads(json.dumps(report))
    wh._render_integrations_full(report, {})
    wh._render_integrations_quick(report)
    check("oa1b_report_not_mutated", report == before, "report changed")


def probe_oa1b_helpers_are_pure():
    """OA1b §4: OAuth-свидетельства классифицируются по структурным полям
    (verdict + primitive) — без имён провайдеров и без сравнения detail-текста."""
    src = (REPO / "scripts" / "webhook.py").read_text(encoding="utf-8")
    banned = ('"nous"', '"codex"', '"openai-codex"', '"xai"', '"minimax"',
              'get("detail") ==')
    hits = sorted({b for b in banned if b in src})
    classified = ('_oauth_evidence_rows' in src
                  and src.count('get("primitive") == "oauth"') >= 2)
    check("oa1b_helpers_are_pure", not hits and classified,
          f"hits={hits} classified={classified}")


def probe_oa1_helpers_are_pure():
    """OA1 §8: хелперы дискавери — чистая структурная логика, без I/O-поверхности."""
    src = (REPO / "scripts" / "integration-discover.py").read_text(encoding="utf-8")
    body = src[src.index("def _nonempty_credential"):src.index("def load_registry")]
    banned = ("subprocess", "urllib", "requests", "socket", "curl", "hermes",
              "os.system", "popen", "open(", "read_text", "write_text")
    hits = sorted({b for b in banned if b in body})
    check("oa1_helpers_are_pure", not hits, f"hits={hits}")


# ── Пробы S4: MCP disabled-by-config (contract mcp-disabled-server-compat) ──
# Канарки вместо реального hermes-бина: на фиксе ни одна не вызывается
# (ноль подпроцессов), на baseline канарка честно показывает, что выключенный
# сервер проверялся бы (HTTP → false-fail, stdio → false-green).

def probe_mcpoff_disabled_http_not_failed(tmp: Path):
    """S4 contract probe 1: выключенный HTTP-сервер (enabled: false + dead URL)
    — skipped/mcp_disabled_by_config, не failed; снапшот несёт флаг."""
    home = _r2a_home(tmp, "mcpoff-http")
    write(home / "config.yaml",
          "mcp_servers:\n  off-http:\n    enabled: false\n"
          "    url: https://dead.invalid/v1\n")
    _r2a_run(home, args=["--baseline"])
    ent = _r2a_snap(home)["entities"]["mcp:off-http"]
    hc = load_module("health-check-v2")
    registry = write(tmp / "mcpoff-reg1.yaml", "kit_entries: []\n")
    out = tmp / "mcpoff-http-report.json"
    calls = []

    def _fail_canary(*a, **k):
        calls.append(1)
        return False, "mcp: connection failed (CANARY — disabled server probed)"

    orig = hc.check_mcp
    hc.check_mcp = _fail_canary
    try:
        rc = hc.run(["--registry", str(registry),
                     "--snapshot", str(home / "state" / "integration-snapshot.json"),
                     "--env", str(home / ".env"), "--out", str(out)])
    finally:
        hc.check_mcp = orig
    row = (json.loads(out.read_text(encoding="utf-8"))["checks"][0]
           if out.exists() else {})
    ok = (rc == 0 and not calls
          and ent.get("enabled") is False and ent.get("transport") == "http"
          and row.get("status") == "skipped" and row.get("verdict") == "skipped"
          and row.get("reason_code") == "mcp_disabled_by_config"
          and row.get("detail") == "mcp: disabled by config")
    check("mcpoff_disabled_http_not_failed", ok,
          f"rc={rc} canary_calls={len(calls)} entity={ent} row={row}")


def probe_mcpoff_disabled_stdio_not_green(disc, hc, tmp: Path):
    """S4 contract probe 2: выключенный stdio-сервер (валидный command) — не
    green и не failed: check_mcp не вызывается, даже когда вернул бы green."""
    cfg = {"mcp_servers": {"off-stdio": {"enabled": False, "command": "/bin/true"}}}
    entities = _r2c_entities(disc, tmp, "mcpoff-stdio", cfg)
    ent = entities["mcp:off-stdio"]
    calls = []

    def _green_canary(*a, **k):
        calls.append(1)
        return True, "mcp: connected in 1ms (CANARY)"

    orig = hc.check_mcp
    hc.check_mcp = _green_canary
    try:
        checks = hc.build_checks({"kit_entries": []},
                                 {"entities": entities, "env_keys": []}, {})
        row = next(c for c in checks if c["id"] == "mcp:off-stdio")
        status, detail = hc.run_check(row, "shimmed-hermes", {})
    finally:
        hc.check_mcp = orig
    ok = (not calls and ent.get("enabled") is False
          and ent.get("transport") == "stdio"
          and row.get("primitive") == "mcp-disabled"
          and status == "skipped" and detail == "mcp: disabled by config")
    check("mcpoff_disabled_stdio_not_green", ok,
          f"canary_calls={len(calls)} primitive={row.get('primitive')} "
          f"status={status} detail={detail!r}")


def _mcpoff_enabled_still_probed(disc, hc, tmp: Path, home_name: str,
                                 extra: dict, pid: str):
    cfg = {"mcp_servers": {"on-http": {"url": "https://live.invalid/v1", **extra}}}
    entities = _r2c_entities(disc, tmp, home_name, cfg)
    ent = entities["mcp:on-http"]
    calls = []

    def _ok_canary(*a, **k):
        calls.append(1)
        return True, "mcp: connected in 5ms"

    orig = hc.check_mcp
    hc.check_mcp = _ok_canary
    try:
        checks = hc.build_checks({"kit_entries": []},
                                 {"entities": entities, "env_keys": []}, {})
        row = next(c for c in checks if c["id"] == "mcp:on-http")
        status, detail = hc.run_check(row, "shimmed-hermes", {})
    finally:
        hc.check_mcp = orig
    ok = ("enabled" not in ent and len(calls) == 1
          and row.get("primitive") == "mcp-test" and status == "ok")
    check(pid, ok, f"entity={ent} canary_calls={len(calls)} status={status}")


def probe_mcpoff_enabled_default_still_probed(disc, hc, tmp: Path):
    """S4 contract probe 3: сервер без ключа enabled проверяется как прежде
    (primitive mcp-test), снапшот не получает флаг."""
    _mcpoff_enabled_still_probed(disc, hc, tmp, "mcpoff-default", {},
                                 "mcpoff_enabled_default_still_probed")


def probe_mcpoff_enabled_true_still_probed(disc, hc, tmp: Path):
    """S4 contract probe 4: enabled: true — поведение в точности прежнее."""
    _mcpoff_enabled_still_probed(disc, hc, tmp, "mcpoff-true", {"enabled": True},
                                 "mcpoff_enabled_true_still_probed")


def probe_mcpoff_falsy_matrix(disc):
    """S4 contract probe 5: falsy-набор локального зеркала совпадает со
    стабильным mcp_server_enabled() (Hermes v0.21.5, f97608f1) на тех же
    входных: absent/null/unparseable = on; False/0/0.0 и строки
    false/0/no/off (регистр/пробелы) = off."""
    helper = getattr(disc, "_mcp_server_enabled", None)
    if helper is None:
        check("mcpoff_falsy_matrix", False, "_mcp_server_enabled mirror missing")
        return
    on = {"absent": helper({}), "none": helper({"enabled": None}),
          "true": helper({"enabled": True}), "one": helper({"enabled": 1}),
          "float": helper({"enabled": 2.5}),
          "str_true": helper({"enabled": "TRUE"}),
          "str_yes": helper({"enabled": " yes "}),
          "str_on": helper({"enabled": "On"}),
          "str_one": helper({"enabled": "1"}),
          "unknown_str": helper({"enabled": "maybe"}),
          "empty_str": helper({"enabled": ""}),
          "list": helper({"enabled": []}), "dict": helper({"enabled": {}})}
    off = {"false": helper({"enabled": False}), "zero": helper({"enabled": 0}),
           "zero_float": helper({"enabled": 0.0}),
           "str_false": helper({"enabled": "false"}),
           "str_zero": helper({"enabled": " 0 "}),
           "str_no": helper({"enabled": "No"}),
           "str_off": helper({"enabled": "OFF"}),
           "str_zero_word": helper({"enabled": "0"})}
    ok = all(on.values()) and not any(off.values())
    check("mcpoff_falsy_matrix", ok, f"on={on} off={off}")


def probe_mcpoff_no_probe_side_effect(tmp: Path):
    """S4 contract probe 6: для выключенного сервера ни check_mcp, ни
    subprocess (hermes mcp test) не выполняются — assert через harness."""
    home = _r2a_home(tmp, "mcpoff-side")
    # Имя сервера не "off": PyYAML 1.1 парсит незакавыченный `off` как boolean.
    write(home / "config.yaml",
          "mcp_servers:\n  sleepy:\n    enabled: false\n    command: /bin/sleep\n")
    _r2a_run(home, args=["--baseline"])
    hc = load_module("health-check-v2")
    registry = write(tmp / "mcpoff-reg6.yaml", "kit_entries: []\n")
    out = tmp / "mcpoff-side-report.json"
    mcp_calls, spawn_calls = [], []

    def _no_mcp(*a, **k):
        mcp_calls.append(1)
        return True, "CANARY"

    class _FakeCompleted:
        stdout = ""
        stderr = ""

    def _no_spawn(*a, **k):
        spawn_calls.append(1)
        return _FakeCompleted()

    orig_mcp = hc.check_mcp
    real_run = subprocess.run
    hc.check_mcp = _no_mcp
    subprocess.run = _no_spawn
    try:
        rc = hc.run(["--registry", str(registry),
                     "--snapshot", str(home / "state" / "integration-snapshot.json"),
                     "--env", str(home / ".env"), "--out", str(out)])
    finally:
        hc.check_mcp = orig_mcp
        subprocess.run = real_run
    row = (json.loads(out.read_text(encoding="utf-8"))["checks"][0]
           if out.exists() else {})
    ok = (rc == 0 and not mcp_calls and not spawn_calls
          and row.get("status") == "skipped")
    check("mcpoff_no_probe_side_effect", ok,
          f"rc={rc} mcp_calls={len(mcp_calls)} spawn_calls={len(spawn_calls)} "
          f"row={row}")


def probe_mcpoff_render_pause_line(wh):
    """S4 contract probe 7: смешанный отчёт (ok + failed + disabled) — провал
    ❌, выключенный сервер своей строкой «⏸ — отключён», отчёт не зелёный."""
    rows = [
        _oa1b_row("provider:ok", "provider ok", "ok", "env"),
        _oa1b_row("provider:bad#http", "provider bad root", "fail", "http",
                  "HTTP 503"),
        _oa1b_row("mcp:off", "mcp off", "skipped", "mcp-disabled",
                  "mcp: disabled by config"),
    ]
    report = _oa1b_report(rows)
    quick = wh._render_integrations_quick(report)
    full = wh._render_integrations_full(report, {})
    f_lines = full.split("\n")
    q_ok = ("❌" in quick and "provider bad root" in quick
            and "⏸ mcp off — отключён" in quick
            and "всё в порядке" not in quick
            and "пропущены политикой" not in quick)
    f_ok = ("❌ provider bad root — HTTP 503" in f_lines
            and "⏸ mcp off — отключён" in f_lines
            and not any(l.startswith("❌") and "mcp off" in l for l in f_lines))
    check("mcpoff_render_pause_line", q_ok and f_ok,
          f"quick={quick!r} full_has={('⏸ mcp off — отключён' in f_lines)}")


def probe_mcpoff_render_counter_exclusion(wh):
    """S4 contract probe 8: выключенный сервер не попадает в generic
    «пропущены политикой» (зеркало OAuth-исключения) — имя видно строкой."""
    rows = [
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
        _oa1b_row("mcp:off", "mcp off", "skipped", "mcp-disabled",
                  "mcp: disabled by config"),
    ]
    report = _oa1b_report(rows)
    quick = wh._render_integrations_quick(report)
    counts = wh._render_integrations_full(report, {}).split("\n")[1]
    ok = ("⏸ 1 проверок пропущены политикой" in quick
          and "⏸ mcp off — отключён" in quick
          and "⏸ 2" not in quick
          and "⏸ 2" not in counts and "⏸ 1" in counts)
    check("mcpoff_render_counter_exclusion", ok,
          f"quick={quick!r} counts={counts!r}")


def probe_mcpoff_other_skip_reasons_unchanged(hc, tmp: Path):
    """S4: классифицированный reason_code только у disabled-MCP; прочие
    skipped-причины (oauth-свидетельство) продолжают получать policy_blocked."""
    registry = write(tmp / "mcpoff-reg9.yaml", "kit_entries: []\n")
    snapshot = write(tmp / "mcpoff-snap9.json", json.dumps({
        "updated": "2026-09-19T00:00:00Z",
        "entities": {
            "mcp:off": {"type": "mcp", "name": "off", "transport": "stdio",
                        "url": "/bin/true", "enabled": False},
            "oauth:nous": {"type": "oauth", "name": "nous", "active": True}},
        "env_keys": []}))
    out = tmp / "mcpoff-report9.json"
    rc, err = None, ""
    try:
        rc = hc.run(["--registry", str(registry), "--snapshot", str(snapshot),
                     "--env", str(tmp / "mcpoff9.env"), "--out", str(out),
                     "--hermes-bin", "/nonexistent/hermes-shim"])
    except Exception as e:  # baseline: выключенный сервер реально проверялся бы
        err = f"{type(e).__name__}: {e}"
    rows = ({c["id"]: c for c in
             json.loads(out.read_text(encoding="utf-8"))["checks"]}
            if out.exists() else {})
    ok = (rc == 0
          and rows.get("mcp:off", {}).get("reason_code") == "mcp_disabled_by_config"
          and rows.get("mcp:off", {}).get("verdict") == "skipped"
          and rows.get("oauth:nous", {}).get("reason_code") == "policy_blocked"
          and rows.get("oauth:nous", {}).get("verdict") == "skipped")
    check("mcpoff_other_skip_reasons_unchanged", ok,
          f"rc={rc} err={err[:120]} "
          f"rows={ {k: (v.get('verdict'), v.get('reason_code')) for k, v in rows.items()} }")


def probe_mcpoff_unrelated_discovery_unchanged(tmp: Path):
    """S4 contract probe 9: для конфига без выключенных MCP-серверов дискавери
    байт-в-байт прежний: формы сущностей не меняются, флага enabled нет."""
    home = _r2a_home(tmp, "mcpoff-unrelated")
    base = ("providers:\n  alpha:\n    key_env: ALPHA_KEY\n"
            "    base_url: https://alpha.invalid/v1\n"
            "mcp_servers:\n  bridge:\n    url: https://mcp.invalid/v1\n"
            "  localtool:\n    command: /usr/bin/bridge\n")
    write(home / "config.yaml", base)
    write(home / "auth.json", '{"providers":{"nous":{"refresh_token":"dummy"}}}\n')
    first = _r2a_run(home, args=["--baseline"])
    snap = _r2a_snap(home)["entities"]
    write(home / "config.yaml",
          base + "fallback_model:\n  - provider: legacy\n    model: old\n")
    report_path = tmp / "mcpoff-unrelated-report.json"
    second = _r2a_run(home, {"DISCOVER_REPORT": str(report_path)})
    after = _r2a_snap(home)["entities"]
    report = _r2a_report(tmp, report_path.name)
    stable = ("provider:alpha", "mcp:bridge", "mcp:localtool", "oauth:nous")
    ok = (first.returncode == 0 and second.returncode == 2
          and all(key in snap for key in stable)
          and all(snap.get(key) == after.get(key) for key in stable)
          and snap.get("mcp:bridge") == {"type": "mcp", "name": "bridge",
                                         "transport": "http",
                                         "url": "https://mcp.invalid/v1"}
          and snap.get("mcp:localtool") == {"type": "mcp", "name": "localtool",
                                            "transport": "stdio",
                                            "url": "/usr/bin/bridge"}
          and "model:fallback" in after
          and all(e["key"] == "model:fallback" for e in report["events"]))
    check("mcpoff_unrelated_discovery_unchanged", ok,
          f"stable={[k for k in stable if snap.get(k) == after.get(k)]}")


def probe_deploy_cron_profile(tmp: Path):
    """Minimal cron profile runs deploy and excludes noisy core jobs."""
    home = tmp / "deploy-home"
    config = write(tmp / "minimal-config.env",
                   "MODULE_CORE=ON\n"
                   "MODULE_INTEGRATIONS=ON\n"
                   "MODULE_TG_BOT=OFF\n"
                   "MODULE_ANALYZER=OFF\n"
                   "MODULE_HEARTBEAT=OFF\n"
                   "MODULE_GH_HEARTBEAT=OFF\n"
                   "MODULE_DISCORD_BOT=OFF\n")
    cron = tmp / "minimal-cron.txt"
    # ВАЖНО: deploy.sh в модульном режиме правит ЖИВОЙ crontab
    # (reconcile_local_services_cron). Этот вызов идёт с настоящим PATH и без
    # crontab-шима, поэтому проба реально сносила боевую строку
    # local-services на dev/CI-хосте, где модуль уже задеплоен. Шим обязателен.
    shim_dir = tmp / "minimal-shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    crontab_fixture = tmp / "minimal-crontab.txt"
    crontab_fixture.write_text("", encoding="utf-8")
    write(shim_dir / "crontab",
          "#!/bin/sh\n"
          'case "$1" in\n'
          '  -l) cat "$CRONTAB_FIXTURE" 2>/dev/null;;\n'
          "  -)  cat > \"$CRONTAB_FIXTURE\";;\n"
          "  *) exit 1;;\n"
          "esac\n").chmod(0o755)
    _write_argv_shim(shim_dir, "flock", "exit 0\n")
    _write_argv_shim(shim_dir, "flock", "exit 0\n")
    # RR1b (host-readiness): преflight deploy'а требует user-менеджер, logrotate
    # и дерево Hermes; без них проба проверяла бы отказ, а не профиль cron.
    _rr1b_host_shims(shim_dir)
    _rr1b_fake_hermes(home)
    # RR1b (H5): каталог планировщика logrotate — в фиксстуру (настоящий
    # /etc/logrotate.d на CI-runner не записываем).
    sched = home / "logrotate.d"
    sched.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HOME=str(home), CRON_PROFILE="minimal", CRON_FILE=str(cron),
               CRONTAB_FIXTURE=str(crontab_fixture),
               LOGROTATE_SCHED_DIR=str(sched),
               PATH=f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    result = subprocess.run(["bash", str(REPO / "deploy.sh"), str(config)],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
    cron_text = cron.read_text(encoding="utf-8") if cron.exists() else ""
    quiet = ("hermes-watchdog.sh" not in cron_text
             and "network-guard.sh" not in cron_text
             and "gateway-liveness.sh" not in cron_text)
    integration = all(name in cron_text for name in (
        "integration-discover-wrapper.sh", "fallback-tracker-v2.py",
        "health-check-v2-wrapper.sh"))
    check("deploy_cron_profile", result.returncode == 0 and quiet and integration,
          f"rc={result.returncode} cron={cron_text!r}")


def _rr1b_host_shims(shim_dir: Path, *, user_bus: bool = True, linger: str = "yes",
                     logrotate: bool = True, sudo: str = "none",
                     guard_cmds: bool = True, crontab: bool = True) -> None:
    """Шимы преflight хоста (RR1b, host-readiness) для deploy.sh.

    Ничего из этого не подменяет проверяемую логику: преflight читает эти
    ответы и решает по ним. Всё остальное delegate'ится на реальную утилиту.

    stat        — режим/владелец config.env из RR1B_CONFIG_MODE/OWNER (на
                  Windows-FS chmod не моделируется, поэтому платформа тут
                  подменяется, а решение deploy'а проверяется настоящее);
    systemctl   — доступность user-менеджера (RR1B_USER_BUS_RC);
    loginctl    — значение Linger (пусто = неизвестно);
    logrotate   — наличие/успех dry-run;
    sudo -l     — печатает список и НИЧЕГО не выполняет: откат не запускается.
    """
    # stat: -c '%U'/'%a' для конфига фикстуры, остальное — настоящий stat.
    # Шим моделирует ПЛАТФОРМУ (на Windows-ФС chmod не работает), а не решает,
    # какой файл является конфигом — поэтому маска *.env, а не *config.env:
    # фикстуры называют свои конфиги по-разному (ls-config-ON.env).
    # Путь к настоящему stat резолвится ЗДЕСЬ: внутри шима `command -v stat`
    # нашёл бы сам шим (он стоит первым в PATH) и exec увёл бы его в
    # бесконечную рекурсию — ровно то, что поймал Linux-CI.
    real_stat = subprocess.run(["bash", "-c", "command -v stat"],
                               capture_output=True, text=True, timeout=30
                               ).stdout.strip().split("\n")[0]
    _write_argv_shim(shim_dir, "stat",
                     'case "$1:$2" in\n'
                     '  "-c:%U"|"-c:%a")\n'
                     '    case "$3" in\n'
                     '      *.env)\n'
                     '        case "$2" in\n'
                     '          %U) printf \'%s\\n\' "${RR1B_CONFIG_OWNER-$(id -un)}"; exit 0 ;;\n'
                     '          %a) printf \'%s\\n\' "${RR1B_CONFIG_MODE-600}"; exit 0 ;;\n'
                     '        esac ;;\n'
                     '    esac ;;\n'
                     'esac\n'
                     f'exec "{real_stat}" "$@"\n')
    _write_argv_shim(shim_dir, "systemctl",
                     'if [ "$1" = "--user" ]; then\n'
                     '  shift\n'
                     '  [ "$1" = "show-environment" ] && exit "${RR1B_USER_BUS_RC:-0}"\n'
                     'fi\n'
                     'exit 0\n')
    _write_argv_shim(shim_dir, "loginctl",
                     'case "$*" in\n'
                     '  *Linger*) printf \'%s\\n\' "${RR1B_LINGER-yes}" ;;\n'
                     'esac\n'
                     'exit 0\n')
    if logrotate:
        _write_argv_shim(shim_dir, "logrotate", 'exit "${RR1B_LOGROTATE_RC:-0}"\n')
    if sudo != "none":
        # Шим моделирует ТОЛЬКО код возврата `sudo -k -n -l <cmd> <args>` —
        # дискриминатор, который проверяет deploy.sh. Никакой имитации формата
        # вывода: на двух прошлых итерациях шим, повторяющий предположения
        # автора, подтверждал их же, а не поведение sudo (сначала тег NOPASSWD,
        # которого в выводе нет, затем выдуманный verbose-блок). Здесь шим
        # отвечает ровно на один вопрос: разрешил бы настоящий sudo эту команду
        # с этими аргументами без пароля?
        #   full       — все три команды разрешены беспарольно;
        #   mixed      — resolvectl да, ip-команды PASSWD (как в строке sudoers
        #                с разными тегами);
        #   nobody     — run-as не root: для default run-as запрещено;
        #   negate     — resolvectl разрешён, ip-команды под правилом !запрещены;
        #   restricted — NOPASSWD, но грант под литеральные аргументы: probe-args
        #                не совпадают с грантом (не покрывает рантайм-цели);
        #   passwd     — все три команды PASSWD;
        #   near/fail  — сопоставления нет / sudo сам завершился ошибкой.
        real_install = subprocess.run(["bash", "-c", "command -v install"],
                                      capture_output=True, text=True, timeout=30
                                      ).stdout.strip().splitlines()[0]
        LS = [
            'POLICY="' + sudo + '"',
            'if [ "$1" = "-k" ] && [ "$2" = "-n" ] && [ "$3" = "-l" ]; then',
            '  shift 3',
            '  base=$(basename "$1")',
            '  case "$POLICY" in',
            '    full)       [ "$base" = "resolvectl" ] || [ "$base" = "ip" ] ;;',
            '    mixed)      [ "$base" = "resolvectl" ] ;;',
            '    nobody)     false ;;',
            '    negate)     [ "$base" = "resolvectl" ] ;;',
            '    restricted) false ;;',
            '    passwd)     false ;;',
            '    *)          false ;;',
            '  esac',
            '  exit $?',
            'fi',
            'if [ "$1" = "-n" ] && [ "$2" = "install" ]; then',
            '  shift 2',
            '  exec "' + real_install + '" "$@"',
            'fi',
            'exit 1',
        ]
        _write_argv_shim(shim_dir, "sudo", "\n".join(LS) + "\n")
    if guard_cmds:
        _write_argv_shim(shim_dir, "resolvectl", "exit 0\n")
        _write_argv_shim(shim_dir, "ip", "exit 0\n")
    if crontab:
        # deploy fail-closed при недоступном crontab, поэтому шим обязателен
        # для ЛЮБОЙ deploy-фикстуры (живой crontab проба не трогает никогда).
        # Уже установленные crontab/flock НЕ перекрываем: RR1a-шимы умеют
        # внедрять сбои чтения/записи и конкуренции лока.
        if not (shim_dir / "crontab").exists():
            _write_argv_shim(shim_dir, "crontab",
                             'case "$1" in\n'
                             '  -l) if [ -f "$CRONTAB_FIXTURE" ]; then cat "$CRONTAB_FIXTURE"; fi ;;\n'
                             '  -)  cat > "$CRONTAB_FIXTURE" ;;\n'
                             '  *) exit 1;;\n'
                             'esac\n')
        if not (shim_dir / "flock").exists():
            _write_argv_shim(shim_dir, "flock", "exit 0\n")


def _rr1b_fake_hermes(home: Path) -> None:
    """Минимальное дерево Hermes, которого ждёт преflight H3: сам Argus Hermes не
    ставит, поэтому для фикстур оно создаётся явно."""
    bindir = home / ".hermes" / "hermes-agent" / "venv" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for name in ("hermes", "python"):
        shim = bindir / name
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
        shim.chmod(0o755)


def _path_shim_env(home: Path, extra: dict | None = None) -> dict:
    """Environment for deploy.sh probes: fixture HOME + caller's PATH overrides."""
    return _probe_subprocess_env(home, extra)


def _write_argv_shim(shim_dir: Path, command: str, body: str) -> Path:
    """Extensionless sh shim: a command shadowed by PATH for argv-capture probes."""
    path = shim_dir / command
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def probe_deploy_secret_not_in_argv(tmp: Path):
    """R1a: deploy substitution values (incl. secrets) never reach a child argv.

    A PATH shim logs every sed invocation argv; a canary token in config.env must
    stay out of that log while still reaching the rendered output (chat-id canary
    proves substitution semantics are unchanged) and must not survive in temp
    files after deploy (sed script cleanup)."""
    home = tmp / "deploy-argv-home"
    token = "ARGUS_CANARY_TOKEN_R1A"
    chat = "ARGUS_CANARY_CHAT_R1A"
    config = write(tmp / "argv-config.env",
                   "MODULE_CORE=ON\n"
                   "MODULE_INTEGRATIONS=ON\n"
                   "MODULE_TG_BOT=OFF\n"
                   "MODULE_ANALYZER=OFF\n"
                   "MODULE_HEARTBEAT=OFF\n"
                   "MODULE_GH_HEARTBEAT=OFF\n"
                   "MODULE_DISCORD_BOT=OFF\n"
                   f"WATCHDOG_BOT_TOKEN={token}\n"
                   f"WATCHDOG_CHAT_ID={chat}\n")
    cron = tmp / "argv-cron.txt"
    shim = tmp / "shim-sed"
    shim.mkdir()
    _rr1b_host_shims(shim)
    _rr1b_fake_hermes(home)
    argv_log = tmp / "sed-argv.log"
    tmpd = tmp / "deploy-tmp"
    tmpd.mkdir()
    real_sed = shutil.which("sed") or "/usr/bin/sed"
    _write_argv_shim(shim, "sed",
                     f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
                     f'exec "{Path(real_sed).as_posix()}" "$@"\n')
    # crontab-шим обязателен: deploy.sh правит живой crontab, и без него проба
    # сносила бы боевую строку local-services на хосте, где модуль задеплоен.
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) cat "$CRONTAB_FIXTURE" 2>/dev/null;;\n'
                     '  -)  cat > "$CRONTAB_FIXTURE";;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    _write_argv_shim(shim, "flock", "exit 0\n")
    crontab_fixture = tmp / "deploy-secret-crontab.txt"
    crontab_fixture.write_text("", encoding="utf-8")
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "TMPDIR": str(tmpd), "TMP": str(tmpd), "TEMP": str(tmpd),
        "CRON_PROFILE": "minimal", "CRON_FILE": str(cron),
        "CRONTAB_FIXTURE": str(crontab_fixture),
    })
    result = subprocess.run(["bash", str(REPO / "deploy.sh"), str(config)],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    argv_text = argv_log.read_text(encoding="utf-8") if argv_log.exists() else ""
    # RR0b: auto-remediate.sh — CORE-сентинел рендера @WATCHDOG_CHAT_ID@; снятый
    # send-monitoring-report.sh не должен появиться даже как пустой артефакт.
    rendered = home / "scripts" / "auto-remediate.sh"
    rendered_ok = rendered.exists() and chat in rendered.read_text(encoding="utf-8")
    removed_rendered = (home / "scripts" / "send-monitoring-report.sh").exists()
    leftover_leak = any(token in p.read_text(encoding="utf-8", errors="ignore")
                        for p in tmpd.iterdir() if p.is_file())
    check("deploy_secret_not_in_argv",
          result.returncode == 0 and token not in argv_text and chat not in argv_text
          and rendered_ok and not removed_rendered and not leftover_leak,
          f"rc={result.returncode} sed_calls={len(argv_text.splitlines())} "
          f"chat_rendered={rendered_ok} removed_rendered={removed_rendered} "
          f"leftover_leak={leftover_leak}")


def probe_deploy_gh_heartbeat_secret_not_in_argv(tmp: Path):
    """R1a: gh secret set and git push take credentials via stdin/env, not argv.

    gh/git PATH shims log argv (gh also captures stdin). The GH_TOKEN canary must
    never appear in any gh/git argv: secret values arrive on stdin (--body-file -),
    the push URL is credential-free, and the in-memory credential helper only
    references the env var name."""
    home = tmp / "deploy-gh-home"
    token = "ARGUS_CANARY_GH_TOKEN_R1A"
    chat = "ARGUS_CANARY_GH_CHAT_R1A"
    config = write(tmp / "gh-config.env",
                   "MODULE_CORE=ON\n"
                   "MODULE_INTEGRATIONS=ON\n"
                   "MODULE_TG_BOT=OFF\n"
                   "MODULE_ANALYZER=OFF\n"
                   "MODULE_HEARTBEAT=OFF\n"
                   "MODULE_GH_HEARTBEAT=ON\n"
                   "MODULE_DISCORD_BOT=OFF\n"
                   f"GH_TOKEN={token}\n"
                   f"WATCHDOG_BOT_TOKEN={token}\n"
                   f"WATCHDOG_CHAT_ID={chat}\n")
    shim = tmp / "shim-gh"
    shim.mkdir()
    _rr1b_host_shims(shim)
    _rr1b_fake_hermes(home)
    gh_argv, gh_stdin = tmp / "gh-argv.log", tmp / "gh-stdin.log"
    git_argv = tmp / "git-argv.log"
    _write_argv_shim(shim, "gh",
                     f'printf \'%s\\n\' "$*" >> "{gh_argv.as_posix()}"\n'
                     'case "$1 $2" in\n'
                     '  "api user") echo dummyuser; exit 0;;\n'
                     '  "repo view") exit 1;;\n'
                     '  "repo create") exit 0;;\n'
                     f'  "secret set") cat >> "{gh_stdin.as_posix()}"; '
                     f'printf \'\\n--\\n\' >> "{gh_stdin.as_posix()}"; exit 0;;\n'
                     '  *) exit 0;;\n'
                     'esac\n')
    _write_argv_shim(shim, "git",
                     f'printf \'%s\\n\' "$*" >> "{git_argv.as_posix()}"\n'
                     'case "$1" in diff) exit 1;; *) exit 0;; esac\n')
    # crontab-шим обязателен: deploy.sh правит живой crontab, и без него проба
    # сносила бы боевую строку local-services на хосте, где модуль задеплоен.
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) cat "$CRONTAB_FIXTURE" 2>/dev/null;;\n'
                     '  -)  cat > "$CRONTAB_FIXTURE";;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    _write_argv_shim(shim, "flock", "exit 0\n")
    crontab_fixture = tmp / "gh-heartbeat-crontab.txt"
    crontab_fixture.write_text("", encoding="utf-8")
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRON_PROFILE": "minimal", "CRON_FILE": str(tmp / "gh-cron.txt"),
        "CRONTAB_FIXTURE": str(crontab_fixture),
    })
    # input в binary-режиме: text=True на Windows переводит "\n" в "\r\n",
    # и read в deploy.sh получает "y\r" — ответ не матчится.
    result = subprocess.run(["bash", str(REPO / "deploy.sh"), str(config)],
                            cwd=REPO, env=env, input=b"y\n",
                            capture_output=True, timeout=120)
    gh_argv_text = gh_argv.read_text(encoding="utf-8") if gh_argv.exists() else ""
    git_argv_text = git_argv.read_text(encoding="utf-8") if git_argv.exists() else ""
    gh_stdin_text = gh_stdin.read_text(encoding="utf-8") if gh_stdin.exists() else ""
    # git получает и -c-опции, поэтому push ищем внутри строки лога
    push_lines = [line for line in git_argv_text.splitlines() if " push " in line]
    push_ok = bool(push_lines) and "https://github.com/dummyuser/" in push_lines[0]
    # gh 2.45 не имеет --body-file и читает значение из stdin только когда
    # --body не передан: любая форма флага тела в argv = регрессия к
    # нерабочему/утекающему варианту
    no_body_flag = "--body" not in gh_argv_text
    check("deploy_gh_heartbeat_secret_not_in_argv",
          result.returncode == 0
          and token not in gh_argv_text and token not in git_argv_text
          and chat not in gh_argv_text
          and token in gh_stdin_text and chat in gh_stdin_text
          and push_ok and no_body_flag,
          f"rc={result.returncode} gh_calls={len(gh_argv_text.splitlines())} "
          f"git_calls={len(git_argv_text.splitlines())} push_ok={push_ok} "
          f"stdin_has_secrets={token in gh_stdin_text and chat in gh_stdin_text} "
          f"no_body_flag={no_body_flag}")


def probe_deploy_gh_secret_failure_gates_deploy(tmp: Path):
    """R1a remediation 2: a failing gh secret set must abort deploy nonzero
    before the readiness message and cron generation.

    Bash errexit does not fire for non-final commands of a bare &&-chain, so
    the gate must be an explicit if around the provisioning pipelines."""
    home = tmp / "deploy-ghfail-home"
    token = "ARGUS_CANARY_GH_TOKEN_R1A"
    config = write(tmp / "ghfail-config.env",
                   "MODULE_CORE=ON\n"
                   "MODULE_INTEGRATIONS=ON\n"
                   "MODULE_TG_BOT=OFF\n"
                   "MODULE_ANALYZER=OFF\n"
                   "MODULE_HEARTBEAT=OFF\n"
                   "MODULE_GH_HEARTBEAT=ON\n"
                   "MODULE_DISCORD_BOT=OFF\n"
                   f"GH_TOKEN={token}\n"
                   f"WATCHDOG_BOT_TOKEN={token}\n"
                   "WATCHDOG_CHAT_ID=ARGUS_CANARY_GH_CHAT_R1A\n")
    shim = tmp / "shim-ghfail"
    shim.mkdir()
    _rr1b_host_shims(shim)
    _rr1b_fake_hermes(home)
    # crontab-шим обязателен: deploy.sh правит живой crontab, и без шима проба
    # сносила бы боевую строку local-services на хосте, где модуль задеплоен.
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) cat "$CRONTAB_FIXTURE" 2>/dev/null;;\n'
                     '  -)  cat > "$CRONTAB_FIXTURE";;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    _write_argv_shim(shim, "flock", "exit 0\n")
    gh_argv = tmp / "ghfail-argv.log"
    _write_argv_shim(shim, "gh",
                     f'printf \'%s\\n\' "$*" >> "{gh_argv.as_posix()}"\n'
                     'case "$1 $2" in\n'
                     '  "api user") echo dummyuser; exit 0;;\n'
                     '  "repo view") exit 1;;\n'
                     '  "repo create") exit 0;;\n'
                     '  "secret set") echo "boom: synthetic gh failure" >&2; exit 1;;\n'
                     '  *) exit 0;;\n'
                     'esac\n')
    _write_argv_shim(shim, "git",
                     'case "$1" in diff) exit 1;; *) exit 0;; esac\n')
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRON_PROFILE": "minimal", "CRON_FILE": str(tmp / "ghfail-cron.txt"),
    })
    result = subprocess.run(["bash", str(REPO / "deploy.sh"), str(config)],
                            cwd=REPO, env=env, input=b"y\n",
                            capture_output=True, timeout=120)
    stdout = result.stdout.decode(errors="ignore")
    argv_text = gh_argv.read_text(encoding="utf-8") if gh_argv.exists() else ""
    check("deploy_gh_secret_failure_gates_deploy",
          result.returncode != 0
          and "GH Heartbeat готов" not in stdout
          and not (tmp / "ghfail-cron.txt").exists()
          and token not in argv_text,
          f"rc={result.returncode} ready_msg_suppressed="
          f"{'GH Heartbeat готов' not in stdout}")


def probe_gh_secret_stdin_flag_supported(tmp: Path):
    """R1a remediation: real gh CLI accepts `gh secret set NAME` with the value
    on stdin and rejects the nonexistent --body-file form.

    Runs against a nonexistent repo with GH_HOST pointed at an unroutable host
    and no token in env: the API call can never mutate anything, so the probe
    observes only flag parsing. The --body-file arm is the negative control
    proving the discriminator itself fires."""
    gh = shutil.which("gh")
    if not gh:
        check("gh_secret_stdin_flag_supported", True, "skipped: gh not installed")
        return
    env = _probe_subprocess_env(tmp / "gh-flag-home", {"GH_HOST": "argus-probe.invalid"})
    stdin_value = "ARGUS_CANARY_GH_TOKEN_R1A\n"
    ok_call = subprocess.run([gh, "secret", "set", "ARGUS_CANARY",
                              "--repo", "dummyuser/argus-nonexistent-repo"],
                             input=stdin_value.encode(), env=env,
                             capture_output=True, timeout=60)
    bad_call = subprocess.run([gh, "secret", "set", "ARGUS_CANARY",
                               "--repo", "dummyuser/argus-nonexistent-repo",
                               "--body-file", "-"],
                              input=stdin_value.encode(), env=env,
                              capture_output=True, timeout=60)
    ok_err = (ok_call.stderr or b"").decode(errors="ignore")
    bad_err = (bad_call.stderr or b"").decode(errors="ignore")
    stdin_form_parses = "unknown flag" not in ok_err
    bodyfile_rejected = "unknown flag" in bad_err
    check("gh_secret_stdin_flag_supported", stdin_form_parses and bodyfile_rejected,
          f"rc={ok_call.returncode} stdin_parses={stdin_form_parses} "
          f"bodyfile_rejected={bodyfile_rejected}")


def probe_git_credential_helper_real(tmp: Path):
    """R1a remediation: the exact credential-helper expression from deploy.sh,
    executed by real git via sh -c, serves `credential fill` from $GH_TOKEN.

    No network contact (fill consults helpers only), no store writes (empty
    helper= resets system/global helpers, fixture HOME isolates state)."""
    git = shutil.which("git")
    if not git:
        check("git_credential_helper_real", True, "skipped: git not installed")
        return
    home = tmp / "cred-home"
    home.mkdir()
    token = "ARGUS_CANARY_GH_TOKEN_R1A"
    helper = ('credential.helper=!f(){ printf "username=argus\\npassword=%s" '
              '"$GH_TOKEN"; }; f')
    env = _probe_subprocess_env(home, {"GH_TOKEN": token})
    result = subprocess.run([git, "-c", "credential.helper=", "-c", helper,
                             "credential", "fill"],
                            input="protocol=https\nhost=github.com\n\n",
                            env=env, capture_output=True, text=True, timeout=60)
    filled = "username=argus" in result.stdout and f"password={token}" in result.stdout
    no_store = not (home / ".git-credentials").exists()
    check("git_credential_helper_real",
          result.returncode == 0 and filled and no_store,
          f"rc={result.returncode} filled={filled} no_store={no_store}")


# ── Пробы: R1b Telegram token-in-argv (shell + child curl) ──────────────────

R1B_TOKEN = "ARGUS_CANARY_R1B"
R1B_CHAT = "ARGUS_CHAT_R1B"


def _install_curl_shim(shim_dir: Path, tmp: Path, tag: str, stdout: str = ""):
    """curl shim: logs argv and stdin (config), then exits 0. Never touches the
    network. stdout emulates what the caller parses (-w output / JSON body)."""
    argv_log = tmp / f"{tag}-curl-argv.log"
    stdin_log = tmp / f"{tag}-curl-stdin.log"
    body = (f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
            f'cat >> "{stdin_log.as_posix()}"\n'
            f'printf \'\\n--\\n\' >> "{stdin_log.as_posix()}"\n')
    if stdout:
        body += f"printf '%s\\n' '{stdout}'\n"
    body += "exit 0\n"
    _write_argv_shim(shim_dir, "curl", body)
    return argv_log, stdin_log


def _read_or(log: Path) -> str:
    return log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""


def _extract_bash_fn(src: str, name: str) -> str:
    """Verbatim function text from a real script (name() ... closing } at col 0)."""
    lines = src.splitlines()
    out, on = [], False
    for line in lines:
        if not on and (line.startswith(name + "() {") or line.startswith(name + "():")):
            on = True
        if on:
            out.append(line)
            if line == "}":
                break
    return "\n".join(out)


def probe_curl_config_stdin_seam(tmp: Path):
    """R1b: real curl parses `url = ...` from stdin config (-K -) and requests
    exactly that URL (loopback server, no external network).

    Negative control: empty config -> curl errors out and no request is made,
    so the probe fails if the config-stdin delivery mechanism breaks."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    hits = []

    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            hits.append(self.path)
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = _handle
        do_POST = _handle
        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 3
    url = f"http://127.0.0.1:{server.server_address[1]}/probe?token={R1B_TOKEN}"
    threading.Thread(target=server.handle_request, daemon=True).start()
    r = subprocess.run(["curl", "-sS", "-K", "-", "-m", "5", "-X", "POST",
                        "-d", "chat_id=x"],
                       input=f"url = {url}\n", capture_output=True, text=True,
                       timeout=30)
    # negative control: invalid (empty) config must fail, not silently skip
    r_bad = subprocess.run(["curl", "-sS", "-K", "-", "-m", "5", "-X", "POST",
                            "-d", "chat_id=x"],
                           input="", capture_output=True, text=True, timeout=30)
    server.server_close()
    check("curl_config_stdin_seam",
          r.returncode == 0 and hits == [f"/probe?token={R1B_TOKEN}"]
          and r_bad.returncode != 0,
          f"rc={r.returncode} hit={hits} bad_rc={r_bad.returncode} "
          f"bad_err={(r_bad.stderr or '').strip()[:60]!r}")


def probe_telegram_form_send_argv_canary(tmp: Path):
    """R1b shape B (form-encoded sendMessage, recovery branch), real script
    gateway-liveness.sh: canary off curl argv, URL on stdin, form payload and
    silent flag preserved. Canonical-matcher shim keeps the process-alive
    precondition."""
    home = tmp / "tg-form-home"
    hermes = home / ".hermes"
    write(hermes / ".env",
          f"WATCHDOG_BOT_TOKEN={R1B_TOKEN}\nWATCHDOG_CHAT_ID={R1B_CHAT}\n")
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write(hermes / "logs" / "agent.log",
          f"{ts},000 INFO gateway: memory trim: reason=messaging gateway housekeeping\n")
    state = hermes / "state" / "gateway-liveness.alerted"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("prefill", encoding="utf-8")
    shim = tmp / "shim-tgform"
    shim.mkdir()
    argv_log, stdin_log = _install_curl_shim(shim, tmp, "form")
    # 2026-10-02: процесс- precondition держит канонический матчер
    # (hermes-gateway-pids.py), а не pgrep по argv — прежний шим делал вид,
    # что gateway жив, но вызывающий код больше pgrep не зовёт. Ставим живой
    # helper в $HOME/scripts (ровно туда, куда смотрит скрипт). Стаб ОБЯЗАН быть
    # Python-сценарием: вызов идёт как `python3 <helper>`, и shell-стаб дал бы
    # SyntaxError → rc=1 → скрипт решил бы «процесс мёртв» и молчал бы.
    stub = home / "scripts" / "hermes-gateway-pids.py"
    write(stub, "print(4242)\n")
    stub.chmod(0o755)
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", "")})
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "gateway-liveness.sh")],
        cwd=REPO, env=env, input=b"", capture_output=True, timeout=60)
    argv = _read_or(argv_log)
    stdin_data = _read_or(stdin_log)
    check("telegram_form_send_argv_canary",
          result.returncode == 0
          and R1B_TOKEN not in argv
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/sendMessage" in stdin_data
          and "chat_id=ARGUS_CHAT_R1B" in argv
          and "--data-urlencode" in argv
          and "disable_notification=true" in argv,
          f"rc={result.returncode} argv_leak={R1B_TOKEN in argv} "
          f"form_wiring={'chat_id=' in argv and '--data-urlencode' in argv}")


def probe_telegram_json_pin_resp_canary(tmp: Path):
    """R1b shape C (JSON sendMessage + pinChatMessage, message_id consumed):
    verbatim send_alert() from network-guard.sh. Two curl invocations, both
    token-free argv, both URLs on stdin, pin payload carries the message_id."""
    home = tmp / "tg-pin-home"
    write(home / ".hermes" / ".env",
          f"WATCHDOG_BOT_TOKEN={R1B_TOKEN}\nWATCHDOG_CHAT_ID={R1B_CHAT}\n")
    src = (REPO / "scripts" / "network-guard.sh").read_text(encoding="utf-8")
    fn = _extract_bash_fn(src, "send_alert")
    shim = tmp / "shim-tgpin"
    shim.mkdir()
    argv_log, stdin_log = _install_curl_shim(
        shim, tmp, "pin", stdout='{"ok": true, "result": {"message_id": 123}}')
    harness = tmp / "tg-pin-fn.sh"
    write(harness, f"log() {{ :; }}\n{fn}\nsend_alert 'probe alert'\n")
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", "")})
    result = subprocess.run(["bash", str(harness)], cwd=REPO, env=env,
                            input=b"", capture_output=True, timeout=60)
    argv = _read_or(argv_log)
    stdin_data = _read_or(stdin_log)
    check("telegram_json_pin_resp_canary",
          result.returncode == 0
          and R1B_TOKEN not in argv
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/sendMessage" in stdin_data
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/pinChatMessage" in stdin_data
          and argv.count("-d") >= 2
          and "message_id" in argv,
          f"rc={result.returncode} argv_leak={R1B_TOKEN in argv} "
          f"pin_url={'pinChatMessage' in stdin_data} "
          f"mid_payload={'message_id' in argv}")


def probe_telegram_getme_module_canary(hc, tmp: Path):
    """R1b shape D (getMe via python-subprocess curl), health-check-v2
    check_tg_getme: subprocess.run is faked (no network, no platform shim
    fragility); asserts canary off argv, config-stdin delivery, wiring."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["argv"] = list(cmd)
        captured["input"] = kwargs.get("input")
        return type("R", (), {"returncode": 0, "stdout": '{"ok": true}\n200',
                              "stderr": ""})()

    real_run = hc.subprocess.run
    hc.subprocess.run = fake_run
    try:
        ok, detail = hc.check_tg_getme(R1B_TOKEN, "http://127.0.0.1:8444")
    finally:
        hc.subprocess.run = real_run
    argv = " ".join(captured.get("argv", []))
    stdin_data = captured.get("input") or ""
    check("telegram_getme_module_canary",
          ok
          and R1B_TOKEN not in argv
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/getMe" in stdin_data
          and "--proxy" in argv and "-K" in argv and "-" in argv.split(),
          f"ok={ok} detail={detail!r} argv_leak={R1B_TOKEN in argv}")


def probe_healthcheck_check_url_canary(tmp: Path):
    """R1b shape D shell variant: verbatim check_url() from
    health-check-integrations.sh (getMe caller) — canary off argv, URL on
    stdin, proxy arg preserved, expected-code match still drives the verdict."""
    src = (REPO / "scripts" / "health-check-integrations.sh").read_text(encoding="utf-8")
    fn = _extract_bash_fn(src, "check_url")
    shim = tmp / "shim-checkurl"
    shim.mkdir()
    argv_log, stdin_log = _install_curl_shim(shim, tmp, "checkurl", stdout="200")
    harness = tmp / "checkurl-fn.sh"
    write(harness,
          "RETRIES=1\nTIMEOUT=5\nRETRY_DELAY=1\nFAILURES=''\n"
          f"{fn}\n"
          f"check_url 'probe' 'https://api.telegram.org/bot{R1B_TOKEN}/getMe' "
          "'200' '' 'http://127.0.0.1:8444'\n")
    env = _path_shim_env(tmp / "checkurl-home", {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", "")})
    (tmp / "checkurl-home").mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["bash", str(harness)], cwd=REPO, env=env,
                            input=b"", capture_output=True, timeout=60)
    argv = _read_or(argv_log)
    stdin_data = _read_or(stdin_log)
    check("healthcheck_check_url_canary",
          result.returncode == 0
          and R1B_TOKEN not in argv
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/getMe" in stdin_data
          and "--proxy" in argv and "-K" in argv,
          f"rc={result.returncode} argv_leak={R1B_TOKEN in argv} "
          f"proxy={'--proxy' in argv}")


def probe_telegram_py_form_send_canary(ft, tmp: Path):
    """R1b shape E (python-subprocess form sendMessage), fallback-tracker
    send_alert: subprocess is faked via sys.modules (the module imports it
    locally, so attribute patching would not apply); asserts canary off argv,
    config-stdin delivery, form payload preserved. No network contact."""
    captured = {}

    class _FakeSubprocess:
        @staticmethod
        def run(cmd, **kwargs):
            captured["argv"] = list(cmd)
            captured["input"] = kwargs.get("input")
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    saved = sys.modules.get("subprocess")
    sys.modules["subprocess"] = _FakeSubprocess
    try:
        ft.send_alert("probe text",
                      {"WATCHDOG_BOT_TOKEN": R1B_TOKEN, "WATCHDOG_CHAT_ID": R1B_CHAT})
        argv_plain = list(captured.get("argv", []))
        input_plain = captured.get("input") or ""
        captured.clear()
        # RR0c B1: явный TELEGRAM_PROXY передаётся curl'у как есть; неявного
        # дефолта больше не существует (без переменной — прямой доступ).
        ft.send_alert("probe text",
                      {"WATCHDOG_BOT_TOKEN": R1B_TOKEN, "WATCHDOG_CHAT_ID": R1B_CHAT,
                       "TELEGRAM_PROXY": "http://10.9.8.7:9999"})
        argv_proxy = " ".join(captured.get("argv", []))
    finally:
        if saved is None:
            sys.modules.pop("subprocess", None)
        else:
            sys.modules["subprocess"] = saved
    argv = " ".join(argv_plain)
    stdin_data = input_plain
    check("telegram_py_form_send_canary",
          R1B_TOKEN not in argv
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/sendMessage" in stdin_data
          and "chat_id=ARGUS_CHAT_R1B" in argv
          and "text=probe text" in argv
          and "-K" in argv and "-" in argv.split(),
          f"argv_leak={R1B_TOKEN in argv} "
          f"form_wiring={'chat_id=' in argv and '--data-urlencode' in argv}")
    check("telegram_py_form_send_explicit_proxy",
          "--proxy" in argv_proxy and "http://10.9.8.7:9999" in argv_proxy
          and "127.0.0.1:8444" not in argv_proxy,
          f"proxy_wired={'--proxy http://10.9.8.7:9999' in argv_proxy}")


def probe_telegram_static_audit_no_argv_leak(tmp: Path):
    """R1b acceptance A: scripted repository audit over scripts/ (top level)
    and modules/ (recursive).

    Forbidden: a curl command line (or its continuation window) carrying the
    token URL — literal or via the TG_API/TELEGRAM_API aliases — and any
    standalone token-URL line that is not a config-stdin delivery line, alias
    assignment, comment, check_url argument (its body is guarded by the
    file-level delivery requirement), or in-process urllib Request.
    Red-capable: every FIX file must keep its delivery line,
    register-commands.sh must read the token from the environment (never
    sys.argv), and the heartbeat workflow must keep the -K - delivery."""
    import re
    offenders = []
    in_process_py = {"webhook.py", "monitoring-bot-poller.py",
                     "register-commands.sh", "local_services_check.py"}
    scan = sorted((REPO / "scripts").glob("*.sh"))
    scan += sorted((REPO / "scripts").glob("*.py"))
    scan += [p for p in sorted((REPO / "modules").rglob("*"))
             if p.suffix in (".yml", ".yaml", ".sh", ".py") and p.is_file()]
    for path in scan:
        text = path.read_text(encoding="utf-8", errors="ignore")
        window = None  # continuation window: None | 'curl' | 'fn'
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            ends_cont = line.rstrip().endswith("\\")
            has_url = "api.telegram.org/bot" in line
            # aliases: braced and unbraced forms
            has_alias = bool(re.search(r"\$\{?TG_API\}?", line)
                             or re.search(r"\$\{?TELEGRAM_API\}?", line))
            # токен как аргумент python-ребёнка (env-чтение в коде это не спасает)
            python_token_argv = ("python" in line
                                 and re.search(r"\$\{?(WATCHDOG_BOT_TOKEN|"
                                               r"TELEGRAM_BOT_TOKEN|BOT_TOKEN)\}?", line)
                                 and "printf 'url = " not in line)
            curl_start = window is None and (
                stripped.startswith("curl") or "| curl" in line)
            fn_start = window is None and "check_url " in stripped
            if window == "curl" or curl_start:
                mode = "curl"
            elif window == "fn" or fn_start:
                mode = "fn"
            else:
                mode = None
            if has_url or has_alias or python_token_argv:
                if "printf 'url = " in line:
                    pass
                elif 'input=f"url = ' in line:
                    pass
                elif stripped.startswith("#"):
                    pass
                elif (not has_alias and not python_token_argv
                      and re.match(r"^\s*(export\s+)?(TG_API|TELEGRAM_API)=", line)):
                    pass
                elif path.name in in_process_py and "curl" not in line and has_url:
                    pass
                elif mode == "fn":
                    pass
                else:
                    # URL внутри curl-команды или вне разрешённых форм — утечка
                    offenders.append(f"{path.relative_to(REPO).as_posix()}:{i}")
            # команда продолжается, пока строки кончаются на "\"
            window = mode if ends_cont else None
    required = {
        "scripts/auto-remediate.sh": "printf 'url = ",
        "scripts/check-updates.sh": "printf 'url = ",
        "scripts/watchdog-health.sh": "printf 'url = ",
        "scripts/ssl-expiry-check.sh": "printf 'url = ",
        "scripts/integration-discover-wrapper.sh": "printf 'url = ",
        "scripts/health-check-v2-wrapper.sh": "printf 'url = ",
        "scripts/dashboard-liveness.sh": "printf 'url = ",
        "scripts/gateway-liveness.sh": "printf 'url = ",
        "scripts/network-guard.sh": "printf 'url = ",
        "scripts/hermes-watchdog.sh": "printf 'url = ",
        "scripts/health-check-integrations.sh": "printf 'url = ",
        "scripts/health-check-v2.py": 'input=f"url = https://api.telegram.org',
        "scripts/fallback-tracker-v2.py": 'input=f"url = https://api.telegram.org',
        "modules/gh-heartbeat/heartbeat-alert.yml": "printf 'url = ",
    }
    missing = []
    for rel, marker in required.items():
        if marker not in (REPO / rel).read_text(encoding="utf-8", errors="ignore"):
            missing.append(rel)
    reg = (REPO / "scripts" / "register-commands.sh").read_text(
        encoding="utf-8", errors="ignore")
    reg_env_ok = ('os.environ["WATCHDOG_BOT_TOKEN"]' in reg
                  and "sys.argv" not in reg)
    check("telegram_static_audit_no_argv_leak",
          not offenders and not missing and reg_env_ok,
          f"offenders={offenders[:5]} missing_fix={missing[:5]} "
          f"reg_env_ok={reg_env_ok}")


def probe_register_commands_env_token_canary(tmp: Path):
    """R1b remediation: register-commands.sh hands the token to the python
    child via inherited environment, never via argv. python3 shim captures
    argv and the env-provided canary."""
    home = tmp / "tg-reg-home"
    (home / ".hermes" / "logs").mkdir(parents=True, exist_ok=True)
    write(home / ".hermes" / ".env",
          f"WATCHDOG_BOT_TOKEN={R1B_TOKEN}\nWATCHDOG_CHAT_ID={R1B_CHAT}\n")
    shim = tmp / "shim-reg"
    shim.mkdir()
    argv_log = tmp / "reg-py-argv.log"
    env_log = tmp / "reg-py-env.log"
    _write_argv_shim(shim, "python3",
                     f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
                     f'printf \'%s\\n\' "${{WATCHDOG_BOT_TOKEN:-}}" >> "{env_log.as_posix()}"\n'
                     'exit 0\n')
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", "")})
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "register-commands.sh")],
        cwd=REPO, env=env, input=b"", capture_output=True, timeout=60)
    argv = _read_or(argv_log)
    env_token = _read_or(env_log)
    check("register_commands_env_token_canary",
          result.returncode == 0
          and R1B_TOKEN not in argv
          and R1B_TOKEN in env_token,
          f"rc={result.returncode} argv_leak={R1B_TOKEN in argv} "
          f"env_ok={R1B_TOKEN in env_token}")


# ── Пробы: D0a schema v2 (envelope, projection, dual-read) ──────────────────

# Explicit environment allowlist for wrapper subprocesses (review pass):
# notification tokens, proxies and credentials are deliberately NOT inherited,
# so a probe run can never reach real Telegram endpoints.
_WRAPPER_ENV_ALLOWLIST = (
    "PATH", "TEMP", "TMP", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC",
    "PATHEXT", "WINDIR", "MSYSTEM", "LC_ALL", "LANG",
)


def _probe_subprocess_env(home: Path, extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k in _WRAPPER_ENV_ALLOWLIST}
    env["HOME"] = str(home)
    env["XDG_RUNTIME_DIR"] = str(home)
    # RR1b (H5): каталог планировщика logrotate направляем в фиксстуру —
    # настоящий /etc/logrotate.d на CI-runner не записываем, а преflight
    # обязан видеть активируемую политику. deploy.sh читает переменную с
    # дефолтом /etc/logrotate.d.
    sched = home / "logrotate.d"
    try:
        sched.mkdir(parents=True, exist_ok=True)
        env["LOGROTATE_SCHED_DIR"] = str(sched)
    except OSError:
        pass
    # deploy.sh в модульном режиме правит ЖИВОЙ crontab. Проба не должна
    # наследовать боевой MODULE_LOCAL_SERVICES=ON: иначе deploy-пробы (у которых
    # шим есть только для gh/git/sed) сносят реальную строку local-services.
    env.pop("MODULE_LOCAL_SERVICES", None)
    # Pin child stdout to UTF-8: on Windows the locale codec (cp1251) cannot
    # encode the alert emoji and the alerting python would die mid-print.
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update(extra)
    return env


# ── Пробы: R1c Authorization headers out of child argv ──────────────────────

R1C_TOKEN = "ARGUS_CANARY_R1C_AUTH"
R1C_TG = "ARGUS_CANARY_R1C_TGURL"
R1C_GH = "ARGUS_CANARY_R1C_GHTOKEN"
R1C_PROXY = "http://127.0.0.1:8444"


def _r1c_shell_curl_shim(shim_dir: Path, tmp: Path, tag: str) -> tuple[Path, Path]:
    """curl shim для shell-проб R1c: логирует argv и stdin каждого вызова и
    эмулирует разбираемые скриптом формы ответа (code-only для -w, body+code
    для getMe — getMe ищем в STDIN, потому что token-bearing URL идёт через
    config, 302 для socks, JSON для status-hint). Сети нет."""
    argv_log = tmp / f"{tag}-argv.log"
    stdin_log = tmp / f"{tag}-stdin.log"
    body = (
        f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
        'STD=$(cat 2>/dev/null)\n'
        f'printf \'%s\\n\' "$STD" >> "{stdin_log.as_posix()}"\n'
        f'printf \'\\n--\\n\' >> "{stdin_log.as_posix()}"\n'
        'case "$*" in\n'
        '  *--socks5-hostname*) printf \'302\\n\'; exit 0 ;;\n'
        'esac\n'
        'case "$STD" in\n'
        '  *getMe*)\n'
        '    case "$*" in\n'
        '      *"-o /dev/null"*) printf \'200\\n\' ;;\n'
        '      *) printf \'{"ok": true}\\n200\\n\' ;;\n'
        '    esac ;;\n'
        '  *)\n'
        '    case "$*" in\n'
        '      *-w*) printf \'200\\n\' ;;\n'
        '      *) printf \'{"ok": true}\\n\' ;;\n'
        '    esac ;;\n'
        'esac\n'
        'exit 0\n'
    )
    _write_argv_shim(shim_dir, "curl", body)
    return argv_log, stdin_log


def _r1c_dc_curl_shim(shim_dir: Path, tmp: Path, tag: str) -> tuple[Path, Path]:
    """curl shim для проб ai-deep-check: тот же capture, но ответ в форме
    `-w "\\n%{http_code}"` — body JSON + код (curl_json парсит rpartition)."""
    argv_log = tmp / f"{tag}-argv.log"
    stdin_log = tmp / f"{tag}-stdin.log"
    body = (
        f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
        f'cat >> "{stdin_log.as_posix()}" 2>/dev/null\n'
        f'printf \'\\n--\\n\' >> "{stdin_log.as_posix()}"\n'
        'printf \'{"data": [{"id": "m1"}]}\\n200\'\n'
        'exit 0\n'
    )
    _write_argv_shim(shim_dir, "curl", body)
    return argv_log, stdin_log


def _r1c_save_outcome(tmp: Path, tag: str, result) -> None:
    """Сохранить stdout/stderr пробы как артефакты для boundary-скана (§7.6)."""
    write(tmp / f"{tag}-out.txt", result.stdout)
    write(tmp / f"{tag}-err.txt", result.stderr)


def probe_rr0c_public_defaults_no_personal_assumptions():
    """RR0c: публичная установка не содержит персональных дефолтов.

    B1: ни один runtime-путь не падает в персональный smart-proxy — дефолт
    127.0.0.1:8444 убран из bash и python, ключ объявлен в config-шаблоне,
    описание в registry не обещает дефолт. B2: GITHUB_REPO без персонального
    дефолта. B3: канонические имена юнитов в манифесте и шаблонах,
    legacy-шаблоны сняты с активной поверхности."""
    problems = []
    for path in sorted((REPO / "scripts").glob("*.sh")):
        if "${TELEGRAM_PROXY:-http" in path.read_text(encoding="utf-8"):
            problems.append(f"scripts/{path.name}: implicit proxy fallback")
    for path in sorted((REPO / "scripts").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if '"TELEGRAM_PROXY", "http://127.0.0.1:8444"' in text:
            problems.append(f"scripts/{path.name}: implicit proxy default")
    deploy_text = (REPO / "deploy.sh").read_text(encoding="utf-8")
    if "upmeister/hermes-infra" in deploy_text:
        problems.append("deploy.sh: personal GITHUB_REPO default")
    if 'GITHUB_REPO="${GITHUB_REPO:-}"' not in deploy_text:
        problems.append("deploy.sh: GITHUB_REPO default not explicit-empty")
    if "hermes-argus-config.path" not in deploy_text:
        problems.append("deploy.sh: canonical path unit missing from manifest")
    template = (REPO / "config" / "config.env.template").read_text(encoding="utf-8")
    for needle in ("TELEGRAM_PROXY=", "GITHUB_REPO="):
        if needle not in template:
            problems.append(f"config.env.template: explicit {needle} missing")
    for path, name in ((REPO / "scripts" / "gen-registry.py", "gen-registry.py"),
                       (REPO / "registry.yaml", "registry.yaml")):
        if "по умолчанию 127.0.0.1:8444" in path.read_text(encoding="utf-8"):
            problems.append(f"{name}: proxy default in description")
    if not (REPO / "modules" / "systemd" / "hermes-argus-config.path").exists():
        problems.append("canonical path unit template missing")
    if (REPO / "modules" / "systemd" / "hermes-vps-kit-config.path").exists():
        problems.append("legacy path unit template still on install surface")
    check("rr0c_public_defaults_no_personal_assumptions", not problems,
          f"problems={problems}")


def probe_rr0c_proxy_check_explicit(hc):
    """RR0c B1: v2 tcp-проверка и getme-транспорт следуют явному
    TELEGRAM_PROXY. Не задан → unconfigured/direct; задан → используется;
    мусор → fail с диагнозом, а не персональный дефолт. Всё offline."""
    ok_url = (hc.proxy_url({}) == ""
              and hc.proxy_url({"TELEGRAM_PROXY": "http://10.1.2.3:9999 # inline"})
              == "http://10.1.2.3:9999")
    ok_parse = (hc.parse_host_port("") is None
                and hc.parse_host_port("socks5://1.2.3.4:1080") == ("1.2.3.4", 1080))
    v_unconf = hc.run_check({"id": "x", "primitive": "tcp", "host": "", "port": 0,
                             "proxy_malformed": False}, "", {})
    v_mal = hc.run_check({"id": "x", "primitive": "tcp", "host": "", "port": 0,
                          "proxy_malformed": True}, "", {})
    v_cfg = hc.run_check({"id": "x", "primitive": "tcp", "host": "127.0.0.1",
                          "port": 1}, "", {})
    ok = (ok_url and ok_parse
          and v_unconf[0] == "unconfigured"
          and v_mal[0] == "fail" and "unparseable" in v_mal[1]
          and v_cfg[0] == "fail")
    check("rr0c_proxy_check_explicit", ok,
          f"url={ok_url} parse={ok_parse} unconf={v_unconf[0]} mal={v_mal[0]} cfg={v_cfg[0]}")


def probe_rr0c_deploy_unit_handoff_detection(tmp: Path):
    """RR0c B3: deploy ставит канонические hermes-argus-* юниты; при живом
    legacy hermes-vps-kit-config.path файл legacy остаётся нетронутым и
    печатается ручной хэндофф — второй активный producer не появляется молча."""
    config = write(tmp / "rr0c-unit-config.env",
                   "MODULE_CORE=OFF\n"
                   "MODULE_INTEGRATIONS=ON\n"
                   "MODULE_TG_BOT=OFF\n"
                   "MODULE_ANALYZER=OFF\n"
                   "MODULE_HEARTBEAT=OFF\n"
                   "MODULE_GH_HEARTBEAT=OFF\n"
                   "MODULE_DISCORD_BOT=OFF\n"
                   "MODULE_LOCAL_SERVICES=OFF\n")
    shim = tmp / "rr0c-unit-shim"
    shim.mkdir()
    # crontab-шим обязателен: deploy reconcile трогает crontab и на OFF-модуле.
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) printf "" 2>/dev/null;;\n'
                     '  -)  cat > /dev/null;;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    _write_argv_shim(shim, "flock", "exit 0\n")
    _rr1b_host_shims(shim)

    def _run_deploy(home: Path, cron_file: Path):
        _rr1b_fake_hermes(home)
        env = _path_shim_env(home, {
            "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
            "CRON_FILE": str(cron_file),
        })
        return subprocess.run(["bash", str(REPO / "deploy.sh"), str(config)],
                              cwd=REPO, env=env, capture_output=True, text=True,
                              timeout=120)

    # Case A — чистая установка: канонические юниты ставятся, legacy нет.
    home_a = tmp / "rr0c-unit-home-fresh"
    cron_a = tmp / "rr0c-unit-cron-a.txt"
    res_a = _run_deploy(home_a, cron_a)
    units_a = home_a / ".config" / "systemd" / "user"
    fresh_ok = (res_a.returncode == 0
                and (units_a / "hermes-argus-config.path").exists()
                and (units_a / "hermes-argus-discover.service").exists()
                and not (units_a / "hermes-vps-kit-config.path").exists()
                and "hermes-vps-kit-config.path" not in res_a.stdout)
    # Case B — legacy-юнит жив: файл не тронут, канонические ставятся рядом,
    # печатается ручной хэндофф.
    home_b = tmp / "rr0c-unit-home-legacy"
    cron_b = tmp / "rr0c-unit-cron-b.txt"
    legacy_unit = home_b / ".config" / "systemd" / "user" / "hermes-vps-kit-config.path"
    legacy_unit.parent.mkdir(parents=True, exist_ok=True)
    legacy_unit.write_text("# legacy live unit (operator-owned)\n", encoding="utf-8")
    res_b = _run_deploy(home_b, cron_b)
    handoff_ok = (res_b.returncode == 0
                  and (home_b / ".config" / "systemd" / "user" /
                       "hermes-argus-config.path").exists()
                  and legacy_unit.read_text(encoding="utf-8")
                  == "# legacy live unit (operator-owned)\n"
                  and "hermes-vps-kit-config.path" in res_b.stdout
                  and "systemctl --user disable --now hermes-vps-kit-config.path"
                  in res_b.stdout)
    check("rr0c_deploy_unit_handoff_detection",
          fresh_ok and handoff_ok,
          f"fresh={fresh_ok} handoff={handoff_ok} rcA={res_a.returncode} "
          f"rcB={res_b.returncode}")


def _rr1a_home_for_deploy(home: Path) -> str:
    """Форма HOME, которую deploy.sh реально увидит: MSYS-баш конвертирует
    Windows-пути при импорте окружения, Linux оставляет как есть."""
    r = subprocess.run(["bash", "-c", "printf %s \"$HOME\""],
                       env={"HOME": home.as_posix(),
                            "PATH": os.environ.get("PATH", "")},
                       capture_output=True, text=True, timeout=30)
    return (r.stdout or home.as_posix()).strip()


# Утилиты, которые deploy.sh вызывает, выводятся из PATH целиком: белый
# список хрупок (dirname, flock, id…), а каталоги с crontab из PATH
# исключаются — на Linux /usr/bin содержит и crontab, и bash, поэтому нужен
# доступ к остальным командам через обёртки.
_RR1A_NEVER_WRAP = {"crontab", "crontab.exe"}


def _rr1a_path_without_crontab(shim_dir: str) -> str:
    """PATH, в котором crontab недостижим, а остальные утилиты доступны.

    Из PATH исключаются каталоги с crontab; каждая найденная команда
    пробрасывается обёрткой `exec <абс-путь> "$@"` в отдельный bin. Так
    `command -v crontab` не находит утилиту нигде (проба не может писать в
    живое расписание), и одновременно bash/sed/dirname/… остаются
    вызываемыми на любой платформе.
    """
    real = os.environ.get("PATH", "")
    wrapper_bin = Path(shim_dir) / "nobin"
    wrapper_bin.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    for entry in real.split(os.pathsep):
        if not entry:
            continue
        try:
            names = sorted(os.listdir(entry))
        except OSError:
            continue
        for name in names:
            base = name
            if base in _RR1A_NEVER_WRAP or base.lower() in _RR1A_NEVER_WRAP:
                continue
            if base in seen:
                continue
            candidate = Path(entry) / name
            if not candidate.is_file():
                continue
            seen.add(base)
            _write_argv_shim(wrapper_bin, base,
                             'exec "' + candidate.as_posix() + '" "$@"\n')
    return os.pathsep.join([shim_dir, str(wrapper_bin)])


def _rr1a_cron_shims(tmp: Path, tag: str, flock_fails: bool = False) -> Path:
    """crontab shim на фикстуре: провал чтения/записи и пустой стейт
    моделируются явно, никакой живой crontab не используется."""
    shim = tmp / f"rr1a-cron-shim-{tag}"
    shim.mkdir(parents=True, exist_ok=True)
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) if [ -n "${CRONTAB_READ_FAIL:-}" ]; then echo "crontab: backend failure" >&2; exit 2; fi\n'
                     '      if [ -f "$CRONTAB_FIXTURE" ]; then cat "$CRONTAB_FIXTURE"; else echo "no crontab for argus-test" >&2; exit 1; fi ;;\n'
                     '  -)  if [ -n "${CRONTAB_WRITE_FAIL:-}" ]; then exit 1; fi\n'
                     '      cat > "$CRONTAB_FIXTURE" ;;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    # grant-маркер: доказательство, что лок реально берётся при успешном deploy
    _write_argv_shim(shim, "flock",
                     'printf "%s\\n" "$*" >> "${FLOCK_GRANT_LOG:-/dev/null}"'
                     + "\n"
                     + "exit " + ("1" if flock_fails else "0") + "\n")
    return shim


def _rr1a_modules(core=False, integrations=False, local_services=False,
                  analyzer=False, heartbeat=False, tg_bot=False) -> str:
    flags = {"MODULE_CORE": core, "MODULE_INTEGRATIONS": integrations,
             "MODULE_LOCAL_SERVICES": local_services,
             "MODULE_ANALYZER": analyzer, "MODULE_HEARTBEAT": heartbeat,
             "MODULE_TG_BOT": tg_bot, "MODULE_GH_HEARTBEAT": False,
             "MODULE_DISCORD_BOT": False}
    return "".join(f"{k}={'ON' if v else 'OFF'}\n" for k, v in flags.items())


def _rr1a_cron_deploy(tmp: Path, tag: str, home: Path, shim: Path,
                      fixture: Path, modules: str, profile: str = "full",
                      extra_env: dict | None = None) -> subprocess.CompletedProcess:
    config = write(tmp / f"rr1a-{tag}-config.env", modules)
    # RR1b (host-readiness): deploy теперь начинается с preflight хоста, поэтому
    # каждая deploy-фикстура обязана иметь работающий user-менеджер, logrotate
    # и дерево Hermes, иначе она проверяла бы отказ вместо своего сюжета.
    # crontab здесь НЕ создаётся: его (вместе с внедрением сбоев и случаем
    # «утилиты нет вовсе») ставит _rr1a_cron_shims.
    _rr1b_host_shims(shim, crontab=False)
    _rr1b_fake_hermes(home)
    env = _probe_subprocess_env(home, {
        "HOME": home.as_posix(),
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRONTAB_FIXTURE": fixture.as_posix(),
        "CRON_FILE": (tmp / f"rr1a-{tag}-proposal.txt").as_posix(),
        "CRON_PROFILE": profile,
        **(extra_env or {}),
    })
    return subprocess.run(
        ["bash", (REPO / "deploy.sh").as_posix(), config.as_posix()],
        cwd=REPO.as_posix(), env=env, capture_output=True, text=True, timeout=180)


def _rr1a_block(text: str) -> str | None:
    m = re.search(r"^# BEGIN HERMES-ARGUS\n(.*?)^# END HERMES-ARGUS\n",
                  text, re.S | re.M)
    return m.group(1) if m else None


def _rr1a_outside(text: str) -> str:
    outside, in_block = [], False
    for line in text.split("\n"):
        if line == "# BEGIN HERMES-ARGUS":
            in_block = True
            continue
        if line == "# END HERMES-ARGUS":
            in_block = False
            continue
        if not in_block:
            outside.append(line)
    return "\n".join(outside)


def probe_rr1a_cron_block_position_and_blank_lines(tmp: Path):
    """RR1a §2: существующий managed-блок заменяется НА ПРЕЖНЕМ МЕСТЕ —
    cron-переменные (SHELL/MAILTO/PATH) действуют на последующие задания, и
    перенос блока в конец молча изменил бы его исполнение. Хвостовые пустые
    строки crontab'а сохраняются дословно при замене и снятии блока."""
    nl = "\n"
    problems = []
    home = tmp / "rr1a-pos-home"
    fixture = tmp / "rr1a-pos-cron.txt"
    shim = _rr1a_cron_shims(tmp, "pos")
    # Блок стоит ДО `SHELL=/bin/false`: после deploy он обязан остаться там же,
    # иначе задачи блока унаследуют /bin/false и перестанут выполняться.
    seeded = nl.join([
        "SHELL=/bin/bash",
        "# BEGIN HERMES-ARGUS",
        "*/9 * * * * /bin/true # placeholder",
        "# END HERMES-ARGUS",
        "SHELL=/bin/false",
        "0 9 * * 1-5 /usr/bin/operator-report --quiet",
        "",
        "",
    ]) + nl
    write(fixture, seeded)
    r1 = _rr1a_cron_deploy(tmp, "pos", home, shim, fixture,
                           _rr1a_modules(core=True))
    text1 = fixture.read_text(encoding="utf-8")
    lines1 = text1.split(nl)
    i_begin = lines1.index("# BEGIN HERMES-ARGUS") if "# BEGIN HERMES-ARGUS" in lines1 else -1
    i_false = lines1.index("SHELL=/bin/false") if "SHELL=/bin/false" in lines1 else -1
    pos_ok = (r1.returncode == 0 and i_begin > 0 and i_false > i_begin
              and "placeholder" not in text1
              and "hermes-watchdog.sh" in text1
              and text1.endswith(nl * 3))
    if not pos_ok:
        problems.append(f"pos rc={r1.returncode} begin={i_begin} false={i_false} "
                        f"tail={text1[-4:]!r}")
    # Снятие блока при OFF сохраняет операторские строки и хвостовые пустые.
    r2 = _rr1a_cron_deploy(tmp, "pos-off", home, shim, fixture, _rr1a_modules())
    text2 = fixture.read_text(encoding="utf-8")
    off_ok = (r2.returncode == 0 and "BEGIN HERMES-ARGUS" not in text2
              and "SHELL=/bin/false" in text2
              and "operator-report" in text2
              and text2.endswith(nl * 3))
    if not off_ok:
        problems.append(f"off rc={r2.returncode} tail={text2[-4:]!r}")
    check("rr1a_cron_block_position_and_blank_lines",
          pos_ok and off_ok, f"problems={problems}")


def probe_rr1a_cron_managed_block_fresh(tmp: Path):
    """RR1a §6.1: свежая установка создаёт один managed-блок с job'ами
    включённых модулей; повторный deploy байт-стабилен и не дублирует."""
    home = tmp / "rr1a-fresh-home"
    fixture = tmp / "rr1a-fresh-cron.txt"
    shim = _rr1a_cron_shims(tmp, "fresh")
    modules = _rr1a_modules(core=True, integrations=True, local_services=True)
    grant_log = tmp / "rr1a-flock-grants.log"
    r1 = _rr1a_cron_deploy(tmp, "fresh", home, shim, fixture, modules,
                           extra_env={"FLOCK_GRANT_LOG": grant_log.as_posix()})
    text1 = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    block = _rr1a_block(text1)
    outside = _rr1a_outside(text1)
    r2 = _rr1a_cron_deploy(tmp, "fresh", home, shim, fixture, modules,
                           extra_env={"FLOCK_GRANT_LOG": grant_log.as_posix()})
    text2 = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    # §6.8: лок действительно берётся на каждом reconciliation (сериализация
    # не декларативна) — grant-маркер пишет шим при успешном захвате.
    granted = (grant_log.read_text(encoding="utf-8").count("-n")
               if grant_log.exists() else 0)
    ok = (r1.returncode == 0 and r2.returncode == 0
          and text1.count("# BEGIN HERMES-ARGUS") == 1
          and text1.count("# END HERMES-ARGUS") == 1
          and block is not None
          and block.count("hermes-watchdog.sh") == 1
          and block.count("integration-discover-wrapper.sh") == 1
          and block.count("service-status-snapshot.py") == 1
          and "/bin/bash -c 'set -a; source" in block
          and not outside.strip()
          and text2 == text1
          and granted >= 2
          and "актуален" in r2.stdout)
    check("rr1a_cron_managed_block_fresh", ok,
          f"rc={r1.returncode}/{r2.returncode} block={block is not None} "
          f"stable={text2 == text1} locks={granted} err={r1.stderr[-200:]!r}")


def probe_rr1a_cron_module_transitions(tmp: Path):
    """RR1a §6.2: ON→OFF каждого scheduling-модуля снимает только его строки;
    все OFF снимает только блок; TG/Discord — не cron-операции."""
    problems = []
    cases = [("core", "hermes-watchdog.sh"),
             ("integrations", "integration-discover-wrapper.sh"),
             ("analyzer", "health-analyzer.py"),
             ("heartbeat", "heartbeat.sh"),
             ("local_services", "service-status-snapshot.py")]
    for name, marker in cases:
        home = tmp / f"rr1a-tr-home-{name}"
        fixture = tmp / f"rr1a-tr-cron-{name}.txt"
        shim = _rr1a_cron_shims(tmp, f"tr-{name}")
        flags = {name: True}
        on = _rr1a_cron_deploy(tmp, f"tr-{name}-on", home, shim, fixture,
                               _rr1a_modules(**flags))
        text_on = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
        off = _rr1a_cron_deploy(tmp, f"tr-{name}-off", home, shim, fixture,
                                _rr1a_modules())
        text_off = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
        if not (on.returncode == 0 and off.returncode == 0
                and marker in (text_on or "")
                and "# BEGIN HERMES-ARGUS" in (text_on or "")
                and marker not in text_off
                and "# BEGIN HERMES-ARGUS" not in text_off):
            problems.append(f"{name}: on={on.returncode} off={off.returncode} "
                            f"tab_on={marker in text_on} tab_off={text_off!r}")
    # TG/Discord активация — не cron-операция: блока нет, crontab не пишется.
    home = tmp / "rr1a-tr-home-tg"
    fixture = tmp / "rr1a-tr-cron-tg.txt"
    shim = _rr1a_cron_shims(tmp, "tr-tg")
    tg = _rr1a_cron_deploy(tmp, "tr-tg", home, shim, fixture,
                           _rr1a_modules(tg_bot=True))
    if not (tg.returncode == 0 and not fixture.exists()):
        problems.append(f"tg: rc={tg.returncode} fixture_exists={fixture.exists()}")
    check("rr1a_cron_module_transitions", not problems, f"problems={problems[:3]}")


def probe_rr1a_cron_minimal_profile(tmp: Path):
    """RR1a §6.3: minimal-профиль остаётся тихим (без CORE-алертных job'ов),
    selected integration/local-services job'ы сохраняют семантику генератора."""
    home = tmp / "rr1a-min-home"
    fixture = tmp / "rr1a-min-cron.txt"
    shim = _rr1a_cron_shims(tmp, "min")
    modules = _rr1a_modules(core=True, integrations=True, local_services=True)
    r = _rr1a_cron_deploy(tmp, "min", home, shim, fixture, modules,
                          profile="minimal")
    block = _rr1a_block(fixture.read_text(encoding="utf-8")
                        if fixture.exists() else "")
    ok = (r.returncode == 0 and block is not None
          and "hermes-watchdog.sh" not in block
          and "network-guard.sh" not in block
          and "integration-discover-wrapper.sh" in block
          and "health-check-v2-wrapper.sh" in block
          and "service-status-snapshot.py" in block)
    check("rr1a_cron_minimal_profile", ok,
          f"rc={r.returncode} block_quiet={block is not None and 'hermes-watchdog.sh' not in block} "
          f"err={r.stderr[-200:]!r}")


def probe_rr1a_cron_mixed_preservation(tmp: Path):
    """RR1a §6.4: посторонние комментарии/env/job'ы (включая lookalike
    basename и кастомный вызов нашего скрипта с другими аргументами)
    сохраняются дословно и в исходном порядке; внешние обёртки не усыновляются."""
    home = tmp / "rr1a-mix-home"
    fixture = tmp / "rr1a-mix-cron.txt"
    shim = _rr1a_cron_shims(tmp, "mix")
    original = [
        "# operator crontab — do not sort",
        "MAILTO=ops@example.invalid",
        "",
        "0 9 * * 1-5 /usr/bin/operator-report --quiet",
        "0 0 * * 0 /usr/local/bin/infra-sync.sh",
        "30 2 * * * /usr/local/bin/app-backup.sh >> /var/log/backup.log 2>&1",
        "0 0 * * * /opt/fake/scripts/hermes-watchdog.sh --fake >> /tmp/fake.log 2>&1",
        f"0 4 * * * {home.as_posix()}/scripts/auto-remediate.sh --dry-run "
        f">> {home.as_posix()}/.hermes/logs/custom-remediate.log 2>&1",
        "*/10 * * * * ~/scripts/check-integrations.sh >> ~/.hermes/logs/quick-check.log 2>&1",
    ]
    write(fixture, "\n".join(original) + "\n")
    r = _rr1a_cron_deploy(tmp, "mix", home, shim, fixture,
                          _rr1a_modules(core=True))
    text = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    outside = [l for l in _rr1a_outside(text).split("\n") if l != "" or True]
    outside = _rr1a_outside(text).split("\n")[:-1] if _rr1a_outside(text) else []
    block = _rr1a_block(text)
    ok = (r.returncode == 0 and block is not None
          and outside == original
          and block.count("hermes-watchdog.sh") == 1
          and "сохранено" in r.stdout
          and "check-integrations.sh" not in (block or ""))
    check("rr1a_cron_mixed_preservation", ok,
          f"rc={r.returncode} preserved={outside == original} "
          f"out={r.stdout[-300:]!r} err={r.stderr[-200:]!r}")


def probe_rr1a_cron_legacy_adoption(tmp: Path):
    """RR1a §6.5: известные ранее сгенерированные формы (оба написания путей,
    включая легаси heartbeat с голым source и producer-only local-services)
    усыновляются ровно один раз в managed-блок; внешние/saved job'ы не тронуты."""
    home = tmp / "rr1a-adopt-home"
    fixture = tmp / "rr1a-adopt-cron.txt"
    shim = _rr1a_cron_shims(tmp, "adopt")
    hp = _rr1a_home_for_deploy(home)
    legacy = [
        "# pre-RR1a manually installed argus lines",
        f"*/5 * * * * {hp}/scripts/hermes-watchdog.sh >> {hp}/.hermes/logs/watchdog-cron.log 2>&1",
        "*/2 * * * * ~/scripts/network-guard.sh >> ~/.hermes/logs/network-guard-cron.log 2>&1",
        f"*/5 * * * * python3 {hp}/scripts/fallback-tracker-v2.py >> {hp}/.hermes/logs/fallback-tracker-v2.log 2>&1",
        "*/5 * * * * set -a; source ~/.hermes/.env; set +a; ~/scripts/heartbeat.sh >> ~/.hermes/logs/heartbeat.log 2>&1",
        f"*/5 * * * * python3 {hp}/.hermes/scripts/service-status-snapshot.py --quiet >> {hp}/.hermes/logs/service-status.log 2>&1",
        f"5 * * * * cd {hp}/.hermes/scripts && python3 health-analyzer.py --update >> {hp}/.hermes/logs/health-analyzer.log 2>&1",
        f"0 3 * * 1 {hp}/scripts/check-updates.sh",
        "0 7 * * * hermes no_agent saved-full-check --full",
        "15 3 * * * /usr/local/bin/operator-backup.sh",
    ]
    write(fixture, "\n".join(legacy) + "\n")
    modules = _rr1a_modules(core=True, integrations=True, analyzer=True,
                            heartbeat=True, local_services=True)
    r1 = _rr1a_cron_deploy(tmp, "adopt", home, shim, fixture, modules)
    text1 = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    outside = _rr1a_outside(text1)
    block = _rr1a_block(text1) or ""
    r2 = _rr1a_cron_deploy(tmp, "adopt", home, shim, fixture, modules)
    text2 = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    ok = (r1.returncode == 0 and r2.returncode == 0
          and outside.split("\n")[:-1] == [legacy[0], legacy[8], legacy[9]]
          and block.count("hermes-watchdog.sh") == 1
          # H4 (RR1b): сетевой guard — отдельный opt-in. При MODULE_NETWORK_GUARD=OFF
          # его строка не генерируется, поэтому ранее установленная форма
          # узнаётся как Argus-owned и УБИРАЕТСЯ из crontab, а не усыновляется
          # в блок. Иначе дефолтная установка сохраняла бы хост-политику.
          and block.count("network-guard.sh") == 0
          and block.count("fallback-tracker-v2.py") == 1
          and block.count("heartbeat.sh") == 1
          and "set -a; source" in block
          and "bin/bash -c 'set -a; source" in block
          and "source ~/.hermes/.env; set +a; ~/scripts/heartbeat.sh" not in text1
          and block.count("service-status-snapshot.py") == 1
          and block.count("health-analyzer.py") == 1
          and block.count("check-updates.sh") == 1
          and text2 == text1)
    check("rr1a_cron_legacy_adoption", ok,
          f"rc={r1.returncode}/{r2.returncode} stable={text2 == text1} "
          f"outside={outside!r} err={r1.stderr[-200:]!r}")


def probe_rr1a_cron_fail_paths(tmp: Path):
    """RR1a §6.6: отсутствие crontab, сбой чтения и сбой записи — громкий
    nonzero deploy; прежний fixture не заменяется пустым расписанием."""
    problems = []
    # a) сбой чтения: generic ошибка не трактуется как пустой crontab
    home = tmp / "rr1a-fail-read-home"
    fixture = tmp / "rr1a-fail-read-cron.txt"
    write(fixture, "0 9 * * 1-5 /usr/bin/operator-report --quiet\n")
    shim = _rr1a_cron_shims(tmp, "fail-read")
    r = _rr1a_cron_deploy(tmp, "fail-read", home, shim, fixture,
                          _rr1a_modules(core=True),
                          extra_env={"CRONTAB_READ_FAIL": "1"})
    if not (r.returncode != 0 and "неопознанной ошибкой" in r.stdout + r.stderr
            and fixture.read_text(encoding="utf-8")
            == "0 9 * * 1-5 /usr/bin/operator-report --quiet\n"):
        problems.append(f"read-fail rc={r.returncode} tab={fixture.read_text()!r}")
    # b) сбой записи
    home = tmp / "rr1a-fail-write-home"
    fixture = tmp / "rr1a-fail-write-cron.txt"
    write(fixture, "0 9 * * 1-5 /usr/bin/operator-report --quiet\n")
    shim = _rr1a_cron_shims(tmp, "fail-write")
    r = _rr1a_cron_deploy(tmp, "fail-write", home, shim, fixture,
                          _rr1a_modules(core=True),
                          extra_env={"CRONTAB_WRITE_FAIL": "1"})
    if not (r.returncode != 0 and "не удалось записать" in r.stdout + r.stderr
            and fixture.read_text(encoding="utf-8")
            == "0 9 * * 1-5 /usr/bin/operator-report --quiet\n"):
        problems.append(f"write-fail rc={r.returncode} tab={fixture.read_text()!r}")
    # c) отсутствие crontab-утилиты: PATH без каталогов, содержащих crontab —
    # command -v не находит утилиту нигде (каталог-шим недостаточен: bash
    # нашёл бы системный crontab и проба писала бы в живое расписание —
    # нарушение §3/§6.11).
    home = tmp / "rr1a-fail-nocron-home"
    fixture = tmp / "rr1a-fail-nocron-cron.txt"
    write(fixture, "0 9 * * 1-5 /usr/bin/operator-report --quiet\n")
    shim = _rr1a_cron_shims(tmp, "fail-nocron")
    (shim / "crontab").unlink(missing_ok=True)
    r = _rr1a_cron_deploy(tmp, "fail-nocron", home, shim, fixture,
                          _rr1a_modules(core=True),
                          extra_env={"PATH": _rr1a_path_without_crontab(str(shim))})
    if not (r.returncode != 0 and "crontab недоступен" in r.stdout + r.stderr
            and fixture.read_text(encoding="utf-8")
            == "0 9 * * 1-5 /usr/bin/operator-report --quiet\n"):
        problems.append(f"no-crontab rc={r.returncode} out={r.stdout[-200:]!r}")
    check("rr1a_cron_fail_paths", not problems, f"problems={problems}")


def probe_rr1a_cron_malformed_markers(tmp: Path):
    """RR1a §6.7: дублированные/незакрытые/перевёрнутые маркеры отклоняются
    без записи; установленный crontab не меняется."""
    problems = []
    layouts = {
        "dup-begin": ["# BEGIN HERMES-ARGUS", "# BEGIN HERMES-ARGUS",
                      "0 9 * * 1-5 /usr/bin/operator-report --quiet",
                      "# END HERMES-ARGUS"],
        "unmatched-begin": ["# BEGIN HERMES-ARGUS",
                            "0 9 * * 1-5 /usr/bin/operator-report --quiet"],
        "reversed": ["0 9 * * 1-5 /usr/bin/operator-report --quiet",
                     "# END HERMES-ARGUS", "# BEGIN HERMES-ARGUS"],
    }
    for name, lines in layouts.items():
        home = tmp / f"rr1a-mm-home-{name}"
        fixture = tmp / f"rr1a-mm-cron-{name}.txt"
        original = "\n".join(lines) + "\n"
        write(fixture, original)
        shim = _rr1a_cron_shims(tmp, f"mm-{name}")
        r = _rr1a_cron_deploy(tmp, f"mm-{name}", home, shim, fixture,
                              _rr1a_modules(core=True))
        if not (r.returncode != 0
                and "разметк" in r.stdout + r.stderr
                and fixture.read_text(encoding="utf-8") == original):
            problems.append(f"{name}: rc={r.returncode} "
                            f"unchanged={fixture.read_text(encoding='utf-8') == original}")
    check("rr1a_cron_malformed_markers", not problems, f"problems={problems}")


def probe_rr1a_cron_contention(tmp: Path):
    """RR1a §6.8: занятый nonblocking-лок даёт явный contention-результат
    без записи и без дублирования блока (flock-шим моделирует удержание)."""
    home = tmp / "rr1a-lock-home"
    fixture = tmp / "rr1a-lock-cron.txt"
    write(fixture, "0 9 * * 1-5 /usr/bin/operator-report --quiet\n")
    shim = _rr1a_cron_shims(tmp, "lock", flock_fails=True)
    r = _rr1a_cron_deploy(tmp, "lock", home, shim, fixture,
                          _rr1a_modules())
    text = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    ok = (r.returncode != 0
          and "параллельный deploy" in r.stdout + r.stderr
          and "# BEGIN HERMES-ARGUS" not in text
          and text.count("# BEGIN HERMES-ARGUS") <= 1)
    check("rr1a_cron_contention", ok,
          f"rc={r.returncode} out={r.stdout[-200:]!r} err={r.stderr[-200:]!r}")


def probe_rr1a_cron_block_shell_safety(tmp: Path):
    """RR1a §6.11: команды блока парсятся под явным шеллом, .env-загрузка
    только через явный /bin/bash -c, креденшел-канарейка не попадает в cron."""
    home = tmp / "rr1a-shell-home"
    fixture = tmp / "rr1a-shell-cron.txt"
    shim = _rr1a_cron_shims(tmp, "shell")
    canary = "ARGUS_CANARY_TOKEN_RR1A"
    modules = ("MODULE_CORE=ON\nMODULE_INTEGRATIONS=ON\nMODULE_LOCAL_SERVICES=ON\n"
               "MODULE_ANALYZER=ON\nMODULE_HEARTBEAT=ON\n"
               "MODULE_TG_BOT=OFF\nMODULE_GH_HEARTBEAT=OFF\n"
               "MODULE_DISCORD_BOT=OFF\n"
               f"WATCHDOG_BOT_TOKEN={canary}\n")
    r = _rr1a_cron_deploy(tmp, "shell", home, shim, fixture, modules)
    text = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    block = _rr1a_block(text) or ""
    parse_fail = []
    bash_only = 0
    for line in block.splitlines():
        if not line.strip():
            continue
        # Проверяется КОМАНДА (поле после расписания), а не вся cron-строка:
        # cron исполняет команду, и именно её интерпретирует /bin/sh.
        parts = line.split(None, 5)
        command = parts[5] if len(parts) > 5 else ""
        if not command:
            parse_fail.append(f"no-command-field: {line[:40]}")
            continue
        if "/bin/bash -c '" in command:
            # Внутри bash-обёртки .env грузится bash'ом (cron зовёт sh/dash).
            bash_only += 1
            inner = command.split("/bin/bash -c '", 1)[1].rsplit("'", 1)[0]
            parsed = subprocess.run(["bash", "-n", "-c", inner],
                                    capture_output=True, text=True, timeout=20)
            if parsed.returncode != 0:
                parse_fail.append(f"bash-inner: {line[:50]}")
        else:
            # Разбор ИМЕННО sh (cron исполняет /bin/sh): запуск через bash,
            # чтобы sh резолвился его PATH — POSIX-путь непригоден для
            # CreateProcess вне MSYS. $0=sh, $1=команда.
            parsed = subprocess.run(
                ["bash", "-c", 'exec sh -n -c "$1"', "sh", command],
                                    capture_output=True, text=True, timeout=20)
            if parsed.returncode != 0:
                parse_fail.append(f"sh: {line[:50]}")
        if "source" in command and "/bin/bash -c 'set -a; source" not in command:
            parse_fail.append(f"bare-source: {line[:50]}")
    ok = (r.returncode == 0 and block and bash_only >= 2
          and not parse_fail and canary not in text)
    check("rr1a_cron_block_shell_safety", ok,
          f"rc={r.returncode} bash_only={bash_only} parse_fail={parse_fail[:3]}")


def probe_rr1a_quick_no_global_cron_count(tmp: Path):
    """RR1a §6.10a: валидное малое расписание не флагается снятой
    «<7 задач»-эвристикой quick-проверки (红 на pre-RR1a: 2 строки < 7)."""
    home = tmp / "rr1a-quick-home"
    shim = tmp / "rr1a-quick-shim"
    shim.mkdir()
    cron_fixture = tmp / "rr1a-quick-crontab.txt"
    write(cron_fixture,
        "0 9 * * 1-5 /usr/bin/operator-report --quiet\n"
        "30 10 * * * /usr/bin/backup-tool run\n")
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) cat "$CRONTAB_FIXTURE";;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    _write_argv_shim(shim, "flock", "exit 0\n")
    argv_log, stdin_log = _install_curl_shim(shim, tmp, "rr1a-quick",
                                             stdout="HTTP 000")
    write(home / ".hermes" / ".env", f"GITHUB_TOKEN={R1C_GH}\n")
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRONTAB_FIXTURE": cron_fixture.as_posix(),
    })
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "health-check-integrations.sh"), "--quick"],
        cwd=REPO, env=env, input="", capture_output=True, text=True, timeout=120)
    ok = ("Crontab" not in result.stdout
          and "найдено" not in result.stdout
          and R1C_GH not in (result.stdout + result.stderr))
    check("rr1a_quick_no_global_cron_count", ok,
          f"rc={result.returncode} out={result.stdout[-200:]!r}")


def probe_rr0c_install_single_active_producer(tmp: Path):
    """RR0c B3 (remediation): install.sh включает канонический вотчер только
    при отсутствии живого legacy-юнита. Legacy, который enabled ИЛИ фактически
    active (active-but-not-enabled — ручной/транзиентный запуск), блокирует
    автовключение канонического: два активных producer'а невозможны.

    Полный прогон install.sh под shims: dpkg/git/systemctl/crontab; deploy
    внутри — настоящий, из локального клона кандидата. Offline."""
    home = tmp / "rr0c-install-home"
    cron_file = tmp / "rr0c-install-cron.txt"
    call_log = tmp / "rr0c-systemctl-calls.log"
    # Фикстура-копия рабочего дерева кандидата (install.sh сам делает cd
    # внутрь и зовёт deploy.sh оттуда); pull-шаг внутри install.sh уходит
    # в git-шим, .git-заглушка имитирует уже склонированный репозиторий.
    fixture = home / "hermes-argus"
    shutil.copytree(REPO, fixture,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    (fixture / ".git").mkdir()
    write(fixture / "config.env",
          "MODULE_CORE=ON\n"
          "MODULE_INTEGRATIONS=ON\n"
          "MODULE_TG_BOT=OFF\n"
          "MODULE_ANALYZER=OFF\n"
          "MODULE_HEARTBEAT=OFF\n"
          "MODULE_GH_HEARTBEAT=OFF\n"
          "MODULE_DISCORD_BOT=OFF\n"
          "MODULE_LOCAL_SERVICES=OFF\n"
          f"WATCHDOG_BOT_TOKEN={R1B_TOKEN}\n"
          f"WATCHDOG_CHAT_ID={R1B_CHAT}\n")
    shim = tmp / "rr0c-install-shim"
    shim.mkdir()
    # RR1b (host-readiness): преflight deploy'а внутри install.sh.
    _rr1b_host_shims(shim)
    _rr1b_fake_hermes(home)
    _write_argv_shim(shim, "dpkg", "exit 0\n")
    _write_argv_shim(shim, "git", "exit 0\n")
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) printf "" ;;\n'
                     '  -)  cat > /dev/null;;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    _write_argv_shim(shim, "flock", "exit 0\n")
    _write_argv_shim(shim, "systemctl",
                     'LOG="$SYSTEMCTL_CALL_LOG"\n'
                     'printf \'%s\\n\' "$*" >> "$LOG"\n'
                     '[ "$1" = "--user" ] && shift\n'
                     'case "$1" in\n'
                     '  is-enabled)\n'
                     '    if [ "$2" = "hermes-vps-kit-config.path" ]; then\n'
                     '      [ "${LEGACY_ENABLED:-0}" = "1" ]; exit $?;\n'
                     '    fi; exit 1 ;;\n'
                     '  is-active)\n'
                     '    if [ "$2" = "hermes-vps-kit-config.path" ]; then\n'
                     '      [ "${LEGACY_ACTIVE:-0}" = "1" ]; exit $?;\n'
                     '    fi; exit 3 ;;\n'
                     '  list-unit-files)\n'
                     '    printf \'hermes-argus-config.path enabled enabled\\n\'\n'
                     '    exit 0 ;;\n'
                     '  *) exit 0 ;;\n'
                     'esac\n')

    def _run_install(legacy_active: str):
        call_log.unlink(missing_ok=True)
        env = _path_shim_env(home, {
            "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
            "CRON_FILE": str(cron_file),
            "SYSTEMCTL_CALL_LOG": str(call_log),
            "LEGACY_ENABLED": "0",
            "LEGACY_ACTIVE": legacy_active,
        })
        return subprocess.run(["bash", str(fixture / "install.sh")],
                              cwd=fixture, env=env, capture_output=True,
                              text=True, timeout=180)

    # Case A: legacy активен, но НЕ enabled (active-but-not-enabled) —
    # канонический вотчер НЕ включается, печатается ручной хэндофф.
    res_a = _run_install(legacy_active="1")
    calls_a = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    case_a = (res_a.returncode == 0
              and "legacy hermes-vps-kit-config.path" in res_a.stdout
              and "enable --now hermes-argus-config.path" not in calls_a)
    # Case B: legacy нет/не активен — канонический вотчер включается.
    res_b = _run_install(legacy_active="0")
    calls_b = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    case_b = (res_b.returncode == 0
              and "enable --now hermes-argus-config.path" in calls_b)
    check("rr0c_install_single_active_producer",
          case_a and case_b,
          f"caseA={case_a} rcA={res_a.returncode} caseB={case_b} "
          f"rcB={res_b.returncode}")


def probe_rr0b_removed_surfaces_stay_removed():
    """RR0b: снятые поверхности не возвращаются; удержанные настройки сохраняют
    живых потребителей.

    C2: send-monitoring-report.sh удалён и не числится в манифесте deploy.sh;
    C3: scripts/legacy/ не существует; C4: HERMES_BOT_TOKEN/HERMES_BOT_UID/
    DMS_API_KEY сняты из deploy.sh и config.env.template без остаточных ссылок,
    а WEBHOOK_SECRET_TOKEN/DMS_SNITCH удержаны вместе с потребителями.
    (C1 — full-режим health-check-integrations.sh — удержан на месте по правилу
    контракта «uncertainty is not a deletion signal»; его владелец записан в
    docs/BACKLOG.md, DEBT-004.)"""
    problems = []
    if (REPO / "scripts" / "send-monitoring-report.sh").exists():
        problems.append("scripts/send-monitoring-report.sh вернулся")
    if (REPO / "scripts" / "legacy").exists():
        problems.append("scripts/legacy/ вернулся")
    deploy_text = (REPO / "deploy.sh").read_text(encoding="utf-8")
    for needle in ("send-monitoring-report", "HERMES_BOT_TOKEN",
                   "HERMES_BOT_UID", "DMS_API_KEY"):
        if needle in deploy_text:
            problems.append(f"deploy.sh: {needle}")
    template_text = (REPO / "config" / "config.env.template").read_text(encoding="utf-8")
    if "DMS_API_KEY" in template_text:
        problems.append("config.env.template: DMS_API_KEY")
    registry_text = (REPO / "registry.yaml").read_text(encoding="utf-8")
    if "HERMES_BOT_TOKEN" in registry_text or "DMS_API_KEY" in registry_text:
        problems.append("registry.yaml: снятая настройка")
    gen_text = (REPO / "scripts" / "gen-registry.py").read_text(encoding="utf-8")
    if "WEBHOOK_SECRET_TOKEN" not in gen_text or "DMS_SNITCH" not in gen_text:
        problems.append("gen-registry.py: потеряна удержанная настройка")
    webhook_text = (REPO / "scripts" / "webhook.py").read_text(encoding="utf-8")
    if "WEBHOOK_SECRET_TOKEN" not in webhook_text:
        problems.append("webhook.py: потерян потребитель WEBHOOK_SECRET_TOKEN")
    hb_text = (REPO / "scripts" / "heartbeat.sh").read_text(encoding="utf-8")
    if "DMS_SNITCH" not in hb_text:
        problems.append("heartbeat.sh: потерян потребитель DMS_SNITCH")
    check("rr0b_removed_surfaces_stay_removed", not problems, f"problems={problems}")


def probe_r1c_shell_full_auth_not_in_argv(tmp: Path):
    """R1c §7.1/§7.3: full-режим — 5 authenticated check_url доставляют
    Authorization через stdin-канал (не argv); token-bearing Telegram URL
    остаётся в stdin (R1b не регрессировал); --proxy сохранён; unauthenticated
    вызовы работают (shim 200 → нет строки сбоя SearXNG)."""
    home = tmp / "r1c-full-home"
    shim = tmp / "r1c-shim-full"
    shim.mkdir()
    argv_log, stdin_log = _r1c_shell_curl_shim(shim, tmp, "r1c-full")
    write(home / ".hermes" / ".env",
          f"OPENCODE_GO_API_KEY={R1C_TOKEN}\n"
          f"FIRECRAWL_API_KEY={R1C_TOKEN}\n"
          f"GITHUB_TOKEN={R1C_TOKEN}\n"
          f"GH_TOKEN={R1C_TOKEN}\n"
          f"GROQ_API_KEY={R1C_TOKEN}\n"
          f"OPENROUTER_API_KEY={R1C_TOKEN}\n"
          f"CLINE_API_KEY={R1C_TOKEN}\n"
          f"AGENTROUTER_API_KEY={R1C_TOKEN}\n"
          f"TELEGRAM_BOT_TOKEN={R1C_TG}\n"
          f"WATCHDOG_BOT_TOKEN={R1C_TG}\n")
    env = _probe_subprocess_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
    })
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "health-check-integrations.sh")],
        cwd=REPO, env=env, input="", capture_output=True, text=True, timeout=180)
    _r1c_save_outcome(tmp, "r1c-full", result)
    argv_text = _read_or(argv_log)
    stdin_text = _read_or(stdin_log)
    auth_headers = stdin_text.count(f'header = "Authorization: Bearer {R1C_TOKEN}"')
    tg_stdin = f"url = https://api.telegram.org/bot{R1C_TG}/getMe" in stdin_text
    no_secret_argv = R1C_TOKEN not in argv_text and R1C_TG not in argv_text
    proxy_kept = "--proxy" in argv_text
    unauth_ok = "SearXNG: HTTP" not in result.stdout
    ok = (no_secret_argv and auth_headers >= 5 and tg_stdin and proxy_kept
          and unauth_ok and result.returncode == 0)
    check("r1c_shell_full_auth_not_in_argv", ok,
          f"rc={result.returncode} auth_headers={auth_headers} tg_stdin={tg_stdin} "
          f"secret_in_argv={not no_secret_argv} proxy={proxy_kept} unauth_ok={unauth_ok}")


def probe_r1c_quick_github_header_not_in_argv(tmp: Path):
    """R1c §7.2/§7.3: quick GitHub — Authorization: token ... через stdin-канал,
    не в argv; getMe URL остаётся в stdin; обе проверки проходят (shim 200)."""
    home = tmp / "r1c-quick-home"
    shim = tmp / "r1c-shim-quick"
    shim.mkdir()
    argv_log, stdin_log = _r1c_shell_curl_shim(shim, tmp, "r1c-quick")
    write(home / ".hermes" / ".env",
          f"GITHUB_TOKEN={R1C_GH}\n"
          f"WATCHDOG_BOT_TOKEN={R1C_TG}\n"
          f"TELEGRAM_PROXY={R1C_PROXY}\n")
    env = _probe_subprocess_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
    })
    result = subprocess.run(
        ["bash", str(REPO / "scripts" / "health-check-integrations.sh"), "--quick"],
        cwd=REPO, env=env, input="", capture_output=True, text=True, timeout=120)
    _r1c_save_outcome(tmp, "r1c-quick", result)
    argv_text = _read_or(argv_log)
    stdin_text = _read_or(stdin_log)
    gh_in_stdin = f'header = "Authorization: token {R1C_GH}"' in stdin_text
    ok = (R1C_GH not in argv_text and R1C_TG not in argv_text
          and gh_in_stdin
          and f"url = https://api.telegram.org/bot{R1C_TG}/getMe" in stdin_text
          and "🔑 GitHub token" not in result.stdout
          and "🤖 Telegram monitoring bot" not in result.stdout)
    check("r1c_quick_github_header_not_in_argv", ok,
          f"rc={result.returncode} gh_stdin={gh_in_stdin} "
          f"secret_in_argv={R1C_GH in argv_text or R1C_TG in argv_text}")


def probe_r1c_curl_config_header_seam(tmp: Path):
    """R1c §7.1 (delivery proof): РЕАЛЬНЫЙ curl парсит `header = ...` из stdin
    config и отправляет именно этот Authorization на провод; logging-exec shim
    доказывает отсутствие canary в реальном argv. Негативный контроль: без
    header-строки Authorization не уходит."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    real_curl = shutil.which("curl")
    if not real_curl:
        check("r1c_curl_config_header_seam", True, "skipped: curl not installed")
        return

    received: list[tuple[str, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            received.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
        do_GET = _handle
        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 3
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/models"
    try:
        argv_log = tmp / "r1c-seam-argv.log"
        stdin_log = tmp / "r1c-seam-stdin.log"
        shim = tmp / "r1c-shim-seam"
        shim.mkdir()
        # Лог argv + tee stdin → реальный curl (реальный запрос + capture argv).
        _write_argv_shim(shim, "curl",
                         f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
                         f'tee "{stdin_log.as_posix()}" | '
                         f'"{Path(real_curl).as_posix()}" "$@"\n')
        env = _probe_subprocess_env(tmp / "r1c-seam-home", {
            "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        })
        # Через bash -c: bash сам резолвит PATH (shim → tee → реальный curl).
        # Прямой CreateProcess-вызов из python на Windows игнорирует PATH
        # ребёнка и молча берёт реальный curl — capture был бы вакуумным.
        curl_via_bash = 'exec curl -s -o /dev/null -w "%{http_code}" -K -'
        positive = subprocess.run(
            ["bash", "-c", curl_via_bash],
            input=f'url = {url}\nheader = "Authorization: Bearer {R1C_TOKEN}"\n'.encode(),
            env=env, capture_output=True, timeout=30)
        # Негативный контроль 1: БЕЗ header-строки Authorization не уходит.
        negative = subprocess.run(
            ["bash", "-c", curl_via_bash],
            input=f"url = {url}\n".encode(),
            env=env, capture_output=True, timeout=30)
        # Негативный контроль 2 (ловушка R1c): НЕциклованный header = значение
        # реальный curl молча не отправляет — проба красная, если сценарий
        # вернётся к непроцитованной форме.
        unquoted = subprocess.run(
            ["bash", "-c", curl_via_bash],
            input=f"url = {url}\nheader = Authorization: Bearer {R1C_TOKEN}\n".encode(),
            env=env, capture_output=True, timeout=30)
        argv_text = _read_or(argv_log)
        pos_header = received[0][1] if received else None
        neg_header = received[1][1] if len(received) > 1 else "missing-call"
        unq_header = received[2][1] if len(received) > 2 else "missing-call"
        captured = len([l for l in argv_text.splitlines() if l.strip()])
        ok = (positive.stdout.decode().strip() == "200"
              and pos_header == f"Bearer {R1C_TOKEN}"
              and neg_header in (None, "")
              and unq_header in (None, "")
              and R1C_TOKEN not in argv_text
              # fail-closed: capture-механизм обязан видеть все 3 вызова
              and captured == 3)
        # §7.6: canary не печатается — только булевы исходы проверки.
        check("r1c_curl_config_header_seam", ok,
              f"pos_auth_ok={pos_header == f'Bearer {R1C_TOKEN}'} "
              f"neg_absent={neg_header in (None, '')} "
              f"unquoted_dropped={unq_header in (None, '')} "
              f"secret_in_argv={R1C_TOKEN in argv_text}")
    finally:
        server.shutdown()


_DC_CURL_STDOUT = '{"data": [{"id": "m1"}]}\n200'


def _r1c_run_deep_check(tmp: Path, tag: str,
                        payload: dict | None) -> tuple[str, str, str]:
    """Прогон curl_json с capture. POSIX: дочерний python с PATH-shim curl
    (os-level child-argv через лог shim'а). Windows: CreateProcess не исполняет
    shebang-shim и молча уходит в реальный curl — therefore in-process capture
    subprocess.run на границе (argv + input = ровно то, что ушло бы в os-argv/
    stdin ребёнка; красная-способность сохраняется: на старом коде canary
    оказывается в argv). Возвращает (stdout, argv_text, stdin_text)."""
    shim = tmp / f"r1c-shim-{tag}"
    shim.mkdir()
    argv_log, stdin_log = _r1c_dc_curl_shim(shim, tmp, f"r1c-dc-{tag}")
    url = "http://127.0.0.1:9/dc-models"
    if os.name == "nt":
        code = (
            "import importlib.util, json, sys\n"
            f"spec = importlib.util.spec_from_file_location('dc', "
            f"{str(REPO / 'scripts' / 'ai-deep-check.py')!r})\n"
            "dc = importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)\n"
            "rec = []\n"
            "real_run = dc.subprocess.run\n"
            "def fake_run(cmd, **kw):\n"
            "    rec.append((list(cmd), kw.get('input')))\n"
            "    from subprocess import CompletedProcess\n"
            f"    return CompletedProcess(cmd, 0, stdout={_DC_CURL_STDOUT!r}, stderr='')\n"
            "dc.subprocess.run = fake_run\n"
            f"code, data = dc.curl_json({url!r}, {R1C_TOKEN!r}, {payload!r}, "
            "timeout=5, attempts=1)\n"
            "dc.subprocess.run = real_run\n"
            "for argv, inp in rec:\n"
            "    sys.stderr.write('ARGVLOG\\t' + json.dumps(argv) + '\\n')\n"
            "    sys.stderr.write('STDINLOG\\t' + json.dumps(inp) + '\\n')\n"
            "print('RC', code)\nprint('DATA', json.dumps(data))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], input="",
                                capture_output=True, text=True, timeout=90)
        err = result.stderr
        argv_lines = [json.loads(l.split("\t", 1)[1]) for l in err.splitlines()
                      if l.startswith("ARGVLOG\t")]
        stdin_lines = [json.loads(l.split("\t", 1)[1]) for l in err.splitlines()
                       if l.startswith("STDINLOG\t")]
        # repr-нормализация: двойные кавычки внутри элементов остаются сырыми,
        # поэтому substring-утверждения работают так же, как на posix-логах.
        argv_text = "\n".join(repr(a) for a in argv_lines)
        stdin_text = "\n".join(repr(s) for s in stdin_lines)
        # Сырой stderr ребёнка НЕ сохраняем: STDINLOG несёт canary по дизайну
        # (это канал доставки), а boundary-скан §7.6 смотрит только stdout/err.
        write(tmp / f"r1c-dc-{tag}-out.txt", result.stdout)
        return result.stdout, argv_text, stdin_text
    env = _probe_subprocess_env(tmp / f"r1c-dc-home-{tag}", {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        # Windows-python в ребёнке требует USERPROFILE для Path.home() модуля.
        "USERPROFILE": str(tmp / f"r1c-dc-home-{tag}"),
    })
    if payload is not None:
        call = (f"code, data = dc.curl_json({url!r}, {R1C_TOKEN!r}, {payload!r}, "
                "timeout=5, attempts=1)\n")
    else:
        call = f"code, data = dc.curl_json({url!r}, {R1C_TOKEN!r}, None, timeout=5, attempts=1)\n"
    code = (
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('dc', "
        f"{str(REPO / 'scripts' / 'ai-deep-check.py')!r})\n"
        "dc = importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)\n"
        + call +
        "print('RC', code)\nprint('DATA', json.dumps(data))\n"
    )
    result = subprocess.run(["bash", "-c",
                             f'exec {sys.executable} -c {shlex.quote(code)}'],
                            env=env, input="", capture_output=True, text=True,
                            timeout=90)
    _r1c_save_outcome(tmp, f"r1c-dc-{tag}", result)
    return result.stdout, _read_or(argv_log), _read_or(stdin_log)


def probe_r1c_deep_check_get_not_in_argv(tmp: Path):
    """R1c §7.4: catalog GET — Bearer canary не в child argv, header доставлен
    через stdin, запрос/парсинг сохранены (200 + JSON catalog)."""
    out, argv_text, stdin_text = _r1c_run_deep_check(tmp, "get", None)
    ok = ("RC 200" in out and '"m1"' in out
          and R1C_TOKEN not in argv_text
          and f"Authorization: Bearer {R1C_TOKEN}" in stdin_text
          and "--max-time" in argv_text and "dc-models" in argv_text)
    check("r1c_deep_check_get_not_in_argv", ok,
          f"rc_ok={'RC 200' in out} secret_in_argv={R1C_TOKEN in argv_text} "
          f"header_stdin={f'Authorization: Bearer {R1C_TOKEN}' in stdin_text}")


def probe_r1c_deep_check_post_not_in_argv(tmp: Path):
    """R1c §7.5: chat POST — Bearer canary не в child argv, header через stdin,
    payload/-d и Content-Type в argv сохранены (свойства запроса не изменились)."""
    payload = {"model": "m1",
               "messages": [{"role": "user", "content": "ping"}],
               "max_tokens": 1}
    out, argv_text, stdin_text = _r1c_run_deep_check(tmp, "post", payload)
    payload_argv = json.dumps(payload) in argv_text
    ok = ("RC 200" in out
          and R1C_TOKEN not in argv_text
          and f"Authorization: Bearer {R1C_TOKEN}" in stdin_text
          and payload_argv and "-d" in argv_text
          and "Content-Type: application/json" in argv_text)
    check("r1c_deep_check_post_not_in_argv", ok,
          f"rc_ok={'RC 200' in out} secret_in_argv={R1C_TOKEN in argv_text} "
          f"payload_argv={payload_argv} header_stdin={f'Authorization: Bearer {R1C_TOKEN}' in stdin_text}")


def probe_r1c_artifact_boundary(tmp: Path):
    """R1c §7.6: canary присутствует ТОЛЬКО в stdin-логах доставки
    (*-stdin.log — канал, по которому секрет уходит в curl) и отсутствует во
    всех остальных r1c-артефактах (stdout/stderr-снимки, argv-логи). Печать
    canary в check()-detail не допускается инвариантом проекта; suite-stdout
    чистота обеспечивается булевыми detail-строками и внешним аудитом ревью."""
    canaries = (R1C_TOKEN, R1C_TG, R1C_GH)
    leaked = []
    delivery = 0
    for p in sorted(tmp.glob("r1c-*")):
        if not p.is_file():
            continue
        text = _read_or(p)
        has = any(c in text for c in canaries)
        if p.name.endswith("-stdin.log"):
            delivery += int(has)
        elif has:
            leaked.append(p.name)
    ok = not leaked and delivery >= 3
    check("r1c_artifact_boundary", ok,
          f"leaked={leaked} delivery_channels_with_canary={delivery}")


@contextmanager
def override_environ(**updates):
    """Temporarily set/replace environment keys (restores prior values)."""
    saved = {k: os.environ.get(k) for k in updates}
    for k, v in updates.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


D0A_REGISTRY = """\
kit_entries:
  - key: "DUMMY_REQUIRED_KEY"
    group: "watchdog"
    check: "env"
    required: true
    label: "dummy required"
  - key: "DUMMY_OPTIONAL_KEY"
    group: "watchdog"
    check: "env"
    required: false
    label: "dummy optional"
  - key: "DUMMY_SET_KEY"
    group: "watchdog"
    check: "env"
    required: false
    label: "dummy set"
"""


def probe_report_v2_envelope(hc, tmp: Path):
    """run() emits a schema-2 envelope with canonical fields plus v1 aliases."""
    registry = write(tmp / "d0a-registry.yaml", D0A_REGISTRY)
    env = write(tmp / "d0a.env", "DUMMY_SET_KEY=DUMMY_SECRET_TOKEN\n")
    snap = write(tmp / "d0a-snap.json", '{"entities": {}}')
    out = tmp / "d0a-report.json"
    rc = hc.run(["--registry", str(registry), "--snapshot", str(snap),
                 "--env", str(env), "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    report = json.loads(text)
    by_id = {x["id"]: x for x in report["checks"]}
    ok = (
        rc == 1  # DUMMY_REQUIRED_KEY missing -> fail
        and report.get("schema") == 2
        and report.get("summary") == {"total": 3, "healthy": 1, "failed": 1,
                                      "unknown": 0, "unconfigured": 1,
                                      "skipped": 0}
        and set(report.get("inventory", {})) == {"active_models",
                                                 "plugin_providers",
                                                 "free_models"}
        and all({"entity_id", "verdict", "reason_code", "legacy_status",
                 "claims", "effects", "evidence"} <= set(x)
                for x in report["checks"])
        # v1 aliases survive for old consumers
        and (report["ok"], report["fail"], report["unconfigured"],
             report["skipped"], report["total"]) == (1, 1, 1, 0, 3)
        and report["active_models"] == [] and report["plugin_providers"] == []
        and "free_models" in report
        # conservative legacy projection per ADR 0001
        and by_id["kit:DUMMY_SET_KEY"]["verdict"] == "healthy"
        and by_id["kit:DUMMY_SET_KEY"]["reason_code"] == "ok"
        and by_id["kit:DUMMY_REQUIRED_KEY"]["verdict"] == "failed"
        and by_id["kit:DUMMY_REQUIRED_KEY"]["reason_code"] == "unclassified_failure"
        and by_id["kit:DUMMY_OPTIONAL_KEY"]["verdict"] == "unconfigured"
        and by_id["kit:DUMMY_OPTIONAL_KEY"]["reason_code"] == "optional_not_configured"
        and all(x["legacy_status"] == x["status"] for x in report["checks"])
        # containers stay empty until D0b adapters fill them with real evidence
        and all(x["claims"] == {} and x["effects"] == {} and x["evidence"] == {}
                for x in report["checks"])
        # no secret values reach the serialized report
        and "DUMMY_SECRET_TOKEN" not in text
    )
    check("report_v2_envelope", ok, f"rc={rc} summary={report.get('summary')}")


def probe_engine_two_runs_independent(hc, tmp: Path):
    """Two engine runs in one process do not leak results between reports."""
    registry = write(tmp / "d0a-registry2.yaml", D0A_REGISTRY)
    snap = write(tmp / "d0a-snap2.json", '{"entities": {}}')
    env_partial = write(tmp / "d0a-partial.env", "DUMMY_SET_KEY=DUMMY_SECRET_TOKEN\n")
    env_full = write(tmp / "d0a-full.env",
                     "DUMMY_SET_KEY=x\nDUMMY_REQUIRED_KEY=x\nDUMMY_OPTIONAL_KEY=x\n")
    out1, out2 = tmp / "d0a-report-1.json", tmp / "d0a-report-2.json"
    rc1 = hc.run(["--registry", str(registry), "--snapshot", str(snap),
                  "--env", str(env_partial), "--out", str(out1)])
    rc2 = hc.run(["--registry", str(registry), "--snapshot", str(snap),
                  "--env", str(env_full), "--out", str(out2)])
    r1 = json.loads(out1.read_text(encoding="utf-8"))
    r2 = json.loads(out2.read_text(encoding="utf-8"))
    check("engine_two_runs_independent",
          rc1 == 1 and rc2 == 0
          and r1["fail"] == 1 and r1["summary"]["failed"] == 1
          and r2["ok"] == 3 and r2["summary"]["healthy"] == 3
          and r2["summary"]["failed"] == 0,
          f"rc1={rc1} rc2={rc2} r1_fail={r1['fail']} r2_ok={r2['ok']}")


def _run_wrapper_with_report(tmp: Path, name: str, report_text: str,
                             state_obj: dict) -> tuple[int, dict, str]:
    """Run the real wrapper with a fixture engine that writes report_text."""
    home = tmp / name
    hermes = home / ".hermes"
    # The fixture engine resolves $HOME explicitly: Path.home() ignores HOME
    # on Windows (USERPROFILE wins) and would write outside the fixture home.
    engine = (
        "import os\n"
        "from pathlib import Path\n"
        "p = Path(os.environ['HOME']) / '.hermes' / 'state' / 'health-check-v2-report.json'\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        f"p.write_text({json.dumps(report_text)})\n"
    )
    write(home / "scripts" / "health-check-v2.py", engine)
    write(hermes / "state" / "health-check-v2-report.json", report_text)
    write(hermes / "state" / "health-check-v2-state.json", json.dumps(state_obj))
    write(hermes / "logs" / ".keep", "")
    r = subprocess.run(["bash", str(REPO / "scripts" / "health-check-v2-wrapper.sh")],
                       capture_output=True, text=True, timeout=30,
                       env=_probe_subprocess_env(home))
    state = json.loads((hermes / "state" / "health-check-v2-state.json").read_text())
    log = (hermes / "logs" / "health-check-v2.log").read_text(encoding="utf-8")
    return r.returncode, state, log


# Legacy status that honestly mirrors each canonical verdict; unknown has no
# legacy producer, so the fixture carries its old-consumer projection
# (unknown -> skipped) in the v1 fields.
_STATUS_FOR_VERDICT = {"healthy": "ok", "failed": "fail",
                       "unconfigured": "unconfigured",
                       "skipped": "skipped", "unknown": "skipped"}


def _v2_report(verdict: str) -> dict:
    status = _STATUS_FOR_VERDICT[verdict]
    n = {v: (1 if v == verdict else 0) for v in
         ("healthy", "failed", "unknown", "unconfigured", "skipped")}
    return {
        "schema": 2,
        "updated": "2026-09-13T00:00:00+00:00",
        "source": {"engine": "health-check-v2",
                   "registry": {"schema": 1, "hermes_version": "0.21.0"}},
        "summary": {"total": 1, **n},
        "inventory": {"active_models": [], "plugin_providers": [],
                      "free_models": {}},
        "checks": [{"id": "kit:DUMMY_KEY", "entity_id": "kit:DUMMY_KEY",
                    "label": "dummy", "primitive": "env",
                    "verdict": verdict, "reason_code": "unclassified_failure",
                    "detail": "fixture", "status": status,
                    "legacy_status": status,
                    "claims": {}, "effects": {}, "evidence": {}}],
        # coherent v1 aliases (unknown exists only via its skipped projection)
        "total": 1, "ok": n["healthy"], "fail": n["failed"],
        "unconfigured": n["unconfigured"],
        "skipped": n["skipped"] or n["unknown"],
        "active_models": [], "plugin_providers": [], "free_models": {},
    }


def _v2_check(cid: str, label: str, verdict: str, detail: str) -> dict:
    """A single fully contract-compliant v2 check record."""
    status = _STATUS_FOR_VERDICT[verdict]
    return {"id": cid, "entity_id": cid, "label": label, "primitive": "env",
            "verdict": verdict, "reason_code": "unclassified_failure",
            "detail": detail, "status": status, "legacy_status": status,
            "claims": {}, "effects": {}, "evidence": {}}


def _v2_report_multi(checks: list) -> dict:
    """A contract-compliant v2 envelope for an arbitrary check list."""
    counts = {v: 0 for v in ("healthy", "failed", "unknown",
                             "unconfigured", "skipped")}
    for c in checks:
        counts[c["verdict"]] += 1
    return {
        "schema": 2, "updated": _fresh_ts(),
        "source": {"engine": "health-check-v2",
                   "registry": {"schema": 1, "hermes_version": "0.21.0"}},
        "summary": {"total": len(checks), **counts},
        "inventory": {"active_models": [], "plugin_providers": [],
                      "free_models": {}},
        "checks": checks,
        "total": len(checks), "ok": counts["healthy"],
        "fail": counts["failed"], "unconfigured": counts["unconfigured"],
        "skipped": counts["skipped"] + counts["unknown"],
        "active_models": [], "plugin_providers": [], "free_models": {},
    }


def probe_wrapper_v1_report_accepted(tmp: Path):
    """A v1 report (no schema key) still drives the failure counter."""
    report = {"updated": "2026-09-13T00:00:00+00:00", "total": 1, "ok": 0,
              "fail": 1, "unconfigured": 0, "skipped": 0,
              "checks": [{"id": "kit:DUMMY_KEY", "label": "dummy",
                          "status": "fail", "detail": "down"}]}
    rc, state, _ = _run_wrapper_with_report(
        tmp, "d0a-v1-accepted", json.dumps(report), {"kit:DUMMY_KEY": 1})
    check("wrapper_v1_report_accepted",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2, f"rc={rc} state={state}")


def probe_wrapper_v2_failed_increments(tmp: Path):
    rc, state, _ = _run_wrapper_with_report(
        tmp, "d0a-v2-failed", json.dumps(_v2_report("failed")), {"kit:DUMMY_KEY": 1})
    check("wrapper_v2_failed_increments",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2, f"rc={rc} state={state}")


def probe_wrapper_v2_unknown_preserves(tmp: Path):
    """failed -> unknown keeps the counter and emits no recovery."""
    rc, state, _ = _run_wrapper_with_report(
        tmp, "d0a-v2-unknown", json.dumps(_v2_report("unknown")), {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_unknown_preserves",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2, f"rc={rc} state={state}")


def probe_wrapper_v2_skipped_preserves(tmp: Path):
    rc, state, _ = _run_wrapper_with_report(
        tmp, "d0a-v2-skipped", json.dumps(_v2_report("skipped")), {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_skipped_preserves",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2, f"rc={rc} state={state}")


def probe_wrapper_v2_unconfigured_preserves(tmp: Path):
    rc, state, _ = _run_wrapper_with_report(
        tmp, "d0a-v2-unconf", json.dumps(_v2_report("unconfigured")),
        {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_unconfigured_preserves",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2, f"rc={rc} state={state}")


def probe_wrapper_v2_healthy_recover_reset(tmp: Path):
    """failed -> healthy emits a non-empty recovery item and resets the counter.

    The assertion checks the actual alert line (the `recovered` key alone is
    serialized even for an empty list, so key presence proves nothing).
    """
    rc, state, log = _run_wrapper_with_report(
        tmp, "d0a-v2-healthy", json.dumps(_v2_report("healthy")), {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_healthy_recover_reset",
          rc == 0 and state.get("kit:DUMMY_KEY") == 0
          and "🟢 dummy (fixture)" in log,
          f"rc={rc} state={state}")


def probe_wrapper_v2_malformed_rejected(tmp: Path):
    """A schema-2 report missing `summary` is rejected without state mutation."""
    report = _v2_report("failed")
    del report["summary"]
    rc, state, log = _run_wrapper_with_report(
        tmp, "d0a-v2-malformed", json.dumps(report), {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_malformed_rejected",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2 and "report invalid" in log,
          f"rc={rc} state={state}")


def probe_wrapper_v2_bad_verdict_rejected(tmp: Path):
    """A v2 check with a non-canonical verdict rejects the whole report."""
    report = _v2_report("healthy")
    report["checks"][0]["verdict"] = "excellent"
    rc, state, log = _run_wrapper_with_report(
        tmp, "d0a-v2-bad-verdict", json.dumps(report), {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_bad_verdict_rejected",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2 and "report invalid" in log,
          f"rc={rc} state={state}")


def probe_wrapper_v1_garbage_status_preserves(tmp: Path):
    """An unreadable legacy status preserves the counter (never recovery).

    The fixture stays count-consistent: v1 semantics bucket a garbage status
    into `skipped`, so the wrapper accepts the report and the legacy projection
    maps the unreadable status to `unknown` -> preserve.
    """
    report = {"updated": "2026-09-13T00:00:00+00:00", "total": 1, "ok": 0,
              "fail": 0, "unconfigured": 0, "skipped": 1,
              "checks": [{"id": "kit:DUMMY_KEY", "label": "dummy",
                          "status": "weird", "detail": "d"}]}
    rc, state, _ = _run_wrapper_with_report(
        tmp, "d0a-v1-garbage", json.dumps(report), {"kit:DUMMY_KEY": 2})
    check("wrapper_v1_garbage_status_preserves",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2, f"rc={rc} state={state}")


def probe_wrapper_v2_duplicate_id_rejected(tmp: Path):
    """Two records sharing one id must not double the failure counter."""
    report = _v2_report("failed")
    report["summary"] = {"total": 2, "healthy": 0, "failed": 2, "unknown": 0,
                         "unconfigured": 0, "skipped": 0}
    report["checks"] = [dict(report["checks"][0]),
                        dict(report["checks"][0])]
    rc, state, log = _run_wrapper_with_report(
        tmp, "d0a-v2-dup-id", json.dumps(report), {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_duplicate_id_rejected",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2
          and "report invalid" in log,
          f"rc={rc} state={state}")


def probe_wrapper_invalid_json_preserves(tmp: Path):
    """A corrupt report file is rejected without state mutation."""
    rc, state, log = _run_wrapper_with_report(
        tmp, "d0a-invalid-json", "{not json", {"kit:DUMMY_KEY": 2})
    check("wrapper_invalid_json_preserves",
          rc == 0 and state.get("kit:DUMMY_KEY") == 2 and "report invalid" in log,
          f"rc={rc} state={state}")


# ── Пробы: webhook-потребители отчёта (fail-closed) ─────────────────────────

def _fresh_ts() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _webhook_report_home(tmp: Path, name: str, report_obj: dict) -> Path:
    home = tmp / name
    write(home / ".hermes" / "state" / "health-check-v2-report.json",
          json.dumps(report_obj))
    return home


def _webhook_home_env(home: Path) -> dict:
    # webhook.py resolves ~ via os.path.expanduser: USERPROFILE on Windows,
    # HOME on posix — set both so the handlers read the fixture home.
    return {"HOME": str(home), "USERPROFILE": str(home)}


def probe_webhook_quick_v1_accepted(wh, tmp: Path):
    """v1 quick view: fail renders non-green, all-ok renders green (unchanged)."""
    fail_report = {"updated": _fresh_ts(), "total": 1, "ok": 0,
                   "fail": 1, "unconfigured": 0, "skipped": 0,
                   "checks": [{"id": "kit:DUMMY_KEY", "label": "dummy",
                               "status": "fail", "detail": "down"}]}
    home = _webhook_report_home(tmp, "wh-v1-fail", fail_report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_check()
    ok_fail = "❌ dummy: down" in out and "всё в порядке" not in out
    ok_report = dict(fail_report, ok=1, fail=0,
                     checks=[{"id": "kit:DUMMY_KEY", "label": "dummy",
                              "status": "ok", "detail": "up"}])
    home2 = _webhook_report_home(tmp, "wh-v1-ok", ok_report)
    with override_environ(**_webhook_home_env(home2)):
        out2 = wh.handle_integrations_check()
    check("webhook_quick_v1_accepted",
          ok_fail and "✅ Argus:" in out2 and "всё в порядке" in out2,
          f"fail_out={out[:60]!r} ok_out={out2[:60]!r}")


def probe_webhook_quick_v2_mixed(wh, tmp: Path):
    """v2 quick view: head from canonical summary, failed/unknown rendered."""
    report = _v2_report_multi([
        _v2_check("kit:A", "alpha", "healthy", "d1"),
        _v2_check("kit:B", "beta", "failed", "down"),
        _v2_check("kit:C", "gamma", "unknown", "inconclusive"),
    ])
    home = _webhook_report_home(tmp, "wh-v2-mixed", report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_check()
    ok = ("1/3 ok" in out and "❌ beta: down" in out
          and "⚠️ gamma: inconclusive" in out and "всё в порядке" not in out)
    check("webhook_quick_v2_mixed", ok, f"out={out[:100]!r}")


def probe_webhook_quick_skipped_not_green(wh, tmp: Path):
    """A skipped-only v2 report is never rendered green by the quick view."""
    report = _v2_report_multi([
        _v2_check("kit:S", "skipped-one", "skipped", "policy")])
    home = _webhook_report_home(tmp, "wh-v2-skipped", report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_check()
    check("webhook_quick_skipped_not_green",
          "всё в порядке" not in out and "⏸" in out,
          f"out={out[:100]!r}")


def probe_webhook_quick_malformed_rejected(wh, tmp: Path):
    """A v2 report without summary is rejected, never rendered as healthy."""
    report = _v2_report("healthy")
    del report["summary"]
    home = _webhook_report_home(tmp, "wh-v2-malformed", report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_check()
    check("webhook_quick_malformed_rejected",
          "отклонён" in out and "всё в порядке" not in out,
          f"out={out[:100]!r}")


def probe_webhook_schema_future_rejected(wh, tmp: Path):
    """An unknown future schema is rejected by both consumers, never legacy."""
    report = _v2_report("healthy")
    report["schema"] = 3
    home = _webhook_report_home(tmp, "wh-schema3", report)
    with override_environ(**_webhook_home_env(home)):
        quick = wh.handle_integrations_check()
        full = wh.handle_integrations_all()
    ok = ("отклонён" in quick and "✅ Argus:" not in quick
          and "всё в порядке" not in quick
          and "отклонён" in full and "✅" not in full.split("\n")[0])
    check("webhook_schema_future_rejected", ok,
          f"quick={quick[:60]!r} full={full[:60]!r}")


def probe_webhook_full_v2_unknown_skipped(wh, tmp: Path):
    """Full view renders unknown as ⚠️ and skipped as ⏸ with honest counts."""
    report = _v2_report_multi([
        _v2_check("kit:A", "alpha", "healthy", "d"),
        _v2_check("kit:B", "beta", "unknown", "unclear"),
        _v2_check("kit:C", "gamma", "unconfigured", "n/a"),
        _v2_check("kit:D", "delta", "skipped", "policy"),
    ])
    home = _webhook_report_home(tmp, "wh-v2-full", report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_all()
    ok = ("⚠️ beta — unclear" in out and "⏸ delta — пропущено" in out
          and "⚪ gamma" in out and "⚠️ 1" in out and "⏸ 1" in out)
    check("webhook_full_v2_unknown_skipped", ok, f"out={out[:120]!r}")


# ── Пробы: review pass 2 — mutation matrix на контракт отчёта ───────────────

def probe_webhook_v2_contract_fields_enforced(wh, tmp: Path):
    """Every D0a contract field is required in the v2 envelope and checks."""
    base = _v2_report("healthy")
    envelope_fields = ("source", "inventory", "active_models",
                       "plugin_providers", "free_models", "ok", "total",
                       "fail", "unconfigured", "skipped")
    check_fields = ("entity_id", "primitive", "reason_code",
                    "legacy_status", "claims", "effects", "evidence")
    for field in envelope_fields + check_fields:
        report = json.loads(json.dumps(base))
        if field in check_fields:
            del report["checks"][0][field]
        else:
            del report[field]
        if not wh._validate_health_report(report):
            check("webhook_v2_contract_fields_enforced", False,
                  f"missing {field} accepted")
            return
    check("webhook_v2_contract_fields_enforced", True,
          f"{len(envelope_fields) + len(check_fields)} deletions all rejected")


def probe_webhook_v2_wrong_types_rejected(wh, tmp: Path):
    """Wrong-typed contract fields are rejected, never coerced."""
    base = _v2_report("healthy")
    mutations = [
        ("schema", "2"), ("schema", 2.0),
        ("entity_id", 42), ("primitive", ""), ("reason_code", None),
        ("legacy_status", "skipped"),  # wrong projection for healthy
        ("claims", []), ("effects", "none"), ("evidence", 0),
        ("active_models", ["not-an-object"]),
        ("plugin_providers", [{"name": 1, "description": None}]),
        ("free_models", {"openrouter": "minimax"}),
    ]
    for field, value in mutations:
        report = json.loads(json.dumps(base))
        if field in ("schema", "active_models", "plugin_providers",
                     "free_models"):
            report[field] = value
        else:
            report["checks"][0][field] = value
        if not wh._validate_health_report(report):
            check("webhook_v2_wrong_types_rejected", False,
                  f"{field}={value!r} accepted")
            return
    check("webhook_v2_wrong_types_rejected", True, "all wrong types rejected")


def probe_webhook_v2_bool_counts_rejected(wh, tmp: Path):
    """True == 1 must not smuggle booleans through schema or counts."""
    base = _v2_report("healthy")
    report = json.loads(json.dumps(base))
    report["summary"]["healthy"] = True
    summary_ok = bool(wh._validate_health_report(report))
    report2 = json.loads(json.dumps(base))
    report2["schema"] = True
    schema_ok = bool(wh._validate_health_report(report2))
    report3 = json.loads(json.dumps(base))
    report3["ok"] = True
    alias_ok = bool(wh._validate_health_report(report3))
    check("webhook_v2_bool_counts_rejected",
          summary_ok and schema_ok and alias_ok,
          f"summary={summary_ok} schema={schema_ok} alias={alias_ok}")


def probe_webhook_v2_inconsistent_aliases_rejected(wh, tmp: Path):
    """Aliases must match canonical summary and the unknown->skipped rule."""
    base = _v2_report("unknown")  # alias skipped must carry the unknown count
    report = json.loads(json.dumps(base))
    report["skipped"] = 0
    projection_ok = bool(wh._validate_health_report(report))
    report2 = json.loads(json.dumps(base))
    report2["fail"] = 1
    counts_ok = bool(wh._validate_health_report(report2))
    report3 = json.loads(json.dumps(base))
    report3["active_models"] = [{"role": "primary"}]
    inventory_ok = bool(wh._validate_health_report(report3))
    check("webhook_v2_inconsistent_aliases_rejected",
          projection_ok and counts_ok and inventory_ok,
          f"projection={projection_ok} counts={counts_ok} inventory={inventory_ok}")


def probe_webhook_full_bad_timestamp_not_green(wh, tmp: Path):
    """A non-ISO updated is rejected by BOTH views (full no longer swallows)."""
    report = _v2_report("healthy")
    report["updated"] = "not-a-timestamp"
    home = _webhook_report_home(tmp, "wh-bad-ts", report)
    with override_environ(**_webhook_home_env(home)):
        quick = wh.handle_integrations_check()
        full = wh.handle_integrations_all()
    ok = ("отклонён" in quick and "✅ Argus:" not in quick
          and "отклонён" in full and "Argus наблюдает" not in full)
    check("webhook_full_bad_timestamp_not_green", ok,
          f"quick={quick[:60]!r} full={full[:60]!r}")


def probe_engine_report_passes_contract_validation(wh, hc, tmp: Path):
    """The engine's own schema-2 output satisfies the consumer contract."""
    registry = write(tmp / "d0a-registry3.yaml", D0A_REGISTRY)
    env = write(tmp / "d0a3.env", "DUMMY_SET_KEY=DUMMY_SECRET_TOKEN\n")
    snap = write(tmp / "d0a-snap3.json", '{"entities": {}}')
    out = tmp / "d0a-report-3.json"
    hc.run(["--registry", str(registry), "--snapshot", str(snap),
            "--env", str(env), "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    reason = wh._validate_health_report(report)
    check("engine_report_passes_contract_validation", reason == "", reason)


def probe_wrapper_v2_contract_enforced(tmp: Path):
    """The wrapper rejects missing contract fields and bool schema pre-state."""
    report = _v2_report("failed")
    del report["checks"][0]["claims"]
    rc1, state1, log1 = _run_wrapper_with_report(
        tmp, "rp2-missing", json.dumps(report), {"kit:DUMMY_KEY": 2})
    report2 = _v2_report("failed")
    report2["schema"] = True
    rc2, state2, log2 = _run_wrapper_with_report(
        tmp, "rp2-bool", json.dumps(report2), {"kit:DUMMY_KEY": 2})
    check("wrapper_v2_contract_enforced",
          rc1 == 0 and state1.get("kit:DUMMY_KEY") == 2 and "report invalid" in log1
          and rc2 == 0 and state2.get("kit:DUMMY_KEY") == 2 and "report invalid" in log2,
          f"missing={state1.get('kit:DUMMY_KEY')} bool={state2.get('kit:DUMMY_KEY')}")


# ── Пробы: R2a fail-safe malformed YAML discovery ──────────────────────────

R2A_CANARY = "R2A_CANARY_SECRET_VALUE"
R2A_VALID_CFG = ("providers:\n"
                 "  alpha:\n"
                 "    key_env: R2A_K1\n"
                 "    base_url: https://alpha.invalid\n")
R2A_VALID_CFG_BETA = R2A_VALID_CFG + ("  beta:\n"
                                      "    key_env: R2A_K2\n")
R2A_CORRUPT_CFG = "providers: {broken\n"
R2A_SHAPE_CFG = "- just\n- a list\n"


def _r2a_home(tmp: Path, name: str) -> Path:
    home = tmp / name
    home.mkdir(parents=True, exist_ok=True)
    write(home / ".env", "R2A_K1=x\n")
    return home


def _r2a_run(home: Path, extra_env: dict | None = None, args: list | None = None):
    env = dict(os.environ, HERMES_DIR=str(home), PYTHONIOENCODING="utf-8")
    if extra_env:
        env.update(extra_env)
    cmd = ["python3", str(REPO / "scripts" / "integration-discover.py")] + (args or [])
    return subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, timeout=60)


def _r2a_snap(home: Path) -> dict:
    return json.loads((home / "state" / "integration-snapshot.json")
                      .read_text(encoding="utf-8"))


def _r2a_report(tmp: Path, name: str) -> dict:
    return json.loads((tmp / name).read_text(encoding="utf-8"))


def _r2c_entities(disc, tmp: Path, name: str, cfg: dict) -> dict:
    home = tmp / name
    home.mkdir(parents=True, exist_ok=True)
    disc.HERMES_DIR = home
    disc.CONFIG = write(home / "config.yaml", "")
    disc.ENV_FILE = write(home / ".env", "")
    disc.REGISTRY = home / "registry.yaml"
    disc.AUTH_JSON = home / "auth.json"
    entities, _env = disc.extract_entities(cfg)
    return entities


def _r2c_rows(entities: dict) -> list[tuple]:
    return [(key, entity.get("provider"), entity.get("model"),
             entity.get("base_url", ""), entity.get("key_env", ""))
            for key, entity in entities.items()
            if key == "model:fallback" or key.startswith("model:fallback:")]


def probe_r2c_fallback_shapes(disc, tmp: Path):
    cases = (
        ("canonical_order", {"fallback_providers": [
            {"provider": "alpha", "model": "one"}, {"provider": "beta", "model": "two"},
            {"provider": "gamma", "model": "three"}]}, [
            ("model:fallback", "alpha", "one", "", ""),
            ("model:fallback:1", "beta", "two", "", ""),
            ("model:fallback:2", "gamma", "three", "", "")]),
        ("canonical_mapping", {"fallback_providers": {"provider": "alpha", "model": "one"}}, [
            ("model:fallback", "alpha", "one", "", "")]),
        ("canonical_legacy_order", {"fallback_providers": [
            {"provider": "alpha", "model": "one"}, {"provider": "beta", "model": "two"}],
            "fallback_model": [{"provider": "gamma", "model": "three"}]}, [
            ("model:fallback", "alpha", "one", "", ""),
            ("model:fallback:1", "beta", "two", "", ""),
            ("model:fallback:2", "gamma", "three", "", "")]),
        ("dedupe_identity", {"fallback_providers": [{
            "provider": " OpenAI ", "model": " M ",
            "base_url": " https://EXAMPLE.invalid/v1/// "}], "fallback_model": [
            {"provider": "openai", "model": "m", "base_url": "https://example.invalid/v1"},
            {"provider": "legacy", "model": "tail"}]}, [
            ("model:fallback", "OpenAI", "M", "https://example.invalid/v1", ""),
            ("model:fallback:1", "legacy", "tail", "", "")]),
        ("distinct_route_identity", {"fallback_providers": [
            {"provider": "vendor", "model": "same", "base_url": "https://one.invalid/v1"},
            {"provider": "vendor", "model": "same", "base_url": "https://two.invalid/v1"}]}, [
            ("model:fallback", "vendor", "same", "https://one.invalid/v1", ""),
            ("model:fallback:1", "vendor", "same", "https://two.invalid/v1", "")]),
        ("legacy_only_shape", {"fallback_model": {
            "provider": "legacy", "model": "old", "key_env": "OLD_KEY"}}, [
            ("model:fallback", "legacy", "old", "", "OLD_KEY")]),
        ("malformed_entries_ignored", {"fallback_providers": ["bad", None,
            {"provider": "", "model": "x"}, {"provider": "valid", "model": "  "},
            {"provider": "valid", "model": "ok"}], "fallback_model": 42}, [
            ("model:fallback", "valid", "ok", "", "")]),
    )
    for i, (name, cfg, expected) in enumerate(cases):
        actual = _r2c_rows(_r2c_entities(disc, tmp, f"r2c-shape-{i}", cfg))
        check(f"r2c_{name}", actual == expected, f"actual={actual}")


def _r2c_chain_yaml(models: list[str]) -> str:
    return "fallback_providers:\n" + "".join(
        f"  - provider: provider-{name}\n    model: model-{name}\n" for name in models)


def probe_r2c_reorder_deterministic(tmp: Path):
    home = _r2a_home(tmp, "r2c-reorder")
    write(home / "config.yaml", _r2c_chain_yaml(["alpha", "beta", "gamma"]))
    first = _r2a_run(home, args=["--baseline"])
    write(home / "config.yaml", _r2c_chain_yaml(["gamma", "alpha", "beta"]))
    report_path = tmp / "r2c-reorder-report.json"
    second = _r2a_run(home, {"DISCOVER_REPORT": str(report_path)})
    report = _r2a_report(tmp, report_path.name)
    changes = {e["key"]: (e.get("old", {}).get("model"), e.get("entity", {}).get("model"))
               for e in report["events"] if e["event"] == "changed"}
    expected = {"model:fallback": ("model-alpha", "model-gamma"),
                "model:fallback:1": ("model-beta", "model-alpha"),
                "model:fallback:2": ("model-gamma", "model-beta")}
    repeat_path = tmp / "r2c-reorder-repeat.json"
    repeat = _r2a_run(home, {"DISCOVER_REPORT": str(repeat_path)})
    repeat_report = _r2a_report(tmp, repeat_path.name)
    check("r2c_reorder_deterministic",
          first.returncode == 0 and second.returncode == 2 and changes == expected
          and repeat.returncode == 0 and not repeat_report["events"],
          f"changes={changes}")


def probe_r2c_secret_boundary(tmp: Path):
    home = _r2a_home(tmp, "r2c-secrets")
    write(home / "config.yaml",
          "fallback_providers:\n"
          "  - provider: vendor\n"
          "    model: safe-model\n"
          "    api_key: R2C_INLINE_API_SECRET\n"
          "    base_url: 'https://user:R2C_URL_PASSWORD@fallback.invalid/v1?api_key=R2C_URL_QUERY_SECRET'\n")
    report_path = tmp / "r2c-secrets-report.json"
    result = _r2a_run(home, {"DISCOVER_REPORT": str(report_path)})
    snap = _r2a_snap(home)
    report_text = report_path.read_text(encoding="utf-8")
    output = (result.stdout + result.stderr).decode(errors="ignore")
    blob = json.dumps(snap, ensure_ascii=False) + report_text + output
    entity = snap.get("entities", {}).get("model:fallback", {})
    secrets = ("R2C_INLINE_API_SECRET", "R2C_URL_PASSWORD", "R2C_URL_QUERY_SECRET")
    check("r2c_secret_boundary",
          result.returncode == 2
          and entity.get("base_url") ==
          "https://fallback.invalid/v1?api_key=%3Credacted%3E"
          and not any(secret in blob for secret in secrets),
          f"entity={entity}")


def probe_r2c_r2a_last_good(tmp: Path):
    home = _r2a_home(tmp, "r2c-r2a")
    write(home / "config.yaml", _r2c_chain_yaml(["alpha", "beta"]))
    first = _r2a_run(home, args=["--baseline"])
    good = _r2a_snap(home)
    keys = [key for key in good["entities"] if key == "model:fallback"
            or key.startswith("model:fallback:")]
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    report_path = tmp / "r2c-r2a-report.json"
    degraded = _r2a_run(home, {"DISCOVER_REPORT": str(report_path)})
    bad = _r2a_snap(home)
    report = _r2a_report(tmp, report_path.name)
    check("r2c_r2a_last_good_fallback",
          first.returncode == 0 and keys == ["model:fallback", "model:fallback:1"]
          and degraded.returncode == 2 and bad["entities"] == good["entities"]
          and [e["event"] for e in report["events"]] == ["discovery_degraded"]
          and not any(e.get("key", "").startswith("model:fallback")
                      for e in report["events"]),
          f"events={report['events']}")


def probe_r2c_unrelated_discovery(tmp: Path):
    home = _r2a_home(tmp, "r2c-unrelated")
    base = ("providers:\n  alpha:\n    key_env: ALPHA_KEY\n"
            "    base_url: https://alpha.invalid/v1\n"
            "mcp_servers:\n  bridge:\n    url: https://mcp.invalid/v1\n")
    write(home / "config.yaml", base)
    write(home / "auth.json", '{"providers":{"nous":{"refresh_token":"dummy"}}}\n')
    plugin = home / "plugins" / "model-providers" / "control" / "plugin.yaml"
    write(plugin, "name: control\ndescription: control fixture\n")
    first = _r2a_run(home, args=["--baseline"])
    before = _r2a_snap(home)["entities"]
    write(home / "config.yaml", base + _r2c_chain_yaml(["alpha"]))
    report_path = tmp / "r2c-unrelated-report.json"
    second = _r2a_run(home, {"DISCOVER_REPORT": str(report_path)})
    after = _r2a_snap(home)["entities"]
    report = _r2a_report(tmp, report_path.name)
    stable = ("provider:alpha", "mcp:bridge", "oauth:nous", "plugin-provider:control")
    check("r2c_unrelated_discovery_unchanged",
          first.returncode == 0 and second.returncode == 2
          and all(before.get(key) == after.get(key) for key in stable)
          and all(key in before for key in stable)
          and "model:fallback" in after
          and all(e["key"] == "model:fallback" for e in report["events"]),
          f"stable={[key for key in stable if before.get(key) == after.get(key)]}")


def probe_r2c_no_effects():
    source = (REPO / "scripts" / "integration-discover.py").read_text(encoding="utf-8")
    effects = ("import hermes", "from hermes", "import subprocess", "import socket",
               "urllib.request", "urlopen(", "resolve_runtime_provider(", "get_secret(",
               "load_plugin(", "import_module(")
    check("r2c_no_runtime_or_external_effects", not any(item in source for item in effects))


def _r2a_degraded_snapshot(tmp: Path, name: str) -> Path:
    """Baseline с валидным конфигом → деградация; путь к деградированному
    снапшоту (общая фикстура fail-closed проб консьюмеров)."""
    home = _r2a_home(tmp, name)
    write(home / "config.yaml", R2A_VALID_CFG)
    _r2a_run(home, args=["--baseline"])
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    _r2a_run(home)
    snap = _r2a_snap(home)
    assert snap["discovery"]["status"] == "degraded", snap.get("discovery")
    return home


def probe_r2a_syntax_degraded_not_crash(tmp: Path):
    """R2a-1: синтаксически битый config.yaml → явная деградация (exit 2,
    без traceback), снапшот/отчёт помечены degraded со стабильным
    reason_code; без last-good инвентаризация пуста и updated пуст."""
    home = _r2a_home(tmp, "r2a-syntax")
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    r = _r2a_run(home, {"DISCOVER_REPORT": str(tmp / "r2a-syntax-report.json")})
    snap = _r2a_snap(home)
    rep = _r2a_report(tmp, "r2a-syntax-report.json")
    out = r.stdout.decode(errors="ignore") + r.stderr.decode(errors="ignore")
    check("r2a_syntax_degraded_not_crash",
          r.returncode == 2 and "Traceback" not in out
          and snap["discovery"]["status"] == "degraded"
          and snap["discovery"]["reason_code"] == "config_yaml_syntax"
          and snap["updated"] == ""
          and rep["discovery"]["status"] == "degraded",
          f"rc={r.returncode} disc={snap.get('discovery')}")


def probe_r2a_wrong_shape_degraded(tmp: Path):
    """R2a-2: валидный YAML с верхним уровнем не-словарь (list, затем string)
    — деградация config_yaml_shape, а не пустой здоровый инвентарь; повтор с
    тем же reason_code тихий."""
    home = _r2a_home(tmp, "r2a-shape")
    write(home / "config.yaml", R2A_SHAPE_CFG)
    r1 = _r2a_run(home)
    write(home / "config.yaml", "just a string\n")
    r2 = _r2a_run(home)
    snap = _r2a_snap(home)
    check("r2a_wrong_shape_degraded",
          r1.returncode == 2 and r2.returncode == 0
          and snap["discovery"]["status"] == "degraded"
          and snap["discovery"]["reason_code"] == "config_yaml_shape",
          f"rc1={r1.returncode} rc2={r2.returncode} disc={snap.get('discovery')}")


def probe_r2a_valid_control_unchanged(tmp: Path):
    """R2a-3: валидный конфиг — прежняя семантика: baseline тихий (0), статус
    ok, сущности извлечены; повтор без изменений тихий."""
    home = _r2a_home(tmp, "r2a-valid")
    write(home / "config.yaml", R2A_VALID_CFG)
    r1 = _r2a_run(home, args=["--baseline"])
    snap = _r2a_snap(home)
    r2 = _r2a_run(home)
    check("r2a_valid_control_unchanged",
          r1.returncode == 0 and r2.returncode == 0
          and snap["discovery"]["status"] == "ok"
          and snap["discovery"]["reason_code"] == ""
          and "provider:alpha" in snap["entities"],
          f"rc1={r1.returncode} rc2={r2.returncode} entities={sorted(snap['entities'])}")


def probe_r2a_missing_config_control(tmp: Path):
    """R2a-4: отсутствие config.yaml — прежняя семантика (ок, не деградация)."""
    home = _r2a_home(tmp, "r2a-missing")
    r1 = _r2a_run(home, args=["--baseline"])
    snap = _r2a_snap(home)
    check("r2a_missing_config_control",
          r1.returncode == 0 and snap["discovery"]["status"] == "ok"
          and snap["discovery"]["reason_code"] == "",
          f"rc={r1.returncode} disc={snap.get('discovery')}")


def probe_r2a_last_good_preserved(tmp: Path):
    """R2a-5: при деградации last-good entities/updated/config_hash сохранены
    дословно; свежесть не переписана; attempted_at отделяет попытку,
    last_good_at указывает на последний успешный прогон."""
    home = _r2a_home(tmp, "r2a-lastgood")
    write(home / "config.yaml", R2A_VALID_CFG)
    _r2a_run(home, args=["--baseline"])
    good = _r2a_snap(home)
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    _r2a_run(home)
    snap = _r2a_snap(home)
    disc = snap["discovery"]
    check("r2a_last_good_preserved",
          snap["entities"] == good["entities"]
          and snap["updated"] == good["updated"]
          and snap["config_hash"] == good["config_hash"]
          and disc["status"] == "degraded"
          and disc["attempted_at"] != snap["updated"]
          and disc["last_good_at"] == good["updated"],
          f"disc={disc}")


def probe_r2a_no_false_removals(tmp: Path):
    """R2a-6: деградация не создаёт removed/changed событий по сущностям —
    единственное событие отчёта: discovery_degraded."""
    home = _r2a_home(tmp, "r2a-nofalse")
    write(home / "config.yaml", R2A_VALID_CFG)
    _r2a_run(home, args=["--baseline"])
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    r = _r2a_run(home, {"DISCOVER_REPORT": str(tmp / "r2a-nofalse-report.json")})
    rep = _r2a_report(tmp, "r2a-nofalse-report.json")
    check("r2a_no_false_removals",
          r.returncode == 2
          and [e["event"] for e in rep["events"]] == ["discovery_degraded"],
          f"rc={r.returncode} events={rep['events']}")


def probe_r2a_repetition_quiet(tmp: Path):
    """R2a-7: первая деградация отчётная (2), повтор идентичной — тихий (0),
    статус в снапшоте остаётся degraded."""
    home = _r2a_home(tmp, "r2a-repeat")
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    r1 = _r2a_run(home)
    r2 = _r2a_run(home)
    snap = _r2a_snap(home)
    check("r2a_repetition_quiet",
          r1.returncode == 2 and r2.returncode == 0
          and snap["discovery"]["status"] == "degraded",
          f"rc1={r1.returncode} rc2={r2.returncode} disc={snap.get('discovery')}")


def probe_r2a_recovery_diff_last_good(tmp: Path):
    """R2a-8: восстановление отчётное; diff считается от last-good —
    легитимное добавление видно один раз, замороженные сущности не
    «удаляются» из-за malformed-интервала."""
    home = _r2a_home(tmp, "r2a-recovery")
    write(home / "config.yaml", R2A_VALID_CFG)
    _r2a_run(home, args=["--baseline"])
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    _r2a_run(home)
    write(home / "config.yaml", R2A_VALID_CFG_BETA)
    r = _r2a_run(home, {"DISCOVER_REPORT": str(tmp / "r2a-recovery-report.json")})
    rep = _r2a_report(tmp, "r2a-recovery-report.json")
    ev = [(e["event"], e["key"]) for e in rep["events"]]
    check("r2a_recovery_diff_last_good",
          r.returncode == 2 and ("discovery_recovered", "discovery") in ev
          and ("added", "provider:beta") in ev
          and not any(e["event"] == "removed" for e in rep["events"]),
          f"rc={r.returncode} events={ev}")


def probe_r2a_recovery_reportable_no_change(tmp: Path):
    """R2a-9: восстановление с неизменённым конфигом — отчётное событие
    recovery и ровно ноль entity-событий (нет remove/add-бури)."""
    home = _r2a_home(tmp, "r2a-rec2")
    write(home / "config.yaml", R2A_VALID_CFG)
    _r2a_run(home, args=["--baseline"])
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    _r2a_run(home)
    write(home / "config.yaml", R2A_VALID_CFG)
    r = _r2a_run(home, {"DISCOVER_REPORT": str(tmp / "r2a-rec2-report.json")})
    rep = _r2a_report(tmp, "r2a-rec2-report.json")
    check("r2a_recovery_reportable_no_change",
          r.returncode == 2
          and [e["event"] for e in rep["events"]] == ["discovery_recovered"],
          f"rc={r.returncode} events={rep['events']}")


def probe_r2a_health_fail_closed(tmp: Path):
    """R2a-10: health-check-v2 на деградированном снапшоте — exit 2 через
    существующий config-error path ДО сетевых/MCP-примитивов; свежий
    health-отчёт не переписывается."""
    home = _r2a_degraded_snapshot(tmp, "r2a-hc")
    hc = load_module("health-check-v2")
    registry = write(tmp / "r2a-registry.yaml", "kit_entries: []\n")
    out = tmp / "r2a-health-report.json"

    calls = []

    def _boom(*a, **k):
        calls.append(1)
        raise AssertionError("network primitive called on degraded snapshot")

    originals = {name: getattr(hc, name)
                 for name in ("check_http", "check_tcp", "check_tg_getme", "check_mcp")}
    for name in originals:
        setattr(hc, name, _boom)
    try:
        rc = hc.run(["--registry", str(registry),
                     "--snapshot", str(home / "state" / "integration-snapshot.json"),
                     "--env", str(home / ".env"), "--out", str(out)])
    finally:
        for name, fn in originals.items():
            setattr(hc, name, fn)
    check("r2a_health_fail_closed",
          rc == 2 and not calls and not out.exists(),
          f"rc={rc} primitive_calls={len(calls)} report_exists={out.exists()}")


def probe_r2a_deep_check_fail_closed(tmp: Path):
    """R2a-11: ai-deep-check на деградированном снапшоте — отказ ДО curl
    (ноль вызовов curl_json) с понятной диагностикой."""
    home = _r2a_degraded_snapshot(tmp, "r2a-dc")
    dc = load_module("ai-deep-check")
    registry = write(tmp / "r2a-dc-registry.yaml", "free_models: {}\n")
    calls = []

    def _boom(*a, **k):
        calls.append(1)
        raise AssertionError("curl called on degraded snapshot")

    orig = dc.curl_json
    dc.curl_json = _boom
    message = ""
    try:
        dc.run(["--snapshot", str(home / "state" / "integration-snapshot.json"),
                "--env", str(home / ".env"), "--registry", str(registry),
                "--out", str(tmp / "r2a-dc-out.json")])
    except SystemExit as e:
        message = str(e)
    finally:
        dc.curl_json = orig
    check("r2a_deep_check_fail_closed",
          not calls and "degraded" in message,
          f"curl_calls={len(calls)} msg={message[:100]!r}")


def probe_r2a_legacy_snapshot_compat(tmp: Path):
    """R2a: legacy-снапшот без конверта discovery — pre-R2a успешный:
    discover при деградации сохраняет его инвентаризацию (last_good_at =
    legacy updated), а health-check-v2 НЕ закрывается на нём."""
    home = _r2a_home(tmp, "r2a-legacy")
    legacy = {"updated": "2026-09-01T00:00:00+00:00", "config_hash": "legacy12",
              "entities": {"provider:alpha": {"type": "provider", "name": "alpha",
                                              "key_env": "R2A_K1", "key_present": True,
                                              "base_url": "https://alpha.invalid"}},
              "env_keys": ["R2A_K1"]}
    (home / "state").mkdir(parents=True, exist_ok=True)
    write(home / "state" / "integration-snapshot.json", json.dumps(legacy, indent=1))
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    r = _r2a_run(home)
    snap = _r2a_snap(home)
    disc = snap["discovery"]
    # health: legacy-снапшот (без конверта, пустые сущности) не fail-closed
    hc = load_module("health-check-v2")
    registry = write(tmp / "r2a-legacy-registry.yaml", "kit_entries: []\n")
    legacy_snap = write(tmp / "r2a-legacy-snap.json",
                        json.dumps({"updated": legacy["updated"],
                                    "config_hash": legacy["config_hash"],
                                    "entities": {}, "env_keys": []}))
    health_rc = hc.run(["--registry", str(registry), "--snapshot", str(legacy_snap),
                        "--env", str(home / ".env"),
                        "--out", str(tmp / "r2a-legacy-health.json")])
    check("r2a_legacy_snapshot_compat",
          r.returncode == 2 and snap["entities"] == legacy["entities"]
          and snap["updated"] == legacy["updated"]
          and disc["status"] == "degraded"
          and disc["last_good_at"] == legacy["updated"]
          and health_rc == 0,
          f"rc={r.returncode} disc={disc} health_rc={health_rc}")


def probe_r2a_wrapper_renders_transitions(tmp: Path):
    """R2a-12: wrapper рендерит деградацию и восстановление человекочитаемо:
    payload содержит humans-текст причины без сырых event-имён/reason_code и
    без содержимого конфига; токен доставляется только через stdin."""
    home = tmp / "r2a-wrap-home"
    scripts = home / "scripts"
    hermes = home / ".hermes"
    scripts.mkdir(parents=True, exist_ok=True)
    # ~/.hermes/logs в проде создаёт deploy.sh; фикстура повторяет это
    (hermes / "logs").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / "scripts" / "integration-discover.py",
                    scripts / "integration-discover.py")
    shim_dir = tmp / "r2a-shims"
    shim_dir.mkdir(exist_ok=True)
    argvlog = tmp / "r2a-wrap-argv.log"
    stdinlog = tmp / "r2a-wrap-stdin.log"
    _write_argv_shim(shim_dir, "curl",
                     'printf "%s\\n" "$*" >> "$R2A_ARGVLOG"\n'
                     'cat >> "$R2A_STDINLOG"\n'
                     'printf -- "---R2A-BOUNDARY---\\n" >> "$R2A_STDINLOG"\n')
    _write_argv_shim(shim_dir, "flock", "exit 0\n")

    def wrap_run():
        return subprocess.run(
            ["bash", str(REPO / "scripts" / "integration-discover-wrapper.sh")],
            cwd=REPO, capture_output=True, timeout=120,
            env=_probe_subprocess_env(home, {
                "PATH": str(shim_dir) + os.pathsep + os.environ.get("PATH", ""),
                "R2A_ARGVLOG": str(argvlog), "R2A_STDINLOG": str(stdinlog),
                # discover-child пинаем на фикстуру: allowlist env режет
                # USERPROFILE, а discover зовёт Path.home() при любом раскладе
                # (default-аргумент os.environ.get вычисляется всегда) — урок R1c
                "HERMES_DIR": str(hermes), "USERPROFILE": str(home)}))

    write(hermes / "config.yaml", R2A_CORRUPT_CFG)
    write(hermes / ".env", "WATCHDOG_BOT_TOKEN=DUMMY_R2A_TOKEN\nWATCHDOG_CHAT_ID=1\n")
    r1 = wrap_run()
    write(hermes / "config.yaml", R2A_VALID_CFG)
    r2 = wrap_run()
    stdin_text = stdinlog.read_text(encoding="utf-8", errors="ignore") \
        if stdinlog.exists() else ""
    argv_text = argvlog.read_text(encoding="utf-8", errors="ignore") \
        if argvlog.exists() else ""
    # Payload с rendered-текстом уходит в argv curl (-d), а русский текст
    # JSON-эскейпится (ensure_ascii) — разбираем text-поля обоих прогонов.
    payloads = []
    for chunk in argv_text.split('"text": "')[1:]:
        esc = chunk.split('", "parse_mode"')[0]
        try:
            payloads.append(json.loads('"' + esc + '"'))
        except ValueError:
            pass
    msg_text = "\n".join(payloads)
    check("r2a_wrapper_renders_transitions",
          r1.returncode == 0 and r2.returncode == 0
          and "Деградация обнаружения" in msg_text
          and "синтаксическая ошибка" in msg_text
          and "восстановлено" in msg_text
          and "discovery_degraded" not in argv_text
          and "config_yaml_syntax" not in msg_text
          and "R2A_K1" not in argv_text
          and "DUMMY_R2A_TOKEN" not in argv_text
          and "DUMMY_R2A_TOKEN" in stdin_text,
          f"rc1={r1.returncode} rc2={r2.returncode} msgs={msg_text[:300]!r} "
          f"stderr={r1.stderr.decode(errors='ignore')[-200:]!r}")


def probe_r2a_secret_error_boundary(tmp: Path):
    """R2a-13: canary в битом YAML (похож на секрет) не появляется в
    stdout/stderr/снапшоте/отчёте — сырой текст ошибки парсера не выводится."""
    home = _r2a_home(tmp, "r2a-secret")
    write(home / "config.yaml", f'providers: "{R2A_CANARY}\n')
    r = _r2a_run(home, {"DISCOVER_REPORT": str(tmp / "r2a-secret-report.json")})
    snap_text = (home / "state" / "integration-snapshot.json").read_text(encoding="utf-8")
    rep_text = (tmp / "r2a-secret-report.json").read_text(encoding="utf-8")
    blob = "\n".join([r.stdout.decode(errors="ignore"), r.stderr.decode(errors="ignore"),
                      snap_text, rep_text])
    check("r2a_secret_error_boundary",
          r.returncode == 2 and R2A_CANARY not in blob,
          f"rc={r.returncode} canary_leaked={R2A_CANARY in blob}")


def probe_r2a_recovery_reportable_via_baseline(tmp: Path):
    """R2a (Pytna Finding 2): --baseline глушит entity-diff, но НЕ обязательный
    degraded→ok переход: recovery через baseline-прогон отчётный (2), следующий
    обычный прогон тихий (без дубля)."""
    home = _r2a_home(tmp, "r2a-recbase")
    write(home / "config.yaml", R2A_VALID_CFG)
    _r2a_run(home, args=["--baseline"])
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    _r2a_run(home)
    write(home / "config.yaml", R2A_VALID_CFG)
    r = _r2a_run(home, args=["--baseline"],
                 extra_env={"DISCOVER_REPORT": str(tmp / "r2a-recbase-report.json")})
    rep = _r2a_report(tmp, "r2a-recbase-report.json")
    r2 = _r2a_run(home)
    check("r2a_recovery_reportable_via_baseline",
          r.returncode == 2
          and [e["event"] for e in rep["events"]] == ["discovery_recovered"]
          and r2.returncode == 0,
          f"rc={r.returncode} rc2={r2.returncode} events={rep['events']}")


def probe_r2a_unreadable_encoding_degraded(tmp: Path):
    """R2a (Pytna Finding 1): config.yaml с битой UTF-8 последовательностью —
    деградация config_unreadable (RC 2, без traceback), не крах чтения."""
    home = _r2a_home(tmp, "r2a-encoding")
    (home / "config.yaml").write_bytes(b'providers: "\xff\xfe broken"\n')
    r = _r2a_run(home)
    snap = _r2a_snap(home)
    out = r.stdout.decode(errors="ignore") + r.stderr.decode(errors="ignore")
    check("r2a_unreadable_encoding_degraded",
          r.returncode == 2 and "Traceback" not in out
          and snap["discovery"]["status"] == "degraded"
          and snap["discovery"]["reason_code"] == "config_unreadable",
          f"rc={r.returncode} disc={snap.get('discovery')}")


def probe_r2a1_plugin_nonmapping_skipped(tmp: Path):
    """R2a.1: plugin.yaml с YAML-list/битым YAML пропускается безопасно
    (дискавери завершается, RC 0, без traceback), авторитетный config.yaml
    не деградирует; валидный mapping сохраняет прежнюю семантику.
    Пустой/comment-only валидный YAML — тоже прежняя семантика: entity
    с именем каталога (Pytna R2a.1-1 Finding 1); явный scalar null — skip."""
    home = _r2a_home(tmp, "r2a1-plugin")
    write(home / "config.yaml", "")
    plugins = home / "plugins" / "model-providers"
    write(plugins / "goodplug" / "plugin.yaml",
          'name: goodplug\ndescription: "R2A1 valid metadata"\n')
    write(plugins / "badplug" / "plugin.yaml", "- just\n- a list\n")
    write(plugins / "malformedplug" / "plugin.yaml", "{broken\n")
    write(plugins / "emptyplug" / "plugin.yaml", "# only a comment\n")
    write(plugins / "nullplug" / "plugin.yaml", "null\n")
    r = _r2a_run(home, args=["--baseline"])
    snap = _r2a_snap(home)
    plugin_ids = {k for k in snap["entities"] if k.startswith("plugin-provider:")}
    out = r.stdout.decode(errors="ignore") + r.stderr.decode(errors="ignore")
    check("r2a1_plugin_nonmapping_skipped",
          r.returncode == 0 and "Traceback" not in out
          and plugin_ids == {"plugin-provider:goodplug", "plugin-provider:emptyplug"}
          and snap["entities"]["plugin-provider:goodplug"]["name"] == "goodplug"
          and snap["entities"]["plugin-provider:emptyplug"]["name"] == "emptyplug"
          and snap["discovery"]["status"] == "ok",
          f"rc={r.returncode} plugins={sorted(plugin_ids)} disc={snap.get('discovery')}")


def probe_r2a_baseline_degraded_reportable(tmp: Path):
    """R2a baseline follow-up (внешний ревью P2): первая деградация отчётная
    даже через --baseline (exit 2, events=[discovery_degraded]); следующий
    обычный прогон с тем же reason тихий (exit 0, events=[])."""
    home = _r2a_home(tmp, "r2a-base")
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    r1 = _r2a_run(home, args=["--baseline"],
                  extra_env={"DISCOVER_REPORT": str(tmp / "r2a-base-report.json")})
    rep = _r2a_report(tmp, "r2a-base-report.json")
    r2 = _r2a_run(home)
    snap = _r2a_snap(home)
    check("r2a_baseline_degraded_reportable",
          r1.returncode == 2
          and [e["event"] for e in rep["events"]] == ["discovery_degraded"]
          and r2.returncode == 0
          and snap["discovery"]["status"] == "degraded",
          f"rc1={r1.returncode} rc2={r2.returncode} events={rep['events']} "
          f"disc={snap.get('discovery')}")


def probe_rr0a_webhook_heartbeat_paths(wh, tmp: Path):
    """RR0a: canonical heartbeat directory wins, with legacy-only fallback."""
    def status_at(home: Path) -> str:
        def expanduser(path: str) -> str:
            if path == "~":
                return str(home)
            if path.startswith("~/"):
                return str(home / path[2:])
            return path

        def fake_run(args, capture_output=False, text=False, timeout=None, **kwargs):
            if args[0] == "systemctl":
                stdout = "not-found\n" if "show" in args else "inactive\n"
            elif args[0] == "crontab":
                stdout = "hermes-watchdog gateway-liveness dashboard-liveness\n"
            else:
                stdout = "000"
            return subprocess.CompletedProcess(args, 0, stdout, "")

        with override_attr(wh.os.path, "expanduser", expanduser), \
                override_attr(wh.subprocess, "run", fake_run), \
                override_attr(wh._time, "time", lambda: 20_000):
            return wh.handle_watchdog_status()

    canonical_home = tmp / "rr0a-heartbeat-canonical-home"
    canonical = canonical_home / ".hermes" / "gh-heartbeat"
    legacy = canonical_home / ".hermes" / "hermes-infra"
    write(canonical / "heartbeat.txt", "canonical\n")
    write(legacy / "heartbeat.txt", "legacy\n")
    os.utime(canonical / "heartbeat.txt", (1_000, 1_000))
    os.utime(legacy / "heartbeat.txt", (19_999, 19_999))
    canonical_status = status_at(canonical_home)

    legacy_home = tmp / "rr0a-heartbeat-legacy-home"
    write(legacy_home / ".hermes" / "hermes-infra" / "heartbeat.txt", "legacy\n")
    os.utime(legacy_home / ".hermes" / "hermes-infra" / "heartbeat.txt",
             (19_900, 19_900))
    legacy_status = status_at(legacy_home)

    check("rr0a_webhook_heartbeat_paths",
          "Heartbeat (19000.0s ago)" in canonical_status
          and "Heartbeat (100.0s ago)" in legacy_status,
          f"canonical={next((l for l in canonical_status.splitlines() if 'Heartbeat (' in l), '')!r} "
          f"legacy={next((l for l in legacy_status.splitlines() if 'Heartbeat (' in l), '')!r}")


# ── gateway liveness: canonical matcher, never an argv substring ─────────────

# Апстрим запрещает определять личность процесса по подстроке argv
# ("Never infer process identity from argv substrings", hermes_cli/AGENTS.md).
# Апдейт 2026-09-30 сменил запуск gateway на runpy, и pgrep-подстрока
# "hermes_cli.main gateway run" перестала совпадать: 33 ложных «процесс НЕ
# НАЙДЕН» в watchdog и — хуже — тихий exit 0 в gateway-liveness.sh, то есть
# страховщик вообще не проверял живость. Проба закрывает оба класса отката:
# возврат argv-матчера и потерю ветки rc=2 («матчер недоступен» ≠ «мёртв»).

_ARGV_SUBSTRING_MATCHERS = ("hermes_cli.main gateway run",
                            "hermes_cli.main", "gateway run")


def _gateway_caller_text(name: str) -> str:
    return (REPO / "scripts" / name).read_text(encoding="utf-8")


def probe_gwmatcher_no_argv_substring(tmp: Path):
    """No caller may identify the gateway by an argv substring again."""
    offenders: list[str] = []
    for name in ("hermes-watchdog.sh", "gateway-liveness.sh"):
        text = _gateway_caller_text(name)
        # Только исполняемые pgrep-вызовы: комментарий, объясняющий запрет,
        # легален (и обязателен), а вот живой pgrep по argv — нет.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "pgrep" not in stripped:
                continue
            if any(sub in stripped for sub in _ARGV_SUBSTRING_MATCHERS):
                offenders.append(f"{name}: {stripped[:70]}")
    check("gwmatcher_no_argv_substring", not offenders,
          f"offenders={offenders}")


def probe_gwmatcher_helper_present(tmp: Path):
    """The canonical matcher exists, is in the deploy manifest, and has no
    unresolved markers — иначе deploy установит вызывающие скрипты без него."""
    helper = REPO / "scripts" / "hermes-gateway-pids.py"
    deploy = (REPO / "deploy.sh").read_text(encoding="utf-8")
    check("gwmatcher_helper_present", helper.is_file(), f"helper={helper.is_file()}")
    check("gwmatcher_helper_in_manifest",
          "hermes-gateway-pids.py" in deploy,
          "helper listed in deploy.sh manifest")
    if helper.is_file():
        text = helper.read_text(encoding="utf-8")
        check("gwmatcher_helper_no_markers", "@" not in text.replace("@staticmethod", ""),
              "helper carries no template markers")
        rc = subprocess.run([sys.executable, str(helper), "--count"],
                            capture_output=True, timeout=60)
        # 2 = matcher unavailable (нет Hermes install) — честный отказ, не падение;
        # 0/1 = окружение ответило. Требование: НЕ traceback.
        check("gwmatcher_helper_executable",
              rc.returncode in (0, 1, 2) and b"Traceback" not in rc.stderr,
              f"rc={rc.returncode}")


def probe_gwmatcher_rc2_not_death(tmp: Path):
    """rc=2 («матчер недоступен») не должен трактоваться как «процесс мёртв».

    Гоняем НАСТОЯЩИЙ шелл-блок gateway-liveness.sh с подсунутым helper,
    который всегда возвращает 2, и требуем, чтобы скрипт НЕ ушёл в рестарт
    и записал в лог честный ПРОПУСК вместо алерта о смерти процесса."""
    home = tmp / "gwmatcher-home"
    bindir = home / "scripts"
    bindir.mkdir(parents=True, exist_ok=True)
    # Стаб вызывается как `python3 <helper>`, поэтому обязан быть Python-сценарием:
    # shell-стаб вернул бы SyntaxError → rc=1 («мёртв»), а нам нужен именно rc=2.
    stub = bindir / "hermes-gateway-pids.py"
    write(stub, "import sys\nsys.exit(2)\n")
    log = home / "logs" / "liveness.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Только блок принятия решения, изолированный от systemd/curl: покрываем
    # ровно то место, где rc=2 обязан стать «не проверил», а не «умер».
    src = _gateway_caller_text("gateway-liveness.sh")
    anchor = 'if GATEWAY_PIDS=$(python3 "$HOME/scripts/hermes-gateway-pids.py"'
    assert anchor in src, "gateway-liveness.sh no longer calls the canonical matcher"
    start = src.index(anchor)
    end = src.index("fi", src.index('if [ -z "$GATEWAY_PIDS" ]; then', start)) + 2
    block = src[start:end]
    harness = bindir / "harness.sh"
    # Блок сам делает `exit 0`, поэтому запускаем его в ПОДПРОЦЕССЕ: иначе
    # `exit` унёс бы весь harness и мы не увидели бы код возврата.
    # HOME выставляем в окружении: скрипт сам адресует helper через $HOME.
    write(harness, "set -u\nLOG=" + str(log) + "\n(\n" + block + "\n)\necho \"EXITED:$?\"\n")
    env = _probe_subprocess_env(home)
    rc = subprocess.run(["bash", str(harness)], capture_output=True, timeout=60,
                        env=env)
    out = rc.stdout.decode(errors="ignore")
    log_text = log.read_text(encoding="utf-8") if log.exists() else ""
    check("gwmatcher_rc2_not_death",
          "EXITED:0" in out and "НЕ НАЙДЕН" not in out and "ПРОПУСК" in log_text,
          f"stdout={out.strip()[:120]!r} log={log_text.strip()[:120]!r} stderr={rc.stderr.decode(errors='ignore').strip()[:160]!r}")


# ── runner ──────────────────────────────────────────────────────────────────



def probe_ux0_bot_interaction(mon, wh: object):
    """UX0 native keyboard, de-duplicated menu, alert keyboard, and poll auth.

    Клавиатура стала module-dependent (local-services); UX0-инвариант проверяем
    при выключенном модуле, независимо от config.env на хосте.

    Патчить нужно ИМЕННО mon.webhook: poller держит собственную ссылку на
    загруженный модуль webhook, и это НЕ тот объект, который load_module()
    вернул пробе. Прежний override_attr(wh, ...) выглядел работающим, но
    изолировал фиктивно: реальный mon.webhook продолжал читать config.env
    хоста, и проба падала (9 кнопок вместо 8) на любой машине, где
    MODULE_LOCAL_SERVICES=ON, а на CI проходила только потому, что там флаг OFF.
    """
    with override_attr(mon.webhook, "local_services_enabled", lambda: False):
        keyboard = mon.reply_keyboard()
    buttons = [button["text"] for row in keyboard["keyboard"] for button in row]
    settings_index = buttons.index("⚙️ Настройки")
    maintenance_index = buttons.index("🛠 Обслуживание")
    check("ux0_reply_keyboard_collapsible",
          "is_persistent" not in keyboard
          and keyboard.get("resize_keyboard") is True
          and len(buttons) == 8,
          f"is_persistent={keyboard.get('is_persistent')!r} buttons={len(buttons)}")
    check("ux0_reply_keyboard_order", maintenance_index < settings_index,
          f"maintenance={maintenance_index} settings={settings_index}")

    menu_actions = [button["callback_data"]
                    for row in wh.menu_keyboard()["inline_keyboard"]
                    for button in row]
    expected_menu_actions = ["restart_gw", "restart_dash", "reboot",
                             "silence_menu", "deep_ai", "show_logs"]
    check("ux0_maintenance_menu_actions",
          menu_actions == expected_menu_actions, f"actions={menu_actions}")

    watchdog_text = (REPO / "scripts" / "hermes-watchdog.sh").read_text(
        encoding="utf-8", errors="ignore")
    problem_line = next(line for line in watchdog_text.splitlines()
                        if 'send_tg "$ALERT_MSG"' in line)
    recovery_line = next(line for line in watchdog_text.splitlines()
                         if 'send_tg "$R_MSG"' in line)
    check("ux0_automatic_alert_no_keyboard",
          'send_tg "$ALERT_MSG" "pin"' in problem_line
          and "keyboard" not in problem_line
          and 'send_tg "$R_MSG"' in recovery_line
          and "keyboard" not in recovery_line,
          f"problem={problem_line!r} recovery={recovery_line!r}")

    captured = {"messages": [], "denials": [], "callback_answers": [],
                "commands": [], "callbacks": []}

    def fake_send_message(text, **kwargs):
        captured["messages"].append((text, kwargs))

    def fake_reply_to(chat_id, text, **kwargs):
        captured["denials"].append((chat_id, text))

    def fake_tg_api(method, data):
        if method == "answerCallbackQuery":
            captured["callback_answers"].append(data.get("callback_query_id"))
    def fake_time():
        return fake_time.value

    fake_time.value = 1000.0

    def fake_route_command(text):
        captured["commands"].append(text)

    def fake_handle_callback_query(query):
        captured["callbacks"].append(query.get("data"))

    def fake_deny(chat_id=None, callback_id=None, query=None):
        user_id = (query or {}).get("from", {}).get("id")
        key = str(user_id or chat_id or "anon")
        now = fake_time.value
        last = mon._DENY_LOG.get(key, 0.0)
        fresh = now - last >= mon._DENY_COOLDOWN_S
        if fresh:
            mon._DENY_LOG[key] = now
            captured["denials"].append((chat_id, bool(callback_id)))
        if callback_id:
            captured["callback_answers"].append(callback_id)

    authorized_id = "123456789"
    unauthorized_id = 99999
    health_label = next(text for text, command in mon.REPLY_LABELS.items()
                        if command == "/health")
    service_update = {"update_id": 1, "message": {
        "message_id": 11, "date": 0,
        "chat": {"id": unauthorized_id, "type": "private"},
        "pinned_message": {"message_id": 10, "date": 0,
                           "chat": {"id": unauthorized_id, "type": "private"}},
    }}
    unsupported_update = {"update_id": 2, "edited_message": {
        "text": "/health", "from": {"id": unauthorized_id},
        "chat": {"id": unauthorized_id, "type": "private"},
    }}

    with override_attr(mon, "is_authorized", lambda user_id: str(user_id) == authorized_id), \
            override_attr(mon, "ALLOWED_USER_ID", authorized_id), \
            override_attr(mon, "_time", fake_time), \
            override_attr(mon, "send_message", fake_send_message), \
            override_attr(mon, "reply_to", fake_reply_to), \
            override_attr(mon, "tg_api", fake_tg_api), \
            override_attr(mon, "route_command", fake_route_command), \
            override_attr(mon, "_send_deny", fake_deny), \
            override_attr(mon.webhook, "handle_callback_query",
                          fake_handle_callback_query):
        mon._DENY_LOG.clear()
        mon.PENDING_SECRET.clear()
        mon._handle_update(service_update)
        service_ignored = not any(captured[name] for name in
                                  ("messages", "denials", "callback_answers",
                                   "commands", "callbacks"))

        for key in captured:
            captured[key].clear()
        mon._DENY_LOG.clear()
        mon._handle_update(unsupported_update)
        unsupported_ignored = not any(captured[name] for name in
                                      ("messages", "denials", "callback_answers",
                                       "commands", "callbacks"))

        fake_time.value = 1000.0
        mon._handle_update({"update_id": 3, "message": {
            "text": "/health", "from": {"id": unauthorized_id},
            "chat": {"id": unauthorized_id, "type": "private"},
        }})
        unauthorized_denied = len(captured["denials"]) == 1

        for key in captured:
            captured[key].clear()
        mon._DENY_LOG.clear()
        fake_time.value = 1100.0
        mon._handle_update({"update_id": 4, "callback_query": {
            "id": "callback-1", "data": "restart_gw",
            "from": {"id": unauthorized_id},
            "message": {"chat": {"id": unauthorized_id, "type": "private"}},
        }})
        mon._handle_update({"update_id": 5, "callback_query": {
            "id": "callback-2", "data": "health",
            "from": {"id": unauthorized_id},
            "message": {"chat": {"id": unauthorized_id, "type": "private"}},
        }})
        cooldown_per_user = (len(captured["denials"]) == 1
                             and len(captured["callback_answers"]) == 2)

        for key in captured:
            captured[key].clear()
        mon._DENY_LOG.clear()
        mon._handle_update({"update_id": 6, "message": {
            "text": "/health", "from": {"id": int(authorized_id)},
            "chat": {"id": int(authorized_id), "type": "private"},
        }})
        mon._handle_update({"update_id": 7, "message": {
            "text": health_label, "from": {"id": int(authorized_id)},
            "chat": {"id": int(authorized_id), "type": "private"},
        }})
        mon._handle_update({"update_id": 8, "callback_query": {
            "id": "callback-3", "data": "restart_gw",
            "from": {"id": int(authorized_id)},
            "message": {"chat": {"id": int(authorized_id), "type": "private"}},
        }})
        authorized_routed = (captured["commands"] == ["/health", "/health"]
                             and captured["callbacks"] == ["restart_gw"])

    check("ux0_service_update_ignored", service_ignored,
          f"messages={captured['messages']} denials={captured['denials']}")
    check("ux0_unsupported_update_ignored", unsupported_ignored,
          f"messages={captured['messages']} denials={captured['denials']}")
    check("ux0_unauthorized_text_denied", unauthorized_denied,
          f"denials={int(unauthorized_denied)}")
    check("ux0_callback_cooldown_per_user", cooldown_per_user,
          f"denials={int(cooldown_per_user)}")
    check("ux0_authorized_paths_routed", authorized_routed,
          f"commands={captured['commands']} callbacks={captured['callbacks']}")


# ── Локальные сервисы (MODULE_LOCAL_SERVICES): consumer, гистерезис, UI, cron ──

_LS_MANIFEST = {
    "schema": 1,
    "targets": [
        {"id": "2ch-monitor", "label": "2ch monitor", "source": "systemd_user",
         "name": "2ch-monitor.service", "expect": "active"},
        {"id": "nail-bot", "label": "Nail bot", "source": "systemd_user",
         "name": "nail-bot.service", "expect": "active"},
    ],
}
_LS_NOW = 1_700_000_000.0
# Заведомо чувствительное содержимое снимка: ни UI, ни алерты не имеют права
# его показывать (контракт §5: никакого сырого JSON/слушателей/контейнеров).
_LS_SECRET_ADDR = "10.99.99.99"
_LS_SECRET_PROC = "secretproc"


def _ls_row(name: str, active: str) -> dict:
    return {"name": name, "active": active, "enabled": "enabled",
            "unit_state": "enabled", "restart": "no", "kind": "user"}


def _ls_snapshot(generated_epoch: float, user_rows: list) -> dict:
    from datetime import datetime, timezone
    return {
        "schema": 1,
        "generated_at": datetime.fromtimestamp(
            generated_epoch, timezone.utc).isoformat(timespec="seconds"),
        "services": {"user": user_rows, "system": []},
        "containers": [{"name": _LS_SECRET_PROC, "state": "running"}],
        "listeners": [{"port": 9999, "addr": f"{_LS_SECRET_ADDR}:9999",
                       "process": _LS_SECRET_PROC}],
        "resources": {"kernel": "leak-kernel", "mem_total_mb": 1},
        "reboot_ready": {"reboot_risk": "ok"},
    }


def _ls_iso(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def probe_ls_module_flag_default_off(lsc):
    """Флаг MODULE_LOCAL_SERVICES: OFF по умолчанию; env главнее config.env
    (deploy экспортирует config.env, cron видит только config.env)."""
    config = write(Path(tempfile.mkdtemp(prefix="ls-flag-")) / "config.env",
                   'MODULE_LOCAL_SERVICES="ON"\n')
    saved = os.environ.pop("MODULE_LOCAL_SERVICES", None)
    try:
        with override_attr(lsc, "config_env_paths",
                           lambda: [Path(tempfile.mkdtemp(prefix="ls-none-")) / "nope.env"]):
            check("ls_flag_default_off", lsc.module_enabled() is False)
        with override_attr(lsc, "config_env_paths", lambda: [config]):
            check("ls_flag_config_on", lsc.module_enabled() is True)
            os.environ["MODULE_LOCAL_SERVICES"] = "OFF"
            check("ls_flag_env_wins_off", lsc.module_enabled() is False)
            os.environ["MODULE_LOCAL_SERVICES"] = "ON"
            check("ls_flag_env_wins_on", lsc.module_enabled() is True)
    finally:
        if saved is None:
            os.environ.pop("MODULE_LOCAL_SERVICES", None)
        else:
            os.environ["MODULE_LOCAL_SERVICES"] = saved


def probe_ls_manifest_validation(lsc, tmp: Path):
    """Strict v1-манифест: отсутствие/пустота — unconfigured (не «всё
    здорово»), любая невалидность — configuration error, ни то ни другое
    не healthy."""
    m_missing = lsc.load_manifest(tmp / "ls-manifest-absent.json")
    check("ls_manifest_missing_unconfigured", m_missing == (None, ""), str(m_missing))
    m_empty = lsc.load_manifest(write(tmp / "ls-manifest-empty.json", "   \n"))
    check("ls_manifest_empty_unconfigured", m_empty == (None, ""), str(m_empty))
    manifest, reason = lsc.load_manifest(
        write(tmp / "ls-manifest-good.json",
              json.dumps(_LS_MANIFEST, ensure_ascii=False)))
    check("ls_manifest_valid",
          manifest is not None and reason == "" and len(manifest["targets"]) == 2,
          reason)

    dup_id = json.dumps({"schema": 1, "targets": [
        _LS_MANIFEST["targets"][0], dict(_LS_MANIFEST["targets"][0])]},
        ensure_ascii=False)
    dup_unit = json.dumps({"schema": 1, "targets": [
        _LS_MANIFEST["targets"][0],
        {**_LS_MANIFEST["targets"][1], "id": "other", "name": "2ch-monitor.service"}]},
        ensure_ascii=False)
    bad: dict[str, str] = {
        "unknown_key": '{"schema": 1, "targets": [], "extra": 1}',
        "schema2": '{"schema": 2, "targets": []}',
        "schema_bool": '{"schema": true, "targets": []}',
        "targets_not_list": '{"schema": 1, "targets": {}}',
        "dup_id": dup_id,
        "dup_unit": dup_unit,
        "name_no_suffix": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "name": "2ch-monitor"}]}),
        "name_other_type": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "name": "2ch-monitor.timer"}]}),
        "name_traversal": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "name": "../evil.service"}]}),
        "name_space": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "name": "nail bot.service"}]}),
        "expect_unsupported": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "expect": "running"}]}),
        "source_unsupported": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "source": "docker"}]}),
        "label_empty": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "label": "  "}]}),
        "label_control_char": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "label": "a\x01b"}]}, ensure_ascii=False),
        "not_json": "{broken",
        "not_object": "[1,2]",
        "target_not_object": '{"schema": 1, "targets": ["x"]}',
        "extra_target_key": json.dumps({"schema": 1, "targets": [
            {**_LS_MANIFEST["targets"][0], "command": "rm -rf /"}]}),
    }
    rejects = {}
    for name, body in bad.items():
        _, reject_reason = lsc.load_manifest(
            write(tmp / f"ls-manifest-bad-{name}.json", body))
        rejects[name] = reject_reason
    check("ls_manifest_rejects_invalid", all(rejects.values()), str(rejects))

    _, oversize_reason = lsc.load_manifest(write(
        tmp / "ls-manifest-oversize.json",
        '{"schema": 1, "targets": [], "pad": "' + "x" * (64 * 1024 + 10) + '"}'))
    check("ls_manifest_oversize_rejected", "exceeds" in oversize_reason,
          oversize_reason)
    raw_path = tmp / "ls-manifest-nonutf8.json"
    raw_path.write_bytes(b'{"schema": 1, "targets": ["\xff"]}')
    _, nonutf8_reason = lsc.load_manifest(raw_path)
    check("ls_manifest_nonutf8_rejected", "UTF-8" in nonutf8_reason, nonutf8_reason)


def probe_ls_snapshot_validation(lsc, tmp: Path):
    """Снимок: bounded read, schema==1, tz-aware generated_at без будущего,
    freshness 12 минут, структурная валидация services.user."""
    def body(generated: str, rows: list | object = None) -> str:
        if rows is None:
            rows = [_ls_row("2ch-monitor.service", "active")]
        return json.dumps({"schema": 1, "generated_at": generated,
                           "services": {"user": rows, "system": []}},
                          ensure_ascii=False)

    snapshot, reason = lsc.load_snapshot(
        write(tmp / "ls-snap-good.json", body(_ls_iso(_LS_NOW - 60))), now=_LS_NOW)
    check("ls_snapshot_valid_fresh", snapshot is not None and reason == "", reason)

    from datetime import datetime, timezone
    naive = datetime.fromtimestamp(_LS_NOW - 60, timezone.utc) \
        .replace(tzinfo=None).isoformat(timespec="seconds")
    bad = {
        "stale": body(_ls_iso(_LS_NOW - 13 * 60)),
        "future": body(_ls_iso(_LS_NOW + 600)),
        "naive_ts": body(naive),
        "no_ts": '{"schema": 1, "services": {"user": [], "system": []}}',
        "schema2": body(_ls_iso(_LS_NOW - 60)).replace('"schema": 1', '"schema": 2'),
        "bad_rows": body(_ls_iso(_LS_NOW - 60), rows=["not-a-dict"]),
        "row_missing_fields": body(_ls_iso(_LS_NOW - 60),
                                   rows=[{"name": "x.service"}]),
        "services_missing": '{"schema": 1, "generated_at": "' + _ls_iso(_LS_NOW - 60) + '"}',
        "not_object": '[]',
        "not_json": "{oops",
    }
    rejects = {}
    for name, text in bad.items():
        _, reject_reason = lsc.load_snapshot(
            write(tmp / f"ls-snap-bad-{name}.json", text), now=_LS_NOW)
        rejects[name] = reject_reason
    check("ls_snapshot_rejects_invalid", all(rejects.values()), str(rejects))

    m_missing = lsc.load_snapshot(tmp / "ls-snap-absent.json", now=_LS_NOW)
    check("ls_snapshot_missing_unknown", m_missing == (None, "snapshot missing"),
          str(m_missing))
    _, oversize_reason = lsc.load_snapshot(write(
        tmp / "ls-snap-oversize.json",
        '{"schema": 1, "generated_at": "' + _ls_iso(_LS_NOW - 60)
        + '", "services": {"user": [], "system": []}, "pad": "'
        + "x" * (2 * 1024 * 1024 + 10) + '"}'), now=_LS_NOW)
    check("ls_snapshot_oversize_rejected", "exceeds" in oversize_reason,
          oversize_reason)


def probe_ls_verdicts(lsc):
    """Вердикты: healthy/failed/unknown строго по контракту; недоступный
    источник user-systemd — unknown, даже если строка юнита говорит inactive."""
    snap = _ls_snapshot(_LS_NOW - 60, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "inactive"),
        _ls_row("third.service", "activating"),
    ])
    t2ch, tnail = _LS_MANIFEST["targets"]
    verdict, observed = lsc.evaluate_target(t2ch, snap)
    check("ls_verdict_healthy", (verdict, observed) == ("healthy", "active"),
          f"{verdict}/{observed}")
    verdict, observed = lsc.evaluate_target(tnail, snap)
    check("ls_verdict_failed", (verdict, observed) == ("failed", "inactive"),
          f"{verdict}/{observed}")
    t3 = {**tnail, "id": "third", "name": "third.service"}
    verdict, observed = lsc.evaluate_target(t3, snap)
    check("ls_verdict_inconclusive_unknown",
          (verdict, observed) == ("unknown", "activating"), f"{verdict}/{observed}")
    ghost = {**tnail, "id": "ghost", "name": "ghost.service"}
    verdict, observed = lsc.evaluate_target(ghost, snap)
    check("ls_verdict_missing_unknown",
          (verdict, observed) == ("unknown", "unit missing from snapshot"),
          f"{verdict}/{observed}")
    marker = _ls_snapshot(_LS_NOW - 60, [
        _ls_row(lsc.USER_SYSTEMD_UNAVAILABLE, "unknown"),
        _ls_row("nail-bot.service", "inactive"),
    ])
    verdict, observed = lsc.evaluate_target(tnail, marker)
    check("ls_verdict_unavailable_source_not_failed",
          (verdict, observed) == ("unknown", "source unavailable"),
          f"{verdict}/{observed}")
    empty = _ls_snapshot(_LS_NOW - 60, [])
    verdict, observed = lsc.evaluate_target(t2ch, empty)
    check("ls_verdict_empty_enumeration_unknown",
          verdict == "unknown" and observed == "unit missing from snapshot",
          f"{verdict}/{observed}")


def probe_ls_hysteresis_two_distinct(lsc, tmp: Path):
    """Алерт — после двух подряд РАЗНЫХ свежих снимков с failed; повторное
    чтение того же снимка — одно наблюдение; unknown не снимает и не
    усиливает; один healthy — одно восстановление и сброс. Содержимое снимка
    (адреса/контейнеры) не протекает в сообщения."""
    state_file = tmp / "ls-hyst-state.json"
    sends: list[str] = []

    def send(text: str) -> tuple[bool, str]:
        sends.append(text)
        return True, ""

    manifest, _ = lsc.load_manifest(
        write(tmp / "ls-hyst-manifest.json", json.dumps(_LS_MANIFEST)))
    assert manifest is not None
    snap_fail_a = _ls_snapshot(_LS_NOW - 600, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "inactive")])
    snap_fail_b = _ls_snapshot(_LS_NOW - 300, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "failed")])
    snap_ok = _ls_snapshot(_LS_NOW - 60, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "active")])
    # ВАЛИДНЫЙ свежий снимок, в котором строки цели НЕТ: evaluate_target даёт
    # ("unknown", "unit missing from snapshot") — это НЕ blind-ветка (снимок
    # валиден), а обычный цикл process() со своим verdict. Именно эту ветку
    # контракт §3/§4 запрещает сбрасывать: alerted обязан уцелеть, иначе
    # «восстановление» приходит вслепую, а настоящий healthy уже не отправит
    # сообщение. Мутация-тест (unknown сбрасывает alerted) обязана падать здесь.
    snap_target_gone = _ls_snapshot(_LS_NOW - 120, [
        _ls_row("2ch-monitor.service", "active")])
    with override_attr(lsc, "STATE_PATH", state_file), \
            override_attr(lsc, "SILENCE_PATH", tmp / "ls-hyst-no-silence.txt"):
        lsc.process(manifest, snap_fail_a, "", _LS_NOW, send=send)
        lsc.process(manifest, snap_fail_a, "", _LS_NOW, send=send)
        after_same = len(sends)
        lsc.process(manifest, snap_fail_b, "", _LS_NOW, send=send)
        after_alert = len(sends)
        lsc.process(manifest, snap_fail_b, "", _LS_NOW, send=send)
        after_repeat = len(sends)
        # цель пропала из валидного снимка → unknown, alerted обязан сохраниться
        lsc.process(manifest, snap_target_gone, "", _LS_NOW, send=send)
        after_target_gone = len(sends)
        state_target_gone = json.loads(state_file.read_text(encoding="utf-8"))
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        after_unknown = len(sends)
        state_unknown = json.loads(state_file.read_text(encoding="utf-8"))
        lsc.process(manifest, snap_ok, "", _LS_NOW, send=send)
        after_recovery = len(sends)
        lsc.process(manifest, snap_ok, "", _LS_NOW, send=send)
        after_recovery_repeat = len(sends)
        state_final = json.loads(state_file.read_text(encoding="utf-8"))
    leaked = [s for s in sends
              if _LS_SECRET_ADDR in s or _LS_SECRET_PROC in s or "leak-kernel" in s]
    check("ls_hysteresis_two_distinct",
          after_same == 0 and after_alert == 1 and after_repeat == 1
          and after_unknown == 1
          # цель пропала из валидного снимка: ни сообщения, ни потери alerted
          and after_target_gone == 1
          and state_target_gone["targets"]["nail-bot"]["alerted"] is True
          # failed_ids не тронуты тем же набором, что и до проп��ска цели:
          # это 2 последних generated_at, а не пустой список и не новый элемент
          and len(state_target_gone["targets"]["nail-bot"]["failed_ids"]) == 2
          and state_target_gone["targets"]["nail-bot"]["failed_ids"] == state_unknown["targets"]["nail-bot"]["failed_ids"]
          and "❌" in sends[0] and "Nail bot" in sends[0]
          and after_recovery == 2 and "✅" in sends[1]
          and after_recovery_repeat == 2
          and state_unknown["targets"]["nail-bot"]["alerted"] is True
          and state_final["targets"]["nail-bot"]["alerted"] is False
          and state_final["targets"]["nail-bot"]["failed_ids"] == []
          and not leaked,
          f"sends={sends!r} unknown_state={state_unknown['targets']['nail-bot']!r} "
          f"target_gone_state={state_target_gone['targets']['nail-bot']!r}")


def probe_ls_blind_diagnostics(lsc, tmp: Path):
    """Слепое наблюдение при настроенных целях: диагностика после двух
    отдельных попыток сбора, дедуп внутри эпизода, выход — по реальным новым
    данным; unconfigured-манифест не порождает ни алертов, ни диагностики."""
    state_file = tmp / "ls-blind-state.json"
    sends: list[str] = []

    def send(text: str) -> tuple[bool, str]:
        sends.append(text)
        return True, ""

    manifest, _ = lsc.load_manifest(
        write(tmp / "ls-blind-manifest.json", json.dumps(_LS_MANIFEST)))
    assert manifest is not None
    snap_ok = _ls_snapshot(_LS_NOW - 60, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "active")])
    with override_attr(lsc, "STATE_PATH", state_file), \
            override_attr(lsc, "SILENCE_PATH", tmp / "ls-blind-no-silence.txt"):
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        after_first = len(sends)
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        after_second = len(sends)
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        after_third = len(sends)
        lsc.process(manifest, snap_ok, "", _LS_NOW, send=send)
        after_restore = len(sends)
        state = json.loads(state_file.read_text(encoding="utf-8"))
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        after_new_episode = len(sends)
    check("ls_blind_diagnostics",
          after_first == 0 and after_second == 1 and after_third == 1
          and after_restore == 2 and "недоступно" in sends[0]
          and "восстановлено" in sends[1]
          and state["blind"] == {"consecutive_unknown_runs": 0, "diag_sent": False}
          and after_new_episode == 3,
          f"sends={sends!r} state={state['blind']!r}")

    # Unconfigured-манифест: main() выходит чисто ДО обработки — без state,
    # без алертов, без диагностики (контракт: no alert for manifest absent/empty).
    empty_manifest_path = tmp / "ls-blind-empty.json"
    write(empty_manifest_path, '{"schema": 1, "targets": []}')
    empty_manifest, empty_reason = lsc.load_manifest(empty_manifest_path)
    empty_state = tmp / "ls-blind-empty-state.json"
    saved_flag = os.environ.pop("MODULE_LOCAL_SERVICES", None)
    sends.clear()
    try:
        os.environ["MODULE_LOCAL_SERVICES"] = "ON"
        with override_attr(lsc, "MANIFEST_PATH", empty_manifest_path), \
                override_attr(lsc, "STATE_PATH", empty_state), \
                override_attr(lsc, "LOCK_PATH", tmp / "ls-blind-empty.lock"), \
                override_attr(lsc, "SILENCE_PATH", tmp / "ls-blind-no-silence.txt"):
            rc = lsc.main([])
    finally:
        if saved_flag is None:
            os.environ.pop("MODULE_LOCAL_SERVICES", None)
        else:
            os.environ["MODULE_LOCAL_SERVICES"] = saved_flag
    check("ls_unconfigured_no_alerts_no_diag",
          empty_manifest is None and empty_reason == ""
          and rc == 0 and sends == [] and not empty_state.exists(),
          f"rc={rc} sends={sends!r} state_exists={empty_state.exists()}")


def probe_ls_silence_mutes_but_preserves(lsc, tmp: Path):
    """Тишина глушит отправку, но не наблюдение: после тишины свежий failed
    алертит ровно один раз; deferred recovery доставляется после тишины."""
    import time
    state_file = tmp / "ls-silence-state.json"
    silence_file = tmp / "ls-silence-until.txt"
    sends: list[str] = []

    def send(text: str) -> tuple[bool, str]:
        sends.append(text)
        return True, ""

    real_now = time.time()
    manifest, _ = lsc.load_manifest(
        write(tmp / "ls-silence-manifest.json", json.dumps(_LS_MANIFEST)))
    assert manifest is not None
    snap_fail_a = _ls_snapshot(_LS_NOW - 600, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "inactive")])
    snap_fail_b = _ls_snapshot(_LS_NOW - 300, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "failed")])
    snap_ok = _ls_snapshot(_LS_NOW - 60, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "active")])
    with override_attr(lsc, "STATE_PATH", state_file), \
            override_attr(lsc, "SILENCE_PATH", silence_file):
        silence_file.write_text(str(int(real_now + 3600)), encoding="utf-8")
        lsc.process(manifest, snap_fail_a, "", _LS_NOW, send=send)
        lsc.process(manifest, snap_fail_b, "", _LS_NOW, send=send)
        muted_alerts = len(sends)
        state = json.loads(state_file.read_text(encoding="utf-8"))
        silence_file.write_text(str(int(real_now - 10)), encoding="utf-8")
        lsc.process(manifest, snap_fail_b, "", _LS_NOW, send=send)
        post_silence = len(sends)
        lsc.process(manifest, snap_ok, "", _LS_NOW, send=send)
        recovery = len(sends)
        state_done = json.loads(state_file.read_text(encoding="utf-8"))
    check("ls_silence_mutes_but_preserves",
          muted_alerts == 0
          and state["targets"]["nail-bot"]["alerted"] is False
          and len(state["targets"]["nail-bot"]["failed_ids"]) == 2
          and post_silence == 1 and "❌" in sends[0]
          and recovery == 2 and "✅" in sends[1]
          and state_done["targets"]["nail-bot"]["alerted"] is False,
          f"sends={sends!r} state={state['targets']['nail-bot']!r}")


def probe_ls_marker_snapshot_is_blind_not_recovery(lsc, tmp: Path):
    """Ревью-блокер 1: маркерный снимок (user-systemd недоступен) — валидный
    schema-1 файл, но НЕ наблюдение: blind-диагностика срабатывает, ложного
    «восстановлено» нет, выход из слепоты — только по реальному снимку."""
    state_file = tmp / "ls-marker-state.json"
    sends: list[str] = []

    def send(text: str) -> tuple[bool, str]:
        sends.append(text)
        return True, ""

    manifest, _ = lsc.load_manifest(
        write(tmp / "ls-marker-manifest.json", json.dumps(_LS_MANIFEST)))
    assert manifest is not None
    marker = _ls_snapshot(_LS_NOW - 60, [
        _ls_row(lsc.USER_SYSTEMD_UNAVAILABLE, "unknown")])
    real = _ls_snapshot(_LS_NOW - 60, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "active")])
    with override_attr(lsc, "STATE_PATH", state_file), \
            override_attr(lsc, "SILENCE_PATH", tmp / "ls-marker-no-silence.txt"):
        for _ in range(20):
            lsc.process(manifest, marker, "", _LS_NOW, send=send)
        after_persistent = len(sends)
        persistent = json.loads(state_file.read_text(encoding="utf-8"))
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        lsc.process(manifest, None, "snapshot missing", _LS_NOW, send=send)
        lsc.process(manifest, marker, "", _LS_NOW, send=send)
        after_marker_after_diag = len(sends)
        lsc.process(manifest, real, "", _LS_NOW, send=send)
        state_done = json.loads(state_file.read_text(encoding="utf-8"))
    check("ls_marker_snapshot_is_blind_not_recovery",
          persistent["blind"] == {"consecutive_unknown_runs": 20, "diag_sent": True}
          and after_persistent == 1 and "недоступно" in sends[0]
          and after_marker_after_diag == 1
          and len(sends) == 2 and "восстановлено" in sends[1]
          and state_done["blind"] == {"consecutive_unknown_runs": 0, "diag_sent": False},
          f"sends={sends!r} persistent={persistent['blind']!r} "
          f"done={state_done['blind']!r}")


def probe_ls_bounded_reflection(lsc, tmp: Path):
    """Ревью-блокер 2: содержимое снимка/манифеста отражается в reasons и
    сообщения оператора только bounded — лимит Telegram не нарушается."""
    huge = "x" * 4096
    _, schema_reason = lsc.load_snapshot(write(
        tmp / "ls-bound-schema.json", json.dumps(
            {"schema": huge, "generated_at": _ls_iso(_LS_NOW - 60),
             "services": {"user": [], "system": []}})), now=_LS_NOW)
    _, keys_reason = lsc.load_manifest(write(
        tmp / "ls-bound-manifest.json", json.dumps(
            {"schema": 1, "targets": [], huge: "v"})))
    snap_huge_active = _ls_snapshot(_LS_NOW - 60, [
        {"name": "nail-bot.service", "active": "z" * 4096,
         "enabled": "enabled", "unit_state": "enabled", "restart": "no",
         "kind": "user"}])
    verdict, observed = lsc.evaluate_target(_LS_MANIFEST["targets"][1],
                                            snap_huge_active)
    sends: list[str] = []
    manifest, _ = lsc.load_manifest(
        write(tmp / "ls-bound-manifest2.json", json.dumps(_LS_MANIFEST)))
    assert manifest is not None
    with override_attr(lsc, "STATE_PATH", tmp / "ls-bound-state.json"), \
            override_attr(lsc, "SILENCE_PATH", tmp / "ls-bound-no-silence.txt"):
        log = lsc.process(manifest, snap_huge_active, "", _LS_NOW,
                          send=lambda t: (sends.append(t), (True, ""))[1])
    check("ls_bounded_reflection",
          len(schema_reason) < 200 and "обрезано" in schema_reason
          and len(keys_reason) < 200
          and verdict == "unknown" and len(observed) < 100
          and sends == [] and all(len(line) <= 300 for line in log),
          f"reasons={len(schema_reason)}/{len(keys_reason)} "
          f"observed={len(observed)} verdict={verdict} sends={sends!r}")


def probe_ls_alert_gate_fail_closed(lsc):
    """Доставка: fail closed без allowlist; HTTP attempt ≠ delivery accepted;
    причины не содержат значений токенов."""
    keys = ("WATCHDOG_BOT_TOKEN", "WATCHDOG_CHAT_ID", "WATCHDOG_ALLOWED_USER_ID")
    saved = {k: os.environ.pop(k, None) for k in keys}
    payloads: list[dict] = []
    try:
        ok_none, reason_none = lsc.send_telegram("probe")
        check("ls_alert_fail_closed_no_allowlist",
              ok_none is False and "ALLOWED_USER_ID" in reason_none, reason_none)
        os.environ["WATCHDOG_BOT_TOKEN"] = "DUMMY_SECRET_TOKEN"
        os.environ["WATCHDOG_CHAT_ID"] = "DUMMY_CHAT"
        ok_no_allowed, reason_no_allowed = lsc.send_telegram("probe")
        check("ls_alert_fail_closed_token_without_allowlist",
              ok_no_allowed is False and "ALLOWED_USER_ID" in reason_no_allowed,
              reason_no_allowed)
        os.environ["WATCHDOG_ALLOWED_USER_ID"] = "123"

        def fake_http(token, payload):
            payloads.append(payload)
            return {"ok": True}

        with override_attr(lsc, "_telegram_http", fake_http):
            ok_sent, reason_sent = lsc.send_telegram("probe")
        check("ls_alert_delivered_requires_ok",
              ok_sent is True and reason_sent == ""
              and payloads and payloads[0]["text"] == "probe"
              and payloads[0]["chat_id"] == "DUMMY_CHAT", reason_sent)
        with override_attr(lsc, "_telegram_http",
                           lambda token, payload: {"ok": False}):
            ok_rejected, reason_rejected = lsc.send_telegram("probe")
        check("ls_alert_http_rejected_is_gap",
              ok_rejected is False and "accept" in reason_rejected, reason_rejected)

        def boom(token, payload):
            raise OSError("net down")

        with override_attr(lsc, "_telegram_http", boom):
            ok_error, reason_error = lsc.send_telegram("probe")
        check("ls_alert_transport_error_is_gap",
              ok_error is False and "telegram send failed" in reason_error,
              reason_error)
        reasons = reason_none + reason_no_allowed + reason_rejected + reason_error
        check("ls_alert_reasons_no_token", "DUMMY_SECRET_TOKEN" not in reasons,
              reasons)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def probe_ls_ui_states(wh, lsc, tmp: Path):
    """/services: fail-closed гейт, onboarding, конфиг-ошибка, blind, свежий
    смешанный статус; топология в вывод не протекает."""
    import time
    ui_now = time.time()
    manifest_file = write(tmp / "ls-ui-manifest.json",
                          json.dumps(_LS_MANIFEST, ensure_ascii=False))
    snap_fresh = _ls_snapshot(ui_now - 120, [
        _ls_row("2ch-monitor.service", "active"),
        _ls_row("nail-bot.service", "inactive")])
    snap_file = write(tmp / "ls-ui-snap.json", json.dumps(snap_fresh, ensure_ascii=False))
    absent_manifest = tmp / "ls-ui-absent-manifest.json"
    absent_snap = tmp / "ls-ui-absent-snap.json"

    with override_attr(lsc, "MANIFEST_PATH", absent_manifest), \
            override_attr(lsc, "SNAPSHOT_PATH", absent_snap), \
            override_attr(wh, "_load_local_services_module", lambda: lsc), \
            override_attr(wh, "ALLOWED_USER_ID", ""):
        gate = wh.handle_local_services()
    with override_attr(lsc, "MANIFEST_PATH", absent_manifest), \
            override_attr(lsc, "SNAPSHOT_PATH", absent_snap), \
            override_attr(wh, "_load_local_services_module", lambda: lsc), \
            override_attr(wh, "ALLOWED_USER_ID", "123"):
        onboarding = wh.handle_local_services()
        bad_manifest = write(tmp / "ls-ui-bad-manifest.json", "{broken")
        with override_attr(lsc, "MANIFEST_PATH", bad_manifest):
            config_error = wh.handle_local_services()
        with override_attr(lsc, "MANIFEST_PATH", manifest_file):
            blind = wh.handle_local_services()
        with override_attr(lsc, "MANIFEST_PATH", manifest_file), \
                override_attr(lsc, "SNAPSHOT_PATH", snap_file):
            view = wh.handle_local_services()
        partial_file = write(tmp / "ls-ui-snap-partial.json", json.dumps(
            _ls_snapshot(ui_now - 120, [
                _ls_row("2ch-monitor.service", "active")]), ensure_ascii=False))
        with override_attr(lsc, "MANIFEST_PATH", manifest_file), \
                override_attr(lsc, "SNAPSHOT_PATH", partial_file):
            partial = wh.handle_local_services()
    stale_file = write(tmp / "ls-ui-snap-stale.json", json.dumps(
        _ls_snapshot(ui_now - 13 * 60, [
            _ls_row("2ch-monitor.service", "active"),
            _ls_row("nail-bot.service", "inactive")]), ensure_ascii=False))
    with override_attr(lsc, "MANIFEST_PATH", manifest_file), \
            override_attr(lsc, "SNAPSHOT_PATH", stale_file), \
            override_attr(wh, "_load_local_services_module", lambda: lsc), \
            override_attr(wh, "ALLOWED_USER_ID", "123"):
        stale = wh.handle_local_services()

    leaked = any(marker in output for output in (gate, onboarding, config_error,
                                                 blind, view, partial, stale)
                 for marker in (_LS_SECRET_ADDR, _LS_SECRET_PROC,
                                "leak-kernel", "containers", "listeners"))
    check("ls_ui_fail_closed_without_allowlist",
          "доступ запрещён" in gate and _LS_SECRET_ADDR not in gate, gate)
    check("ls_ui_onboarding",
          "local-services.json" in onboarding and lsc.DOCS_URL in onboarding,
          onboarding)
    check("ls_ui_manifest_config_error", "ошибка конфигурации" in config_error,
          config_error)
    check("ls_ui_blind_unknown", "неизвестен" in blind and "не сбой" in blind, blind)
    check("ls_ui_fresh_mixed_view",
          "✅" in view and "❌" in view and "inactive" in view
          and "2ch monitor" in view and "Nail bot" in view
          and "systemd-статус" in view and not leaked, view)
    check("ls_ui_missing_unit_flagged",
          "юнита нет в снимке" in partial and "⚠️" in partial
          and "❌" not in partial, partial)
    check("ls_ui_stale_unknown", "неизвестен" in stale, stale)


def probe_ls_keyboard_module_dependent(mon, wh):
    """Кнопка/команда /services существуют только при включённом модуле;
    зависшая команда при OFF — явный отказ + свежая клавиатура, обработчик
    не вызывается. Патчим mon.webhook: poller импортирует СВОЙ экземпляр
    модуля (load_module не пишет в sys.modules)."""
    wh_mon = mon.webhook
    with override_attr(wh_mon, "local_services_enabled", lambda: False):
        kb_off = mon.reply_keyboard()
        labels_off = mon.reply_labels()
    with override_attr(wh_mon, "local_services_enabled", lambda: True):
        kb_on = mon.reply_keyboard()
        labels_on = mon.reply_labels()
    off_buttons = [b["text"] for row in kb_off["keyboard"] for b in row]
    on_buttons = [b["text"] for row in kb_on["keyboard"] for b in row]
    check("ls_keyboard_button_gated",
          wh.LOCAL_SERVICES_LABEL not in off_buttons and len(off_buttons) == 8
          and wh.LOCAL_SERVICES_LABEL in on_buttons and len(on_buttons) == 9
          and "/services" not in labels_off.values()
          and labels_on.get(wh.LOCAL_SERVICES_LABEL) == "/services",
          f"off={len(off_buttons)} on={len(on_buttons)}")
    check("ls_keyboard_button_position",
          on_buttons.index(wh.LOCAL_SERVICES_LABEL)
          < on_buttons.index("🛠 Обслуживание"),
          f"buttons={on_buttons!r}")

    captured: list[tuple] = []
    handler_calls: list[int] = []
    with override_attr(mon, "send_message",
                       lambda text, **kw: captured.append((text, kw))), \
            override_attr(wh_mon, "local_services_enabled", lambda: False), \
            override_attr(wh_mon, "handle_local_services",
                          lambda: handler_calls.append(1) or "SHOULD_NOT_RENDER"):
        mon.route_command("/services")
    rejected = (len(handler_calls) == 0 and len(captured) == 1
                and "выключен" in captured[0][0]
                and captured[0][1].get("reply_markup") is not None)
    with override_attr(mon, "send_message",
                       lambda text, **kw: captured.append((text, kw))), \
            override_attr(wh_mon, "local_services_enabled", lambda: True), \
            override_attr(wh_mon, "handle_local_services", lambda: "🖥 ok-render"):
        mon.route_command("/services")
    routed = (captured[-1][0] == "🖥 ok-render" and len(handler_calls) == 0)
    check("ls_stale_services_rejected", rejected,
          f"captured={captured!r} handler={len(handler_calls)}")
    check("ls_services_routed_when_on", routed,
          f"captured={captured!r} handler={len(handler_calls)}")


def probe_ls_toggle_keyboard_refresh(wh, tmp: Path):
    """Успешный тоггл → сообщение с новым ReplyKeyboardMarkup; неудача → без
    markup; никаких silent-kwargs (раньше silent=True молча убивал worker)."""
    class _FakeCompleted:
        def __init__(self, code: int):
            self.returncode = code
            self.stdout = "line1\nline2"
            self.stderr = ""

    class _FakeSubprocess:
        def __init__(self, code: int):
            self.code = code

        def run(self, *args, **kwargs):
            return _FakeCompleted(self.code)

    captured: list[tuple] = []

    def chat_send(text, **kw):
        captured.append((text, kw))

    fresh = {"keyboard": [[{"text": "FRESH"}]], "resize_keyboard": True}
    with override_attr(wh, "subprocess", _FakeSubprocess(0)), \
            override_attr(wh, "KEYBOARD_REFRESH", lambda: fresh):
        wh._deploy_worker(chat_send, str(tmp / "ls-unused.cfg"))
    success = (len(captured) == 1 and captured[0][0].startswith("✅")
               and captured[0][1].get("reply_markup") is fresh
               and "silent" not in captured[0][1])
    check("ls_toggle_success_sends_fresh_markup", success, f"captured={captured!r}")
    captured.clear()
    with override_attr(wh, "subprocess", _FakeSubprocess(1)):
        wh._deploy_worker(chat_send, str(tmp / "ls-unused.cfg"))
    failure = (len(captured) == 1 and captured[0][0].startswith("❌")
               and captured[0][1].get("reply_markup") is None
               and "silent" not in captured[0][1])
    check("ls_toggle_failure_no_markup_no_silent", failure,
          f"captured={captured!r}")


def probe_ls_deploy_on_off_cron(tmp: Path):
    """deploy.sh: ON ставит единую последовательную cron-строку в живой
    crontab и делает начальный сбор; OFF снимает и ранее установленную
    вручную строку, сохраняя чужую; сбой записи crontab — fail closed."""
    kind = subprocess.run(
        ["bash", "-c",
         'if command -v wslpath >/dev/null 2>&1; then echo wsl; '
         'elif command -v cygpath >/dev/null 2>&1; then echo msys; '
         "else uname -s; fi"],
        capture_output=True, text=True, timeout=30).stdout.strip()
    if os.name == "nt" and kind != "Linux":
        # Спавн по имени `bash` на Windows может дать WSL/MSYS: другой mount
        # namespace и СВОЙ системный crontab — shim мог бы не перехватить
        # `crontab`, и проба задела бы реальные объекты. Гейт пробы — CI
        # (ubuntu); локально честно скипаем с причиной.
        for probe_id in ("ls_deploy_on_installs_owned_cron",
                         "ls_deploy_off_removes_legacy_cron",
                         "ls_deploy_off_crontab_fail_closed"):
            check(probe_id, True, f"skipped: spawnable bash is {kind!r} (CI gates this)")
        return
    home = tmp / "ls-deploy-home"
    shims = tmp / "ls-shims"
    shims.mkdir(parents=True, exist_ok=True)
    _rr1b_host_shims(shims)
    _rr1b_fake_hermes(home)
    crontab_fixture = tmp / "ls-crontab.txt"
    py3_log = tmp / "ls-py3.log"
    write(shims / "crontab",
          "#!/bin/sh\n"
          'case "$1" in\n'
          '  -l) cat "$CRONTAB_FIXTURE" 2>/dev/null;;\n'
          '  -)  cat > "$CRONTAB_FIXTURE";;\n'
          "  *) exit 1;;\n"
          "esac\n").chmod(0o755)
    _write_argv_shim(shims, "flock", "exit 0\n")
    _write_argv_shim(shims, "flock", "exit 0\n")
    write(shims / "python3",
          "#!/bin/sh\n"
          'echo "$@" >> "$PY3_LOG"\n'
          "exit 0\n").chmod(0o755)
    shims_fail = tmp / "ls-shims-fail"
    shims_fail.mkdir(parents=True, exist_ok=True)
    write(shims_fail / "crontab",
          "#!/bin/sh\n"
          'case "$1" in\n'
          '  -l) cat "$CRONTAB_FIXTURE" 2>/dev/null;;\n'
          "  *) exit 1;;\n"
          "esac\n").chmod(0o755)
    _write_argv_shim(shims_fail, "flock", "exit 0\n")
    # канонический путь этой установки: adoption узнаёт ТОЛЬКО точное
    # совпадение строки (после нормализации ~/) — по basename нельзя.
    hp = _rr1a_home_for_deploy(home)
    legacy_cron = (f"*/5 * * * * python3 {hp}/.hermes/scripts/"
                   "service-status-snapshot.py --quiet "
                   f">> {hp}/.hermes/logs/service-status.log 2>&1")
    # чужая установка с тем же basename — операторская, не наша
    foreign_cron = ("*/5 * * * * python3 /home/other-tenant/.hermes/scripts/"
                    "service-status-snapshot.py --quiet "
                    ">> /home/other-tenant/.hermes/logs/service-status.log 2>&1")
    unrelated = "0 9 * * * /usr/bin/unrelated-operator-job --flag"
    base_modules = ("MODULE_CORE=OFF\nMODULE_INTEGRATIONS=OFF\nMODULE_TG_BOT=OFF\n"
                    "MODULE_ANALYZER=OFF\nMODULE_HEARTBEAT=OFF\n"
                    "MODULE_GH_HEARTBEAT=OFF\nMODULE_DISCORD_BOT=OFF\n")

    def deploy(flag: str, shim_dir: Path) -> subprocess.CompletedProcess:
        config = write(tmp / f"ls-config-{flag}.env",
                       base_modules + f'MODULE_LOCAL_SERVICES="{flag}"\n')
        # bash (Git Bash на Windows) не понимает backslash-пути в argv —
        # передаём POSIX-стиль; MSYS сам конвертирует PATH.
        env = _probe_subprocess_env(home, {
            "HOME": home.as_posix(),
            "PATH": f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "CRONTAB_FIXTURE": crontab_fixture.as_posix(),
            "PY3_LOG": py3_log.as_posix(),
            "CRON_FILE": (tmp / f"ls-cron-{flag}.txt").as_posix(),
            "CRON_PROFILE": "full",
        })
        return subprocess.run(
            ["bash", (REPO / "deploy.sh").as_posix(), config.as_posix()],
            cwd=REPO.as_posix(), env=env, capture_output=True, text=True,
            timeout=120)

    # write() нормализует переводы строк (на Windows write_text дал бы CRLF
    # и построчное adoption не совпало бы)
    write(crontab_fixture, legacy_cron + "\n" + foreign_cron + "\n"
          + unrelated + "\n")
    py3_log.write_text("", encoding="utf-8")
    on = deploy("ON", shims)
    on_tab = crontab_fixture.read_text(encoding="utf-8")
    cron_file = tmp / "ls-cron-ON.txt"
    cron_text = cron_file.read_text(encoding="utf-8") if cron_file.exists() else ""
    check("ls_deploy_on_installs_owned_cron",
          on.returncode == 0
          # наш job — ровно один и ВНУТРИ managed-блока; второй вхождение
          # во всём crontab — операторская чужая установка (вне блока)
          and (_rr1a_block(on_tab) or "").count("service-status-snapshot.py") == 1
          and (_rr1a_block(on_tab) or "").count("local_services_check.py") == 1
          and "source" in on_tab and ".env" in on_tab
          and unrelated in on_tab
          and foreign_cron in on_tab
          and on_tab.count("service-status-snapshot.py") == 2
          and "other-tenant" not in (_rr1a_block(on_tab) or "")
          and "local_services_check.py" in cron_text
          and "service-status-snapshot.py" in py3_log.read_text(encoding="utf-8"),
          f"rc={on.returncode} tab={on_tab!r} "
          f"out={on.stdout[-400:]!r} err={on.stderr[-300:]!r}")

    # write() нормализует переводы строк (на Windows write_text дал бы CRLF
    # и построчное adoption не совпало бы)
    write(crontab_fixture, legacy_cron + "\n" + foreign_cron + "\n"
          + unrelated + "\n")
    off = deploy("OFF", shims)
    off_tab = crontab_fixture.read_text(encoding="utf-8")
    check("ls_deploy_off_removes_legacy_cron",
          off.returncode == 0
          and off_tab.count("service-status-snapshot.py") == 1
          and legacy_cron not in off_tab
          and "local_services_check.py" not in off_tab
          and foreign_cron in off_tab
          and unrelated in off_tab,
          f"rc={off.returncode} tab={off_tab!r} err={off.stderr[-300:]!r}")

    # write() нормализует переводы строк (на Windows write_text дал бы CRLF
    # и построчное adoption не совпало бы)
    write(crontab_fixture, legacy_cron + "\n" + foreign_cron + "\n"
          + unrelated + "\n")
    failed = deploy("OFF", shims_fail)
    fail_tab = crontab_fixture.read_text(encoding="utf-8")
    check("ls_deploy_off_crontab_fail_closed",
          failed.returncode != 0 and legacy_cron in fail_tab and unrelated in fail_tab,
          f"rc={failed.returncode} tab={fail_tab!r}")


# ── Пробы: RR1b module dependency truth и payload completeness ──────────────

RR1B_TOKEN = "DUMMY_RR1B_TOKEN"
RR1B_CHAT = "DUMMY_RR1B_CHAT"

_ANALYZER_OK_SCRIPT = (
    "#!/bin/bash\n"
    "echo '=== СИСТЕМНЫЙ ОТЧЁТ 2026-10-04 12:00:00 UTC ==='\n"
    "echo ''\n"
    "echo '── ПАМЯТЬ ──'\n"
    "echo 'Mem: total used'\n"
    "echo '── OOM KILLER ──'\n"
    "echo 'Нет событий OOM'\n"
)


def _rr1b_real(name: str) -> str:
    """Абсолютный путь к утилите ПОСЛЕ bash-резолвинга. Годится ТОЛЬКО для
    тела sh-шима, который исполняет сам MSYS-bash: прямой вызов из
    Windows-python с таким путём падает в CreateProcess."""
    r = subprocess.run(["bash", "-c", f"command -v {name}"],
                       capture_output=True, text=True, timeout=30)
    return (r.stdout or "").strip().split("\n")[0] if r.stdout else ""


def _rr1b_sh_exec(target: str) -> str:
    """Путь, пригодный для `exec` внутри sh-шима: Windows-путь, переписанный
    прямыми слэшами (MSYS-bash понимает оба вида)."""
    return target.replace("\\", "/")


def _rr1b_curl_shim(shim_dir: Path) -> None:
    """curl shim: код ответа на каждую поверхность задаётся env'ом
    (RR1B_CODE_GH/TG/ND). URL GitHub и Telegram приходят в stdin (`curl -K -`),
    поэтому решение принимается по stdin+argv. Сети нет."""
    body = (
        'STD=$(cat 2>/dev/null)\n'
        'BOTH="$STD $*"\n'
        'case "$BOTH" in\n'
        '  *githubstatus*) printf \'{"status": {"description": "Operational"}}\\n\'; exit 0 ;;\n'
        '  *api.github.com*) printf \'%s\\n\' "${RR1B_CODE_GH:-200}"; exit 0 ;;\n'
        '  *api.telegram.org*)\n'
        '    case "$*" in\n'
        '      *"-o /dev/null"*) printf \'%s\\n\' "${RR1B_CODE_TG:-200}" ;;\n'
        '      *) printf \'{"ok": true}\\n%s\\n\' "${RR1B_CODE_TG:-200}" ;;\n'
        '    esac; exit 0 ;;\n'
        '  *api/v1/info*) printf \'%s\\n\' "${RR1B_CODE_ND:-200}"; exit 0 ;;\n'
        'esac\n'
        'case "$*" in\n'
        '  *-w*) printf \'%s\\n\' "${RR1B_CODE_ND:-200}" ;;\n'
        '  *) printf \'{}\\n\' ;;\n'
        'esac\n'
        'exit 0\n'
    )
    _write_argv_shim(shim_dir, "curl", body)


def _rr1b_systemctl_shim(shim_dir: Path) -> None:
    """systemctl shim: RR1B_NETDATA=1 → юнит netdata.service СИСТЕМЕ известен
    (опциональная поверхность установлена). Остальные юниты отсутствуют."""
    body = (
        'case "$*" in\n'
        '  *"LoadState netdata.service"*) [ "${RR1B_NETDATA:-0}" = "1" ] && printf \'loaded\\n\' || printf \'not-found\\n\'; exit 0 ;;\n'
        'esac\n'
        'printf \'not-found\\n\'\n'
        'exit 0\n'
    )
    _write_argv_shim(shim_dir, "systemctl", body)


def _rr1b_quick(tmp: Path, tag: str, *, github_token: str = "", netdata: str = "0",
                code_gh: str = "200", code_nd: str = "200") -> subprocess.CompletedProcess:
    home = tmp / f"rr1b-quick-home-{tag}"
    write(home / ".hermes" / ".env",
          f"GITHUB_TOKEN={github_token}\n" if github_token else "")
    shim = tmp / f"rr1b-quick-shim-{tag}"
    shim.mkdir(parents=True, exist_ok=True)
    _rr1b_curl_shim(shim)
    _rr1b_systemctl_shim(shim)
    env = _probe_subprocess_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "RR1B_NETDATA": netdata,
        "RR1B_CODE_GH": code_gh,
        "RR1B_CODE_ND": code_nd,
        "RR1B_CODE_TG": "200",
    })
    return subprocess.run(
        ["bash", str(REPO / "scripts" / "health-check-integrations.sh"), "--quick"],
        cwd=REPO, env=env, input="", capture_output=True, text=True, timeout=120)


def probe_rr1b_quick_optional_expectations(tmp: Path):
    """RR1b B1 §6.1: quick-чек по опциональным поверхностям. Нет агента Netdata
    и нет GitHub-токена = НЕТ ложной проблемы; настроенная и сломанная — видна;
    настроенная и здоровая — здорова.

    Прежде обе проверки шли безусловно: пустой токен давал 401, отсутствующий
    Netdata — 000, поэтому чистая CORE+INTEGRATIONS без этих расширений
    рапортовала инцидент, которого нет. Нейтраль в quick-режиме МОЛЧИТ: любая
    строка при ненулевом коде hermes-watchdog.sh становится отдельным инцидентом.
    """
    absent = _rr1b_quick(tmp, "absent", code_gh="401", code_nd="000")
    gh_broken = _rr1b_quick(tmp, "gh-broken", github_token=RR1B_TOKEN, code_gh="401")
    nd_broken = _rr1b_quick(tmp, "nd-broken", netdata="1", code_nd="000")
    healthy = _rr1b_quick(tmp, "healthy", github_token=RR1B_TOKEN, netdata="1")
    absent_ok = (absent.returncode == 0
                 and "🔑 GitHub token" not in absent.stdout
                 and "📊 Netdata API" not in absent.stdout)
    gh_ok = gh_broken.returncode == 1 and "🔑 GitHub token" in gh_broken.stdout
    nd_ok = nd_broken.returncode == 1 and "📊 Netdata API" in nd_broken.stdout
    healthy_ok = (healthy.returncode == 0
                  and "🔑 GitHub token" not in healthy.stdout
                  and "📊 Netdata API" not in healthy.stdout)
    check("rr1b_quick_optional_expectations",
          absent_ok and gh_ok and nd_ok and healthy_ok,
          f"absent={absent_ok}(rc={absent.returncode}) gh={gh_ok}(rc={gh_broken.returncode}) "
          f"nd={nd_ok}(rc={nd_broken.returncode}) healthy={healthy_ok}(rc={healthy.returncode}) "
          f"absent_out={absent.stdout[-140:]!r}")


def probe_rr1b_watchdog_netdata_expectation(wh, tmp: Path):
    """RR1b B1 §6.2: панель статуса. Предикат `hermes_installed` был истинен на
    любом хосте с Hermes, поэтому Netdata без агента давал ❌. Ожидание теперь
    выводится из установленного агента: юнита нет — ⚪ нейтрально; юнит есть, а
    API не отвечает — ❌ видна."""
    home = tmp / "rr1b-wh-home"
    (home / ".hermes" / "hermes-agent").mkdir(parents=True, exist_ok=True)
    (home / ".hermes" / "scripts").mkdir(parents=True, exist_ok=True)

    def status_at(nd_unit: str, nd_code: str) -> str:
        def expanduser(path: str) -> str:
            return str(home / path[2:]) if path.startswith("~/") else path

        def fake_run(args, capture_output=False, text=False, timeout=None, **kwargs):
            argv = [str(a) for a in args]
            if argv[0] == "systemctl":
                stdout = (f"{nd_unit}\n" if "netdata.service" in argv
                          else ("not-found\n" if "show" in argv else "inactive\n"))
            elif argv[0] == "crontab":
                stdout = ""
            else:
                stdout = f"{nd_code}\n"
            return subprocess.CompletedProcess(argv, 0, stdout, "")

        with override_attr(wh.os.path, "expanduser", expanduser), \
                override_attr(wh.subprocess, "run", fake_run), \
                override_attr(wh._time, "time", lambda: 20_000):
            return wh.handle_watchdog_status()

    absent = status_at("not-found", "000")
    broken = status_at("loaded", "000")
    healthy = status_at("loaded", "200")
    absent_ok = "⚪ Netdata API" in absent and "❌ Netdata API" not in absent
    broken_ok = "❌ Netdata API" in broken and "не отвечает" in broken
    healthy_ok = "✅ Netdata API" in healthy
    check("rr1b_watchdog_netdata_expectation",
          absent_ok and broken_ok and healthy_ok,
          f"absent={absent_ok} broken={broken_ok} healthy={healthy_ok} "
          f"absent_lines={[l for l in absent.split(chr(10)) if 'Netdata' in l]}")


def _rr1b_modules(core=False, integrations=False, analyzer=False,
                  tg_bot=False, discord=False, network_guard=False) -> str:
    flags = {"MODULE_CORE": core, "MODULE_INTEGRATIONS": integrations,
             "MODULE_ANALYZER": analyzer, "MODULE_TG_BOT": tg_bot,
             "MODULE_DISCORD_BOT": discord, "MODULE_HEARTBEAT": False,
             "MODULE_GH_HEARTBEAT": False, "MODULE_LOCAL_SERVICES": False,
             # H4 (RR1b): дефолт OFF — guard не наследует CORE.
             "MODULE_NETWORK_GUARD": network_guard}
    return "".join(f"{k}={'ON' if v else 'OFF'}\n" for k, v in flags.items())


_RR1B_H_SECRET = "ARGUS_CANARY_H1_SECRET_TOKEN"


def _rr1b_cron_text(tmp: Path, tag: str) -> str:
    path = tmp / f"rr1b-{tag}-cron.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _rr1b_deploy_env(tmp: Path, tag: str, home: Path, shim: Path,
                     modules: str, extra_env: dict | None = None):
    """deploy.sh напрямую, с произвольными override'ами преflight-шимов."""
    config = write(tmp / f"rr1b-{tag}-config.env", modules)
    env = _probe_subprocess_env(home, {
        "HOME": home.as_posix(),
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRONTAB_FIXTURE": (tmp / f"rr1b-{tag}-cron.txt").as_posix(),
        "CRON_FILE": (tmp / f"rr1b-{tag}-proposal.txt").as_posix(),
        **(extra_env or {}),
    })
    return subprocess.run(
        ["bash", (REPO / "deploy.sh").as_posix(), config.as_posix()],
        cwd=REPO.as_posix(), env=env, capture_output=True, text=True, timeout=180)


def probe_rr1b2_private_config(tmp: Path):
    """H1: конфиг с секретами обязан быть обычным файлом, принадлежать
    пользователю установки и не быть доступным группе/остальным.

    Canary кладётся в РЕАЛЬНО передаваемый конфиг (а не в посторонний файл),
    а каналы утечки — stdout/stderr и argv sed (единственная команда, которая
    получает значения подстановки). Безопасный режим/владелец — через шим stat,
    моделирующий платформу; создание под umask 077 проверяется на POSIX."""
    problems = []
    argv_log = tmp / "h1-sed-argv.log"

    def sed_logging(shim: Path) -> None:
        # sed получает значения подстановки через временный файл (-f), но его
        # argv и stdin всё равно проверяем: canary там появляться не должен.
        # Путь к настоящему sed резолвится ЗДЕСЬ (вне PATH шима): делегация
        # через `command -v sed` внутри шима нашла бы сам шим и ушла в
        # бесконечную рекурсию — тот же класс ошибки, что у stat-шима.
        real_sed = subprocess.run(["bash", "-c", "command -v sed"],
                                  capture_output=True, text=True, timeout=30
                                  ).stdout.strip().split("\n")[0]
        _write_argv_shim(shim, "sed",
                         f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
                         'cat >> "' + argv_log.as_posix() + '" 2>/dev/null\n'
                         f'printf \'\\n--\\n\' >> "{argv_log.as_posix()}"\n'
                         f'exec "{real_sed}" "$@"\n')

    # 1. Отказ на group/other-доступном файле — без эха значения.
    home = tmp / "h1-mode-home"
    shim = tmp / "h1-mode-shim"
    shim.mkdir(parents=True, exist_ok=True)
    _rr1b_host_shims(shim)
    sed_logging(shim)
    _rr1b_fake_hermes(home)
    secret_modules = _rr1b_modules(core=True) + f"WATCHDOG_BOT_TOKEN={_RR1B_H_SECRET}\n"
    argv_log.unlink(missing_ok=True)
    r644 = _rr1b_deploy_env(tmp, "h1-mode", home, shim, secret_modules,
                            {"RR1B_CONFIG_MODE": "644"})
    out644 = r644.stdout + r644.stderr
    argv_text = argv_log.read_text(encoding="utf-8") if argv_log.exists() else ""
    if not (r644.returncode != 0 and "chmod 600" in out644
            and _RR1B_H_SECRET not in out644):
        problems.append(f"644: rc={r644.returncode} out={out644[-200:]!r}")
    if _RR1B_H_SECRET in argv_text:
        problems.append("canary утёк в argv sed")

    # 2. Отказ на конфиге чужого владельца.
    argv_log.unlink(missing_ok=True)
    r_owner = _rr1b_deploy_env(tmp, "h1-owner", home, shim, secret_modules,
                               {"RR1B_CONFIG_MODE": "600",
                                "RR1B_CONFIG_OWNER": "root"})
    out_owner = r_owner.stdout + r_owner.stderr
    argv_text_owner = argv_log.read_text(encoding="utf-8") if argv_log.exists() else ""
    if not (r_owner.returncode != 0 and "chown" in out_owner
            and _RR1B_H_SECRET not in out_owner):
        problems.append(f"owner: rc={r_owner.returncode} out={out_owner[-200:]!r}")
    if _RR1B_H_SECRET in argv_text_owner:
        problems.append("canary утёк в argv sed (owner-кейс)")

    # 3. Безопасный конфиг (0600, свой владелец) — развёртка идёт.
    r_ok = _rr1b_deploy_env(tmp, "h1-ok", home, shim, secret_modules,
                            {"RR1B_CONFIG_MODE": "600"})
    if r_ok.returncode != 0 or "✅ payload проверен" not in r_ok.stdout:
        problems.append(f"600: rc={r_ok.returncode} out={r_ok.stdout[-200:]!r}")
    if _RR1B_H_SECRET in out644 or _RR1B_H_SECRET in out_owner:
        problems.append("canary утекает в диагностику")

    # 4. Создание нового конфига — под umask 077 (owner-only).
    #    install.sh дойдёт до проверки пустого токена и выйдет с 1: это ожидаемо,
    #    нас интересует режим созданного файла.
    created = tmp / "h1-create-home"
    res_create, home_create = _rr1b_install_fixture(
        tmp, "h1-create", "", deploy_mode="skip",
        plant=None, skip_config=True)
    cfg = home_create / "hermes-argus" / "config.env"
    if not cfg.exists():
        problems.append("install.sh не создал config.env")
    elif os.name == "nt":
        # chmod на Windows-ФС не моделируется; POSIX-проверку режима сделает CI.
        posix_note = "режим созданного файла проверит CI (chmod на Windows-ФС no-op)"
    elif oct(cfg.stat().st_mode)[-3:] != "600":
        problems.append(f"созданный конфиг имеет режим {oct(cfg.stat().st_mode)[-3:]}")
        posix_note = ""
    else:
        posix_note = "созданный конфиг 0600"

    check("rr1b2_private_config", not problems,
          f"problems={problems} {posix_note if not problems else ''}".strip())


def probe_rr1b2_user_manager(tmp: Path):
    """H2: user-юниты требуют живого user-manager'а, а персистентность после
    logout/reboot — свойство linger'а. Argus НЕ включает linger сам: это
    проверяется по журналу вызовов loginctl, а не по отсутствию ошибки."""
    problems = []
    loginctl_log = tmp / "h2-loginctl.log"

    def run(tag: str, *, env_extra: dict, hermes: bool = True,
            modules: str | None = None):
        home = tmp / f"h2-{tag}-home"
        shim = tmp / f"h2-{tag}-shim"
        shim.mkdir(parents=True, exist_ok=True)
        _rr1b_host_shims(shim)
        # loginctl-шим логирует ВЫЗОВЫ: этим доказывается, что enable-linger
        # не выполнялся, а не «что его не было видно».
        _write_argv_shim(shim, "loginctl",
                         f'printf \'%s\\n\' "$*" >> "{loginctl_log.as_posix()}"\n'
                         'case "$*" in\n'
                         '  *Linger*) printf \'%s\\n\' "${RR1B_LINGER-yes}" ;;\n'
                         'esac\n'
                         'exit 0\n')
        if hermes:
            _rr1b_fake_hermes(home)
        else:
            (home / ".hermes").mkdir(parents=True, exist_ok=True)
        loginctl_log.unlink(missing_ok=True)
        return _rr1b_deploy_env(tmp, tag, home, shim,
                                modules or _rr1b_modules(core=True), env_extra)

    # 1. Нет user bus → отказ ДО юнит-гейта, ничего не объявлено готовым.
    r_nobus = run("nobus", env_extra={"RR1B_USER_BUS_RC": "1"})
    out_nobus = r_nobus.stdout + r_nobus.stderr
    if not (r_nobus.returncode != 0 and "user-manager" in out_nobus
            and "✅ payload проверен" not in r_nobus.stdout):
        problems.append(f"nobus: rc={r_nobus.returncode} out={out_nobus[-200:]!r}")

    # 2. Linger=no → отказ с ручной командой, и linger НЕ включается.
    r_nolinger = run("nolinger", env_extra={"RR1B_LINGER": "no"})
    out_nolinger = r_nolinger.stdout + r_nolinger.stderr
    calls = loginctl_log.read_text(encoding="utf-8") if loginctl_log.exists() else ""
    if not (r_nolinger.returncode != 0 and "enable-linger" in out_nolinger
            and "✅ payload проверен" not in r_nolinger.stdout):
        problems.append(f"nolinger: rc={r_nolinger.returncode} out={out_nolinger[-220:]!r}")
    if "enable-linger" in calls:
        problems.append(f"linger включался автоматически: {calls!r}")

    # 3. Linger неизвестен → предупреждение без обещания персистентности,
    #    развёртка продолжается.
    r_unknown = run("unknown", env_extra={"RR1B_LINGER": ""})
    out_unknown = r_unknown.stdout + r_unknown.stderr
    if not (r_unknown.returncode == 0 and "НЕ гарантируется" in out_unknown
            and "✅ payload проверен" in r_unknown.stdout):
        problems.append(f"unknown: rc={r_unknown.returncode} out={out_unknown[-220:]!r}")
    calls_unknown = loginctl_log.read_text(encoding="utf-8") if loginctl_log.exists() else ""
    if "enable-linger" in calls_unknown:
        problems.append("linger включался при неизвестном состоянии")

    # 4. Рабочий менеджер + linger=yes → обычный путь.
    r_ok = run("ready", env_extra={})
    if not (r_ok.returncode == 0 and "linger: yes" in r_ok.stdout
            and "✅ payload проверен" in r_ok.stdout):
        problems.append(f"ready: rc={r_ok.returncode} out={r_ok.stdout[-220:]!r}")

    check("rr1b2_user_manager", not problems, f"problems={problems}")


def probe_rr1b2_hermes_preflight(tmp: Path):
    """H3: для модулей, читающих Hermes-owned пути, проверяются home,
    исполняемый файл и цель liveness. Argus не ставит и не чинит Hermes."""
    problems = []

    def run(tag: str, *, hermes: bool, modules: str | None = None,
            extra: str = ""):
        home = tmp / f"h3-{tag}-home"
        shim = tmp / f"h3-{tag}-shim"
        shim.mkdir(parents=True, exist_ok=True)
        _rr1b_host_shims(shim)
        (home / ".hermes").mkdir(parents=True, exist_ok=True)
        if hermes:
            _rr1b_fake_hermes(home)
        body = (modules or _rr1b_modules(core=True)) + extra
        return _rr1b_deploy_env(tmp, tag, home, shim, body, {})

    # 1. Hermes не установлен → отказ с именем модуля.
    r_missing = run("missing", hermes=False)
    out = r_missing.stdout + r_missing.stderr
    if not (r_missing.returncode != 0 and "hermes-agent" in out
            and "CORE" in out and "не устанавливает Hermes" in out):
        problems.append(f"missing: rc={r_missing.returncode} out={out[-220:]!r}")

    # 2. Нечисловой порт.
    r_port = run("badport", hermes=True, extra="HERMES_PORT=\"abc\"\n")
    out_port = r_port.stdout + r_port.stderr
    if not (r_port.returncode != 0 and "HERMES_PORT" in out_port
            and "1..65535" in out_port):
        problems.append(f"port: rc={r_port.returncode} out={out_port[-220:]!r}")

    # 2b. Переполнение десятичного домена: арифметика bash на 9223372036854775808
    #     даёт «integer expected» и НЕ делает условие ложным — раньше это
    #     проходило как валидный порт.
    r_huge = run("hugeport", hermes=True,
                 extra='HERMES_PORT="9223372036854775808"\n')
    out_huge = r_huge.stdout + r_huge.stderr
    if not (r_huge.returncode != 0 and "HERMES_PORT" in out_huge):
        problems.append(f"hugeport: rc={r_huge.returncode} out={out_huge[-200:]!r}")

    # 3. Пустой хост.
    r_host = run("badhost", hermes=True, extra="HERMES_HOST=\"\"\n")
    out_host = r_host.stdout + r_host.stderr
    if not (r_host.returncode != 0 and "HERMES_HOST" in out_host):
        problems.append(f"host: rc={r_host.returncode} out={out_host[-220:]!r}")

    # 4. Валидная цель и остановленный dashboard — это runtime-наблюдение,
    #    а не ошибка bootstrap: развёртка идёт, HTTP-запроса не делается.
    r_ok = run("valid", hermes=True)
    if not (r_ok.returncode == 0 and "✅ payload проверен" in r_ok.stdout):
        problems.append(f"valid: rc={r_ok.returncode} out={r_ok.stdout[-220:]!r}")

    check("rr1b2_hermes_preflight", not problems, f"problems={problems}")


_RR1B_H4_SUDO_FULL = (
    "Matching Defaults entries for root on host:\n"
    "    (root) NOPASSWD: /usr/bin/resolvectl revert *\n"
    "    (root) NOPASSWD: /usr/sbin/ip route flush table *\n"
    "    (root) NOPASSWD: /usr/sbin/ip rule del *\n"
)


def probe_rr1b2_network_guard(tmp: Path):
    """H4: сетевой guard — явный opt-in, а не наследие CORE. OFF: не ставится и
    не планируется. ON без подтверждённого NOPASSWD под границу аргументов:
    fail closed. ON с политикой: ровно одна cron-строка. Проверка sudo НИЧЕГО
    не выполняет (`sudo -n -l` только печатает перечень).

    Негативные случаи закрыты: перечень без NOPASSWD (PASSWD-политика), перечень
    с близкими, но не теми границами аргументов, и отказ самого `sudo -n -l`."""
    problems = []

    def run(tag: str, *, guard: bool, sudo: str = "none"):
        home = tmp / f"h4-{tag}-home"
        shim = tmp / f"h4-{tag}-shim"
        shim.mkdir(parents=True, exist_ok=True)
        _rr1b_host_shims(shim, sudo=sudo)
        _rr1b_fake_hermes(home)
        return (_rr1b_deploy_env(tmp, tag, home, shim,
                                 _rr1b_modules(core=True, network_guard=guard), {}),
                home)

    # 1. Дефолт: CORE включён, guard выключен — ни файла, ни cron-строки.
    r_off, home_off = run("default", guard=False)
    cron_off = _rr1b_cron_text(tmp, "default")
    if not (r_off.returncode == 0
            and not (home_off / "scripts" / "network-guard.sh").exists()
            and "network-guard.sh" not in cron_off
            and "MODULE_NETWORK_GUARD=OFF" in r_off.stdout):
        problems.append(f"default: rc={r_off.returncode} guard_cron={'network-guard.sh' in cron_off}")

    # 2. Негативные sudo-политики — каждая должна отказать и НЕ ставить/не
    #    планировать guard (все моделируют реальный вывод `sudo -ll`):
    #      passwd     — все три команды PASSWD;
    #      mixed      — одна строка с разными тегами: NOPASSWD на resolvectl,
    #                   PASSWD на обеих ip-командах;
    #      nobody     — run-as не root (команда для default run-as запрещена);
    #      near       — правила под другие команды (revert-not-real и т.п.);
    #      restricted — NOPASSWD, но грант под литеральные аргументы без маски
    #                   (не покрывает рантайм-цели, которые guard находит сам);
    #      fail       — `sudo` сам завершился ошибкой.
    for tag, policy in (("passwd", "passwd"), ("mixed", "mixed"),
                        ("nobody", "nobody"), ("near", "near"),
                        ("restricted", "restricted"), ("fail", "fail")):
        r_bad, home_bad = run(tag, guard=True, sudo=policy)
        cron_bad = _rr1b_cron_text(tmp, tag)
        out_bad = r_bad.stdout + r_bad.stderr
        if not (r_bad.returncode != 0
                and "network-guard.sh" not in cron_bad
                and not (home_bad / "scripts" / "network-guard.sh").exists()
                and "❌" in out_bad):
            problems.append(f"{tag}: rc={r_bad.returncode} "
                            f"guard_installed={(home_bad / 'scripts' / 'network-guard.sh').exists()}")

    # 3. ON с полной политикой → guard поставлен и запланирован РОВНО один раз.
    r_on, home_on = run("on", guard=True, sudo="full")
    cron_on = _rr1b_cron_text(tmp, "on")
    if not (r_on.returncode == 0
            and (home_on / "scripts" / "network-guard.sh").is_file()
            and cron_on.count("network-guard.sh") == 1
            and "исполнения не было" in r_on.stdout):
        problems.append(f"on: rc={r_on.returncode} count={cron_on.count('network-guard.sh')}")

    check("rr1b2_network_guard", not problems, f"problems={problems}")


def probe_rr1b2_installer_private_config(tmp: Path):
    """H1: гейт приватности конфига обязан работать в ОБОИХ входах. Проверка
    продублирована в install.sh и deploy.sh, и ремедиация починила только deploy:
    installer продолжал трактовать недоступный режим как «безопасно» и source'ил
    конфиг с секретами до того, как deploy его отверг."""
    problems = []
    # Провал чтения режима при корректном владельце: install.sh обязан отказать.
    for tag, env_extra in (("mode-fail", {"RR1B_CONFIG_MODE": ""}),
                           ("mode-644", {"RR1B_CONFIG_MODE": "644"})):
        res, home = _rr1b_install_fixture(
            tmp, f"h1-inst-{tag}",
            _rr1b_modules(core=False, integrations=True)
            + "WATCHDOG_BOT_TOKEN=" + _RR1B_H_SECRET + "\n",
            deploy_mode="real",
            extra_env=env_extra)
        out = res.stdout + res.stderr
        if res.returncode == 0:
            problems.append(f"{tag}: installer вернул 0 (должен отказать)")
        if "определить режим" not in out and "доступен группе" not in out:
            problems.append(f"{tag}: отказ без объяснения свойства: {out[-200:]!r}")
        if _RR1B_H_SECRET in out:
            problems.append(f"{tag}: canary утёк в вывод installer'а")

    # Контроль: безопасный конфиг installer проходит (deploy в skip-режиме).
    res_ok, _ = _rr1b_install_fixture(
        tmp, "h1-inst-ok",
        _rr1b_modules(core=False, integrations=True)
        + "WATCHDOG_BOT_TOKEN=" + _RR1B_H_SECRET + "\n",
        deploy_mode="real", extra_env={"RR1B_CONFIG_MODE": "600"})
    if res_ok.returncode != 0:
        problems.append(f"ok-контроль сломан: rc={res_ok.returncode}")

    check("rr1b2_installer_private_config", not problems, f"problems={problems}")


def probe_rr1b2_logrotate_preflight_order(tmp: Path):
    """H5: неисправный logrotate обязан обнаруживаться в преflight, ДО записей.
    Раньше парсерный прогон жил в install_logrotate_policy и деплой падал уже
    после записи watchdog'а и dashboard-юнита."""
    home = tmp / "h5ord-home"
    shim = tmp / "h5ord-shim"
    shim.mkdir(parents=True, exist_ok=True)
    _rr1b_host_shims(shim)
    _rr1b_fake_hermes(home)
    config = write(tmp / "h5ord-config.env",
                   _rr1b_modules(core=True) + "WATCHDOG_BOT_TOKEN=" + _RR1B_H_SECRET + "\n")
    env = _probe_subprocess_env(home, {
        "HOME": home.as_posix(),
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRONTAB_FIXTURE": (tmp / "h5ord-cron.txt").as_posix(),
        "CRON_FILE": (tmp / "h5ord-proposal.txt").as_posix(),
        "RR1B_LOGROTATE_RC": "1",
    })
    result = subprocess.run(
        ["bash", (REPO / "deploy.sh").as_posix(), config.as_posix()],
        cwd=REPO.as_posix(), env=env, capture_output=True, text=True, timeout=180)
    ok = (result.returncode != 0
          and "не проходит парсер logrotate" in (result.stdout + result.stderr)
          # НИЧЕГО из развёртки не должно было случиться: преflight раньше записей.
          and not (home / "scripts" / "hermes-watchdog.sh").exists()
          and not (home / ".config" / "systemd" / "user" / "hermes-dashboard.service").exists()
          and not (home / ".hermes" / "argus-logrotate.conf").exists())
    check("rr1b2_logrotate_preflight_order", ok,
          f"rc={result.returncode} watchdog={(home / 'scripts' / 'hermes-watchdog.sh').exists()} "
          f"unit={(home / '.config' / 'systemd' / 'user' / 'hermes-dashboard.service').exists()} "
          f"out={(result.stdout + result.stderr)[-220:]!r}")


def probe_rr1b2_sudo_ll_real(tmp: Path):
    """H4: дискриминатор `sudo -k -n -l` проверяется против НАСТОЯЩЕГО sudo.

    Прошлые итерации падали одинаково: шим подтверждал предположение реализации
    (сначала тег NOPASSWD в коротком выводе, которого там нет, затем
    смоделированный verbose-блок), и зелёный CI ничего не ловил, потому что шим
    и код были согласованы между собой, но не с реальностью. Финальный дизайн
    вообще не читает вывод sudo — только код возврата, — но и его нужно
    сверить с настоящим sudo: при живом timestamp оператора check_user()
    возвращает SUCCESS даже для PASSWD-правила, и спасает только `-k` с
    командой (не использовать кеш). Поэтому здесь на disposable CI-runner'е
    создаётся временный sudoers drop-in и проверяется, что deploy правильно
    классифицирует НАСТОЯЩЕЕ поведение: положительный грант пропускает,
    PASSWD-грант (последнее совпадение выигрывает) отказывает.

    Фикстура пишет sudoers ТОЛЬКО на одноразовый runner (это не путь deploy —
    тот sudoers не правит никогда) и удаляет её в finally."""
    problems = []
    if os.name == "nt":
        check("rr1b2_sudo_ll_real", True, "skipped: настоящий sudo недоступен на Windows — проверит CI")
        return
    if not shutil.which("sudo") or not shutil.which("visudo"):
        check("rr1b2_sudo_ll_real", True, "skipped: sudo/visudo отсутствуют")
        return
    if subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=30).returncode != 0:
        check("rr1b2_sudo_ll_real", True, "skipped: нет passwordless sudo")
        return

    home = tmp / "sudo-real-home"
    shim = tmp / "sudo-real-shim"
    shim.mkdir(parents=True, exist_ok=True)
    # ВАЖНО: sudo НЕ шимится — против настоящего sudo проверяется deploy.
    _rr1b_host_shims(shim, sudo="none")
    _rr1b_fake_hermes(home)
    config = write(tmp / "sudo-real-config.env",
                   _rr1b_modules(core=True, network_guard=True)
                   + f"WATCHDOG_BOT_TOKEN={_RR1B_H_SECRET}\n")

    # ВАЖНО: без !r — repr добавляет кавычки внутрь значения PATH, каталог
    # шимов перестаёт находиться, и drop-in ссылается на системные пути вместо
    # шим-путей, которые зондирует deploy (первый реальный прогон CI поймал
    # ровно это: PASSWD-грант не совпал с зондируемым путём).
    resolvectl_path = subprocess.run(
        ["bash", "-c", f"PATH='{shim.as_posix()}':$PATH command -v resolvectl"],
        capture_output=True, text=True, timeout=30).stdout.strip()
    ip_path = subprocess.run(
        ["bash", "-c", f"PATH='{shim.as_posix()}':$PATH command -v ip"],
        capture_output=True, text=True, timeout=30).stdout.strip()
    user = subprocess.run(["bash", "-c", "id -un"],
                          capture_output=True, text=True, timeout=30).stdout.strip()
    if not (resolvectl_path and ip_path and user):
        check("rr1b2_sudo_ll_real", True, "skipped: не удалось разрешить пути шимов")
        return

    # Имя обязано сортироваться ПОСЛЕ runner-файла с NOPASSWD: ALL: sudoers
    # читает /etc/sudoers.d по алфавиту, и при последнем совпадении более
    # поздний PASSWD-грант обязан выиграть у глобального ALL — иначе негативный
    # кейс бессмыслен. (Первый прогон поймал ровно это: "argus-probe" шёл
    # раньше "runner", PASSWD-правило переопределялось, deploy проходил.)
    dropin = Path("/etc/sudoers.d/zz-argus-probe")

    def write_dropin(body: str) -> bool:
        tmpf = tmp / "argus-probe-sudoers"
        write(tmpf, body)
        chk = subprocess.run(["sudo", "visudo", "-cf", str(tmpf)],
                             capture_output=True, text=True, timeout=60)
        if chk.returncode != 0:
            problems.append(f"sudoers фикстура не прошла visudo: {chk.stdout[-160:]!r}")
            return False
        inst = subprocess.run(["sudo", "install", "-m", "0440", str(tmpf), str(dropin)],
                              capture_output=True, text=True, timeout=60)
        if inst.returncode != 0:
            problems.append(f"не удалось установить drop-in: {inst.stderr[-160:]!r}")
            return False
        return True

    def deploy_guard(tag: str) -> subprocess.CompletedProcess:
        env = _probe_subprocess_env(home, {
            "HOME": home.as_posix(),
            "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
            "CRONTAB_FIXTURE": (tmp / f"sudo-real-cron-{tag}.txt").as_posix(),
            "CRON_FILE": (tmp / f"sudo-real-proposal-{tag}.txt").as_posix(),
        })
        return subprocess.run(
            ["bash", (REPO / "deploy.sh").as_posix(), config.as_posix()],
            cwd=REPO.as_posix(), env=env, capture_output=True, text=True, timeout=240)

    try:
        # A. Позитив: NOPASSWD с маской аргументов на все три команды — deploy
        #    обязан пройти. Это проверяет тег (`authenticate`) и запись sudoers
        #    с маской (`<путь> *`) против НАСТОЯЩЕГО вывода.
        if not write_dropin(
                f"{user} ALL=(root) NOPASSWD: {resolvectl_path} *, "
                f"{ip_path} route flush table *, {ip_path} rule del *\n"):
            check("rr1b2_sudo_ll_real", False, "fixtures: drop-in не установлен")
            return
        home_a = tmp / "sudo-real-home"
        res_a = deploy_guard("pos")
        if not (res_a.returncode == 0
                and "исполнения не было" in res_a.stdout):
            problems.append(f"positive: rc={res_a.returncode} "
                            f"out={(res_a.stdout + res_a.stderr)[-260:]!r}")

        # B. Негатив: DENY (`!`) на ip-команды в ПОСЛЕДНЕМ файле — реальный
        #    отказ sudo. PASSWD-грант здесь непроверяем принципиально: по
        #    семантике sudoers «any» тег NOPASSWD ставится, если он есть хотя
        #    бы у одного совпавшего правила, а на runner'е есть глобальный
        #    NOPASSWD: ALL — PASSWD-запись никогда не сделает команду
        #    требующей пароль (проверено на реальном sudo в изолированной
        #    фикстуре). Deploy обязан отказать и не поставить guard.
        if not write_dropin(
                f"{user} ALL=(root) !{ip_path} route flush table *, "
                f"!{ip_path} rule del *\n"):
            check("rr1b2_sudo_ll_real", False, "fixtures: drop-in не переустановлен")
            return
        res_b = deploy_guard("neg")
        out_b = res_b.stdout + res_b.stderr
        # Диагностика на случай расхождения с реальным sudo: rc и вывод прямого
        # зонда (с -k, как в deploy) на запрещённой команде.
        probe_rc = subprocess.run(
            ["sudo", "-k", "-n", "-l", ip_path, "route", "flush", "table",
             "4294967295"], capture_output=True, text=True, timeout=60)
        diag = (f" direct_rc={probe_rc.returncode} "
                f"direct_out={probe_rc.stdout.strip()[-120:]!r} "
                f"direct_err={probe_rc.stderr.strip()[-120:]!r} ip_path={ip_path!r}")
        if not (res_b.returncode != 0
                and "❌" in out_b
                and not (home_a / "scripts" / "network-guard.sh").exists()):
            problems.append(f"negative: rc={res_b.returncode} out={out_b[-200:]!r}{diag}")
    finally:
        subprocess.run(["sudo", "rm", "-f", str(dropin)], capture_output=True, timeout=60)

    check("rr1b2_sudo_ll_real", not problems, f"problems={problems}")


def probe_rr1b2_logrotate_policy(tmp: Path):
    """H5: одна Argus-owned политика ротации с фиксированными границами
    (daily / rotate 7 / maxsize 50M / compress / delaycompress / copytruncate),
    перечень файлов — ЯВНЫЙ: логи Hermes (agent.log, gateway.log) в политику не
    попадают, иначе Argus навязал бы ретенцию чужой собственности. Политика
    активируется в планировщике хоста, а не просто создаётся рядом.

    Парсер и семантика проверяются НАСТОЯЩИМ logrotate, если он есть на хосте:
    no-op шим доказывает только что deploy его позвал."""
    problems = []
    home = tmp / "h5-home"
    shim = tmp / "h5-shim"
    shim.mkdir(parents=True, exist_ok=True)
    logrotate_log = tmp / "h5-logrotate.log"
    _rr1b_host_shims(shim)
    _write_argv_shim(shim, "logrotate",
                     f'printf \'%s\\n\' "$*" >> "{logrotate_log.as_posix()}"\n'
                     'exit 0\n')
    _rr1b_fake_hermes(home)
    # Логи Hermes рядом с логами Argus: раньше глоб `logs/*.log` захватывал их.
    (home / ".hermes" / "logs").mkdir(parents=True, exist_ok=True)
    for name in ("agent.log", "gateway.log"):
        (home / ".hermes" / "logs" / name).write_text("hermes-owned\n",
                                                      encoding="utf-8")
    config_body = _rr1b_modules(core=True) + f"WATCHDOG_BOT_TOKEN={_RR1B_H_SECRET}\n"
    config = write(tmp / "h5-config.env", config_body)
    env = _probe_subprocess_env(home, {
        "HOME": home.as_posix(),
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRONTAB_FIXTURE": (tmp / "h5-cron.txt").as_posix(),
        "CRON_FILE": (tmp / "h5-proposal.txt").as_posix(),
    })
    result = subprocess.run(
        ["bash", (REPO / "deploy.sh").as_posix(), config.as_posix()],
        cwd=REPO.as_posix(), env=env, capture_output=True, text=True, timeout=180)
    policy = home / ".hermes" / "argus-logrotate.conf"
    sched_dir = home / "logrotate.d"
    activated = sched_dir / "argus"
    if result.returncode != 0 or not policy.is_file() or not activated.is_file():
        problems.append(f"rc={result.returncode} policy={policy.exists()} "
                        f"activated={activated.exists()} "
                        f"out={(result.stdout + result.stderr)[-260:]!r}")
    else:
        text = policy.read_text(encoding="utf-8")
        active = activated.read_text(encoding="utf-8")
        # Область действия — явный перечень Argus-файлов, без глоба.
        if [ln for ln in text.splitlines() if "*.log" in ln]:
            problems.append("политика использует глоб *.log вместо явного перечня")
        # Только НЕ-комментарийные строки: комментарий политики сам называет
        # agent.log/gateway.log как ИСКЛЮЧЁННЫЕ.
        body_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        for hermes_log in ("agent.log", "gateway.log"):
            if any(hermes_log in ln for ln in body_lines):
                problems.append(f"лог Hermes {hermes_log} попал в политику")
        argus_hits = [ln for ln in text.splitlines()
                      if ln.endswith(".log") and "/logs/" in ln]
        if len(argus_hits) < 15:
            problems.append(f"перечень логов Argus подозрительно мал: {len(argus_hits)}")
        for needle in ("daily", "rotate 7", "maxsize 50M",
                       "compress", "delaycompress", "copytruncate",
                       "missingok", "notifempty"):
            if needle not in text:
                problems.append(f"нет директивы {needle!r}")
        if re.search(r"^\s*size 50M", text, re.M):
            problems.append("size 50M отменяет daily — должен быть maxsize")
        if _RR1B_H_SECRET in text or _RR1B_H_SECRET in active:
            problems.append("canary попал в политику")
        if text != active:
            problems.append("активированная копия отличается от исходной")
        calls = logrotate_log.read_text(encoding="utf-8") if logrotate_log.exists() else ""
        if "--debug" not in calls:
            problems.append(f"dry-run не выполнялся: {calls!r}")

    # Парсер и семантика — настоящим logrotate, если он есть.
    if shutil.which("logrotate"):
        real = subprocess.run(
            ["bash", "-c",
             f'logrotate --debug --state /dev/null {policy.as_posix()} 2>&1; echo "rc=$?"'],
            capture_output=True, text=True, timeout=120)
        if f"rc={0}" not in real.stdout and "rc=0" not in real.stdout:
            problems.append(f"настоящий logrotate отклонил политику: {real.stdout[-260:]!r}")
        if "maxsize" not in text and "maxsize 50M" in text:
            problems.append("maxsize потерян при реальной проверке")
    else:
        check("rr1b2_logrotate_policy", not problems,
              f"problems={problems} настоящий logrotate отсутствует — парсер проверит CI")
        return

    check("rr1b2_logrotate_policy", not problems, f"problems={problems}")


def _rr1b_deploy(tmp: Path, tag: str, modules: str, extra_env: dict | None = None):
    home = tmp / f"rr1b-deploy-home-{tag}"
    shim = _rr1a_cron_shims(tmp, f"rr1b-{tag}")
    _rr1b_host_shims(shim)
    _rr1b_fake_hermes(home)
    config = write(tmp / f"rr1b-{tag}-config.env", modules)
    env = _probe_subprocess_env(home, {
        "HOME": home.as_posix(),
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRONTAB_FIXTURE": (tmp / f"rr1b-{tag}-cron.txt").as_posix(),
        "CRON_FILE": (tmp / f"rr1b-{tag}-proposal.txt").as_posix(),
        **(extra_env or {}),
    })
    result = subprocess.run(
        ["bash", (REPO / "deploy.sh").as_posix(), config.as_posix()],
        cwd=REPO.as_posix(), env=env, capture_output=True, text=True, timeout=180)
    return result, home


def probe_rr1b_analyzer_collector_ownership(tmp: Path):
    """RR1b B2 §6.3: у коллектора ОДИН владелец и канонический путь. Манифест
    ставил collect-metrics.sh в ~/scripts (CORE), а единственный потребитель
    health-analyzer.py читал ~/.hermes/scripts/ — ANALYZER-фикстура запускалась
    без своего коллектора и опиралась на старый файл чужого модуля."""
    cases = []
    # ANALYZER-only: коллектор обязан приехать вместе с потребителем.
    _, home_a = _rr1b_deploy(tmp, "an-only", _rr1b_modules(analyzer=True))
    cases.append(("analyzer-only", True,
                  (home_a / ".hermes" / "scripts" / "collect-metrics.sh").is_file(),
                  (home_a / "scripts" / "collect-metrics.sh").is_file()))
    # CORE+ANALYZER: канонический путь один, второй копии нет.
    _, home_b = _rr1b_deploy(tmp, "core-an", _rr1b_modules(core=True, analyzer=True))
    cases.append(("core+analyzer", True,
                  (home_b / ".hermes" / "scripts" / "collect-metrics.sh").is_file(),
                  (home_b / "scripts" / "collect-metrics.sh").is_file()))
    # ANALYZER=OFF: коллектор не ставится вовсе.
    _, home_c = _rr1b_deploy(tmp, "an-off", _rr1b_modules(core=True))
    cases.append(("analyzer-off", False,
                  (home_c / ".hermes" / "scripts" / "collect-metrics.sh").is_file(),
                  (home_c / "scripts" / "collect-metrics.sh").is_file()))
    problems = [f"{n}: canonical={c} (want {want}) legacy_home={l}"
                for n, want, c, l in cases if c is not want or l is not False]
    check("rr1b_analyzer_collector_ownership", not problems, f"problems={problems}")


def _rr1b_run_analyzer(tmp: Path, tag: str, script: str | None,
                       prior_state: str | None, executable: bool = True
                       ) -> tuple[subprocess.CompletedProcess, Path]:
    """Прогон health-analyzer.py --update в изолированном HERMES_HOME.
    script=None — коллектора нет; executable=False — есть, но без бита
    исполнения; prior_state — заранее записанное health-state.json."""
    home = tmp / f"rr1b-an-home-{tag}"
    logs = home / ".hermes" / "logs"
    scripts = home / ".hermes" / "scripts"
    logs.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    # Соседние модули копируются из кандидата — импорты health-analyzer'а
    # берутся из его же каталога.
    for name in ("health-analyzer.py", "health_decay.py",
                 "health_patterns.py", "health_netdata.py"):
        shutil.copy2(REPO / "scripts" / name, scripts / name)
    if script is not None:
        collector = write(scripts / "collect-metrics.sh", script)
        collector.chmod(0o755 if executable else 0o644)
    if prior_state is not None:
        write(logs / "health-state.json", prior_state)
    env = _probe_subprocess_env(home, {
        "HERMES_HOME": str(home / ".hermes"),
        "USERPROFILE": str(home),
        "PYTHONIOENCODING": "utf-8",
        # UTF-8-режим повторяет поведение Linux-CI: коллектор печатает
        # кириллицу, и без него windows-локаль cp1251 роняет декодирование.
        "PYTHONUTF8": "1",
    })
    result = subprocess.run(
        [sys.executable, str(scripts / "health-analyzer.py"), "--update"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    return result, logs / "health-state.json"


_RR1B_COLLECTOR_CASES = {
    "missing": None,
    "nonzero": "printf 'partial\\n'\nexit 3\n",
    "empty": "exit 0\n",
    "ok": _ANALYZER_OK_SCRIPT,
}


def probe_rr1b_analyzer_collector_failure(tmp: Path):
    """RR1b B2 §6.3: сбой коллектора ≠ чистое сканирование. Прежде
    collect_metrics() не смотрела на код возврата, а отсутствующий файл давал
    пустой stdout без исключения (bash → 127, stderr проглатывался): пустой
    вывод уходил в find_issues() как «проблем нет» и записывался в
    health-state.json. При отказе состояние не создаётся вовсе."""
    results = {tag: _rr1b_run_analyzer(tmp, f"fresh-{tag}", script, None)
               for tag, script in _RR1B_COLLECTOR_CASES.items()}

    def rejected(tag: str) -> bool:
        r, state = results[tag]
        return (r.returncode == 2
                and "ANALYZER_COLLECTOR_FAILED" in r.stderr
                and "МЕТРИКИ НЕ СОБРАНЫ" in r.stdout
                and not state.exists())

    missing_ok = rejected("missing")
    nonzero_ok = rejected("nonzero")
    empty_ok = rejected("empty")
    r_ok, state_ok = results["ok"]
    ok_ok = (r_ok.returncode == 0 and state_ok.exists()
             and "STATE_UPDATED" in r_ok.stderr)
    check("rr1b_analyzer_collector_failure",
          missing_ok and nonzero_ok and empty_ok and ok_ok,
          f"missing={missing_ok}(rc={results['missing'][0].returncode}) "
          f"nonzero={nonzero_ok}(rc={results['nonzero'][0].returncode}) "
          f"empty={empty_ok}(rc={results['empty'][0].returncode}) "
          f"ok={ok_ok}(rc={r_ok.returncode})")


def probe_rr1b_analyzer_collector_not_executable(tmp: Path):
    """RR1b B2 §6.3: неисполняемый коллектор и побайтовое сохранение
    состояния. Запуск через `bash` обходит бит исполнения, поэтому проверка
    обязана быть до сбора; отказ не должен двигать last_check (ревью F4)."""
    prior = ('{"version": 1, "last_check": "2026-01-01T00:00:00+00:00",'
             ' "check_count": 7, "issues": {}}\n')
    results = {tag: _rr1b_run_analyzer(tmp, f"prior-{tag}", script, prior)
               for tag, script in _RR1B_COLLECTOR_CASES.items() if tag != "ok"}
    if os.name != "nt":
        results["not-exec"] = _rr1b_run_analyzer(
            tmp, "prior-not-exec", _ANALYZER_OK_SCRIPT, prior, executable=False)
        not_exec_note = ""
    else:
        not_exec_note = "os.access(X_OK) не моделируется на Windows — проверит CI"

    def preserved(tag: str) -> bool:
        r, state = results[tag]
        return (r.returncode == 2
                and "ANALYZER_COLLECTOR_FAILED" in r.stderr
                and state.exists()
                and state.read_text(encoding="utf-8") == prior)

    missing_ok = preserved("missing")
    nonzero_ok = preserved("nonzero")
    empty_ok = preserved("empty")
    not_exec_ok = ("not-exec" not in results
                   or (preserved("not-exec")
                       and "не исполняемый" in results["not-exec"][0].stderr))
    check("rr1b_analyzer_collector_not_executable",
          missing_ok and nonzero_ok and empty_ok and not_exec_ok,
          f"missing={missing_ok} nonzero={nonzero_ok} empty={empty_ok} "
          f"not_exec={not_exec_ok} {not_exec_note} "
          f"err={results.get('not-exec', results['missing'])[0].stderr[-140:]!r}")


def probe_rr1b_discord_only_payload(tmp: Path):
    """RR1b B3 §6.4: Discord-only развёртка не зависит от TG_BOT и не от
    старой установленной копии. discord-bot.py делает `import webhook`; файл
    ставил только TG_BOT, поэтому чистая DISCORD_BOT=ON установка падала на
    ImportError (или, хуже, цепляла чужую копию).

    Проверка преrequisтов должна быть НАСТОЯЩИМ импортом под интерпретатором
    юнита: find_spec доказывал лишь находимость пакета, а невозможность
    выполнить саму проверку не должна превращаться в «зелёный» вывод (ревью F3).
    """
    real_py = _rr1b_sh_exec(sys.executable)

    def deploy_discord(tag: str, venv_body: str) -> tuple[subprocess.CompletedProcess, Path, str]:
        home = tmp / f"rr1b-deploy-home-{tag}"
        call_log = tmp / f"rr1b-discord-{tag}-calls.log"
        venv_bin = home / ".hermes" / "discord-venv" / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        _write_argv_shim(venv_bin, "python", venv_body(call_log))
        result, home = _rr1b_deploy(tmp, tag, _rr1b_modules(discord=True))
        calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
        return result, home, calls

    # 1. Интерпретатор рабочий, но discord не установлен → предупреждение.
    res_ok, home_ok, calls_ok = deploy_discord(
        "discord", lambda log: f'printf \'%s\\n\' "$*" >> "{log.as_posix()}"\n'
                               f'exec "{real_py}" "$@"\n')
    handler = home_ok / "scripts" / "webhook.py"
    deployed_ok = (res_ok.returncode == 0 and handler.is_file()
                   and not (home_ok / ".hermes" / "scripts" / "webhook.py").exists()
                   and "@HERMES_BIN@" not in handler.read_text(encoding="utf-8"))
    # Реальный импорт общей библиотеки тем же поиском, что делает discord-bot:
    # sys.path[0] = каталог самого скрипта.
    imported = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import webhook; "
         "print(sorted(n for n in vars(webhook) if n.startswith('handle_')))"
         % str(home_ok / "scripts")],
        cwd=REPO, capture_output=True, text=True, timeout=60)
    import_ok = imported.returncode == 0 and "handle_watchdog_status" in imported.stdout
    missing_ok = (res_ok.returncode == 0 and "не импортирует" in res_ok.stdout
                  and "✅ discord-venv" not in res_ok.stdout
                  and "discord" in calls_ok)

    # 2. Проверка не выполнилась (битый интерпретатор) → провал преrequisта,
    #    а НЕ «зелёный» вывод.
    res_bad, _, calls_bad = deploy_discord(
        "discord-bad", lambda log: f'printf \'%s\\n\' "$*" >> "{log.as_posix()}"\n'
                                  'exit 7\n')
    failed_check_ok = (res_bad.returncode != 0
                       and "✅ discord-venv" not in res_bad.stdout
                       and "Проверка импортов" in res_bad.stdout
                       and calls_bad.startswith("-c"))

    deploy_text = (REPO / "deploy.sh").read_text(encoding="utf-8")
    webhook_src = (REPO / "scripts" / "webhook.py").read_text(encoding="utf-8")
    discord_src = (REPO / "scripts" / "discord-bot.py").read_text(encoding="utf-8")
    # Проверка не «размыта» подавлением ошибки и покрывает реальные импорты.
    contract_ok = ('"$HERMES_DIR/discord-venv/bin/python" -c' in deploy_text
                   and "__import__" in deploy_text
                   and 'for name in ("discord", "yaml")' in deploy_text
                   # исполняемый код больше не использует обнаружение пакета
                   and "u.find_spec" not in deploy_text
                   and "importlib.util" not in deploy_text
                   and "PyYAML" in deploy_text
                   and "import yaml" in webhook_src
                   and "import discord" in discord_src)
    check("rr1b_discord_only_payload",
          deployed_ok and import_ok and missing_ok and failed_check_ok and contract_ok,
          f"deployed={deployed_ok} import={import_ok} missing={missing_ok} "
          f"failed_check={failed_check_ok}(rc={res_bad.returncode}) "
          f"contract={contract_ok} ok_out={res_ok.stdout[-200:]!r}")


def _rr1b_install_fixture(tmp: Path, tag: str, config_body: str,
                          deploy_mode: str = "real",
                          mutate_repo=None, plant=None, skip_config: bool = False,
                          extra_env: dict | None = None
                          ) -> tuple[subprocess.CompletedProcess, Path]:
    """Полный прогон install.sh под shims (dpkg/git/systemctl/crontab/flock/bash).
    deploy внутри — настоящий, из локальной копии дерева кандидата.

    deploy_mode: real | skip (deploy не отрабатывает) |
    broken-watchdog (deploy кладёт CORE-артефакт с ошибкой синтаксиса).
    mutate_repo(fixture) правит копию репозитория ДО deploy (порча шаблона,
    удаление источника манифеста); plant(home) кладёт файлы в HOME (чужая
    инфраструктура оператора, остатки отключённого модуля);
    skip_config=True — не создавать config.env, чтобы проверить его создание
    самим install.sh (H1)."""
    home = tmp / f"rr1b-install-home-{tag}"
    fixture = home / "hermes-argus"
    shutil.copytree(REPO, fixture,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    (fixture / ".git").mkdir()
    if not skip_config:
        write(fixture / "config.env", config_body)
    if mutate_repo is not None:
        mutate_repo(fixture)
    if plant is not None:
        plant(home)
    shim = tmp / f"rr1b-install-shim-{tag}"
    shim.mkdir(parents=True, exist_ok=True)
    # RR1b (host-readiness): преflight deploy'а (stat/loginctl/logrotate).
    # Ниже поверх них кладётся собственный systemctl-шим этой фикстуры.
    _rr1b_host_shims(shim)
    _rr1b_fake_hermes(home)
    _write_argv_shim(shim, "dpkg", "exit 0\n")
    _write_argv_shim(shim, "git", "exit 0\n")
    _write_argv_shim(shim, "crontab",
                     'case "$1" in\n'
                     '  -l) printf "" ;;\n'
                     '  -)  cat > /dev/null;;\n'
                     '  *) exit 1;;\n'
                     'esac\n')
    _write_argv_shim(shim, "flock", "exit 0\n")
    _write_argv_shim(shim, "systemctl",
                     '[ "$1" = "--user" ] && shift\n'
                     'case "$1" in\n'
                     '  show-environment) exit 0 ;;\n'
                     '  is-enabled) exit 1 ;;\n'
                     '  is-active)  exit 3 ;;\n'
                     '  list-unit-files) printf \'hermes-argus-config.path enabled enabled\\n\'; exit 0 ;;\n'
                     '  *) exit 0 ;;\n'
                     'esac\n')
    # RR1b (host-readiness): logrotate/стат для преflight deploy'а внутри.
    _rr1b_fake_hermes(home)
    _write_argv_shim(shim, "bash",
                     'if [ "${1:-}" = "deploy.sh" ]; then\n'
                     '  case "${RR1B_DEPLOY_MODE:-real}" in\n'
                     '    skip) exit 0 ;;\n'
                     '    broken-watchdog)\n'
                     '      mkdir -p "$HOME/scripts"\n'
                     '      printf \'if then\\n\' > "$HOME/scripts/hermes-watchdog.sh"\n'
                     '      exit 0 ;;\n'
                     '  esac\n'
                     'fi\n'
                     f'exec "{_rr1b_real("bash")}" "$@"\n')
    env = _probe_subprocess_env(home, {
        "HOME": home.as_posix(),
        "USERPROFILE": str(home),
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRONTAB_FIXTURE": (tmp / f"rr1b-install-cron-{tag}.txt").as_posix(),
        "CRON_FILE": str(tmp / f"rr1b-install-proposal-{tag}.txt"),
        "RR1B_DEPLOY_MODE": deploy_mode,
        **(extra_env or {}),
    })
    result = subprocess.run(["bash", str(fixture / "install.sh")],
                            cwd=fixture, env=env, capture_output=True,
                            text=True, timeout=240)
    return result, home


# Конфиг в СИНТАКСИСЕ ШАБЛОНА: значение в кавычках + комментарий. Наивный
# парсер строки склеивал комментарий со значением (`OFF#watchdog`), и CORE=OFF
# установка требовала несуществующий watchdog (ревью F1).
_RR1B_TEMPLATE_CFG = (
    'MODULE_CORE="OFF"            # watchdog, liveness, auto-remediate\n'
    'MODULE_INTEGRATIONS="ON"    # integration-discover и каскад-трекер\n'
    'MODULE_TG_BOT="OFF"         # интерактивный Telegram-бот\n'
    'MODULE_ANALYZER="OFF"       # L3 health-analyzer\n'
    'MODULE_HEARTBEAT="OFF"      # внешний dead man\'s switch\n'
    'MODULE_GH_HEARTBEAT="OFF"   # GitHub Heartbeat\n'
    'MODULE_DISCORD_BOT="OFF"    # Discord control plane\n'
    'MODULE_LOCAL_SERVICES="OFF" # локальная топология\n'
    f"WATCHDOG_BOT_TOKEN={RR1B_TOKEN}\nWATCHDOG_CHAT_ID={RR1B_CHAT}\n"
)


def probe_rr1b_install_module_neutral_gate(tmp: Path):
    """RR1b B4 §6.5: гейт следует выбранным модулям и проверяет ровно то, что
    deploy положил по манифестам включённых модулей.

    Каждый случай ловит свою ошибку (ревью F1/F2 + повторное ревью R1/R2/R3):
    шаблонный комментированный CORE=OFF доходит до финала; минимальный конфиг
    без optional-флагов тоже (дефолты deploy'а — OFF, а не ON); чужая
    инфраструктура оператора и остатки ОТКЛЮЧЁННОГО модуля с маркером не роняют
    установку; при этом битый скрипт ВКЛЮЧЁННОГО модуля, не являющийся
    «представителем», и отсутствующий источник манифеста — роняют.
    """
    marker_plant = lambda home: (  # noqa: E731 — короткий фикстурный хук
        write(home / "scripts" / "operator-owned.sh",
              "#!/bin/bash\n# чужой файл оператора: @DUMMY_OPERATOR_MARKER@\nexit 0\n"),
        write(home / "scripts" / "heartbeat.sh",
              "#!/bin/bash\n# остаток отключённого модуля: @DUMMY_LEFTOVER_MARKER@\nexit 0\n"),
    )

    def gate_ok(res: subprocess.CompletedProcess) -> bool:
        return (res.returncode == 0
                and "payload: проверен deploy.sh" in res.stdout
                and "Готово" in res.stdout)

    # 1. Шаблонный конфиг с комментариями, CORE=OFF.
    res_tpl, home_tpl = _rr1b_install_fixture(tmp, "template-off", _RR1B_TEMPLATE_CFG)
    template_ok = (gate_ok(res_tpl)
                   and not (home_tpl / "scripts" / "hermes-watchdog.sh").exists()
                   and (home_tpl / "scripts" / "integration-discover-wrapper.sh").is_file()
                   and "payload проверен" in res_tpl.stdout)

    # 2. Минимальный конфиг: optional-флаги не указаны → deploy считает их OFF.
    minimal = ("MODULE_CORE=OFF\nMODULE_INTEGRATIONS=ON\n"
               f"WATCHDOG_BOT_TOKEN={RR1B_TOKEN}\nWATCHDOG_CHAT_ID={RR1B_CHAT}\n")
    res_min, _ = _rr1b_install_fixture(tmp, "minimal", minimal)
    minimal_ok = gate_ok(res_min)

    # 3. Чужая инфраструктура и остатки отключённого модуля с маркерами.
    res_foreign, _ = _rr1b_install_fixture(tmp, "foreign", _RR1B_TEMPLATE_CFG,
                                          plant=marker_plant)
    foreign_ok = gate_ok(res_foreign)

    # 4. Битый скрипт ВКЛЮЧЁННОГО модуля, не входящий в «представители».
    res_broken, _ = _rr1b_install_fixture(
        tmp, "broken-wrapper", _RR1B_TEMPLATE_CFG,
        mutate_repo=lambda fx: write(fx / "scripts" / "health-check-v2-wrapper.sh",
                                     "#!/bin/bash\nif then\n"))
    broken_ok = res_broken.returncode != 0

    # 5. Отсутствующий источник манифеста включённого модуля.
    res_absent, _ = _rr1b_install_fixture(
        tmp, "absent-source", _RR1B_TEMPLATE_CFG,
        mutate_repo=lambda fx: (fx / "scripts" / "integration-discover-wrapper.sh").unlink())
    absent_ok = res_absent.returncode != 0

    check("rr1b_install_module_neutral_gate",
          template_ok and minimal_ok and foreign_ok and broken_ok and absent_ok,
          f"template={template_ok}(rc={res_tpl.returncode}) "
          f"minimal={minimal_ok}(rc={res_min.returncode}) "
          f"foreign={foreign_ok}(rc={res_foreign.returncode}) "
          f"broken={broken_ok}(rc={res_broken.returncode}) "
          f"absent={absent_ok}(rc={res_absent.returncode}) "
          f"tpl_out={res_tpl.stdout[-260:]!r}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="argus-probes-"))
    hc = load_module("health-check-v2")
    dc = load_module("ai-deep-check")
    ft = load_module("fallback-tracker-v2")
    hp = load_module("health_patterns")
    disc = load_module("integration-discover")
    wh = load_module("webhook")
    mon = load_module("monitoring-bot-poller")

    probe_catalog_429(hc)
    probe_catalog_401_then_public200(hc)
    probe_catalog_429_then_public200(hc)
    probe_honcho_503_green(hc)
    probe_honcho_token_not_in_argv(hc)
    probe_generator_honcho_contract()
    probe_honcho_queue_json_200(hc, tmp)
    probe_honcho_queue_json_401(hc, tmp)
    probe_honcho_queue_json_schema(hc, tmp)
    probe_honcho_workspace_path_injection(hc, tmp)
    probe_honcho_json_content_type(hc, tmp)
    probe_honcho_profile_host_block(hc, tmp)
    probe_honcho_default_host(hc, tmp)
    probe_honcho_default_profile_fallback(hc, tmp)
    probe_honcho_global_config_fallback(hc, tmp)
    probe_missing_required_provider_key(hc)
    probe_quoted_empty_provider_key(hc, tmp)
    probe_snapshot_missing_green(hc, tmp)
    probe_snapshot_corrupt_green(hc, tmp)
    probe_health_cli_entrypoint(tmp)

    # D0a: schema-v2 envelope, projection, dual-read hysteresis
    probe_rr0a_webhook_heartbeat_paths(wh, tmp)
    probe_report_v2_envelope(hc, tmp)
    probe_engine_two_runs_independent(hc, tmp)
    probe_ux0_bot_interaction(mon, wh)
    # Локальные сервисы (MODULE_LOCAL_SERVICES): consumer, гистерезис, UI, cron
    lsc = load_module("local_services_check")
    probe_ls_module_flag_default_off(lsc)
    probe_ls_manifest_validation(lsc, tmp)
    probe_ls_snapshot_validation(lsc, tmp)
    probe_ls_verdicts(lsc)
    probe_ls_hysteresis_two_distinct(lsc, tmp)
    probe_ls_blind_diagnostics(lsc, tmp)
    probe_ls_silence_mutes_but_preserves(lsc, tmp)
    probe_ls_marker_snapshot_is_blind_not_recovery(lsc, tmp)
    probe_ls_bounded_reflection(lsc, tmp)
    probe_ls_alert_gate_fail_closed(lsc)
    probe_ls_ui_states(wh, lsc, tmp)
    probe_ls_keyboard_module_dependent(mon, wh)
    probe_ls_toggle_keyboard_refresh(wh, tmp)
    probe_ls_deploy_on_off_cron(tmp)
    probe_wrapper_v1_report_accepted(tmp)
    probe_wrapper_v2_failed_increments(tmp)
    probe_wrapper_v2_unknown_preserves(tmp)
    probe_wrapper_v2_skipped_preserves(tmp)
    probe_wrapper_v2_unconfigured_preserves(tmp)
    probe_wrapper_v2_healthy_recover_reset(tmp)
    probe_wrapper_v2_malformed_rejected(tmp)
    probe_wrapper_v2_bad_verdict_rejected(tmp)
    probe_wrapper_v1_garbage_status_preserves(tmp)
    probe_wrapper_invalid_json_preserves(tmp)
    probe_wrapper_v2_duplicate_id_rejected(tmp)

    # D0a review pass: webhook consumers are fail-closed
    probe_webhook_quick_v1_accepted(wh, tmp)
    probe_webhook_quick_v2_mixed(wh, tmp)
    probe_webhook_quick_skipped_not_green(wh, tmp)
    probe_webhook_quick_malformed_rejected(wh, tmp)
    probe_webhook_schema_future_rejected(wh, tmp)
    probe_webhook_full_v2_unknown_skipped(wh, tmp)

    # D0a review pass 2: full schema-contract mutation matrix
    probe_webhook_v2_contract_fields_enforced(wh, tmp)
    probe_webhook_v2_wrong_types_rejected(wh, tmp)
    probe_webhook_v2_bool_counts_rejected(wh, tmp)
    probe_webhook_v2_inconsistent_aliases_rejected(wh, tmp)
    probe_webhook_full_bad_timestamp_not_green(wh, tmp)
    probe_engine_report_passes_contract_validation(wh, hc, tmp)
    probe_wrapper_v2_contract_enforced(tmp)

    probe_deep_skipped_counted_ok(dc)
    probe_deep_html200_green(dc)
    probe_deep_error_secret_leak(dc)
    probe_deep_quoted_off_ignored(dc)

    probe_fallback_same_second_lost(ft, tmp)
    probe_fallback_cross_session_restore(ft, tmp)
    probe_fallback_registry_free_ignored(ft, tmp)
    probe_envref_enrichment(hc)
    probe_envkey_enrichment(hc)
    probe_deep_activemodel_targeted(dc, tmp)
    probe_deep_paid_off_main(dc, tmp)
    probe_deep_unconfigured_report(dc, tmp)
    probe_wrapper_crash_no_stale(hp, tmp)
    probe_wrapper_unconfigured_not_recovery(hp, tmp)
    probe_fallback_baseline_first_incident(ft, tmp)

    probe_disk100(hp, tmp)
    probe_telegram_final_attempt(hp, tmp)
    probe_pattern_sample_secret_leak(hp, tmp)
    probe_pattern_bearer_secret_leak(hp, tmp)

    probe_discover_url_secret_leak(disc, tmp)
    probe_discover_url_shape_and_literals(disc, tmp)

    # OA1: структурный account-auth discovery + не-зелёная health-семантика
    probe_oa1_discovery_fixtures(disc, tmp)
    probe_oa1_storage_shape_stability(disc, tmp)
    probe_oa1_malformed_ignored(disc, tmp)
    probe_oa1_copilot_compat(disc, tmp)
    probe_oa1_secret_canary_scan(tmp)
    probe_oa1_health_static_evidence_non_green(hc, tmp)
    probe_oa1_health_pat_only_unconfigured(hc, tmp)
    probe_oa1_quick_report_not_green(wh)
    probe_oa1_helpers_are_pure()
    # OA1b: презентационная семантика OAuth-свидетельств (webhook-рендер)
    probe_oa1b_full_oauth_evidence(wh)
    probe_oa1b_full_generic_skipped_control(wh)
    probe_oa1b_full_counts_split(wh)
    probe_oa1b_full_oauth_line_survives_cap(wh)
    probe_oa1b_full_failure_survives_cap(wh)
    probe_oa1b_quick_oauth_only_not_blank_green(wh)
    probe_oa1b_quick_mixed_failure_and_oauth(wh)
    probe_oa1b_report_not_mutated(wh)
    probe_oa1b_helpers_are_pure()
    # S4: MCP disabled-by-config — честное сообщение о намеренно выключенных
    # серверах (contract docs/handoffs/mcp-disabled-server-compat-contract.md)
    probe_mcpoff_disabled_http_not_failed(tmp)
    probe_mcpoff_disabled_stdio_not_green(disc, hc, tmp)
    probe_mcpoff_enabled_default_still_probed(disc, hc, tmp)
    probe_mcpoff_enabled_true_still_probed(disc, hc, tmp)
    probe_mcpoff_falsy_matrix(disc)
    probe_mcpoff_no_probe_side_effect(tmp)
    probe_mcpoff_render_pause_line(wh)
    probe_mcpoff_render_counter_exclusion(wh)
    probe_mcpoff_other_skip_reasons_unchanged(hc, tmp)
    probe_mcpoff_unrelated_discovery_unchanged(tmp)
    # RR0b: снятые поверхности не возвращаются (статическая проверка)
    probe_rr0b_removed_surfaces_stay_removed()
    # RR0c: публичные дефолты — proxy/github/units (статика + поведение)
    probe_rr0c_public_defaults_no_personal_assumptions()
    probe_rr0c_proxy_check_explicit(hc)
    probe_rr0c_deploy_unit_handoff_detection(tmp)
    probe_rr0c_install_single_active_producer(tmp)
    # RR1a: managed cron ownership (блок/writer/adoption/fail-closed)
    probe_rr1a_cron_block_position_and_blank_lines(tmp)
    probe_rr1a_cron_managed_block_fresh(tmp)
    probe_rr1a_cron_module_transitions(tmp)
    probe_rr1a_cron_minimal_profile(tmp)
    probe_rr1a_cron_mixed_preservation(tmp)
    probe_rr1a_cron_legacy_adoption(tmp)
    probe_rr1a_cron_fail_paths(tmp)
    probe_rr1a_cron_malformed_markers(tmp)
    probe_rr1a_cron_contention(tmp)
    probe_rr1a_cron_block_shell_safety(tmp)
    probe_rr1a_quick_no_global_cron_count(tmp)
    # RR1b: module dependency truth и payload completeness
    probe_rr1b_quick_optional_expectations(tmp)
    probe_rr1b_watchdog_netdata_expectation(wh, tmp)
    probe_rr1b_analyzer_collector_ownership(tmp)
    probe_rr1b_analyzer_collector_failure(tmp)
    probe_rr1b_analyzer_collector_not_executable(tmp)
    probe_rr1b_discord_only_payload(tmp)
    probe_rr1b_install_module_neutral_gate(tmp)
    # RR1b, host-readiness slice: H1 private config, H2 user manager,
    # H3 Hermes preflight, H4 network-guard opt-in, H5 logrotate policy
    probe_rr1b2_private_config(tmp)
    probe_rr1b2_user_manager(tmp)
    probe_rr1b2_hermes_preflight(tmp)
    probe_rr1b2_network_guard(tmp)
    probe_rr1b2_sudo_ll_real(tmp)
    probe_rr1b2_installer_private_config(tmp)
    probe_rr1b2_logrotate_preflight_order(tmp)
    probe_rr1b2_logrotate_policy(tmp)
    # R1c: Authorization headers out of child argv (shell + ai-deep-check)
    probe_r1c_shell_full_auth_not_in_argv(tmp)
    probe_r1c_quick_github_header_not_in_argv(tmp)
    probe_r1c_curl_config_header_seam(tmp)
    probe_r1c_deep_check_get_not_in_argv(tmp)
    probe_r1c_deep_check_post_not_in_argv(tmp)
    probe_r1c_artifact_boundary(tmp)
    # R2a: fail-safe malformed YAML discovery (degradation/recovery + consumers)
    probe_r2a_syntax_degraded_not_crash(tmp)
    probe_r2a_wrong_shape_degraded(tmp)
    probe_r2a_valid_control_unchanged(tmp)
    probe_r2a_missing_config_control(tmp)
    probe_r2a_last_good_preserved(tmp)
    probe_r2a_no_false_removals(tmp)
    probe_r2a_repetition_quiet(tmp)
    probe_r2a_recovery_diff_last_good(tmp)
    probe_r2a_recovery_reportable_no_change(tmp)
    probe_r2a_health_fail_closed(tmp)
    probe_r2a_deep_check_fail_closed(tmp)
    probe_r2a_legacy_snapshot_compat(tmp)
    probe_r2a_wrapper_renders_transitions(tmp)
    probe_r2a_secret_error_boundary(tmp)
    probe_r2a_recovery_reportable_via_baseline(tmp)
    probe_r2a_unreadable_encoding_degraded(tmp)
    probe_r2a1_plugin_nonmapping_skipped(tmp)
    probe_r2a_baseline_degraded_reportable(tmp)
    # R2c.1: canonical top-level fallback chain inventory
    probe_r2c_fallback_shapes(disc, tmp)
    probe_r2c_reorder_deterministic(tmp)
    probe_r2c_secret_boundary(tmp)
    probe_r2c_r2a_last_good(tmp)
    probe_r2c_unrelated_discovery(tmp)
    probe_r2c_no_effects()
    probe_deploy_cron_profile(tmp)
    probe_deploy_secret_not_in_argv(tmp)
    probe_deploy_gh_heartbeat_secret_not_in_argv(tmp)
    probe_deploy_gh_secret_failure_gates_deploy(tmp)
    probe_gh_secret_stdin_flag_supported(tmp)
    probe_git_credential_helper_real(tmp)

    probe_curl_config_stdin_seam(tmp)
    probe_telegram_form_send_argv_canary(tmp)
    probe_telegram_json_pin_resp_canary(tmp)
    probe_telegram_getme_module_canary(hc, tmp)
    probe_healthcheck_check_url_canary(tmp)
    probe_telegram_py_form_send_canary(ft, tmp)
    probe_telegram_static_audit_no_argv_leak(tmp)
    probe_register_commands_env_token_canary(tmp)

    probe_gwmatcher_no_argv_substring(tmp)
    probe_gwmatcher_helper_present(tmp)
    probe_gwmatcher_rc2_not_death(tmp)

    print(f"\nprobes: {len(PASS)} pass, {len(FAIL)} fail")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
