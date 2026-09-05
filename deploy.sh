#!/bin/bash
# ============================================================================
# deploy.sh — развёртка hermes-vps-kit из шаблонов в живую систему.
# Запуск: ./deploy.sh [config.env]
# По умолчанию читает config.env из текущей директории.
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

HOME_DIR="${HOME:-$HOME}"
HERMES_DIR="${HERMES_DIR:-$HOME_DIR/.hermes}"

echo "🔧 Развёртка hermes-vps-kit"
echo "   Хост: $HERMES_HOST:$HERMES_PORT"
echo "   Hermes директория: $HERMES_DIR"
echo ""

# ── Функция: развернуть bash-шаблон ──────────────────────────────────────
# Заменяет @МАРКЕРЫ@ на значения из конфига.
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

# ── Развёртка скриптов ────────────────────────────────────────────────────
echo "📁 Развёртка скриптов → $HOME_DIR/scripts/..."
for script in hermes-watchdog.sh auto-remediate.sh check-updates.sh \
              network-guard.sh heartbeat.sh send-monitoring-report.sh \
              collect-metrics.sh webhook.py \
              integration-discover.py integration-discover-wrapper.sh \
              fallback-tracker-v2.py; do
    [ -f "$SCRIPTS_DIR/$script" ] && deploy_template "$SCRIPTS_DIR/$script" "$HOME_DIR/scripts/$script" "$script"
done

echo ""
echo "📁 Развёртка скриптов → $HERMES_DIR/scripts/..."
for script in dashboard-liveness.sh gateway-liveness.sh \
              health-check-integrations.sh health-analyzer.py \
              health_decay.py health_patterns.py health_netdata.py \
              watchdog-health.sh ssl-expiry-check.sh \
              monitoring-bot-poller.py model-fallback-tracker.py; do
    [ -f "$SCRIPTS_DIR/$script" ] && deploy_template "$SCRIPTS_DIR/$script" "$HERMES_DIR/scripts/$script" "$script"
done

# ── Развёртка systemd шаблонов ─────────────────────────────────────────────
echo ""
echo "📁 Развёртка systemd шаблонов..."
if [ -d "$MODULES_DIR/systemd" ]; then
    while IFS= read -r -d '' unit; do
        relpath="${unit#$MODULES_DIR/systemd/}"
        if [[ "$relpath" == */* ]]; then
            # Это .d/*.conf файл
            service_name="${relpath%%/*}"
            conf_name="${relpath#*/}"
            target_dir="$HOME_DIR/.config/systemd/user/${service_name}"
            mkdir -p "$target_dir"
            deploy_template "$unit" "$target_dir/$conf_name" "systemd: $relpath"
        else
            deploy_template "$unit" "$HOME_DIR/.config/systemd/user/$relpath" "systemd: $relpath"
        fi
    done < <(find "$MODULES_DIR/systemd" -type f \( -name '*.service' -o -name '*.conf' -o -name '*.timer' -o -name '*.path' \) -print0)
fi

# ── Генерация crontab (если есть шаблон) ──────────────────────────────────
if [ -f "$MODULES_DIR/crontab.template" ]; then
    echo ""
    echo "📁 Генерация crontab..."
    deploy_template "$MODULES_DIR/crontab.template" "/tmp/hermes-vps-kit-crontab.txt" "crontab"
    echo "   ℹ️  crontab сгенерирован: /tmp/hermes-vps-kit-crontab.txt"
    echo "   Установка: crontab /tmp/hermes-vps-kit-crontab.txt"
fi

echo ""
echo "✅ Развёртка завершена!"
echo ""
echo "👉 Что дальше:"
echo "   1. Проверь, что нет незаменённых маркеров:"
echo "      grep -rn '@.*@' $HOME_DIR/scripts/ $HERMES_DIR/scripts/ 2>/dev/null || echo 'Чисто!'"
echo "   2. Если есть Telegram бот — проверь токен в .env"
echo "   3. Перезапусти демоны: systemctl --user daemon-reload"
echo "   4. Тестовый прогон: $HOME_DIR/scripts/hermes-watchdog.sh"
echo ""
echo "📡 Включить вотчер конфига (discover по изменению):"
echo "      systemctl --user daemon-reload"
echo "      systemctl --user enable --now hermes-vps-kit-config.path"