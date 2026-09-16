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
import subprocess
import json
import os
import sys
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



# ── Пробы: C1a shadow bridge (ADR 0002 discovery/sync) ─────────────────────

def _c1a_shadow():
    return load_module("hermes-discovery-shadow")


def _c1a_write_child(tmp: Path, name: str, body: str) -> str:
    p = tmp / name
    p.write_text(body, encoding="utf-8", newline="\n")
    return str(p)


def probe_c1a_containment_matrix(tmp: Path):
    """C1a parent containment: env allowlist without parent-secret
    inheritance, reserved-key rejection, fail-closed missing env, strict
    parser (stderr truncation / duplicate keys / missing effects), timeout
    bounded, output cap stops the child."""
    sh = _c1a_shadow()
    home = tmp / "c1a-profile"
    home.mkdir(parents=True, exist_ok=True)
    child = _c1a_write_child(tmp, "c1a_env_dump.py",
                             "import json, os\n"
                             "print(json.dumps(dict(os.environ)))\n")
    os.environ["C1A_PARENT_TOKEN"] = "C1A_DUMMY_CANARY"
    try:
        env = sh.build_child_env(home, os.path.join(str(tmp), "src"),
                                 extra={"C1A_CANARY_ENV": "declared"},
                                 rev="r")
        result = sh.run_child(child, env=env, timeout_s=15)
    finally:
        os.environ.pop("C1A_PARENT_TOKEN", None)
    child_env = json.loads(result["stdout"]) if result["status"] == "ok" else {}
    reserved_rejected = False
    try:
        sh.build_child_env(home, os.path.join(str(tmp), "src"),
                           extra={"HOME": str(tmp / "wrong")}, rev="r")
    except ValueError:
        reserved_rejected = True
    invalid_env = sh.run_child(child, timeout_s=5)["status"] == "invalid_env"
    flood = _c1a_write_child(
        tmp, "c1a_flood.py",
        "import sys; sys.stdout.write('C1A' * 4 * 1024 * 1024)\n")
    capped = sh.run_child(
        flood, env=sh.build_child_env(home, os.path.join(str(tmp), "src"),
                                      rev="r"),
        timeout_s=30, output_cap=64 * 1024)
    sleeper = _c1a_write_child(tmp, "c1a_sleep.py",
                               "import time; time.sleep(60)\n")
    timed = sh.run_child(
        sleeper, env=sh.build_child_env(home, os.path.join(str(tmp), "src"),
                                        rev="r"),
        timeout_s=2)
    valid = {"schema": 1,
             "source": {"hermes_revision": "r", "bridge_revision": "b",
                        "profile_id": "p"},
             "facets": {"x": {"state": "ok", "authority": "argus",
                              "data": {}}},
             "effects": {"network": [], "process_spawn": [], "writes": [],
                         "truncated": False}}
    bad_stderr_trunc = sh.parse_envelope({
        "status": "ok", "exit_code": 0, "stdout": json.dumps(valid),
        "stdout_truncated": False, "stderr": "", "stderr_truncated": True,
        "output_limited": False})[0] is None
    bad_dup = sh.parse_envelope({
        "status": "ok", "exit_code": 0,
        "stdout": json.dumps(valid).replace('"schema": 1',
                                            '"schema": 1, "schema": 1'),
        "stdout_truncated": False, "stderr": "", "stderr_truncated": False,
        "output_limited": False})[0] is None
    bad_effects = sh.parse_envelope({
        "status": "ok", "exit_code": 0,
        "stdout": json.dumps({"schema": 1, "source": valid["source"],
                              "facets": valid["facets"]}),
        "stdout_truncated": False, "stderr": "", "stderr_truncated": False,
        "output_limited": False})[0] is None
    unknown_facet = sh.parse_envelope({
        "status": "ok", "exit_code": 0,
        "stdout": json.dumps({"schema": 1, "source": valid["source"],
                              "facets": {"x": valid["facets"]["x"],
                                         "rogue": valid["facets"]["x"]}}),
        "stdout_truncated": False, "stderr": "", "stderr_truncated": False,
        "output_limited": False})[0] is None
    bound = sh.parse_envelope({
        "status": "ok", "exit_code": 0,
        "stdout": json.dumps({"schema": 1,
                              "source": dict(valid["source"],
                                             profile_id="attacker"),
                              "facets": valid["facets"],
                              "effects": valid["effects"]}),
        "stdout_truncated": False, "stderr": "", "stderr_truncated": False,
        "output_limited": False},
        expected_profile_id="expected")[0] is None
    nan_rejected = sh.parse_envelope({
        "status": "ok", "exit_code": 0,
        "stdout": '{"schema": 1, "source": {"hermes_revision": "r", '
                  '"bridge_revision": "b", "profile_id": "p"}, '
                  '"facets": {"x": {"state": "ok", "authority": "argus", '
                  '"data": {"n": NaN}}}, "effects": {"network": [], '
                  '"process_spawn": [], "writes": [], "truncated": false}}',
        "stdout_truncated": False, "stderr": "", "stderr_truncated": False,
        "output_limited": False})[0] is None
    ok = (result["status"] == "ok"
          and unknown_facet and bound and nan_rejected
          and "C1A_DUMMY_CANARY" not in result["stdout"]
          and child_env.get("HERMES_HOME") == str(home)
          and child_env.get("HOME") == str(home)
          and child_env.get("C1A_CANARY_ENV") == "declared"
          and reserved_rejected and invalid_env
          and capped["status"] == "output_limit"
          and capped["stdout_truncated"]
          and len(capped["stdout"]) == 64 * 1024
          and timed["status"] == "timeout"
          and bad_stderr_trunc and bad_dup and bad_effects)
    check("c1a_parent_containment_matrix", ok,
          f"env={result['status']} reserved={reserved_rejected} "
          f"invalid_env={invalid_env} cap={capped['status']} "
          f"timeout={timed['status']} "
          f"parser={bad_stderr_trunc}/{bad_dup}/{bad_effects}/"
          f"{unknown_facet}/{bound}/{nan_rejected}")


