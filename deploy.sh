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
# H1 (RR1b, host-readiness): конфиг несёт секреты (WATCHDOG_BOT_TOKEN), поэтому
# файл обязан быть обычным, принадлежать пользователю установки и не быть
# доступным группе/остальным. .gitignore защищает только от попадания в Git —
# права доступа он не проверяет. Значения конфига в диагностику не попадают:
# выводится только имя нарушенного свойства и команда починки.
assert_private_config() {
    local cfg="$1" owner mode
    if [ ! -f "$cfg" ]; then
        echo "❌ Конфиг $cfg не является обычным файлом (или отсутствует)." >&2
        echo "   Ожидается: $cfg — файл, созданный тобой." >&2
        return 1
    fi
    if ! owner=$(stat -c '%U' "$cfg" 2>/dev/null); then
        echo "❌ Не удалось определить владельца $cfg (нет stat?)." >&2
        return 1
    fi
    if [ "$owner" != "$(id -un)" ]; then
        echo "❌ Владелец $cfg — '$owner', а установка идёт от '$(id -un)'." >&2
        echo "   Починка: chown $(id -un) $cfg" >&2
        return 1
    fi
    mode=$(stat -c '%a' "$cfg" 2>/dev/null || true)
    # H1: недоступный режим = невозможно доказать безопасность = отказ.
    # Раньше пустая строка трактовалась как «ок», и сбой чтения прав делал
    # конфиг с секретами «безопасным».
    if [ -z "$mode" ]; then
        echo "❌ Не удалось определить режим доступа $cfg — доказательств, что" >&2
        echo "   файл не читается посторонними, нет." >&2
        return 1
    fi
    # group/other-биты = доступ посторонним к секретам в файле.
    if [ $(( 0$mode & 077 )) -ne 0 ]; then
        echo "❌ $cfg доступен группе/остальным (режим $mode)." >&2
        echo "   Починка: chmod 600 $cfg" >&2
        return 1
    fi
    return 0
}

if [ -f "$CONFIG_FILE" ]; then
    echo "📖 Загружаю конфигурацию: $CONFIG_FILE"
    assert_private_config "$CONFIG_FILE" || exit 1
    set -a; source "$CONFIG_FILE"; set +a
else
    echo "⚠️  config.env не найден ($CONFIG_FILE). Использую переменные окружения."
fi

# ── Значения по умолчанию ──────────────────────────────────────────────────
# H3 (RR1b): «цель должна быть задана» проверяется по СЫРОМУ значению из
# config.env, а не по подстановке дефолтов ниже — `${VAR:-…}` превращает
# явно пустой HERMES_HOST в 127.0.0.1, и проверка «непустой хост» была бы
# недостижимой ровно в том случае, когда она нужна.
RAW_HERMES_HOST="${HERMES_HOST-__UNSET__}"
RAW_HERMES_PORT="${HERMES_PORT-__UNSET__}"

HERMES_HOST="${HERMES_HOST:-127.0.0.1}"
HERMES_PORT="${HERMES_PORT:-9119}"
NETDATA_PORT="${NETDATA_PORT:-19999}"
WATCHDOG_CHAT_ID="${WATCHDOG_CHAT_ID:-}"
WATCHDOG_BOT_TOKEN="${WATCHDOG_BOT_TOKEN:-}"
BREAKER_MAX="${BREAKER_MAX:-3}"
DMS_SNITCH="${DMS_SNITCH:-change_me}"
GITHUB_REPO="${GITHUB_REPO:-}"

# ── Модули: deploy ставит только включённое ────────────────────────────────
# Всё, что требует внешних сервисов, — OFF по умолчанию (см. config.env.template).
MODULE_CORE="${MODULE_CORE:-ON}"
MODULE_INTEGRATIONS="${MODULE_INTEGRATIONS:-ON}"
MODULE_TG_BOT="${MODULE_TG_BOT:-OFF}"
MODULE_ANALYZER="${MODULE_ANALYZER:-OFF}"
MODULE_HEARTBEAT="${MODULE_HEARTBEAT:-OFF}"
MODULE_GH_HEARTBEAT="${MODULE_GH_HEARTBEAT:-OFF}"
MODULE_DISCORD_BOT="${MODULE_DISCORD_BOT:-OFF}"
MODULE_LOCAL_SERVICES="${MODULE_LOCAL_SERVICES:-OFF}"
# H4 (RR1b): сетевой guard — host-policy инструмент с неинтерактивным sudo на
# откат маршрутов/DNS. Это НЕ переносимая зависимость CORE: по умолчанию OFF,
# и только явный флаг делает его применимым на конкретном хосте.
MODULE_NETWORK_GUARD="${MODULE_NETWORK_GUARD:-OFF}"

module_enabled() { [ "${!1}" = "ON" ]; }

HOME_DIR="${HOME:-$HOME}"
HERMES_DIR="${HERMES_DIR:-$HOME_DIR/.hermes}"

# Модули, которые пишут или включают systemd USER-юниты. Их surface требует
# живого user-manager'а (H2).
module_needs_user_units() {
    module_enabled MODULE_CORE || module_enabled MODULE_INTEGRATIONS \
        || module_enabled MODULE_TG_BOT || module_enabled MODULE_DISCORD_BOT
}

# Модули, чей runtime использует интерпретатор Hermes venv (H3). Их юниты и
# скрипты исполняются этим интерпретатором: CORE (hermes-gateway-pids.py
# ре-exec'ится под ним), INTEGRATIONS (health-check читает конфиг Hermes),
# TG_BOT (monitoring-bot-poller.service стартует venv-питоном).
# DISCORD_BOT и LOCAL_SERVICES пользуются СВОИМ/системным python3 — требовать
# от них Hermes venv было бы выходом за контракт.
module_uses_hermes_venv() {
    module_enabled MODULE_CORE || module_enabled MODULE_INTEGRATIONS \
        || module_enabled MODULE_TG_BOT
}

echo "🔧 Развёртка hermes-argus"
echo "   Хост: $HERMES_HOST:$HERMES_PORT"
echo "   Hermes директория: $HERMES_DIR"
echo "   Модули: CORE=$(module_enabled MODULE_CORE && echo ON || echo OFF) INTEGRATIONS=$(module_enabled MODULE_INTEGRATIONS && echo ON || echo OFF) TG_BOT=$(module_enabled MODULE_TG_BOT && echo ON || echo OFF) ANALYZER=$(module_enabled MODULE_ANALYZER && echo ON || echo OFF) HEARTBEAT=$(module_enabled MODULE_HEARTBEAT && echo ON || echo OFF) GH_HEARTBEAT=$(module_enabled MODULE_GH_HEARTBEAT && echo ON || echo OFF) DISCORD_BOT=$(module_enabled MODULE_DISCORD_BOT && echo ON || echo OFF) LOCAL_SERVICES=$(module_enabled MODULE_LOCAL_SERVICES && echo ON || echo OFF) NETWORK_GUARD=$(module_enabled MODULE_NETWORK_GUARD && echo ON || echo OFF)"
echo ""

