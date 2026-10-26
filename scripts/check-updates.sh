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
# B2 (DEBT-013): .env уже источён выше — применяем настроенный TELEGRAM_PROXY
# к отправке отчёта (RR0c-конвенция: source снимает кавычки сам).
TG_PROXY="${TELEGRAM_PROXY:-}"

send_tg() {
    local msg="$1"
    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        local escaped=$(echo "$msg" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"$msg\"")
        # Токен не в argv: URL уходит в curl через -K - (config на stdin)
        printf 'url = %s\n' "${TG_API}${BOT_TOKEN}/sendMessage" | \
            curl -s -K - -x "$TG_PROXY" -X POST \
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
    # Контракт A: CLI через адаптер (PM-установка v0.22.5 не гарантирует
    # in-checkout venv; резолв лаунчера — на каждый запуск).
    CURRENT_VERSION=$("$HOME/scripts/hermes-runtime.py" hermes --version 2>/dev/null || echo "неизвестно")
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
