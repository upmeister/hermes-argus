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

import html
import json
import os
import re
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

def send_message(text: str, silent: bool = False, reply_markup: dict = None,
                 html_mode: bool = False):
    """Отправка сообщения в мониторинг-чат."""
    data = {"chat_id": CHAT_ID, "text": text}
    if html_mode:
        data["parse_mode"] = "HTML"
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

def handle_silence(hours: int = 1) -> str:
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
    
    silence_until = int(datetime.now(timezone.utc).timestamp() + hours * 3600)
    state_dir = os.path.expanduser("~/.hermes/logs/auto-remediate-state")
    os.makedirs(state_dir, exist_ok=True)
    with open(f"{state_dir}/silence-until.txt", "w") as f:
        f.write(str(silence_until))
    return "\U0001f515 Алерты приглушены на 1 час"

def handle_start() -> str:
    """Branded onboarding: what Argus is + live status from the cached report."""
    lines = ["👁 Argus — страж Hermes Agent.",
             "Слежу за интеграциями, провайдерами и живучестью сервера:",
             "• discover следит за config.yaml (systemd.path + cron)",
             "• health-check проверяет провайдеров, MCP и ключи (cron :20)",
             "• watchdog/liveness чинят сервисы и алертят",
             "• heartbeat стучится наружу (cronping/gh)", ""]
    try:
        with open(os.path.expanduser(
                "~/.hermes/state/health-check-v2-report.json"), encoding="utf-8") as f:
            report = json.load(f)
        age = datetime.fromisoformat(report.get("updated", "")).astimezone().strftime("%H:%M")
        lines.append(f"📡 Статус ({age}): {report.get('ok', 0)}/{report.get('total', 0)} ok"
                     f", {report.get('fail', 0)} fail — детали: /integrations_all")
    except Exception:
        lines.append("📡 Статус: отчёт ещё не готов — /integrations_all")
    lines.append("")
    lines.append("Действия: /menu · Навигация уже открыта внизу экрана.")
    return chr(10).join(lines)


