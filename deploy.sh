#!/bin/bash
# ============================================================================
# deploy.sh — развёртка hermes-argus из шаблонов в живую систему.
# Запуск: ./deploy.sh [config.env]
# По умолчанию читает config.env из текущей директории.
# Модульность: ставится только включённое флагами MODULE_* (см.
# config/config.env.template). Всё, что требует внешних сервисов, — OFF.
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${1:-$REPO_DIR/config.env}"
SCRIPTS_DIR="$REPO_DIR/scripts"
MODULES_DIR="$REPO_DIR/modules"

# ── Загрузка конфигурации ──────────────────────────────────────────────────
if [ -f "$CONFIG_FILE" ]; then
    echo "📖 Загружаю конфигурацию: $CONFIG_FILE"
    set -a; source "$CONFIG_FILE"; set +a
else
    echo "⚠️  config.env не найден ($CONFIG_FILE). Использую переменные окружения."
fi

# ── Значения по умолчанию ──────────────────────────────────────────────────
HERMES_HOST="${HERMES_HOST:-127.0.0.1}"
HERMES_PORT="${HERMES_PORT:-9119}"
NETDATA_PORT="${NETDATA_PORT:-19999}"
WATCHDOG_CHAT_ID="${WATCHDOG_CHAT_ID:-}"
WATCHDOG_BOT_TOKEN="${WATCHDOG_BOT_TOKEN:-}"
HERMES_BOT_TOKEN="${HERMES_BOT_TOKEN:-}"
HERMES_BOT_UID="${HERMES_BOT_UID:-}"
BREAKER_MAX="${BREAKER_MAX:-3}"
DMS_SNITCH="${DMS_SNITCH:-change_me}"
DMS_API_KEY="${DMS_API_KEY:-change_me}"
GITHUB_REPO="${GITHUB_REPO:-upmeister/hermes-infra}"

# ── Модули: deploy ставит только включённое ────────────────────────────────
# Всё, что требует внешних сервисов, — OFF по умолчанию (см. config.env.template).
MODULE_CORE="${MODULE_CORE:-ON}"
MODULE_INTEGRATIONS="${MODULE_INTEGRATIONS:-ON}"
MODULE_TG_BOT="${MODULE_TG_BOT:-OFF}"
MODULE_ANALYZER="${MODULE_ANALYZER:-OFF}"
MODULE_HEARTBEAT="${MODULE_HEARTBEAT:-OFF}"
MODULE_GH_HEARTBEAT="${MODULE_GH_HEARTBEAT:-OFF}"
MODULE_DISCORD_BOT="${MODULE_DISCORD_BOT:-OFF}"

module_enabled() { [ "${!1}" = "ON" ]; }

HOME_DIR="${HOME:-$HOME}"
HERMES_DIR="${HERMES_DIR:-$HOME_DIR/.hermes}"

echo "🔧 Развёртка hermes-argus"
echo "   Хост: $HERMES_HOST:$HERMES_PORT"
echo "   Hermes директория: $HERMES_DIR"
echo "   Модули: CORE=$(module_enabled MODULE_CORE && echo ON || echo OFF) INTEGRATIONS=$(module_enabled MODULE_INTEGRATIONS && echo ON || echo OFF) TG_BOT=$(module_enabled MODULE_TG_BOT && echo ON || echo OFF) ANALYZER=$(module_enabled MODULE_ANALYZER && echo ON || echo OFF) HEARTBEAT=$(module_enabled MODULE_HEARTBEAT && echo ON || echo OFF) GH_HEARTBEAT=$(module_enabled MODULE_GH_HEARTBEAT && echo ON || echo OFF)"
echo ""

