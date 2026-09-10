"""Паттерны проблем и их детекция в логах и метриках.

Важно:
- gateway_crash НЕ должен ловить штатный SIGTERM/restart
- Учитываются только события в lookback-окне (иначе старый tail держит issue forever)
"""
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time

# Часовой пояс сервера: gateway.log пишет в локальном времени.
# Преобразуем в UTC для корректного сравнения с now (UTC).
LOCAL_TZ = timezone(timedelta(seconds=-time.timezone))

GATEWAY_LOG = Path(__file__).resolve().parent.parent / "logs" / "gateway.log"

# Глобальный lookback: события старше этого не создают active issue.
# Decay всё равно может resolve'ить по last_error, но лучше не поднимать stale matches.
DEFAULT_LOOKBACK_HOURS = 24

PATTERNS = {
    "telegram_api_error": {
        # Только ошибки, указывающие на реальную проблему (не transient RKN-блокировки).
        # Исключаем: polling degraded (heartbeat), ВСЕ попытки переподключения
        # (attempt N/10), INFO-строки recovery, updater.stop таймауты,
        # _redact_telegram_error_text, reconnect failed — всё это self-healing.
        # Плюс failover-механизм telegram_network: "Primary connection failed;
        # trying fallback IPs", "Fallback IP ... failed", "Sticky fallback ...
        # resetting" — это НОРМАЛЬНАЯ работа при РКН-волнах (334 из 386 матчей
        # за историю — этот шум), не ошибка. Исключение attempt \d/ намеренно
        # НЕ ловит attempt 10/10 — последняя попытка перед рестартом gateway.
        # Фикс 2026-09-08 (C6-отчёт Питны + находка Влада 09.09): новый формат
        # telegram_network не матчится старыми exclusion-подстроками —
        # 'Sticky Telegram path X failed; re-walking IPv4 literals' и
        # 'IPv4 Telegram API IP X failed:' держали issue активным до 6ч
        # (ложный 'Telegram сломан' в /watchdog). Добавлены в исключения.
        # Также исключаем "MarkdownV2 parse failed, falling back to plain text" —
        # graceful-fallback форматирования (сообщение всё равно доставлено),
        # НЕ API-ошибка (фикс 18.08: 2 ложных матча 09:36).
        "pattern": r"\b(telegram|TELEGRAM)\b(?!.*(?:polling degraded|network error \(attempt \d/|restarted after network error|updater\.stop\(\) timed out|_redact_telegram_error_text|reconnect failed|retrying|trying fallback IPs|Fallback IP \S+ failed|Sticky fallback|MarkdownV2 parse failed|falling back to plain text|\d+ chars)).*(error|fail|timed out|429|Too Many Requests|send_path_degraded)",
        "source": "gateway_log",
        "severity": "warning",
        # Строчный фильтр шума: lookahead не видит подстроки ДО якоря
        # "Telegram" (кейс 2026-09-08: "IPv4 Telegram API IP X failed" —
        # исключение "IPv4 Telegram API IP" оставалось позади матча).
        "exclude_any": [
            "polling degraded", "network error (attempt",
            "restarted after network error", "updater.stop() timed out",
            "_redact_telegram_error_text", "reconnect failed", "retrying",
            "trying fallback IPs", "Fallback IP", "Sticky fallback",
            "Sticky Telegram path", "re-walking IPv4 literals",
            "IPv4 Telegram API IP", "MarkdownV2 parse failed",
            "falling back to plain text",
        ],
        "description": "Ошибки Telegram API (rate limit, timeout, сетевые)",
        "lookback_hours": 6,
    },
    "gateway_crash": {
        # Только реальные падения/OOM/traceback. НЕ SIGTERM (штатный restart/stop).
        "pattern": r"(Traceback \(most recent call last\)|FATAL|oom-kill|Killed process|Out of memory|panic:|segfault|exit code (?!0)\d+)",
        "source": "gateway_log",
        "severity": "critical",
        "description": "Критические ошибки / падения gateway",
        "lookback_hours": 12,
    },
    "gateway_restart_loop": {
        # Частые SIGTERM/restart — отдельный сигнал, не «crash»
        "pattern": r"Received SIGTERM — initiating shutdown",
        "source": "gateway_log",
        "severity": "warning",
        "description": "Серия перезапусков gateway (SIGTERM)",
        # Короткое окно: исторические рестарты не должны висеть часами
        "lookback_hours": 2,
        "min_matches": 3,
    },
    "disk_high": {
        "pattern": r"disk.*(8[5-9]|9[0-9])%",
        "source": "metrics",
        "severity": "warning",
        "description": "Диск заполнен >85%",
    },
    "network_guard_issue": {
        # Сетевые инварианты нарушены / guard вмешался (B1). Строка из collect-metrics.sh.
        "pattern": r"Network guard:.*(dns_ok=false|rules_ok=false|e2e=.*000|fails=[1-9])",
        "source": "metrics",
        "severity": "warning",
        "description": "Сетевые инварианты нарушены (guard зафиксировал поломку/вмешательство)",
        "lookback_hours": 2,
    },
    "swap_high": {
        "pattern": r"swap.*([5-9][0-9]|100)%",
        "source": "metrics",
        "severity": "warning",
        "description": "Swap использован >50%",
    },
    "oom_event": {
        "pattern": r"(Out of memory|oom-kill|Killed process)",
        "source": "metrics",
        "severity": "critical",
        "description": "OOM-killer сработал",
    },
    "hermes_process_missing": {
        "pattern": r"Процессов Hermes не найдено",
        "source": "metrics",
        "severity": "critical",
        "description": "Процесс Hermes не запущен",
    },
    "hermes_spawn_storm": {
        # Спавн-шторм: канбан-воркеры/циклические агенты (hermes -p ...).
        # В норме 0 воркеров; базовые сервисы НЕ считаются (10 процессов ~/.hermes — норма).
        # Инцидент 2026-08-08: 14 воркеров × ~110MB → OOM на 2GB VPS.
        "pattern": r"Воркеров \(kanban/агенты\): ([3-9]|[1-9][0-9]+)",
        "source": "metrics",
        "severity": "critical",
        "description": "Спавн-шторм воркеров (канбан/агенты) — возможен OOM",
        "lookback_hours": 2,
    },
    "port_closed": {
        "pattern": r"(port.*(?!19999).*closed|connection refused.*9119)",
        "source": "metrics",
        "severity": "critical",
        "description": "Порт Hermes dashboard не отвечает",
    },
    "fail2ban_jail": {
        "pattern": r"fail2ban.*(ban|jail|error)",
        "source": "metrics",
        "severity": "info",
        "description": "Активность fail2ban (баны)",
    },
    "hf_download_stuck": {
        "pattern": r"\.incomplete",
        "source": "metrics",
        "severity": "warning",
        "description": "HuggingFace model download in progress (incomplete files)",
    },
    "github_auth_failure": {
        "pattern": r"(401|403).*github|GH_TOKEN.*invalid|Bad credentials",
        "source": "gateway_log",
        "severity": "critical",
        "description": "GitHub-токен недействителен (401/403)",
        "lookback_hours": 6,
    },
    "telegram_bot_disconnected": {
        "pattern": r"send_path_degraded|polling.*error.*5[0-9][0-9]",
        "source": "gateway_log",
        "severity": "critical",
        "description": "Telegram-бот не может подключиться / send_path_degraded",
        # Transient network blips: если 2ч нет повторов — не держим active
        "lookback_hours": 2,
    },
    "api_key_expired": {
        "pattern": r"(API key.*expired|key.*invalid|401.*Unauthorized|403.*Forbidden).*api",
        "source": "gateway_log",
        "severity": "critical",
        "description": "API-ключ истёк или недействителен",
        "lookback_hours": 6,
    },
    "webhook_down": {
        "pattern": r"(Connection refused|Connection reset).*8443",
        "source": "gateway_log",
        "severity": "critical",
        "description": "Webhook-сервер не отвечает (порт 8443)",
        "lookback_hours": 2,
    },
    "cron_corrupted": {
        "pattern": r"crontab.*(0 tasks|empty|no crontab)",
        "source": "metrics",
        "severity": "critical",
        "description": "Crontab пуст или повреждён",
    },
}


