#!/bin/bash
# ============================================================================
# Hermes Watchdog — мониторинг здоровья сервера и алерты в Telegram
# Запуск: каждые 5 минут через системный cron
# v3: pressure-aware swap, stateful recovery hysteresis, non-overlapping runs
# ============================================================================

set -euo pipefail

# ── Конфигурация ──────────────────────────────────────────────────────────
HERMES_HOST="@HERMES_HOST@"
HERMES_PORT="@HERMES_PORT@"
DISK_THRESHOLD=85        # % — алерт если занято больше
SWAP_THRESHOLD=50        # % — только диагностический порог occupancy
MEM_AVAILABLE_THRESHOLD=15  # % — low available memory threshold
SWAP_PSI_THRESHOLD=5.0      # memory PSI some avg10, percent
SWAP_ALERT_STREAK=2
SWAP_RECOVERY_STREAK=2
HERMES_DIR="@HERMES_DIR@"
HOME_DIR="@HOME_DIR@"
HEALTH_STATE_FILE="@HERMES_DIR@/logs/health-state.json"
HEALTH_STATE_MAX_AGE=7200  # секунд (2 часа) — алерт если deep health-check не обновлялся
LOG_FILE="@HERMES_DIR@/logs/watchdog.log"
MAX_LOG_SIZE=$((500 * 1024))  # 500 KB — ротация лога
STATE_DIR="$HERMES_DIR/logs/auto-remediate-state"
SWAP_SAMPLE_FILE="$STATE_DIR/swap-metrics.state"
PROC_ROOT="${PROC_ROOT:-/proc}"

mkdir -p "$HERMES_DIR/logs" "$STATE_DIR"
LOCK_FILE="$STATE_DIR/hermes-watchdog.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    printf '[%s] watchdog уже выполняется — пропускаю параллельный запуск\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
    exit 0
fi

# ── Telegram (используем существующего бота Hermes) ───────────────────────
# Токен и chat_id читаем из .env (source'им ниже)
TELEGRAM_API="https://api.telegram.org/bot"

# ── Подгрузка .env ────────────────────────────────────────────────────────
if [ -f "$HERMES_DIR/.env" ]; then
    set -a
    source "$HERMES_DIR/.env"
    set +a
fi

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
SILENCE_FILE="$STATE_DIR/silence-until.txt"
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
        response=$(printf 'url = %s\n' "${TELEGRAM_API}${BOT_TOKEN}/sendMessage" | \
            curl -s -m 15 -x "$proxy" -K - -X POST \
            -H "Content-Type: application/json" \
            -d "$json" 2>&1 || true)
        
        # Закрепление сообщения (если запрошен pin и отправка успешна)
        if [[ "$opts" == *"pin"* ]]; then
            local msg_id
            msg_id=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('message_id',''))" 2>/dev/null)
            if [ -n "$msg_id" ]; then
                printf 'url = %s\n' "${TELEGRAM_API}${BOT_TOKEN}/pinChatMessage" | \
                    curl -s -m 15 -x "$proxy" -K - -X POST \
                    -H "Content-Type: application/json" \
                    -d "{\"chat_id\": \"$CHAT_ID\", \"message_id\": $msg_id, \"disable_notification\": true}" \
                    -o /dev/null 2>&1 || true
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
ALERT_STATE_FILE="$STATE_DIR/watchdog-alerts.state"
declare -A ST_ALERTED ST_STREAK ST_CLEAR ST_LABEL SEEN PERSIST
if [ -f "$ALERT_STATE_FILE" ]; then
    while IFS=$'\t' read -r k alerted streak clear_streak label; do
        [ -n "$k" ] || continue
        # Backward-compatible read of the old four-column state format.
        if [ -z "$label" ] && [[ ! "$clear_streak" =~ ^[0-9]+$ ]]; then
            label="$clear_streak"
            clear_streak=0
        fi
        [[ "$streak" =~ ^[0-9]+$ ]] || streak=0
        [[ "$clear_streak" =~ ^[0-9]+$ ]] || clear_streak=0
        ST_ALERTED["$k"]="$alerted"; ST_STREAK["$k"]="$streak"; ST_LABEL["$k"]="$label"
        ST_CLEAR["$k"]="$clear_streak"
    done < "$ALERT_STATE_FILE"
