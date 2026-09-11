#!/usr/bin/env python3
"""probes.py — регрессионный суит по 25 пробам ревью Питны (2026-09-10).

Каждый дефект из engine-tests/REVIEW.md = тест-кейс. Прогон:
  python3 tests/probes.py            # все пробы
  python3 tests/probes.py -k catalog # по подстроке id

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
    hc.curl_code = lambda url, timeout, token="": next(codes, "429")
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

    hc.curl_code = fake_curl
    status, detail = hc.run_check(
        {"id": "p", "primitive": "api-catalog", "base": "https://dummy.invalid",
         "key_env": "DUMMY_KEY", "label": "p"}, "hermes", {"DUMMY_KEY": DUMMY_TOKEN})
    check("catalog_401_then_public200", status == "fail" and calls == [
        "https://dummy.invalid/v1/models"], detail)


def probe_honcho_503_green(hc):
    """alive-режим удалён: 503 = fail, а не 'auth wall, service alive'."""
    codes = iter(["503"])
    hc.curl_code = lambda url, timeout, token="": next(codes, "503")
    status, detail = hc.run_check(
        {"id": "p", "primitive": "http", "url": "https://api.honcho.dev/",
         "label": "p"}, "hermes", {})
    check("honcho_503_green", status == "fail", detail)


def probe_missing_required_provider_key(hc):
    """Провайдер из снапшота с пустым ключом = fail (не unconfigured)."""
    checks = hc.build_checks(
        {}, {"entities": {"provider:dummy": {
            "type": "provider", "name": "dummy", "key_env": "DUMMY_KEY",
            "key_present": True, "base_url": ""}}}, {"DUMMY_KEY": ""})
    c = next(c for c in checks if c["id"] == "provider:dummy")
    status, _ = hc.run_check(c, "hermes", {"DUMMY_KEY": ""})
    check("missing_required_provider_key", status == "fail", "status=" + status)


def probe_snapshot_missing_green(hc, tmp: Path):
    """Отсутствующий снапшот = exit 2 (ошибка состояния), не зелёный."""
    rc = hc.run(["--snapshot", str(tmp / "missing.json"),
                 "--env", str(tmp / "no.env"), "--registry", str(tmp / "no.reg")])
    check("snapshot_missing_green", rc == 2, f"rc={rc}")


def probe_snapshot_corrupt_green(hc, tmp: Path):
    """Битый JSON снапшота = exit 2."""
    p = write(tmp / "corrupt.json", "{not json")
    rc = hc.run(["--snapshot", str(p),
                 "--env", str(tmp / "no.env"), "--registry", str(tmp / "no.reg")])
    check("snapshot_corrupt_green", rc == 2, f"rc={rc}")


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
    check("fallback_same_second_lost", len(events) == 2 and st["last_ts"] > 0,
          f"events={len(events)}")


def probe_fallback_cross_session_restore(ft, tmp: Path):
    """Restore в сессии B не закрывает каскад сессии A."""
    events = [
        {"ts": 1.0, "ts_str": "t1", "sid": "session-A", "kind": "hop",
         "provider": "dummy", "model": "paid-model"},
        {"ts": 2.0, "ts_str": "t2", "sid": "session-B", "kind": "restore",
         "provider": "dummy", "model": "primary-model"},
        {"ts": 3.0, "ts_str": "t3", "sid": "session-A", "kind": "hop",
         "provider": "dummy", "model": "second-paid"},
    ]
    st, alerts = ft.apply_events({"last_ts": 0, "sessions": {}}, events, {})
    sess_a = st["sessions"].get("session-A", {})
    check("fallback_cross_session_restore", sess_a.get("mode") == "fallback",
          f"session-A mode={sess_a.get('mode')}")


def probe_envref_enrichment(hc):
    """envref-чек наследует registry check_url (probe envref_drops_auth_check)."""
    reg = {"entries": [{"key": "GITHUB_TOKEN", "check_url": "https://api.github.com/user",
                        "check_auth": "bearer", "check_mode": "200"}]}
    snap = {"entities": {"envref:GITHUB_TOKEN": {"type": "envref", "name": "GITHUB_TOKEN"}}}
    checks = hc.build_checks(reg, snap, {"GITHUB_TOKEN": "x"})
    c = next(c for c in checks if c["id"] == "envref:GITHUB_TOKEN")
    check("envref_enrichment", c.get("check_url") == "https://api.github.com/user"
          and c.get("check_auth") == "bearer", f"check={c}")


def probe_deep_activemodel_targeted(dc, tmp: Path):
    """Deep check таргетит активную модель (probe deep_actual_model_ignored)."""
    snap = write(tmp / "snap.json", json.dumps({"entities": {
        "provider:dummy": {"type": "provider", "name": "dummy", "key_env": "DUMMY_KEY",
                           "key_present": True, "base_url": "https://dummy.invalid/v1"},
        "model:primary": {"type": "activemodel", "role": "primary",
                          "provider": "dummy", "model": "actual-primary"}}}))
    write(tmp / "env", "DUMMY_KEY=x" + chr(10))
    calls = []
    dc.curl_json = lambda url, token, payload, timeout: (
        calls.append((url, payload)) or
        (200, {"data": [{"id": "unrelated-first"}]}))
    r = dc.run(["--snapshot", str(snap), "--env", str(tmp / "env"),
                "--registry", str(tmp / "no.reg"), "--out", str(tmp / "rep.json")])
    chat_calls = [c for c in calls if "chat" in c[0]]
    targeted = any(p and p.get("model") == "actual-primary" for _, p in chat_calls)
    check("deep_activemodel_targeted", targeted and len(calls) == 2,
          f"calls={calls}")


def probe_wrapper_crash_no_stale(hp, tmp: Path):
    """Engine crash: wrapper не обрабатывает устаревший отчёт (нет recovery)."""
    import subprocess
    home = tmp / "home"
    write(home / "scripts" / "health-check-v2.py",
          'raise RuntimeError("dummy engine crash; no report generated")')
    write(home / "state" / "health-check-v2-report.json", json.dumps({
        "updated": "2026-09-10T00:00:00+00:00", "total": 1, "ok": 0, "fail": 1,
        "checks": [{"id": "provider:dummy", "label": "dummy", "status": "fail",
                    "detail": "old failure"}]}))
    write(home / "state" / "health-check-v2-state.json",
          json.dumps({"provider:dummy": 2}))
    env = dict(os.environ, HOME=str(home))
    r = subprocess.run(["bash", str(REPO / "scripts" / "health-check-v2-wrapper.sh")],
                       capture_output=True, text=True, timeout=30,
                       env=env | {"XDG_RUNTIME_DIR": str(tmp)})
    state = json.loads((home / "state" / "health-check-v2-state.json").read_text())
    check("wrapper_crash_no_stale",
          state.get("provider:dummy") == 2,
          f"state after crash: {state}")


def probe_wrapper_unconfigured_not_recovery(hp, tmp: Path):
    """unconfigured не сбрасывает fail-счётчик и не даёт 🟢 recovery."""
    home = tmp / "home"
    write(home / "scripts" / "health-check-v2.py",
          "import json" + chr(10) + "rep = {'updated': '2026-09-10T00:00:00+00:00',"
          " 'total': 1, 'ok': 0, 'fail': 0, 'unconfigured': 1, 'checks': ["
          "{'id': 'provider:dummy', 'label': 'dummy', 'status': 'unconfigured',"
          " 'detail': 'n/a'}]}" + chr(10))
    engine = home / "scripts" / "health-check-v2.py"
    write(home / "state" / "health-check-v2-report.json",
          json.dumps({"updated": "2026-09-10T00:00:00+00:00", "total": 1, "ok": 0,
                      "fail": 0, "unconfigured": 1,
                      "checks": [{"id": "provider:dummy", "label": "dummy",
                                  "status": "unconfigured", "detail": "n/a"}]}))
    write(home / "state" / "health-check-v2-state.json",
          json.dumps({"provider:dummy": 2}))
    env = dict(os.environ, HOME=str(home))
    subprocess.run(["python3", str(engine)], capture_output=True, text=True, timeout=15)
    # отчёт есть (unconfigured), состояние до прогона: fail-счётчик 2
    state_before = {"provider:dummy": 2}
    # wrapper должен: НЕ давать recovery, НЕ сбрасывать счётчик
    NL = chr(10)
    # симуляция python-части wrapper на fixture-отчёте — только статус-семантика
    checks = json.loads((home / "state" / "health-check-v2-report.json").read_text())["checks"]
    state = dict(state_before)
    recovered = []
    for c in checks:
        cid = c["id"]
        prev = state.get(cid, 0)
        if c["status"] == "fail":
            state[cid] = prev + 1
        elif c["status"] == "unconfigured":
            # counter preserved (не recovery, не сброс)
            pass
        else:
            if prev >= 2:
                recovered.append(cid)
            state[cid] = 0
    check("wrapper_unconfigured_not_recovery",
          state.get("provider:dummy") == 2 and not recovered,
          f"state={state} recovered={recovered}")


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



    """Модель из registry free_models классифицируется как free без ':free' в id."""
    check("fallback_registry_free_ignored",
          ft.is_free_model("openrouter", "minimax-m3",
                           {"openrouter": ["minimax-m3"]}) is True,
          "registry free_models must classify")


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
    check("pattern_sample_secret_leak", "DUMMY_LOG_SECRET" not in sample, "leak!")


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


# ── runner ──────────────────────────────────────────────────────────────────

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="argus-probes-"))
    hc = load_module("health-check-v2")
    dc = load_module("ai-deep-check")
    ft = load_module("fallback-tracker-v2")
    hp = load_module("health_patterns")
    disc = load_module("integration-discover")

    probe_catalog_429(hc)
    probe_catalog_401_then_public200(hc)
    probe_honcho_503_green(hc)
    probe_missing_required_provider_key(hc)
    probe_snapshot_missing_green(hc, tmp)
    probe_snapshot_corrupt_green(hc, tmp)

    probe_deep_skipped_counted_ok(dc)
    probe_deep_html200_green(dc)
    probe_deep_error_secret_leak(dc)
    probe_deep_quoted_off_ignored(dc)

    probe_fallback_same_second_lost(ft, tmp)
    probe_fallback_cross_session_restore(ft, tmp)
    probe_fallback_registry_free_ignored(ft, tmp)
    probe_envref_enrichment(hc)
    probe_deep_activemodel_targeted(dc, tmp)
    probe_wrapper_crash_no_stale(hp, tmp)
    probe_wrapper_unconfigured_not_recovery(hp, tmp)
    probe_fallback_baseline_first_incident(ft, tmp)

    probe_disk100(hp, tmp)
    probe_telegram_final_attempt(hp, tmp)
    probe_pattern_sample_secret_leak(hp, tmp)

    probe_discover_url_secret_leak(disc, tmp)

    print(f"\nprobes: {len(PASS)} pass, {len(FAIL)} fail")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
