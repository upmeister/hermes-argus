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
bash deploy.sh config.env

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

# B4 (RR1b): гейт следует ВЫБРАННЫМ модулям, а не только CORE.
#
# Значение модуля читается РОВНО так, как его читает deploy.sh — источником
# конфигурации в ПОД-шелле. Собственный разбор строки здесь недопустим: в
# штатном шаблоне `MODULE_CORE="OFF"   # комментарий` — это корректная строка
# с комментарием, и наивный парсер склеивал его со значением
# (`OFF#watchdog`), из-за чего CORE=OFF-установка требовала несуществующий
# watchdog. Секреты config.env при этом не попадают в окружение bootstrap'а:
# под-шелл с источником сразу завершается.
module_flag() {   # module_flag MODULE_CORE -> ON|OFF, как увидит deploy.sh
    ( set +e; set -a; . ./config.env >/dev/null 2>&1; set +a; printf '%s' "${!1:-ON}" )
}

module_on() { [ "$(module_flag "$1")" = "ON" ]; }

# Артефакт, который включённый модуль обязан оставить после deploy. Имена — те
# же, что в манифестах deploy.sh; это проверка «поставили то, что просили», а не
# новый реестр зависимостей (deploy_scripts сам падает на отсутствующем
# источнике манифеста).
module_artifact() {
    case "$1" in
        MODULE_CORE)            echo "$HOME/scripts/hermes-watchdog.sh" ;;
        MODULE_INTEGRATIONS)    echo "$HOME/scripts/integration-discover-wrapper.sh" ;;
        MODULE_ANALYZER)        echo "$HOME/.hermes/scripts/health-analyzer.py" ;;
        MODULE_HEARTBEAT)       echo "$HOME/scripts/heartbeat.sh" ;;
        MODULE_TG_BOT)          echo "$HOME/.hermes/scripts/monitoring-bot-poller.py" ;;
        MODULE_DISCORD_BOT)     echo "$HOME/scripts/discord-bot.py" ;;
        MODULE_LOCAL_SERVICES)  echo "$HOME/.hermes/scripts/service-status-snapshot.py" ;;
        *) echo "" ;;
    esac
}

echo -n "   маркеры: "
if grep -rn '@[A-Z_]*@' "$HOME/scripts/" "$HOME/.hermes/scripts/" 2>/dev/null | grep -q .; then
    echo "❌ Найдены незаменённые маркеры!"; exit 1
fi
echo "чисто"

CHECKED=""
for MODULE in MODULE_CORE MODULE_INTEGRATIONS MODULE_ANALYZER MODULE_HEARTBEAT \
             MODULE_TG_BOT MODULE_DISCORD_BOT MODULE_LOCAL_SERVICES; do
    module_on "$MODULE" || continue
    ARTIFACT="$(module_artifact "$MODULE")"
    [ -n "$ARTIFACT" ] || continue
    # Включённый модуль без своего артефакта — сбой развёртки, а не «модуль выключен».
    if [ ! -f "$ARTIFACT" ]; then
        echo "   ❌ $MODULE включён, но не развёрнут: $ARTIFACT"
        exit 1
    fi
    # Ошибка синтаксиса обязана ронять установку. В `bash -n ... && echo` левая
    # часть не прерывает `set -e`, и битый скрипт проходил гейт насквозь.
    case "$ARTIFACT" in
        *.sh)
            if ! bash -n "$ARTIFACT"; then
                echo "   ❌ синтаксис $ARTIFACT не прошёл проверку"
                exit 1
            fi
            ;;
        *.py)
            if ! python3 -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$ARTIFACT"; then
                echo "   ❌ синтаксис $ARTIFACT не прошёл проверку"
                exit 1
            fi
            ;;
    esac
    CHECKED="$CHECKED ${ARTIFACT##*/}"
done

if [ -n "$CHECKED" ]; then
    echo "   артефакты модулей:$CHECKED — ok"
else
    echo "   артефакты модулей: включённых модулей нет — проверка не требуется"
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