# ── Функция: развернуть bash-шаблон ──────────────────────────────────────
# Заменяет @МАРКЕРЫ@ на значения из конфига. Новый маркер = новая sed-рулька.
deploy_template() {
    local src="$1"
    local dst="$2"
    local name="$3"

    mkdir -p "$(dirname "$dst")"

    sed \
        -e "s/@HERMES_HOST@/$HERMES_HOST/g" \
        -e "s/@HERMES_PORT@/$HERMES_PORT/g" \
        -e "s|@HERMES_DIR@|$HERMES_DIR|g" \
        -e "s|@HERMES_BIN@|$HERMES_DIR/hermes-agent/venv/bin/hermes|g" \
        -e "s|@HOME_DIR@|$HOME_DIR|g" \
        -e "s/@WATCHDOG_BOT_TOKEN@/$WATCHDOG_BOT_TOKEN/g" \
        -e "s/@WATCHDOG_CHAT_ID@/$WATCHDOG_CHAT_ID/g" \
        -e "s/@HERMES_BOT_TOKEN@/$HERMES_BOT_TOKEN/g" \
        -e "s/@HERMES_BOT_UID@/$HERMES_BOT_UID/g" \
        -e "s/@BREAKER_MAX@/$BREAKER_MAX/g" \
        -e "s/@DMS_SNITCH@/$DMS_SNITCH/g" \
        -e "s/@DMS_API_KEY@/$DMS_API_KEY/g" \
        -e "s/@NETDATA_PORT@/$NETDATA_PORT/g" \
        -e "s|@GITHUB_REPO@|$GITHUB_REPO|g" \
        -e "s/@HOSTNAME@/$(hostname)/g" \
        "$src" > "$dst"

    # Делаем исполняемым если исходник был
    [ -x "$src" ] && chmod +x "$dst"

    echo "   ✅ $name → $dst"
}

# ── Манифесты модулей (ЯВНЫЕ списки — в целевых каталогах лежит и чужая
#    инфраструктура, wildcard-раскладка по каталогу запрещена) ──────────────

# CORE: локальный мониторинг и самозащита (внешнее — только TG-алерты)
CORE_HOME_SCRIPTS=(hermes-watchdog.sh auto-remediate.sh check-updates.sh \
                   network-guard.sh collect-metrics.sh send-monitoring-report.sh)
CORE_HERMES_SCRIPTS=(dashboard-liveness.sh gateway-liveness.sh watchdog-health.sh ssl-expiry-check.sh)
CORE_SYSTEMD=(hermes-dashboard.service hermes-dashboard.service.d/memory-limits.conf \
              hermes-gateway.service hermes-gateway.service.d/memory-limits.conf)

# INTEGRATIONS: discover конфига + каскад-трекер фолбека + health-check v2 (ядро Argus v2)
INTEGRATIONS_HOME_SCRIPTS=(integration-discover.py integration-discover-wrapper.sh fallback-tracker-v2.py \
                           health-check-v2.py health-check-v2-wrapper.sh)
INTEGRATIONS_HERMES_SCRIPTS=(health-check-integrations.sh)
INTEGRATIONS_SYSTEMD=(hermes-vps-kit-config.path hermes-vps-kit-discover.service)

# TG_BOT: интерактивный мониторинг-бот (control plane) — OFF по умолчанию
# webhook.py разворачивается в ОБЕ копии: poller импортирует её из своего каталога
# (~/.hermes/scripts), discord-bot — из ~/scripts (урок 2026-09-07: частичный
# деплой оставлял свежую и старую копии — AttributeError на import).
TG_BOT_HOME_SCRIPTS=(webhook.py ai-deep-check.py register-commands.sh)
TG_BOT_HERMES_SCRIPTS=(monitoring-bot-poller.py webhook.py)
TG_BOT_SYSTEMD=(monitoring-bot-poller.service)

# DISCORD_BOT: control plane для Discord (C5) — OFF по умолчанию
DISCORD_HOME_SCRIPTS=(discord-bot.py)
DISCORD_SYSTEMD=(discord-bot.service)

# ANALYZER: L3 health-analyzer экосистема (LLM-анализ логов) — OFF по умолчанию
ANALYZER_HERMES_SCRIPTS=(health-analyzer.py health_decay.py health_patterns.py health_netdata.py)

# HEARTBEAT: внешний dead man's switch (DMS / GitHub Heartbeat) — OFF по умолчанию
HEARTBEAT_HOME_SCRIPTS=(heartbeat.sh)

# ── Функции развёртки ──────────────────────────────────────────────────────
deploy_scripts() {
    local dest_dir="$1"; shift
    local script
    for script in "$@"; do
        if [ -f "$SCRIPTS_DIR/$script" ]; then
            deploy_template "$SCRIPTS_DIR/$script" "$dest_dir/$script" "$script"
        fi
    done
}

