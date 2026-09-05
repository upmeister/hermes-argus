#!/usr/bin/env bash
# gateway-liveness.sh — детектор зависания hermes-gateway.
# Heartbeat: gateway пишет "memory trim: reason=messaging gateway housekeeping"
# в ~/.hermes/logs/agent.log каждую минуту (проверено: тик ровно :19 каждой
# минуты). Если свежей записи нет STALE_AFTER сек (две проверки подряд) →
# gateway завис (GIL-stall/своп-трэш) → systemctl --user restart + алерт.
# Молчит (пустой stdout), когда всё в порядке.
set -u
# cron-окружение не имеет XDG_RUNTIME_DIR → systemctl --user падает с
# "Failed to connect to bus". Без этого экспорта авто-рестарт невозможен.
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
H="$HOME/.hermes"
LOG="$H/logs/gateway-liveness.log"
STATE_FILE="$H/state/gateway-liveness.alerted" # 2026-09-04: дедуп как в watchdog — файл есть = уже алертили, ждём восстановления
mkdir -p "$H/state" 2>/dev/null || true
STALE_AFTER="${STALE_AFTER:-180}" # секунд без housekeeping → подозрение (переопределяется из env для тестов)
# Числовая защита: битое env-переопределение не должно ронять порог (пустое → всегда fire)
case "$STALE_AFTER" in ''|*[!0-9]*) STALE_AFTER=180;; esac
CHECK_INTERVAL=20 # пауза между двумя проверками (анти-ложные срабатывания)

# Процесс мёртв → systemd Restart=always сам разберётся (крэш, а не зависание)
if ! pgrep -f "hermes_cli.main gateway run" >/dev/null 2>&1; then
  exit 0
fi

last_ts() {
  # agent.log свежее .1 — берём первую непустую запись housekeeping
  local f ts=""
  for f in "$H"/logs/agent.log "$H"/logs/agent.log.1; do
    ts=$(tail -300 "$f" 2>/dev/null | grep "messaging gateway housekeeping" | tail -1 | cut -c1-19)
    [ -n "$ts" ] && break
  done
  echo "$ts"
}

age_sec() {
  local ts
  ts=$(last_ts)
  [ -z "$ts" ] && { echo 99999; return; }
  echo $(( $(date +%s) - $(date -d "$ts" +%s) ))
}

send_recovery() {
  # Одно тихое уведомление о восстановлении (рутина — тихо, CONVENTIONS)
  local btok chtok prx
  btok=$(grep -E '^WATCHDOG_BOT_TOKEN=' "$H/.env" | cut -d= -f2-)
  chtok=$(grep -E '^WATCHDOG_CHAT_ID=' "$H/.env" | cut -d= -f2-)
  [ -z "$chtok" ] && chtok=@WATCHDOG_CHAT_ID@
  prx="${TELEGRAM_PROXY:-http://127.0.0.1:8444}"
  curl -s -m 20 -x "$prx" -X POST "https://api.telegram.org/bot${btok}/sendMessage" \
    -d chat_id="$chtok" --data-urlencode "text=✅ Gateway восстановился (housekeeping снова свежий)" -d disable_notification=true > /dev/null
}

AGE=$(age_sec)
if [ "$AGE" -lt "$STALE_AFTER" ]; then
  if [ -f "$STATE_FILE" ]; then
    rm -f "$STATE_FILE"
    echo "$(date -Is) gateway восстановился (housekeeping свежий)" >> "$LOG"
    send_recovery
    echo "✅ Gateway восстановился (housekeeping снова свежий)"
  fi
  exit 0
fi
# Первое подозрение — перепроверяем через интервал (логгер мог задержаться)
sleep "$CHECK_INTERVAL"
AGE2=$(age_sec)
if [ "$AGE2" -lt "$STALE_AFTER" ]; then
  if [ -f "$STATE_FILE" ]; then
    rm -f "$STATE_FILE"
    echo "$(date -Is) gateway восстановился (housekeeping свежий, 2-я проверка)" >> "$LOG"
    send_recovery
    echo "✅ Gateway восстановился (housekeeping снова свежий)"
  fi
  exit 0
fi
# Числовая защита: пустой/битый возраст (parse fail) — данных нет, НЕ рестартуем
case "$AGE2" in ''|*[!0-9]*) echo "$(date -Is) housekeeping ts unparseable (age=[$AGE2]) — пропуск, рестарт отменён" >> "$LOG"; exit 0;; esac

echo "$(date -Is) gateway завис (housekeeping старше ${AGE2}s), рестарт" >> "$LOG"
# DRY_RUN=1 — тест детекта без рестарта (иначе рестарт убьёт текущую сессию)
if [ "${GATEWAY_LIVENESS_DRY:-0}" = "1" ]; then
  echo "$(date -Is) DRY-RUN: рестарт пропущен (тест)" >> "$LOG"
  exit 0
fi
systemctl --user restart hermes-gateway
# Зависший gateway: SIGTERM не обрабатывается → systemd ждёт TimeoutStopSec
# до SIGKILL + старт. Одиночный sleep давал ложное «НЕ помог» — цикл до ~60с.
ALIVE=0
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 5
  if pgrep -f "hermes_cli.main gateway run" >/dev/null 2>&1; then
    ALIVE=1
    break
  fi
done
if [ "$ALIVE" = "1" ]; then
  TEXT="⚠️ Gateway завис (нет housekeeping >3 мин) → авто-рестарт, процесс снова жив"
else
  TEXT="🚨 Gateway завис, рестарт НЕ помог. Нужен ручной разбор!"
fi
BOT_TOKEN=$(grep -E '^WATCHDOG_BOT_TOKEN=' "$H/.env" | cut -d= -f2-)
CHAT_ID=$(grep -E '^WATCHDOG_CHAT_ID=' "$H/.env" | cut -d= -f2-)
[ -z "$CHAT_ID" ] && CHAT_ID=@WATCHDOG_CHAT_ID@
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
