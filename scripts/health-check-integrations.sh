#!/bin/bash
# health-check-integrations.sh — quick-канон интеграционных проверок (2026-08-20).
#
# Формат вывода = legacy check-integrations.sh (строки "Label: msg" + заголовок
# "=== INTEGRATION HEALTH PROBLEMS ==="), потому что hermes-watchdog.sh (L1, 5 мин)
# парсит вывод именно так (классы auth/cfg/net по подстрокам).
#
# История:
#   2026-08-08: (в daily) + Groq, OpenRouter (models+balance <$0.50), Honcho, agentrouter 8319,
#               searxng log check. Supermemory/Tavily removed.
#   2026-08-20: объединены check-integrations.sh (quick) и health-check-integrations.sh (full)
#               в один канон с режимом --quick. wrapper ~/scripts/check-integrations.sh → это --quick.
#   17.08.2026: status_hint по статус-страницам (GitHub 503 при валидном токене — внешний инцидент).
#   23.08.2026: убрана проверка OpenRouter credits/balance — все OR-модели free-тир, баланс не нужен.
#   2026-10-02: RR0b — полный режим (14 расширенных personal-проверок) снят: живых
#               вызывающих нет, структурированный full-check принадлежит
#               health-check-v2.py (cron health-check-v2-wrapper.sh). Остался quick-канон:
#               --quick, --full и вызов без аргументов выполняют один и тот же набор.

set -uo pipefail

case "${1:-}" in
  --quick) : ;;
  --full)  : ;;  # принят для совместимости: выполняется тот же quick-канон
  -h|--help)
    echo "Usage: $0 [--quick|--full] (оба выполняют quick-канон; full снят — см. health-check-v2.py)"; exit 0 ;;
esac

# --- config -----------------------------------------------------------
set -a; source ~/.hermes/.env 2>/dev/null || true; set +a

# ── QUICK ЧЕКИ (4 быстрых; формат вывода = legacy check-integrations.sh, парсит watchdog) ──
run_quick() {
    local PROBLEMS=()
    TG_PROXY="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"

    # Внешний статус-хинт (quick): печатает строку хинта в сообщение о проблеме
    status_hint() {
        local label="$1" url="$2" out
        out=$(curl -s --connect-timeout 4 --max-time 6 "$url" 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    parts = []
    if d.get("status", {}).get("description"):
        parts.append(d["status"]["description"])
    for i in d.get("incidents", []):
        if i.get("status") not in ("resolved", "postmortem"):
            parts.append(i.get("name", ""))
            break
    print(" | ".join(p for p in parts if p))
except Exception:
    pass
' 2>/dev/null)
        [ -n "$out" ] && echo " — $label: $out"
    }

    # 1. GitHub token
    local HTTP_CODE hdr
    # R1c: Authorization не в argv — quoted header в curl config на stdin;
    # без кавычек реальный curl заголовок молча не отправляет.
    hdr=${GITHUB_TOKEN//\\/\\\\}
    hdr=${hdr//\"/\\\"}
    HTTP_CODE=$(printf 'url = https://api.github.com/user\nheader = "Authorization: token %s"\n' \
        "$hdr" | \
        curl -s -o /dev/null -w "%{http_code}" --connect-timeout 8 --max-time 12 -K - 2>/dev/null)
        HTTP_CODE=${HTTP_CODE:-000}
    if [ "$HTTP_CODE" != "200" ]; then
        local MSG="🔑 GitHub token: HTTP $HTTP_CODE (ожидался 200)"
        if [[ "$HTTP_CODE" == "5"* ]] || [ "$HTTP_CODE" = "000" ]; then
            MSG+="$(status_hint "GitHub Status" "https://www.githubstatus.com/api/v2/summary.json")"
        fi
        PROBLEMS+=("$MSG")
    fi

    # 2. Telegram monitoring bot (getMe через TG_PROXY, ретраи 3×10с, таймаут 25с — РКН-полублок)
    if [ -n "${WATCHDOG_BOT_TOKEN:-}" ]; then
        local BOT_OK=false attempt RESP BODY
        for attempt in 1 2 3; do
            # Токен не в argv: URL уходит в curl через -K - (config на stdin)
            RESP=$(printf 'url = %s\n' "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/getMe" | \
                curl -s -w $'\n%{http_code}' --connect-timeout 8 --max-time 25 -x "$TG_PROXY" -K - 2>/dev/null)
            HTTP_CODE=$(printf '%s' "$RESP" | tail -1)
            BODY=$(printf '%s' "$RESP" | head -n -1)
            if printf '%s' "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
                BOT_OK=true; break
            fi
            [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "404" ] && break
            [ "$attempt" -lt 3 ] && sleep 10
        done
        if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "404" ]; then
            PROBLEMS+=("🤖 Telegram monitoring bot: HTTP $HTTP_CODE — токен невалиден/отозван")
        elif ! $BOT_OK; then
            PROBLEMS+=("🤖 Telegram monitoring bot: не отвечает (HTTP ${HTTP_CODE:-000}) — сеть/канал, токен в порядке")
        fi
    fi

    # 3. Netdata API
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 8 \
        "http://@HERMES_HOST@:@NETDATA_PORT@/api/v1/info" 2>/dev/null); HTTP_CODE=${HTTP_CODE:-000}
    [ "$HTTP_CODE" != "200" ] && PROBLEMS+=("📊 Netdata API: HTTP $HTTP_CODE (ожидался 200)")

    # 4. Целостность crontab
    local CRON_COUNT
    CRON_COUNT=$(crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | wc -l)
    [ "$CRON_COUNT" -lt 7 ] && PROBLEMS+=("📋 Crontab: найдено $CRON_COUNT задач (ожидалось ≥7) — возможна потеря!")

    if [ ${#PROBLEMS[@]} -gt 0 ]; then
        echo "=== INTEGRATION HEALTH PROBLEMS ==="
        for p in "${PROBLEMS[@]}"; do echo "$p"; done
        exit 1
    fi
    echo "=== Все интеграции OK ==="
    exit 0
}

# ── MAIN ─────────────────────────────────────────────────────────────
# RR0b: полный режим снят — структурированный full-check принадлежит
# health-check-v2.py (deploy ставит его cron-строку health-check-v2-wrapper.sh).
# Любой вызов (--quick, --full, без аргументов) выполняет quick-канон выше.
run_quick