deploy_systemd() {
    local relpath service_name conf_name target_dir
    # Базовые юниты управляются Hermes (refresh_systemd_unit_if_needed их
    # перезаписывает) — не перезаписываем существующие, лимиты только через drop-in.
    local base_units=" hermes-gateway.service hermes-dashboard.service "
    for relpath in "$@"; do
        local unit="$MODULES_DIR/systemd/$relpath"
        if [[ "$relpath" == */* ]]; then
            # Это .d/*.conf файл
            service_name="${relpath%%/*}"
            conf_name="${relpath#*/}"
            target_dir="$HOME_DIR/.config/systemd/user/${service_name}"
            mkdir -p "$target_dir"
            deploy_template "$unit" "$target_dir/$conf_name" "systemd: $relpath"
        else
            if [[ "$base_units" == *" $relpath "* ]] && [ -f "$HOME_DIR/.config/systemd/user/$relpath" ]; then
                echo "   ⏭️  systemd: $relpath уже существует (управляется Hermes) — пропускаю (лимиты через drop-in)"
                continue
            fi
            deploy_template "$unit" "$HOME_DIR/.config/systemd/user/$relpath" "systemd: $relpath"
        fi
    done
}

# ── Развёртка по модулям ───────────────────────────────────────────────────
if module_enabled MODULE_CORE; then
    echo ""
    echo "📁 [CORE] скрипты и systemd-юниты..."
    deploy_scripts "$HOME_DIR/scripts" "${CORE_HOME_SCRIPTS[@]}"
    deploy_scripts "$HERMES_DIR/scripts" "${CORE_HERMES_SCRIPTS[@]}"
    deploy_systemd "${CORE_SYSTEMD[@]}"
fi

if module_enabled MODULE_INTEGRATIONS; then
    echo ""
    echo "📁 [INTEGRATIONS] discover + каскад-трекер + health-check v2..."
    deploy_scripts "$HOME_DIR/scripts" "${INTEGRATIONS_HOME_SCRIPTS[@]}"
    deploy_scripts "$HERMES_DIR/scripts" "${INTEGRATIONS_HERMES_SCRIPTS[@]}"
    deploy_systemd "${INTEGRATIONS_SYSTEMD[@]}"
    if [ -f "$REPO_DIR/registry.yaml" ]; then
        deploy_template "$REPO_DIR/registry.yaml" "$HERMES_DIR/state/registry.yaml" "registry.yaml"
    fi
fi

if module_enabled MODULE_TG_BOT; then
    echo ""
    echo "📁 [TG_BOT] мониторинг-бот (control plane)..."
    deploy_scripts "$HOME_DIR/scripts" "${TG_BOT_HOME_SCRIPTS[@]}"
    deploy_scripts "$HERMES_DIR/scripts" "${TG_BOT_HERMES_SCRIPTS[@]}"
    deploy_systemd "${TG_BOT_SYSTEMD[@]}"
    bash "$HOME_DIR/scripts/register-commands.sh" || true
    echo "   ℹ️  Перезапуск poller — вручную и вне активного использования бота."
fi

if module_enabled MODULE_DISCORD_BOT; then
    echo ""
    echo "📁 [DISCORD_BOT] control plane для Discord (C5)..."
    if [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
        echo "   ⚠️  DISCORD_BOT_TOKEN не задан в $HERMES_DIR/.env — бот не запустится."
        echo "      Токен: Discord Developer Portal → Applications → Bot → Reset Token."
    fi
    deploy_scripts "$HOME_DIR/scripts" "${DISCORD_HOME_SCRIPTS[@]}"
    deploy_systemd "${DISCORD_SYSTEMD[@]}"
    if [ ! -x "$HERMES_DIR/discord-venv/bin/python" ]; then
        echo "   🐍 Создаю venv и ставлю discord.py (одноразово)..."
        python3 -m venv "$HERMES_DIR/discord-venv" &&
            "$HERMES_DIR/discord-venv/bin/pip" install -q discord.py
    fi
    echo "   ℹ️  Старт: systemctl --user enable --now discord-bot.service (согласованно)"
fi

if module_enabled MODULE_ANALYZER; then
    echo ""
    echo "📁 [ANALYZER] health-analyzer экосистема (L3)..."
    deploy_scripts "$HERMES_DIR/scripts" "${ANALYZER_HERMES_SCRIPTS[@]}"
fi

if module_enabled MODULE_HEARTBEAT; then
    echo ""
    echo "📁 [HEARTBEAT] внешний dead man's switch..."
    deploy_scripts "$HOME_DIR/scripts" "${HEARTBEAT_HOME_SCRIPTS[@]}"
    echo "   ℹ️  Бекенды включаются ключами в $HERMES_DIR/.env (см. scripts/heartbeat.sh):"
    echo "      CRONPING_TOKEN — Cronping (рекомендуется, 5-мин гранулярность)"
    echo "      DMS_SNITCH     — Dead Man's Snitch (hourly)"
    echo "      GH_TOKEN+GITHUB_REPO — GitHub Heartbeat (MODULE_GH_HEARTBEAT)"
fi

# ── GH Heartbeat module: приватный репо + Actions-алерт по протуханию ──────
# OFF по умолчанию; gh repo create — только при явном согласии юзера (C4).
if module_enabled MODULE_GH_HEARTBEAT; then
    echo ""
    echo "📁 [GH_HEARTBEAT] внешний сторож через GitHub Actions..."
    if [ -z "${GH_TOKEN:-}" ]; then
        echo "   ⚠️  GH_TOKEN не задан — GitHub Heartbeat пропущен."
        echo "      Нужен PAT: classic — scopes repo + workflow; fine-grained —"
        echo "      Contents RW + Workflows RW. Если токен Hermes не подходит —"
        echo "      создайте отдельный: https://github.com/settings/tokens"
        echo "      Альтернативы: Dead Man's Snitch https://deadmanssnitch.com"
        echo "      или Cronping https://cronping.com (бекенды в scripts/heartbeat.sh)"
    elif ! command -v gh >/dev/null 2>&1; then
        echo "   ⚠️  gh CLI не найден (https://cli.github.com) — авто-создание репо недоступно."
        echo "      Альтернативы: Dead Man's Snitch https://deadmanssnitch.com"
        echo "      или Cronping https://cronping.com (бекенды в scripts/heartbeat.sh)"
    else
        GH_USER=$(gh api user -q .login 2>/dev/null || echo "")
        GH_HB_REPO="${GH_HEARTBEAT_REPO:-argus-heartbeat-$(hostname)}"
        if [ -z "$GH_USER" ]; then
            echo "   ⚠️  gh не авторизован / токен невалиден — GitHub Heartbeat пропущен."
        else
            printf "   Создать приватный репо %s/%s? [y/N]: " "$GH_USER" "$GH_HB_REPO"
            read -r ANSWER
            if [ "${ANSWER:-}" = "y" ] || [ "${ANSWER:-}" = "Y" ]; then
                if gh repo view "$GH_USER/$GH_HB_REPO" >/dev/null 2>&1; then
                    echo "   ℹ️  репо уже существует — использую его"
                else
                    gh repo create "$GH_USER/$GH_HB_REPO" --private
                fi
                HB_DIR="$HERMES_DIR/gh-heartbeat"
                mkdir -p "$HB_DIR/.github/workflows"
                date -u +"%Y-%m-%dT%H:%M:%SZ" > "$HB_DIR/heartbeat.txt"
                if [ -f "$MODULES_DIR/gh-heartbeat/heartbeat-alert.yml" ]; then
                    deploy_template "$MODULES_DIR/gh-heartbeat/heartbeat-alert.yml" \
                        "$HB_DIR/.github/workflows/heartbeat-alert.yml" "gh-heartbeat workflow"
                fi
                cd "$HB_DIR"
                git init -q 2>/dev/null || true
                git checkout -q -b main 2>/dev/null || true
                git add -A && git diff --cached --quiet || git commit -q -m "argus heartbeat init"
                if git push -q -f "https://${GH_TOKEN}@github.com/$GH_USER/$GH_HB_REPO" main 2>/dev/null; then
                    echo "   ✅ репо запушен"
                else
                    echo "   ⚠️  push failed — проверьте права токена (repo/workflow)"
                fi
                gh secret set WATCHDOG_BOT_TOKEN --repo "$GH_USER/$GH_HB_REPO" --body "${WATCHDOG_BOT_TOKEN:-}" >/dev/null && \
                gh secret set WATCHDOG_CHAT_ID --repo "$GH_USER/$GH_HB_REPO" --body "${WATCHDOG_CHAT_ID:-}" >/dev/null && \
                echo "   ✅ secrets установлены"
                echo "   ✅ GH Heartbeat готов. Добавьте в config.env и перезапустите deploy:"
                echo "      GITHUB_REPO=$GH_USER/$GH_HB_REPO"
            else
                echo "   ℹ️  Пропущено по отказу юзера. Альтернативы: DMS / Cronping"
                echo "      (https://deadmanssnitch.com, https://cronping.com)"
            fi
        fi
    fi
fi

# ── Генерация cron-строк по включённым модулям ─────────────────────────────
# Только СТРОКИ: весь crontab юзера не заменяем.
# CRON_PROFILE (C6 F6): full — весь набор; minimal — только тихие discovery/
# health-check строки (для тест-VM, чтобы алерты не сыпались в реальный чат)
CRON_PROFILE="${CRON_PROFILE:-full}"

CRON_TMP=$(mktemp)
{
    echo "# hermes-argus: cron-строки включённых модулей ($(date -Iseconds))"
    if module_enabled MODULE_CORE && [ "$CRON_PROFILE" = "full" ]; then
        echo "*/5 * * * * $HOME_DIR/scripts/hermes-watchdog.sh >> $HERMES_DIR/logs/watchdog-cron.log 2>&1"
        echo "*/2 * * * * $HOME_DIR/scripts/network-guard.sh >> $HERMES_DIR/logs/network-guard-cron.log 2>&1"
        echo "*/2 * * * * $HERMES_DIR/scripts/gateway-liveness.sh >> $HERMES_DIR/logs/gateway-liveness.log 2>&1"
        echo "*/5 * * * * $HERMES_DIR/scripts/dashboard-liveness.sh >> $HERMES_DIR/logs/dashboard-liveness.log 2>&1"
        echo "*/10 * * * * $HOME_DIR/scripts/auto-remediate.sh >> $HERMES_DIR/logs/auto-remediate.log 2>&1"
        echo "0 3 * * 1 $HOME_DIR/scripts/check-updates.sh"
        echo "30 * * * * $HERMES_DIR/scripts/watchdog-health.sh >> $HERMES_DIR/logs/watchdog-health-cron.log 2>&1"
        echo "0 6 * * * $HERMES_DIR/scripts/ssl-expiry-check.sh >> $HERMES_DIR/logs/ssl-expiry-cron.log 2>&1"
    fi
    if module_enabled MODULE_INTEGRATIONS; then
        echo "*/10 * * * * $HOME_DIR/scripts/integration-discover-wrapper.sh >> $HERMES_DIR/logs/integration-discover-cron.log 2>&1"
        echo "*/5 * * * * python3 $HOME_DIR/scripts/fallback-tracker-v2.py >> $HERMES_DIR/logs/fallback-tracker-v2.log 2>&1"
        echo "20 * * * * $HOME_DIR/scripts/health-check-v2-wrapper.sh >> $HERMES_DIR/logs/health-check-v2.log 2>&1"
    fi
    if module_enabled MODULE_ANALYZER; then
        echo "5 * * * * cd $HERMES_DIR/scripts && python3 health-analyzer.py --update >> $HERMES_DIR/logs/health-analyzer.log 2>&1"
    fi
    if module_enabled MODULE_HEARTBEAT; then
        echo "*/5 * * * * set -a; source $HERMES_DIR/.env; set +a; $HOME_DIR/scripts/heartbeat.sh >> $HERMES_DIR/logs/heartbeat.log 2>&1"
    fi
} > "$CRON_TMP"

if [ -s "$CRON_TMP" ]; then
    mv "$CRON_TMP" "$CRON_FILE"
    echo ""
    echo "📁 Cron-строки сгенерированы: $CRON_FILE"
    echo "   ⚠️  НЕ заменяй весь crontab! Добавь строки к существующим (без дублей):"
    echo "      (crontab -l; grep -v '^#' $CRON_FILE) | awk '!seen[\$0]++' | crontab -"
else
    rm -f "$CRON_TMP"
fi

echo ""
echo "✅ Развёртка завершена!"
echo ""
echo "👉 Что дальше:"
echo "   1. Проверь, что нет незаменённых маркеров:"
echo "      grep -rn '@[A-Z_]*@' $HOME_DIR/scripts/ $HERMES_DIR/scripts/ 2>/dev/null || echo 'Чисто!'"
echo "   2. Если включены TG-алерты/бот — проверь токены в config.env"
echo "   3. Перезагрузи systemd: systemctl --user daemon-reload"
if module_enabled MODULE_INTEGRATIONS; then
echo "   4. Включи вотчер конфига: systemctl --user enable --now hermes-vps-kit-config.path"
fi
echo "   5. Тестовый прогон: $HOME_DIR/scripts/hermes-watchdog.sh"