# ── Функция: развернуть bash-шаблон ──────────────────────────────────────
# Заменяет @МАРКЕРЫ@ на значения из конфига. Новый маркер = новая printf-строка.
SED_SCRIPT_TMP=""
# B4 (RR1b): развёрнутые payload'ы. deploy — единственное место, которое знает
# ВЫБРАННЫЕ модули и фактически куда положила каждый файл, поэтому проверка
# «поставлено то, что просили» живёт здесь, а не дублируется в bootstrap
# отдельным списком артефактов и собственной таблицей дефолтов.
DEPLOYED_PATHS=()
cleanup_sed_script() { [ -z "$SED_SCRIPT_TMP" ] || rm -f "$SED_SCRIPT_TMP"; }
trap cleanup_sed_script EXIT

deploy_template() {
    local src="$1"
    local dst="$2"
    local name="$3"

    mkdir -p "$(dirname "$dst")"

    # Значения замен (в т.ч. секреты) пишутся во временный sed-скрипт (mktemp =
    # 0600) и подаются через -f: в argv sed попадает только путь скрипта, не
    # значения. Порядок замен сохранён прежнему sed -e списку.
    SED_SCRIPT_TMP=$(mktemp)
    {
        printf 's/@HERMES_HOST@/%s/g\n' "$HERMES_HOST"
        printf 's/@HERMES_PORT@/%s/g\n' "$HERMES_PORT"
        printf 's|@HERMES_DIR@|%s|g\n' "$HERMES_DIR"
        printf 's|@HERMES_BIN@|%s|g\n' "$HERMES_DIR/hermes-agent/venv/bin/hermes"
        printf 's|@HOME_DIR@|%s|g\n' "$HOME_DIR"
        printf 's/@MODULE_INTEGRATIONS@/%s/g\n' "$(module_enabled MODULE_INTEGRATIONS && echo ON || echo OFF)"
        printf 's/@MODULE_ANALYZER@/%s/g\n' "$(module_enabled MODULE_ANALYZER && echo ON || echo OFF)"
        printf 's/@MODULE_TG_BOT@/%s/g\n' "$(module_enabled MODULE_TG_BOT && echo ON || echo OFF)"
        printf 's/@WATCHDOG_BOT_TOKEN@/%s/g\n' "$WATCHDOG_BOT_TOKEN"
        printf 's/@WATCHDOG_CHAT_ID@/%s/g\n' "$WATCHDOG_CHAT_ID"
        printf 's/@BREAKER_MAX@/%s/g\n' "$BREAKER_MAX"
        printf 's/@DMS_SNITCH@/%s/g\n' "$DMS_SNITCH"
        printf 's/@NETDATA_PORT@/%s/g\n' "$NETDATA_PORT"
        printf 's|@GITHUB_REPO@|%s|g\n' "$GITHUB_REPO"
        printf 's/@HOSTNAME@/%s/g\n' "$(hostname)"
    } > "$SED_SCRIPT_TMP"

    sed -f "$SED_SCRIPT_TMP" "$src" > "$dst"
    cleanup_sed_script
    SED_SCRIPT_TMP=""

    # Делаем исполняемым если исходник был
    [ -x "$src" ] && chmod +x "$dst"

    DEPLOYED_PATHS+=("$dst")
    echo "   ✅ $name → $dst"
}

# ── Preflight хоста (RR1b, host-readiness) ───────────────────────────────────
# Всё fail-closed и ДО развёртки: цена ложно-зелёной «успешной» установки выше
# цены остановки с одной понятной строкой. Ничего здесь не мутирует: маршруты,
# DNS, интерфейсы, sudoers и linger не трогаются, Hermes не ставится и не
# запускается. Модульный список и дефолты — те же, что у развёртки ниже.

# H3 — цель liveness: непустой хост и целочисленный порт 1..65535.
# Пустое значение, заданное оператором ОСОЗНАННО, ошибка, а не повод молча
# подставить дефолт (иначе опечатка в конфиге выглядит как рабочая установка).
# Десятичный домен ограничен длиной ДО арифметики: `[ 9223… -lt 1 ]` на
# переполнении печатает «integer expected», но не делает условие ложным.
preflight_target() {
    local ok=1
    if [ "$RAW_HERMES_HOST" = "__UNSET__" ]; then
        : # не задан вовсе — работает дефолт, это штатный путь
    elif [ -z "$RAW_HERMES_HOST" ]; then
        echo "❌ HERMES_HOST задан пустым — цель liveness не определена." >&2
        ok=0
    fi
    if [ "$RAW_HERMES_PORT" != "__UNSET__" ]; then
        if ! [[ "$RAW_HERMES_PORT" =~ ^[0-9]{1,5}$ ]]; then
            echo "❌ HERMES_PORT='$RAW_HERMES_PORT' — ожидалось целое 1..65535." >&2
            ok=0
        elif [ "$RAW_HERMES_PORT" -lt 1 ] || [ "$RAW_HERMES_PORT" -gt 65535 ]; then
            echo "❌ HERMES_PORT='$RAW_HERMES_PORT' — вне диапазона 1..65535." >&2
            ok=0
        fi
    fi
    if [ "$ok" -ne 1 ]; then
        echo "   Починка: задай HERMES_HOST и HERMES_PORT в config.env." >&2
        return 1
    fi
}

# H3 — Hermes venv для модулей, чей runtime его реально использует.
# Argus наблюдает существующий Hermes и не имеет права его чинить.
# Проверяется не только `-x`: исполняемый бит не доказывает, что интерпретатор
# работает, поэтомуCapability проверяется безобидным запуском.
preflight_hermes() {
    module_uses_hermes_venv || return 0
    local names="" m bindir ok=1 out
    for m in MODULE_CORE MODULE_INTEGRATIONS MODULE_TG_BOT; do
        module_enabled "$m" && names="$names ${m#MODULE_}"
    done
    bindir="$HERMES_DIR/hermes-agent/venv/bin"
    [ -d "$HERMES_DIR/hermes-agent" ] || {
        echo "❌ Не найден $HERMES_DIR/hermes-agent (модули:$names)." >&2; ok=0; }
    if [ "$ok" -eq 1 ]; then
        [ -x "$bindir/python" ] || {
            echo "❌ Интерпретатор Hermes $bindir/python отсутствует или не исполняем (модули:$names)." >&2
            ok=0; }
        [ -x "$bindir/hermes" ] || {
            echo "❌ Hermes-исполняемый $bindir/hermes отсутствует или не исполняем (модули:$names)." >&2
            ok=0; }
        if [ "$ok" -eq 1 ] \
           && ! out=$("$bindir/python" -c 'import sys; sys.exit(0)' 2>&1); then
            echo "❌ Интерпретатор Hermes не работает: $bindir/python → ${out:-нет вывода}" >&2
            echo "   (модули:$names)" >&2
            ok=0
        fi
    fi
    if [ "$ok" -ne 1 ]; then
        echo "   Argus не устанавливает Hermes. Поставь его своим штатным" >&2
        echo "   workflow и повтори deploy." >&2
        return 1
    fi
}

