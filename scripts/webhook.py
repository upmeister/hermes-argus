#!/usr/bin/env python3
"""Обработчики мониторинг-бота @ceo_of_monitoring_bot — ИМПОРТИРУЕМАЯ БИБЛИОТЕКА.

С 2026-08-18 этот файл — НЕ веб-сервер, а модуль с логикой кнопок/команд,
который импортирует long-polling сервис `monitoring-bot-poller.py`
(`import webhook; webhook.handle_callback_query(...)`).

Историческая справка (чтобы агенты не путались, прояснено 2026-08-20):
- Раньше здесь был Flask-сервер `webhook-monitoring.service` (Gunicorn :8443)
  с HTTP-эндпоинтами:
    POST /webhook/monitoring        (Telegram webhook, X-Telegram-Bot-Api-Secret-Token)
    POST /webhook/monitoring/alarm  (Netdata, X-Netdata-Secret)
- 2026-08-18: Telegram-приём переехал на long-polling (monitoring-bot-poller.service,
  getUpdates через telegram-smart-proxy 8444). Webhook снят; getWebhookInfo.url пуст.
- Netdata НЕ ходит в /webhook/monitoring/alarm — SEND_CUSTOM="NO", алерты идут
  напрямую в Telegram через 8444 (systemd override HTTPS_PROXY).
- 2026-08-20: оба HTTP-эндпоинта и spawn_hermes_agent удалены как мёртвые;
  webhook-monitoring.service отключён. Файл остался чистой библиотекой для poller'а.
"""

import json
import os
import subprocess
import threading
from datetime import datetime, timezone
import time as _time

# Секреты больше не используются здесь (эндпоинты удалены), но оставлены как
# документированные переменные на случай возврата HTTP-приёма.
# WEBHOOK_SECRET_TOKEN / NETDATA_WEBHOOK_SECRET — в .env (см. webhook-monitoring.service legacy)

# Загрузка конфигурации
BOT_TOKEN = os.environ.get("WATCHDOG_BOT_TOKEN", "")
CHAT_ID = os.environ.get("WATCHDOG_CHAT_ID", "@WATCHDOG_CHAT_ID@")
ALLOWED_USER_ID = os.environ.get("WATCHDOG_ALLOWED_USER_ID", "").strip()
HERMES_BIN = "@HERMES_BIN@"

# Rate-limit для «🚫 нет доступа» ответов неавторизованным.
_DENY_LOG: dict[str, float] = {}
_DENY_COOLDOWN_S = 60.0

# ── Telegram API helpers ────────────────────────────────────────────────

def tg_api(method: str, data: dict) -> dict:
    """Вызов Telegram Bot API."""
    import urllib.request
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def send_message(text: str, silent: bool = False, reply_markup: dict = None):
    """Отправка сообщения в мониторинг-чат."""
    data = {"chat_id": CHAT_ID, "text": text}
    if silent:
        data["disable_notification"] = True
    if reply_markup:
        data["reply_markup"] = reply_markup
    return tg_api("sendMessage", data)

def send_message_to(chat_id, text: str):
    """Отправка в произвольный chat_id (для отказов до попытки auth)."""
    return tg_api("sendMessage", {
        "chat_id": chat_id, "text": text, "disable_notification": True
    })

def answer_callback(query_id: str, text: str = ""):
    """Ответ на callback_query (убирает «часики» на кнопке)."""
    return tg_api("answerCallbackQuery", {
        "callback_query_id": query_id,
        "text": text
    })

def _deny_or_passthrough(user_id, chat_id=None, callback_id=None):
    """Гейт авторизации + rate-limited 'нет доступа'.

    True  → пользователь авторизован, продолжай обычную обработку.
    False → отказ отправлен (или проглочен по cooldown), ничего не делай.
    """
    if not ALLOWED_USER_ID or str(user_id) == ALLOWED_USER_ID:
        return True
    key = str(user_id)
    now = _time.time()
    last = _DENY_LOG.get(key, 0.0)
    if now - last < _DENY_COOLDOWN_S:
        # Cooldown: глушим и кнопочный ответ (если был).
        if callback_id:
            try: answer_callback(callback_id, "🚫 нет доступа")
            except Exception: pass
        return False
    _DENY_LOG[key] = now
    if chat_id:
        try: send_message_to(chat_id, "🚫 У вас нет доступа к этому боту.")
        except Exception: pass
    if callback_id:
        try: answer_callback(callback_id, "🚫 нет доступа")
        except Exception: pass
    return False

