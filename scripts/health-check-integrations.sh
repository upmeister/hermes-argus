#!/bin/bash
# health-check-integrations.sh — единый канон интеграционных проверок (2026-08-20).
#
# Двухрежимный скрипт (консолидация check-integrations.sh + старый health-check-integrations.sh):
#   --quick  (default для watchdog L1 и crontab hourly): 4 быстрые проверки ключей/живости.
#            Формат вывода = legacy check-integrations.sh (строки "Label: msg" + заголовок
#            "=== INTEGRATION HEALTH PROBLEMS ==="), потому что hermes-watchdog.sh (L1, 5 мин)
#            парсит вывод именно так (классы auth/cfg/net по подстрокам).
#   default  (Hermes cron daily no_agent): все 14 расширенных проверок (провайдеры, egress,
#            балансы, ddgs-fallback). Формат legacy health-check-integrations.sh (блок ════).
#
# Silent on success (full) → no delivery. Output only on failure.
#
# История:
#   2026-08-08: (в daily) + Groq, OpenRouter (models+balance <$0.50), Honcho, agentrouter 8319,
#               searxng log check. Supermemory/Tavily removed.
#   2026-08-20: объединены check-integrations.sh (quick) и health-check-integrations.sh (full)
#               в один канон с режимом --quick. wrapper ~/scripts/check-integrations.sh → это --quick.
#   17.08.2026: status_hint по статус-страницам (GitHub 503 при валидном токене — внешний инцидент).
#   23.08.2026: убрана проверка OpenRouter credits/balance — все OR-модели free-тир, баланс не нужен.

set -uo pipefail   # НЕ -e: быстрые проверки гоняем через || true и собираем вручную

MODE="full"
case "${1:-}" in
  --quick) MODE="quick" ;;
  --full)  MODE="full" ;;
  -h|--help)
    echo "Usage: $0 [--quick|--full]"; exit 0 ;;
esac

# --- config -----------------------------------------------------------
RETRIES=3
RETRY_DELAY=10
TIMEOUT=15
set -a; source ~/.hermes/.env 2>/dev/null || true; set +a
FAILURES=""
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── helpers (общие) ──────────────────────────────────────────────────
check_env() {   # name var — проверяет, что env var не пустая
    local name="$1" var="$2"
    if [[ -z "${!var:-}" ]]; then
        FAILURES+="  ❌ $name: \`$var\` is empty or unset"$'\n'
        return 1
    fi
    return 0
}

check_url() {   # name url [expected] [auth_header] [proxy]
    local name="$1" url="$2" expected="${3:-200}" auth_header="${4:-}" proxy="${5:-}"
    local attempt=0 code
    while [[ $attempt -lt $RETRIES ]]; do
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" \
            ${proxy:+--proxy "$proxy"} \
            ${auth_header:+-H "$auth_header"} "$url" 2>/dev/null || true)
        [[ "$code" == "$expected" ]] && return 0
        attempt=$((attempt + 1))
        [[ $attempt -lt $RETRIES ]] && sleep "$RETRY_DELAY"
    done
    FAILURES+="  ❌ $name: HTTP $code (expected $expected)"$'\n'
    return 1
}

check_alive() {   # name url — любой HTTP (401/403) = жив; только 000 fails
    local name="$1" url="$2"
    local attempt=0 code
    while [[ $attempt -lt $RETRIES ]]; do
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$url" 2>/dev/null || true)
        [[ "$code" != *000* ]] && return 0
        attempt=$((attempt + 1))
        [[ $attempt -lt $RETRIES ]] && sleep "$RETRY_DELAY"
    done
    FAILURES+="  ❌ $name: HTTP $code (no response)"$'\n'
    return 1
}

