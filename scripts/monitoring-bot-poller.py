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
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:8444"
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
        if len(parts) > 1 and parts[1].isdigit():
            hours = int(parts[1])
            if 1 <= hours <= 24:
                # Custom silence
                import time
                silence_until = int(time.time()) + hours * 3600
                state_dir = os.path.expanduser("~/.hermes/logs/auto-remediate-state")
                os.makedirs(state_dir, exist_ok=True)
                with open(f"{state_dir}/silence-until.txt", "w") as f:
                    f.write(str(silence_until))
                send_message(f"🔕 Алерты приглушены на {hours} ч")
            else:
                send_message("🔇 Укажите часы от 1 до 24")
        else:
            send_message(webhook.handle_silence_1h())
    elif text.startswith("/silence_1h"):
        send_message(webhook.handle_silence_1h())
    elif text.startswith("/logs"):
        parts = text.split()
        lines = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 20
        send_message(webhook.handle_show_logs(lines))
    elif text.startswith("/watchdog"):
        send_message(webhook.handle_watchdog_status())
    elif text.startswith("/integrations all"):
        send_message(webhook.handle_integrations_all())
    elif text.startswith("/integrations"):
        send_message(webhook.handle_integrations_check())
    elif text.startswith("/uptime"):
        send_message(webhook.handle_uptime())
    elif text.startswith("/reboot_confirm"):
        send_message(webhook.handle_reboot_confirm())
    elif text.startswith("/reboot_cancel"):
        send_message(webhook.handle_reboot_cancel())
    elif text.startswith("/reboot"):
        send_message(webhook.handle_reboot(""))
    elif text.startswith("/menu"):
        # Отправляем кнопки
        import json as _json
        send_message("📋 **Доступные команды:**\n\nВыберите действие:", reply_markup=webhook.menu_keyboard())
    else:
        send_message("🤔 Неизвестная команда.\n"
                     "Доступно: /health, /restart_gw, /restart_dash, /restart_all, "
                     "/network, /silence [N], /logs [N], "
                     "/watchdog, /integrations, /uptime, /reboot, /menu")

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
                if not text or not text.startswith("/"):
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