def send_logs_messages(lines: int = 20) -> None:
    """C-phase 2: /logs with HTML <code> + line-chunked pagination.

    Log content is html-escaped (logs contain angle brackets and ampersands —
    HTML injection guard); each chunk stays under the TG 4096-char limit.
    NL is built via chr(10) so the source has no escape sequences to break."""
    NL = chr(10)
    try:
        result = subprocess.run(
            ["tail", f"-{lines}", "@HERMES_DIR@/logs/gateway.log"],
            capture_output=True, text=True, timeout=5
        )
        raw = (result.stdout or "").rstrip()
        esc = html.escape(raw) if raw else "(пусто — gateway.log пуст или отсутствует)"
        body_lines = esc.split(NL)
        header = f"📋 gateway.log — последние {lines} строк:"
        chunks, cur = [], ""
        for ln in body_lines:
            if len(cur) + len(ln) + 1 > 3400:
                chunks.append(cur)
                cur = ""
            cur += ln + NL
        if cur:
            chunks.append(cur)
        send_message(header)
        total = min(len(chunks), 3)
        for i, chunk in enumerate(chunks[:3]):
            tail_note = f"{NL}…часть {i + 1}/{total}" if total > 1 else ""
            send_message(f"<code>{chunk}</code>{tail_note}", html_mode=True)
        if len(chunks) > 3:
            send_message(f"⚠️ Лог длинный — показано 3/{len(chunks)} частей. "
                         f"Уменьшите объём: /logs 10", html_mode=True)
    except Exception as e:
        send_message(f"❌ Не удалось прочитать логи: {e}")


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
    """Статус стражи с честной семантикой: компоненты Argus vs Hermes-платформа.
    Отсутствие платформенного компонента — ⏸ (не установлен / требуется
    Hermes), а не ❌: Argus мониторит СУЩЕСТВУЮЩИЙ Hermes, не устанавливает."""
    NL = chr(10)
    h = os.path.expanduser("~/.hermes")
    hermes_installed = os.path.isdir(os.path.join(h, "hermes-agent"))

    def svc_status(unit: str) -> str:
        return subprocess.run(["systemctl", "--user", "is-active", unit],
                              capture_output=True, text=True, timeout=5
                              ).stdout.strip() or "unknown"

    def mark(st: str) -> str:
        if st == "active":
            return _CHECK
        if st == "not-found":
            return "⚪"
        return _CROSS

    lines = ["👁 Argus: статус стражи", "", "👁 Argus"]

    ok = svc_status("monitoring-bot-poller") == "active"
    lines.append(f"{_CHECK if ok else _CROSS} Сервис monitoring-bot-poller")

    cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
    for name in ["hermes-watchdog"]:
        lines.append(f"{_CHECK if name in cron.stdout else _CROSS} Cron {name}")

    if os.path.exists(os.path.join(h, "scripts", "health-analyzer.py")):
        try:
            with open(os.path.join(h, "logs", "health-state.json"), encoding="utf-8") as f:
                hs = json.load(f)
            last = hs.get("last_check", "?")[:19]
            active = [k for k, v in hs.get("issues", {}).items() if v.get("status") == "active"]
            lines.append(f"{_CHECK} Analyzer (last: {last})")
            if active:
                lines.append(f"{_WARN} Issues: {', '.join(active)}")
        except Exception:
            lines.append(f"{_CROSS} Analyzer: health-state.json не читается")
    else:
        lines.append("⚪ Analyzer не установлен (MODULE_ANALYZER)")

    hb = os.path.join(h, "hermes-infra", "heartbeat.txt")
    if os.path.exists(hb):
        age = int(_time.time()) - os.path.getmtime(hb)
        lines.append(f"{_CHECK if age < 900 else _WARN} Heartbeat ({age}s ago)")

    lines.append("")
    lines.append("🖥 Hermes-платформа")
    for sname in ["hermes-dashboard", "hermes-gateway", "telegram-smart-proxy"]:
        st = svc_status(sname)
        if st == "not-found" and not hermes_installed:
            lines.append(f"⚪ Сервис {sname} — не установлен (требуется Hermes)")
        else:
            lines.append(f"{mark(st)} Сервис {sname} ({st})")

    # Netdata: HTTP probe, оба адреса (бинд варьируется по установкам)
    nd = "000"
    for host in dict.fromkeys(["@HERMES_HOST@", "127.0.0.1"]):
        nd = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "6",
             f"http://{host}:@NETDATA_PORT@/api/v1/info"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip() or "000"
        if nd == "200":
            break
    if nd == "200":
        lines.append(f"{_CHECK} Netdata API (HTTP {nd})")
    elif hermes_installed:
        lines.append(f"{_CROSS} Netdata API (HTTP {nd})")
    else:
        lines.append(f"⚪ Netdata API (HTTP {nd}) — не настроен")

    for name in ["gateway-liveness", "dashboard-liveness"]:
        present = name in cron.stdout
        if hermes_installed:
            lines.append(f"{_CHECK if present else _CROSS} Cron {name}")
        else:
            lines.append(f"⚪ Cron {name} — требуется Hermes")

    return NL.join(lines)


