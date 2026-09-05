#!/bin/bash
# ssl-expiry-check.sh — проверка expiry SSL-сертификатов для критичных доменов.
# Запуск: system cron, раз в день.
# Если до expiry меньше 14 дней — алерт.
set -u
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
H="$HOME/.hermes"
LOG="$H/logs/ssl-expiry.log"
STATE_FILE="$H/state/ssl-expiry-alerted.txt"  # файл есть = уже алертили

# Критичные домены: те, без которых Hermes не работает
DOMAINS=(
    "api.telegram.org:443"
    "api.groq.com:443"
    "opencode.ai:443"
    "api.deadmanssnitch.com:443"
    "github.com:443"
)

WARN_DAYS=14
CRIT_DAYS=7
problems=""

for domain in "${DOMAINS[@]}"; do
    # Получаем дату expiry через openssl
    expiry_date=$(echo | openssl s_client -servername "${domain%:*}" -connect "$domain" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    if [ -z "$expiry_date" ]; then
        problems="$problems\n⚠️ $domain: не удалось получить сертификат"
        continue
    fi
    
    # Конвертируем в timestamp
    expiry_ts=$(date -d "$expiry_date" +%s 2>/dev/null || echo 0)
    now=$(date +%s)
    days_left=$(( (expiry_ts - now) / 86400 ))
    
    if [ "$days_left" -lt 0 ]; then
        problems="$problems\n🔴 $domain: ПРОСРОЧЕН на $(( -days_left )) дн!"
    elif [ "$days_left" -lt "$CRIT_DAYS" ]; then
        problems="$problems\n🔴 $domain: истекает через $days_left дн (критично!)"
    elif [ "$days_left" -lt "$WARN_DAYS" ]; then
        problems="$problems\n🟡 $domain: истекает через $days_left дн"
    fi
done

# Отчёт
if [ -n "$problems" ]; then
    # Дедуп: не шлём повторный алерт, если уже алертили
    if [ -f "$STATE_FILE" ]; then
        echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Known issues (already alerted):$problems" >> "$LOG"
        exit 0
    fi
    touch "$STATE_FILE"
    source "$HOME/.hermes/.env" 2>/dev/null || true
    MSG="🔐 <b>SSL Certificate Expiry</b>
Обнаружены проблемы с сертификатами:$problems"
    MSG_ESC=$(echo "$MSG" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
    curl -s -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\": \"$WATCHDOG_CHAT_ID\", \"text\": $MSG_ESC, \"parse_mode\": \"HTML\", \"disable_notification\": false}" \
        -o /dev/null -x "${TELEGRAM_PROXY:-}" 2>/dev/null || true
else
    # Всё ок — сбрасываем флаг алерта
    rm -f "$STATE_FILE"
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] All certificates OK" >> "$LOG"
fi