#!/usr/bin/env python3
"""probes.py вЂ” СЂРµРіСЂРµСЃСЃРёРѕРЅРЅС‹Р№ СЃСѓРёС‚ РїРѕ 43 РїСЂРѕР±Р°Рј СЂРµРІСЊСЋ РџРёС‚РЅС‹ (2026-09-10).

РљР°Р¶РґС‹Р№ РґРµС„РµРєС‚ РёР· engine-tests/REVIEW.md = С‚РµСЃС‚-РєРµР№СЃ. РџСЂРѕРіРѕРЅ:
  python3 tests/probes.py            # РІСЃРµ РїСЂРѕР±С‹
  python3 tests/probes.py -k catalog # РїРѕ РїРѕРґСЃС‚СЂРѕРєРµ id

D0a (2026-09-13) РґРѕР±Р°РІР»СЏРµС‚ СЃРµРєС†РёСЋ schema-v2: envelope/projection РґРІРёР¶РєР° Рё
dual-read hysteresis РѕР±С‘СЂС‚РєРё (ADR 0001).

РР·РѕР»СЏС†РёСЏ: dummy HOME/РєР°С‚Р°Р»РѕРіРё, subprocess-РІС‹Р·РѕРІС‹ РїРѕРґРјРµРЅСЏСЋС‚СЃСЏ РЅР° fixture-С„РµР№Рє
curl (СЃРј. _FakeCurl), СЃРµС‚СЊ РЅРµ С‚СЂРѕРіР°РµС‚СЃСЏ. РЎРµРєСЂРµС‚С‹ РІ С„РёРєСЃС‚СѓСЂР°С… вЂ” С‚РѕР»СЊРєРѕ
DUMMY_* РјР°СЂРєРµСЂС‹.

РЎС‚Р°С‚СѓСЃС‹: ok | fail | unconfigured | skipped вЂ” СЂР°Р·РґРµР»СЊРЅС‹Рµ, РЅРёРєРѕРіРґР° РЅРµ
СЃРІРѕСЂР°С‡РёРІР°СЋС‚СЃСЏ РІ ok (СЃРёСЃС‚РµРјРЅС‹Р№ СѓСЂРѕРє СЂРµРІСЊСЋ: 'not a failure' != 'ok').
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
    print(f"[{'PASS' if ok else 'FAIL'}] {probe_id}" + (f" вЂ” {detail}" if detail else ""))


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


# в”Ђв”Ђ Р¤РёРєСЃС‚СѓСЂС‹ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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


# в”Ђв”Ђ РџСЂРѕР±С‹: health-check-v2 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

def probe_catalog_429(hc):
    """429 РЅРµ РґРѕРєР°Р·С‹РІР°РµС‚ accepted key вЂ” fail, Р° РЅРµ ok."""
    codes = iter(["429"])
    fake_curl = lambda url, timeout, token="": next(codes, "429")
    with override_attr(hc, "curl_code", fake_curl):
        status, detail = hc.run_check(
            {"id": "p", "primitive": "api-catalog", "base": "https://dummy.invalid/v1",
             "key_env": "DUMMY_KEY", "label": "p"}, "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("catalog_429", status == "fail", detail)


def probe_catalog_401_then_public200(hc):
    """401 РЅР° РїРµСЂРІРѕРј РєР°РЅРґРёРґР°С‚Рµ вЂ” fail fast, РїСѓР±Р»РёС‡РЅС‹Р№ РєР°С‚Р°Р»РѕРі РЅРµ СЃРїР°СЃР°РµС‚."""
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
    """429 РЅР° РїРµСЂРІРѕРј РєР°РЅРґРёРґР°С‚Рµ вЂ” fail fast, РїСѓР±Р»РёС‡РЅС‹Р№ РєР°С‚Р°Р»РѕРі РЅРµ СЃРїР°СЃР°РµС‚."""
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
    """alive-СЂРµР¶РёРј СѓРґР°Р»С‘РЅ: 503 = fail, Р° РЅРµ 'auth wall, service alive'."""
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
    """РџСЂРѕРІР°Р№РґРµСЂ РёР· СЃРЅР°РїС€РѕС‚Р° СЃ РїСѓСЃС‚С‹Рј РєР»СЋС‡РѕРј = fail (РЅРµ unconfigured)."""
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
    """РћС‚СЃСѓС‚СЃС‚РІСѓСЋС‰РёР№ СЃРЅР°РїС€РѕС‚ = exit 2 (РѕС€РёР±РєР° СЃРѕСЃС‚РѕСЏРЅРёСЏ), РЅРµ Р·РµР»С‘РЅС‹Р№."""
    registry = write(tmp / "valid-registry.yaml", "kit_entries: []\n")
    rc = hc.run(["--snapshot", str(tmp / "missing.json"),
                 "--env", str(tmp / "no.env"), "--registry", str(registry)])
    check("snapshot_missing_green", rc == 2, f"rc={rc}")


def probe_snapshot_corrupt_green(hc, tmp: Path):
    """Р‘РёС‚С‹Р№ JSON СЃРЅР°РїС€РѕС‚Р° = exit 2."""
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


# в”Ђв”Ђ РџСЂРѕР±С‹: ai-deep-check в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

def probe_deep_skipped_counted_ok(dc):
    checks = [{"id": "provider:dummy", "status": "unconfigured"}]
    oks, fails, unconf, skipped = dc.count_statuses(checks)
    check("deep_skipped_counted_ok", len(oks) == 0 and len(unconf) == 1 and len(fails) == 0,
          f"oks={len(oks)} unconf={len(unconf)}")


def probe_deep_html200_green(dc):
    """HTML 200 РЅРµ РґРѕРєР°Р·С‹РІР°РµС‚ РєР°С‚Р°Р»РѕРі вЂ” fail, Р° РЅРµ ok."""
    dc.curl_json = lambda url, token, payload, timeout: (
        200, None) if payload is None else (200, {"choices": []})
    status, detail, _data = dc.catalog_verdict("https://dummy.invalid/v1/models", DUMMY_TOKEN)
    check("deep_html200_green", status == "fail", "status=" + status + " " + detail)


def probe_deep_error_secret_leak(dc):
    """РћС€РёР±РєР° API, СЌС…РѕРј СЃРѕРґРµСЂР¶Р°С‰Р°СЏ РєР»СЋС‡, СЂРµРґР°РєС‚РёСЂСѓРµС‚СЃСЏ РґРѕ РѕС‚С‡С‘С‚Р°."""
    err = dc.redact_error("Rejected request key " + DUMMY_KEY, DUMMY_KEY)
    check("deep_error_secret_leak", DUMMY_KEY not in err, "leak!" if DUMMY_KEY in err else "redacted")


def probe_deep_quoted_off_ignored(dc):
    allow = dc.allow_paid({"DEEP_CHECK_ALLOW_PAID": '"OFF"'}, no_paid=False)
    check("deep_quoted_off_ignored", allow is False, f"allow={allow}")


# в”Ђв”Ђ РџСЂРѕР±С‹: fallback-tracker в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

def probe_fallback_same_second_lost(ft, tmp: Path):
    """Р”РІР° СЃРѕР±С‹С‚РёСЏ РІ РѕРґРЅСѓ СЃРµРєСѓРЅРґСѓ вЂ” РѕР±Р° РѕР±СЂР°Р±Р°С‚С‹РІР°СЋС‚СЃСЏ (ms РІ watermark)."""
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
    """Restore РІ СЃРµСЃСЃРёРё B РЅРµ Р·Р°РєСЂС‹РІР°РµС‚ РєР°СЃРєР°Рґ СЃРµСЃСЃРёРё A."""
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
    """envref-С‡РµРє РЅР°СЃР»РµРґСѓРµС‚ registry check_url (probe envref_drops_auth_check)."""
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
    """Deep check С‚Р°СЂРіРµС‚РёС‚ Р°РєС‚РёРІРЅСѓСЋ РјРѕРґРµР»СЊ (probe deep_actual_model_ignored)."""
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
    """РњРѕРґРµР»СЊ РёР· registry free_models РєР»Р°СЃСЃРёС„РёС†РёСЂСѓРµС‚СЃСЏ РєР°Рє free Р±РµР· ':free' РІ id."""
    check("fallback_registry_free_ignored",
          ft.is_free_model("openrouter", "minimax-m3",
                           {"openrouter": ["minimax-m3"]}) is True,
          "registry free_models must classify")


def probe_fallback_baseline_first_incident(ft, tmp: Path):
    """Baseline РЅР° РёСЃС‚РѕСЂРёРё СЃ Р°РєС‚РёРІРЅС‹Рј РёРЅС†РёРґРµРЅС‚РѕРј: РїРµСЂРІС‹Р№ РќРћР’Р«Р™ РёРЅС†РёРґРµРЅС‚ РІ РЅРѕРІРѕР№
    СЃРµСЃСЃРёРё Р°Р»РµСЂС‚РёС‚ (probe fallback_first_incident_baselined)."""
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

# в”Ђв”Ђ РџСЂРѕР±С‹: health_patterns в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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


# в”Ђв”Ђ РџСЂРѕР±С‹: integration-discover (СЃР°РЅРёС‚Р°Р№Р·РµСЂ URL) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    """userinfo СѓРґР°Р»С‘РЅ Р±РµР· placeholder-host; literal URL-РєР»СЋС‡Рё С‚РѕР¶Рµ РѕС‡РёС‰Р°СЋС‚СЃСЏ."""
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


# в”Ђв”Ђ РџСЂРѕР±С‹: OA1 вЂ” СЃС‚СЂСѓРєС‚СѓСЂРЅС‹Р№ account-auth discovery + skipped-СЃРµРјР°РЅС‚РёРєР° в”Ђв”Ђв”Ђв”Ђв”Ђ

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
    """extract_entities РЅР° СЃРёРЅС‚РµС‚РёС‡РµСЃРєРѕРј HERMES_DIR (auth.json = С„РёРєСЃС‚СѓСЂР°:
    dict в†’ JSON, str в†’ СЃС‹СЂРѕРµ СЃРѕРґРµСЂР¶РёРјРѕРµ РґР»СЏ malformed-РєРµР№СЃРѕРІ)."""
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

    # 4. generic future provider id вЂ” Р±РµР· РїСЂР°РІРєРё СЂРѕСЃС‚РµСЂР°
    ents = _oa1_discover(disc, tmp, _oa1_fixture(pool={
        "synthetic-future-provider": [{"auth_type": "oauth", "access_token": "x"}]}))
    check("oa1_generic_future_pool_provider",
          ents.get("oauth:synthetic-future-provider") == {
              "type": "oauth", "name": "synthetic-future-provider", "active": False},
          f"got {ents.get('oauth:synthetic-future-provider')!r}")

    # 5. same-id dedupe (singleton + pool = РѕРґРЅР° СЃСѓС‰РЅРѕСЃС‚СЊ)
    ents = _oa1_discover(disc, tmp, _oa1_fixture(
        providers={"openai-codex": {"tokens": {"access_token": "a", "refresh_token": "r"}}},
        pool={"openai-codex": [{"auth_type": "oauth", "access_token": "b"}]}))
    codex_keys = [k for k in ents if k.startswith("oauth:openai-codex")]
    check("oa1_same_id_dedupe", codex_keys == ["oauth:openai-codex"], f"keys={codex_keys}")

    # 7. РЅРµРіР°С‚РёРІРЅС‹Рµ РєРѕРЅС‚СЂРѕР»С‹: СЏРІРЅС‹Р№ api_key, РЅРµРёР·РІРµСЃС‚РЅС‹Р№ auth_type,
    #    bare access_token (pool Рё flat) вЂ” РќР• account-auth СЃРІРёРґРµС‚РµР»СЊСЃС‚РІР°
    ents = _oa1_discover(disc, tmp, _oa1_fixture(
        providers={"api-key-blob": {"access_token": "OA1_CANARY_G"}},
        pool={"keyed": [{"auth_type": "api_key", "access_token": "OA1_CANARY_H",
                         "refresh_token": "OA1_CANARY_I"}],
              "weird": [{"auth_type": "totp", "refresh_token": "OA1_CANARY_J"}],
              "bare": [{"access_token": "OA1_CANARY_K"}]}))
    leftovers = [k for k in ents if k.startswith("oauth:")]
    check("oa1_apikey_negative_control", leftovers == [], f"leaked={leftovers}")

    # 10. active marker: С‚РѕС‡РЅРѕРµ СЃРѕРІРїР°РґРµРЅРёРµ id, Р±РµР· alias-РЅРѕСЂРјР°Р»РёР·Р°С†РёРё
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
    """OA1 acceptance 6: singleton-only vs pool-only vs both РґР»СЏ С‚РѕРіРѕ Р¶Рµ id
    РґР°СЋС‚ РёРґРµРЅС‚РёС‡РЅСѓСЋ СЃСѓС‰РЅРѕСЃС‚СЊ (Р±РµР· provenance-С€СѓРјР°)."""
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
    """OA1 acceptance 8 + review remediation: Р±РёС‚С‹Рµ/РЅРµРїРѕР»РЅС‹Рµ СЃС‚СЂСѓРєС‚СѓСЂС‹ auth.json
    РЅРµ СЂРѕРЅСЏСЋС‚ РґРёСЃРєР°РІРµСЂРё Рё РЅРµ РєР»Р°СЃСЃРёС„РёС†РёСЂСѓСЋС‚СЃСЏ РєР°Рє OAuth."""
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
        # remediation: partial nested tokens вЂ” СЂР°РЅС‚Р°Р№Рј С‚СЂРµР±СѓРµС‚ РћР‘Р• С‡Р°СЃС‚Рё РїР°СЂС‹
        "tokens_partial_access": _oa1_auth({"providers": {"x": {"tokens": {
            "access_token": "a"}}}}),
        "tokens_partial_refresh": _oa1_auth({"providers": {"x": {"tokens": {
            "refresh_token": "r"}}}}),
        # remediation: РїСЂРёСЃСѓС‚СЃС‚РІСѓСЋС‰РёР№, РЅРѕ falsey auth_type вЂ” malformed,
        # Р° РќР• В«РѕС‚СЃСѓС‚СЃС‚РІРёРµ РєР»СЋС‡Р°В» (weak-fallback РЅРµ РїСЂРёРјРµРЅСЏРµС‚СЃСЏ)
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
        except Exception as e:  # noqa: BLE001 вЂ” РїСЂРѕР±Р° Р»РѕРІРёС‚ Р»СЋР±РѕР№ РєСЂР°С€
            results[name] = f"CRASH: {e}"
    bad = {k: v for k, v in results.items() if v != []}
    check("oa1_malformed_ignored", not bad, f"{bad}")


def probe_oa1_copilot_compat(disc, tmp: Path):
    """OA1 acceptance 9: Copilot env-РєР°РЅР°Р» РЅРµ РёР·РјРµРЅРёР»СЃСЏ (token vs PAT-only)."""
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
    """OA1 secret boundary: canary РІРѕ РІСЃРµС… СЃРµРєСЂРµС‚РЅС‹С… РїРѕР»СЏС… С„РёРєСЃС‚СѓСЂС‹ РЅРµ
    РїРѕСЏРІР»СЏРµС‚СЃСЏ РІ snapshot, discover report/stdout/stderr Рё health-report."""
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
    for _ in range(2):  # baseline-РїСЂРѕРіРѕРЅ + diff-РїСЂРѕРіРѕРЅ
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
    """OA1 acceptance 11-13: СЃС‚Р°С‚РёС‡РµСЃРєР°СЏ oauth-СЃСѓС‰РЅРѕСЃС‚СЊ = skipped/РЅРµ-Р·РµР»С‘РЅР°СЏ,
    РЅРёРєРѕРіРґР° ok/'logged in'."""
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
    """OA1 acceptance 14: pat-only РѕСЃС‚Р°С‘С‚СЃСЏ unconfigured (РЅРµ skipped)."""
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
    """OA1 acceptance 15: quick-СЂРµРЅРґРµСЂ РЅРµ Р·РµР»С‘РЅС‹Р№ РЅР° skipped-only РѕС‚С‡С‘С‚Рµ."""
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
          "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in text and "вЏё" in text, f"text={text!r}")


# в”Ђв”Ђ РџСЂРѕР±С‹ OA1b: РїСЂРµР·РµРЅС‚Р°С†РёРѕРЅРЅР°СЏ СЃРµРјР°РЅС‚РёРєР° OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    """OA1b В§7.1: OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІРѕ РІ full view вЂ” informational-СЃС‚СЂРѕРєР° Р±РµР·
    вЏё/вњ…/В«РїСЂРѕРїСѓС‰РµРЅРѕВ»."""
    report = _oa1b_report([
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
        _oa1b_row("oauth:openai-codex", "oauth openai-codex", "skipped", "oauth"),
    ])
    text = wh._render_integrations_full(report, {})
    row = next(l for l in text.split("\n") if "oauth nous" in l)
    ok = ("рџ”ђ" in row and "СѓС‡С‘С‚РЅС‹Рµ РґР°РЅРЅС‹Рµ РѕР±РЅР°СЂСѓР¶РµРЅС‹" in row
          and "runtime-СЃС‚Р°С‚СѓСЃ РЅРµ РїСЂРѕРІРµСЂСЏРµС‚СЃСЏ" in row
          and "вЏё" not in row and "вњ…" not in row and "РїСЂРѕРїСѓС‰РµРЅРѕ" not in row)
    check("oa1b_full_oauth_evidence", ok, f"row={row!r}")


def probe_oa1b_full_generic_skipped_control(wh):
    """OA1b В§7.2: generic skipped (РЅРµ oauth) РІ full view вЂ” РїСЂРµР¶РЅРёР№ вЏё-СЂРµРЅРґРµСЂ."""
    report = _oa1b_report([
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
    ])
    text = wh._render_integrations_full(report, {})
    row = next(l for l in text.split("\n") if "kit tg-auth" in l)
    check("oa1b_full_generic_skipped_control",
          "вЏё" in row and "РїСЂРѕРїСѓС‰РµРЅРѕ" in row and "рџ”ђ" not in row,
          f"row={row!r}")


def probe_oa1b_full_counts_split(wh):
    """OA1b В§5/В§7.5: СЃС‡С‘С‚С‡РёРє вЏё СЃС‡РёС‚Р°РµС‚ С‚РѕР»СЊРєРѕ generic-skipped; OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІР°
    РёРґСѓС‚ РѕС‚РґРµР»СЊРЅС‹Рј РЅРµР№С‚СЂР°Р»СЊРЅС‹Рј рџ”ђ-СЃС‡С‘С‚С‡РёРєРѕРј."""
    report = _oa1b_report([
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
        _oa1b_row("provider:dummy", "provider dummy", "ok", "env"),
    ])
    text = wh._render_integrations_full(report, {})
    counts = text.split("\n")[1]
    check("oa1b_full_counts_split",
          "вЏё 1" in counts and "рџ”ђ 1" in counts and "вЏё 2" not in counts
          and "вњ… 1" in counts,
          f"counts={counts!r}")


def probe_oa1b_full_oauth_line_survives_cap(wh):
    """OA1b remediation (Pytna P2): Р»РёРјРёС‚ 4000 СЃРёРјРІРѕР»РѕРІ full view РЅРµ СЂРµР¶РµС‚ Рё
    РЅРµ РѕС‚Р±СЂР°СЃС‹РІР°РµС‚ СЃС‚СЂРѕРєСѓ OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІР° вЂ” РѕР±СЏР·Р°С‚РµР»СЊРЅРѕРµ Р·Р°СЏРІР»РµРЅРёРµ
    В«runtime-СЃС‚Р°С‚СѓСЃ РЅРµ РїСЂРѕРІРµСЂСЏРµС‚СЃСЏВ» РґРѕРµР·Р¶Р°РµС‚ С†РµР»РёРєРѕРј; СЂРµР·РєР° РёРґС‘С‚ РїРѕ С†РµР»С‹Рј
    СЃС‚СЂРѕРєР°Рј (СЃС†РµРЅР°СЂРёР№ СЂРµРІСЊСЋРµСЂР°: 16 healthy-РјРµС‚РѕРє РїРѕ 250 СЃРёРјРІРѕР»РѕРІ)."""
    long_label = "provider " + "p" * 241
    rows = [_oa1b_row(f"provider:fill{i}", long_label, "ok", "env")
            for i in range(16)]
    rows.append(_oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"))
    text = wh._render_integrations_full(_oa1b_report(rows), {})
    evidence_line = ("рџ”ђ oauth nous вЂ” СѓС‡С‘С‚РЅС‹Рµ РґР°РЅРЅС‹Рµ РѕР±РЅР°СЂСѓР¶РµРЅС‹ В· "
                     "runtime-СЃС‚Р°С‚СѓСЃ РЅРµ РїСЂРѕРІРµСЂСЏРµС‚СЃСЏ")
    out_lines = text.split("\n")
    complete = {evidence_line, "вњ… " + long_label, "рџ¤– AI-РїСЂРѕРІР°Р№РґРµСЂС‹ (custom)",
                "рџ”ђ OAuth-РїСЂРѕРІР°Р№РґРµСЂС‹", ""}
    healthy_left = sum(1 for l in out_lines if l == "вњ… " + long_label)
    ok = (len(text) <= 4000
          and evidence_line in out_lines
          and healthy_left < 16
          and all(l in complete or l.startswith(("рџ‘Ѓ ", "вњ… 1"))
                  for l in out_lines))
    check("oa1b_full_oauth_line_survives_cap", ok,
          f"len={len(text)} evidence_complete={evidence_line in out_lines} "
          f"healthy_left={healthy_left}")


def probe_oa1b_full_failure_survives_cap(wh):
    """OA1b remediation 2 (Pytna P2): cap 4000 РЅРµ СѓРґР°Р»СЏРµС‚ СЂРµР°Р»СЊРЅСѓСЋ вќЊ-СЃС‚СЂРѕРєСѓ
    РїСЂРѕРІР°Р»Р° вЂ” СЃ С…РІРѕСЃС‚Р° РїР°РґР°СЋС‚ С‚РѕР»СЊРєРѕ РёРЅС„РѕСЂРјР°С†РёРѕРЅРЅС‹Рµ СЃС‚СЂРѕРєРё; РїСЂРѕРІР°Р» Рё
    OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІРѕ РґРѕРµР·Р¶Р°СЋС‚ С†РµР»РёРєРѕРј. РќР°РїРѕР»РЅРёС‚РµР»Рё Р»РµР¶Р°С‚ РІ РўРћРњ Р¶Рµ
    kit:watchdog-bucket, С‡С‚Рѕ Рё РїСЂРѕРІР°Р», Рё РёРґСѓС‚ РџР•Р Р•Р” РЅРёРј: РЅР° СЃС‚Р°СЂРѕРј СЃР»РµРїРѕРј
    cap-Рµ СЂСѓР±РєР° РїРѕРїР°РґР°РµС‚ РІ РЅР°РїРѕР»РЅРёС‚РµР»Рё, Рё РїСЂРѕРІР°Р» РёСЃС‡РµР·Р°РµС‚ РёР· РІС‹РІРѕРґР°
    (РїСЂРѕР±Р° РєСЂР°СЃРЅР°СЏ РЅР° 3ff88370)."""
    long_label = "kit " + "k" * 280
    rows = [_oa1b_row(f"kit:fill{i}", long_label, "ok", "env")
            for i in range(15)]
    rows.append(_oa1b_row("kit:failure", "kit failure", "fail", "http",
                          "HTTP 500"))
    rows.append(_oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"))
    text = wh._render_integrations_full(_oa1b_report(rows), {})
    evidence_line = ("рџ”ђ oauth nous вЂ” СѓС‡С‘С‚РЅС‹Рµ РґР°РЅРЅС‹Рµ РѕР±РЅР°СЂСѓР¶РµРЅС‹ В· "
                     "runtime-СЃС‚Р°С‚СѓСЃ РЅРµ РїСЂРѕРІРµСЂСЏРµС‚СЃСЏ")
    fail_line = "вќЊ kit failure вЂ” HTTP 500"
    out_lines = text.split("\n")
    healthy_left = sum(1 for l in out_lines if l == "вњ… " + long_label)
    ok = (len(text) <= 4000
          and fail_line in out_lines
          and evidence_line in out_lines
          and healthy_left < 15
          and "рџ›Ў Watchdog kit" in out_lines)
    check("oa1b_full_failure_survives_cap", ok,
          f"len={len(text)} failure={fail_line in out_lines} "
          f"evidence_complete={evidence_line in out_lines} "
          f"healthy_left={healthy_left}")


def probe_oa1b_quick_oauth_only_not_blank_green(wh):
    """OA1b В§7.3: quick view РЅР° healthy+OAuth-only вЂ” РЅРµ В«РІСЃС‘ РІ РїРѕСЂСЏРґРєРµВ», РЅРµ
    В«РїСЂРѕРїСѓС‰РµРЅС‹ РїРѕР»РёС‚РёРєРѕР№В», РёРјРµРЅР° РІРёРґРЅС‹, runtime-СЃС‚Р°С‚СѓСЃ Р·Р°СЏРІР»РµРЅ РЅРµРїСЂРѕРІРµСЂРµРЅРЅС‹Рј."""
    report = _oa1b_report([
        _oa1b_row("provider:dummy", "provider dummy", "ok", "env"),
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
        _oa1b_row("oauth:openai-codex", "oauth openai-codex", "skipped", "oauth"),
    ])
    text = wh._render_integrations_quick(report)
    ok = ("РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in text
          and "РїСЂРѕРїСѓС‰РµРЅС‹ РїРѕР»РёС‚РёРєРѕР№" not in text and "вЏё" not in text
          and "nous" in text and "openai-codex" in text
          and "СѓС‡С‘С‚РЅС‹Рµ РґР°РЅРЅС‹Рµ РѕР±РЅР°СЂСѓР¶РµРЅС‹" in text
          and "runtime-СЃС‚Р°С‚СѓСЃ РЅРµ РїСЂРѕРІРµСЂСЏРµС‚СЃСЏ" in text)
    check("oa1b_quick_oauth_only_not_blank_green", ok, f"text={text!r}")


def probe_oa1b_quick_mixed_failure_and_oauth(wh):
    """OA1b В§7.4: СЂРµР°Р»СЊРЅС‹Р№ РїСЂРѕРІР°Р» РІРёРґРµРЅ, OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІРѕ вЂ” informational-
    РєРѕРЅС‚РµРєСЃС‚, Р·РµР»С‘РЅРѕРіРѕ Р·Р°СЏРІР»РµРЅРёСЏ РЅРµС‚; generic-skipped quick-РєРѕРЅС‚СЂРѕР»СЊ РїСЂРµР¶РЅРёР№."""
    fail_report = _oa1b_report([
        _oa1b_row("provider:dummy#http", "provider dummy root", "fail", "http",
                  "HTTP 503"),
        _oa1b_row("oauth:nous", "oauth nous", "skipped", "oauth"),
    ])
    text = wh._render_integrations_quick(fail_report)
    mixed_ok = ("вќЊ" in text and "provider dummy root" in text
                and "СѓС‡С‘С‚РЅС‹Рµ РґР°РЅРЅС‹Рµ РѕР±РЅР°СЂСѓР¶РµРЅС‹" in text
                and "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in text)
    generic_report = _oa1b_report([
        _oa1b_row("kit:tg-auth", "kit tg-auth", "skipped", "env"),
    ])
    generic_text = wh._render_integrations_quick(generic_report)
    generic_ok = "вЏё 1 РїСЂРѕРІРµСЂРѕРє РїСЂРѕРїСѓС‰РµРЅС‹ РїРѕР»РёС‚РёРєРѕР№" in generic_text
    check("oa1b_quick_mixed_failure_and_oauth",
          mixed_ok and generic_ok, f"mixed={text!r} generic={generic_text!r}")


def probe_oa1b_report_not_mutated(wh):
    """OA1b В§7.5: СЂРµРЅРґРµСЂ РЅРµ РјСѓС‚РёСЂСѓРµС‚ РєР°РЅРѕРЅРёС‡РµСЃРєРёР№ РѕС‚С‡С‘С‚ (JSON summary РЅРµРёР·РјРµРЅРµРЅ)."""
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
    """OA1b В§4: OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІР° РєР»Р°СЃСЃРёС„РёС†РёСЂСѓСЋС‚СЃСЏ РїРѕ СЃС‚СЂСѓРєС‚СѓСЂРЅС‹Рј РїРѕР»СЏРј
    (verdict + primitive) вЂ” Р±РµР· РёРјС‘РЅ РїСЂРѕРІР°Р№РґРµСЂРѕРІ Рё Р±РµР· СЃСЂР°РІРЅРµРЅРёСЏ detail-С‚РµРєСЃС‚Р°."""
    src = (REPO / "scripts" / "webhook.py").read_text(encoding="utf-8")
    banned = ('"nous"', '"codex"', '"openai-codex"', '"xai"', '"minimax"',
              'get("detail") ==')
    hits = sorted({b for b in banned if b in src})
    classified = ('_oauth_evidence_rows' in src
                  and src.count('get("primitive") == "oauth"') >= 2)
    check("oa1b_helpers_are_pure", not hits and classified,
          f"hits={hits} classified={classified}")


def probe_oa1_helpers_are_pure():
    """OA1 В§8: С…РµР»РїРµСЂС‹ РґРёСЃРєР°РІРµСЂРё вЂ” С‡РёСЃС‚Р°СЏ СЃС‚СЂСѓРєС‚СѓСЂРЅР°СЏ Р»РѕРіРёРєР°, Р±РµР· I/O-РїРѕРІРµСЂС…РЅРѕСЃС‚Рё."""
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
    # input РІ binary-СЂРµР¶РёРјРµ: text=True РЅР° Windows РїРµСЂРµРІРѕРґРёС‚ "\n" РІ "\r\n",
    # Рё read РІ deploy.sh РїРѕР»СѓС‡Р°РµС‚ "y\r" вЂ” РѕС‚РІРµС‚ РЅРµ РјР°С‚С‡РёС‚СЃСЏ.
    result = subprocess.run(["bash", str(REPO / "deploy.sh"), str(config)],
                            cwd=REPO, env=env, input=b"y\n",
                            capture_output=True, timeout=120)
    gh_argv_text = gh_argv.read_text(encoding="utf-8") if gh_argv.exists() else ""
    git_argv_text = git_argv.read_text(encoding="utf-8") if git_argv.exists() else ""
    gh_stdin_text = gh_stdin.read_text(encoding="utf-8") if gh_stdin.exists() else ""
    # git РїРѕР»СѓС‡Р°РµС‚ Рё -c-РѕРїС†РёРё, РїРѕСЌС‚РѕРјСѓ push РёС‰РµРј РІРЅСѓС‚СЂРё СЃС‚СЂРѕРєРё Р»РѕРіР°
    push_lines = [line for line in git_argv_text.splitlines() if " push " in line]
    push_ok = bool(push_lines) and "https://github.com/dummyuser/" in push_lines[0]
    # gh 2.45 РЅРµ РёРјРµРµС‚ --body-file Рё С‡РёС‚Р°РµС‚ Р·РЅР°С‡РµРЅРёРµ РёР· stdin С‚РѕР»СЊРєРѕ РєРѕРіРґР°
    # --body РЅРµ РїРµСЂРµРґР°РЅ: Р»СЋР±Р°СЏ С„РѕСЂРјР° С„Р»Р°РіР° С‚РµР»Р° РІ argv = СЂРµРіСЂРµСЃСЃРёСЏ Рє
    # РЅРµСЂР°Р±РѕС‡РµРјСѓ/СѓС‚РµРєР°СЋС‰РµРјСѓ РІР°СЂРёР°РЅС‚Сѓ
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
          and "GH Heartbeat РіРѕС‚РѕРІ" not in stdout
          and not (tmp / "ghfail-cron.txt").exists()
          and token not in argv_text,
          f"rc={result.returncode} ready_msg_suppressed="
          f"{'GH Heartbeat РіРѕС‚РѕРІ' not in stdout}")


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


# в”Ђв”Ђ РџСЂРѕР±С‹: R1b Telegram token-in-argv (shell + child curl) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    health-check-integrations.sh (getMe caller) вЂ” canary off argv, URL on
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
    token URL вЂ” literal or via the TG_API/TELEGRAM_API aliases вЂ” and any
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
            # С‚РѕРєРµРЅ РєР°Рє Р°СЂРіСѓРјРµРЅС‚ python-СЂРµР±С‘РЅРєР° (env-С‡С‚РµРЅРёРµ РІ РєРѕРґРµ СЌС‚Рѕ РЅРµ СЃРїР°СЃР°РµС‚)
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
                    # URL РІРЅСѓС‚СЂРё curl-РєРѕРјР°РЅРґС‹ РёР»Рё РІРЅРµ СЂР°Р·СЂРµС€С‘РЅРЅС‹С… С„РѕСЂРј вЂ” СѓС‚РµС‡РєР°
                    offenders.append(f"{path.relative_to(REPO).as_posix()}:{i}")
            # РєРѕРјР°РЅРґР° РїСЂРѕРґРѕР»Р¶Р°РµС‚СЃСЏ, РїРѕРєР° СЃС‚СЂРѕРєРё РєРѕРЅС‡Р°СЋС‚СЃСЏ РЅР° "\"
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


# в”Ђв”Ђ РџСЂРѕР±С‹: D0a schema v2 (envelope, projection, dual-read) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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


# в”Ђв”Ђ РџСЂРѕР±С‹: R1c Authorization headers out of child argv в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

R1C_TOKEN = "ARGUS_CANARY_R1C_AUTH"
R1C_TG = "ARGUS_CANARY_R1C_TGURL"
R1C_GH = "ARGUS_CANARY_R1C_GHTOKEN"
R1C_PROXY = "http://127.0.0.1:8444"


def _r1c_shell_curl_shim(shim_dir: Path, tmp: Path, tag: str) -> tuple[Path, Path]:
    """curl shim РґР»СЏ shell-РїСЂРѕР± R1c: Р»РѕРіРёСЂСѓРµС‚ argv Рё stdin РєР°Р¶РґРѕРіРѕ РІС‹Р·РѕРІР° Рё
    СЌРјСѓР»РёСЂСѓРµС‚ СЂР°Р·Р±РёСЂР°РµРјС‹Рµ СЃРєСЂРёРїС‚РѕРј С„РѕСЂРјС‹ РѕС‚РІРµС‚Р° (code-only РґР»СЏ -w, body+code
    РґР»СЏ getMe вЂ” getMe РёС‰РµРј РІ STDIN, РїРѕС‚РѕРјСѓ С‡С‚Рѕ token-bearing URL РёРґС‘С‚ С‡РµСЂРµР·
    config, 302 РґР»СЏ socks, JSON РґР»СЏ status-hint). РЎРµС‚Рё РЅРµС‚."""
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
    """curl shim РґР»СЏ РїСЂРѕР± ai-deep-check: С‚РѕС‚ Р¶Рµ capture, РЅРѕ РѕС‚РІРµС‚ РІ С„РѕСЂРјРµ
    `-w "\\n%{http_code}"` вЂ” body JSON + РєРѕРґ (curl_json РїР°СЂСЃРёС‚ rpartition)."""
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
    """РЎРѕС…СЂР°РЅРёС‚СЊ stdout/stderr РїСЂРѕР±С‹ РєР°Рє Р°СЂС‚РµС„Р°РєС‚С‹ РґР»СЏ boundary-СЃРєР°РЅР° (В§7.6)."""
    write(tmp / f"{tag}-out.txt", result.stdout)
    write(tmp / f"{tag}-err.txt", result.stderr)


def probe_r1c_shell_full_auth_not_in_argv(tmp: Path):
    """R1c В§7.1/В§7.3: full-СЂРµР¶РёРј вЂ” 5 authenticated check_url РґРѕСЃС‚Р°РІР»СЏСЋС‚
    Authorization С‡РµСЂРµР· stdin-РєР°РЅР°Р» (РЅРµ argv); token-bearing Telegram URL
    РѕСЃС‚Р°С‘С‚СЃСЏ РІ stdin (R1b РЅРµ СЂРµРіСЂРµСЃСЃРёСЂРѕРІР°Р»); --proxy СЃРѕС…СЂР°РЅС‘РЅ; unauthenticated
    РІС‹Р·РѕРІС‹ СЂР°Р±РѕС‚Р°СЋС‚ (shim 200 в†’ РЅРµС‚ СЃС‚СЂРѕРєРё СЃР±РѕСЏ SearXNG)."""
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
    """R1c В§7.2/В§7.3: quick GitHub вЂ” Authorization: token ... С‡РµСЂРµР· stdin-РєР°РЅР°Р»,
    РЅРµ РІ argv; getMe URL РѕСЃС‚Р°С‘С‚СЃСЏ РІ stdin; РѕР±Рµ РїСЂРѕРІРµСЂРєРё РїСЂРѕС…РѕРґСЏС‚ (shim 200)."""
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
          and "рџ”‘ GitHub token" not in result.stdout
          and "рџ¤– Telegram monitoring bot" not in result.stdout)
    check("r1c_quick_github_header_not_in_argv", ok,
          f"rc={result.returncode} gh_stdin={gh_in_stdin} "
          f"secret_in_argv={R1C_GH in argv_text or R1C_TG in argv_text}")


def probe_r1c_curl_config_header_seam(tmp: Path):
    """R1c В§7.1 (delivery proof): Р Р•РђР›Р¬РќР«Р™ curl РїР°СЂСЃРёС‚ `header = ...` РёР· stdin
    config Рё РѕС‚РїСЂР°РІР»СЏРµС‚ РёРјРµРЅРЅРѕ СЌС‚РѕС‚ Authorization РЅР° РїСЂРѕРІРѕРґ; logging-exec shim
    РґРѕРєР°Р·С‹РІР°РµС‚ РѕС‚СЃСѓС‚СЃС‚РІРёРµ canary РІ СЂРµР°Р»СЊРЅРѕРј argv. РќРµРіР°С‚РёРІРЅС‹Р№ РєРѕРЅС‚СЂРѕР»СЊ: Р±РµР·
    header-СЃС‚СЂРѕРєРё Authorization РЅРµ СѓС…РѕРґРёС‚."""
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
        # Р›РѕРі argv + tee stdin в†’ СЂРµР°Р»СЊРЅС‹Р№ curl (СЂРµР°Р»СЊРЅС‹Р№ Р·Р°РїСЂРѕСЃ + capture argv).
        _write_argv_shim(shim, "curl",
                         f'printf \'%s\\n\' "$*" >> "{argv_log.as_posix()}"\n'
                         f'tee "{stdin_log.as_posix()}" | '
                         f'"{Path(real_curl).as_posix()}" "$@"\n')
        env = _probe_subprocess_env(tmp / "r1c-seam-home", {
            "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        })
        # Р§РµСЂРµР· bash -c: bash СЃР°Рј СЂРµР·РѕР»РІРёС‚ PATH (shim в†’ tee в†’ СЂРµР°Р»СЊРЅС‹Р№ curl).
        # РџСЂСЏРјРѕР№ CreateProcess-РІС‹Р·РѕРІ РёР· python РЅР° Windows РёРіРЅРѕСЂРёСЂСѓРµС‚ PATH
        # СЂРµР±С‘РЅРєР° Рё РјРѕР»С‡Р° Р±РµСЂС‘С‚ СЂРµР°Р»СЊРЅС‹Р№ curl вЂ” capture Р±С‹Р» Р±С‹ РІР°РєСѓСѓРјРЅС‹Рј.
        curl_via_bash = 'exec curl -s -o /dev/null -w "%{http_code}" -K -'
        positive = subprocess.run(
            ["bash", "-c", curl_via_bash],
            input=f'url = {url}\nheader = "Authorization: Bearer {R1C_TOKEN}"\n'.encode(),
            env=env, capture_output=True, timeout=30)
        # РќРµРіР°С‚РёРІРЅС‹Р№ РєРѕРЅС‚СЂРѕР»СЊ 1: Р‘Р•Р— header-СЃС‚СЂРѕРєРё Authorization РЅРµ СѓС…РѕРґРёС‚.
        negative = subprocess.run(
            ["bash", "-c", curl_via_bash],
            input=f"url = {url}\n".encode(),
            env=env, capture_output=True, timeout=30)
        # РќРµРіР°С‚РёРІРЅС‹Р№ РєРѕРЅС‚СЂРѕР»СЊ 2 (Р»РѕРІСѓС€РєР° R1c): РќР•С†РёРєР»РѕРІР°РЅРЅС‹Р№ header = Р·РЅР°С‡РµРЅРёРµ
        # СЂРµР°Р»СЊРЅС‹Р№ curl РјРѕР»С‡Р° РЅРµ РѕС‚РїСЂР°РІР»СЏРµС‚ вЂ” РїСЂРѕР±Р° РєСЂР°СЃРЅР°СЏ, РµСЃР»Рё СЃС†РµРЅР°СЂРёР№
        # РІРµСЂРЅС‘С‚СЃСЏ Рє РЅРµРїСЂРѕС†РёС‚РѕРІР°РЅРЅРѕР№ С„РѕСЂРјРµ.
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
              # fail-closed: capture-РјРµС…Р°РЅРёР·Рј РѕР±СЏР·Р°РЅ РІРёРґРµС‚СЊ РІСЃРµ 3 РІС‹Р·РѕРІР°
              and captured == 3)
        # В§7.6: canary РЅРµ РїРµС‡Р°С‚Р°РµС‚СЃСЏ вЂ” С‚РѕР»СЊРєРѕ Р±СѓР»РµРІС‹ РёСЃС…РѕРґС‹ РїСЂРѕРІРµСЂРєРё.
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
    """РџСЂРѕРіРѕРЅ curl_json СЃ capture. POSIX: РґРѕС‡РµСЂРЅРёР№ python СЃ PATH-shim curl
    (os-level child-argv С‡РµСЂРµР· Р»РѕРі shim'Р°). Windows: CreateProcess РЅРµ РёСЃРїРѕР»РЅСЏРµС‚
    shebang-shim Рё РјРѕР»С‡Р° СѓС…РѕРґРёС‚ РІ СЂРµР°Р»СЊРЅС‹Р№ curl вЂ” therefore in-process capture
    subprocess.run РЅР° РіСЂР°РЅРёС†Рµ (argv + input = СЂРѕРІРЅРѕ С‚Рѕ, С‡С‚Рѕ СѓС€Р»Рѕ Р±С‹ РІ os-argv/
    stdin СЂРµР±С‘РЅРєР°; РєСЂР°СЃРЅР°СЏ-СЃРїРѕСЃРѕР±РЅРѕСЃС‚СЊ СЃРѕС…СЂР°РЅСЏРµС‚СЃСЏ: РЅР° СЃС‚Р°СЂРѕРј РєРѕРґРµ canary
    РѕРєР°Р·С‹РІР°РµС‚СЃСЏ РІ argv). Р’РѕР·РІСЂР°С‰Р°РµС‚ (stdout, argv_text, stdin_text)."""
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
        # repr-РЅРѕСЂРјР°Р»РёР·Р°С†РёСЏ: РґРІРѕР№РЅС‹Рµ РєР°РІС‹С‡РєРё РІРЅСѓС‚СЂРё СЌР»РµРјРµРЅС‚РѕРІ РѕСЃС‚Р°СЋС‚СЃСЏ СЃС‹СЂС‹РјРё,
        # РїРѕСЌС‚РѕРјСѓ substring-СѓС‚РІРµСЂР¶РґРµРЅРёСЏ СЂР°Р±РѕС‚Р°СЋС‚ С‚Р°Рє Р¶Рµ, РєР°Рє РЅР° posix-Р»РѕРіР°С….
        argv_text = "\n".join(repr(a) for a in argv_lines)
        stdin_text = "\n".join(repr(s) for s in stdin_lines)
        # РЎС‹СЂРѕР№ stderr СЂРµР±С‘РЅРєР° РќР• СЃРѕС…СЂР°РЅСЏРµРј: STDINLOG РЅРµСЃС‘С‚ canary РїРѕ РґРёР·Р°Р№РЅСѓ
        # (СЌС‚Рѕ РєР°РЅР°Р» РґРѕСЃС‚Р°РІРєРё), Р° boundary-СЃРєР°РЅ В§7.6 СЃРјРѕС‚СЂРёС‚ С‚РѕР»СЊРєРѕ stdout/err.
        write(tmp / f"r1c-dc-{tag}-out.txt", result.stdout)
        return result.stdout, argv_text, stdin_text
    env = _probe_subprocess_env(tmp / f"r1c-dc-home-{tag}", {
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        # Windows-python РІ СЂРµР±С‘РЅРєРµ С‚СЂРµР±СѓРµС‚ USERPROFILE РґР»СЏ Path.home() РјРѕРґСѓР»СЏ.
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
    """R1c В§7.4: catalog GET вЂ” Bearer canary РЅРµ РІ child argv, header РґРѕСЃС‚Р°РІР»РµРЅ
    С‡РµСЂРµР· stdin, Р·Р°РїСЂРѕСЃ/РїР°СЂСЃРёРЅРі СЃРѕС…СЂР°РЅРµРЅС‹ (200 + JSON catalog)."""
    out, argv_text, stdin_text = _r1c_run_deep_check(tmp, "get", None)
    ok = ("RC 200" in out and '"m1"' in out
          and R1C_TOKEN not in argv_text
          and f"Authorization: Bearer {R1C_TOKEN}" in stdin_text
          and "--max-time" in argv_text and "dc-models" in argv_text)
    check("r1c_deep_check_get_not_in_argv", ok,
          f"rc_ok={'RC 200' in out} secret_in_argv={R1C_TOKEN in argv_text} "
          f"header_stdin={f'Authorization: Bearer {R1C_TOKEN}' in stdin_text}")


def probe_r1c_deep_check_post_not_in_argv(tmp: Path):
    """R1c В§7.5: chat POST вЂ” Bearer canary РЅРµ РІ child argv, header С‡РµСЂРµР· stdin,
    payload/-d Рё Content-Type РІ argv СЃРѕС…СЂР°РЅРµРЅС‹ (СЃРІРѕР№СЃС‚РІР° Р·Р°РїСЂРѕСЃР° РЅРµ РёР·РјРµРЅРёР»РёСЃСЊ)."""
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
    """R1c В§7.6: canary РїСЂРёСЃСѓС‚СЃС‚РІСѓРµС‚ РўРћР›Р¬РљРћ РІ stdin-Р»РѕРіР°С… РґРѕСЃС‚Р°РІРєРё
    (*-stdin.log вЂ” РєР°РЅР°Р», РїРѕ РєРѕС‚РѕСЂРѕРјСѓ СЃРµРєСЂРµС‚ СѓС…РѕРґРёС‚ РІ curl) Рё РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РІРѕ
    РІСЃРµС… РѕСЃС‚Р°Р»СЊРЅС‹С… r1c-Р°СЂС‚РµС„Р°РєС‚Р°С… (stdout/stderr-СЃРЅРёРјРєРё, argv-Р»РѕРіРё). РџРµС‡Р°С‚СЊ
    canary РІ check()-detail РЅРµ РґРѕРїСѓСЃРєР°РµС‚СЃСЏ РёРЅРІР°СЂРёР°РЅС‚РѕРј РїСЂРѕРµРєС‚Р°; suite-stdout
    С‡РёСЃС‚РѕС‚Р° РѕР±РµСЃРїРµС‡РёРІР°РµС‚СЃСЏ Р±СѓР»РµРІС‹РјРё detail-СЃС‚СЂРѕРєР°РјРё Рё РІРЅРµС€РЅРёРј Р°СѓРґРёС‚РѕРј СЂРµРІСЊСЋ."""
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
          and "рџџў dummy (fixture)" in log,
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


# в”Ђв”Ђ РџСЂРѕР±С‹: webhook-РїРѕС‚СЂРµР±РёС‚РµР»Рё РѕС‚С‡С‘С‚Р° (fail-closed) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    # HOME on posix вЂ” set both so the handlers read the fixture home.
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
    ok_fail = "вќЊ dummy: down" in out and "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in out
    ok_report = dict(fail_report, ok=1, fail=0,
                     checks=[{"id": "kit:DUMMY_KEY", "label": "dummy",
                              "status": "ok", "detail": "up"}])
    home2 = _webhook_report_home(tmp, "wh-v1-ok", ok_report)
    with override_environ(**_webhook_home_env(home2)):
        out2 = wh.handle_integrations_check()
    check("webhook_quick_v1_accepted",
          ok_fail and "вњ… Argus:" in out2 and "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" in out2,
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
    ok = ("1/3 ok" in out and "вќЊ beta: down" in out
          and "вљ пёЏ gamma: inconclusive" in out and "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in out)
    check("webhook_quick_v2_mixed", ok, f"out={out[:100]!r}")


def probe_webhook_quick_skipped_not_green(wh, tmp: Path):
    """A skipped-only v2 report is never rendered green by the quick view."""
    report = _v2_report_multi([
        _v2_check("kit:S", "skipped-one", "skipped", "policy")])
    home = _webhook_report_home(tmp, "wh-v2-skipped", report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_check()
    check("webhook_quick_skipped_not_green",
          "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in out and "вЏё" in out,
          f"out={out[:100]!r}")


def probe_webhook_quick_malformed_rejected(wh, tmp: Path):
    """A v2 report without summary is rejected, never rendered as healthy."""
    report = _v2_report("healthy")
    del report["summary"]
    home = _webhook_report_home(tmp, "wh-v2-malformed", report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_check()
    check("webhook_quick_malformed_rejected",
          "РѕС‚РєР»РѕРЅС‘РЅ" in out and "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in out,
          f"out={out[:100]!r}")


def probe_webhook_schema_future_rejected(wh, tmp: Path):
    """An unknown future schema is rejected by both consumers, never legacy."""
    report = _v2_report("healthy")
    report["schema"] = 3
    home = _webhook_report_home(tmp, "wh-schema3", report)
    with override_environ(**_webhook_home_env(home)):
        quick = wh.handle_integrations_check()
        full = wh.handle_integrations_all()
    ok = ("РѕС‚РєР»РѕРЅС‘РЅ" in quick and "вњ… Argus:" not in quick
          and "РІСЃС‘ РІ РїРѕСЂСЏРґРєРµ" not in quick
          and "РѕС‚РєР»РѕРЅС‘РЅ" in full and "вњ…" not in full.split("\n")[0])
    check("webhook_schema_future_rejected", ok,
          f"quick={quick[:60]!r} full={full[:60]!r}")


def probe_webhook_full_v2_unknown_skipped(wh, tmp: Path):
    """Full view renders unknown as вљ пёЏ and skipped as вЏё with honest counts."""
    report = _v2_report_multi([
        _v2_check("kit:A", "alpha", "healthy", "d"),
        _v2_check("kit:B", "beta", "unknown", "unclear"),
        _v2_check("kit:C", "gamma", "unconfigured", "n/a"),
        _v2_check("kit:D", "delta", "skipped", "policy"),
    ])
    home = _webhook_report_home(tmp, "wh-v2-full", report)
    with override_environ(**_webhook_home_env(home)):
        out = wh.handle_integrations_all()
    ok = ("вљ пёЏ beta вЂ” unclear" in out and "вЏё delta вЂ” РїСЂРѕРїСѓС‰РµРЅРѕ" in out
          and "вљЄ gamma" in out and "вљ пёЏ 1" in out and "вЏё 1" in out)
    check("webhook_full_v2_unknown_skipped", ok, f"out={out[:120]!r}")


# в”Ђв”Ђ РџСЂРѕР±С‹: review pass 2 вЂ” mutation matrix РЅР° РєРѕРЅС‚СЂР°РєС‚ РѕС‚С‡С‘С‚Р° в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    ok = ("РѕС‚РєР»РѕРЅС‘РЅ" in quick and "вњ… Argus:" not in quick
          and "РѕС‚РєР»РѕРЅС‘РЅ" in full and "Argus РЅР°Р±Р»СЋРґР°РµС‚" not in full)
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


# в”Ђв”Ђ РџСЂРѕР±С‹: R2a fail-safe malformed YAML discovery в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    """Baseline СЃ РІР°Р»РёРґРЅС‹Рј РєРѕРЅС„РёРіРѕРј в†’ РґРµРіСЂР°РґР°С†РёСЏ; РїСѓС‚СЊ Рє РґРµРіСЂР°РґРёСЂРѕРІР°РЅРЅРѕРјСѓ
    СЃРЅР°РїС€РѕС‚Сѓ (РѕР±С‰Р°СЏ С„РёРєСЃС‚СѓСЂР° fail-closed РїСЂРѕР± РєРѕРЅСЃСЊСЋРјРµСЂРѕРІ)."""
    home = _r2a_home(tmp, name)
    write(home / "config.yaml", R2A_VALID_CFG)
    _r2a_run(home, args=["--baseline"])
    write(home / "config.yaml", R2A_CORRUPT_CFG)
    _r2a_run(home)
    snap = _r2a_snap(home)
    assert snap["discovery"]["status"] == "degraded", snap.get("discovery")
    return home


def probe_r2a_syntax_degraded_not_crash(tmp: Path):
    """R2a-1: СЃРёРЅС‚Р°РєСЃРёС‡РµСЃРєРё Р±РёС‚С‹Р№ config.yaml в†’ СЏРІРЅР°СЏ РґРµРіСЂР°РґР°С†РёСЏ (exit 2,
    Р±РµР· traceback), СЃРЅР°РїС€РѕС‚/РѕС‚С‡С‘С‚ РїРѕРјРµС‡РµРЅС‹ degraded СЃРѕ СЃС‚Р°Р±РёР»СЊРЅС‹Рј
    reason_code; Р±РµР· last-good РёРЅРІРµРЅС‚Р°СЂРёР·Р°С†РёСЏ РїСѓСЃС‚Р° Рё updated РїСѓСЃС‚."""
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
    """R2a-2: РІР°Р»РёРґРЅС‹Р№ YAML СЃ РІРµСЂС…РЅРёРј СѓСЂРѕРІРЅРµРј РЅРµ-СЃР»РѕРІР°СЂСЊ (list, Р·Р°С‚РµРј string)
    вЂ” РґРµРіСЂР°РґР°С†РёСЏ config_yaml_shape, Р° РЅРµ РїСѓСЃС‚РѕР№ Р·РґРѕСЂРѕРІС‹Р№ РёРЅРІРµРЅС‚Р°СЂСЊ; РїРѕРІС‚РѕСЂ СЃ
    С‚РµРј Р¶Рµ reason_code С‚РёС…РёР№."""
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
    """R2a-3: РІР°Р»РёРґРЅС‹Р№ РєРѕРЅС„РёРі вЂ” РїСЂРµР¶РЅСЏСЏ СЃРµРјР°РЅС‚РёРєР°: baseline С‚РёС…РёР№ (0), СЃС‚Р°С‚СѓСЃ
    ok, СЃСѓС‰РЅРѕСЃС‚Рё РёР·РІР»РµС‡РµРЅС‹; РїРѕРІС‚РѕСЂ Р±РµР· РёР·РјРµРЅРµРЅРёР№ С‚РёС…РёР№."""
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
    """R2a-4: РѕС‚СЃСѓС‚СЃС‚РІРёРµ config.yaml вЂ” РїСЂРµР¶РЅСЏСЏ СЃРµРјР°РЅС‚РёРєР° (РѕРє, РЅРµ РґРµРіСЂР°РґР°С†РёСЏ)."""
    home = _r2a_home(tmp, "r2a-missing")
    r1 = _r2a_run(home, args=["--baseline"])
    snap = _r2a_snap(home)
    check("r2a_missing_config_control",
          r1.returncode == 0 and snap["discovery"]["status"] == "ok"
          and snap["discovery"]["reason_code"] == "",
          f"rc={r1.returncode} disc={snap.get('discovery')}")


def probe_r2a_last_good_preserved(tmp: Path):
    """R2a-5: РїСЂРё РґРµРіСЂР°РґР°С†РёРё last-good entities/updated/config_hash СЃРѕС…СЂР°РЅРµРЅС‹
    РґРѕСЃР»РѕРІРЅРѕ; СЃРІРµР¶РµСЃС‚СЊ РЅРµ РїРµСЂРµРїРёСЃР°РЅР°; attempted_at РѕС‚РґРµР»СЏРµС‚ РїРѕРїС‹С‚РєСѓ,
    last_good_at СѓРєР°Р·С‹РІР°РµС‚ РЅР° РїРѕСЃР»РµРґРЅРёР№ СѓСЃРїРµС€РЅС‹Р№ РїСЂРѕРіРѕРЅ."""
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
    """R2a-6: РґРµРіСЂР°РґР°С†РёСЏ РЅРµ СЃРѕР·РґР°С‘С‚ removed/changed СЃРѕР±С‹С‚РёР№ РїРѕ СЃСѓС‰РЅРѕСЃС‚СЏРј вЂ”
    РµРґРёРЅСЃС‚РІРµРЅРЅРѕРµ СЃРѕР±С‹С‚РёРµ РѕС‚С‡С‘С‚Р°: discovery_degraded."""
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
    """R2a-7: РїРµСЂРІР°СЏ РґРµРіСЂР°РґР°С†РёСЏ РѕС‚С‡С‘С‚РЅР°СЏ (2), РїРѕРІС‚РѕСЂ РёРґРµРЅС‚РёС‡РЅРѕР№ вЂ” С‚РёС…РёР№ (0),
    СЃС‚Р°С‚СѓСЃ РІ СЃРЅР°РїС€РѕС‚Рµ РѕСЃС‚Р°С‘С‚СЃСЏ degraded."""
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
    """R2a-8: РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ РѕС‚С‡С‘С‚РЅРѕРµ; diff СЃС‡РёС‚Р°РµС‚СЃСЏ РѕС‚ last-good вЂ”
    Р»РµРіРёС‚РёРјРЅРѕРµ РґРѕР±Р°РІР»РµРЅРёРµ РІРёРґРЅРѕ РѕРґРёРЅ СЂР°Р·, Р·Р°РјРѕСЂРѕР¶РµРЅРЅС‹Рµ СЃСѓС‰РЅРѕСЃС‚Рё РЅРµ
    В«СѓРґР°Р»СЏСЋС‚СЃСЏВ» РёР·-Р·Р° malformed-РёРЅС‚РµСЂРІР°Р»Р°."""
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
    """R2a-9: РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ СЃ РЅРµРёР·РјРµРЅС‘РЅРЅС‹Рј РєРѕРЅС„РёРіРѕРј вЂ” РѕС‚С‡С‘С‚РЅРѕРµ СЃРѕР±С‹С‚РёРµ
    recovery Рё СЂРѕРІРЅРѕ РЅРѕР»СЊ entity-СЃРѕР±С‹С‚РёР№ (РЅРµС‚ remove/add-Р±СѓСЂРё)."""
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
    """R2a-10: health-check-v2 РЅР° РґРµРіСЂР°РґРёСЂРѕРІР°РЅРЅРѕРј СЃРЅР°РїС€РѕС‚Рµ вЂ” exit 2 С‡РµСЂРµР·
    СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№ config-error path Р”Рћ СЃРµС‚РµРІС‹С…/MCP-РїСЂРёРјРёС‚РёРІРѕРІ; СЃРІРµР¶РёР№
    health-РѕС‚С‡С‘С‚ РЅРµ РїРµСЂРµРїРёСЃС‹РІР°РµС‚СЃСЏ."""
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
    """R2a-11: ai-deep-check РЅР° РґРµРіСЂР°РґРёСЂРѕРІР°РЅРЅРѕРј СЃРЅР°РїС€РѕС‚Рµ вЂ” РѕС‚РєР°Р· Р”Рћ curl
    (РЅРѕР»СЊ РІС‹Р·РѕРІРѕРІ curl_json) СЃ РїРѕРЅСЏС‚РЅРѕР№ РґРёР°РіРЅРѕСЃС‚РёРєРѕР№."""
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
    """R2a: legacy-СЃРЅР°РїС€РѕС‚ Р±РµР· РєРѕРЅРІРµСЂС‚Р° discovery вЂ” pre-R2a СѓСЃРїРµС€РЅС‹Р№:
    discover РїСЂРё РґРµРіСЂР°РґР°С†РёРё СЃРѕС…СЂР°РЅСЏРµС‚ РµРіРѕ РёРЅРІРµРЅС‚Р°СЂРёР·Р°С†РёСЋ (last_good_at =
    legacy updated), Р° health-check-v2 РќР• Р·Р°РєСЂС‹РІР°РµС‚СЃСЏ РЅР° РЅС‘Рј."""
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
    # health: legacy-СЃРЅР°РїС€РѕС‚ (Р±РµР· РєРѕРЅРІРµСЂС‚Р°, РїСѓСЃС‚С‹Рµ СЃСѓС‰РЅРѕСЃС‚Рё) РЅРµ fail-closed
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
    """R2a-12: wrapper СЂРµРЅРґРµСЂРёС‚ РґРµРіСЂР°РґР°С†РёСЋ Рё РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ С‡РµР»РѕРІРµРєРѕС‡РёС‚Р°РµРјРѕ:
    payload СЃРѕРґРµСЂР¶РёС‚ humans-С‚РµРєСЃС‚ РїСЂРёС‡РёРЅС‹ Р±РµР· СЃС‹СЂС‹С… event-РёРјС‘РЅ/reason_code Рё
    Р±РµР· СЃРѕРґРµСЂР¶РёРјРѕРіРѕ РєРѕРЅС„РёРіР°; С‚РѕРєРµРЅ РґРѕСЃС‚Р°РІР»СЏРµС‚СЃСЏ С‚РѕР»СЊРєРѕ С‡РµСЂРµР· stdin."""
    home = tmp / "r2a-wrap-home"
    scripts = home / "scripts"
    hermes = home / ".hermes"
    scripts.mkdir(parents=True, exist_ok=True)
    # ~/.hermes/logs РІ РїСЂРѕРґРµ СЃРѕР·РґР°С‘С‚ deploy.sh; С„РёРєСЃС‚СѓСЂР° РїРѕРІС‚РѕСЂСЏРµС‚ СЌС‚Рѕ
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
                # discover-child РїРёРЅР°РµРј РЅР° С„РёРєСЃС‚СѓСЂСѓ: allowlist env СЂРµР¶РµС‚
                # USERPROFILE, Р° discover Р·РѕРІС‘С‚ Path.home() РїСЂРё Р»СЋР±РѕРј СЂР°СЃРєР»Р°РґРµ
                # (default-Р°СЂРіСѓРјРµРЅС‚ os.environ.get РІС‹С‡РёСЃР»СЏРµС‚СЃСЏ РІСЃРµРіРґР°) вЂ” СѓСЂРѕРє R1c
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
    # Payload СЃ rendered-С‚РµРєСЃС‚РѕРј СѓС…РѕРґРёС‚ РІ argv curl (-d), Р° СЂСѓСЃСЃРєРёР№ С‚РµРєСЃС‚
    # JSON-СЌСЃРєРµР№РїРёС‚СЃСЏ (ensure_ascii) вЂ” СЂР°Р·Р±РёСЂР°РµРј text-РїРѕР»СЏ РѕР±РѕРёС… РїСЂРѕРіРѕРЅРѕРІ.
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
          and "Р”РµРіСЂР°РґР°С†РёСЏ РѕР±РЅР°СЂСѓР¶РµРЅРёСЏ" in msg_text
          and "СЃРёРЅС‚Р°РєСЃРёС‡РµСЃРєР°СЏ РѕС€РёР±РєР°" in msg_text
          and "РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРѕ" in msg_text
          and "discovery_degraded" not in argv_text
          and "config_yaml_syntax" not in msg_text
          and "R2A_K1" not in argv_text
          and "DUMMY_R2A_TOKEN" not in argv_text
          and "DUMMY_R2A_TOKEN" in stdin_text,
          f"rc1={r1.returncode} rc2={r2.returncode} msgs={msg_text[:300]!r} "
          f"stderr={r1.stderr.decode(errors='ignore')[-200:]!r}")


def probe_r2a_secret_error_boundary(tmp: Path):
    """R2a-13: canary РІ Р±РёС‚РѕРј YAML (РїРѕС…РѕР¶ РЅР° СЃРµРєСЂРµС‚) РЅРµ РїРѕСЏРІР»СЏРµС‚СЃСЏ РІ
    stdout/stderr/СЃРЅР°РїС€РѕС‚Рµ/РѕС‚С‡С‘С‚Рµ вЂ” СЃС‹СЂРѕР№ С‚РµРєСЃС‚ РѕС€РёР±РєРё РїР°СЂСЃРµСЂР° РЅРµ РІС‹РІРѕРґРёС‚СЃСЏ."""
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
    """R2a (Pytna Finding 2): --baseline РіР»СѓС€РёС‚ entity-diff, РЅРѕ РќР• РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Р№
    degradedв†’ok РїРµСЂРµС…РѕРґ: recovery С‡РµСЂРµР· baseline-РїСЂРѕРіРѕРЅ РѕС‚С‡С‘С‚РЅС‹Р№ (2), СЃР»РµРґСѓСЋС‰РёР№
    РѕР±С‹С‡РЅС‹Р№ РїСЂРѕРіРѕРЅ С‚РёС…РёР№ (Р±РµР· РґСѓР±Р»СЏ)."""
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
    """R2a (Pytna Finding 1): config.yaml СЃ Р±РёС‚РѕР№ UTF-8 РїРѕСЃР»РµРґРѕРІР°С‚РµР»СЊРЅРѕСЃС‚СЊСЋ вЂ”
    РґРµРіСЂР°РґР°С†РёСЏ config_unreadable (RC 2, Р±РµР· traceback), РЅРµ РєСЂР°С… С‡С‚РµРЅРёСЏ."""
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
    """R2a.1: plugin.yaml СЃ YAML-list/Р±РёС‚С‹Рј YAML РїСЂРѕРїСѓСЃРєР°РµС‚СЃСЏ Р±РµР·РѕРїР°СЃРЅРѕ
    (РґРёСЃРєР°РІРµСЂРё Р·Р°РІРµСЂС€Р°РµС‚СЃСЏ, RC 0, Р±РµР· traceback), Р°РІС‚РѕСЂРёС‚РµС‚РЅС‹Р№ config.yaml
    РЅРµ РґРµРіСЂР°РґРёСЂСѓРµС‚; РІР°Р»РёРґРЅС‹Р№ mapping СЃРѕС…СЂР°РЅСЏРµС‚ РїСЂРµР¶РЅСЋСЋ СЃРµРјР°РЅС‚РёРєСѓ.
    РџСѓСЃС‚РѕР№/comment-only РІР°Р»РёРґРЅС‹Р№ YAML вЂ” С‚РѕР¶Рµ РїСЂРµР¶РЅСЏСЏ СЃРµРјР°РЅС‚РёРєР°: entity
    СЃ РёРјРµРЅРµРј РєР°С‚Р°Р»РѕРіР° (Pytna R2a.1-1 Finding 1); СЏРІРЅС‹Р№ scalar null вЂ” skip."""
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
    """R2a baseline follow-up (РІРЅРµС€РЅРёР№ СЂРµРІСЊСЋ P2): РїРµСЂРІР°СЏ РґРµРіСЂР°РґР°С†РёСЏ РѕС‚С‡С‘С‚РЅР°СЏ
    РґР°Р¶Рµ С‡РµСЂРµР· --baseline (exit 2, events=[discovery_degraded]); СЃР»РµРґСѓСЋС‰РёР№
    РѕР±С‹С‡РЅС‹Р№ РїСЂРѕРіРѕРЅ СЃ С‚РµРј Р¶Рµ reason С‚РёС…РёР№ (exit 0, events=[])."""
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


def probe_ux0_bot_interaction(mon, wh: object):
    """UX0 native keyboard, de-duplicated menu, alert keyboard, and poll auth."""
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
            override_attr(mon, "is_authorized", lambda user_id: str(user_id) == authorized_id), \
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


# в”Ђв”Ђ runner в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    probe_ux0_bot_interaction(mon, wh)
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

    # OA1: СЃС‚СЂСѓРєС‚СѓСЂРЅС‹Р№ account-auth discovery + РЅРµ-Р·РµР»С‘РЅР°СЏ health-СЃРµРјР°РЅС‚РёРєР°
    probe_oa1_discovery_fixtures(disc, tmp)
    probe_oa1_storage_shape_stability(disc, tmp)
    probe_oa1_malformed_ignored(disc, tmp)
    probe_oa1_copilot_compat(disc, tmp)
    probe_oa1_secret_canary_scan(tmp)
    probe_oa1_health_static_evidence_non_green(hc, tmp)
    probe_oa1_health_pat_only_unconfigured(hc, tmp)
    probe_oa1_quick_report_not_green(wh)
    probe_oa1_helpers_are_pure()
    # OA1b: РїСЂРµР·РµРЅС‚Р°С†РёРѕРЅРЅР°СЏ СЃРµРјР°РЅС‚РёРєР° OAuth-СЃРІРёРґРµС‚РµР»СЊСЃС‚РІ (webhook-СЂРµРЅРґРµСЂ)
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
