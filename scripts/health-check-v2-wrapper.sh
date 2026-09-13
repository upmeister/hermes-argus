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
# D0a dual-read: schema-2 reports are judged by the canonical ADR 0001 verdict,
# legacy reports by the v1 status. unknown/unconfigured/skipped preserve the
# failure counter — never a recovery; a malformed v2 report is rejected whole.

set -u
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
H="$HOME/.hermes"
LOG="$H/logs/health-check-v2.log"
STATE="$H/state/health-check-v2-state.json"
REPORT="$H/state/health-check-v2-report.json"

report_before=$(stat -c '%d:%i:%s:%y:%z' "$REPORT" 2>/dev/null || printf 'absent')
python3 "$HOME/scripts/health-check-v2.py" >>"$LOG" 2>&1
RC=$?
echo "[$(date -Is)] health-check-v2 exit=$RC" >> "$LOG"

# Engine crash may also exit 1 (the same code as a real health failure). If the
# report was not rewritten during this invocation, it is stale and must not be
# processed as a recovery (probe wrapper_crash_replays_stale_green).
if [ "$RC" != "2" ]; then
    report_after=$(stat -c '%d:%i:%s:%y:%z' "$REPORT" 2>/dev/null || printf 'absent')
    if [ "$report_after" = "$report_before" ]; then
        echo "[$(date -Is)] engine produced no fresh report (exit $RC) — stale report NOT processed" >> "$LOG"
        exit 0
    fi
fi

# Engine exit 2: registry/snapshot configuration error — log only, no alert spam
[ "$RC" = "2" ] && exit 0
[ -f "$REPORT" ] || { echo "[$(date -Is)] report missing, skip alerting" >> "$LOG"; exit 0; }
if ! python3 - "$REPORT" <<'PYEOF'
import json, sys
from pathlib import Path

VERDICTS = ("healthy", "failed", "unknown", "unconfigured", "skipped")


def reject(reason):
    print(f"reject: {reason}", file=sys.stderr)
    raise SystemExit(1)


try:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    reject("unreadable json")

# Fail-closed whole-report validation (ADR 0001, D0a review pass): an
# untrusted report must never touch the hysteresis state.
if not isinstance(report, dict):
    reject("report is not an object")
schema = report.get("schema", 1)
if schema not in (1, 2):
    reject(f"unsupported schema {schema!r}")
if not isinstance(report.get("updated"), str) or not report["updated"]:
    reject("missing updated")
checks = report.get("checks")
if not isinstance(checks, list):
    reject("checks is not a list")
vk = "verdict" if schema == 2 else "status"
seen, counts = set(), {}
for c in checks:
    if not isinstance(c, dict):
        reject("check record is not an object")
    cid = c.get("id")
    if not isinstance(cid, str) or not cid:
        reject("check record without a string id")
    if cid in seen:
        reject(f"duplicate check id {cid!r}")
    seen.add(cid)
    v = c.get(vk)
    if schema == 2 and v not in VERDICTS:
        reject(f"check {cid!r}: verdict {v!r} is not canonical")
    if schema == 1 and (not isinstance(v, str) or not v):
        reject(f"check {cid!r}: status must be a non-empty string")
    if not isinstance(c.get("label"), str) or not isinstance(c.get("detail"), str):
        reject(f"check {cid!r}: label and detail must be strings")
    counts[v] = counts.get(v, 0) + 1
if schema == 2:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        reject("missing summary")
    for k in VERDICTS:
        if summary.get(k) != counts.get(k, 0):
            reject(f"summary.{k} is inconsistent with checks")
    if summary.get("total") != len(checks):
        reject("summary.total is inconsistent with checks")
    if not isinstance(report.get("inventory"), dict):
        reject("missing inventory")
else:
    ok = counts.get("ok", 0)
    fail = counts.get("fail", 0)
    unconf = counts.get("unconfigured", 0)
    # v1 semantics: skipped is everything not ok/fail/unconfigured
    expected = {"total": len(checks), "ok": ok, "fail": fail,
                "unconfigured": unconf,
                "skipped": len(checks) - ok - fail - unconf}
    for k, want in expected.items():
        if report.get(k, 0) != want:
            reject(f"{k} count is inconsistent with checks")
PYEOF
then
    echo "[$(date -Is)] report invalid, skip alerting and preserve state" >> "$LOG"
    exit 0
fi

ALERT_GROUPS=$(python3 - "$STATE" "$REPORT" <<'PYEOF'
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
# Dual-read (D0a): schema-2 reports are judged by the canonical ADR 0001
# verdict; legacy reports are projected conservatively. `unknown` — and any
# unreadable legacy status — preserves the failure counter: it is never a
# recovery.
legacy_verdict = {"ok": "healthy", "fail": "failed",
                  "unconfigured": "unconfigured", "skipped": "skipped"}
is_v2 = report.get("schema") == 2
for c in report.get("checks", []):
    cid = c["id"]
    live.add(cid)
    prev = state.get(cid, 0)
    label = html.escape(str(c.get("label", cid)))
    detail = html.escape(str(c.get("detail", "")))
    if is_v2:
        verdict = c.get("verdict")
    else:
        verdict = legacy_verdict.get(c.get("status"), "unknown")
    if verdict == "failed":
        state[cid] = prev + 1
        if state[cid] == 2:
            # hysteresis: alert exactly once on the 2nd consecutive fail
            groups["degraded"].append(f"🔴 {label}: {detail}")
        elif state[cid] > 2 and state[cid] % 12 == 0:
            groups["watching"].append(
                f"⏳ {label}: still failing ({state[cid]} runs): {detail}")
    elif verdict in ("unknown", "unconfigured", "skipped"):
        # config drift, an intentionally skipped check, or an unknown state is
        # NOT recovery: preserve the previous failure counter.
        pass
    elif verdict == "healthy":
        if prev >= 2:
            groups["recovered"].append(f"🟢 {label} ({detail})")
        state[cid] = 0
    # validated reports cannot carry any other verdict value

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
    echo "$ALERT_GROUPS" >> "$LOG"
    exit 0
fi

send_group() {
    local key="$1" header="$2" body
    body=$(printf '%s' "$ALERT_GROUPS" | python3 -c "
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