def _parse_ts(line: str):
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
    if not m:
        return None
    try:
        # gateway.log пишет в локальном времени сервера; конвертируем в UTC
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
        return ts.astimezone(timezone.utc)
    except Exception:
        return None


def find_issues(metrics: str, now: datetime = None) -> dict:
    """Сканирует метрики и логи на известные паттерны проблем."""
    if now is None:
        now = datetime.now(timezone.utc)

    found = {}
    log_lines = []
    if GATEWAY_LOG.exists():
        try:
            with open(GATEWAY_LOG) as f:
                log_lines = f.readlines()[-400:]
        except Exception:
            pass

    for issue_id, config in PATTERNS.items():
        source = config["source"]
        pattern = config["pattern"]
        min_matches = config.get("min_matches", 1)
        lookback = config.get("lookback_hours", DEFAULT_LOOKBACK_HOURS)
        cutoff = now - timedelta(hours=lookback)

        if source == "metrics":
            matches = re.findall(pattern, metrics, re.IGNORECASE)
            if len(matches) < min_matches:
                continue
            found[issue_id] = {
                "detected": True,
                "match_count": len(matches),
                "severity": config["severity"],
                "description": config["description"],
                "sample": str(matches[:3]),
                # metrics — текущий срез, считаем «сейчас»
                "first_error": now.replace(microsecond=0).isoformat(),
                "last_error": now.replace(microsecond=0).isoformat(),
                "error_window_hours": 0.0,
            }
            continue

        # gateway_log: только свежие строки в lookback
        timeline = []
        matched_lines = []
        exclude_any = tuple(config.get("exclude_any", ()))
        for line in log_lines:
            if exclude_any and any(x in line for x in exclude_any):
                continue
            if not re.search(pattern, line, re.IGNORECASE):
                continue
            ts = _parse_ts(line)
            if ts is None:
                continue
            if ts < cutoff:
                continue
            timeline.append(ts)
            matched_lines.append(line.strip()[:200])

        if len(timeline) < min_matches:
            continue

        first = min(timeline)
        last = max(timeline)
        hours = round((last - first).total_seconds() / 3600, 2)
        info = {
            "detected": True,
            "match_count": len(timeline),
            "severity": config["severity"],
            "description": config["description"],
            "sample": str(matched_lines[:3]),
            "first_error": first.replace(tzinfo=None).isoformat(sep="T", timespec="seconds")
            if first.tzinfo
            else first.isoformat(sep="T", timespec="seconds"),
            # Храним naive local-log style + обеспечим UTC в decay через replace
            "last_error": last.replace(microsecond=0).isoformat(),
            "error_window_hours": hours,
        }
        # Нормализуем last_error/first_error в ISO UTC-naive как раньше (decay добавит UTC)
        info["first_error"] = first.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        info["last_error"] = last.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        if hours > 0:
            info["density_per_hour"] = round(len(timeline) / hours, 1)
        found[issue_id] = info

    return found
