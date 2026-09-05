#!/bin/bash
# ============================================================================
# Network Guard (B1): сетевые инварианты + авто-откат.
# Системный cron каждые 2 мин. No LLM — работает даже когда агент мёртв.
#
# Инварианты:
#   1. DNS: ни один интерфейс кроме lo/eth0 не должен иметь DNS/DNS-домены
#      (sing-box при поднятии tun захватывает DNS через systemd-resolved →
#       все запросы уходят в мёртвый адрес → агент молчит)
#   2. ip rule: только baseline + warp-правила path-manager (lookup 99)
#      (кастомное правило/таблица → пакеты в tun с src-петлёй → anti-loop drop)
#
# Откат ТОЛЬКО при нарушении инвариантов. Внешняя деградация (РКН-волна) —
# не наш случай: guard молчит, её мониторят heartbeat/health-check.
# Circuit breaker: >=2 отката/час → стоп на час + алерт.
# ============================================================================

set -u

STATE_DIR="$HOME/.hermes/state/network-guard"
BASELINE="$STATE_DIR/baseline-iprule.txt"
STATE="$STATE_DIR/state.json"
LOG="$HOME/.hermes/logs/network-guard.log"
BREAKER_MAX=2           # откатов в час
BREAKER_WINDOW=3600     # секунд
CHECK_TIMEOUT=5

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG"; }

# --- state helpers ----------------------------------------------------------
state_read() { [ -f "$STATE" ] && cat "$STATE" || echo '{"fails":0,"actions_hour":0,"breaker_until":0}'; }
state_write() { echo "$1" > "$STATE"; }

# --- Telegram alert (паттерн watchdog: прямой API, громкий + пин) -----------
send_alert() {
    local msg="$1"
    set -a; source "$HOME/.hermes/.env" 2>/dev/null; set +a
    [ -z "${WATCHDOG_BOT_TOKEN:-}" ] && { log "ALERT (no token): $msg"; return; }
    # Через telegram-smart-proxy: прямой api.telegram.org мёртв при РКН-волнах,
    # а HTTPS_PROXY из .env (8445) умеет только opencode.ai
    local proxy="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
    local escaped=$(python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" <<< "$msg")
    local resp=$(curl -s -m 10 -x "$proxy" -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\":\"${WATCHDOG_CHAT_ID:-@WATCHDOG_CHAT_ID@}\",\"text\":$escaped,\"disable_notification\":false}" 2>/dev/null)
    local mid=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('message_id',''))" 2>/dev/null)
    [ -n "$mid" ] && curl -s -m 10 -x "$proxy" -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/pinChatMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\":\"${WATCHDOG_CHAT_ID:-@WATCHDOG_CHAT_ID@}\",\"message_id\":$mid,\"disable_notification\":true}" -o /dev/null 2>/dev/null
    local status=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('ok') else d.get('error_code','ERR'))" 2>/dev/null || echo ERR)
    log "ALERT sent [$status]: $msg"
}

# --- Проверка 1: DNS-захват -------------------------------------------------
check_dns() {
    local bad=""
    local primary=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
    for iface in $(ls /sys/class/net 2>/dev/null); do
        [ "$iface" = "lo" ] && continue
        [ "$iface" = "$primary" ] && continue
        [ "$iface" = "tailscale0" ] && continue
        # singtun0/wgX и пр. не должны иметь DNS
        if timeout $CHECK_TIMEOUT resolvectl status "$iface" 2>/dev/null | grep -qE "Current DNS Server|DNS Domain"; then
            bad="$bad $iface"
        fi
    done
    echo "$bad"
}

# --- Проверка 2: ip rule diff ------------------------------------------------
check_rules() {
    local current new
    current=$(ip rule show 2>/dev/null | sed 's/^[0-9]*:[[:space:]]*//')
    # Новые правила: которых нет в baseline
    new=$(comm -13 <(sort "$BASELINE") <(echo "$current" | sort))
    # Разрешено: warp-правила path-manager (lookup 99). Всё остальное — нарушение.
    echo "$new" | grep -v "lookup 99" | grep -v '^$'
}

# --- Откат: DNS --------------------------------------------------------------
rollback_dns() {
    for iface in $1; do
        sudo -n resolvectl revert "$iface" 2>/dev/null
        log "ROLLBACK DNS: revert $iface"
    done
}

