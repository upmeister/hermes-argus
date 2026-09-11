#!/usr/bin/env python3
"""fallback-tracker-v2.py — каскадный трекер фолбеков основного агента.

Парсит agent.log(+ротации): хопы 'Fallback to <prov>/<model>' (main-loop) и
'Primary runtime restored'. Алерты: первый провал primary (громкий), провал
до free-tier (громкий, тег FREE), восстановление (тихое). Дедуп — state JSON.

Замена model-fallback-tracker.py. Запуск: cron каждые 2-5 мин.
C1 (2026-09-07): session-id из строк лога ([YYYYMMDD_HHMMSS_hex8]) попадает
в алерты — различение тестов/эпизодов (инцидент неразличимости двух тестов).
"""
import json, os, re, glob, time, sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
LOG_DIR = HOME / ".hermes" / "logs"
STATE_FILE = HOME / ".hermes" / "state" / "fallback-tracker-state.json"
ENV_FILE = HOME / ".hermes" / ".env"

# main-loop хопы: 'Fallback to X/Y: ...' от chat_completion_helpers (не auxiliary_client!)
# Хоп = ТОЛЬКО 'attached fallback credential pool' (финальное закрепление перехода).
# Строки 'clearing primary credential pool' — внутренняя кухня ТОГО ЖЕ перехода
# (одна секунда, та же сессия) — без фильтра один хоп считался дважды
# и порождал дубли-алерты (урок 2026-09-06).
# C1: session-id ([YYYYMMDD_HHMMSS_hex8]) сохраняется (группа 2) — per-turn
# correlation id, меняется на каждый хоп.
HOP_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) \S+ (?:\[(\S+)\] )?"
    r"agent\.chat_completion_helpers: Fallback to ([^/\s]+)/(.+?): "
    r"attached fallback credential pool")
RESTORE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) \S+ (?:\[(\S+)\] )?"
    r"agent\.agent_runtime_helpers: Primary runtime restored for new turn: (\S+) \(([^)]+)\)")
FREE_RE = re.compile(r"(?:^|[:\-_/])free(?:$|[:\-_/.])", re.IGNORECASE)


def parse_line(line):
    """Log line -> event dict (ts_epoch, ts_str, sid, kind, provider, model) or None.

    ts_str is the log's naive LOCAL timestamp, displayed as-is in alerts
    (tracker convention: log TZ is local, epoch is used for dedup only).
    """
    m = HOP_RE.match(line)
    if m:
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp() + int(m.group(2)) / 1000.0
        return {"ts": ts, "ts_str": m.group(1), "sid": m.group(3) or "n/a",
                "kind": "hop", "provider": m.group(4), "model": m.group(5)}
    m = RESTORE_RE.search(line)
    if m:
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp() + int(m.group(2)) / 1000.0
        return {"ts": ts, "ts_str": m.group(1), "sid": m.group(3) or "n/a",
                "kind": "restore", "model": m.group(4), "provider": m.group(5)}
    return None


def load_env():
    env = {}
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def read_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def write_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False))


def scan_events():
    """Хронологические события (ts_epoch, kind, model, provider) из свежих логов."""
    events = []
    files = sorted(glob.glob(str(LOG_DIR / "agent.log*")),
                   key=lambda p: (0 if p.endswith("agent.log") else 1, p))
    for path in files:
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    e = parse_line(line)
                    if e:
                        events.append(e)
        except FileNotFoundError:
            continue
    events.sort(key=lambda e: e["ts"])
    return events


def send_alert(text, env, silent=False):
    token = env.get("WATCHDOG_BOT_TOKEN")
    chat = env.get("WATCHDOG_CHAT_ID")
    if not token or not chat:
        return
    proxy_args = []
    try:
        import socket
        s = socket.create_connection(("127.0.0.1", 8444), timeout=1)
        s.close()
        proxy_args = ["--proxy", "http://127.0.0.1:8444"]
    except OSError:
        pass
    import subprocess
    notify = "true" if silent else "false"
    subprocess.run(["curl", "-s", *proxy_args, "--connect-timeout", "10", "--max-time", "15",
                    "-X", "POST", f"https://api.telegram.org/bot{token}/sendMessage",
                    "-d", f"chat_id={chat}", "--data-urlencode", f"text={text}",
                    "-d", f"disable_notification={notify}", "-o", "/dev/null"],
                   capture_output=True)


