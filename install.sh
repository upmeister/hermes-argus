#!/bin/bash
# Versioned hermes-argus install/update; stable by default.
set -euo pipefail

# ARGUS_LIFECYCLE_V1 — selected revisions must implement this protocol.
REPO_URL="https://github.com/upmeister/hermes-argus.git"
REPO_DIR="$HOME/hermes-argus"

usage() {
    echo 'Usage: bash install.sh [--channel stable|edge | --version TAG]'
    echo 'Default: stable. Repeat --version for an RC; channel is not persisted.'
}
CHANNEL=stable
VERSION=""
SELECTOR_SET=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --channel|--version)
            [ "$SELECTOR_SET" -eq 0 ] && [ "$#" -ge 2 ] || { usage >&2; exit 1; }
            SELECTOR_SET=1
            if [ "$1" = --version ]; then VERSION="$2"; CHANNEL=tag
            else CHANNEL="$2"; [[ "$CHANNEL" = stable || "$CHANNEL" = edge ]] || { usage >&2; exit 1; }; fi
            shift 2 ;;
        *) usage >&2; exit 1 ;;
    esac
done

install_stop() { echo "install: $*; no deployment performed" >&2; exit 1; }

for cmd in git curl python3; do
    command -v "$cmd" >/dev/null 2>&1 || install_stop "version selection requires git, curl and python3; install these prerequisites first"
done