# H2 — доступность user-manager'а и честный статус персистентности.
preflight_user_manager() {
    module_needs_user_units || return 0
    if ! systemctl --user show-environment >/dev/null 2>&1; then
        echo "❌ Недоступен systemd user-manager (нет user bus / XDG_RUNTIME_DIR)." >&2
        echo "   Argus ставит user-юниты; без менеджера они не стартуют." >&2
        echo "   Починка: выполняй в сессии пользователя с systemd-logind." >&2
        return 1
    fi
    local linger
    linger=$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)
    case "$linger" in
        yes) echo "   linger: yes — user-юниты переживут logout и reboot." ;;
        no)
            echo "❌ linger выключен — user-юниты не переживут logout/reboot." >&2
            echo "   Argus НЕ включает linger сам. Ручная починка:" >&2
            echo "     sudo loginctl enable-linger $(id -un)" >&2
            return 1
            ;;
        *) echo "   ⚠️  Состояние linger определить не удалось — персистентность" >&2
           echo "       после reboot НЕ гарантируется (проверь loginctl)." >&2 ;;
    esac
}

# H4 — применимость сетевого guard'а. Ни один откат при проверке не выполняется:
# `sudo -n -l <команда> <аргументы>` ТОЛЬКО перечисляет, каким правилом была бы
# исполнена эта команда с этими аргументами, и завершается ошибкой, если она
# запрещена. Это единственный надёжный способ связать NOPASSWD/run-as/отрицание
# именно с той командой, которую вызовет guard: разбор текста sudoers регэкспом
# путает смешанные теги в одной строке, run-as `(nobody)` и правила `!команда`,
# и ничего не говорит о грантах, ограниченных конкретными аргументами.
#
# Аргументы зондирующих вызовов нужны только для сопоставления с шаблоном
# sudoers и НЕ исполняются. Два из них выбраны заведомо не «узкими»: грант под
# одно конкретное число покрыл бы зонд, но guard снимает правила, обнаруженные
# в рантайме, поэтому достаточен только грант по маске.
preflight_network_guard() {
    module_enabled MODULE_NETWORK_GUARD || return 0
    local cmd ok=1
    for cmd in resolvectl ip sudo; do
        command -v "$cmd" >/dev/null 2>&1 || {
            echo "❌ Команда '$cmd' не найдена — guard её использует." >&2; ok=0; }
    done
    [ "$ok" -eq 1 ] || {
        echo "   Починка: поставь недостающее ПО или выключи MODULE_NETWORK_GUARD." >&2
        return 1; }

    local RESOLVECTL IP primary probe cmd_path args out
    RESOLVECTL=$(command -v resolvectl)
    IP=$(command -v ip)
    primary=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
    [ -n "$primary" ] || primary="lo"

    # (команда|аргументы) в том виде, в каком их зовёт network-guard.sh.
    # Таблица/преф — максимальные значения домена: грант под одно конкретное
    # число покрыл бы зонд, но не покрыл бы реальные цели guard'а.
    for probe in         "$RESOLVECTL|revert $primary"         "$IP|route flush table 4294967295"         "$IP|rule del pref 4294967295"; do
        cmd_path="${probe%%|*}"
        args="${probe#*|}"
        # shellcheck disable=SC2086 — args преднамеренно разбивается на слова
        if ! out=$(sudo -n -l "$cmd_path" $args 2>&1); then
            echo "❌ Отказ: guard не сможет исполнить '$(basename "$cmd_path") $args'" >&2
            echo "   (sudo -n -l: не разрешено, запрещено правилом ! или требует пароль)" >&2
            ok=0
        elif ! printf '%s
' "$out" | grep -q 'NOPASSWD'; then
            echo "❌ Отказ: '$(basename "$cmd_path") $args' разрешён С паролем (PASSWD)" >&2
            echo "   в cron вводить пароль некому — откат молча не сработает" >&2
            ok=0
        fi
    done
    if [ "$ok" -ne 1 ]; then
        echo "   Нужен NOPASSWD ровно на эти команды и формы аргументов:" >&2
        echo "     <user> ALL=(root) NOPASSWD: /usr/bin/resolvectl revert *, /usr/sbin/ip route flush table *, /usr/sbin/ip rule del *" >&2
        echo "   Argus не правит sudoers и не исполняет откат при проверке." >&2
        echo "   Альтернатива: MODULE_NETWORK_GUARD=OFF." >&2
        return 1
    fi
    echo "   сетевой guard: sudo -n -l подтвердил NOPASSWD по всем трём откатам (исполнения не было)."
}

# H5 — Argus-owned политика ротации файловых логов. Использует уже стоящий на
# хосте logrotate: второй планировщик или «служба» не появляются.
#
# Область действия — ЯВНЫЙ список файлов Argus, а не `logs/*.log`: каталог
# логов делит Argus с Hermes, и его agent.log/gateway.log — собственность
# Hermes, которую Argus только читает. Наложение ретенции/copytruncate на них
# было бы выходом за ownership.
ARGUS_LOG_FILES=(argus.log auto-remediate.log dashboard-liveness.log \
                 fallback-tracker-v2.log gateway-liveness.log health-analyzer.log \
                 health-check-v2.log heartbeat.log integration-discover.log \
                 integration-discover-cron.log local-services.log network-guard.log \
                 network-guard-cron.log service-status.log ssl-expiry.log \
                 ssl-expiry-cron.log watchdog.log watchdog-cron.log \
                 watchdog-health.log watchdog-health-cron.log)
LOGROTATE_POLICY_NAME="argus-logrotate.conf"
# Каталог планировщика logrotate. Дефолт — контрактный /etc/logrotate.d;
# переопределяется окружением для интеграционных тестов и нестандартных
# раскладок хоста (путь, не поведение).
LOGROTATE_SCHED_DIR="${LOGROTATE_SCHED_DIR:-/etc/logrotate.d}"

# Преflight ДО любых записей: контракт требует остановиться с инструкцией
# ремонта, если существующий механизм хоста не может активировать политику.
# Раньше проверка была в install_logrotate_policy — после записи юнитов.
logrotate_policy_body() {
    # Содержимое политики печатается в stdout: один источник для преflight-парса
    # и для финальной записи, иначе проверка и установка могли бы разойтись.
    local f body=""
    for f in "${ARGUS_LOG_FILES[@]}"; do
        body+="$HERMES_DIR/logs/$f"$'
'
    done
    local grp su_line=""
    if grp=$(id -gn 2>/dev/null); then su_line="    su $(id -un) $grp"; fi
    # daily + maxsize: maxsize не отменяет периодическую ротацию, а лишь
    # срабатывает раньше при переполнении (size после daily отменил бы daily).
    # copytruncate — логи дописываются работающим процессом, переименование их
    # не освободит.
    cat <<EOF
# hermes-argus — ротация ТОЛЬКО файловых логов Argus (RR1b).
# Создаётся deploy.sh; systemd-журналы, логи Hermes (agent.log, gateway.log)
# и чужие /var/log не входят. Перечень — явный, не глоб-маска.
$body{
    daily
    rotate 7
    maxsize 50M
    compress
    delaycompress
    copytruncate
    missingok
    notifempty
$su_line
}
EOF
}

