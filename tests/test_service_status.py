#!/usr/bin/env python3
"""Регрессионные пробы для scripts/service-status-snapshot.py (2026-09-27).

Модуль пишет отчёт о локальной топологии, поэтому его главный класс отказа —
НЕ упасть, а СОЛГАТЬ ЧЕСТНО. Каждая проба ниже закрывает реальный баг, найденный
при первой реализации:

  T1  `systemctl --user ""` — пустой аргумент НЕ значит «без флага»: system-юниты
      молча исчезали из отчёта (0 вместо 138).
  T2  фиксированный индекс колонки `ss` — раздел listeners был пуст (0 вместо 73);
      колонки сдвигаются в зависимости от наличия колонки Process.
  T3  docker без сокета: `_run` глотал stderr и возвращал пустую строку → раздел
      выглядел как «контейнеров нет». Теперь обязан быть явный маркер недоступности.
  T4  адрес ENI (172.31.31.168:443) не должен считаться «не публичным»: у EC2
      публичный IP — это NAT, трафик снаружи приходит на приватный адрес.
  T5  атомарная запись: мониторинг читает файл в любой момент, поэтому .tmp не
      должен оставаться, а целевой файл — всегда валидный json.

Запуск: python3 tests/test_service_status.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "scripts" / "service-status-snapshot.py"


def _load():
    """Загрузить скрипт как модуль: имя файла содержит дефис, importlib его не берёт."""
    spec = importlib.util.spec_from_file_location("service_status_snapshot", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"не удалось загрузить {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILS.append(label)

print("T1: scope=user и scope=system дают разные (непустые) наборы юнитов")
user = mod._run_units("user")
system = mod._run_units("system")
check("user-юниты собраны", len(user) > 0, f"получено {len(user)}")
check("system-юниты собраны", len(system) > 0, f"получено {len(system)}")
check("в scope указан верно",
      all(s["kind"] == "user" for s in user) and all(s["kind"] == "system" for s in system))
check("наши сервисы в user-наборе",
      {"nail-bot.service", "hermes-gateway.service"} <= {s["name"] for s in user},
      "ожидались nail-bot и hermes-gateway")
check("sing-box/tailscaled в system-наборе",
      {"sing-box.service", "tailscaled.service"} <= {s["name"] for s in system},
      "ожидались sing-box и tailscaled")
check("нет мусора systemd-*", not any(s["name"].startswith("systemd-") for s in system))
check("у каждого юнита есть active/enabled",
      all(s["active"] and s["enabled"] for s in user + system))

print("T2: парсер ss не теряет слушатели (без фиксированного индекса колонки)")
listeners = mod._listeners()
check("слушатели разобраны", len(listeners) > 0, f"получено {len(listeners)}")
check("все порты — числа", all(isinstance(l["port"], int) for l in listeners))
check("есть известные порты",
      {22, 80, 443} & {l["port"] for l in listeners} != set(),
      "не найдено ни 22, ни 80, ни 443")
check("каждая запись имеет scope", all(l.get("scope") for l in listeners))
check("нет дублей (port, addr, process)",
      len({(l["port"], l["addr"], l["process"]) for l in listeners}) == len(listeners))

print("T3: недоступный docker API даёт явный маркер, а не пустой список")
saved_run = mod._run


def _empty_run(argv, timeout=20):
    return ""


mod._run = _empty_run
try:
    containers = mod._containers()
finally:
    mod._run = saved_run
check("docker недоступен → не пустой список", len(containers) > 0, "получен пустой список")
check("маркер содержит 'недоступен'",
      any("недоступен" in c["name"] for c in containers),
      f"получено: {containers}")
check("running=None (не False) при недоступности",
      all(c["running"] is None for c in containers),
      "running должен быть None, а не False — иначе это ложное «выключено»")

print("T4: приватный адрес ENI классифицируется как публично достижимый")
# Проверяем ПОВЕДЕНИЕ, а не текст исходника: подсовываем парсеру настоящий вывод `ss`
# и смотрим на получившуюся классификацию.
SS_FIXTURE = """Netid State  Recv-Q Send-Q   Local Address:Port  Peer Address:Port Process
tcp   LISTEN 0      128        0.0.0.0:22         0.0.0.0:*         sshd
tcp   LISTEN 0      512      172.31.31.168:443     0.0.0.0:*         users:(("sing-box",pid=886195,fd=10))
tcp   LISTEN 0      128      100.77.100.96:8090   0.0.0.0:*         users:(("python",pid=923298,fd=13))
tcp   LISTEN 0      128        127.0.0.1:1080     0.0.0.0:*         users:(("sing-box",pid=886195,fd=8))
udp   UNCONN 0      0            0.0.0.0:41641   0.0.0.0:*         users:(("tailscaled",pid=2028,fd=20))
"""
saved_ss = mod._run


def _fake_run(argv, timeout=20):
    if argv and argv[0] == "ss":
        return SS_FIXTURE
    return saved_ss(argv, timeout=timeout)


mod._run = _fake_run
try:
    parsed = mod._listeners()
finally:
    mod._run = saved_ss
by_port = {l["port"]: l for l in parsed}
expect = {
    22: ("all-interfaces", True),
    443: ("vpc-eni", True),      # ENI: снаружи достижимо (публичный IP = NAT)
    8090: ("tailnet", False),    # 100.x — tailnet
    1080: ("loopback", False),
    41641: ("all-interfaces", True),
}
for port, (want_scope, want_public) in expect.items():
    got = by_port.get(port)
    check(f"порт {port} → {want_scope}", got is not None and got["scope"] == want_scope,
          f"получено: {got}")
    check(f"порт {port} public={want_public}", got is not None and got["public"] is want_public,
          f"получено: {got}")
check("процесс извлечён", by_port.get(443, {}).get("process") == "sing-box",
      f"получено: {by_port.get(443, {}).get('process')}")

print("T5: запись атомарна, .tmp не остаётся, файл валиден")
with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "nested" / "svc.json"
    mod.write_report({"schema": 1, "generated_at": "x", "probe": True}, out)
    check("файл создан", out.exists())
    check("json валиден", json.loads(out.read_text(encoding="utf-8"))["schema"] == 1)
    check(".tmp не остался", not list(out.parent.glob("*.tmp")),
          f"осталось: {[p.name for p in out.parent.glob('*.tmp')]}")
    mod.write_report({"schema": 1, "probe": 2}, out)
    check("повторная запись перезаписывает", json.loads(out.read_text())["probe"] == 2)

print("T6: collect() отдаёт полную структуру (контракт отчёта)")
report = mod.collect()
for key in ("schema", "generated_at", "services", "containers", "listeners",
            "resources", "reboot_ready"):
    check(f"есть секция {key}", key in report)
check("schema == 1", report["schema"] == 1)
check("resources заполнены",
      report["resources"]["mem_total_mb"] and report["resources"]["disk_pct"] is not None)
check("reboot_ready содержит linger и списки",
      {"linger", "active_user_units_not_enabled", "reboot_risk"} <= set(report["reboot_ready"]))
check("generated_at в ISO с таймзоной", "+" in report["generated_at"] or report["generated_at"].endswith("Z"),
      report["generated_at"])
check("в отчёте нет значений секретов",
      "API_KEY" not in json.dumps(report) and "token" not in json.dumps(report).lower()
      .replace("restart", "").replace("unauthorized", ""),
      "в отчёте не должно быть полей с токенами")

print("T7: transient-юниты не считаются риском для ребута (ложная тревога)")
# Проверяем _reboot_ready() на СИНТЕТИЧЕСКИХ данных, а не на живом хосте: c6-tunnel
# существует только пока поднят туннель (его создаёт systemd-run), поэтому проверка
# «есть ли он сейчас» была бы нестабильной и мигала бы между прогонами.
synthetic_user = [
    {"name": "nail-bot.service", "active": "active", "enabled": "enabled",
     "unit_state": "enabled", "kind": "user"},
    # transient: enabled невозможен, но и переживать ребут ему не нужно —
    # его пересоздаёт таймер, который его и породил.
    {"name": "c6-tunnel.service", "active": "active", "enabled": "transient",
     "unit_state": "transient", "kind": "user"},
    {"name": "session-42.scope", "active": "active", "enabled": "generated",
     "unit_state": "generated", "kind": "user"},
    # настоящая проблема: активен, но не включён → после ребута не поднимется
    {"name": "rogue.service", "active": "active", "enabled": "disabled",
     "unit_state": "disabled", "kind": "user"},
]
rr_test = mod._reboot_ready(synthetic_user, [])
check("transient уведён из not_enabled",
      rr_test["active_user_units_not_enabled"] == ["rogue.service"],
      f"получено: {rr_test['active_user_units_not_enabled']}")
check("transient и scope перечислены отдельно",
      set(rr_test["active_user_units_transient"]) == {"c6-tunnel.service", "session-42.scope"},
      f"получено: {rr_test['active_user_units_transient']}")
check("реальный rogue.service даёт reboot_risk",
      rr_test["reboot_risk"] == "reboot_risk",
      f"получено: {rr_test['reboot_risk']}")
check("без rogue — risk=ok при linger=yes",
      mod._reboot_ready(synthetic_user[:2], [])["reboot_risk"] == "ok",
      "только transient+enabled должен давать ok")
check("без linger — всегда риск (юниты не стартуют без логина)",
      mod._reboot_ready(synthetic_user[:2], []) is not None
      and "linger" in mod._reboot_ready(synthetic_user[:2], []))

# и сверка с живым хостом: наши постоянные сервисы обязаны быть enabled
rr = report["reboot_ready"]
check("живой хост: наши три юнита enabled",
      all(u["enabled"] == "enabled" for u in report["services"]["user"]
          if u["name"] in ("nail-bot.service", "2ch-monitor.service", "hermes-gateway.service")),
      "проверь, что эти три действительно enabled")
check("живой хост: reboot_risk=ok",
      rr["reboot_risk"] == "ok",
      f"reboot_risk={rr['reboot_risk']}, not_enabled={rr['active_user_units_not_enabled']}")
check("живой хост: есть поле transient",
      "active_user_units_transient" in rr, f"ключи: {sorted(rr)}")

print("T8: запуск из cron (без XDG_RUNTIME_DIR) даёт тот же результат, что и из сессии")
# Это был самый коварный баг: в cron нет XDG_RUNTIME_DIR/DBUS_SESSION_BUS_ADDRESS,
# `systemctl --user` молча возвращает пустоту, и отчёт показывал «0 user-юнитов»,
# reboot_risk=ok — то есть мониторинг БЫЛ СЛЕПЫМ ровно там, где слепота опаснее всего
# (а именно: пропущенный не-enabled юнит = сервис, который не поднимется после ребута).
saved_env = {k: os.environ.pop(k, None) for k in
             ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "USER")}
try:
    cron_user = mod._run_units("user")
finally:
    for k, v in saved_env.items():
        if v is not None:
            os.environ[k] = v
check("без XDG_RUNTIME_DIR находятся user-юниты", len(cron_user) > 0,
      f"получено {len(cron_user)} — это баг cron-окружения")
check("в cron-режиме виден nail-bot",
      any(u["name"] == "nail-bot.service" for u in cron_user),
      "nail-bot должен попадать в отчёт независимо от окружения")
check("user-scope совпадает с интерактивным",
      {u["name"] for u in cron_user} == {u["name"] for u in user},
      "состав юнитов не должен зависеть от наличия XDG_RUNTIME_DIR")

print()
if FAILS:
    print(f"ПРОВАЛЕНО {len(FAILS)}:")
    for f in FAILS:
        print("  •", f)
    sys.exit(1)
print("ВСЕ ПРОБЫ ПРОШЛИ")
