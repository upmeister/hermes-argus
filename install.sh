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
# C6 F5 (review 2026-09-11): sudo-гейт ПОСЛЕ dpkg-проверки и только для
# реально недостающих пакетов; probe — scoped apt-get, не sudo -n true
# (NOPASSWD-scoped установки проходят честно).
# B3 (RR1b): python3-venv — преrequisит изолированного интерпретатора бота
# (discord-bot.service запускается ~/.hermes/discord-venv/bin/python); без
# него `python3 -m venv` в deploy падает с ensurepip-ошибкой.
NEED=()
for pkg in git curl python3 python3-yaml python3-venv cron; do
    dpkg -s "$pkg" >/dev/null 2>&1 || NEED+=("$pkg")
done
if [ "${#NEED[@]}" -gt 0 ]; then
    SUDO=""
    if [ "$(id -u)" != "0" ]; then
        SUDO="sudo"
        if ! $SUDO -n apt-get -v >/dev/null 2>&1; then
            echo "⚠️  Недостающие пакеты: ${NEED[*]}"
            echo "    sudo требует пароль/права — поставь вручную и перезапусти:"
            echo "    sudo apt-get install -y ${NEED[*]}"
            exit 1
        fi
    fi
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
    git clone -q --depth 1 "$REPO_URL" "$REPO_DIR"
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
    # F7: без TTY редактор не предлагается (headless не виснет)
    if [ -t 0 ] && [ -z "${ARGUS_SKIP_EDIT:-}" ]; then
        read -r -p "Открыть config.env для редактирования сейчас? [Y/n]: " ANSWER
        if [ "${ANSWER:-Y}" != "n" ] && [ "${ANSWER:-N}" != "N" ]; then
            ${EDITOR:-nano} config.env
        fi
    fi
fi

if grep -qE '^WATCHDOG_BOT_TOKEN=""' config.env; then
    echo "⚠️  WATCHDOG_BOT_TOKEN пуст в config.env — заполни и перезапусти: bash install.sh"
    exit 1
fi

# ── 4. Deploy ───────────────────────────────────────────────────────────────
echo ""
echo "🚀 Деплой..."
# Вывод сохраняется для fail-closed гейта ниже, но идёт в терминал как раньше.
# pipefail в шелле уже включён: сбой deploy.sh обрывает установку здесь.
DEPLOY_LOG="$(mktemp)"
trap 'rm -f "$DEPLOY_LOG"' EXIT
bash deploy.sh config.env 2>&1 | tee "$DEPLOY_LOG"
DEPLOY_OUT="$(cat "$DEPLOY_LOG")"

# ── 5. Watcher ──────────────────────────────────────────────────────────────
systemctl --user daemon-reload
# RR0c (B3): ровно один активный producer. Legacy-юнит, который включён ИЛИ
# фактически активен (active-but-not-enabled: ручной старт, транзиентный
# запуск), не переключается автоматически — оператор делает хэндофф вручную.
if systemctl --user is-enabled hermes-vps-kit-config.path >/dev/null 2>&1 \
   || systemctl --user is-active hermes-vps-kit-config.path >/dev/null 2>&1; then
    echo "📡 Discover-вотчер: живой legacy hermes-vps-kit-config.path — оставляю его;"
    echo "   хэндофф на hermes-argus-config.path — вручную (см. вывод deploy.sh)."
elif systemctl --user list-unit-files | grep -q hermes-argus-config.path; then
    systemctl --user enable --now hermes-argus-config.path
    echo "📡 Discover-вотчер config.yaml включён (path unit + cron-страховка)."
fi

# ── 6. Post-deploy gates ────────────────────────────────────────────────────
echo ""
echo "🚦 Post-deploy gates:"

# B4 (RR1b): проверка payload'а живёт в deploy.sh — там единственном месте,
# где известны выбранные модули и фактические пути развёрнутых файлов.
# Bootstrap не дублирует ни список артефактов, ни таблицу дефолтов модулей:
# предыдущие версии гейта расходились с deploy и по дефолтам (не указанный
# флаг считался ON, хотя optional-модули по умолчанию OFF), и по охвату
# (рекурсивный grep целых каталогов цеплял чужую инфраструктуру и остатки
# отключённых модулей), и проверял один представитель на модуль.
#
# Здесь гейт fail-closed: отсутствие подтверждения означает, что проверка не
# отработала, и молчать об этом нельзя.
echo -n "   payload: "
if printf '%s\n' "$DEPLOY_OUT" | grep -q 'payload проверен:'; then
    echo "проверен deploy.sh (маркеры + синтаксис каждого развёрнутого файла)"
else
    echo "❌ deploy.sh не подтвердил проверку развёрнутого payload"
    exit 1
fi

echo ""
echo "🏁 Готово. Расписание установлено deploy.sh в managed-блоке"
echo "   $'# BEGIN HERMES-ARGUS / # END HERMES-ARGUS' вашего crontab —"
echo "   вручную добавлять cron-строки не нужно (ON→OFF модулей реконсилятся"
echo "   следующим deploy). Осталось вручную:"
echo "   1. Hermes должен быть установлен — health-check проверит ключи автоматически"
echo "      (/integrations all в боте, cron :20)."
echo "   2. Heartbeat-бекенды (опционально): CRONPING_TOKEN / DMS_SNITCH в ~/.hermes/.env"
echo "   3. Discord (опционально): MODULE_DISCORD_BOT=ON + DISCORD_BOT_TOKEN + intents"
echo "      в Developer Portal."
