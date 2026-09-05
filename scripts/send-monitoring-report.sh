#!/bin/bash
# Отправка health-check отчёта в мониторинг-бот (с опциональными кнопками)
# Использование:
#   send-monitoring-report.sh "текст" [silent] [keyboard]
#   keyboard — inline-кнопки действий (набор в синхроне с webhook.py alert_keyboard())

source ~/.hermes/.env
MSG="$1"
SILENT="${2:-}"
KEYBOARD="${3:-}"

DISABLE_NOTIF=""
if [ "$SILENT" = "silent" ]; then
    DISABLE_NOTIF=', "disable_notification": true'
fi

# Экранирование текста для JSON
ESCAPED=$(echo "$MSG" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"$MSG\"")

# Inline-клавиатура (по запросу)
REPLY_MARKUP=""
if [ "$KEYBOARD" = "keyboard" ]; then
    REPLY_MARKUP=', "reply_markup": {"inline_keyboard": [[{"text": "🔄 Restart Gateway", "callback_data": "restart_gw"}, {"text": "🔄 Restart Dashboard", "callback_data": "restart_dash"}], [{"text": "🛜 Сеть", "callback_data": "network"}, {"text": "ℹ️ Статус", "callback_data": "health"}], [{"text": "📋 Логи", "callback_data": "show_logs"}, {"text": "👀 Игнорировать 1ч", "callback_data": "silence_1h"}]]}'
fi

# Используем smart-proxy для доступа к Telegram API (прямые IP заблокированы РКН)
curl -s --max-time 30 --proxy http://127.0.0.1:8444 \
    -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\": \"@WATCHDOG_CHAT_ID@\", \"text\": ${ESCAPED}${DISABLE_NOTIF}${REPLY_MARKUP}}" \
    -o /dev/null -w "HTTP %{http_code}"
echo