# ── Changelog ─────────────────────────────────────────────────────────────

CHANGELOG_FILE = os.path.expanduser("~/.hermes/logs/infra-changelog.md")

def log_to_changelog(action: str, detail: str = ""):
    """Записывает действие пользователя в infra-changelog.md."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = (
        f"\n### [{now}] Пользователь: {action}\n"
        f"**Файлы:** —\n"
        f"**Причина:** действие через мониторинг-бот\n"
        f"**Ожидаемое воздействие:** {detail}\n"
        f"**Как проверить:** systemctl status / логи\n"
        f"**Связанные issue:** —\n"
        f"**Статус:** applied\n"
    )
    try:
        with open(CHANGELOG_FILE, "a") as f:
            f.write(entry)
    except Exception:
        pass

# ── Обработчики команд ──────────────────────────────────────────────────

def handle_restart_service(unit: str, logfile: str) -> str:
    """Fast-path рестарт systemd-юнита БЕЗ LLM (P0.3): restart → wait active → tail лога.

    Работает даже когда провайдеры моделей лежат — не зависит от агента."""
    import time
    try:
        r = subprocess.run(["systemctl", "--user", "restart", unit],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return f"❌ systemctl restart {unit} rc={r.returncode}: {r.stderr.strip()[:200]}"
        for _ in range(6):  # до 30 секунд
            time.sleep(5)
            st = subprocess.run(["systemctl", "--user", "is-active", unit],
                                capture_output=True, text=True, timeout=5).stdout.strip()
            if st == "active":
                tail = subprocess.run(["tail", "-5", logfile],
                                      capture_output=True, text=True, timeout=5).stdout.strip()
                return f"✅ {unit} перезапущен и активен.\n<pre>{tail[-400:]}</pre>"
        return f"⚠️ {unit} перезапущен, но статус не подтверждён за 30с"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def handle_restart_gateway() -> str:
    """Перезапуск gateway: fast-path, без LLM."""
    return handle_restart_service("hermes-gateway", "@HERMES_DIR@/logs/gateway.log")

def handle_restart_dashboard() -> str:
    """Перезапуск dashboard: fast-path, без LLM (опыт 08.08: висел 1.5ч)."""
    return handle_restart_service("hermes-dashboard", "@HERMES_DIR@/logs/gui.log")

def handle_silence_1h() -> str:
    """Режим тишины на 1 час: если уже активен — сброс."""
    remaining = _silence_remaining()
    if remaining > 0:
        # Уже есть тишина — сбрасываем
        try:
            sf = os.path.expanduser("~/.hermes/logs/auto-remediate-state/silence-until.txt")
            with open(sf, "w") as f:
                f.write("0")
        except:
            pass
        return "\U0001f50a Тишина сброшена. Алерты снова активны."
    
    silence_until = int(datetime.now(timezone.utc).timestamp() + 3600)
    state_dir = os.path.expanduser("~/.hermes/logs/auto-remediate-state")
    os.makedirs(state_dir, exist_ok=True)
    with open(f"{state_dir}/silence-until.txt", "w") as f:
        f.write(str(silence_until))
    return "\U0001f515 Алерты приглушены на 1 час"

def handle_show_logs(lines: int = 20) -> str:
    """Показать последние строки gateway.log."""
    try:
        result = subprocess.run(
            ["tail", f"-{lines}", "@HERMES_DIR@/logs/gateway.log"],
            capture_output=True, text=True, timeout=5
        )
        return f"📋 Последние {lines} строк gateway.log:\n<pre>{result.stdout[-1500:]}</pre>"
    except Exception as e:
        return f"❌ Не удалось прочитать логи: {e}"

def handle_health_status() -> str:
    """Краткий статус сервера."""
    try:
        ram = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5).stdout
        ram_line = [l for l in ram.splitlines() if l.startswith("Mem:")]
        ram_str = " ".join(ram_line[0].split()[2:4]) if ram_line else "?"

        swap = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5).stdout
        swap_line = [l for l in swap.splitlines() if l.startswith("Swap:")]
        swap_str = " ".join(swap_line[0].split()[2:4]) if swap_line else "?"

        load = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5).stdout
        load_str = load.split("load average:")[-1].strip() if "load average:" in load else "?"

        gw = subprocess.run(["systemctl", "--user", "is-active", "hermes-gateway"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        dash = subprocess.run(["systemctl", "--user", "is-active", "hermes-dashboard"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        
        return (
            f"🖥 **@HOSTNAME@**\n"
            f"RAM: {ram_str} | Swap: {swap_str} | Load:{load_str}\n"
            f"Gateway: {gw} | Dashboard: {dash}\n\n"
            f"{handle_kanban_snapshot()}"
        )
    except Exception as e:
        return f"❌ Ошибка: {e}"

def handle_network_status() -> str:
    """Текущий путь Telegram (path-manager state) + статус прокси."""
    try:
        state = {}
        state_path = os.path.expanduser("~/.hermes/state/telegram-path-state.json")
        with open(state_path) as f:
            state = json.load(f)
        mode = state.get("mode", "?")
        detail = state.get("detail", "")
        since = state.get("since", "")
        smart = subprocess.run(["systemctl", "--user", "is-active", "telegram-smart-proxy"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        ocp = subprocess.run(["systemctl", "--user", "is-active", "opencode-smart-proxy"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        mode_icon = {"direct": "🟢", "warp": "🔵", "vless": "🟣", "tor": "🟠", "blocked": "🔴"}.get(mode, "⚪")
        return (f"🛜 Telegram path: {mode_icon} **{mode}**{(' (' + detail + ')') if detail else ''}\n"
                f"с {since[:19]}\n"
                f"smart-proxy: {smart} | opencode-proxy: {ocp}")
    except Exception as e:
        return f"❌ Ошибка: {e}"

def handle_kanban_snapshot() -> str:
    """Канбан-снапшот: счётчики по статусам + активные задачи (running/ready)."""
    try:
        # HERMES_BIN с абсолютным путём: в PATH systemd user-юнитов нет venv/bin
        # (голый "hermes" → Errno 2, инцидент 18.08)
        r = subprocess.run([HERMES_BIN, "kanban", "list"],
                           capture_output=True, text=True, timeout=30,
                           env={**os.environ, "HERMES_HOME": "@HOME_DIR@/.hermes"})
        from collections import Counter
        counts = Counter()
        active = []
        icon_map = {"✓": "done", "●": "running", "▶": "ready", "⊘": "blocked",
                    "?": "triage", "⏳": "scheduled"}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            st = icon_map.get(parts[0], parts[0])
            counts[st] += 1
            if st in ("running", "ready"):
                active.append(line.strip()[:80])
        summary = " | ".join(f"{k}:{v}" for k, v in counts.items()) or "пусто"
        out = f"🗂 **Kanban:** {summary}"
        for a in active[:5]:
            out += f"\n  {a}"
        return out
    except Exception as e:
        return f"❌ Ошибка: {e}"


# ── Новые обработчики (2026-09-06) ────────────────────────────────────

_CHECK = "✅"
_CROSS = "❌"
_WARN = "⚠️"

def _silence_remaining() -> int:
    """Сколько секунд осталось тишины."""
    sf = os.path.expanduser("~/.hermes/logs/auto-remediate-state/silence-until.txt")
    try:
        with open(sf) as f:
            until = int(f.read().strip())
        return max(0, until - int(_time.time()))
    except:
        return 0


def handle_watchdog_status() -> str:
    """Статус всех уровней мониторинга (сервисы, cron, analyzer, heartbeat)."""
    try:
        h = os.path.expanduser("~/.hermes")
        lines = []
        for s in ["hermes-dashboard", "hermes-gateway", "telegram-smart-proxy",
                   "monitoring-bot-poller"]:
            ok = subprocess.run(
                ["systemctl", "--user", "is-active", s],
                capture_output=True, text=True, timeout=5
            ).stdout.strip() == "active"
            lines.append(f"{_CHECK if ok else _CROSS} Сервис {s}")
        # Netdata — SYSTEM-юнит (не user) и биндится на HERMES_HOST, поэтому
        # проверяем HTTP API, а не systemctl --user (фикс 2026-09-07: ложный
        # негатив «сломана» при живой netdata на Tailscale IP).
        code = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "6",
             "http://@HERMES_HOST@:@NETDATA_PORT@/api/v1/info"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip() or "000"
        lines.append(f"{_CHECK if code == '200' else _CROSS} Netdata API (HTTP {code})")
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        for name in ["hermes-watchdog", "gateway-liveness", "dashboard-liveness"]:
            lines.append(f"{_CHECK if name in cron.stdout else _CROSS} Cron {name}")
        try:
            with open(f"{h}/logs/health-state.json") as f:
                hs = json.load(f)
            last = hs.get("last_check", "?")[:19]
            active = [k for k, v in hs.get("issues", {}).items() if v.get("status") == "active"]
            lines.append(f"{_CHECK} Analyzer (last: {last})")
            if active:
                lines.append(f"{_WARN} Issues: {', '.join(active)}")
        except:
            lines.append(f"{_CROSS} Analyzer: health-state.json не найден")
        hb = f"{h}/hermes-infra/heartbeat.txt"
        if os.path.exists(hb):
            age = int(_time.time()) - os.path.getmtime(hb)
            lines.append(f"{_CHECK if age < 900 else _WARN} Heartbeat ({age}s ago)")
        return "\n".join(lines)
    except Exception as e:
        return f"{_CROSS} Ошибка: {e}"


def handle_integrations_check() -> str:
    """Быстрая проверка интеграций."""
    try:
        r = subprocess.run(
            [os.path.expanduser("~/.hermes/scripts/health-check-integrations.sh"), "--quick"],
            capture_output=True, text=True, timeout=30
        )
        out = r.stdout.strip()
        if not out or "все в порядке" in out.lower():
            return f"{_CHECK} Все интеграции в порядке"
        problems = [l for l in out.split("\n") if _CROSS in l or _WARN in l]
        if problems:
            return f"{_WARN} **Проблемы:**\n" + "\n".join(problems[:5])
        return f"{_CHECK} Все интеграции в порядке"
    except Exception as e:
        return f"{_CROSS} Ошибка: {e}"


def handle_integrations_all() -> str:
    """Full grouped integration view from the health-check-v2 report + registry.

    Reads the cached hourly report (cron :20) instead of re-running checks:
    a live re-run is C2 (deep check) territory. Falls back to a hint when the
    report has not been generated yet. Plain text only — the poller's
    send_message sends without parse_mode.
    """
    try:
        with open(os.path.expanduser("~/.hermes/state/health-check-v2-report.json"),
                  encoding="utf-8") as f:
            report = json.load(f)
    except Exception:
        return (f"{_WARN} Отчёт health-check-v2 недоступен.\n"
                "Он создаётся cron-обёрткой (ежечасно :20) или вручную:\n"
                "~/scripts/health-check-v2-wrapper.sh")

    try:
        import yaml
        with open(os.path.expanduser("~/.hermes/state/registry.yaml"),
                  encoding="utf-8") as f:
            registry = yaml.safe_load(f) or {}
    except Exception:
        registry = {}
    kit_group = {k.get("key"): k.get("group", "watchdog")
                 for k in registry.get("kit_entries", []) if isinstance(k, dict)}
    free_models = report.get("free_models", {})

    marks = {"ok": "✅", "fail": "❌", "unconfigured": "⚪"}
    checks = report.get("checks", [])
    # Merge provider env + root http-alive checks into one line when healthy
    # (fix 2026-09-07: "provider X" + "provider X root" read as duplicates)
    ids = {c.get("id") for c in checks}
    root_ok = {c["id"][:-5]: c.get("detail", "") for c in checks
               if c.get("id", "").endswith("#http") and c.get("status") == "ok"}
    buckets: dict[str, list[str]] = {}
    for c in checks:
        cid, st = c.get("id", ""), c.get("status", "?")
        if cid.endswith("#http"):
            base = cid[:-5]
            if base in ids and c.get("status") == "ok":
                continue  # healthy root merged into the provider line below
        label = c.get("label", cid)
        detail = c.get("detail", "")
        if st == "fail":
            line = f"❌ {label} — {detail}"
        elif st == "unconfigured":
            line = f"⚪ {label} — не настроено (опционально)"
        else:
            line = f"✅ {label}"
            if cid in root_ok:
                line += f" · root {root_ok[cid]}"
        # free-tier hint on provider key checks (not on root http checks)
        if cid.startswith("provider:") and not cid.endswith("#http") \
                and c.get("primitive") == "env":
            pname = label.replace("provider ", "", 1)
            models = next((v for k, v in free_models.items()
                           if pname == k or pname.startswith(k)), None)
            if models:
                line += f" · free: {', '.join(models)}"
        if cid.startswith("kit:"):
            g = "kit:" + kit_group.get(cid[4:], "watchdog")
        else:
            g = cid.split(":", 1)[0]
        buckets.setdefault(g, []).append(line)

    titles = {"kit:watchdog": "🛡 Watchdog kit", "kit:proxy": "🌐 Proxy",
              "kit:infra": "🧰 Infra", "provider": "🤖 AI-провайдеры",
              "mcp": "🔌 MCP", "local": "🖥 Self-hosted", "envref": "🔑 Env-ключи"}
    age = ""
    try:
        age = datetime.fromisoformat(report.get("updated", "")).astimezone().strftime("%H:%M")
    except Exception:
        pass

    lines = [f"🩺 Интеграции — отчёт {age}" if age else "🩺 Интеграции",
             f"✅ {report.get('ok', 0)} · ❌ {report.get('fail', 0)} · "
             f"⚪ {report.get('unconfigured', 0)} из {report.get('total', 0)}"]
    for g, title in titles.items():
        items = buckets.get(g)
        if not items:
            continue
        lines.append("")
        lines.append(title)
        lines.extend(items[:20])
        if len(items) > 20:
            lines.append(f"…и ещё {len(items) - 20}")
    return "\n".join(lines)[:4000]


def handle_deep_check() -> str:
    """C2: deep AI check (chat max_tokens=1) by button/command.

    BUTTON-ONLY: never scheduled; chat calls are gated to known free models
    inside ai-deep-check.py. Runs synchronously — the poller dispatches each
    update in its own thread, so a long check does not block other commands.
    """
    try:
        r = subprocess.run(
            ["python3", os.path.expanduser("~/scripts/ai-deep-check.py")],
            capture_output=True, text=True, timeout=240)
        out = (r.stdout or "").strip()
        if not out:
            err = (r.stderr or "").strip()
            msg = f"пустой вывод (exit {r.returncode})"
            if err:
                msg += ": " + err[-200:]
            return f"{_CROSS} Deep check: {msg}"
        return "🧪 **Deep AI check**\n" + (out[-3500:] if len(out) > 3500 else out)
    except subprocess.TimeoutExpired:
        return f"{_CROSS} Deep check превысил таймаут 240с"
    except Exception as e:
        return f"{_CROSS} Ошибка: {e}"


def handle_uptime() -> str:
    """Аптайм сервера."""
    try:
        uptime = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5).stdout.strip()
        load = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True, timeout=5).stdout.strip().split()[:3]
        return f"\u23f1 **Аптайм:** {uptime}\n\U0001f4ca **Нагрузка:** {' '.join(load)}"
    except Exception as e:
        return f"{_CROSS} Ошибка: {e}"


_REBOOT_PENDING = {}

def handle_reboot(text: str) -> str:
    """Первый шаг: запрос подтверждения."""
    _REBOOT_PENDING["confirm"] = {"expires": _time.time() + 60}
    return (f"{_WARN} **Подтвердите перезагрузку сервера!**\n\n"
            "Напишите `/reboot_confirm` в течение 60 секунд.\n"
            "После подтверждения — перезагрузка через 1 минуту.")


def handle_reboot_confirm() -> str:
    """Второй шаг: подтверждение ребута."""
    try:
        subprocess.run(["sudo", "-n", "shutdown", "-r", "+1"],
                       capture_output=True, text=True, timeout=10, check=True)
        return f"{_WARN} **Перезагрузка через 1 минуту!** Сервер будет недоступен ~2-5 мин."
    except subprocess.CalledProcessError as e:
        return f"{_CROSS} Ошибка: {e.stderr.strip() or 'нет прав sudo'}"


def handle_reboot_cancel() -> str:
    """Отмена ребута."""
    subprocess.run(["sudo", "-n", "shutdown", "-c"], capture_output=True, text=True, timeout=5)
    return f"{_CHECK} Перезагрузка отменена."


def menu_keyboard():
    """Постоянная клавиатура для команды /menu."""
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4ca Статус", "callback_data": "health"},
                {"text": "\U0001f6dc Сеть", "callback_data": "network"},
            ],
            [
                {"text": "\U0001f50d Мониторинг", "callback_data": "watchdog"},
                {"text": "\u23f1 Аптайм", "callback_data": "uptime"},
            ],
            [
                {"text": "\U0001f504 Gateway", "callback_data": "restart_gw"},
                {"text": "\U0001f504 Dashboard", "callback_data": "restart_dash"},
            ],
            [
                {"text": "\U0001f504 All", "callback_data": "restart_all"},
                {"text": "\U0001f50c Интеграции", "callback_data": "integrations"},
            ],
            [
                {"text": "\U0001f4cb Интеграции (all)", "callback_data": "integrations_all"},
            ],
            [
                {"text": "\U0001f9ea Deep AI", "callback_data": "deep_ai"},
                {"text": "\U0001f4cb Логи", "callback_data": "show_logs"},
            ],
            [
                {"text": "\U0001f507 Silence", "callback_data": "silence_1h"},
            ],
        ]
    }

# ── Inline-клавиатуры ───────────────────────────────────────────────────

def alert_keyboard():
    """Клавиатура для критических алертов (актуализирована 2026-08-15).

    ⚠️ Этот набор — канон. Дублируется в bash-скриптах (hermes-watchdog.sh,
    send-monitoring-report.sh) — при изменении обновлять ВСЕ ТРИ места."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Restart Gateway", "callback_data": "restart_gw"},
                {"text": "🔄 Restart Dashboard", "callback_data": "restart_dash"},
            ],
            [
                {"text": "🛜 Сеть", "callback_data": "network"},
                {"text": "ℹ️ Статус", "callback_data": "health"},
            ],
            [
                {"text": "📋 Логи", "callback_data": "show_logs"},
                {"text": "👀 Игнорировать 1ч", "callback_data": "silence_1h"},
            ],
        ]
    }

