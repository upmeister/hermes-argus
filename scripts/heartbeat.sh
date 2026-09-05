#!/bin/bash
# Heartbeat: пушит timestamp в GitHub-репо hermes-infra + Dead Man's Snitch
# Если сервер жив — DMS и GitHub видят свежий heartbeat
# Если сервер упал — внешние системы заметят просрочку и отправят алерт

REPO_DIR="$HOME/.hermes/hermes-infra"

# Загружаем токен (cron не экспортирует переменные из .env)
if [ -z "$GH_TOKEN" ] && [ -f "$HOME/.hermes/.env" ]; then
    set -a; source "$HOME/.hermes/.env"; set +a
fi

# ===== Dead Man's Snitch (hourly fallback) =====
# Бесплатный внешний наблюдатель — алерт, если сервер не пинговал >1ч
# Для 5-минутной гранулярности используется GitHub Heartbeat
curl -fsS -m 10 "https://nosnch.in/@DMS_SNITCH@" >/dev/null 2>&1 || true

# ===== GitHub Heartbeat (5-минутная гранулярность) =====
cd "$REPO_DIR" || exit 0

# Синхронизация с remote перед пушем: Actions (heartbeat-monitor) коммитит
# флаг-файл .heartbeat-alert — без pull серверный push падает (non-fast-forward)
git pull --rebase --autostash -q 2>/dev/null || true

# Записываем свежий timestamp
date -u +"%Y-%m-%dT%H:%M:%SZ" > heartbeat.txt

# Commit & push
git add heartbeat.txt
if git diff --cached --quiet; then
    exit 0
fi

git commit -m "heartbeat: $(date -u +'%Y-%m-%d %H:%M UTC')" --quiet
git push "https://${GH_TOKEN}@github.com/@GITHUB_REPO@" main --quiet
echo "[heartbeat] pushed at $(date -u +'%Y-%m-%d %H:%M UTC')"
