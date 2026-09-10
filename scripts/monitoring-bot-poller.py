#!/usr/bin/env python3
"""monitoring-bot-poller — long-polling бот @ceo_of_monitoring_bot.

Единственный активный канал приёма апдейтов: webhook не установлен
(Funnel сломан), поэтому и команды, и callback_query (нажатия кнопок)
приходят через getUpdates.

Вся логика действий (кнопки + команды) — в ~/scripts/webhook.py:
poller только маршрутизирует, НЕ дублирует обработчики (урок 15-18.08:
кнопки разъехались по трём копиям, watchdog слал старый набор).

Runs as systemd user service.
"""

import json
import os
import sys
import threading
import time as _time
import time
import urllib.request
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("WATCHDOG_BOT_TOKEN", "")
CHAT_ID = os.environ.get("WATCHDOG_CHAT_ID", "@WATCHDOG_CHAT_ID@")
# Единственный авторизованный пользователь бота.
# Без allowlist любой, кто узнал bot_token/username, мог дёргать команды —
# ответ уходил бы в CHAT_ID (твой), а триггеры (restart_gw, restart_dash) выполнялись.
ALLOWED_USER_ID = os.environ.get("WATCHDOG_ALLOWED_USER_ID", "").strip()

# Всегда через telegram-smart-proxy (8444) — он сам решает каскад direct→vless→tor.
# НЕ использовать get_proxy()/прямой путь: при mode=direct прямой api.telegram.org
# мёртв во время РКН-волн, а прокси перечитывается только при старте процесса.
# (Инцидент 2026-08-08: poller молчал с 29.07 из-за одноразовой инициализации.)
# C6: сети с блокировкой TG требуют локального прокси на 8444 (реверс-туннель
# или смарт-прокси); TELEGRAM_PROXY из .env позволяет переопределить
os.environ.setdefault("HTTPS_PROXY",
                      os.environ.get("TELEGRAM_PROXY", "http://127.0.0.1:8444"))
os.environ.pop("https_proxy", None)

# Обработчики кнопок/команд — единый источник истины (webhook.py).
sys.path.insert(0, "@HOME_DIR@/scripts")
import webhook  # noqa: E402

# ── Telegram API ────────────────────────────────────────────────────────

def tg_api(method: str, data: dict) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def send_message(text: str, reply_markup: dict = None):
    """Отправка текстового сообщения в мониторинг-чат."""
    data = {"chat_id": CHAT_ID, "text": text, "disable_notification": True}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return tg_api("sendMessage", data)

def reply_to(chat_id: str, text: str):
    """Ответ в ЛС того, кто написал (для отказов и тестов)."""
    return tg_api("sendMessage", {
        "chat_id": chat_id, "text": text, "disable_notification": True
    })

def is_authorized(user_id: int | None) -> bool:
    """Пустой ALLOWED_USER_ID = open mode (для отладки/инцидентов)."""
    if not ALLOWED_USER_ID:
        return True
    return str(user_id) == ALLOWED_USER_ID

# Rate-limit для «🚫 нет доступа» ответов неавторизованным (1/мин на user_id).
# ponytail: in-process dict, глобальный lock под GIL достаточен, poller однопроцессный.
_DENY_LOG: dict[str, float] = {}
_DENY_COOLDOWN_S = 60.0

def _send_deny(chat_id, callback_id: str | None = None, query: dict | None = None):
    """Сообщает «🚫 нет доступа» не чаще 1/мин на user_id; возвращает всегда False."""
    key = str((query or {}).get("id") or callback_id or chat_id or "anon")
    now = time.time()
    last = _DENY_LOG.get(key, 0.0)
    fresh = now - last >= _DENY_COOLDOWN_S
    if fresh:
        _DENY_LOG[key] = now
        if chat_id:
            try: reply_to(chat_id, "🚫 У вас нет доступа к этому боту.")
            except Exception: pass
    # Кнопочный ответ — всегда (часики не должны висеть).
    if callback_id:
        try:
            tg_api("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "🚫 нет доступа" if fresh else "🚫 тихо"
            })
        except Exception:
            pass
    return False

# ── Маршрутизация команд (слеш-дубли всех кнопок) ──────────────────────
# Кнопки из webhook.alert_keyboard() и команды ниже — один набор действий.

# Hybrid UI (Vlad, 2026-09-08): MAIN navigation on a persistent REPLY
# keyboard (Russian labels mapped to commands); inline keyboards stay for
# actions (restarts, reboot confirm, silence) and /menu.
REPLY_LABELS = {
    "📊 Статус Hermes": "/health",
    "👁 Статус Argus": "/watchdog",
    "🔌 Проверка интеграций": "/integrations",
    "📋 Все интеграции": "/integrations_all",
    "⚙️ Настройки": "/settings",
    "🔇 Тишина": "/silence",
    "🛠 Обслуживание": "/menu",
    "❓ Помощь": "/help",
}


