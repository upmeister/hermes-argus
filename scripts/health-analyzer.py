#!/usr/bin/env python3
"""
Анализатор состояния сервера — вычисляет diff между текущим состоянием
и предыдущим, выдаёт структурированный отчёт для LLM.

Использование: python3 health-analyzer.py [--update]
  Без флагов: выводит отчёт (только чтение)
  --update: записывает обновлённое состояние после анализа
"""

import json, os, sys, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Локальные модули
sys.path.insert(0, str(Path(__file__).resolve().parent))
from health_patterns import PATTERNS, find_issues
from health_decay import should_auto_resolve
from health_netdata import collect_netdata_trends

STATE_FILE = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "logs" / "health-state.json"
METRICS_SCRIPT = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "scripts" / "collect-metrics.sh"

NOW = datetime.now(timezone.utc)
NOW_ISO = NOW.isoformat()

# ═══════════════════════════════════════════════════════════════════════════
# 1. Загрузка состояния
# ═══════════════════════════════════════════════════════════════════════════

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"version": 1, "last_check": None, "issues": {}, "daily_summary_sent": None, "weekly_summary_sent": None, "escalations": {}}

state = load_state()

# ═══════════════════════════════════════════════════════════════════════════
# 2. Сбор метрик
# ═══════════════════════════════════════════════════════════════════════════

