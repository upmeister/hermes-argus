#!/bin/bash
# ============================================================================
# Hermes Watchdog — мониторинг здоровья сервера и алерты в Telegram
# Запуск: каждые 5 минут через системный cron
# v2: фикс HTTP 000000, добавлена проверка свежести health-state.json
# ============================================================================

set -euo pipefail

# ── Конфигурация ──────────────────────────────────────────────────────────
HERMES_HOST="@HERMES_HOST@"
HERMES_PORT="9119"
DISK_THRESHOLD=85        # % — алерт если занято больше
SWAP_THRESHOLD=50        # % — алерт если swap использован больше чем на
HEALTH_STATE_FILE="@HERMES_DIR@/logs/health-state.json"
HEALTH_STATE_MAX_AGE=7200  # секунд (2 часа) — алерт если deep health-check не обновлялся
LOG_FILE="@HERMES_DIR@/logs/watchdog.log"
MAX_LOG_SIZE=$((500 * 1024))  # 500 KB — ротация лога

# ── Telegram (используем существующего бота Hermes) ───────────────────────
# Токен и chat_id читаем из .env (source'им ниже)
TELEGRAM_API="https://api.telegram.org/bot"

# ── Подгрузка .env ────────────────────────────────────────────────────────
set -a
source $HOME/.hermes/.env
set +a

BOT_TOKEN="${WATCHDOG_BOT_TOKEN:-}"
CHAT_ID="${WATCHDOG_CHAT_ID:-}"

# Если нет токена или chat_id — пишем только в лог
TG_ENABLED=false
if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
    TG_ENABLED=true
fi

# ── Логирование (должно быть ДО любого вызова) ────────────────────────────
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# ── Ротация лога ──────────────────────────────────────────────────────────
if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$MAX_LOG_SIZE" ]; then
    mv "$LOG_FILE" "${LOG_FILE}.old"
fi

# Проверка режима тишины (silence) — после определения log(), иначе set -e валит скрипт
SILENCE_FILE="$HOME/.hermes/logs/auto-remediate-state/silence-until.txt"
if [ -f "$SILENCE_FILE" ]; then
    SILENCE_UNTIL=$(cat "$SILENCE_FILE" 2>/dev/null || true)
    NOW_EPOCH=$(date +%s)
    if [ -n "$SILENCE_UNTIL" ] && [ "$NOW_EPOCH" -lt "$SILENCE_UNTIL" ] 2>/dev/null; then
        REMAINING=$(( (SILENCE_UNTIL - NOW_EPOCH) / 60 ))
        log "🔕 Режим тишины: ещё ${REMAINING} мин — пропускаю watchdog"
        exit 0
    else
        rm -f "$SILENCE_FILE"
    fi
fi

# ── Функция отправки в Telegram ───────────────────────────────────────────
# $1: текст сообщения
# $2: опции (необязательно): "silent" — без звука, "pin" — закрепить, "keyboard" — кнопки действий
send_tg() {
    local msg="$1"
    local opts="${2:-}"
    if $TG_ENABLED; then
        # Через telegram-smart-proxy: прямой api.telegram.org мёртв при РКН-волнах,
        # а HTTPS_PROXY из .env (8445) умеет только opencode.ai
        local proxy="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
        local escaped
        escaped=$(echo "$msg" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"$msg\"")
        
        # Собираем JSON с опциями
        local json="{\"chat_id\": \"$CHAT_ID\", \"text\": $escaped, \"parse_mode\": \"HTML\""
        
        # Тихая отправка (без звука)
        if [[ "$opts" == *"silent"* ]]; then
            json="$json, \"disable_notification\": true"
        fi
        
        # Inline-кнопки действий (набор в синхроне с webhook.py alert_keyboard())
        if [[ "$opts" == *"keyboard"* ]]; then
            json="$json, \"reply_markup\": {\"inline_keyboard\": [[{\"text\": \"🔄 Restart Gateway\", \"callback_data\": \"restart_gw\"}, {\"text\": \"🔄 Restart Dashboard\", \"callback_data\": \"restart_dash\"}], [{\"text\": \"🛜 Сеть\", \"callback_data\": \"network\"}, {\"text\": \"ℹ️ Статус\", \"callback_data\": \"health\"}], [{\"text\": \"📋 Логи\", \"callback_data\": \"show_logs\"}, {\"text\": \"👀 Игнорировать 1ч\", \"callback_data\": \"silence_1h\"}]]}"
        fi
        
        json="$json}"
        
        local response
        response=$(curl -s -m 15 -x "$proxy" -X POST "${TELEGRAM_API}${BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "$json" 2>&1)
        
        # Закрепление сообщения (если запрошен pin и отправка успешна)
        if [[ "$opts" == *"pin"* ]]; then
            local msg_id
            msg_id=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('message_id',''))" 2>/dev/null)
            if [ -n "$msg_id" ]; then
                curl -s -m 15 -x "$proxy" -X POST "${TELEGRAM_API}${BOT_TOKEN}/pinChatMessage" \
                    -H "Content-Type: application/json" \
                    -d "{\"chat_id\": \"$CHAT_ID\", \"message_id\": $msg_id, \"disable_notification\": true}" \
                    -o /dev/null 2>&1
            fi
        fi
        # Статус доставки в лог (не доверяем факту вызова curl)
        local tg_status
        tg_status=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('ok') else d.get('error_code','ERR'))" 2>/dev/null || echo "ERR")
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] TG[$tg_status]: $msg" >> "$LOG_FILE"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
# ПРОВЕРКИ
# ═══════════════════════════════════════════════════════════════════════════