def probe_c1a_profile_isolation_ab_ba(tmp: Path):
    """C1a gate 1: one explicit profile per child, no bleed in A->B and
    B->A orders."""
    sh = _c1a_shadow()
    child = _c1a_write_child(
        tmp, "c1a_home_echo.py",
        "import os; print(os.environ.get('HERMES_HOME', ''))\n")
    homes = {"A": tmp / "c1a-profile-a", "B": tmp / "c1a-profile-b"}
    for h in homes.values():
        h.mkdir(parents=True, exist_ok=True)
    seen = {}
    for order, pair in (("AB", ("A", "B")), ("BA", ("B", "A"))):
        for label in pair:
            home = homes[label]
            env = sh.build_child_env(home, os.path.join(str(tmp), "src"),
                                     rev="r")
            result = sh.run_child(child, env=env, timeout_s=15)
            seen[(order, label)] = result["stdout"].strip() \
                if result["status"] == "ok" else None
    ok = all(seen[(o, l)] == str(homes[l])
             for o in ("AB", "BA") for l in ("A", "B"))
    check("c1a_profile_isolation_ab_ba", ok, f"seen={seen}")


def probe_c1a_hermes_facets(tmp: Path):
    """C1a accepted facets against the actual production Hermes revision
    (skipped unless C1A_HERMES_PYTHON/C1A_HERMES_SRC/C1A_HERMES_REV are
    declared — the suite stays CI-green without a Hermes checkout)."""
    hp = os.environ.get("C1A_HERMES_PYTHON")
    src = os.environ.get("C1A_HERMES_SRC")
    rev = os.environ.get("C1A_HERMES_REV")
    if not (hp and src and rev):
        print("[SKIP] c1a_hermes_facets — C1A_HERMES_PYTHON/C1A_HERMES_SRC/"
              "C1A_HERMES_REV not declared")
        return
    sh = _c1a_shadow()
    home = tmp / "c1a-hermes-home"
    (home / "plugins" / "model-providers" / "c1a-sentinel").mkdir(
        parents=True, exist_ok=True)
    sentinel = home / "plugins" / "model-providers" / "c1a-sentinel" / "__init__.py"
    sentinel.write_text(
        "raise RuntimeError('C1a sentinel: plugin code must never be "
        "imported by automatic facets')\n",
        encoding="utf-8", newline="\n")
    (home / ".env").write_text("ALPHA_API_KEY=C1A_DUMMY_DOTENV_CANARY\n",
                               encoding="utf-8", newline="\n")
    marker = tmp / "c1a-keycmd-marker.txt"
    helper_cmd = f"sh -c 'echo C1A_DUMMY_KEYCMD_SECRET; touch {marker}'"
    (home / "config.yaml").write_text(
        'model:\n  default: "alpha-provider/model-a"\n'
        'fallback_providers:\n  - "beta-provider"\n'
        'providers:\n  gated:\n'
        '    base_url: "https://gated.invalid/v1"\n'
        f'    key_cmd: "{helper_cmd}"\n',
        encoding="utf-8", newline="\n")
    env = sh.build_child_env(home, src, rev=rev)
    result = sh.run_child(
        os.path.join(str(REPO), "scripts", "hermes-discovery-bridge.py"),
        ["--facets", "identity,config_health,effective_config",
         "--profile-id", "c1a-probe"],
        env=env, timeout_s=120, python_executable=hp)
    envelope, reason = sh.parse_envelope(result)
    facets = (envelope or {}).get("facets", {})
    blob = json.dumps(envelope, ensure_ascii=False) if envelope else ""
    canaries = ("C1A_DUMMY_DOTENV_CANARY", "C1A_DUMMY_KEYCMD_SECRET")
    leaks = [c for c in canaries
             if c in blob
             or c in (result.get("stdout") or "")
             or c in (result.get("stderr") or "")
             or any(c in p for p in result.get("argv", []))]
    marker_absent = not marker.exists()
    no_network = (envelope or {}).get("effects", {}).get("network") == []
    no_spawn = (envelope or {}).get("effects", {}).get("process_spawn") == []
    unexpected_writes = [
        w for w in (envelope or {}).get("effects", {}).get("writes", [])
        if not (w.startswith("{HERMES_HOME}/SOUL.md")
                or w.startswith("{HERMES_HOME}/audio_cache/")
                or w.startswith("{HERMES_HOME}/backups/config/"))]
    ok = (envelope is not None
          and facets.get("identity", {}).get("state") == "ok"
          and facets.get("config_health", {}).get("state") == "ok"
          and facets.get("effective_config", {}).get("state") == "ok"
          and facets.get("effective_config", {}).get("data", {})
          .get("fallback_providers") == [{"name": "beta-provider"}]
          and marker_absent and no_network and no_spawn
          and not unexpected_writes and leaks == [])
    check("c1a_hermes_facets_negative_control", ok,
          f"states={ {k: v.get('state') for k, v in facets.items()} } "
          f"marker_absent={marker_absent} network={no_network} "
          f"spawn={no_spawn} unexpected_writes={unexpected_writes} "
          f"leaks={leaks} reason={reason}")