def selftest():
    """Synthetic log lines -> parsed events. Proves: hop dedup (clearing line
    ignored), session-id capture on hop and restore. Exit 1 on failure."""
    fixtures = [
        "2026-09-07 01:00:00,123 INFO [20260907_010000_abcd1234] agent.chat_completion_helpers: "
        "Fallback to openrouter/minimax-m3:free: clearing primary credential pool (pool_provider=xai)",
        "2026-09-07 01:00:00,124 INFO [20260907_010000_abcd1234] agent.chat_completion_helpers: "
        "Fallback to openrouter/minimax-m3:free: attached fallback credential pool",
        "2026-09-07 01:05:00,042 INFO [20260907_010500_deadbeef] agent.agent_runtime_helpers: "
        "Primary runtime restored for new turn: z-ai/glm-5.2 (openrouter)",
        "2026-09-07 01:06:00,000 INFO agent.chat_completion_helpers: "
        "Fallback to openrouter/gemma-3:free: attached fallback credential pool",
    ]
    events = [e for line in fixtures if (e := parse_line(line))]
    hops = [e for e in events if e["kind"] == "hop"]
    restores = [e for e in events if e["kind"] == "restore"]

    checks = [
        ("clearing line must NOT match (hop dedup)", len(hops) == 2),
        ("hop session-id captured", hops and hops[0]["sid"] == "20260907_010000_abcd1234"),
        ("hop provider/model", hops and hops[0]["provider"] == "openrouter"
         and hops[0]["model"] == "minimax-m3:free"),
        ("restore session-id captured", restores and restores[0]["sid"] == "20260907_010500_deadbeef"),
        ("no-session line still parses (sid=n/a)",
         any(e["sid"] == "n/a" for e in hops)),
        ("restore provider/model", restores and restores[0]["model"] == "z-ai/glm-5.2"
         and restores[0]["provider"] == "openrouter"),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    print(f"events parsed: {len(events)} (hops={len(hops)}, restores={len(restores)})")
    sys.exit(1 if failed else 0)


def load_free_models() -> dict:
    """registry.yaml free_models (provider -> [models]); {} on any failure."""
    try:
        import yaml
        reg = Path(STATE_FILE).parent / "registry.yaml"
        return (yaml.safe_load(reg.read_text(encoding="utf-8")) or {}).get("free_models", {}) or {}
    except Exception:
        return {}


def is_free_model(provider: str, model: str, free_models: dict) -> bool:
    """Free = ':free'-style token in the model id OR the registry free_models
    list for this provider (probe fallback_registry_free_ignored)."""
    if FREE_RE.search(model or ""):
        return True
    for key, models in (free_models or {}).items():
        if (provider == key or provider.startswith(key)) and model in (models or []):
            return True
    return False


def apply_events(state: dict, events: list, free_models: dict | None = None) -> tuple[dict, list]:
    """Pure cascade state machine: (state, events) -> (new_state, alerts).

    Per-session cascade state: a restore closes only ITS OWN session's cascade
    (probe fallback_cross_session_restore). Alerts are dicts {text, silent} —
    the caller owns delivery.
    """
    alerts = []
    sessions = state.get("sessions", {})
    if not events:
        state.setdefault("last_ts", 0)
        state["sessions"] = sessions
        return state, alerts

    # First run with history: baseline to the newest event, no alerts.
    if "last_ts" not in state:
        last = events[-1]
        sid = last.get("sid", "n/a")
        sess = sessions.setdefault(sid, {"mode": "primary", "hops": 0})
        sess["mode"] = "primary" if last["kind"] == "restore" else (
            "free-hop" if is_free_model(last.get("provider", ""), last.get("model", ""), free_models)
            else "fallback")
        state.update({"last_ts": last["ts"], "sessions": sessions})
        return state, alerts

    fresh = [e for e in events if e["ts"] > state.get("last_ts", 0)]
    for e in fresh:
        sid = e.get("sid", "n/a")
        sess = sessions.setdefault(sid, {"mode": "primary", "hops": 0})
        if e["kind"] == "hop":
            is_free = is_free_model(e.get("provider", ""), e.get("model", ""), free_models)
            if sess["mode"] == "primary" or (is_free and sess["mode"] != "free-hop"):
                label = "FREE-TIER" if is_free else "fallback"
                alerts.append({
                    "text": (f"📌 Модель недоступна: фолбек на {e['provider']}/{e['model']} "
                             f"({label}) · session {sid} · log {e['ts_str']}. Наблюдаю за каскадом."),
                    "silent": False})
            sess["mode"] = "free-hop" if is_free else "fallback"
            sess["hops"] = sess.get("hops", 0) + 1
        elif e["kind"] == "restore":
            if sess["mode"] != "primary":
                alerts.append({
                    "text": (f"✅ Primary восстановлен: {e['model']} ({e['provider']}) "
                             f"· session {sid} · log {e['ts_str']}. "
                             f"Каскад завершён (хопов: {sess.get('hops', '?')})."),
                    "silent": True})
            sess.update({"mode": "primary", "hops": 0})
        state["last_ts"] = e["ts"]

    state["sessions"] = sessions
    return state, alerts


def main():
    env = load_env()
    st = read_state()
    events = scan_events()
    free_models = load_free_models()

    # Baseline на пустых логах: last_ts=0, чтобы первый будущий инцидент алертил
    if not events and "last_ts" not in st:
        st.update({"last_ts": 0, "sessions": {}})
        write_state(st)
        return

    new_state, alerts = apply_events(st, events, free_models)
    write_state(new_state)
    for a in alerts:
        send_alert(a["text"], env, silent=a["silent"])


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