preflight_logrotate() {
    if ! command -v logrotate >/dev/null 2>&1; then
        echo "❌ logrotate не найден — файловые логи Argus росли бы без границы." >&2
        echo "   Починка: sudo apt-get install -y logrotate" >&2
        return 1
    fi
    if [ -d "$LOGROTATE_SCHED_DIR" ] && [ -w "$LOGROTATE_SCHED_DIR" ]; then
        :
    # Незаписываемый каталог — нормальная ситуация для обычного пользователя.
    # Достаточно неинтерактивного sudo для install: проверяется безобидным
    # `--help`, который ничего не пишет.
    elif sudo -n install --help >/dev/null 2>&1; then
        echo "   logrotate: $LOGROTATE_SCHED_DIR не записываем — активация через sudo install"
    else
        echo "❌ $LOGROTATE_SCHED_DIR недоступна для записи и неинтерактивного sudo" >&2
        echo "   для install нет — политика не будет активирована в планировщике хоста." >&2
        echo "   Починка (одна из):" >&2
        echo "     sudo install -d -o $(id -un) -g $(id -gn) $LOGROTATE_SCHED_DIR" >&2
        echo "     выполнить deploy от root" >&2
        echo "   Argus не повышает привилегии сам и не правит sudoers." >&2
        return 1
    fi
    # Парсер прогоняется ЗДЕСЬ, до любых записей deploy'а: иначе неисправный
    # logrotate обнаруживался после того, как юниты уже записаны.
    local tmp err
    tmp=$(mktemp)
    logrotate_policy_body > "$tmp"
    chmod 0600 "$tmp"
    if ! err=$(logrotate --debug --state /dev/null "$tmp" 2>&1); then
        echo "❌ Политика не проходит парсер logrotate: $err" >&2
        rm -f "$tmp"
        return 1
    fi
    rm -f "$tmp"
}

install_logrotate_policy() {
    local policy="$HERMES_DIR/$LOGROTATE_POLICY_NAME" target="$LOGROTATE_SCHED_DIR/argus"
    mkdir -p "$HERMES_DIR/logs"
    # Содержимое уже проверено парсером в преflight; здесь только запись и
    # активация, применимость которых тоже доказана преflight'ом.
    logrotate_policy_body > "$policy"
    chmod 0644 "$policy"
    DEPLOYED_PATHS+=("$policy")
    if [ -w "$LOGROTATE_SCHED_DIR" ]; then
        if ! cp "$policy" "$target"; then
            echo "❌ Не удалось активировать политику: $target" >&2
            return 1
        fi
    elif ! sudo -n install -m 0644 "$policy" "$target" 2>/dev/null; then
        echo "❌ Не удалось активировать политику: $target" >&2
        echo "   Преflight допускал sudo install, но фактическая активация не удалась." >&2
        return 1
    fi
    chmod 0644 "$target" 2>/dev/null || true
}

echo ""
echo "🔎 Preflight хоста..."
preflight_target || exit 1
preflight_hermes || exit 1
preflight_user_manager || exit 1
preflight_network_guard || exit 1
preflight_logrotate || exit 1

# ── Манифесты модулей (ЯВНЫЕ списки — в целевых каталогах лежит и чужая
#    инфраструктура, wildcard-раскладка по каталогу запрещена) ──────────────

# CORE: локальный мониторинг и самозащита (внешнее — только TG-алерты)
# hermes-gateway-pids.py — канонический матчер живости gateway, зовётся
# hermes-watchdog.sh и gateway-liveness.sh; без него оба считают gateway
# мёртвым (или, наоборот, молча пропускают проверку). Идёт в $HOME_DIR/scripts.
# B2 (RR1b): collect-metrics.sh уехал в ANALYZER — единственный его потребитель
# health-analyzer.py; в CORE он жил вторым экземпляром в неканоническом пути.
CORE_HOME_SCRIPTS=(hermes-watchdog.sh hermes-gateway-pids.py auto-remediate.sh \
                   check-updates.sh)
CORE_HERMES_SCRIPTS=(dashboard-liveness.sh gateway-liveness.sh watchdog-health.sh ssl-expiry-check.sh)

# NETWORK_GUARD (H4, RR1b): хост-политика маршрутов/DNS с неинтерактивным sudo
# на откат. Это НЕ переносимая зависимость CORE: guard кодирует политику
# конкретной машины, поэтому вынесен из CORE в отдельный флаг, OFF по умолчанию.
NETWORK_GUARD_HOME_SCRIPTS=(network-guard.sh)

# LOCAL_SERVICES: opt-in сборщик снимка + консьюмер (манифест, гистерезис,
# алерты). UI/клавиатура — при MODULE_TG_BOT; переключение в /settings.
LOCAL_SERVICES_HERMES_SCRIPTS=(service-status-snapshot.py local_services_check.py)
CORE_SYSTEMD=(hermes-dashboard.service hermes-dashboard.service.d/memory-limits.conf \
              hermes-gateway.service hermes-gateway.service.d/memory-limits.conf)

# INTEGRATIONS: discover конфига + каскад-трекер фолбека + health-check v2 (ядро Argus v2)
INTEGRATIONS_HOME_SCRIPTS=(integration-discover.py integration-discover-wrapper.sh fallback-tracker-v2.py \
                           health-check-v2.py health-check-v2-wrapper.sh)
INTEGRATIONS_HERMES_SCRIPTS=(health-check-integrations.sh)
# RR0c (B3): канонические имена юнитов нового образца — Argus-owned. Легаси
# hermes-vps-kit-* на живой машине не трогаются и не мигрируют автоматически:
# deploy ставит канонические файлы рядом и печатает оператору хэндофф-команды
# (одна активная пара producer'ов в каждый момент времени; в окно миграции
# discovery продолжает работать через legacy-юнит и cron-страховку).
INTEGRATIONS_SYSTEMD=(hermes-argus-config.path hermes-argus-discover.service)

# SHARED: webhook.py — библиотека handlers'ов, общая для обоих ботов.
# Владеет ею SHARED, а не TG_BOT (B3, RR1b): discord-bot.py делает `import
# webhook` и брал файл из ~/scripts, который ставился только TG_BOT, поэтому
# MODULE_DISCORD_BOT=ON без TG_BOT зависел от старой установленной копии.
# Два бота — два control plane, но библиотека handlers'ов у них одна.
SHARED_BOT_HOME_SCRIPTS=(webhook.py)

# TG_BOT: интерактивный мониторинг-бот (control plane) — OFF по умолчанию.
# webhook.py в $HOME_DIR/scripts ставит SHARED выше; в ~/.hermes/scripts копия
# остаётся своей (poller импортирует её из своего каталога — урок 2026-09-07:
# частичный деплой оставлял свежую и старую копии, AttributeError на import).
TG_BOT_HOME_SCRIPTS=(ai-deep-check.py register-commands.sh)
TG_BOT_HERMES_SCRIPTS=(monitoring-bot-poller.py webhook.py)
TG_BOT_SYSTEMD=(monitoring-bot-poller.service)

# DISCORD_BOT: control plane для Discord (C5) — OFF по умолчанию
DISCORD_HOME_SCRIPTS=(discord-bot.py)
DISCORD_SYSTEMD=(discord-bot.service)

# ANALYZER: L3 health-analyzer экосистема (LLM-анализ логов) — OFF по умолчанию
# B2 (RR1b): collect-metrics.sh — канонический путь ~/.hermes/scripts/, ровно
# тот, который читает health-analyzer.py. Ставит его модуль-потребитель.
ANALYZER_HERMES_SCRIPTS=(health-analyzer.py health_decay.py health_patterns.py health_netdata.py \
                         collect-metrics.sh)

# HEARTBEAT: внешний dead man's switch (DMS / GitHub Heartbeat) — OFF по умолчанию
HEARTBEAT_HOME_SCRIPTS=(heartbeat.sh)

