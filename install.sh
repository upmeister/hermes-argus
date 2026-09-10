#!/bin/bash
# ============================================================================
# install.sh — bootstrap hermes-argus on a CLEAN Ubuntu 24.04 (C6).
#
# Usage (as a sudo-capable user, NOT root):
#   bash install.sh
#
# What it does: installs dependencies -> clones the repo -> creates config.env
# -> runs deploy.sh -> enables the config watcher -> runs post-deploy gates.
# Idempotent: safe to re-run after filling config.env.
# ============================================================================
set -euo pipefail

REPO_URL="https://github.com/upmeister/hermes-argus.git"
REPO_DIR="$HOME/hermes-argus"

echo "🦾 hermes-argus bootstrap"
echo "   Host: $(hostname) · user: ${USER:-$(whoami)} · $(lsb_release -ds 2>/dev/null || echo 'linux')"

# ── 1. Dependencies ─────────────────────────────────────────────────────────
SUDO=""
if [ "$(id -u)" != "0" ]; then
    SUDO="sudo"
    # Headless-проверка (C6 F2): парольный sudo в неинтерактивной среде = тупик
    if ! $SUDO -n true 2>/dev/null; then
        echo "⚠️  sudo требует пароль, а интерактива нет. Варианты:"
        echo "    1) поставь пакеты вручную и перезапусти install.sh:"
        echo "       sudo apt-get install -y git curl python3 python3-yaml cron"
        echo "    2) запусти install.sh в интерактивной сессии"
        exit 1
    fi
fi

# Ставим только отсутствующие пакеты (C6 F2: unconditional apt ломал headless)
NEED=()
for pkg in git curl python3 python3-yaml cron; do
    dpkg -s "$pkg" >/dev/null 2>&1 || NEED+=("$pkg")
done
if [ "${#NEED[@]}" -gt 0 ]; then
    echo "📦 Ставлю недостающее: ${NEED[*]}"
    $SUDO apt-get update -qq
    $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${NEED[@]}" >/dev/null
else
    echo "📦 Зависимости уже установлены — apt пропущен"
fi

# ── 2. Repo ─────────────────────────────────────────────────────────────────
if [ -d "$REPO_DIR/.git" ]; then
    echo "📥 Репо уже склонировано — обновляю..."
    git -C "$REPO_DIR" pull -q --ff-only
else
    echo "📥 Клонирую репо..."
    git clone -q "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

# ── 3. Config ───────────────────────────────────────────────────────────────
if [ ! -f config.env ]; then
    cp config/config.env.template config.env
    echo ""
    echo "✏️  Создан config.env из шаблона. Минимум для старта:"
    echo "      WATCHDOG_BOT_TOKEN  — токен бота мониторинга (@BotFather)"
    echo "      WATCHDOG_CHAT_ID    — твой Telegram ID (алерты и команды)"
    echo "   Опционально сейчас: HERMES_HOST (если netdata/dashboard биндятся на"
    echo "   внешний IP), heartbeat-бекенды — позже через ~/.hermes/.env."
    echo ""
    read -r -p "Открыть config.env для редактирования сейчас? [Y/n]: " ANSWER
    if [ "${ANSWER:-Y}" != "n" ] && [ "${ANSWER:-N}" != "N" ]; then
        ${EDITOR:-nano} config.env
    fi
fi

if grep -qE '^WATCHDOG_BOT_TOKEN=""' config.env; then
    echo "⚠️  WATCHDOG_BOT_TOKEN пуст в config.env — заполни и перезапусти: bash install.sh"
    exit 1
fi

# ── 4. Deploy ───────────────────────────────────────────────────────────────
echo ""
echo "🚀 Деплой..."
bash deploy.sh config.env

# ── 5. Watcher ──────────────────────────────────────────────────────────────
systemctl --user daemon-reload
if systemctl --user list-unit-files | grep -q hermes-vps-kit-config.path; then
    systemctl --user enable --now hermes-vps-kit-config.path
    echo "📡 Discover-вотчер config.yaml включён (path unit + cron-страховка)."
fi

# ── 6. Post-deploy gates ────────────────────────────────────────────────────
echo ""
echo "🚦 Post-deploy gates:"
echo -n "   маркеры: "
if grep -rn '@[A-Z_]*@' "$HOME/scripts/" "$HOME/.hermes/scripts/" 2>/dev/null | grep -q .; then
    echo "❌ Найдены незаменённые маркеры!"; exit 1
fi
echo "чисто"
bash -n "$HOME/scripts/hermes-watchdog.sh" && echo "   синтаксис: ok"

echo ""
echo "🏁 Готово. Осталось вручную:"
echo "   1. Cron-строки: (crontab -l; grep -v '^#' /tmp/hermes-argus-crontab.txt) | awk '!seen[\$0]++' | crontab -"
echo "   2. Hermes должен быть установлен — health-check проверит ключи автоматически"
echo "      (/integrations all в боте, cron :20)."
echo "   3. Heartbeat-бекенды (опционально): CRONPING_TOKEN / DMS_SNITCH в ~/.hermes/.env"
echo "   4. Discord (опционально): MODULE_DISCORD_BOT=ON + DISCORD_BOT_TOKEN + intents"
echo "      в Developer Portal."