# --- Откат: ip rules ---------------------------------------------------------
rollback_rules() {
    while IFS= read -r rule; do
        [ -z "$rule" ] && continue
        # таблицы, на которые ссылается правило
        for tbl in $(echo "$rule" | grep -oE 'lookup [0-9]+' | awk '{print $2}'); do
            sudo -n ip route flush table "$tbl" 2>/dev/null
            log "ROLLBACK: flushed table $tbl"
        done
        # само правило (без суффикса pref, ip rule del сам найдёт)
        sudo -n ip rule del $rule 2>/dev/null
        log "ROLLBACK: ip rule del $rule"
    done <<< "$1"
}

# ============================================================================
# MAIN
# ============================================================================
mkdir -p "$STATE_DIR"

# Первый запуск: фиксируем baseline known-good
if [ ! -f "$BASELINE" ]; then
    ip rule show 2>/dev/null | sed 's/^[0-9]*:[[:space:]]*//' | sort > "$BASELINE"
    log "BASELINE создан ($(wc -l < "$BASELINE") правил)"
    echo '{"fails":0,"actions_hour":0,"breaker_until":0,"note":"baseline created"}' > "$STATE"
    exit 0
fi

STATE_JSON=$(state_read)
BREAKER_UNTIL=$(echo "$STATE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('breaker_until',0))" 2>/dev/null || echo 0)
NOW=$(date +%s)

# Circuit breaker активен?
if [ "$NOW" -lt "$BREAKER_UNTIL" ]; then
    log "CIRCUIT BREAKER active until $(date -u -d @$BREAKER_UNTIL +%H:%M:%SZ) — skip"
    exit 0
fi

DNS_BAD=$(check_dns)
RULES_BAD=$(check_rules)
E2E=$(curl -m 6 -s -o /dev/null -w '%{http_code}' https://opencode.ai/zen/go/v1/models 2>/dev/null; printf '/'; curl -m 6 -s -o /dev/null -w '%{http_code}' https://github.com 2>/dev/null)

VIOLATIONS=0
[ -n "$DNS_BAD" ] && VIOLATIONS=$((VIOLATIONS+1))
[ -n "$RULES_BAD" ] && VIOLATIONS=$((VIOLATIONS+1))

# Нарушений нет — обновляем state и выходим тихо
if [ "$VIOLATIONS" -eq 0 ]; then
    state_write "{\"fails\":0,\"actions_hour\":$(echo "$STATE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('actions_hour',0))" 2>/dev/null || echo 0),\"breaker_until\":$BREAKER_UNTIL,\"last_check\":\"$(date -u +%H:%M:%SZ)\",\"dns_ok\":true,\"rules_ok\":true,\"e2e\":\"$E2E\"}"
    exit 0
fi

# --- Нарушения: откат --------------------------------------------------------
log "VIOLATIONS: dns=[$DNS_BAD] rules=[$RULES_BAD]"
[ -n "$DNS_BAD" ] && rollback_dns "$DNS_BAD"
[ -n "$RULES_BAD" ] && rollback_rules "$RULES_BAD"

# Проверяем, что откат помог
DNS_BAD_AFTER=$(check_dns)
RULES_BAD_AFTER=$(check_rules)
OK_AFTER="no"
if [ -z "$DNS_BAD_AFTER" ] && [ -z "$RULES_BAD_AFTER" ]; then
    OK_AFTER="yes"
fi

# Circuit breaker
ACTIONS_HOUR=$(echo "$STATE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('actions_hour',0))" 2>/dev/null || echo 0)
LAST_ACTION=$(echo "$STATE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('last_action',0))" 2>/dev/null || echo 0)
if [ $((NOW - LAST_ACTION)) -gt $BREAKER_WINDOW ]; then
    ACTIONS_HOUR=0
fi
ACTIONS_HOUR=$((ACTIONS_HOUR + 1))
BREAKER=0
if [ "$ACTIONS_HOUR" -ge "$BREAKER_MAX" ]; then
    BREAKER=$((NOW + BREAKER_WINDOW))
    send_alert "🛑 Network Guard: $BREAKER_MAX отката за час — circuit breaker на 1ч. Возможны легитимные изменения сети (проверить вручную)."
fi

send_alert "🛠 Network Guard откатил сетевые нарушения:
DNS-захват: [$DNS_BAD]
Чужие правила: [$RULES_BAD]
Откат успешен: $OK_AFTER
E2E (opencode/github): $E2E"

state_write "{\"fails\":1,\"actions_hour\":$ACTIONS_HOUR,\"breaker_until\":$BREAKER,\"last_action\":$NOW,\"last_check\":\"$(date -u +%H:%M:%SZ)\",\"dns_ok\":false,\"rules_ok\":false,\"e2e\":\"$E2E\",\"rolled_back\":\"$OK_AFTER\"}"
exit 0