# ── Функции развёртки ──────────────────────────────────────────────────────

LOCAL_SERVICES_CRON_LINE="*/5 * * * * python3 $HERMES_DIR/scripts/service-status-snapshot.py --quiet >> $HERMES_DIR/logs/service-status.log 2>&1; /bin/bash -c 'set -a; source $HERMES_DIR/.env; set +a; export MODULE_LOCAL_SERVICES=\${MODULE_LOCAL_SERVICES:-ON}; python3 $HERMES_DIR/scripts/local_services_check.py' >> $HERMES_DIR/logs/local-services.log 2>&1"

# ── RR1a: единый managed cron-блок (единственный writer расписания) ─────────
# Исторически deploy.sh только ПЕЧАТАЛ cron-строки и просил оператора
# устанавливать их вручную; единственным живым writer'ом был узкий
# local-services reconciliation (контракт docs PR #55). RR1a вводит ОДИН
# управляемый блок «# BEGIN/END HERMES-ARGUS» в crontab вызывающего юзера:
# deploy читает crontab, заменяет только свой блок (плюс однократное adoption
# известных ранее сгенерированных форм), посторонние строки/комментарии/env
# не трогает. Сбой чтения/записи/разметки — fail closed: deploy прерывается,
# установленное расписание не меняется. Cron выполняет команды через /bin/sh:
# команды, требующие bash, явно зовут /bin/bash -c (значения .env не грузятся
# «source'ом» голым sh). Значения креденшелов в cron-строках запрещены.
# ВАЖНО (provenance инцидента local-services): cron-`source` под dash молча
# не работает — с `source` в cron доставка 0, с `/bin/bash -c` — ок.
CRON_BLOCK_BEGIN="# BEGIN HERMES-ARGUS"
CRON_BLOCK_END="# END HERMES-ARGUS"
CRON_LOCK_FILE="${CRON_LOCK_FILE:-/tmp/hermes-argus-cron.lock}"

# Известные ранее сгенерированные формы (adoption). Совпадение — ТОЛЬКО полная
# строка (расписание+путь+аргументы+редирект), подстрока по basename не есть
# доказательство владения. Допускаются два установленных написания путей:
# абсолютный $HOME_DIR и «~/» (нормализация до сравнения).
is_known_generated_form() {
    local l="$1"
    case "$l" in
        "*/5 * * * * $HOME_DIR/scripts/hermes-watchdog.sh >> $HERMES_DIR/logs/watchdog-cron.log 2>&1") return 0 ;;
        "*/2 * * * * $HOME_DIR/scripts/network-guard.sh >> $HERMES_DIR/logs/network-guard-cron.log 2>&1") return 0 ;;
        "*/2 * * * * $HERMES_DIR/scripts/gateway-liveness.sh >> $HERMES_DIR/logs/gateway-liveness.log 2>&1") return 0 ;;
        "*/5 * * * * $HERMES_DIR/scripts/dashboard-liveness.sh >> $HERMES_DIR/logs/dashboard-liveness.log 2>&1") return 0 ;;
        "*/10 * * * * $HOME_DIR/scripts/auto-remediate.sh >> $HERMES_DIR/logs/auto-remediate.log 2>&1") return 0 ;;
        "0 3 * * 1 $HOME_DIR/scripts/check-updates.sh") return 0 ;;
        "30 * * * * $HERMES_DIR/scripts/watchdog-health.sh >> $HERMES_DIR/logs/watchdog-health-cron.log 2>&1") return 0 ;;
        "0 6 * * * $HERMES_DIR/scripts/ssl-expiry-check.sh >> $HERMES_DIR/logs/ssl-expiry-cron.log 2>&1") return 0 ;;
        "*/10 * * * * $HOME_DIR/scripts/integration-discover-wrapper.sh >> $HERMES_DIR/logs/integration-discover-cron.log 2>&1") return 0 ;;
        "*/5 * * * * python3 $HOME_DIR/scripts/fallback-tracker-v2.py >> $HERMES_DIR/logs/fallback-tracker-v2.log 2>&1") return 0 ;;
        "20 * * * * $HOME_DIR/scripts/health-check-v2-wrapper.sh >> $HERMES_DIR/logs/health-check-v2.log 2>&1") return 0 ;;
        "5 * * * * cd $HERMES_DIR/scripts && python3 health-analyzer.py --update >> $HERMES_DIR/logs/health-analyzer.log 2>&1") return 0 ;;
        # Легаси-форма heartbeat: генерировалась до RR1a с голым `source`
        # (молча не работал под /bin/sh); заменяется формой с /bin/bash -c.
        "*/5 * * * * set -a; source $HERMES_DIR/.env; set +a; $HOME_DIR/scripts/heartbeat.sh >> $HERMES_DIR/logs/heartbeat.log 2>&1") return 0 ;;
        "*/5 * * * * /bin/bash -c 'set -a; source $HERMES_DIR/.env; set +a; exec $HOME_DIR/scripts/heartbeat.sh' >> $HERMES_DIR/logs/heartbeat.log 2>&1") return 0 ;;
        # LOCAL_SERVICES: producer-only форма (миграционные пробы PR #55) и
        # комбинированные формы, которые ставил baseline-deploy: bare-source
        # (до f99eee3) и bash-форма (после). Без них ON дал бы два job'а, а
        # OFF оставил бы старый работать вне блока.
        "*/5 * * * * python3 $HERMES_DIR/scripts/service-status-snapshot.py --quiet >> $HERMES_DIR/logs/service-status.log 2>&1") return 0 ;;
        "$LOCAL_SERVICES_CRON_LINE") return 0 ;;
        "*/5 * * * * python3 $HERMES_DIR/scripts/service-status-snapshot.py --quiet >> $HERMES_DIR/logs/service-status.log 2>&1; set -a; source $HERMES_DIR/.env; set +a; python3 $HERMES_DIR/scripts/local_services_check.py >> $HERMES_DIR/logs/local-services.log 2>&1") return 0 ;;
        *) return 1 ;;
    esac
}

