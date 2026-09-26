#!/usr/bin/env python3
"""service-status-snapshot.py — единая сводка «что на сервере запущено».

Задача: дать оператору (и Argus) ОДИН json-файл вместо того, чтобы держать в голове
список из 15+ сервисов. Скрипт только ЧИТАЕТ состояние systemd/контейнеров/слушателей
и пишет его в файл; никаких правок, рестартов и алертов.

Почему отдельный модуль, а не расширение health-check-v2: тот проверяет ВНЕШНИЕ
интеграции (API, провайдеры), этот — локальную топологию (юниты, порты, контейнеры,
ресурсы). Смешивать их в один отчёт нельзя: у них разные времена жизни и разные
владельцы правок.

Формат: schema-1, поле `generated_at` (UTC ISO8601), секции:
  services.user[] / services.system[] — {name, active, enabled, restart, kind}
  containers[]                        — {name, status, restart, running}
  listeners[]                         — {port, addr, process, public}
  resources                           — {mem_total_mb, mem_available_mb, disk_pct, load1, kernel, uptime_s}
  reboot_ready                        — {linger, active_user_units_total,
                                       active_user_units_not_enabled[], reboot_risk}

Запуск: python3 service-status-snapshot.py [--output PATH] [--timeout 30] [--quiet]
Дефолтный output: ~/.hermes/state/service-status.json (атомарная запись через tmp+rename).

Границы (намеренно НЕ делаем):
- не рестартим, не чиним, не алертим — это работа watchdog/Argus;
- не ходим в сеть (никаких health-endpoint запросов): блокирующий вызов наружу в
  кроне мониторинга — источник ложных «упало» при собственном же падении сети;
- не трогаем /etc, не меняем unit-файлы;
- не печатаем секреты и не показываем cmdline процессов (в нём могут быть токены).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
DEFAULT_OUT = Path.home() / ".hermes" / "state" / "service-status.json"
SUBPROCESS_TIMEOUT = 20

# Единицы, которые НЕ являются нашими сервисами и не должны засорять отчёт
# (сессионные/служебные + ванильные юниты Ubuntu). Список осознанно узкий.
USER_NOISE = {
    "dbus.service", "dconf.service", "gpg-agent.service", "gpg-agent-dbus.service",
    "gpg-agent-ssh-extra.service", "gpg-agent-extra.service", "gpg-agent-ssh.service",
    "at-spi-dbus-bus.service", "rampage.service",
}
SYSTEM_NOISE = {
    "dbus.service", "systemd-journald.service", "systemd-logind.service",
    "systemd-udevd.service", "systemd-udev-trigger.service", "systemd-resolved.service",
    "systemd-fsck@dev-disk-by\\x2dlabel-BOOT.service", "systemd-fsck@dev-disk-by\\x2dlabel-UEFI.service",
    "systemd-tmpfiles-clean.service", "systemd-initctl.service", "systemd-sysctl.service",
    "systemd-modules-load.service", "systemd-remount-fs.service", "systemd-journal-flush.service",
    "systemd-binfmt.service", "systemd-private-tmp-timers.service",
    "snapd.apparmor.service", "snapd.apparmor.trigger.service", "snap.seeded.service",
    "serial-getty@ttyS0.service", "getty@tty1.service", "console-getty@tty1.service",
    "systemd-fsck-root.service", "plymouth-quit.service", "plymouth-quit-wait.service",
    "plymouth-read-write.service", "plymouth-start.service", "plymouth-sysinit.service",
    "man-db.service", "e2scrub_all.service", "e2scrub_reap.service", "sysstat-collect.service",
    "motd-news.service", "apport.service", "apport-autoreport.path", "unattended-upgrades.service",
    "pollinate.service", "ua-timer.service", "dnsmasq.service", "nvidia-persistenced.service",
    "nvidia-powerd.service", "openvpn.service", "winbind.service",
}

# Порты, которые по дизайну слушают ТОЛЬКО loopback/tailnet — «наружу» они не выставлены
PRIVATE_PORT_HINTS = {80, 443, 8090, 9119, 9090, 1080, 1086, 10801, 19999, 22, 8080}


def _run(argv: list[str], timeout: int = SUBPROCESS_TIMEOUT) -> str:
    """Выполнить команду и вернуть stdout. Любая ошибка → пустая строка.

    Команды ниже read-only и не требуют sudo: systemctl/ss/df/free работают
    на пользовательском уровне; при отсутствии доступа отчёт будет неполным,
    но не должен падать (мониторинг не должен роняться из-за привилегий)."""
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _run_units(scope: str) -> list[dict]:
    """Все unit-файлы сервисов (включая остановленные) с их состоянием.

    Берём list-unit-files, а не list-units: упавший сервис не появляется в
    list-units и исчезает из отчёта — именно такие «исчезновения» нужно видеть.

    Обрати внимание на пустой аргумент scope: `systemctl --user ""` — это НЕ «без
    флага», а юнит с пустым именем. Поэтому флаг строим списком, а не склейкой строк;
    пустой scope даёт команду без `--user` (системный режим)."""
    user_flag = ["--user"] if scope == "user" else []
    # В cron окружении нет XDG_RUNTIME_DIR/DBUS_SESSION_BUS_ADDRESS, и `systemctl --user`
    # падает с «Failed to connect to bus: No medium found», возвращая ПУСТОЙ вывод.
    # Раньше это давало ложный отчёт «0 user-юнитов» и reboot_risk=ok при слепом user-скопе.
    # Подставляем окружение пользовательского менеджера явно, с проверкой, что он существует.
    if scope == "user":
        uid = os.getuid()
        runtime = f"/run/user/{uid}"
        if not os.path.isdir(runtime):
            return [{
                "name": "(user systemd недоступен)",
                "active": "unknown",
                "enabled": "unknown",
                "unit_state": "unknown",
                "restart": "unknown",
                "kind": "user",
            }]
        os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
        os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    files = _run(["systemctl", *user_flag, "--no-legend", "--no-pager", "--plain",
                  "list-unit-files", "--type=service"]).splitlines()
    out: list[dict] = []
    for raw in files:
        parts = raw.split()
        if len(parts) < 2 or not parts[0].endswith(".service"):
            continue
        name = parts[0]
        # колонка unit_state из list-unit-files: enabled/disabled/linked/transient/…
        # Именно здесь systemd честно помечает transient-юниты, поэтому признак
        # «не переживёт ребут» берём отсюда, а не угадываем по имени.
        unit_state = parts[1] if len(parts) > 1 else "unknown"
        if name in (USER_NOISE if scope == "user" else SYSTEM_NOISE):
            continue
        # отсекаем шаблонные/чужие имена (getty@ssh, systemd-*, sshd@…), оставляя наши
        if name.startswith(("systemd-", "getty@", "console-getty@", "user@", "session-")):
            continue
        if name.startswith(("apt-daily", "apt-daily-upgrade", "app-", "snapd.")):
            continue
        if name.endswith(("-autostart.service",)):
            continue
        active = _run(["systemctl", *user_flag, "is-active", name]).strip().splitlines()[-1:] or ["unknown"]
        enabled = _run(["systemctl", *user_flag, "is-enabled", name]).strip().splitlines()[-1:] or ["unknown"]
        restart = _run(["systemctl", *user_flag, "show", name, "-p", "Restart", "--value"]).strip()
        out.append({
            "name": name,
            "active": active[0] or "unknown",
            "enabled": enabled[0] or "unknown",
            "unit_state": unit_state,
            "restart": restart or "no",
            "kind": scope,
        })
    return sorted(out, key=lambda s: s["name"])


def _containers() -> list[dict]:
    """Контейнеры. Пустой список ≠ «контейнеров нет»: без доступа к docker API
    отчёт обязан сказать «неизвестно», иначе получается ложно-зелёная картина
    (searxng выглядит выключенным, хотя работает)."""
    if not shutil.which("docker"):
        return []
    last_err = ""
    # сначала без sudo; если сокет закрыт — одна попытка через sudo -n (read-only ps).
    # sudo -n неинтерактивен: без правила NOPASSWD просто вернёт ошибку, ничего не спросив.
    for argv in (
        ["docker", "ps", "-a", "--format", "{{.Names}}\\t{{.State}}\\t{{.Status}}"],
        ["sudo", "-n", "docker", "ps", "-a", "--format", "{{.Names}}\\t{{.State}}\\t{{.Status}}"],
    ):
        raw = _run(argv, timeout=SUBPROCESS_TIMEOUT)
        if raw.strip():
            out = []
            for line in raw.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name, state = parts[0], parts[1]
                status = parts[2] if len(parts) > 2 else ""
                out.append({
                    "name": name,
                    "state": state,
                    "status": status,
                    "running": state == "running",
                    "restart": "unknown",  # политику из `docker inspect` намеренно не читаем
                })
            return sorted(out, key=lambda c: c["name"])
        # сохраняем причину для отчёта
        try:
            err = subprocess.run(argv[:2] if argv[0] == "sudo" else argv[:1],
                                 capture_output=True, text=True, timeout=5, check=False).stderr
            last_err = (err or "").strip().splitlines()[-1:] or ["empty output"]
        except (OSError, subprocess.SubprocessError):
            last_err = ["error"]
    # недоступно — возвращаем явный маркер вместо пустого списка
    return [{
        "name": "(docker API недоступен)",
        "state": "unknown",
        "status": last_err[0][:120] if last_err else "no output",
        "running": None,
        "restart": "unknown",
    }]


def _listeners() -> list[dict]:
    """Слушатели TCP/UDP с классификацией области видимости.

    Процесс (`users:`) виден только в выводе с правами root: без них колонки
    Process просто нет, и процесс остаётся пустым. Поэтому сначала пробуем
    обычный `ss -tulnp`, затем `sudo -n ss -tulnp` (read-only, неинтерактивно),
    затем `ss -tuln` (без процессов, но с портами) — чтобы раздел НИКОГДА не был
    молча пустым, когда данные есть."""
    raw = ""
    for argv in (["ss", "-tulnp"], ["sudo", "-n", "ss", "-tulnp"], ["ss", "-tuln"]):
        raw = _run(argv, timeout=SUBPROCESS_TIMEOUT)
        if raw.strip():
            break
    out: list[dict] = []
    for line in raw.splitlines()[1:]:
        fields = line.split()
        if not fields or fields[0] not in ("tcp", "udp", "tcp6", "udp6"):
            continue
        # НЕ фиксированный индекс: колонки `ss` сдвигаются в зависимости от
        # наличия Process/users и от версии. Берём ПЕРВОЕ поле вида addr:port —
        # это Local Address:Port; иначе порт молча терялся и раздел был пуст.
        local = next(
            (f for f in fields[1:]
             if ":" in f and f.rpartition(":")[2].isdigit()),
            "",
        )
        if not local:
            continue
        addr, _, port_s = local.rpartition(":")
        port = int(port_s)
        proc = ""
        if "users:((" in line:
            proc = line.split('users:(("', 1)[1].split('"', 1)[0]
        mgr = f"{addr.strip('[]')}:{port}"
        # Классификация по СЕМЕЙСТВУ адреса, а не по «0.0.0.0 или нет»:
        #  - 0.0.0.0 / ::            — все интерфейсы;
        #  - 127.x / ::1              — только локально;
        #  - 100.64/10, fd7a:…       — адреса tailnet (Tailscale), наружу не выставлены;
        #  - 10/8, 172.16/12, 192.168/16 — адреса ENI в VPC: снаружи НЕ видны, но трафик
        #    из интернета приходит на них (у EC2 публичный IP = 1:1 NAT), поэтому для
        #    «будет ли это видно снаружи» они эквивалентны публичному слушателю.
        # Ошибка этого раздела была именно здесь: 443 на 172.31.31.168 выглядел как
        # «не публичный» и мог бы скрыть потерю публичной поверхности.
        addr_n = addr.strip("[]")
        if addr_n in ("0.0.0.0", "::", "*", ""):
            public, scope = True, "all-interfaces"
        elif addr_n.startswith(("127.", "::1")):
            public, scope = False, "loopback"
        elif addr_n.startswith(("100.", "fd7a:")):
            public, scope = False, "tailnet"
        elif addr_n.startswith(("10.", "192.168.", "172.")) or ":" not in addr_n:
            public, scope = True, "vpc-eni"
        else:
            public, scope = True, "other"
        out.append({
            "port": port,
            "addr": mgr,
            "process": proc,
            "kind": "tcp" if fields[0].startswith("tcp") else "udp",
            "public": public,
            "scope": scope,
            "loopback_only": scope == "loopback",
        })
    # дедуп по (port, addr, process) — ss может печатать дубли для v4/v6
    seen, uniq = set(), []
    for item in out:
        key = (item["port"], item["addr"], item["process"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return sorted(uniq, key=lambda x: (x["port"], x["addr"]))


def _resources() -> dict:
    mem_total_mb = mem_avail_mb = None
    for line in _run(["free", "-m"]).splitlines():
        if line.lower().startswith("mem:"):
            cols = line.split()
            if len(cols) >= 7:
                mem_total_mb = int(cols[1])
                mem_avail_mb = int(cols[6])
    disk_pct = None
    for line in _run(["df", "-P", "/"]).splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 5 and cols[4].rstrip("%").isdigit():
            disk_pct = int(cols[4].rstrip("%"))
            break
    load1 = None
    try:
        load1 = round(os.getloadavg()[0], 2)
    except OSError:
        pass
    kernel = _run(["uname", "-r"]).strip()
    uptime_s = None
    try:
        with open("/proc/uptime", encoding="utf-8") as fh:
            uptime_s = int(float(fh.read().split()[0]))
    except (OSError, ValueError):
        pass
    return {
        "mem_total_mb": mem_total_mb,
        "mem_available_mb": mem_avail_mb,
        "disk_pct": disk_pct,
        "load1": load1,
        "kernel": kernel,
        "uptime_s": uptime_s,
    }


def _reboot_ready(user_units: list[dict], system_units: list[dict]) -> dict:
    """Готовность к ребуту: что НЕ поднимется само.

    Главный риск на этом сервере — user-юниты без `enabled` и без linger:
    они не стартуют после ребута, потому что пользователь не логинится по SSH.
    Поэтому linger проверяем явно, а не «по умолчанию считаем что есть»."""
    linger = _run(["loginctl", "show-user", os.environ.get("USER", "ubuntu"),
                   "-p", "Linger", "--value"]).strip() or "unknown"

    def _survives_reboot(unit: dict) -> bool:
        """Отсекаем то, что НЕ обязано переживать ребут.

        Transient-юниты (созданные `systemd-run --user`) и `.scope`-юниты по
        определению не имеют unit-файла в постоянном хранилище: они не могут быть
        `enabled`, и их пересоздаёт то, что их породило (например, c6-tunnel поднимает
        провайдерский туннель по таймеру). Считать их «не переживёт ребут» — ложная
        тревога, которая со временем приучает оператора игнорировать reboot_risk.
        """
        name = str(unit.get("name", ""))
        return (not name.endswith(".scope")
                and "transient" not in str(unit.get("unit_state", "")).lower())

    persistent_user = [s for s in user_units if _survives_reboot(s)]
    not_enabled = sorted(
        s["name"] for s in persistent_user
        if s["active"] == "active" and s["enabled"] != "enabled"
    )
    transient_active = sorted(
        s["name"] for s in user_units if not _survives_reboot(s) and s["active"] == "active"
    )
    active_total = sum(1 for s in persistent_user if s["active"] == "active")
    # системные юниты, активные, но disabled — ssh.service здесь норма (есть ssh.socket)
    sys_not_enabled = sorted(
        s["name"] for s in system_units
        if s["active"] == "active" and s["enabled"] == "disabled"
    )
    if not_enabled or linger != "yes":
        risk = "reboot_risk"
    else:
        risk = "ok"
    return {
        "linger": linger,
        "active_user_units_total": active_total,
        "active_user_units_not_enabled": not_enabled,
        "active_user_units_transient": transient_active,
        "active_system_units_disabled": sys_not_enabled,
        "reboot_risk": risk,
    }


def collect(timeout: int = SUBPROCESS_TIMEOUT) -> dict:
    user_units = _run_units("user")
    system_units = _run_units("system")
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "services": {"user": user_units, "system": system_units},
        "containers": _containers(),
        "listeners": _listeners(),
        "resources": _resources(),
        "reboot_ready": _reboot_ready(user_units, system_units),
    }


def write_report(report: dict, output: Path) -> None:
    """Атомарная запись: мониторинг читает файл в любой момент, поэтому
    полузаписанный JSON хуже, чем файл предыдущего цикла."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(output)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Сводка запущенных сервисов в JSON")
    ap.add_argument("--output", default=str(DEFAULT_OUT), help="путь к json-файлу")
    ap.add_argument("--timeout", type=int, default=SUBPROCESS_TIMEOUT, help="таймаут подкоманд, с")
    ap.add_argument("--quiet", action="store_true", help="без human-readable вывода")
    ap.add_argument("--print", dest="do_print", action="store_true", help="вывести json в stdout")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    report = collect(timeout=args.timeout)
    out = Path(args.output)
    try:
        write_report(report, out)
    except OSError as exc:
        print(f"service-status-snapshot: не удалось записать {out}: {exc}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - t0

    if args.do_print:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    if not args.quiet and not args.do_print:
        r = report["reboot_ready"]
        res = report["resources"]
        print(f"service-status-snapshot: {out}")
        print(
            f"  юниты: user={len(report['services']['user'])} "
            f"(active {r['active_user_units_total']}), system={len(report['services']['system'])}"
        )
        print(f"  контейнеры: {len(report['containers'])}, слушателей: {len(report['listeners'])}")
        print(
            f"  ресурсы: RAM avail {res['mem_available_mb']}MB / {res['mem_total_mb']}MB, "
            f"disk {res['disk_pct']}%, load {res['load1']}, kernel {res['kernel']}"
        )
        print(
            f"  готовность к ребуту: {r['reboot_risk']} "
            f"(linger={r['linger']}, не включены: {r['active_user_units_not_enabled'] or 'нет'})"
        )
        print(f"  собрано за {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
