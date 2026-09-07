#!/bin/bash
# register-commands.sh — canonical Telegram command list for the Argus bot.
# Idempotent: safe to run on every deploy. Needs WATCHDOG_BOT_TOKEN in
# ~/.hermes/.env; exits silently (log) when the token is absent.
# Canon: add new commands HERE, deploy.sh registers them automatically
# (before 2026-09-07 the list was registered manually — drift risk).

set -u
H="$HOME/.hermes"
LOG="$H/logs/argus.log"

[ -f "$H/.env" ] && set -a && source "$H/.env" && set +a
if [ -z "${WATCHDOG_BOT_TOKEN:-}" ]; then
    echo "[$(date -Is)] register-commands: no WATCHDOG_BOT_TOKEN, skip" >> "$LOG"
    exit 0
fi

python3 - "$WATCHDOG_BOT_TOKEN" "${TELEGRAM_PROXY:-http://127.0.0.1:8444}" <<'PYEOF'
import json, sys, urllib.request

token, proxy = sys.argv[1], sys.argv[2]
commands = [
    {"command": "health", "description": "Argus: статус сервисов и системы"},
    {"command": "integrations", "description": "Быстрый статус интеграций"},
    {"command": "integrations_all", "description": "Все интеграции по группам"},
    {"command": "watchdog", "description": "Статус стража мониторинга"},
    {"command": "uptime", "description": "Аптайм и нагрузка"},
    {"command": "deepcheck", "description": "Deep check AI-провайдеров (chat ping)"},
    {"command": "settings", "description": "Настройки Argus (read-only)"},
    {"command": "logs", "description": "Последние строки gateway.log"},
    {"command": "network", "description": "Статус сети"},
    {"command": "silence", "description": "Заглушить алерты на N часов"},
    {"command": "menu", "description": "Панель кнопок"},
    {"command": "reboot", "description": "Перезагрузка сервера (2 шага)"},
    {"command": "restart_gw", "description": "Рестарт gateway"},
    {"command": "restart_dash", "description": "Рестарт dashboard"},
    {"command": "restart_all", "description": "Рестарт gateway+dashboard"},
]
data = json.dumps({"commands": commands}).encode()
req = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/setMyCommands", data=data,
    headers={"Content-Type": "application/json"})
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
try:
    with opener.open(req, timeout=20) as r:
        resp = json.load(r)
    print("register-commands:", "ok" if resp.get("ok") else resp)
    sys.exit(0 if resp.get("ok") else 1)
except Exception as e:
    print(f"register-commands FAILED: {e}")
    sys.exit(1)
PYEOF