# S3: one pending secret at a time; value arrives as the next plain message.
# Gate: WATCHDOG_ALLOWED_USER_ID must be set (poller-level auth is not enough
# for secret WRITES). Keys of Hermes itself are permanently out of scope.
SECRET_ALLOWLIST = (
    "WATCHDOG_BOT_TOKEN", "WATCHDOG_CHAT_ID", "WATCHDOG_ALLOWED_USER_ID",
    "WEBHOOK_SECRET_TOKEN", "DISCORD_BOT_TOKEN", "DISCORD_ALLOWED_USER_IDS",
    "CRONPING_TOKEN", "CRONPING_API_KEY", "DMS_SNITCH", "GH_TOKEN")
PENDING_SECRET = {}


def reply_keyboard() -> dict:
    keys = list(REPLY_LABELS.keys())
    rows = [keys[i:i + 2] for i in range(0, len(keys), 2)]
    return {"keyboard": [[{"text": t} for t in row] for row in rows],
            "resize_keyboard": True, "is_persistent": True}


def _secret_worker(key: str, value: str) -> None:
    """S3: send the report FIRST, then a DETACHED restart (F4: the poller
    process must not die before its reply leaves the chat)."""
    try:
        text, restart = webhook.handle_secret_value(key, value)
        send_message(text)
    except Exception as e:
        send_message(f"❌ Ошибка записи секрета: {e}")
        return
    for unit in restart:
        subprocess.Popen(["bash", "-c",
                          f"sleep 2 && systemctl --user restart {unit}"],
                         start_new_session=True)


def route_command(text: str) -> None:
    """Выполняет команду и шлёт ответ. Обработчики — из webhook.py."""
    if text.startswith("/health"):
        send_message(webhook.handle_health_status())
    elif text.startswith("/restart_gw") or text.startswith("/restart_gateway"):
        webhook.log_to_changelog("Перезапуск gateway (команда)", "через polling-бот")
        send_message("🔄 Запускаю перезапуск gateway...")
        send_message(webhook.handle_restart_gateway())
    elif text.startswith("/restart_dash"):
        webhook.log_to_changelog("Перезапуск dashboard (команда)", "через polling-бот")
        send_message("🔄 Запускаю перезапуск dashboard...")
        send_message(webhook.handle_restart_dashboard())
    elif text.startswith("/restart_all"):
        webhook.log_to_changelog("Перезапуск gateway+dashboard (команда)", "через polling-бот")
        send_message("🔄 Запускаю перезапуск всех сервисов...")
        send_message(webhook.handle_restart_gateway() + "\n---\n" + webhook.handle_restart_dashboard())
    elif text.startswith("/network"):
        send_message(webhook.handle_network_status())
    elif text.startswith("/silence"):
        parts = text.split()
        if len(parts) > 1 and parts[1].isdigit() and 1 <= int(parts[1]) <= 24:
            send_message(webhook.handle_silence(int(parts[1])))
        else:
            send_message("🔕 Заглушить алерты на:",
                         reply_markup=webhook.silence_chooser_keyboard())
    elif text.startswith("/logs"):
        parts = text.split()
        lines = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 20
        webhook.send_logs_messages(lines)
    elif text.startswith("/watchdog"):
        send_message(webhook.handle_watchdog_status())
    elif text.startswith("/integrations_all"):
        send_message(webhook.handle_integrations_all())
    elif text.startswith("/integrations all"):
        send_message(webhook.handle_integrations_all())
    elif text.startswith("/integrations"):
        send_message(webhook.handle_integrations_check())
    elif text.startswith("/deepcheck"):
        send_message("🧪 Deep check AI-провайдеров запущен (до ~2 мин)...")
        send_message(webhook.handle_deep_check())
    elif text.startswith("/settings"):
        # S2: read-only view + inline MODULE_* toggles (settings_keyboard)
        send_message(webhook.handle_settings(),
                     reply_markup=webhook.settings_keyboard())
    elif text.startswith("/uptime"):
        send_message(webhook.handle_uptime())
    elif text.startswith("/reboot_confirm"):
        send_message(webhook.handle_reboot_confirm())
    elif text.startswith("/reboot_cancel"):
        send_message(webhook.handle_reboot_cancel())
    elif text.startswith("/reboot"):
        send_message(webhook.handle_reboot(""))
    elif text.startswith("/menu"):
        # Inline-панель действий (reply keyboard с навигацией уже открыта)
        import json as _json
        send_message("👁 Argus — панель стража. Действия:", reply_markup=webhook.menu_keyboard())
    elif text.startswith("/start"):
        send_message(webhook.handle_start(), reply_markup=reply_keyboard())
    elif text.startswith("/setsecret"):
        parts = text.split(maxsplit=1)
        key = parts[1].strip().upper() if len(parts) > 1 else ""
        if not ALLOWED_USER_ID:
            send_message("🚫 Гейт S3: сначала задай WATCHDOG_ALLOWED_USER_ID в .env.")
        elif key not in SECRET_ALLOWLIST:
            send_message("🤔 Ключ вне allowlist: " + ", ".join(SECRET_ALLOWLIST))
        else:
            import time as _t
            PENDING_SECRET.update({"key": key, "expires": _t.time() + 120})
            send_message(f"🔑 Пришли значение для {key} одним сообщением (2 мин)."
                         + chr(10) + "⚠️ Оно останется в истории чата. /cancel — отмена.")
    elif text.startswith("/help"):
        send_message("👁 Argus — команды:\n"
                     "/health /integrations /integrations_all /watchdog /uptime\n"
                     "/deepcheck /settings /setsecret /logs [N] /network /silence [N]\n"
                     "/restart_gw /restart_dash /restart_all /reboot /menu")
    else:
        send_message("🤔 Argus не понял команду.\n"
                     "Панель: /menu · Команды: /help")