def handle_callback_query(query: dict) -> None:
    """Обработка нажатия inline-кнопки. Единая точка для webhook И poller'а.

    (Бот в polling-режиме: webhook не установлен, callback_query приходит
    в getUpdates → poller зовёт эту функцию напрямую.)"""
    action = query.get("data", "")
    query_id = query.get("id", "")
    if query_id:
        answer_callback(query_id, "Принято!")
    if action == "restart_gw":
        log_to_changelog("Перезапуск gateway (кнопка)", "fast-path, без LLM")
        send_message(f"🔄 **Restart Gateway:**\n{handle_restart_gateway()}", silent=True)
    elif action == "restart_dash":
        log_to_changelog("Перезапуск dashboard (кнопка)", "fast-path, без LLM")
        send_message(f"🔄 **Restart Dashboard:**\n{handle_restart_dashboard()}", silent=True)
    elif action == "restart_all":
        log_to_changelog("Перезапуск gateway+dashboard (кнопка)", "fast-path, без LLM")
        send_message(f"🔄 **Restart All:**\n{handle_restart_gateway()}\n---\n{handle_restart_dashboard()}", silent=True)
    elif action == "show_logs":
        send_message(handle_show_logs(), silent=True)
    elif action == "network":
        send_message(handle_network_status(), silent=True)
    elif action == "health":
        send_message(handle_health_status(), silent=True)
    elif action == "silence_1h":
        send_message(handle_silence_1h(), silent=True)
    elif action == "watchdog":
        send_message(handle_watchdog_status(), silent=True)
    elif action == "integrations":
        send_message(handle_integrations_check(), silent=True)
    elif action == "integrations_all":
        send_message(handle_integrations_all(), silent=True)
    elif action == "deep_ai":
        log_to_changelog("Deep AI check (кнопка)", "chat max_tokens=1, free-models gated")
        send_message("🧪 Deep check запущен (до ~2 мин)...", silent=True)
        send_message(handle_deep_check(), silent=True)
    elif action == "uptime":
        send_message(handle_uptime(), silent=True)
    elif action == "reboot_confirm":
        send_message(handle_reboot_confirm(), silent=True)
    elif action == "reboot_cancel":
        send_message(handle_reboot_cancel(), silent=True)