def collect_metrics():
    try:
        result = subprocess.run(
            ["bash", str(METRICS_SCRIPT)],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout
    except Exception as e:
        return f"ОШИБКА сбора метрик: {e}"

metrics_output = collect_metrics()

# ═══════════════════════════════════════════════════════════════════════════
# 2b. L1-алерты watchdog (для L3-контекста: health-check должен видеть,
#     что L1 уже алертил, а не «слепнуть» на своих паттернах)
# ═══════════════════════════════════════════════════════════════════════════

WATCHDOG_LOG = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "logs" / "watchdog.log"


def collect_watchdog_alerts(log_path=None, hours=24, max_alerts=8):
    """Последние отправленные L1-алерты (блоки TG[OK]) из watchdog.log.

    Блок TG[OK] многострочный (тело сообщения идёт следом за первой строкой),
    собираем строки до следующего таймстемпа. Таймстемпы локальные (+07).
    """
    path = Path(log_path) if log_path else WATCHDOG_LOG
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    alerts = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("[") and "TG[OK]" in line:
            block = [line]
            j = i + 1
            while j < n and not lines[j].startswith("["):
                block.append(lines[j])
                j += 1
            alerts.append("\n".join(block))
            i = j
        else:
            i += 1
    now_local = datetime.now()
    cutoff = now_local - timedelta(hours=hours)
    out = []
    for block in alerts[-200:]:
        try:
            ts = datetime.strptime(block[1:20], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if ts >= cutoff:
            text = block.split("]: ", 1)[-1].replace("<b>", "").replace("</b>", "")
            if len(text) > 300:
                text = text[:300] + "…"
            out.append({"time": ts.strftime("%Y-%m-%d %H:%M"), "alert": text})
    return out[-max_alerts:]

# ═══════════════════════════════════════════════════════════════════════════
# 3. Поиск проблем и decay-фильтрация
# ═══════════════════════════════════════════════════════════════════════════

current_issues = find_issues(metrics_output)

auto_resolved_now = {}
truly_active = {}

for issue_id, info in current_issues.items():
    if should_auto_resolve(info, NOW):
        auto_resolved_now[issue_id] = info
    else:
        truly_active[issue_id] = info

# ═══════════════════════════════════════════════════════════════════════════
# 4. Вычисление diff'а
# ═══════════════════════════════════════════════════════════════════════════

known = state.get("issues", {})

new_issues = []
recurring_issues = []
ongoing_issues = []
resolved_issues = []

def _add_timeline(entry, info):
    for key in ("first_error", "last_error", "error_window_hours", "density_per_hour"):
        if key in info:
            entry[key] = info[key]

for issue_id, info in truly_active.items():
    prev = known.get(issue_id)
    if not prev:
        entry = {"id": issue_id, "description": info["description"], "severity": info["severity"], "matches": info["match_count"], "sample": info["sample"]}
        _add_timeline(entry, info)
        new_issues.append(entry)
    elif prev.get("status") == "resolved":
        entry = {"id": issue_id, "description": info["description"], "severity": info["severity"], "matches": info["match_count"], "first_seen": prev.get("first_seen"), "was_resolved": True}
        _add_timeline(entry, info)
        recurring_issues.append(entry)
    else:
        entry = {"id": issue_id, "description": info["description"], "severity": info["severity"], "matches": info["match_count"], "first_seen": prev.get("first_seen"), "duration_hours": round((NOW - datetime.fromisoformat(prev["first_seen"].replace("Z", "+00:00"))).total_seconds() / 3600, 1)}
        _add_timeline(entry, info)
        ongoing_issues.append(entry)

for issue_id, info in auto_resolved_now.items():
    prev = known.get(issue_id)
    if prev and prev.get("status") == "active":
        resolved_issues.append({"id": issue_id, "description": info["description"], "severity": info["severity"], "first_seen": prev.get("first_seen"), "reason": "decay", "duration_hours": round((NOW - datetime.fromisoformat(prev["first_seen"].replace("Z", "+00:00"))).total_seconds() / 3600, 1), "last_error": info.get("last_error"), "error_window_hours": info.get("error_window_hours")})

for issue_id, prev in known.items():
    if prev.get("status") == "active" and issue_id not in truly_active and issue_id not in auto_resolved_now:
        resolved_issues.append({"id": issue_id, "description": PATTERNS.get(issue_id, {}).get("description", issue_id), "first_seen": prev.get("first_seen"), "duration_hours": round((NOW - datetime.fromisoformat(prev["first_seen"].replace("Z", "+00:00"))).total_seconds() / 3600, 1)})

# ═══════════════════════════════════════════════════════════════════════════
# 5. Формирование отчёта
# ═══════════════════════════════════════════════════════════════════════════

def output_report():
    last_check = state.get("last_check")
    last_check_str = last_check if last_check else "никогда (первый запуск)"
    report = {
        "meta": {"timestamp": NOW_ISO, "last_check": last_check_str, "check_number": state.get("check_count", 0) + 1},
        "summary": {"new": len(new_issues), "recurring": len(recurring_issues), "ongoing": len(ongoing_issues), "resolved": len(resolved_issues), "total_active": len(new_issues) + len(recurring_issues) + len(ongoing_issues)},
        "new_issues": new_issues, "recurring_issues": recurring_issues, "ongoing_issues": ongoing_issues, "resolved_issues": resolved_issues,
        "daily_summary_due": _is_daily_due(), "weekly_summary_due": _is_weekly_due(),
    }
    print("=== HEALTH-STATE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Диета L3-промпта (2026-08-20): Netdata-тренды — тяжёлый блок (~130 строк JSON),
    # нужный ТОЛЬКО при диагностике активной проблемы или на дайджесте. При чистоте
    # (total_active==0, дайджест не due) LLM всё равно ответит [SILENT] и тренды не
    # прочитает — не грузим их в контекст каждый час.
    need_trends = (report["summary"]["total_active"] > 0
                   or report["daily_summary_due"]
                   or report["weekly_summary_due"])
    if need_trends:
        print("\n=== NETDATA TRENDS (last hour) ===")
        try:
            trends = collect_netdata_trends()
            print(json.dumps(trends, ensure_ascii=False, indent=2))
        except Exception as e:
            print(json.dumps({"error": f"Netdata unavailable: {e}"}, ensure_ascii=False))
    print("\n=== WATCHDOG ALERTS (L1, last 24h) ===")
    print(json.dumps(collect_watchdog_alerts(), ensure_ascii=False, indent=2))
    print("\n=== RAW METRICS ===")
    print(metrics_output)

def _is_daily_due():
    hour = NOW.hour
    today = NOW.strftime("%Y-%m-%d")
    return hour == 23 and state.get("daily_summary_sent") != today

def _is_weekly_due():
    if NOW.weekday() != 6:
        return False
    hour = NOW.hour
    week = NOW.strftime("%Y-W%W")
    return hour == 23 and state.get("weekly_summary_sent") != week

# ═══════════════════════════════════════════════════════════════════════════
# 6. Обновление состояния
# ═══════════════════════════════════════════════════════════════════════════

def update_state():
    new_state = {"version": 1, "last_check": NOW_ISO, "check_count": state.get("check_count", 0) + 1, "issues": {}, "daily_summary_sent": state.get("daily_summary_sent"), "weekly_summary_sent": state.get("weekly_summary_sent"), "escalations": state.get("escalations", {})}
    for issue_id, info in truly_active.items():
        prev = known.get(issue_id, {})
        new_state["issues"][issue_id] = {"first_seen": prev.get("first_seen", NOW_ISO), "last_seen": NOW_ISO, "count": prev.get("count", 0) + 1, "status": "active", "severity": info["severity"], "description": info["description"], "reported": prev.get("reported", False)}
    for issue_id, info in auto_resolved_now.items():
        prev = known.get(issue_id, {})
        new_state["issues"][issue_id] = {**prev, "status": "resolved", "resolution": "decay"}
    for issue_id, prev in known.items():
        if issue_id not in truly_active and issue_id not in auto_resolved_now and prev.get("status") == "active":
            new_state["issues"][issue_id] = {**prev, "status": "resolved"}
    for issue_id, prev in known.items():
        if issue_id not in new_state["issues"]:
            new_state["issues"][issue_id] = prev
    if _is_daily_due():
        new_state["daily_summary_sent"] = NOW.strftime("%Y-%m-%d")
    if _is_weekly_due():
        new_state["weekly_summary_sent"] = NOW.strftime("%Y-W%W")
    with open(STATE_FILE, "w") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)
    print(f"STATE_UPDATED: {NOW_ISO}", file=sys.stderr)

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    output_report()
    if "--no-update" not in sys.argv:
        update_state()