if [ "${ARGUS_INSTALL_REEXEC:-}" = 1 ]; then
    [[ "${ARGUS_INSTALL_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || install_stop 'invalid selected-tree transition'
    [ "$(git -C "$REPO_DIR" rev-parse HEAD)" = "$ARGUS_INSTALL_SHA" ] || install_stop 'selected checkout changed'
    echo "Selected tree: $ARGUS_INSTALL_SHA"
    unset ARGUS_INSTALL_REEXEC ARGUS_INSTALL_SHA
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


else
    if [ "$CHANNEL" = stable ]; then
        # Public release metadata only. No credential header or fallback to main.
        if ! VERSION=$(curl --fail --silent --show-error --max-time 20 \
            https://api.github.com/repos/upmeister/hermes-argus/releases/latest | python3 -c '
import json,re,sys
try:
    d=json.load(sys.stdin)
    assert d.get("draft") is False and d.get("prerelease") is False
    tag=d["tag_name"]
    assert isinstance(tag,str) and tag and tag.strip()==tag
    assert not re.fullmatch(r"v?\d+\.\d+\.\d+-[^+]+(?:\+.*)?",tag)
    print(tag)
except (ValueError,KeyError,TypeError,AssertionError):
    sys.exit(1)
'); then install_stop 'stable release unavailable or malformed'; fi
    fi
    if [ "$CHANNEL" != edge ]; then
        git check-ref-format "refs/tags/$VERSION" >/dev/null 2>&1 || install_stop 'invalid release tag'
    fi
    FRESH=0
    if [ ! -e "$REPO_DIR" ]; then
        git clone --quiet "$REPO_URL" "$REPO_DIR" || install_stop 'clone failed'
        FRESH=1
    fi
    git -C "$REPO_DIR" rev-parse --git-dir >/dev/null 2>&1 || install_stop 'destination is not a Git checkout'
    [ "$(git -C "$REPO_DIR" remote get-url origin)" = "$REPO_URL" ] || install_stop 'unexpected origin remote'
    if [ "$FRESH" -eq 0 ]; then
        SOURCE_STATUS=$(git -C "$REPO_DIR" status --porcelain --untracked-files=no) || install_stop 'cannot read checkout status'
        [ -z "$SOURCE_STATUS" ] || install_stop 'tracked local changes'
    fi
    OLD_SHA=$(git -C "$REPO_DIR" rev-parse HEAD)
    git -C "$REPO_DIR" fetch --quiet origin main || install_stop 'origin/main unavailable'
    if git -C "$REPO_DIR" symbolic-ref -q HEAD >/dev/null \
        || [ -z "$(git -C "$REPO_DIR" tag --points-at HEAD)" ]; then
        git -C "$REPO_DIR" merge-base --is-ancestor "$OLD_SHA" origin/main \
            || install_stop 'local branch diverges from origin/main'
    fi
    if [ "$CHANNEL" = edge ]; then
        SELECTED_SHA=$(git -C "$REPO_DIR" rev-parse 'origin/main^{commit}')
    else
        git -C "$REPO_DIR" fetch --quiet origin "refs/tags/$VERSION:refs/tags/$VERSION" \
            || install_stop 'release tag unavailable'
        SELECTED_SHA=$(git -C "$REPO_DIR" rev-parse "refs/tags/$VERSION^{commit}") \
            || install_stop 'release tag is not a commit'
    fi
    echo "Selected $CHANNEL${VERSION:+ ($VERSION)}: $SELECTED_SHA"
    git -C "$REPO_DIR" show "$SELECTED_SHA:install.sh" | grep '^# ARGUS_LIFECYCLE_V1 ' >/dev/null \
        || install_stop 'target predates the supported lifecycle contract'
    git -C "$REPO_DIR" cat-file -e "$SELECTED_SHA:uninstall.sh" \
        || install_stop 'target has no bounded uninstall'
    STAGED_TREE=$(mktemp -d)
    # A temporary Git worktree exposes target code before changing the installed
    # source. No install-state database, copied secrets or speculative history.
    rmdir "$STAGED_TREE"
    cleanup_selected_tree() {
        [ -z "${OWN_LOG:-}" ] || rm -f -- "$OWN_LOG"
        git -C "$REPO_DIR" worktree remove "$STAGED_TREE" >/dev/null 2>&1 || {
            echo "install: temporary selected tree retained at $STAGED_TREE; cleanup required" >&2
            return 1
        }
    }
    trap cleanup_selected_tree EXIT
    git -C "$REPO_DIR" worktree add --quiet --detach "$STAGED_TREE" "$SELECTED_SHA" \
        || install_stop 'cannot stage selected tree'
    OWN_CONFIG=""
    if [ -e "$REPO_DIR/config.env" ] || [ -L "$REPO_DIR/config.env" ]; then OWN_CONFIG="$REPO_DIR/config.env"; fi
    OWN_REV="$OLD_SHA"
    [ "$FRESH" -eq 0 ] || OWN_REV="$SELECTED_SHA"
    OWN_LOG=$(mktemp)
    if ! bash "$STAGED_TREE/deploy.sh" --check-ownership "$OWN_CONFIG" "$REPO_DIR" "$OWN_REV" >"$OWN_LOG" 2>&1; then
        cat "$OWN_LOG"
        install_stop 'installed ownership differs or cannot be established; reconcile before updating'
    fi
    cat "$OWN_LOG"
    CURRENT_TAGS=$(git -C "$REPO_DIR" tag --points-at HEAD)
    if grep -q "^MATCH " "$OWN_LOG" && [ "$FRESH" -eq 0 ] && [ -n "$CURRENT_TAGS" ] && [ "$OLD_SHA" != "$SELECTED_SHA" ]; then
        TARGET_TAG="${VERSION:-$(git -C "$REPO_DIR" tag --points-at "$SELECTED_SHA")}"
        ORDER=$(python3 - "$CURRENT_TAGS" "$TARGET_TAG" <<'PY'
import re,sys
def key(tag):
    m=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?',tag)
    if not m: return None
    pre=m[4]
    return (tuple(map(int,m.group(1,2,3))),pre is None,
            tuple((0,int(p)) if p.isdigit() else (1,p) for p in (pre or '').split('.')))
a=[k for t in sys.argv[1].splitlines() if (k:=key(t)) is not None]
b=[k for t in sys.argv[2].splitlines() if (k:=key(t)) is not None]
print('older' if a and b and max(b)<max(a) else 'other')
PY
)
        # Git ancestry supplies the conservative fallback for non-semver tags.
        if [ "$ORDER" = older ] || ! git -C "$REPO_DIR" merge-base --is-ancestor "$OLD_SHA" "$SELECTED_SHA"; then
            [ "$CHANNEL" = tag ] || install_stop 'implicit downgrade or incomparable tagged revision'
            echo 'Intentional downgrade/revision change requested by --version.'
        fi
    fi
    cleanup_selected_tree || install_stop 'temporary worktree cleanup failed'
    trap - EXIT
    git -C "$REPO_DIR" checkout --quiet --no-overwrite-ignore --detach "$SELECTED_SHA" \
        || install_stop 'checkout refused (including untracked/ignored collision); user work retained'
    # Exactly one transition: the selected installer's dependency/config/deploy
    # logic executes, never an old in-memory bootstrap over a different tree.
    exec env ARGUS_INSTALL_REEXEC=1 ARGUS_INSTALL_SHA="$SELECTED_SHA" \
        bash "$REPO_DIR/install.sh"
fi
cd "$REPO_DIR"

assert_private_config() {
    local cfg="$1" owner mode
    # H1 (ремедиация ревью PR #75): симлинк — не обычный файл; `[ -f ]` следует
    # по ссылке, и цель с корректными правами проходила бы проверку. Обе копии
    # (deploy.sh и здесь) обязаны отвергать одинаковые свойства.
    if [ -L "$cfg" ]; then
        echo "❌ Конфиг $cfg — символическая ссылка, а не обычный файл." >&2
        echo "   Починка: rm $cfg (снимет ссылку, не цель) и положи на его" >&2
        echo "   место обычный файл." >&2
        return 1
    fi
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
    # конфиг с секретами «безопасным». Проверка дублируется из deploy.sh —
    # обе копии обязаны вести себя одинаково.
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

# H1 (ремедиация): симлинк запрещён ещё до ветки создания — иначе `cp` через
# висячую ссылку записал бы В ЦЕЛЬ за пределами ожидаемого места.
if [ -L config.env ]; then
    echo "❌ config.env — символическая ссылка, а не обычный файл." >&2
    echo "   Секреты не должны разрешаться через чужие пути. Починка:" >&2
    echo "   rm config.env (снимет ссылку, не цель) и повтори установку." >&2
    exit 1
fi
if [ ! -f config.env ]; then
    ( umask 077; cp config/config.env.template config.env )
    echo ""
    echo "✏️  Создан config.env из шаблона (режим 0600, секреты не читают другие)."
    echo "   Минимум для старта:"
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
elif ! assert_private_config config.env; then
    echo "   Установка остановлена: конфиг с секретами доступен посторонним."
    exit 1
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
if ! bash deploy.sh config.env 2>&1 | tee "$DEPLOY_LOG"; then
    echo 'install: deploy failed; checkout is selected, runtime may be partial; no completion or rollback claimed' >&2
    exit 1
fi
DEPLOY_OUT="$(cat "$DEPLOY_LOG")"

# ── 5. Watcher ──────────────────────────────────────────────────────────────
systemctl --user daemon-reload || { echo 'install: deployment applied, daemon-reload failed; manual read-back required' >&2; exit 1; }
# RR0c (B3): ровно один активный producer. Legacy-юнит, который включён ИЛИ
# фактически активен (active-but-not-enabled: ручной старт, транзиентный
# запуск), не переключается автоматически — оператор делает хэндофф вручную.
if systemctl --user is-enabled hermes-vps-kit-config.path >/dev/null 2>&1 \
   || systemctl --user is-active hermes-vps-kit-config.path >/dev/null 2>&1; then
    echo "📡 Discover-вотчер: живой legacy hermes-vps-kit-config.path — оставляю его;"
    echo "   хэндофф на hermes-argus-config.path — вручную (см. вывод deploy.sh)."
elif systemctl --user list-unit-files | grep -q hermes-argus-config.path; then
    systemctl --user enable --now hermes-argus-config.path || { echo 'install: deployment applied, watcher activation failed' >&2; exit 1; }
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