def handle_integrations_check() -> str:
    """Quick status from the cached health-check-v2 report (fresh < 26h) —
    covers MCP and everything else the v2 engine sees. Falls back to the
    legacy --quick script when the report is missing or stale. The legacy
    --quick itself stays the watchdog L1 contract (untouched)."""
    now = _time.time()
    try:
        with open(os.path.expanduser("~/.hermes/state/health-check-v2-report.json"),
                  encoding="utf-8") as f:
            report = json.load(f)
        updated = datetime.fromisoformat(report.get("updated", "")).timestamp()
        if now - updated < 26 * 3600:
            fails = [c for c in report.get("checks", []) if c.get("status") == "fail"]
            age = datetime.fromisoformat(report["updated"]).astimezone().strftime("%H:%M")
            head = (f"🩺 Интеграции (отчёт {age}): "
                    f"{report.get('ok', 0)}/{report.get('total', 0)} ok")
            if not fails:
                return f"✅ Argus: {head} — всё в порядке"
            probs = [f"❌ {c.get('label')}: {c.get('detail')}" for c in fails[:8]]
            extra = len(fails) - 8
            if extra > 0:
                probs.append(f"…и ещё {extra}")
            return head + "\n" + "\n".join(probs)
    except Exception:
        pass
    # Legacy fallback (report missing or stale)
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
            if "endpoint" in detail:
                line += f" — {detail}"
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
        elif cid.startswith("envkey:"):
            g = "envkey:" + c.get("category", "setting")
        else:
            g = cid.split(":", 1)[0]
        buckets.setdefault(g, []).append(line)

    titles = {"kit:watchdog": "🛡 Watchdog kit", "kit:proxy": "🌐 Proxy",
              "kit:infra": "🧰 Argus Infra", "provider": "🤖 AI-провайдеры (custom)",
              "envkey:provider": "🤖 AI-провайдеры (built-in)",
              "envkey:tool": "🔧 Инструменты", "envkey:messaging": "💬 Messaging",
              "envkey:skill": "🧩 Навыки", "envkey:setting": "⚙️ Прочие ключи",
              "oauth": "🔐 OAuth-провайдеры",
              "mcp": "🔌 MCP", "local": "🖥 Self-hosted", "envref": "🔑 Env-refs"}
    age = ""
    try:
        age = datetime.fromisoformat(report.get("updated", "")).astimezone().strftime("%H:%M")
    except Exception:
        pass

    lines = [f"👁 Argus наблюдает — интеграции (отчёт {age})" if age else "👁 Argus наблюдает — интеграции",
             f"✅ {report.get('ok', 0)} · ❌ {report.get('fail', 0)} · "
             f"⚪ {report.get('unconfigured', 0)} из {report.get('total', 0)}"]
    ams = report.get("active_models") or []
    if ams:
        lines.append("")
        lines.append("🎯 Активные модели")
        for m in ams:
            lines.append(f"• {m.get('role')}: {m.get('provider')}/{m.get('model')}")
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
        # engine prints plain "[OK  ]/[FAIL]/[SKIP]" markers — replace with
        # emoji for the chat (Vlad, 2026-09-08)
        out = (out.replace("[OK  ]", "✅").replace("[FAIL]", "❌")
                  .replace("[SKIP]", "⚪"))
        return "🧪 **Deep AI check**\n" + (out[-3500:] if len(out) > 3500 else out)
    except subprocess.TimeoutExpired:
        return f"{_CROSS} Deep check превысил таймаут 240с"
    except Exception as e:
        return f"{_CROSS} Ошибка: {e}"


def _mask(value: str) -> str:
    """Mask a secret: show only that it is set + last 4 chars."""
    v = (value or "").strip().strip('"\'')
    if not v:
        return "— не задано"
    return "****" + v[-4:] if len(v) > 4 else "****"


