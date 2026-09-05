#!/usr/bin/env python3
"""model-fallback-tracker.py — фиксирует, какая модель реально работала в сессиях.

Парсит agent.log (и ротации agent.log.N) на строки вида:
  API call #N: model=deepseek-v4-pro provider=opencode-go ...
  Turn ended: ... model=deepseek-v4-flash ...
При переходе основной модели на free-тир OpenRouter (модель с суффиксом :free)
пишет алерт в мониторинг-бот и state. При возврате на основную — тихое уведомление.
Висим на free — тишина (дедуп как в watchdog, 17.08): один алерт на падение + один на восстановление.

State: ~/.hermes/state/model-fallback-state.json
  {"mode": "primary"|"free"|"unknown", "model": "...", "provider": "...",
   "since": "<iso>", "last_alert": <epoch>}
Алерты: WATCHDOG_BOT_TOKEN → WATCHDOG_CHAT_ID через telegram-smart-proxy (8444), если жив.
Запуск: системный crontab (bash-уровень, без LLM), каждые 5 минут. Молчит, когда стабильно.

История:
  2026-09-04: убран повторный ремайндер «все еще на free» (спам каждые 5 мин после 30 мин
  из-за несохранения last_alert — write_state вызывался только при смене модели).
  Теперь только переходы free<->primary (CONVENTIONS dedup). Recovery — тихий.
"""

import json
import os
import re
import glob
import time
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
LOG_DIR = os.path.join(HOME, ".hermes", "logs")
STATE_FILE = os.path.join(HOME, ".hermes", "state", "model-fallback-state.json")
FREE_SUFFIX = ":free"
ENV_FILE = os.path.join(HOME, ".hermes", ".env")

CALL_RE = re.compile(
    r"(?:API call #\d+|Turn ended):.*?\bmodel=(\S+)\s+provider=(\S+)"
)
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


def load_env():
    env = {}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def read_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, ensure_ascii=False)


def send_alert(text, env, silent=False):
    token = env.get("WATCHDOG_BOT_TOKEN")
    chat = env.get("WATCHDOG_CHAT_ID")
    if not token or not chat:
        return
    # Алерты через smart-proxy, если он жив (переживает РКН-волны)
    proxy_args = []
    try:
        with open("/dev/tcp/127.0.0.1/8444", "w"):
            proxy_args = ["--proxy", "http://127.0.0.1:8444"]
    except OSError:
        pass
    notify = "true" if silent else "false"
    cmd = ["curl", "-s", *proxy_args, "--connect-timeout", "10", "--max-time", "15",
           "-X", "POST", f"https://api.telegram.org/bot{token}/sendMessage",
           "-d", f"chat_id={chat}", "--data-urlencode", f"text={text}",
           "-d", f"disable_notification={notify}", "-o", "/dev/null"]
    import subprocess
    subprocess.run(cmd, capture_output=True)


def main():
    env = load_env()
    st = read_state()

    # Собираем строки с model= из свежих логов (агент.лог + ротации)
    latest_ts = None
    latest_model = None
    latest_provider = None
    files = sorted(glob.glob(os.path.join(LOG_DIR, "agent.log*")),
                   key=lambda p: 0 if "agent.log" == os.path.basename(p) else int(
                       os.path.basename(p).rsplit(".", 1)[-1]) if os.path.basename(p).rsplit(".", 1)[-1].isdigit() else 1)
    for path in files:
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    m_ts = TS_RE.match(line)
                    m = CALL_RE.search(line)
                    if m_ts and m:
                        ts = datetime.strptime(m_ts.group(1)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if latest_ts is None or ts >= latest_ts:
                            latest_ts = ts
                            latest_model, latest_provider = m.group(1), m.group(2)
        except FileNotFoundError:
            continue
        except Exception:
            continue

    now = time.time()
    mode = "unknown"
    if latest_model:
        is_free = FREE_SUFFIX in latest_model
        mode = "free" if is_free else "primary"

    if latest_ts is None:
        return

    prev_mode = st.get("mode")
    prev_model = st.get("model")

    # Переход на free-тир → громкий алерт (один раз, дальше тишина пока висим)
    if mode == "free" and prev_mode != "free":
        send_alert(f"Модель упала на free-тир: {latest_model} ({latest_provider}) с {prev_model or 'неизвестно'}. Проверь основного провайдера!", env, silent=False)
        st.update({
            "mode": mode,
            "model": latest_model,
            "provider": latest_provider,
            "since": latest_ts.isoformat(),
            "last_alert": now,
        })
        write_state(st)
    # Возврат с free → тихое уведомление (рутина — тихо, CONVENTIONS)
    elif mode == "primary" and prev_mode == "free":
        send_alert(f"Модель вернулась на основную: {latest_model} ({latest_provider}).", env, silent=True)
        st.update({
            "mode": mode,
            "model": latest_model,
            "provider": latest_provider,
            "since": latest_ts.isoformat(),
            "last_alert": now,
        })
        write_state(st)
    elif mode != prev_mode or latest_model != prev_model or not st:
        # Смена модели внутри одного режима (напр. gemma:free → nemotron:free)
        # или первый запуск — state обновить молча, since не трогаем если режим тот же.
        st.update({
            "mode": mode,
            "model": latest_model,
            "provider": latest_provider,
            "since": latest_ts.isoformat() if mode != prev_mode else st.get("since", latest_ts.isoformat()),
        })
        write_state(st)


if __name__ == "__main__":
    main()