def probe_c1a_deploy_installs_runtime_entrypoints(tmp: Path):
    """C1a review finding: deploy.sh must actually install the shadow parent,
    the bridge and the wrapper — otherwise enabling the flag after a deploy
    ends in a silently non-fatal missing-script path."""
    import subprocess as sp
    home = tmp / "c1a-deploy-home"
    config = write(tmp / "c1a-deploy-config.env",
                   "MODULE_CORE=ON\n"
                   "MODULE_INTEGRATIONS=ON\n"
                   "MODULE_TG_BOT=OFF\n"
                   "MODULE_ANALYZER=OFF\n"
                   "MODULE_HEARTBEAT=OFF\n"
                   "MODULE_GH_HEARTBEAT=OFF\n"
                   "MODULE_DISCORD_BOT=OFF\n")
    env = dict(os.environ, HOME=str(home),
               XDG_RUNTIME_DIR=str(tmp),
               CRON_FILE=str(tmp / "c1a-crontab.txt"))
    r = sp.run(["bash", str(REPO / "deploy.sh"), str(config)],
               cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    # deploy.sh places INTEGRATIONS_HOME_SCRIPTS under $HOME/scripts (the
    # wrapper hook resolves the shadow parent there); the poller belongs to
    # the TG_BOT module, which stays OFF in this fixture.
    installed = all(
        (home / "scripts" / name).exists()
        for name in ("hermes-discovery-bridge.py",
                     "hermes-discovery-shadow.py"))
    wrapper_installed = (home / "scripts" /
                         "integration-discover-wrapper.sh").exists()
    ok = r.returncode == 0 and installed and wrapper_installed
    check("c1a_deploy_installs_runtime_entrypoints", ok,
          f"rc={r.returncode} installed={installed} "
          f"wrapper={wrapper_installed}")


def probe_c1a_reconciliation_relations(tmp: Path):
    """C1a review finding: normalized comparisons and per-record provenance.
    Covers bridge_gain, equal, not_comparable, static_retained across the
    OAuth/plugin/registry families, and per-record profile_id."""
    sh = _c1a_shadow()
    static = {
        "model:primary": {"type": "activemodel", "role": "primary",
                          "provider": "alpha-provider",
                          "model": "model-a"},
        "model:fallback": {"type": "activemodel", "role": "fallback",
                           "provider": "fallback-provider",
                           "model": "fallback-provider/model-b"},
        "mcp:time": {"type": "mcp", "name": "time", "transport": "stdio"},
        "oauth:nous": {"type": "oauth", "name": "nous", "active": True},
        "plugin-provider:community": {"type": "plugin-provider",
                                      "name": "community"},
        "envkey:TOOL_KEY": {"type": "envkey", "name": "TOOL_KEY"},
        "envref:LEGACY_VAR": {"type": "envref", "name": "LEGACY_VAR",
                              "key_present": True},
    }
    envelope = {"schema": 1,
                "source": {"hermes_revision": "r", "bridge_revision": "b",
                           "profile_id": "production"},
                "facets": {
                    "effective_config": {"state": "ok", "authority": "hermes",
                                         "reason_code": "allowlist_extracted",
                                         "data": {
        "model_primary": {"value": "alpha-provider/model-a",
                          "source": "user"},
        "fallback_providers": [{"name": "fallback-provider"}],
        "providers": {}, "mcp_servers": {"time": {"transport": "stdio"}},
        "auxiliary": {}}},
                    "config_health": {"state": "ok", "authority": "hermes",
                                      "reason_code": "config_parsed",
                                      "data": {
        "config_file_present": True, "raw_parse_ok": True, "load_ok": True,
        "primary_model": "alpha-provider/model-a", "note": ""}},
                    "identity": {"state": "ok", "authority": "hermes",
                                 "reason_code": "ok",
                                 "data": {"hermes_version": "0.21.3"}}},
                "effects": {"network": [], "process_spawn": [], "writes": [],
                            "truncated": False}}
    recon = sh.reconcile(static, envelope, profile_id="production")
    by_key = {r["semantic_key"]: r for r in recon["records"]}
    ok = (
        by_key["model.primary"]["relation"] == "equal"
        and by_key["model.fallback"]["relation"] == "equal"
        and by_key["mcp.time"]["relation"] == "equal"
        and by_key["oauth:nous"]["relation"] == "static_retained"
        and by_key["plugin-provider:community"]["relation"] == "static_retained"
        and by_key["envkey:TOOL_KEY"]["relation"] == "static_retained"
        and all(r["profile_id"] == "production" for r in recon["records"]))
    check("c1a_reconciliation_relations", ok,
          f"counts={recon['counts']} "
          f"fallback={by_key['model.fallback']['relation']}")


def probe_c1a_wrapper_shadow_matrix(tmp: Path):
    """C1a gate: the guarded wrapper hook must not change legacy behavior for
    shadow disabled / success / degraded, and must isolate shadow output from
    the legacy report (C10)."""
    import subprocess as sp
    home = tmp / "c1a-wrapper-home"
    hermes = home / ".hermes"
    (hermes / "state").mkdir(parents=True, exist_ok=True)
    (hermes / "logs").mkdir(parents=True, exist_ok=True)
    (home / "scripts").mkdir(parents=True, exist_ok=True)
    # Deploy installs the shadow parent next to the wrapper; the fixture
    # mirrors that layout with the real implementation (both files: the hook
    # resolves the bridge next to the deployed shadow parent).
    for deployed in ("hermes-discovery-shadow.py", "hermes-discovery-bridge.py"):
        (home / "scripts" / deployed).write_text(
            (REPO / "scripts" / deployed).read_text(encoding="utf-8"),
            encoding="utf-8", newline="\n")
    report = {"events": [{"event": "added", "key": "provider:dummy",
                          "entity": {"type": "provider", "name": "dummy"}}]}
    engine = ("import json, os, sys\n"
              "rc = int(os.environ.get('C1A_FAKE_STATIC_RC', '2'))\n"
              f"sys.stdout.write(json.dumps({json.dumps(report)}))\n"
              "sys.exit(rc)\n")
    write(home / "scripts" / "integration-discover.py", engine)
    env_base = {"PATH": os.environ.get("PATH", ""),
                "HOME": str(home), "XDG_RUNTIME_DIR": str(tmp),
                "PYTHONIOENCODING": "utf-8",
                "WATCHDOG_BOT_TOKEN": ""}
    hp = os.environ.get("C1A_HERMES_PYTHON")
    rev = os.environ.get("C1A_HERMES_REV")
    if not (hp and rev):
        # The wrapper matrix runs the real production Hermes interpreter;
        # without declared C1A_HERMES_* variables the probe skips cleanly.
        print("[SKIP] c1a_wrapper_shadow_matrix — C1A_HERMES_PYTHON/"
              "C1A_HERMES_REV not declared")
        return

    import shutil
    if shutil.which("flock") is None:
        # The wrapper's lock primitive is unavailable on Windows dev boxes;
        # the matrix runs in CI/ubuntu and on peetna-aws.
        print("[SKIP] c1a_wrapper_shadow_matrix — flock not available")
        return

    def run_wrapper(extra_env):
        env = dict(env_base)
        env.update(extra_env)
        return sp.run(["bash", str(REPO / "scripts" /
                                   "integration-discover-wrapper.sh")],
                      capture_output=True, text=True, timeout=60, env=env)

    def snapshot_bytes():
        p_ = hermes / "state" / "integration-snapshot.json"
        return p_.read_bytes() if p_.exists() else b""

    def log_fingerprint():
        p_ = hermes / "logs" / "integration-discover.log"
        return "\n".join(
            l for l in p_.read_text(encoding="utf-8",
                                    errors="replace").splitlines()
            if "discover exit=" in l or "алерт" in l)

    baseline = run_wrapper({"HERMES_DISCOVERY_SHADOW": "0"})
    base_snap, base_log, base_rc = snapshot_bytes(), log_fingerprint(), \
        baseline.returncode
    success = run_wrapper({
        "HERMES_DISCOVERY_SHADOW": "1",
        "HERMES_DISCOVERY_HERMES_PYTHON": hp,
        "HERMES_DISCOVERY_HERMES_REV": rev})
    degraded = run_wrapper({
        "HERMES_DISCOVERY_SHADOW": "1",
        "HERMES_DISCOVERY_HERMES_PYTHON": hp,
        "HERMES_DISCOVERY_HERMES_REV": rev,
        "C1A_FORCE_SHADOW_FAILURE": "1"})
    timeout_zero = run_wrapper({
        "HERMES_DISCOVERY_SHADOW": "1",
        "HERMES_DISCOVERY_HERMES_PYTHON": hp,
        "HERMES_DISCOVERY_HERMES_REV": rev,
        "HERMES_DISCOVERY_SHADOW_TIMEOUT": "0"})
    legacy_same = (base_rc == success.returncode == degraded.returncode
                   == timeout_zero.returncode
                   and snapshot_bytes() == base_snap
                   and log_fingerprint() == base_log)
    shadow_files = hermes / "state" / "hermes-discovery-shadow.json"
    shadow_recorded = success.returncode == 0 and shadow_files.exists()
    degraded_ok = degraded.returncode == 0
    ok = legacy_same and shadow_recorded and degraded_ok
    shadow_log = hermes / "logs" / "hermes-discovery-shadow.log"
    log_tail = (shadow_log.read_text(encoding="utf-8",
                                     errors="replace")[-300:]
                if shadow_log.exists() else "ABSENT")
    check("c1a_wrapper_shadow_matrix", ok,
          f"legacy_same={legacy_same} shadow_recorded={shadow_recorded} "
          f"degraded_ok={degraded_ok} log={log_tail!r}")


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
    probe_deploy_cron_profile(tmp)

    # C1a shadow bridge (ADR 0002 discovery/sync)
    probe_c1a_containment_matrix(tmp)
    probe_c1a_profile_isolation_ab_ba(tmp)
    probe_c1a_hermes_facets(tmp)
    probe_c1a_reconciliation_relations(tmp)
    probe_c1a_deploy_installs_runtime_entrypoints(tmp)
    probe_c1a_wrapper_shadow_matrix(tmp)

    print(f"\nprobes: {len(PASS)} pass, {len(FAIL)} fail")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
