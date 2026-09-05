#!/bin/bash
# Auto-remediation: безопасные авто-фиксы для типовых проблем
# Запуск: каждые 10 минут через системный cron
# Принцип: только операции без риска потери данных

LOG_FILE="$HOME/.hermes/logs/auto-remediate.log"
STATE_DIR="$HOME/.hermes/logs/auto-remediate-state"
REPORT=""

mkdir -p "$STATE_DIR"

# ═══════════════════════════════════════════════════════════════════════════
# Circuit breaker: если авто-фикс срабатывал >3 раз за час — стоп
# ═══════════════════════════════════════════════════════════════════════════

CIRCUIT_FILE="$STATE_DIR/circuit-breaker.txt"
HOUR_KEY=$(date -u +"%Y-%m-%dT%H")

# Читаем счётчик за текущий час
CURRENT_COUNT=0
if [ -f "$CIRCUIT_FILE" ]; then
    STORED_KEY=$(head -1 "$CIRCUIT_FILE" 2>/dev/null)
    STORED_COUNT=$(tail -1 "$CIRCUIT_FILE" 2>/dev/null)
    if [ "$STORED_KEY" = "$HOUR_KEY" ]; then
        CURRENT_COUNT=$STORED_COUNT
    fi
fi

if [ "$CURRENT_COUNT" -ge 3 ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M UTC')] CIRCUIT BREAKER: $CURRENT_COUNT авто-фиксов за час — стоп" >> "$LOG_FILE"
    source "$HOME/.hermes/.env" 2>/dev/null
    if [ -n "$WATCHDOG_BOT_TOKEN" ]; then
        curl -s -x "${TELEGRAM_PROXY:-http://127.0.0.1:8444}" -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\":\"@WATCHDOG_CHAT_ID@\",\"text\":\"🚨 Circuit Breaker: ${CURRENT_COUNT} авто-фиксов за час. Требуется вмешательство человека.\"}" \
            -o /dev/null 2>&1
    fi
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════
# Проверка режима тишины (silence)
# ═══════════════════════════════════════════════════════════════════════════

SILENCE_FILE="$STATE_DIR/silence-until.txt"
if [ -f "$SILENCE_FILE" ]; then
    SILENCE_UNTIL=$(cat "$SILENCE_FILE" 2>/dev/null)
    NOW_EPOCH=$(date +%s)
    if [ "$NOW_EPOCH" -lt "$SILENCE_UNTIL" ] 2>/dev/null; then
        REMAINING=$(( (SILENCE_UNTIL - NOW_EPOCH) / 60 ))
        echo "[$(date -u +'%Y-%m-%d %H:%M UTC')] SILENCED: ещё ${REMAINING} мин" >> "$LOG_FILE"
        exit 0
    else
        rm -f "$SILENCE_FILE"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════
# Авто-фиксы
# ═══════════════════════════════════════════════════════════════════════════

DID_SOMETHING=false

# ── 1. Swap > 50% → сброс page cache ─────────────────────────────────
SWAP_PCT=$(free | awk 'NR==3{if($2>0) printf "%.0f", $3/$2*100; else print "0"}')
if [ "$SWAP_PCT" -gt 50 ] 2>/dev/null; then
    echo "[$(date -u +'%Y-%m-%d %H:%M UTC')] Swap ${SWAP_PCT}% — dropping page cache" >> "$LOG_FILE"
    sync
    echo 1 | sudo tee /proc/sys/vm/drop_caches > /dev/null 2>&1
    REPORT="🧹 Сброшен page cache (swap был ${SWAP_PCT}%)"
    DID_SOMETHING=true
fi

# ── 2. Диск > 85% → очистка ─────────────────────────────────────────
DISK_PCT=$(df / | awk 'NR==2{print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 85 ] 2>/dev/null; then
    echo "[$(date -u +'%Y-%m-%d %H:%M UTC')] Disk ${DISK_PCT}% — cleaning" >> "$LOG_FILE"
    journalctl --vacuum-size=100M 2>/dev/null
    if command -v docker &>/dev/null; then
        docker system prune -f --filter "until=24h" 2>/dev/null
    fi
    find /home /var/log -type f -size +100M -mtime +7 2>/dev/null | head -10 > /tmp/large-files-hermes.txt
    NEW_PCT=$(df / | awk 'NR==2{print $5}' | tr -d '%')
    REPORT="${REPORT:+$REPORT\n}🧹 Очистка диска: было ${DISK_PCT}% → стало ${NEW_PCT}%"
    DID_SOMETHING=true
fi

# ── 3. Crontab recovery ──────────────────────────────────────────────
CRON_COUNT=$(crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | wc -l)
CRON_BACKUP="$HOME/.hermes/backups/crontab-known-good.txt"
if [ "$CRON_COUNT" -lt 7 ] && [ -f "$CRON_BACKUP" ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M UTC')] Crontab: $CRON_COUNT задач (<7) — восстанавливаю из бэкапа" >> "$LOG_FILE"
    crontab "$CRON_BACKUP" 2>/dev/null
    NEW_COUNT=$(crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | wc -l)
    REPORT="${REPORT:+$REPORT\n}📋 Crontab восстановлен: было $CRON_COUNT → стало $NEW_COUNT задач"
    DID_SOMETHING=true
fi

# ═══════════════════════════════════════════════════════════════════════════
# Circuit breaker: увеличиваем счётчик если что-то делали
# ═══════════════════════════════════════════════════════════════════════════

if $DID_SOMETHING; then
    NEW_COUNT=$((CURRENT_COUNT + 1))
    echo "$HOUR_KEY" > "$CIRCUIT_FILE"
    echo "$NEW_COUNT" >> "$CIRCUIT_FILE"
    echo "[$(date -u +'%Y-%m-%d %H:%M UTC')] Circuit breaker: $NEW_COUNT/3 за $HOUR_KEY" >> "$LOG_FILE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Отправка отчёта
# ═══════════════════════════════════════════════════════════════════════════

if [ -n "$REPORT" ]; then
    source "$HOME/.hermes/.env" 2>/dev/null
    if [ -n "$WATCHDOG_BOT_TOKEN" ]; then
        ESCAPED=$(echo -e "$REPORT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null)
        curl -s -x "${TELEGRAM_PROXY:-http://127.0.0.1:8444}" -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\": \"@WATCHDOG_CHAT_ID@\", \"text\": ${ESCAPED}, \"disable_notification\": true}" \
            -o /dev/null 2>&1
    fi
fi
