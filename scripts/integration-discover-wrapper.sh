#!/bin/bash
# Обёртка discover: алерт в TG при событиях (added/removed/changed ключей).
# Молчит при пустом diff. exit 2 → systemd SuccessExitStatus.
set -u
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
H="$HOME/.hermes"
LOG="$H/logs/integration-discover.log"

# Lock: path-триггер и cron-страховка могут сработать одновременно — второй
# запуск молча пропускаем, иначе алерты о изменениях задваиваются.
LOCK="/tmp/hermes-argus-discover.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -Is)] discover: уже запущен, пропуск" >> "$LOG"
    exit 0
fi

REPORT=$(python3 "$HOME/scripts/integration-discover.py" 2>>"$LOG")
RC=$?
echo "[$(date -Is)] discover exit=$RC" >> "$LOG"

[ "$RC" != "2" ] && exit 0

# Есть события — алерт в TG (новое в конфиге = важно)
source "$H/.env" 2>/dev/null || true
if [ -z "${WATCHDOG_BOT_TOKEN:-}" ]; then
    echo "$REPORT" >> "$LOG"
    exit 0
fi

SUMMARY=$(printf '%s' "$REPORT" | python3 -c '
import json, sys
r = json.load(sys.stdin)
lines = []
icon_map = {"added": "\U0001F7E2", "removed": "\U0001F534", "changed": "\U0001F7E1"}
# R2a: discovery-переходы рендерятся человекочитаемо; сырой текст ошибки
# парсера/YAML не выводится — в config.yaml могут быть секреты.
reason_text = {
    "config_yaml_syntax": "config.yaml: синтаксическая ошибка",
    "config_yaml_shape": "config.yaml: верхний уровень — не словарь",
    "config_unreadable": "config.yaml: файл не читается",
}
for e in r["events"][:10]:
    ent = e.get("entity") or {}
    if e.get("event") == "discovery_degraded":
        reason = reason_text.get(ent.get("reason_code"), ent.get("reason_code") or "неизвестная причина")
        lines.append("\u26A0\uFE0F Деградация обнаружения интеграций: " + reason
                     + " (инвентаризация заморожена на last-good)")
        continue
    if e.get("event") == "discovery_recovered":
        lines.append("\U0001F50C Обнаружение интеграций восстановлено: config.yaml снова читается")
        continue
    t = ent.get("type", "?")
    n = ent.get("name", e["key"])
    icon = icon_map.get(e["event"], "\u26AA")
    lines.append(icon + " " + e["event"] + ": " + t + " " + n)
extra = len(r["events"]) - 10
if extra > 0:
    lines.append("  …и ещё " + str(extra))
print("\n".join(lines))
' 2>>"$LOG")

if [ -z "$SUMMARY" ]; then
    SUMMARY="$REPORT"
fi

MSG="🔌 <b>Интеграции: изменения конфига</b>
$SUMMARY"
MSG_ESC=$(python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" <<< "$MSG")
proxy="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
# Токен не в argv: URL уходит в curl через -K - (config на stdin)
printf 'url = %s\n' "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" | \
    curl -s -m 20 -x "$proxy" -K - -X POST \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\": \"${WATCHDOG_CHAT_ID}\", \"text\": $MSG_ESC, \"parse_mode\": \"HTML\"}" \
    -o /dev/null >> "$LOG" 2>&1 || true
echo "[$(date -Is)] алерт отправлен" >> "$LOG"
exit 0