fi

# ── Suppression от L3 (подтверждённый внешний/известный инцидент) ───────
# L3-агент health-check пишет external-suppress.state (TSV: key|expiry|reason);
# watchdog молчит по этим ключам до expiry. Только сетевые классы — auth/cfg
# suppression получать не должны (реальная наша проблема не должна гаснуть).
SUPPRESS_FILE="$STATE_DIR/external-suppress.state"
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
# A currently observed problem resets its clean/recovery streak.
track_problem() {
    local key="$1" label="$2" msg="$3" thr="${4:-1}"
    SEEN["$key"]=1
    ST_LABEL["$key"]="$label"
    ST_CLEAR["$key"]=0
    if [[ "$key" == int:*:net && -n "${ST_SUPPRESS[$key]:-}" ]]; then
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
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 8 "http://${HERMES_HOST}:${HERMES_PORT}/" 2>/dev/null || true)

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
MEM_INFO=$(free -h | awk 'NR==2 {print $3 "/" $2}' || true)
MEM_INFO="${MEM_INFO:-unknown}"

read_meminfo_value() {
    awk -v key="$1" '$1 == key ":" {print $2; exit}' "$PROC_ROOT/meminfo" 2>/dev/null || true
}

MEM_TOTAL_KB=$(read_meminfo_value MemTotal)
MEM_AVAILABLE_KB=$(read_meminfo_value MemAvailable)
SWAP_TOTAL_KB=$(read_meminfo_value SwapTotal)
SWAP_FREE_KB=$(read_meminfo_value SwapFree)
for value_name in MEM_TOTAL_KB MEM_AVAILABLE_KB SWAP_TOTAL_KB SWAP_FREE_KB; do
    value="${!value_name:-}"
    [[ "$value" =~ ^[0-9]+$ ]] || printf -v "$value_name" '%s' 0
done

SWAP_USED_KB=0
SWAP_PCT=0
if [ "$SWAP_TOTAL_KB" -gt 0 ] && [ "$SWAP_FREE_KB" -le "$SWAP_TOTAL_KB" ]; then
    SWAP_USED_KB=$((SWAP_TOTAL_KB - SWAP_FREE_KB))
    SWAP_PCT=$((SWAP_USED_KB * 100 / SWAP_TOTAL_KB))
fi

MEM_AVAILABLE_PCT=0
if [ "$MEM_TOTAL_KB" -gt 0 ] && [ "$MEM_AVAILABLE_KB" -le "$MEM_TOTAL_KB" ]; then
    MEM_AVAILABLE_PCT=$((MEM_AVAILABLE_KB * 100 / MEM_TOTAL_KB))
fi

CURRENT_SWAP_IN=$(awk '$1 == "pswpin" {print $2; exit}' "$PROC_ROOT/vmstat" 2>/dev/null || true)
CURRENT_SWAP_OUT=$(awk '$1 == "pswpout" {print $2; exit}' "$PROC_ROOT/vmstat" 2>/dev/null || true)
[[ "${CURRENT_SWAP_IN:-}" =~ ^[0-9]+$ ]] || CURRENT_SWAP_IN=0
[[ "${CURRENT_SWAP_OUT:-}" =~ ^[0-9]+$ ]] || CURRENT_SWAP_OUT=0

PREV_SWAP_IN=0
PREV_SWAP_OUT=0
HAVE_PREV_SAMPLE=false
if [ -f "$SWAP_SAMPLE_FILE" ]; then
    read -r _ PREV_SWAP_IN PREV_SWAP_OUT < "$SWAP_SAMPLE_FILE" || true
    if [[ "${PREV_SWAP_IN:-}" =~ ^[0-9]+$ ]] && [[ "${PREV_SWAP_OUT:-}" =~ ^[0-9]+$ ]]; then
        HAVE_PREV_SAMPLE=true
    fi
fi

SWAP_IN_DELTA=0
SWAP_OUT_DELTA=0
if $HAVE_PREV_SAMPLE; then
    [ "$CURRENT_SWAP_IN" -ge "$PREV_SWAP_IN" ] && SWAP_IN_DELTA=$((CURRENT_SWAP_IN - PREV_SWAP_IN))
    [ "$CURRENT_SWAP_OUT" -ge "$PREV_SWAP_OUT" ] && SWAP_OUT_DELTA=$((CURRENT_SWAP_OUT - PREV_SWAP_OUT))