reconcile_argus_cron() {
    local crontab_tmp desired_tmp read_err line
    local in_block=0 saw_block=0 phase="before"
    local begin_count end_count adopted=0 ambiguous=0
    local before="" after="" kept="" norm_line
    if ! command -v crontab >/dev/null 2>&1; then
        echo "   🚨 crontab недоступен — reconciliation managed-блока невозможен, fail closed" >&2
        return 1
    fi
    exec 9>"$CRON_LOCK_FILE"
    if ! flock -n 9; then
        echo "   🚨 crontab: параллельный deploy уже выполняет reconciliation (lock: $CRON_LOCK_FILE) — repeat later" >&2
        return 1
    fi
    crontab_tmp=$(mktemp); desired_tmp=$(mktemp); read_err=$(mktemp)
    # Чтение в файл (не в переменную): переводы строк сохраняются байт-в-байт.
    # «нет crontab» — валидный пустой стейт; прочий сбой — fail closed.
    if ! crontab -l >"$crontab_tmp" 2>"$read_err"; then
        if grep -q "no crontab for" "$read_err"; then
            : > "$crontab_tmp"
        else
            echo "   🚨 crontab -l завершился с неопознанной ошибкой — не трактую как пустой crontab, fail closed" >&2
            rm -f "$crontab_tmp" "$desired_tmp" "$read_err"
            return 1
        fi
    fi
    rm -f "$read_err"

    begin_count=$(grep -Fxc "$CRON_BLOCK_BEGIN" "$crontab_tmp" || true)
    end_count=$(grep -Fxc "$CRON_BLOCK_END" "$crontab_tmp" || true)
    if [ "$begin_count" -gt 1 ] || [ "$end_count" -gt 1 ]; then
        echo "   🚨 crontab: несколько маркеров managed-блока (BEGIN=$begin_count END=$end_count) — исправь разметку вручную, deploy прерван" >&2
        rm -f "$crontab_tmp" "$desired_tmp"
        return 1
    fi
    if [ "$begin_count" -ne "$end_count" ]; then
        echo "   🚨 crontab: незакрытый managed-блок (BEGIN=$begin_count END=$end_count) — исправь разметку вручную, deploy прерван" >&2
        rm -f "$crontab_tmp" "$desired_tmp"
        return 1
    fi

    # Разбор: строки вне блока сохраняются дословно (комментарии, пустые строки,
    # env-объявления) СОХРАНЯЯ ПОЗИЦИЮ относительно блока — cron-переменные
    # действуют на последующие задания, перенос блока в конец недопустим.
    while IFS= read -r line || [ -n "$line" ]; do
        if [ "$line" = "$CRON_BLOCK_BEGIN" ]; then
            in_block=1
            saw_block=1
            continue
        fi
        if [ "$line" = "$CRON_BLOCK_END" ]; then
            in_block=0
            phase="after"
            continue
        fi
        if [ "$in_block" -eq 0 ]; then
            if [ "$phase" = "before" ]; then
                before+="$line"$'
'
            else
                after+="$line"$'
'
            fi
        fi
    done < "$crontab_tmp"
    if [ "$in_block" -ne 0 ]; then
        echo "   🚨 crontab: BEGIN без END (перевёрнутая/незакрытая разметка) — исправь вручную, deploy прерван" >&2
        rm -f "$crontab_tmp" "$desired_tmp"
        return 1
    fi

    # Adoption (однократно, только при отсутствии блока): известные ранее
    # сгенерированные формы уходят в управляемый блок; чужие/кастомные строки
    # сохраняются. Имена наших скриптов в сохранённых строках — счётчиком,
    # без печати сырого текста команд.
    if [ "$saw_block" -eq 0 ] && [ -s "$crontab_tmp" ]; then
        while IFS= read -r line || [ -n "$line" ]; do
            if [ -n "$line" ]; then
                norm_line=${line//'~/'/"$HOME_DIR/"}
                if is_known_generated_form "$norm_line"; then
                    adopted=$((adopted + 1))
                    continue
                fi
                case "$norm_line" in
                    *hermes-watchdog.sh*|*network-guard.sh*|*gateway-liveness.sh*|*dashboard-liveness.sh*|*auto-remediate.sh*|*check-updates.sh*|*watchdog-health.sh*|*ssl-expiry-check.sh*|*integration-discover-wrapper.sh*|*fallback-tracker-v2.py*|*health-check-v2-wrapper.sh*|*health-analyzer.py*|*heartbeat.sh*|*service-status-snapshot.py*|*local_services_check.py*)
                        ambiguous=$((ambiguous + 1)) ;;
                esac
            fi
            kept+="$line"$'
'
        done < "$crontab_tmp"
        before="$kept"
        after=""
    fi

    # Композиция: при существующем блоке — замена НА ПРЕЖНЕМ МЕСТЕ (cron-env
    # до блока продолжают действовать на него); при первом создании блок
    # добавляется в конец, порядок сохранённых строк не меняется.
    : > "$desired_tmp"
    printf '%s' "$before" >> "$desired_tmp"
    if [ "$saw_block" -eq 1 ] && [ -n "$SCHEDULE" ]; then
        printf '%s\n' "$CRON_BLOCK_BEGIN" >> "$desired_tmp"
        printf '%s' "$SCHEDULE" >> "$desired_tmp"
        printf '%s\n' "$CRON_BLOCK_END" >> "$desired_tmp"
    fi
    printf '%s' "$after" >> "$desired_tmp"
    if [ "$saw_block" -eq 0 ] && [ -n "$SCHEDULE" ]; then
        printf '%s\n' "$CRON_BLOCK_BEGIN" >> "$desired_tmp"
        printf '%s' "$SCHEDULE" >> "$desired_tmp"
        printf '%s\n' "$CRON_BLOCK_END" >> "$desired_tmp"
    fi

    if cmp -s "$crontab_tmp" "$desired_tmp"; then
        echo "   🕒 crontab: managed-блок актуален, изменений нет"
        rm -f "$crontab_tmp" "$desired_tmp"
        return 0
    fi
    if ! crontab - <"$desired_tmp" 2>/dev/null; then
        echo "   🚨 не удалось записать crontab — fail closed, deploy прерван" >&2
        rm -f "$crontab_tmp" "$desired_tmp"
        return 1
    fi
    rm -f "$crontab_tmp" "$desired_tmp"
    local block_jobs=0
    if [ -n "$SCHEDULE" ]; then
        block_jobs=$(printf '%s' "$SCHEDULE" | grep -c . || true)
    fi
    echo "   🕒 crontab: managed-блок $CRON_BLOCK_BEGIN / $CRON_BLOCK_END записан (job'ов: $block_jobs, принято легаси-строк: $adopted)"
    if [ "$ambiguous" -gt 0 ]; then
        echo "   ℹ️  crontab: сохранено $ambiguous строк(и) с именами скриптов Argus вне известных сгенерированных форм — оставлены оператору без изменений"
    fi
    return 0
}

