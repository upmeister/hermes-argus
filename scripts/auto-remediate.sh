#!/bin/bash
# Auto-remediation: безопасные авто-фиксы для типовых проблем
# Запуск: каждые 10 минут через системный cron
# Принцип: только операции без риска потери данных
# Swap occupancy is diagnostic; pressure-aware alerting lives in watchdog.

set -euo pipefail

HERMES_DIR="@HERMES_DIR@"
LOG_FILE="$HERMES_DIR/logs/auto-remediate.log"
STATE_DIR="$HERMES_DIR/logs/auto-remediate-state"
REPORT=""

mkdir -p "$HERMES_DIR/logs" "$STATE_DIR"
LOCK_FILE="$STATE_DIR/auto-remediate.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    printf '[%s] auto-remediate уже выполняется — пропускаю параллельный запуск\n' \
        "$(date -u +'%Y-%m-%d %H:%M UTC')" >> "$LOG_FILE"
    exit 0
fi

# cron does not export .env — load secrets ourselves.
if [ -f "$HERMES_DIR/.env" ]; then
    set -a
    source "$HERMES_DIR/.env"
    set +a
fi

# ═══════════════════════════════════════════════════════════════════════════
# Circuit breaker: если авто-фикс срабатывал >3 раз за час — стоп
# ═══════════════════════════════════════════════════════════════════════════

CIRCUIT_FILE="$STATE_DIR/circuit-breaker.txt"
HOUR_KEY=$(date -u +"%Y-%m-%dT%H")

CURRENT_COUNT=0
if [ -f "$CIRCUIT_FILE" ]; then
    STORED_KEY=$(head -1 "$CIRCUIT_FILE" 2>/dev/null || true)
    STORED_COUNT=$(tail -1 "$CIRCUIT_FILE" 2>/dev/null || true)
    if [ "$STORED_KEY" = "$HOUR_KEY" ] && [[ "$STORED_COUNT" =~ ^[0-9]+$ ]]; then
        CURRENT_COUNT=$STORED_COUNT
    fi
fi

if [ "$CURRENT_COUNT" -ge 3 ]; then
    printf '[%s] CIRCUIT BREAKER: %s авто-фиксов за час — стоп\n' \
        "$(date -u +'%Y-%m-%d %H:%M UTC')" "$CURRENT_COUNT" >> "$LOG_FILE"
    if [ -n "${WATCHDOG_BOT_TOKEN:-}" ]; then
        printf 'url = %s\n' "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" | \
            curl -s -K - -m 15 -x "${TELEGRAM_PROXY:-http://127.0.0.1:8444}" -X POST \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\":\"@WATCHDOG_CHAT_ID@\",\"text\":\"🚨 Circuit Breaker: ${CURRENT_COUNT} авто-фиксов за час. Требуется вмешательство человека.\"}" \
            -o /dev/null 2>&1 || true
    fi
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════
# Проверка режима тишины (silence)
# ═══════════════════════════════════════════════════════════════════════════

SILENCE_FILE="$STATE_DIR/silence-until.txt"
if [ -f "$SILENCE_FILE" ]; then
    SILENCE_UNTIL=$(cat "$SILENCE_FILE" 2>/dev/null || true)
    NOW_EPOCH=$(date +%s)
    if [[ "$SILENCE_UNTIL" =~ ^[0-9]+$ ]] && [ "$NOW_EPOCH" -lt "$SILENCE_UNTIL" ]; then
        REMAINING=$(( (SILENCE_UNTIL - NOW_EPOCH) / 60 ))
        printf '[%s] SILENCED: ещё %s мин\n' \
            "$(date -u +'%Y-%m-%d %H:%M UTC')" "$REMAINING" >> "$LOG_FILE"
        exit 0
    else
        rm -f "$SILENCE_FILE"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════
# Авто-фиксы
# ═══════════════════════════════════════════════════════════════════════════

DID_SOMETHING=false