fi
printf '%s\t%s\t%s\n' "$(date +%s)" "$CURRENT_SWAP_IN" "$CURRENT_SWAP_OUT" > "$SWAP_SAMPLE_FILE.tmp"
mv "$SWAP_SAMPLE_FILE.tmp" "$SWAP_SAMPLE_FILE"

PSI_SOME_AVG10=0
if [ -r "$PROC_ROOT/pressure/memory" ]; then
    PSI_SOME_AVG10=$(awk '/^some / {for (i = 1; i <= NF; i++) if ($i ~ /^avg10=/) {split($i, a, "="); print a[2]; exit}}' \
        "$PROC_ROOT/pressure/memory" 2>/dev/null || true)
fi
PSI_SOME_AVG10="${PSI_SOME_AVG10:-0}"

SWAP_ACTIVITY=false
if [ "$SWAP_IN_DELTA" -gt 0 ] || [ "$SWAP_OUT_DELTA" -gt 0 ]; then
    SWAP_ACTIVITY=true
fi
PSI_PRESSURE=false
if awk -v value="$PSI_SOME_AVG10" -v threshold="$SWAP_PSI_THRESHOLD" 'BEGIN {exit !(value >= threshold)}'; then
    PSI_PRESSURE=true
fi

PRESSURE_ACTIVE=false
if [ "$MEM_TOTAL_KB" -gt 0 ] && [ "$MEM_AVAILABLE_KB" -lt "$MEM_TOTAL_KB" ] \
    && [ "$MEM_AVAILABLE_PCT" -lt "$MEM_AVAILABLE_THRESHOLD" ] \
    && { $SWAP_ACTIVITY || $PSI_PRESSURE; }; then
    PRESSURE_ACTIVE=true
fi

if [ "$SWAP_TOTAL_KB" -gt 0 ]; then
    if $PRESSURE_ACTIVE; then
        track_problem "swap_high" "Swap pressure" \
            "⚠️ <b>Активное давление памяти</b>: swap ${SWAP_PCT}%, MemAvailable ${MEM_AVAILABLE_PCT}%, swap Δin/out ${SWAP_IN_DELTA}/${SWAP_OUT_DELTA} pages, PSI some10 ${PSI_SOME_AVG10}%" \
            "$SWAP_ALERT_STREAK"
        log "⚠️ Swap pressure: ${SWAP_PCT}% used, MemAvailable ${MEM_AVAILABLE_PCT}%, swap Δin/out ${SWAP_IN_DELTA}/${SWAP_OUT_DELTA}, PSI ${PSI_SOME_AVG10}%"
    elif [ "$SWAP_PCT" -gt "$SWAP_THRESHOLD" ]; then
        OKS+=("🧠 RAM: ${MEM_INFO}, swap: ${SWAP_PCT}% (occupancy, pressure absent)")
        log "ℹ️ Swap occupancy: ${SWAP_PCT}% — active pressure absent"
    else
        OKS+=("🧠 RAM: ${MEM_INFO}, swap: ${SWAP_PCT}%")
        log "🧠 Swap: ${SWAP_PCT}%"
    fi
else
    OKS+=("🧠 RAM: ${MEM_INFO}, swap: нет")
    log "🧠 Swap отсутствует"
fi

# ── 5. Проверка свежести health-state.json (deep health-check жив?) ──────
if [ "@MODULE_ANALYZER@" = "ON" ]; then
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
            track_problem "health_state_unreadable" "health-state.json" \
                "⚠️ <b>health-state.json содержит некорректный timestamp</b>" 1
            log "⚠️ Не удалось распарсить timestamp из health-state.json"
        fi
    else
        track_problem "health_state_unreadable" "health-state.json" \
            "⚠️ <b>health-state.json не содержит last_check</b>" 1
        log "⚠️ last_check пустой в health-state.json"
    fi
else
    track_problem "health_state_missing" "health-state.json" "⚠️ <b>health-state.json не найден!</b> Deep health-check никогда не запускался" 1
    log "⚠️ health-state.json отсутствует"
fi
fi