deploy_scripts() {
    local dest_dir="$1"; shift
    local script
    for script in "$@"; do
        # B4 (RR1b): манифест — это обещание развернуть артефакт. Отсутствие
        # источника в манифесте означает, что включённый модуль останется без
        # своего файла; молчаливый skip давал «успешный» deploy без payload и
        # ронял гейт bootstrap'а уже после того, как отчёт об успехе напечатан.
        if [ ! -f "$SCRIPTS_DIR/$script" ]; then
            echo "   ❌ Манифест требует $script, но его нет в $SCRIPTS_DIR" >&2
            return 1
        fi
        deploy_template "$SCRIPTS_DIR/$script" "$dest_dir/$script" "$script"
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

# ── Проверка развёрнутого payload (RR1b, B4) ────────────────────────────────
# Проверяются РОВНО те файлы, которые deploy положил по манифестам включённых
# модулей: ни чужая инфраструктура в целевых каталогах, ни остатки отключённых
# модулей сюда не попадают. Проверяется всё, а не один представитель на модуль.
verify_deployed_payload() {
    local f bad=0
    echo ""
    echo "🔎 Проверка развёрнутого payload..."
    for f in ${DEPLOYED_PATHS[@]+"${DEPLOYED_PATHS[@]}"}; do
        if [ ! -f "$f" ]; then
            echo "   ❌ файл не создан: $f"; bad=1; continue
        fi
        if grep -q '@[A-Z_]*@' "$f" 2>/dev/null; then
            echo "   ❌ незаменённые маркеры: $f"; bad=1
        fi
        case "$f" in
            *.sh)
                if ! bash -n "$f" 2>/dev/null; then
                    echo "   ❌ ошибка синтаксиса: $f"; bad=1
                fi
                ;;
            *.py)
                if ! python3 -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$f" 2>/dev/null; then
                    echo "   ❌ ошибка синтаксиса: $f"; bad=1
                fi
                ;;
        esac
    done
    if [ "$bad" -ne 0 ]; then
        echo "   ❌ payload не прошёл проверку — развёртка считается неуспешной."
        return 1
    fi
    echo "   ✅ payload проверен: ${#DEPLOYED_PATHS[@]} файл(ов), маркеров и синтаксических ошибок нет"
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
    # RR0c (B3): детекция legacy-вотчера — канонические юниты ставятся файлами,
    # но активным остаётся legacy; переключает ТОЛЬКО оператор (ниже команды).
    if [ -f "$HOME_DIR/.config/systemd/user/hermes-vps-kit-config.path" ]; then
        echo "   ⚠️  Обнаружен legacy-вотчер hermes-vps-kit-config.path (активный producer не меняю)."
        echo "      Ручной хэндофф на канонические имена (в удобное окно):"
        echo "        systemctl --user disable --now hermes-vps-kit-config.path"
        echo "        systemctl --user enable --now hermes-argus-config.path"
    fi
    if [ -f "$REPO_DIR/registry.yaml" ]; then
        deploy_template "$REPO_DIR/registry.yaml" "$HERMES_DIR/state/registry.yaml" "registry.yaml"
    fi
fi

if module_enabled MODULE_LOCAL_SERVICES; then
    echo ""
    echo "📁 [LOCAL_SERVICES] локальный снимок топологии + консьюмер..."
    deploy_scripts "$HERMES_DIR/scripts" "${LOCAL_SERVICES_HERMES_SCRIPTS[@]}"
    # RR1a: расписание ставит общий managed-блок в секции cron ниже;
    # начальный сбор выполняется сразу после успешного reconciliation.
else
    # OFF: расписание снимает общий managed-блок (секция cron ниже).
# Установленные скрипты остаются, но без флага они no-op,
    # а старый снимок читается как unknown (все читатели закрыты флагом).
    :
fi

# H4 (RR1b): сетевой guard ставится и планируется ТОЛЬКО при явном флаге.
# При OFF свежая установка не разворачивает файл (остаток от старой
# развёртки может лежать, но он не ставится в cron и не активен).
if module_enabled MODULE_NETWORK_GUARD; then
    echo ""
    echo "📁 [NETWORK_GUARD] откат сетевых инвариантов (host-policy)..."
    deploy_scripts "$HOME_DIR/scripts" "${NETWORK_GUARD_HOME_SCRIPTS[@]}"
    echo "   ℹ️  Откат выполняется только при нарушении инвариантов и только"
    echo "      командами, проверенными в preflight (маршруты/DNS не трогаются иначе)."
else
    echo "   ℹ️  MODULE_NETWORK_GUARD=OFF — сетевой guard не ставится и не планируется."
fi

# H5 (RR1b): политика ротации файловых логов Argus — после того, как
# $HERMES_DIR и его каталог логов существуют.
install_logrotate_policy || exit 1

