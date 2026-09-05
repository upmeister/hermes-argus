#!/bin/bash
# ============================================================================
# Проверка обновлений системы и Hermes — еженедельный отчёт
# Запуск: раз в неделю через системный cron
# ============================================================================
set -euo pipefail

LOGFILE="@HERMES_DIR@/logs/update-check.log"

# ── Telegram ──────────────────────────────────────────────────────────────
set -a; source $HOME/.hermes/.env; set +a
BOT_TOKEN="${WATCHDOG_BOT_TOKEN:-}"
CHAT_ID="${WATCHDOG_CHAT_ID:-}"
TG_API="https://api.telegram.org/bot"

send_tg() {
    local msg="$1"
    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        local escaped=$(echo "$msg" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"$msg\"")
        curl -s -X POST "${TG_API}${BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\": \"$CHAT_ID\", \"text\": $escaped, \"parse_mode\": \"HTML\"}" -o /dev/null
    fi
}

{
    echo "=== $(date '+%Y-%m-%d %H:%M') ==="

    # ── Системные пакеты ──────────────────────────────────────────────────
    echo "📦 Системные пакеты (apt):"
    UPDATES=$(apt list --upgradable 2>/dev/null | grep -v "^Listing\|^$" | wc -l || echo "0")
    if [ "$UPDATES" -gt 0 ]; then
        echo "  Доступно обновлений: ${UPDATES}"
        # Показываем security-обновления отдельно
        SEC_UPDATES=$(apt list --upgradable 2>/dev/null | grep -i security | wc -l || echo "0")
        echo "  Из них security: ${SEC_UPDATES}"
    else
        echo "  Система актуальна"
    fi

    # ── Hermes ────────────────────────────────────────────────────────────
    echo "🐱 Hermes Agent:"
    CURRENT_VERSION=$(@HERMES_BIN@ --version 2>/dev/null || echo "неизвестно")
    echo "  Установлена: ${CURRENT_VERSION}"

    # Проверяем последний релиз на GitHub (без аутентификации — публичный API)
    LATEST_RELEASE=$(curl -s --max-time 10 "https://api.github.com/repos/NousResearch/hermes-agent/releases/latest" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('tag_name','unknown'))" 2>/dev/null || echo "unknown")
    echo "  Последний релиз: ${LATEST_RELEASE}"

    # ── Перезагрузка нужна? ──────────────────────────────────────────────
    if [ -f /var/run/reboot-required ]; then
        echo ""
        echo "⚠️ Требуется перезагрузка сервера (обновление ядра)"
    fi

    echo "───"

} >> "$LOGFILE" 2>&1

# ── Отправка в Telegram ──────────────────────────────────────────────────
REPORT=$(tail -20 "$LOGFILE" | grep -v "^$")
if [ -n "$REPORT" ]; then
    MSG="📋 <b>Еженедельный отчёт по обновлениям</b>

${REPORT}"
    send_tg "$MSG"
fi
