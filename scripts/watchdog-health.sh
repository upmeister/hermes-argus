#!/bin/bash
# watchdog-health.sh — мониторинг самого мониторинга (L1.5)
# Проверяет, что все компоненты системы мониторинга живы.
# Запуск: system cron, каждый час.
# Если мониторинг не работает — алерт в мониторинг-бот.
set -u
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
H="$HOME/.hermes"
LOG="$H/logs/watchdog-health.log"
STATE_FILE="$H/logs/health-state.json"
NOW=$(date +%s)

problems=""

# 1. health-state.json свежий? (не старше 2 часов)
if [ "@MODULE_ANALYZER@" = "ON" ]; then
if [ -f "$STATE_FILE" ]; then
    LAST_CHECK=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('last_check',''))" 2>/dev/null)
    if [ -n "$LAST_CHECK" ]; then
        LAST_TS=$(date -d "$LAST_CHECK" +%s 2>/dev/null || echo 0)
        AGE=$(( (NOW - LAST_TS) / 60 ))
        if [ "$AGE" -gt 150 ]; then  # 2.5 часа — запас
            problems="$problems\n⚠️ L3 health-check stale: last run ${AGE}min ago"
        fi
    else
        problems="$problems\n⚠️ L3 health-state.json: no last_check"
    fi
else
    problems="$problems\n⚠️ L3 health-state.json: not found"
fi
fi

# 2. watchdog cron работает?
if ! crontab -l 2>/dev/null | grep -q "hermes-watchdog.sh"; then
    problems="$problems\n⚠️ Watchdog cron entry missing"
else
    # Проверка свежести watchdog.log
    if [ -f "$H/logs/watchdog.log" ]; then
        WATCHDOG_AGE=$(( NOW - $(stat -c %Y "$H/logs/watchdog.log" 2>/dev/null || echo 0) ))
        if [ "$WATCHDOG_AGE" -gt 600 ]; then  # 10 минут
            problems="$problems\n⚠️ Watchdog log stale: ${WATCHDOG_AGE}s ago"
        fi
    fi
fi

# 3. gateway-liveness cron работает?
if ! crontab -l 2>/dev/null | grep -q "gateway-liveness.sh"; then
    problems="$problems\n⚠️ gateway-liveness cron entry missing"
fi

# 4. dashboard-liveness cron работает?
if ! crontab -l 2>/dev/null | grep -q "dashboard-liveness.sh"; then
    problems="$problems\n⚠️ dashboard-liveness cron entry missing"
fi

# 5. Мониторинг-бот активен?
if [ "@MODULE_TG_BOT@" = "ON" ]; then
    if ! systemctl --user is-active monitoring-bot-poller.service >/dev/null 2>&1; then
        problems="$problems\n⚠️ monitoring-bot-poller.service not active"
    fi
fi

# 6. Netdata health
NETDATA_LOAD_STATE=$(systemctl show -p LoadState --value netdata.service 2>/dev/null || echo unknown)
if [ "$NETDATA_LOAD_STATE" != "not-found" ] && ! systemctl is-active netdata.service >/dev/null 2>&1; then
    problems="$problems\n⚠️ netdata.service not active (system)"
fi

# 7. Heartbeat работает?
GH_HEARTBEAT_DIR="$H/gh-heartbeat"
if [ ! -d "$GH_HEARTBEAT_DIR" ]; then
    GH_HEARTBEAT_DIR="$H/hermes-infra"
fi
if [ -f "$GH_HEARTBEAT_DIR/heartbeat.txt" ]; then
    HB_AGE=$(( NOW - $(stat -c %Y "$GH_HEARTBEAT_DIR/heartbeat.txt" 2>/dev/null || echo 0) ))
    if [ "$HB_AGE" -gt 900 ]; then  # 15 минут
        problems="$problems\n⚠️ Heartbeat stale: ${HB_AGE}s ago"
    fi
fi

# Отчёт
if [ -n "$problems" ]; then
    echo -e "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] PROBLEMS FOUND:$problems" >> "$LOG"
    # Отправляем в мониторинг-бот
    source "$HOME/.hermes/.env" 2>/dev/null || true
    MSG="⚠️ <b>Мониторинг мониторинга</b> (%HOSTNAME%)
Обнаружены проблемы:$problems"
    MSG_ESC=$(echo "$MSG" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
    # Токен не в argv: URL уходит в curl через -K - (config на stdin)
    printf 'url = %s\n' "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" | \
        curl -s -K - -X POST \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\": \"$WATCHDOG_CHAT_ID\", \"text\": $MSG_ESC, \"parse_mode\": \"HTML\", \"disable_notification\": false}" \
        -o /dev/null -x "${TELEGRAM_PROXY:-}" 2>/dev/null || true
else
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] All OK" >> "$LOG"
fi
