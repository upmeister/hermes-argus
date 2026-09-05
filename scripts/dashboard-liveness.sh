#!/usr/bin/env bash
# dashboard-liveness.sh — детектор зависания hermes-dashboard.
# Если порт 9119 слушается, но HTTP не отвечает 3 раза подряд → завис →
# systemctl --user restart hermes-dashboard + алерт в мониторинг-бот.
# Молчит (пустой stdout), когда всё в порядке.
set -u
# cron-окружение не имеет XDG_RUNTIME_DIR → systemctl --user падает с
# "Failed to connect to bus". Без этого экспорта авто-рестарт невозможен.
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
H="$HOME/.hermes"
URL="http://@HERMES_HOST@:@HERMES_PORT@/"
LOG="$H/logs/dashboard-liveness.log"
STATE_FILE="$H/state/dashboard-liveness.alerted" # 2026-09-04: дедуп как в watchdog — файл есть = уже алертили, ждём восстановления
mkdir -p "$H/state" 2>/dev/null || true

send_recovery() {
  # Одно тихое уведомление о восстановлении (рутина — тихо, CONVENTIONS)
  local btok chtok prx
  btok=$(grep -E '^WATCHDOG_BOT_TOKEN=' "$H/.env" | cut -d= -f2-)
  chtok=$(grep -E '^WATCHDOG_CHAT_ID=' "$H/.env" | cut -d= -f2-)
  [ -z "$chtok" ] && chtok=@WATCHDOG_CHAT_ID@
  prx="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
  curl -s -m 20 -x "$prx" -X POST "https://api.telegram.org/bot${btok}/sendMessage" \
    -d chat_id="$chtok" --data-urlencode "text=✅ Dashboard восстановился (снова отвечает)" -d disable_notification=true > /dev/null
}

# Сервис не слушает порт → systemd Restart=always сам разберётся (крэш, а не зависание)
if ! ss -tln 2>/dev/null | grep -q ':9119 '; then
  exit 0
fi

FAILS=0
CODES=""
for i in 1 2 3; do
  # НЕ писать `|| echo 000`: curl при ошибке и так печатает 000 через -w,
  # а || добавит второе → "000000" (ложные срабатывания, см. скилл).
  CODE=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null)
  CODE=${CODE:-000}
  CODES="$CODES $CODE"
  if [[ "$CODE" == *000* ]]; then
    FAILS=$((FAILS + 1))
    [ "$i" -lt 3 ] && sleep 3
  else
    break
  fi
done

if [ "$FAILS" -ge 3 ]; then
  echo "$(date -Is) dashboard не отвечает (3×000, коды:$CODES), рестарт" >> "$LOG"
  systemctl --user restart hermes-dashboard
  # Зависший процесс: systemd ждёт TimeoutStopSec=30с до SIGKILL + старт 5-10с.
  # Одиночный sleep давал ложное «НЕ помог» — ждём подъёма в цикле до ~60с.
  CODE2=000
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    sleep 5
    CODE2=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null)
    CODE2=${CODE2:-000}
    [[ "$CODE2" != *000* ]] && break
  done
  BOT_TOKEN=$(grep -E '^WATCHDOG_BOT_TOKEN=' "$H/.env" | cut -d= -f2-)
  CHAT_ID=$(grep -E '^WATCHDOG_CHAT_ID=' "$H/.env" | cut -d= -f2-)
  [ -z "$CHAT_ID" ] && CHAT_ID=@WATCHDOG_CHAT_ID@
  if [[ "$CODE2" != *000* ]]; then
    TEXT="⚠️ Dashboard завис (3×HTTP 000) → авто-рестарт, снова отвечает (HTTP $CODE2)"
  else
    TEXT="🚨 Dashboard завис, рестарт НЕ помог (HTTP $CODE2 после restart). Нужен ручной разбор!"
  fi
  # 2026-09-04: дедуп как в watchdog (CONVENTIONS) — один алерт на инцидент, повтор молча в лог
  if [ -f "$STATE_FILE" ]; then
    echo "$(date -Is) всё ещё завис (уже алертили $(cat "$STATE_FILE" 2>/dev/null)), рестарт attempted, без повтора в ТГ" >> "$LOG"
    echo "$TEXT (повтор, без ТГ)"
    exit 0
  fi
  date -Is > "$STATE_FILE"
  # Прямой api.telegram.org мёртв при РКН-волнах — только через telegram-smart-proxy
  proxy="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
  curl -s -m 20 -x "$proxy" -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="$CHAT_ID" --data-urlencode "text=$TEXT" -d disable_notification=false > /dev/null
  echo "$TEXT"
  exit 0
fi
# Здоров — если раньше алертили, значит восстановился → одно тихое уведомление
if [ -f "$STATE_FILE" ]; then
  rm -f "$STATE_FILE"
  echo "$(date -Is) dashboard восстановился (HTTP отвечает)" >> "$LOG"
  send_recovery
  echo "✅ Dashboard восстановился (снова отвечает)"
fi
exit 0