OKS=()

# ── Stateful алерты: дедупликация + гистерезис (17.08.2026) ───────────────
# 1 провал ≠ мёртвый сервис (CONVENTIONS.md; уроки 16.08/17.08 — ложные
# «бот не отвечает» при РКН-волне). Сетевой класс (000/5xx/«не отвечает»)
# алертит после 2 подряд чеков, определённый (401/403/404, crontab) — сразу.
# Известный инцидент (ключ уже алармили) молчит до восстановления;
# восстановление шлёт 1 сообщение. State — watchdog-alerts.state.
ALERT_STATE_FILE="$HOME/.hermes/logs/auto-remediate-state/watchdog-alerts.state"
declare -A ST_ALERTED ST_STREAK ST_LABEL SEEN
if [ -f "$ALERT_STATE_FILE" ]; then
    while IFS=$'\t' read -r k alerted streak label; do
        [ -n "$k" ] || continue
        ST_ALERTED["$k"]="$alerted"; ST_STREAK["$k"]="$streak"; ST_LABEL["$k"]="$label"
    done < "$ALERT_STATE_FILE"
fi

# ── Suppression от L3 (подтверждённый внешний/известный инцидент) ───────
# L3-агент health-check пишет external-suppress.state (TSV: key|expiry|reason);
# watchdog молчит по этим ключам до expiry. Только сетевые классы — auth/cfg
# suppression получать не должны (реальная наша проблема не должна гаснуть).
SUPPRESS_FILE="$HOME/.hermes/logs/auto-remediate-state/external-suppress.state"
declare -A ST_SUPPRESS
if [ -f "$SUPPRESS_FILE" ]; then
    SUPP_NOW=$(date +%s)
    while IFS=$'\t' read -r skey sexp sreason; do
        [ -n "$skey" ] || continue
        [ "$sexp" -gt "$SUPP_NOW" ] 2>/dev/null && ST_SUPPRESS["$skey"]="$sreason"
    done < "$SUPPRESS_FILE"
fi

NEW_PROBLEMS=()

# track_problem <key> <label> <msg> <порог> — ключ в state с alerted=1 → тишина;
# иначе streak+1, при достижении порога → NEW_PROBLEMS + alerted=1.
track_problem() {
    local key="$1" label="$2" msg="$3" thr="${4:-1}"
    SEEN["$key"]=1
    ST_LABEL["$key"]="$label"
    if [ -n "${ST_SUPPRESS[$key]:-}" ]; then
        log "🔕 ${label}: suppressed L3 (${ST_SUPPRESS[$key]})"
        return 0
    fi
    [ "${ST_ALERTED[$key]:-0}" = "1" ] && return 0
    local streak=$(( ${ST_STREAK[$key]:-0} + 1 ))
    ST_STREAK["$key"]="$streak"
    if [ "$streak" -ge "$thr" ]; then
        NEW_PROBLEMS+=("$msg")
        ST_ALERTED["$key"]=1
    fi
}

# ── 1. Проверка порта Hermes dashboard ───────────────────────────────────
log "🔍 Проверка порта ${HERMES_HOST}:${HERMES_PORT}..."
# curl печатает "000" через -w при ошибке (timeout/dns/connect)
# Оборачиваем, чтобы не дублировать и не портить %{http_code} в дубль
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 8 "http://${HERMES_HOST}:${HERMES_PORT}/" 2>/dev/null)

# Пустой ответ или "000" = порт не отвечает. *000* — ловит и "000" и "000000"
# (защита от повторного `|| echo 000`, см. скилл hermes-server-maintenance)
if [ -z "$HTTP_CODE" ] || [[ "$HTTP_CODE" == *000* ]]; then
    track_problem "port_9119" "Hermes dashboard" "❌ <b>Hermes dashboard не отвечает!</b> Порт ${HERMES_PORT} недоступен (connection refused / timeout)" 1
    log "❌ Порт ${HERMES_PORT} не отвечает (HTTP ${HTTP_CODE:-пустой ответ})"