def handle_settings() -> str:
    """S1 (plan §13): read-only settings view. Sources: ~/.hermes/.env (runtime
    secrets) and config.env (deploy-time MODULE_* flags) when it can be located.
    NEVER prints secret values — masked via _mask(). No mutations (S2/S3 later)."""
    env = {}
    try:
        for line in open(os.path.expanduser("~/.hermes/.env"),
                         encoding="utf-8", errors="replace"):
            m = re.match(r"^([A-Z_0-9]+)=", line.strip())
            if m:
                env[m.group(1)] = line.split("=", 1)[1]
    except OSError:
        pass

    cfg = {}
    for cand in (os.path.expanduser("~/hermes-argus/config.env"),
                 os.path.expanduser("~/hermes-vps-kit/config.env")):
        if os.path.exists(cand):
            try:
                for line in open(cand, encoding="utf-8", errors="replace"):
                    m = re.match(r'^\s*(MODULE_[A-Z_]+)\s*=\s*"?(\w+)"?', line)
                    if m:
                        cfg[m.group(1)] = m.group(2)
            except OSError:
                pass
            break

    def val(key: str) -> str:
        return (env.get(key, "") or "").strip().strip('"\'')

    lines = ["⚙️ Argus · Настройки", ""]

    lines.append("🧩 Модули (config.env):")
    if cfg:
        for k in sorted(cfg):
            lines.append(f"• {k} = {cfg[k]}")
    else:
        lines.append("• config.env не найден — модули задаются установщиком")
    lines.append("")

    lines.append("💬 Каналы:")
    lines.append(f"• WATCHDOG_BOT_TOKEN: {_mask(val('WATCHDOG_BOT_TOKEN'))}")
    lines.append(f"• WATCHDOG_CHAT_ID: {_mask(val('WATCHDOG_CHAT_ID'))}")
    lines.append(f"• WATCHDOG_ALLOWED_USER_ID: {_mask(val('WATCHDOG_ALLOWED_USER_ID'))}")
    lines.append(f"• WEBHOOK_SECRET_TOKEN: {_mask(val('WEBHOOK_SECRET_TOKEN'))}")
    lines.append(f"• TELEGRAM_BOT_TOKEN: {_mask(val('TELEGRAM_BOT_TOKEN'))}")
    lines.append(f"• DISCORD_BOT_TOKEN: {_mask(val('DISCORD_BOT_TOKEN'))}")
    lines.append(f"• DISCORD_ALLOWED_USER_IDS: {_mask(val('DISCORD_ALLOWED_USER_IDS'))}")
    lines.append("")

    lines.append("💓 Heartbeat:")
    lines.append(f"• CRONPING_TOKEN: {_mask(val('CRONPING_TOKEN'))}")
    lines.append(f"• DMS_SNITCH: {_mask(val('DMS_SNITCH'))}")
    lines.append(f"• GH_TOKEN: {_mask(val('GH_TOKEN'))}")
    lines.append(f"• GITHUB_REPO: {val('GITHUB_REPO') or '— не задано'}")
    lines.append("")

    lines.append("🌐 Сеть:")
    lines.append(f"• HERMES_HOST: {val('HERMES_HOST') or '127.0.0.1'} · NETDATA_PORT: {val('NETDATA_PORT') or '19999'}")
    lines.append(f"• TELEGRAM_PROXY: {val('TELEGRAM_PROXY') or 'дефолт 127.0.0.1:8444'}")
    lines.append("")

    lines.append(f"🎚 Поведение: BREAKER_MAX = {val('BREAKER_MAX') or '3'} · "
                 f"DEEP_CHECK_ALLOW_PAID = {val('DEEP_CHECK_ALLOW_PAID') or 'ON (default)'}")
    lines.append("")
    lines.append("Тогглы модулей — кнопками ниже (S2: confirm → deploy).")
    lines.append("Секреты — /setsecret KEY (S3): значение следующим сообщением.")
    lines.append("Остальное — config.env → ./deploy.sh.")
    return "\n".join(lines)[:3500]


MODULE_NAMES = ("CORE", "INTEGRATIONS", "TG_BOT", "ANALYZER",
                "HEARTBEAT", "GH_HEARTBEAT", "DISCORD_BOT")


def _config_env_path() -> str:
    """Locate the live config.env (same heuristic as handle_settings)."""
    for cand in (os.path.expanduser("~/hermes-argus/config.env"),
                 os.path.expanduser("~/hermes-vps-kit/config.env")):
        if os.path.exists(cand):
            return cand
    return ""


def _read_modules() -> dict:
    mods = {}
    path = _config_env_path()
    if path:
        try:
            for line in open(path, encoding="utf-8", errors="replace"):
                ls = line.strip()
                if ls.startswith("MODULE_") and "=" in ls:
                    k, _, v = ls.partition("=")
                    mods[k.strip()] = v.strip().strip('"').upper()
        except OSError:
            pass
    for name in MODULE_NAMES:
        mods.setdefault(f"MODULE_{name}", "OFF")
    return mods


def settings_keyboard() -> dict:
    """Inline rows for MODULE_* toggles (S2). Press = confirm step next."""
    mods = _read_modules()
    rows = []
    for name in MODULE_NAMES:
        key = f"MODULE_{name}"
        cur = mods.get(key, "OFF")
        newval = "OFF" if cur == "ON" else "ON"
        rows.append([{"text": f"🧩 {key}: {cur} → {newval}",
                      "callback_data": f"mod_toggle:{key}:{newval}"}])
    return {"inline_keyboard": rows}


