#!/usr/bin/env python3
"""fallback-tracker-v2.py — каскадный трекер фолбеков основного агента.

Парсит agent.log(+ротации): хопы 'Fallback to <prov>/<model>' (main-loop) и
'Primary runtime restored'. Алерты: первый провал primary (громкий), провал
до free-tier (громкий, тег FREE), восстановление (тихое). Дедуп — state JSON.

Замена model-fallback-tracker.py. Запуск: cron каждые 2-5 мин.
"""
import json, os, re, glob, time
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
HOP_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \S+ (?:\[\S+\] )?"
    r"agent\.chat_completion_helpers: Fallback to ([^/\s]+)/(.+?): "
    r"attached fallback credential pool")
RESTORE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \S+ (?:\[\S+\] )?"
    r"agent\.agent_runtime_helpers: Primary runtime restored for new turn: (\S+) \(([^)]+)\)")
FREE_RE = re.compile(r"(?:^|[:\-_/])free(?:$|[:\-_/.])", re.IGNORECASE)


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
                    m = HOP_RE.match(line)
                    if m:
                        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
                            tzinfo=timezone.utc).timestamp()
                        events.append({"ts": ts, "kind": "hop",
                                       "provider": m.group(2), "model": m.group(3)})
                        continue
                    m = RESTORE_RE.search(line)
                    if m:
                        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
                            tzinfo=timezone.utc).timestamp()
                        events.append({"ts": ts, "kind": "restore",
                                       "model": m.group(2), "provider": m.group(3)})
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


def main():
    env = load_env()
    st = read_state()
    events = scan_events()
    if not events:
        return

    # Первый запуск: baseline без алертов (иначе 181 исторических алертов)
    if "last_ts" not in st:
        last = events[-1]
        st.update({"last_ts": last["ts"],
                   "mode": "primary" if last["kind"] == "restore" else (
                       "free-hop" if FREE_RE.search(last.get("model", "")) else "fallback"),
                   "hops": 0})
        write_state(st)
        return

    now_mode = st.get("mode", "primary")
    last_processed = st.get("last_ts", 0)

    # Пропускаем уже обработанное
    fresh = [e for e in events if e["ts"] > last_processed]
    if not fresh:
        return

    for e in fresh:
        now_mode = st.get("mode", "primary")  # режим НА момент события
        if e["kind"] == "hop":
            is_free = bool(FREE_RE.search(e["model"]))
            # Алерт только на ПЕРВЫЙ хоп (переход primary→fallback) или на free-провал
            if now_mode == "primary" or (is_free and now_mode != "free-hop"):
                label = "FREE-TIER" if is_free else "fallback"
                send_alert(
                    f"📉 Модель недоступна: фолбек на {e['provider']}/{e['model']} "
                    f"({label}). Наблюдаю за каскадом.",
                    env, silent=False)
            st.update({"mode": "free-hop" if is_free else "fallback",
                       "last_hop": f"{e['provider']}/{e['model']}",
                       "hops": st.get("hops", 0) + 1})
        elif e["kind"] == "restore":
            if now_mode != "primary":
                send_alert(
                    f"✅ Primary восстановлен: {e['model']} ({e['provider']}). "
                    f"Каскад завершён (хопов: {st.get('hops', '?')}).",
                    env, silent=True)
            st.update({"mode": "primary", "hops": 0})
        st["last_ts"] = e["ts"]

    write_state(st)


if __name__ == "__main__":
    main()
