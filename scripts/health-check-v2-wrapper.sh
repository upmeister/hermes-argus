#!/bin/bash
# health-check-v2-wrapper.sh — stateful alerting around health-check-v2.py.
#
# Runs the engine, keeps consecutive-fail counts per check id, sends ONE
# Telegram message when a check degrades (2+ consecutive fails — hysteresis
# per repo conventions), re-notifies every ~12h while still failing, and on
# recovery. Healthy runs only touch the log ("silence on health").
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

REPORT_OUT=$(python3 "$HOME/scripts/health-check-v2.py" 2>>"$LOG")
RC=$?
echo "[$(date -Is)] health-check-v2 exit=$RC" >> "$LOG"
echo "$REPORT_OUT" >> "$LOG"

# Engine exit 2: registry missing/engine error — log only, no alert spam
[ "$RC" = "2" ] && exit 0

[ -f "$REPORT" ] || { echo "[$(date -Is)] report missing, skip alerting" >> "$LOG"; exit 0; }

TRANSITIONS=$(python3 - "$STATE" "$REPORT" <<'PYEOF'
import json, sys
from pathlib import Path

state_p, report_p = Path(sys.argv[1]), Path(sys.argv[2])
try:
    report = json.loads(report_p.read_text(encoding="utf-8"))
except Exception as e:
    print(json.dumps({"alerts": []})); sys.exit(0)
try:
    state = json.loads(state_p.read_text(encoding="utf-8"))
except Exception:
    state = {}

alerts = []
live = set()
for c in report.get("checks", []):
    cid = c["id"]
    live.add(cid)
    prev = state.get(cid, 0)
    if c["status"] == "fail":
        state[cid] = prev + 1
        if state[cid] == 2:
            # hysteresis: alert exactly once on the 2nd consecutive fail
            alerts.append("\U0001F534 " + c["label"] + ": " + c["detail"])
        elif state[cid] > 2 and state[cid] % 12 == 0:
            alerts.append("\u23F3 still failing (" + str(state[cid]) + " runs): "
                          + c["label"] + ": " + c["detail"])
    else:
        if prev >= 2:
            alerts.append("\U0001F7E2 recovered: " + c["label"] + " (" + c["detail"] + ")")
        state[cid] = 0

# prune checks that disappeared from the snapshot
state = {k: v for k, v in state.items() if k in live}

state_p.parent.mkdir(parents=True, exist_ok=True)
tmp = state_p.with_suffix(".tmp")
tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
tmp.replace(state_p)
print(json.dumps({"alerts": alerts}, ensure_ascii=False))
PYEOF
)

ALERTS=$(printf '%s' "$TRANSITIONS" | python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin)["alerts"]))' 2>>"$LOG")
[ -z "$ALERTS" ] && exit 0

source "$H/.env" 2>/dev/null || true
if [ -z "${WATCHDOG_BOT_TOKEN:-}" ]; then
    echo "$ALERTS" >> "$LOG"
    exit 0
fi

MSG="🩺 <b>Argus: интеграции деградировали</b>
$ALERTS"
MSG_ESC=$(python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" <<< "$MSG")
proxy="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
curl -s -m 20 -x "$proxy" -X POST "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\": \"${WATCHDOG_CHAT_ID}\", \"text\": $MSG_ESC, \"parse_mode\": \"HTML\"}" \
    -o /dev/null >> "$LOG" 2>&1 || true
echo "[$(date -Is)] alert sent" >> "$LOG"
exit 0