# ── 1. Swap occupancy: только диагностика, без destructive remediation ────
# Высокий SwapUsed может быть остатком короткого пика и сам по себе не
# доказывает active pressure. Watchdog проверяет MemAvailable + activity/PSI.
SWAP_PCT=$(free | awk 'NR==3{if($2>0) printf "%.0f", $3/$2*100; else print "0"}' || true)
if [[ "$SWAP_PCT" =~ ^[0-9]+$ ]] && [ "$SWAP_PCT" -gt 50 ]; then
    printf '[%s] Swap %s%% — occupancy only; watchdog owns pressure alerting\n' \
        "$(date -u +'%Y-%m-%d %H:%M UTC')" "$SWAP_PCT" >> "$LOG_FILE"
fi

# ── 2. Диск > 85% → очистка ──────────────────────────────────────────────
DISK_PCT=$(df / | awk 'NR==2{print $5}' | tr -d '%' || true)
if [[ "$DISK_PCT" =~ ^[0-9]+$ ]] && [ "$DISK_PCT" -gt 85 ]; then
    printf '[%s] Disk %s%% — cleaning\n' \
        "$(date -u +'%Y-%m-%d %H:%M UTC')" "$DISK_PCT" >> "$LOG_FILE"
    journalctl --vacuum-size=100M 2>/dev/null || true
    if command -v docker >/dev/null 2>&1; then
        docker system prune -f --filter "until=24h" 2>/dev/null || true
    fi
    find /home /var/log -type f -size +100M -mtime +7 2>/dev/null | head -10 > /tmp/large-files-hermes.txt || true
    NEW_PCT=$(df / | awk 'NR==2{print $5}' | tr -d '%' || true)
    REPORT="${REPORT:+$REPORT\\n}🧹 Очистка диска: было ${DISK_PCT}% → стало ${NEW_PCT:-unknown}%"
    DID_SOMETHING=true
fi

# ── 3. Crontab recovery ──────────────────────────────────────────────────
CRON_COUNT=$( (crontab -l 2>/dev/null || true) | grep -v "^#" | grep -v "^$" | wc -l )
CRON_BACKUP="$HERMES_DIR/backups/crontab-known-good.txt"
if [ "$CRON_COUNT" -lt 7 ] && [ -f "$CRON_BACKUP" ]; then
    printf '[%s] Crontab: %s задач (<7) — восстанавливаю из бэкапа\n' \
        "$(date -u +'%Y-%m-%d %H:%M UTC')" "$CRON_COUNT" >> "$LOG_FILE"
    crontab "$CRON_BACKUP" 2>/dev/null || true
    NEW_COUNT=$( (crontab -l 2>/dev/null || true) | grep -v "^#" | grep -v "^$" | wc -l )
    REPORT="${REPORT:+$REPORT\\n}📋 Crontab восстановлен: было ${CRON_COUNT} → стало ${NEW_COUNT} задач"
    DID_SOMETHING=true
fi

# ═══════════════════════════════════════════════════════════════════════════
# Circuit breaker: увеличиваем счётчик если что-то делали
# ═══════════════════════════════════════════════════════════════════════════

if $DID_SOMETHING; then
    NEW_COUNT=$((CURRENT_COUNT + 1))
    printf '%s\n%s\n' "$HOUR_KEY" "$NEW_COUNT" > "$CIRCUIT_FILE"
    printf '[%s] Circuit breaker: %s/3 за %s\n' \
        "$(date -u +'%Y-%m-%d %H:%M UTC')" "$NEW_COUNT" "$HOUR_KEY" >> "$LOG_FILE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Отправка отчёта
# ═══════════════════════════════════════════════════════════════════════════

if [ -n "$REPORT" ] && [ -n "${WATCHDOG_BOT_TOKEN:-}" ]; then
    ESCAPED=$(printf '%b' "$REPORT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$REPORT")
    printf 'url = %s\n' "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" | \
        curl -s -K - -m 15 -x "${TELEGRAM_PROXY:-http://127.0.0.1:8444}" -X POST \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\": \"@WATCHDOG_CHAT_ID@\", \"text\": ${ESCAPED}, \"disable_notification\": true}" \
        -o /dev/null 2>&1 || true
fi