else
    OKS+=("✅ Hermes dashboard: HTTP ${HTTP_CODE}")
    log "✅ Порт ${HERMES_PORT}: HTTP ${HTTP_CODE}"
fi

# ── 2. Проверка процесса gateway ─────────────────────────────────────────
log "🔍 Проверка процесса gateway..."
GATEWAY_PIDS=$(pgrep -f "hermes_cli.main gateway run" 2>/dev/null || true)

if [ -z "$GATEWAY_PIDS" ]; then
    track_problem "gateway_proc" "Gateway" "❌ <b>Gateway процесс НЕ НАЙДЕН!</b> Hermes gateway не запущен" 1
    log "❌ Gateway процесс не найден"
else
    PID_COUNT=$(echo "$GATEWAY_PIDS" | wc -l)
    OKS+=("✅ Gateway: ${PID_COUNT} процесс(ов)")
    log "✅ Gateway процесс(ов): ${PID_COUNT}"
fi

# ── 3. Проверка диска ────────────────────────────────────────────────────
log "🔍 Проверка диска..."
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt "$DISK_THRESHOLD" ]; then
    DISK_INFO=$(df -h / | awk 'NR==2 {print $3 " из " $2}')
    track_problem "disk_high" "Диск" "⚠️ <b>Диск заполнен на ${DISK_USAGE}%!</b> (${DISK_INFO})" 1
    log "⚠️ Диск: ${DISK_USAGE}%"
else
    OKS+=("💾 Диск: ${DISK_USAGE}%")
    log "💾 Диск: ${DISK_USAGE}%"
fi

# ── 4. Проверка памяти и swap ────────────────────────────────────────────
log "🔍 Проверка памяти..."
MEM_INFO=$(free -h | awk 'NR==2 {print $3 "/" $2}')
SWAP_TOTAL=$(free | awk 'NR==3 {print $2}')
SWAP_USED=$(free | awk 'NR==3 {print $3}')

if [ "$SWAP_TOTAL" -gt 0 ]; then
    SWAP_PCT=$((SWAP_USED * 100 / SWAP_TOTAL))
    if [ "$SWAP_PCT" -gt "$SWAP_THRESHOLD" ]; then
        track_problem "swap_high" "Swap" "⚠️ <b>Swap использован на ${SWAP_PCT}%!</b> RAM: ${MEM_INFO}" 1
        log "⚠️ Swap: ${SWAP_PCT}%"
    else
        OKS+=("🧠 RAM: ${MEM_INFO}, swap: ${SWAP_PCT}%")
        log "🧠 Swap: ${SWAP_PCT}%"
    fi
else
    OKS+=("🧠 RAM: ${MEM_INFO}, swap: нет")
    log "🧠 Swap отсутствует"
fi