def _set_config_module(key: str, value: str) -> str:
    path = _config_env_path()
    if not path:
        return "config.env не найден"
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    out, hit = [], False
    prefix = key + "="
    for line in lines:
        if line.strip().startswith(prefix):
            out.append(f'{key}="{value}"')
            hit = True
        else:
            out.append(line)
    if not hit:
        out.append(f'{key}="{value}"')
    tmp = path + ".tmp"
    NL = chr(10)
    open(tmp, "w", encoding="utf-8", newline="").write(NL.join(out) + NL)
    os.replace(tmp, path)
    return path


def _run_deploy_async(chat_send, cfg_path: str) -> None:
    """Background deploy (S2 apply). Reports the output tail to the chat."""
    def worker():
        try:
            r = subprocess.run(["bash", "deploy.sh", cfg_path],
                               cwd=os.path.dirname(cfg_path) or ".",
                               capture_output=True, text=True, timeout=300)
            NL = chr(10)
            tail = NL.join((r.stdout or "").strip().splitlines()[-6:])
            status = "✅ deploy завершён" if r.returncode == 0 else f"❌ deploy exit {r.returncode}"
            chat_send(f"{status}{NL}{tail}", silent=True)
        except Exception as e:
            chat_send(f"❌ deploy error: {e}", silent=True)
    threading.Thread(target=worker, daemon=True).start()


def handle_secret_value(key: str, value: str) -> tuple:
    """S3: write a secret into ~/.hermes/.env.

    Returns (report_text, restart_units). The value arrives from a Telegram
    message — shell-dangerous characters are rejected outright (the .env is
    bash-sourced: quotes, $(), backticks would execute on the next source).
    Token values are never printed; restarts are returned to the caller
    (F4: reply first, then a DETACHED restart)."""
    value = (value or "").strip()
    restart = []
    if not value:
        return f"{_CROSS} Пустое значение — отклонено.", []
    forbidden = " " + chr(39) + chr(34) + chr(96) + "$;&|<>()" + chr(10) + chr(13)
    bad = sorted({ch for ch in value if ch in forbidden})
    if bad:
        return (f"{_CROSS} Недопустимые символы в значении: "
                + " ".join(bad) + " — отклонено."), []
    env_path = os.path.expanduser("~/.hermes/.env")
    lines = open(env_path, encoding="utf-8", errors="replace").read().splitlines()
    out, hit = [], False
    prefix = key + "="
    for line in lines:
        if line.strip().startswith(prefix):
            out.append(f"{key}={value}")
            hit = True
        else:
            out.append(line)
    if not hit:
        out.append(f"{key}={value}")
    tmp = env_path + ".tmp"
    NL = chr(10)
    open(tmp, "w", encoding="utf-8", newline="").write(NL.join(out) + NL)
    os.replace(tmp, env_path)
    if key.startswith(("WATCHDOG_", "WEBHOOK_")) or key == "TELEGRAM_PROXY":
        restart = ["monitoring-bot-poller"]
    elif key.startswith("DISCORD_"):
        restart = ["discord-bot"]
    return f"{_CHECK} {key} обновлён ({_mask(value)}). Проверь: /settings", restart


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


def silence_chooser_keyboard() -> dict:
    """Inline duration chooser for /silence (no-arg)."""
    return {"inline_keyboard": [
        [{"text": "1ч", "callback_data": "silence_h:1"},
         {"text": "4ч", "callback_data": "silence_h:4"},
         {"text": "12ч", "callback_data": "silence_h:12"},
         {"text": "24ч", "callback_data": "silence_h:24"}],
        [{"text": "❌ Сбросить тишину", "callback_data": "silence_reset"}],
    ]}


