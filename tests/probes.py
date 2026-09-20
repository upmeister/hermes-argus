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
    env = dict(os.environ, HOME=str(home), CRON_PROFILE="minimal", CRON_FILE=str(cron))
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
    argv_log = tmp / "sed-argv.log"
    tmpd = tmp / "deploy-tmp"
    tmpd.mkdir()
    real_sed = shutil.which("sed") or "/usr/bin/sed"
    _write_argv_shim(shim, "sed",
                     f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
                     f'exec "{Path(real_sed).as_posix()}" "$@"\n')
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "TMPDIR": str(tmpd), "TMP": str(tmpd), "TEMP": str(tmpd),
        "CRON_PROFILE": "minimal", "CRON_FILE": str(cron),
    })
    result = subprocess.run(["bash", str(REPO / "deploy.sh"), str(config)],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    argv_text = argv_log.read_text(encoding="utf-8") if argv_log.exists() else ""
    rendered = home / "scripts" / "send-monitoring-report.sh"
    rendered_ok = rendered.exists() and chat in rendered.read_text(encoding="utf-8")
    leftover_leak = any(token in p.read_text(encoding="utf-8", errors="ignore")
                        for p in tmpd.iterdir() if p.is_file())
    check("deploy_secret_not_in_argv",
          result.returncode == 0 and token not in argv_text and chat not in argv_text
          and rendered_ok and not leftover_leak,
          f"rc={result.returncode} sed_calls={len(argv_text.splitlines())} "
          f"chat_rendered={rendered_ok} leftover_leak={leftover_leak}")


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
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "CRON_PROFILE": "minimal", "CRON_FILE": str(tmp / "gh-cron.txt"),
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


def probe_telegram_json_send_argv_canary(tmp: Path):
    """R1b shape A (JSON sendMessage, response discarded), deployed-equivalent
    send-monitoring-report.sh: token canary stays off curl argv, URL arrives on
    curl stdin, request wiring (proxy/timeout/headers/payload) unchanged."""
    home = tmp / "tg-json-home"
    write(home / ".hermes" / ".env",
          f"WATCHDOG_BOT_TOKEN={R1B_TOKEN}\nWATCHDOG_CHAT_ID={R1B_CHAT}\n")
    # Deployed equivalent: deploy substitutes @WATCHDOG_CHAT_ID@ (R1a probes
    # prove render parity); the probe copy applies the same substitution.
    src = (REPO / "scripts" / "send-monitoring-report.sh").read_text(encoding="utf-8")
    deployed = tmp / "send-monitoring-report.deployed.sh"
    write(deployed, src.replace("@WATCHDOG_CHAT_ID@", R1B_CHAT))
    shim = tmp / "shim-tgjson"
    shim.mkdir()
    argv_log, stdin_log = _install_curl_shim(shim, tmp, "json", stdout="HTTP 000")
    env = _path_shim_env(home, {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", "")})
    result = subprocess.run(
        ["bash", str(deployed), "probe msg", "silent"],
        cwd=REPO, env=env, input=b"", capture_output=True, timeout=60)
    argv = _read_or(argv_log)
    stdin_data = _read_or(stdin_log)
    check("telegram_json_send_argv_canary",
          result.returncode == 0
          and R1B_TOKEN not in argv
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/sendMessage" in stdin_data
          and "-H" in argv and "Content-Type: application/json" in argv
          and "--max-time" in argv and "--proxy" in argv
          and R1B_CHAT in argv,
          f"rc={result.returncode} argv_leak={R1B_TOKEN in argv} "
          f"stdin_url={'url = https://api.telegram.org' in stdin_data} "
          f"wiring={'-H' in argv and '--proxy' in argv and R1B_CHAT in argv}")


def probe_telegram_form_send_argv_canary(tmp: Path):
    """R1b shape B (form-encoded sendMessage, recovery branch), real script
    gateway-liveness.sh: canary off curl argv, URL on stdin, form payload and
    silent flag preserved. pgrep shim keeps the process-alive precondition."""
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
    _write_argv_shim(shim, "pgrep", "exit 0\n")
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
    finally:
        if saved is None:
            sys.modules.pop("subprocess", None)
        else:
            sys.modules["subprocess"] = saved
    argv = " ".join(captured.get("argv", []))
    stdin_data = captured.get("input") or ""
    check("telegram_py_form_send_canary",
          R1B_TOKEN not in argv
          and f"url = https://api.telegram.org/bot{R1B_TOKEN}/sendMessage" in stdin_data
          and "chat_id=ARGUS_CHAT_R1B" in argv
          and "text=probe text" in argv
          and "-K" in argv and "-" in argv.split(),
          f"argv_leak={R1B_TOKEN in argv} "
          f"form_wiring={'chat_id=' in argv and '--data-urlencode' in argv}")


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
    in_process_py = {"webhook.py", "monitoring-bot-poller.py", "register-commands.sh"}
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
        "scripts/send-monitoring-report.sh": "printf 'url = ",
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


# ── runner ──────────────────────────────────────────────────────────────────

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="argus-probes-"))
    hc = load_module("health-check-v2")
    dc = load_module("ai-deep-check")
    ft = load_module("fallback-tracker-v2")
    hp = load_module("health_patterns")
    disc = load_module("integration-discover")
    wh = load_module("webhook")

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
    probe_report_v2_envelope(hc, tmp)
    probe_engine_two_runs_independent(hc, tmp)
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
    # R1c: Authorization headers out of child argv (shell + ai-deep-check)
    probe_r1c_shell_full_auth_not_in_argv(tmp)
    probe_r1c_quick_github_header_not_in_argv(tmp)
    probe_r1c_curl_config_header_seam(tmp)
    probe_r1c_deep_check_get_not_in_argv(tmp)
    probe_r1c_deep_check_post_not_in_argv(tmp)
    probe_r1c_artifact_boundary(tmp)
    probe_deploy_cron_profile(tmp)
    probe_deploy_secret_not_in_argv(tmp)
    probe_deploy_gh_heartbeat_secret_not_in_argv(tmp)
    probe_deploy_gh_secret_failure_gates_deploy(tmp)
    probe_gh_secret_stdin_flag_supported(tmp)
    probe_git_credential_helper_real(tmp)

    probe_curl_config_stdin_seam(tmp)
    probe_telegram_json_send_argv_canary(tmp)
    probe_telegram_form_send_argv_canary(tmp)
    probe_telegram_json_pin_resp_canary(tmp)
    probe_telegram_getme_module_canary(hc, tmp)
    probe_healthcheck_check_url_canary(tmp)
    probe_telegram_py_form_send_canary(ft, tmp)
    probe_telegram_static_audit_no_argv_leak(tmp)
    probe_register_commands_env_token_canary(tmp)

    print(f"\nprobes: {len(PASS)} pass, {len(FAIL)} fail")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