# Общая библиотека handlers'ов — если включён хотя бы один бот. Ставится
# СВЕЖИМ из шаблона, поэтому Discord-only установка получает свою копию, а не
# зависит от остатка чужого модуля (B3, RR1b).
if module_enabled MODULE_TG_BOT || module_enabled MODULE_DISCORD_BOT; then
    echo ""
    echo "📁 [SHARED] библиотека handlers'ов ботов..."
    deploy_scripts "$HOME_DIR/scripts" "${SHARED_BOT_HOME_SCRIPTS[@]}"
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
    # B3 (RR1b): PyYAML нужен изолированному venv, а не системным
    # site-packages — handle_integrations_all читает реестр именно через yaml.
    if [ ! -x "$HERMES_DIR/discord-venv/bin/python" ]; then
        echo "   🐍 Создаю venv и ставлю discord.py + PyYAML (одноразово)..."
        if ! python3 -m venv "$HERMES_DIR/discord-venv"; then
            echo "   ❌ Не удалось создать $HERMES_DIR/discord-venv."
            echo "      Частая причина — нет python3-venv: sudo apt-get install -y python3-venv"
            echo "      (bootstrap install.sh ставит его сам)."
            exit 1
        fi
        if ! "$HERMES_DIR/discord-venv/bin/pip" install -q discord.py PyYAML; then
            echo "   ❌ Не удалось поставить discord.py/PyYAML в discord-venv."
            exit 1
        fi
    fi
    # Импорты проверяются ТЕМ ЖЕ интерпретатором, что запускает юнит
    # (modules/systemd/discord-bot.service: discord-venv/bin/python), и РЕАЛЬНЫМИ
    # импортами: find_spec доказывал бы лишь находимость пакета, а то, что он
    # импортируется, — нет. Невозможность выполнить саму проверку (битый
    # интерпретатор) — провал преrequisта, а НЕ «зелёный» вывод.
    if DISCORD_IMPORT_OUT=$("$HERMES_DIR/discord-venv/bin/python" -c '
import sys
missing = []
for name in ("discord", "yaml"):
    try:
        __import__(name)
    except Exception:
        missing.append(name)
print(",".join(missing))
' 2>&1); then
        if [ -n "$DISCORD_IMPORT_OUT" ]; then
            echo "   ⚠️  discord-venv не импортирует: $DISCORD_IMPORT_OUT — юнит не стартует."
            echo "      Фикс: $HERMES_DIR/discord-venv/bin/pip install discord.py PyYAML"
        else
            echo "   ✅ discord-venv импортирует discord + yaml"
        fi
    else
        echo "   ❌ Проверка импортов discord-venv не выполнилась (код $?):"
        echo "      $DISCORD_IMPORT_OUT"
        exit 1
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
                # Токен не попадает в argv: username/password подставляет
                # in-memory credential-helper (значение берётся из окружения),
                # пустой helper= сбрасывает системные хелперы (никаких записей
                # в ~/.git-credentials).
                if git -c credential.helper= \
                       -c 'credential.helper=!f(){ printf "username=argus\npassword=%s" "$GH_TOKEN"; }; f' \
                       push -q -f "https://github.com/$GH_USER/$GH_HB_REPO" main 2>/dev/null; then
                    echo "   ✅ репо запушен"
                else
                    echo "   ⚠️  push failed — проверьте права токена (repo/workflow)"
                fi
                # Секреты через stdin (gh читает значение из stdin, когда --body
                # не передан; флага --body-file в gh 2.45 нет): значения не
                # попадают в argv. Провал provisioning — явный гейт: bare
                # &&-цепочка под set -e НЕ прерывает деплой (errexit подавляется
                # для не-финальных команд AND-списка), и деплой отчитался бы
                # «готов» без secrets.
                if printf '%s' "${WATCHDOG_BOT_TOKEN:-}" | gh secret set WATCHDOG_BOT_TOKEN --repo "$GH_USER/$GH_HB_REPO" >/dev/null \
                   && printf '%s' "${WATCHDOG_CHAT_ID:-}" | gh secret set WATCHDOG_CHAT_ID --repo "$GH_USER/$GH_HB_REPO" >/dev/null; then
                    echo "   ✅ secrets установлены"
                    echo "   ✅ GH Heartbeat готов. Добавьте в config.env и перезапустите deploy:"
                    echo "      GITHUB_REPO=$GH_USER/$GH_HB_REPO"
                else
                    echo "   🚨 gh secret set failed — heartbeat secrets НЕ установлены, деплой прерван (повторный запуск deploy идемпотентен)" >&2
                    exit 1
                fi
            else
                echo "   ℹ️  Пропущено по отказу юзера. Альтернативы: DMS / Cronping"
                echo "      (https://deadmanssnitch.com, https://cronping.com)"
            fi
        fi
    fi
fi

# ── Генерация расписания и managed-блока (RR1a: единый writer) ─────────────
# CRON_PROFILE (C6 F6): full — весь набор; minimal — только тихие discovery/
# health-check строки (для тест-VM, чтобы алерты не сыпались в реальный чат).
# CRON_FILE остаётся proposal/diagnostic-артефактом; установленное расписание —
# это managed-блок в crontab, его пишет только reconcile_argus_cron.
CRON_PROFILE="${CRON_PROFILE:-full}"
CRON_FILE="${CRON_FILE:-/tmp/hermes-argus-crontab.txt}"

SCHEDULE=""
if module_enabled MODULE_CORE && [ "$CRON_PROFILE" = "full" ]; then
    SCHEDULE+="*/5 * * * * $HOME_DIR/scripts/hermes-watchdog.sh >> $HERMES_DIR/logs/watchdog-cron.log 2>&1"$'\n'
    SCHEDULE+="*/2 * * * * $HERMES_DIR/scripts/gateway-liveness.sh >> $HERMES_DIR/logs/gateway-liveness.log 2>&1"$'\n'
    SCHEDULE+="*/5 * * * * $HERMES_DIR/scripts/dashboard-liveness.sh >> $HERMES_DIR/logs/dashboard-liveness.log 2>&1"$'\n'
    SCHEDULE+="*/10 * * * * $HOME_DIR/scripts/auto-remediate.sh >> $HERMES_DIR/logs/auto-remediate.log 2>&1"$'\n'
    SCHEDULE+="0 3 * * 1 $HOME_DIR/scripts/check-updates.sh"$'\n'
    SCHEDULE+="30 * * * * $HERMES_DIR/scripts/watchdog-health.sh >> $HERMES_DIR/logs/watchdog-health-cron.log 2>&1"$'\n'
    SCHEDULE+="0 6 * * * $HERMES_DIR/scripts/ssl-expiry-check.sh >> $HERMES_DIR/logs/ssl-expiry-cron.log 2>&1"$'\n'
fi
if module_enabled MODULE_LOCAL_SERVICES; then
    # Один последовательный джоб: снимок → консьюмер (не конкурирующие cron'ы).
    # Креденшелы алертов — из ~/.hermes/.env (set -a, значения не в argv).
    SCHEDULE+="$LOCAL_SERVICES_CRON_LINE"$'\n'
fi
# H4 (RR1b): guard — отдельный opt-in, а не часть CORE. При OFF строка не
# генерируется, и reconciliation снимает её из managed-блока на ON→OFF.
if module_enabled MODULE_NETWORK_GUARD && [ "$CRON_PROFILE" = "full" ]; then
    SCHEDULE+="*/2 * * * * $HOME_DIR/scripts/network-guard.sh >> $HERMES_DIR/logs/network-guard-cron.log 2>&1"$'\n'
fi
if module_enabled MODULE_INTEGRATIONS; then
    SCHEDULE+="*/10 * * * * $HOME_DIR/scripts/integration-discover-wrapper.sh >> $HERMES_DIR/logs/integration-discover-cron.log 2>&1"$'\n'
    SCHEDULE+="*/5 * * * * python3 $HOME_DIR/scripts/fallback-tracker-v2.py >> $HERMES_DIR/logs/fallback-tracker-v2.log 2>&1"$'\n'
    SCHEDULE+="20 * * * * $HOME_DIR/scripts/health-check-v2-wrapper.sh >> $HERMES_DIR/logs/health-check-v2.log 2>&1"$'\n'
fi
if module_enabled MODULE_ANALYZER; then
    SCHEDULE+="5 * * * * cd $HERMES_DIR/scripts && python3 health-analyzer.py --update >> $HERMES_DIR/logs/health-analyzer.log 2>&1"$'\n'
fi
if module_enabled MODULE_HEARTBEAT; then
    # RR1a: cron зовёт команды через /bin/sh — `source` там не существует;
    # .env-загрузка требует явного /bin/bash -c (provenance: инцидент
    # local-services, контракт docs PR #55).
    SCHEDULE+="*/5 * * * * /bin/bash -c 'set -a; source $HERMES_DIR/.env; set +a; exec $HOME_DIR/scripts/heartbeat.sh' >> $HERMES_DIR/logs/heartbeat.log 2>&1"$'\n'
fi

# Proposal/diagnostic-артефакт: то, что селектировано настройками. Не является
# доказательством установленного расписания — им является managed-блок.
CRON_TMP=$(mktemp)
if [ -n "$SCHEDULE" ]; then
    {
        echo "# hermes-argus: proposal, установленное расписание живёт в managed-блоке crontab ($(date -Iseconds))"
        printf '%s' "$SCHEDULE"
    } > "$CRON_TMP"
    mv "$CRON_TMP" "$CRON_FILE"
else
    rm -f "$CRON_TMP"
    rm -f "$CRON_FILE"
fi

# Установка/снятие managed-блока — единственная точка записи crontab.
# Fail closed: сбой прерывает deploy (запись не состояла — не рапортуем успех).
if ! reconcile_argus_cron; then
    exit 1
fi

# Начальный сбор LOCAL_SERVICES — после успешного reconciliation (контракт
# RR1a: reconciliation завершается до начальной коллекции).
if module_enabled MODULE_LOCAL_SERVICES; then
    if python3 "$HERMES_DIR/scripts/service-status-snapshot.py" --quiet; then
        echo "   ✅ начальный снимок собран: $HERMES_DIR/state/service-status.json"
    else
        echo "   ⚠️  начальный снимок не удался — повторит cron-запуск через ≤5 мин (лог: service-status.log)"
    fi
fi

echo ""
verify_deployed_payload

echo ""
echo "✅ Развёртка завершена!"
echo ""
echo "👉 Что дальше:"
echo "   1. Маркеры и синтаксис уже проверены выше — повторно грепать не нужно"
echo "   2. Если включены TG-алерты/бот — проверь токены в config.env"
echo "   3. Перезагрузи systemd: systemctl --user daemon-reload"
if module_enabled MODULE_INTEGRATIONS; then
echo "   4. Включи вотчер конфига: systemctl --user enable --now hermes-argus-config.path (если не активен legacy hermes-vps-kit-* — см. шаг [INTEGRATIONS])"
fi
echo "   5. Тестовый прогон: $HOME_DIR/scripts/hermes-watchdog.sh"
echo "   6. Политика ротации логов: $HERMES_DIR/$LOGROTATE_POLICY_NAME"
echo "      (активирована в $LOGROTATE_SCHED_DIR/argus)"