# ── 5. Проверка свежести health-state.json (deep health-check жив?) ──────
log "🔍 Проверка свежести health-state.json..."
if [ -f "$HEALTH_STATE_FILE" ]; then
    # Извлекаем last_check timestamp из JSON
    LAST_CHECK=$(python3 -c "
import json, sys
try:
    with open('$HEALTH_STATE_FILE') as f:
        d = json.load(f)
    print(d.get('last_check', ''))
except:
    print('')
" 2>/dev/null)

    if [ -n "$LAST_CHECK" ]; then
        # Парсим ISO timestamp и сравниваем с текущим временем
        STATE_AGE=$(python3 -c "
from datetime import datetime, timezone
try:
    ts = '$LAST_CHECK'.replace('Z', '+00:00')
    dt = datetime.fromisoformat(ts)
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    print(int(age))
except:
    print(-1)
" 2>/dev/null)

        if [ "$STATE_AGE" -ge 0 ] && [ "$STATE_AGE" -gt "$HEALTH_STATE_MAX_AGE" ]; then
            AGE_HOURS=$((STATE_AGE / 3600))
            track_problem "health_state_stale" "Health-check L3" "⚠️ <b>Deep health-check не обновлялся ${AGE_HOURS}ч!</b> Cron-задача сломалась (config drift?)" 1
            log "⚠️ health-state.json stale: ${AGE_HOURS}ч"
        elif [ "$STATE_AGE" -ge 0 ]; then
            AGE_H=$((STATE_AGE / 3600))
            OKS+=("🔬 Health-check свежий (${AGE_H}ч назад)")
            log "✅ health-state.json свежий: ${STATE_AGE}с назад"
        else
            log "⚠️ Не удалось распарсить timestamp из health-state.json"
        fi
    else
        log "⚠️ last_check пустой в health-state.json"
    fi
else
    track_problem "health_state_missing" "health-state.json" "⚠️ <b>health-state.json не найден!</b> Deep health-check никогда не запускался" 1
    log "⚠️ health-state.json отсутствует"
fi

# ═══════════════════════════════════════════════════════════════════════════
# 6. Проверка API-ключей и интеграций (каждый watchdog-цикл)
# ═══════════════════════════════════════════════════════════════════════════

log "🔍 Проверка API-ключей и интеграций..."
# check-integrations может вернуть exit 1 (найдены проблемы) — НЕ должен убивать watchdog
set +e
INTEGRATION_OUTPUT=$(bash ~/scripts/check-integrations.sh 2>&1)
INTEGRATION_EXIT=$?
set -e

if [ $INTEGRATION_EXIT -ne 0 ]; then
    # Каждая строка = отдельный инцидент: ключ = label + класс
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        [[ "$line" == "=== INTEGRATION HEALTH PROBLEMS ===" ]] && continue
        label="${line%%:*}"
        [ -n "$label" ] || label="$line"
        case "$line" in
            *"невалиден/отозван"*)                    cls="auth" ;;
            *"HTTP 401"*|*"HTTP 403"*|*"HTTP 404"*)   cls="auth" ;;
            *"Crontab"*)                              cls="cfg" ;;
            *"auth не проходит"*)                     cls="cfg" ;;
            *)                                        cls="net" ;;
        esac
        thr=1; [ "$cls" = "net" ] && thr=2
        track_problem "int:${label}:${cls}" "$label" "$line" "$thr"
    done <<< "$INTEGRATION_OUTPUT"
    log "❌ Интеграции: найдены проблемы"
else
    OKS+=("🔌 Интеграции: OK")
    log "✅ Интеграции: OK"
fi

# ═══════════════════════════════════════════════════════════════════════════
# ОТПРАВКА АЛЕРТОВ
# ═══════════════════════════════════════════════════════════════════════════

# ── Восстановленные (были alerted, в этом прогоне не обнаружены) ────────
RESOLVED=()
for key in "${!ST_ALERTED[@]}"; do
    if [ "${ST_ALERTED[$key]}" = "1" ] && [ "${SEEN[$key]:-0}" != "1" ]; then
        RESOLVED+=("${ST_LABEL[$key]:-$key}")
    fi
done

# ── Сохранение state (только текущие проблемы) ───────────────────────────
: > "$ALERT_STATE_FILE.tmp"
for key in "${!SEEN[@]}"; do
    printf '%s\t%s\t%s\t%s\n' "$key" "${ST_ALERTED[$key]:-0}" "${ST_STREAK[$key]:-0}" "${ST_LABEL[$key]:-$key}" >> "$ALERT_STATE_FILE.tmp"
done
mv "$ALERT_STATE_FILE.tmp" "$ALERT_STATE_FILE"

# ── Отправка ─────────────────────────────────────────────────────────────
if [ ${#NEW_PROBLEMS[@]} -gt 0 ]; then
    ALERT_MSG="🛡️ <b>WATCHDOG АЛЕРТ</b> — $(date '+%H:%M')
"
    for p in "${NEW_PROBLEMS[@]}"; do
        ALERT_MSG+="$p
"
    done
    if [ ${#RESOLVED[@]} -gt 0 ]; then
        ALERT_MSG+="
✅ Восстановлено:
"
        for r in "${RESOLVED[@]}"; do
            ALERT_MSG+="• $r
"
        done
    fi
    if [ ${#OKS[@]} -gt 0 ]; then
        ALERT_MSG+="
В порядке:
"
        for o in "${OKS[@]}"; do
            ALERT_MSG+="$o
"
        done
    fi
    send_tg "$ALERT_MSG" "pin keyboard"
    log "📤 Отправлен алерт (${#NEW_PROBLEMS[@]} новых) + пин"
elif [ ${#RESOLVED[@]} -gt 0 ]; then
    R_MSG="✅ <b>Восстановлено</b> — $(date '+%H:%M')
"
    for r in "${RESOLVED[@]}"; do
        R_MSG+="• $r
"
    done
    send_tg "$R_MSG" "keyboard"
    log "📤 Отправлено восстановление (${#RESOLVED[@]}): ${RESOLVED[*]}"
else
    # Всё хорошо — тишина (heartbeat-сообщения убраны: шум при здоровой системе,
    # мониторинг здоровья — health-check L3 + heartbeat GitHub L4)
    log "✅ Все проверки пройдены — алерт не требуется"
fi

log "─── Конец проверки ───"