# ═══════════════════════════════════════════════════════════════════════════
# 6. Проверка API-ключей и интеграций (каждый watchdog-цикл)
# ═══════════════════════════════════════════════════════════════════════════

if [ "@MODULE_INTEGRATIONS@" = "ON" ]; then
    log "🔍 Проверка API-ключей и интеграций..."
    INTEGRATION_CHECKER="$HERMES_DIR/scripts/health-check-integrations.sh"
    if [ ! -f "$INTEGRATION_CHECKER" ]; then
        track_problem "integration_check_missing" "Integration checker" \
            "⚠️ <b>health-check-integrations.sh не найден:</b> $INTEGRATION_CHECKER" 1
        log "❌ health-check-integrations.sh missing: $INTEGRATION_CHECKER"
    else
# check-integrations может вернуть exit 1 (найдены проблемы) — НЕ должен убивать watchdog
set +e
INTEGRATION_OUTPUT=$(bash "$INTEGRATION_CHECKER" --quick 2>&1)
INTEGRATION_EXIT=$?
set -e

if [ $INTEGRATION_EXIT -ne 0 ]; then
    # Каждая строка = отдельный инцидент: ключ = label + класс
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        [[ "$line" == "=== INTEGRATION HEALTH PROBLEMS ===" ]] && continue
        [[ "$line" == 🔌\ Проблемы\ с\ интеграциями:* ]] && continue
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
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════
# ОТПРАВКА АЛЕРТОВ
# ═══════════════════════════════════════════════════════════════════════════

# ── Восстановленные: swap требует 2 чистых цикла, остальные — один ──────
RESOLVED=()
for key in "${!ST_ALERTED[@]}"; do
    if [ "${ST_ALERTED[$key]}" = "1" ] && [ "${SEEN[$key]:-0}" != "1" ]; then
        recovery_threshold=1
        [ "$key" = "swap_high" ] && recovery_threshold="$SWAP_RECOVERY_STREAK"
        clean_streak=$(( ${ST_CLEAR[$key]:-0} + 1 ))
        if [ "$clean_streak" -ge "$recovery_threshold" ]; then
            RESOLVED+=("${ST_LABEL[$key]:-$key}")
            unset 'ST_ALERTED[$key]' 'ST_STREAK[$key]' 'ST_CLEAR[$key]' 'ST_LABEL[$key]'
        else
            ST_CLEAR["$key"]="$clean_streak"
            PERSIST["$key"]=1
            log "⏳ ${ST_LABEL[$key]:-$key}: clean recovery ${clean_streak}/${recovery_threshold}"
        fi
    fi
done

# ── Сохранение state атомарно; формат: key, alerted, bad_streak, clean_streak, label
# Persist an alerted problem during the hysteresis window so one clean sample
# cannot erase the evidence needed by the next run.
declare -A STATE_KEYS
for key in "${!SEEN[@]}"; do STATE_KEYS["$key"]=1; done
for key in "${!PERSIST[@]}"; do STATE_KEYS["$key"]=1; done
: > "$ALERT_STATE_FILE.tmp"
for key in "${!STATE_KEYS[@]}"; do
    printf '%s\t%s\t%s\t%s\t%s\n' "$key" "${ST_ALERTED[$key]:-0}" \
        "${ST_STREAK[$key]:-0}" "${ST_CLEAR[$key]:-0}" "${ST_LABEL[$key]:-$key}" >> "$ALERT_STATE_FILE.tmp"
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
    send_tg "$ALERT_MSG" "pin"
    log "📤 Отправлен алерт (${#NEW_PROBLEMS[@]} новых) + пин"
elif [ ${#RESOLVED[@]} -gt 0 ]; then
    R_MSG="✅ <b>Восстановлено</b> — $(date '+%H:%M')
"
    for r in "${RESOLVED[@]}"; do
        R_MSG+="• $r
"
    done
    send_tg "$R_MSG"
    log "📤 Отправлено восстановление (${#RESOLVED[@]}): ${RESOLVED[*]}"
else
    # Всё хорошо — тишина (heartbeat-сообщения убраны: шум при здоровой системе,
    # мониторинг здоровья — health-check L3 + heartbeat GitHub L4)
    log "✅ Все проверки пройдены — алерт не требуется"
fi

log "─── Конец проверки ───"