# Внешний статус-хинт (no-LLM): 5xx/000 внешнего API ≠ наш сбой → уточняем по
# официальной Statuspage-странице. 17.08.2026: GitHub 503 при валидном токене.
status_hint_daily() {   # добавляет хинт прямо в FAILURES (формат daily)
    local name="$1" url="$2"
    if ! grep -qE "$name: HTTP (5|0)" <<< "$FAILURES"; then return 0; fi
    local hint
    hint=$(curl -s --connect-timeout 4 --max-time 6 "$url" 2>/dev/null | python3 -c '
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
    [ -n "$hint" ] && FAILURES+="  💡 $name — внешний статус: $hint"$'\n'
}

# e2e SOCKS5 (sing-box vless-тир)
check_socks() {   # name port url expected
    local name="$1" port="$2" url="$3" expected="${4:-200}"
    local attempt=0 code
    while [[ $attempt -lt $RETRIES ]]; do
        code=$(curl -s -o /dev/null -w "%{http_code}" --socks5-hostname "127.0.0.1:$port" \
            --max-time "$TIMEOUT" "$url" 2>/dev/null || true)
        [[ "$code" == "$expected" ]] && return 0
        attempt=$((attempt + 1))
        [[ $attempt -lt $RETRIES ]] && sleep "$RETRY_DELAY"
    done
    FAILURES+="  ❌ $name: HTTP $code (expected $expected)"$'\n'
    return 1
}

# ── QUICK ЧЕКИ (4 быстрых; формат вывода = legacy check-integrations.sh, парсит watchdog) ──
run_quick() {
    local PROBLEMS=()
    TG_PROXY="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"

    # Внешний статус-хинт (quick): печатает строку, а не в FAILURES
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
    local HTTP_CODE
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 8 --max-time 12 \
        -H "Authorization: token ${GITHUB_TOKEN}" \
        "https://api.github.com/user" 2>/dev/null)
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
            RESP=$(curl -s -w $'\n%{http_code}' --connect-timeout 8 --max-time 25 -x "$TG_PROXY" \
                "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/getMe" 2>/dev/null)
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

# ── FULL ЧЕКИ (14 расширенных; формат legacy health-check-integrations.sh) ──
run_full() {
    echo "integration-health-check @ $TIMESTAMP"

    # 1. OpenCode Go API (critical)
    check_url "OpenCode Go API" "https://opencode.ai/zen/go/v1/models" "200" \
        "Authorization: Bearer ${OPENCODE_GO_API_KEY:-}" || true
    status_hint_daily "OpenCode Go API" "https://deepseek.statuspage.io/api/v2/status.json"

    # 2. SearXNG (critical, local)
    check_url "SearXNG" "http://localhost:8080/search?format=json&q=health+check" "200" || true

    # 3. Firecrawl
    check_url "Firecrawl API" "https://api.firecrawl.dev/v1/team/credit-usage" "200" \
        "Authorization: Bearer ${FIRECRAWL_API_KEY:-}" || true

    # 4. Telegram Bot API (critical, через TELEGRAM_PROXY — РКН)
    check_url "Telegram Bot API" \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN:-}/getMe" "200" "" \
        "${TELEGRAM_PROXY:-}" || true

    # 5. GitHub API
    check_url "GitHub API" "https://api.github.com/user" "200" \
        "Authorization: Bearer ${GITHUB_TOKEN:-}" || true
    status_hint_daily "GitHub API" "https://www.githubstatus.com/api/v2/summary.json"

    # 6. DuckDuckGo (fallback search; тоже РКН-блокируется)
    check_url "DuckDuckGo" "https://duckduckgo.com/" "200" "" "${TELEGRAM_PROXY:-}" || true

    # 7. sing-box VLESS tier (critical: telegram tier-3/4 + luna geo-unblock), e2e через socks
    check_socks "sing-box VLESS (1080)" "1080" "https://api.telegram.org" "302" || true

    # 8. opencode-smart-proxy (8445, HTTPS_PROXY для модельных вызовов — luna)
    check_url "opencode-smart-proxy (8445)" "https://opencode.ai/zen/go/v1/models" "200" "" \
        "http://127.0.0.1:8445" || true

    # 9. Groq API (STT/vision)
    check_url "Groq API" "https://api.groq.com/openai/v1/models" "200" \
        "Authorization: Bearer ${GROQ_API_KEY:-}" || true
    status_hint_daily "Groq API" "https://groqstatus.com/api/v2/status.json"

    # 10. OpenRouter API. Все используемые модели — free-тир (z-ai/glm-5.2:free default,
        #     gemma/nemotron fallback) → баланс не нужен. Проверка credits убрана 23.08.2026:
        #     рудимент vision-on-OR (14-19.08, сожгла $11.9, фикс 20.08 → custom:groq).
        #     Вернуть, если появятся платные OR-модели.
        check_url "OpenRouter API" "https://openrouter.ai/api/v1/models" "200" \
            "Authorization: Bearer ${OPENROUTER_API_KEY:-}" || true

    # 11. Honcho API (memory provider; без auth — любой HTTP = жив)
    check_alive "Honcho API" "https://api.honcho.dev/" || true

    # 12. agentrouter-proxy (8319, WAF-fingerprint + SSE data:null)
    check_url "agentrouter-proxy (8319)" "http://127.0.0.1:8319/v1/models" "200" || true

    # 13. Web search должен идти через searxng (месяц молчаливого ddgs-fallback). Нет строки = ок.
    local LAST_SEARCH
    LAST_SEARCH=$(grep 'Web search via' ~/.hermes/logs/agent.log 2>/dev/null | tail -1 || true)
    if [[ -n "$LAST_SEARCH" && "$LAST_SEARCH" != *"via searxng"* ]]; then
        FAILURES+="  ❌ Web search backend: last search NOT via searxng (silent ddgs fallback): $(echo "$LAST_SEARCH" | cut -c1-160)"$'\n'
    fi

    # 14. systemd user timer telegram-path-manager: active + state тикает ≤6 мин
    local TIMER_STATE
    TIMER_STATE=$(systemctl --user is-active telegram-path-manager.timer 2>/dev/null || true)
    if [[ "$TIMER_STATE" == "active" ]]; then
        if [[ -z "$(find ~/.hermes/state/telegram-path-state.json -mmin -6 2>/dev/null)" ]]; then
            FAILURES+="  ❌ telegram-path-manager.timer: active, но state не обновлялся >6 мин"$'\n'
        fi
    elif [[ -n "$TIMER_STATE" ]]; then
        FAILURES+="  ❌ telegram-path-manager.timer: $TIMER_STATE"$'\n'
    fi

    # 15. Ключевые env-переменные: пустая = секрет пропал
    check_env "ClinePass"  "CLINE_API_KEY"
    check_env "GitHub"     "GH_TOKEN"
    check_env "Telegram"   "TELEGRAM_BOT_TOKEN"
    check_env "Watchdog"   "WATCHDOG_BOT_TOKEN"
    check_env "OpenRouter" "OPENROUTER_API_KEY"
    check_env "Groq"       "GROQ_API_KEY"
    check_env "AgentRouter" "AGENTROUTER_API_KEY"

    if [[ -n "$FAILURES" ]]; then
        echo ""
        echo "═══════════════════════════════════════════"
        echo "⚠️  Integration health-check FAILED at $TIMESTAMP"
        echo "═══════════════════════════════════════════"
        echo "$FAILURES"
        echo "Server: $(hostname) · RAM: $(free -h | awk '/Mem/{print $3"/"$2}') · Swap: $(free -h | awk '/Swap/{print $3"/"$2}')"
        exit 1
    fi
    exit 0
}

# ── MAIN ─────────────────────────────────────────────────────────────
if [ "$MODE" = "quick" ]; then
    run_quick
else
    run_full
fi