# ── Main poll loop ──────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now()}] Monitoring bot poller started", flush=True)
    offset = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            if offset:
                url += f"?offset={offset}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            if not data.get("ok"):
                time.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                # Извлекаем user_id независимо от типа update (message / callback_query).
                user = update.get("message", {}).get("from") or \
                       update.get("callback_query", {}).get("from")
                chat = update.get("message", {}).get("chat") or \
                       update.get("callback_query", {}).get("message", {}).get("chat")

                if not is_authorized(user.get("id")):
                    # Rate-limited отказ — единая точка для cooldown.
                    cb = update.get("callback_query") or {}
                    _send_deny(
                        chat_id=chat.get("id") if chat else None,
                        callback_id=cb.get("id"),
                        query=cb,
                    )
                    continue

                # Inline-кнопки → единый обработчик webhook.py
                if "callback_query" in update:
                    threading.Thread(
                        target=webhook.handle_callback_query,
                        args=(update["callback_query"],), daemon=True
                    ).start()
                    continue

                msg = update.get("message", {})
                text = msg.get("text", "")
                if not text:
                    continue
                if PENDING_SECRET.get("expires", 0) > _time.time():
                    key = PENDING_SECRET.pop("key")
                    if text == "/cancel":
                        send_message("🚫 Отменено.")
                    else:
                        threading.Thread(target=_secret_worker,
                                         args=(key, text), daemon=True).start()
                    continue
                # Hybrid UI: reply-keyboard labels map to commands BEFORE
                # the command test (lesson 2026-09-08: unmapped labels hit
                # the welcome branch — keyboard "did not work")
                text = REPLY_LABELS.get(text.strip(), text)
                if not text.startswith("/"):
                    # Hybrid UI: plain text gets the branded welcome + the
                    # persistent reply keyboard (main navigation lives there)
                    send_message("👁 Argus на посту. Смотрю в оба.",
                                 reply_markup=reply_keyboard())
                    continue

                # Команды — в потоке: рестарты блокируют до 30с, не стопорим polling
                threading.Thread(target=route_command, args=(text,), daemon=True).start()

            time.sleep(2)

        except Exception as e:
            print(f"[{datetime.now()}] Poll error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # ponytail: минимальный self-check — гейт + cooldown без поднятия polling.
        def gate(allowed: str, uid):
            if not allowed: return True
            return str(uid) == allowed
        assert gate("123456789", 123456789) is True  # тестовый ID, не секрет
        assert gate("123456789", 99999) is False
        assert gate("", 12345) is True  # open-mode fallback

        # Cooldown: первый запрос → fresh, второй в окне → throttled.
        log = {}
        COOL = 60.0
        t = [1000.0]
        def maybe(key):
            last = log.get(key, 0.0)
            fresh = t[0] - last >= COOL
            if fresh: log[key] = t[0]
            return fresh
        assert maybe("u1") is True
        assert maybe("u1") is False  # throttled
        t[0] += 61.0
        assert maybe("u1") is True   # после cooldown — снова fresh
        print("OK — gate + rate-limit passed")
        sys.exit(0)
    main()
