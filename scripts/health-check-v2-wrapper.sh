#!/bin/bash
# health-check-v2-wrapper.sh — stateful alerting around health-check-v2.py.
#
# Runs the engine, keeps consecutive-fail counts per check id, and sends
# SEPARATE Telegram messages per alert type (C-phase 2, 2026-09-07):
#   👁 Argus увидел деградацию   — 2nd consecutive fail (hysteresis)
#   🟢 Argus заметил восстановление — after ≥2 fails then ok
#   ⏳ Argus наблюдает           — still failing, re-notify every ~12 runs
# Healthy runs only touch the log ("silence on health"). Items are
# html-escaped because messages are sent with parse_mode=HTML.
#
# Architecture mirrors integration-discover.py / -wrapper.sh: stateless engine
# + stateful alerting shell. Registry missing (engine exit 2) = config problem,
# logged without alerting.

set -u
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
H="$HOME/.hermes"
LOG="$H/logs/health-check-v2.log"
STATE="$H/state/health-check-v2-state.json"
REPORT="$H/state/health-check-v2-report.json"

python3 "$HOME/scripts/health-check-v2.py" >>"$LOG" 2>&1
RC=$?
echo "[$(date -Is)] health-check-v2 exit=$RC" >> "$LOG"

# Engine exit 2: registry missing/engine error — log only, no alert spam
[ "$RC" = "2" ] && exit 0
[ -f "$REPORT" ] || { echo "[$(date -Is)] report missing, skip alerting" >> "$LOG"; exit 0; }

GROUPS=$(python3 - "$STATE" "$REPORT" <<'PYEOF'
import html, json, sys
from pathlib import Path

state_p, report_p = Path(sys.argv[1]), Path(sys.argv[2])
try:
    report = json.loads(report_p.read_text(encoding="utf-8"))
except Exception:
    print(json.dumps({}))
    sys.exit(0)
try:
    state = json.loads(state_p.read_text(encoding="utf-8"))
except Exception:
    state = {}

groups = {"degraded": [], "recovered": [], "watching": []}
live = set()
for c in report.get("checks", []):
    cid = c["id"]
    live.add(cid)
    prev = state.get(cid, 0)
    label = html.escape(str(c.get("label", cid)))
    detail = html.escape(str(c.get("detail", "")))
    if c["status"] == "fail":
        state[cid] = prev + 1
        if state[cid] == 2:
            # hysteresis: alert exactly once on the 2nd consecutive fail
            groups["degraded"].append(f"🔴 {label}: {detail}")
        elif state[cid] > 2 and state[cid] % 12 == 0:
            groups["watching"].append(
                f"⏳ {label}: still failing ({state[cid]} runs): {detail}")
    else:
        if prev >= 2:
            groups["recovered"].append(f"🟢 {label} ({detail})")
        state[cid] = 0

# prune checks that disappeared from the snapshot
state = {k: v for k, v in state.items() if k in live}
state_p.parent.mkdir(parents=True, exist_ok=True)
tmp = state_p.with_suffix(".tmp")
tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
tmp.replace(state_p)
print(json.dumps(groups, ensure_ascii=False))
PYEOF
)

source "$H/.env" 2>/dev/null || true
if [ -z "${WATCHDOG_BOT_TOKEN:-}" ]; then
    echo "$GROUPS" >> "$LOG"
    exit 0
fi

send_group() {
    local key="$1" header="$2" body
    body=$(printf '%s' "$GROUPS" | python3 -c "
import json, sys
d = json.load(sys.stdin)
items = d.get('$key') or []
if items:
    print('$header')
    print('\n'.join(items))
" 2>>"$LOG")
    [ -z "$body" ] && return 0
    MSG_ESC=$(python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" <<< "$body")
    proxy="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
    curl -s -m 20 -x "$proxy" -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\": \"${WATCHDOG_CHAT_ID}\", \"text\": $MSG_ESC, \"parse_mode\": \"HTML\"}" \
        -o /dev/null >> "$LOG" 2>&1 || true
    echo "[$(date -Is)] alert sent ($key)" >> "$LOG"
}

send_group "degraded"  "👁 Argus увидел деградацию"
send_group "recovered" "🟢 Argus заметил восстановление"
send_group "watching"  "⏳ Argus наблюдает"
exit 0
