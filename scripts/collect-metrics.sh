#!/bin/bash
# ============================================================================
# Сборщик системных метрик для Hermes cron (deep health check)
# Запускается каждый час, вывод передаётся агенту для анализа
# ============================================================================

echo "=== СИСТЕМНЫЙ ОТЧЁТ $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo ""

echo "── ПАМЯТЬ ──"
free -h
echo ""

echo "── ДИСК ──"
df -h /
echo ""

echo "── ПРОЦЕСС HERMES ──"
pgrep -f "hermes" -a 2>/dev/null | head -5 || echo "Процессов Hermes не найдено!"
echo ""

echo "── СИСТЕМНЫЕ СЕРВИСЫ ──"
systemctl --user is-active hermes-dashboard hermes-gateway 2>/dev/null || echo "Сервисы не найдены"
echo ""

echo "── НАГРУЗКА ──"
uptime
echo ""

echo "── ОШИБКИ В ЛОГАХ GATEWAY (последние 100 строк) ──"
grep -i "error\|traceback\|fail\|exception" @HERMES_DIR@/logs/gateway.log 2>/dev/null | tail -10 || echo "Лог gateway не найден"
echo ""

echo "── OOM KILLER ──"
dmesg 2>/dev/null | grep -i "oom\|killed process" | tail -5 || echo "Нет событий OOM"
echo ""

echo "── FAIL2BAN ──"
sudo fail2ban-client status sshd 2>/dev/null | head -5 || echo "Fail2ban не доступен"
echo ""

echo "── АКТИВНЫЕ ПОДКЛЮЧЕНИЯ К ПОРТАМ ──"
ss -tlnp 2>/dev/null | grep -E "22|9119" | head -10
echo ""

echo "── ПОСЛЕДНЯЯ АКТИВНОСТЬ WATCHDOG ──"
tail -5 @HERMES_DIR@/logs/watchdog.log 2>/dev/null || echo "Лог watchdog не найден"
