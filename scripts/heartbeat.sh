#!/bin/bash
# heartbeat.sh — external dead man's switch, multi-backend (C4).
#
# Backends activate by config only — silence if nothing is configured:
#   cronping — CRONPING_TOKEN in ~/.hermes/.env        (5-min granularity, recommended)
#   dms      — DMS_SNITCH in ~/.hermes/.env            (Dead Man's Snitch, hourly free tier)
#   github   — GITHUB_REPO + GH_TOKEN + repo dir       (5-min, requires MODULE_GH_HEARTBEAT)
# If the server dies, backends that stop receiving pings alert externally.
#
# Backend setup (also printed by deploy.sh):
#   cronping: register at cronping.com -> create organization -> Organization
#     settings -> API keys -> create key. Argus installer (MODULE_GH_HEARTBEAT
#     off) can create the heartbeat via Management API automatically and store
#     its ping token in CRONPING_TOKEN.
#   dms: register at deadmanssnitch.com -> create a snitch -> put the ID (the
#     path part of the ping URL) into DMS_SNITCH.
#   github: see modules/gh-heartbeat/ — needs a PAT with repo write
#     (classic: repo scope; fine-grained: Contents read/write).

set -euo pipefail

H="@HERMES_DIR@"
LOG="$H/logs/heartbeat.log"
STATE_DIR="$H/logs/auto-remediate-state"

mkdir -p "$H/logs" "$STATE_DIR"
LOCK_FILE="$STATE_DIR/heartbeat.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    printf '[%s] heartbeat уже выполняется — пропускаю параллельный запуск\n' \
        "$(date -Is)" >> "$LOG"
    exit 0
fi

# cron does not export .env — load secrets ourselves
if [ -f "$H/.env" ]; then
    set -a; source "$H/.env"; set +a
fi

sent=0

# ── Cronping ────────────────────────────────────────────────────────────
if [ -n "${CRONPING_TOKEN:-}" ]; then
    if curl -fsS -m 10 "https://ping.cronping.com/${CRONPING_TOKEN}" >/dev/null 2>&1; then
        sent=$((sent + 1))
    else
        echo "[$(date -Is)] cronping ping FAILED" >> "$LOG"
    fi
fi

# ── Dead Man's Snitch ───────────────────────────────────────────────────
if [ -n "${DMS_SNITCH:-}" ] && [ "${DMS_SNITCH:-}" != "change_me" ]; then
    if curl -fsS -m 10 "https://nosnch.in/${DMS_SNITCH}" >/dev/null 2>&1; then
        sent=$((sent + 1))
    else
        echo "[$(date -Is)] dms ping FAILED" >> "$LOG"
    fi
fi

# ── GitHub Heartbeat ────────────────────────────────────────────────────
# Pushes a fresh timestamp into the private heartbeat repo; the repo's
# Actions workflow alerts when the timestamp goes stale. GITHUB_REPO comes
# from ~/.hermes/.env (set by the GH heartbeat module setup).
if [ -n "${GITHUB_REPO:-}" ] && [ -n "${GH_TOKEN:-}" ] && [ -d "$H/hermes-infra" ]; then
    cd "$H/hermes-infra" || exit 0
    # Pull before push: the Actions workflow commits the .heartbeat-alert flag
    # file — without pull the server push fails (non-fast-forward)
    git pull --rebase --autostash -q 2>/dev/null || true
    date -u +"%Y-%m-%dT%H:%M:%SZ" > heartbeat.txt
    git add heartbeat.txt
    if git diff --cached --quiet; then
        sent=$((sent + 1))   # repo already fresh — counts as a live beat
    else
        if git commit -m "heartbeat: $(date -u +'%Y-%m-%d %H:%M UTC')" --quiet &&
           GIT_CONFIG_COUNT=1 \
           GIT_CONFIG_KEY_0='http.https://github.com/.extraheader' \
           GIT_CONFIG_VALUE_0="Authorization: Basic $(printf 'x-access-token:%s' "$GH_TOKEN" | base64 -w0)" \
           git push "https://github.com/${GITHUB_REPO}" main --quiet 2>>"$LOG"; then
            sent=$((sent + 1))
            echo "[heartbeat] gh pushed at $(date -u +'%Y-%m-%d %H:%M UTC')" >> "$LOG"
        else
            echo "[$(date -Is)] gh push FAILED" >> "$LOG"
        fi
    fi
fi

if [ "$sent" -eq 0 ]; then
    echo "[$(date -Is)] no heartbeat backend configured — nothing sent" >> "$LOG"
fi