def menu_keyboard():
    """Inline action panel for /menu. Main navigation lives on the REPLY
    keyboard (hybrid decision, Vlad 2026-09-08): inline stays for actions —
    restarts, reboot confirm, silence."""
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f504 Gateway", "callback_data": "restart_gw"},
                {"text": "\U0001f504 Dashboard", "callback_data": "restart_dash"},
            ],
            [
                {"text": "\u26a0\ufe0f Reboot server", "callback_data": "reboot"},
                {"text": "\U0001f507 Silence 1ч", "callback_data": "silence_1h"},
            ],
            [
                {"text": "\U0001f9ea Deep AI", "callback_data": "deep_ai"},
                {"text": "\U0001f4cb Логи", "callback_data": "show_logs"},
            ],
            [
                {"text": "\U0001f4ca Статус", "callback_data": "health"},
                {"text": "\U0001f50d Мониторинг", "callback_data": "watchdog"},
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
        send_logs_messages()
    elif action == "network":
        send_message(handle_network_status(), silent=True)
    elif action == "health":
        send_message(handle_health_status(), silent=True)
    elif action == "silence_1h":
        send_message(handle_silence(1), silent=True)
    elif action == "watchdog":
        send_message(handle_watchdog_status(), silent=True)
    elif action == "integrations":
        send_message(handle_integrations_check(), silent=True)
    elif action == "integrations_all":
        send_message(handle_integrations_all(), silent=True)
    elif action == "settings":
        send_message(handle_settings(), reply_markup=settings_keyboard(), silent=True)
    elif action == "deep_ai":
        log_to_changelog("Deep AI check (кнопка)", "chat max_tokens=1, free-models gated")
        send_message("🧪 Deep check запущен (до ~2 мин)...", silent=True)
        send_message(handle_deep_check(), silent=True)
    elif action == "uptime":
        send_message(handle_uptime(), silent=True)
    elif action == "reboot":
        log_to_changelog("Reboot server (кнопка, шаг 1)", "запрос подтверждения")
        kb = {"inline_keyboard": [[
            {"text": "✅ Подтвердить ребут", "callback_data": "reboot_confirm"},
            {"text": "❌ Отмена", "callback_data": "reboot_cancel"}]]}
        send_message("⚠️ Перезагрузка сервера. Точно ребутаем? "
                     "(shutdown через 1 минуту после подтверждения)",
                     reply_markup=kb, silent=True)
    elif action == "silence_menu":
        kb = {"inline_keyboard": [
            [{"text": "1ч", "callback_data": "silence_h:1"},
             {"text": "4ч", "callback_data": "silence_h:4"},
             {"text": "12ч", "callback_data": "silence_h:12"},
             {"text": "24ч", "callback_data": "silence_h:24"}],
            [{"text": "❌ Сбросить тишину", "callback_data": "silence_reset"}],
        ]}
        send_message("🔕 Заглушить алерты на:", reply_markup=kb, silent=True)
    elif action.startswith("silence_h:"):
        try:
            hours = int(action.split(":", 1)[1])
        except ValueError:
            hours = 1
        send_message(handle_silence(hours), silent=True)
    elif action == "silence_reset":
        send_message(handle_silence(0), silent=True)
    elif action.startswith("mod_toggle:"):
        _, key, newval = action.split(":", 2)
        kb = {"inline_keyboard": [[
            {"text": "✅ Применить + deploy", "callback_data": f"mod_apply:{key}:{newval}"},
            {"text": "❌ Отмена", "callback_data": "mod_cancel"}]]}
        send_message(f"⚠️ Применить {key}={newval}? Запустится deploy (до ~2 мин).",
                     reply_markup=kb, silent=True)
    elif action.startswith("mod_apply:"):
        _, key, newval = action.split(":", 2)
        path = _set_config_module(key, newval)
        log_to_changelog(f"S2: {key}={newval}", "toggle из бота + deploy")
        send_message(f"🧩 {key}={newval} записан в config.env, запускаю deploy...",
                     silent=True)
        _run_deploy_async(send_message, path)
    elif action == "mod_cancel":
        send_message("🚫 Отменено.", silent=True)
    elif action == "reboot_confirm":
        send_message(handle_reboot_confirm(), silent=True)
    elif action == "reboot_cancel":
        send_message(handle_reboot_cancel(), silent=True)

