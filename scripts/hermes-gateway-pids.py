#!/usr/bin/env python3
"""Каноническая проверка живости hermes gateway для шелл-скриптов.

2026-09-30: `hermes-watchdog.sh` и `gateway-liveness.sh` искали процесс через
`pgrep -f "hermes_cli.main gateway run"` — argv-подстроку. Апдейт Hermes в
03:06 сменил форму запуска на runpy (`hermes_cli/main.py`, 'gateway', 'run'),
паттерн перестал совпадать: 33 ложных «Gateway процесс НЕ НАЙДЕН» за 3 часа
и — хуже — `gateway-liveness.sh` молча выходил с кодом 0, не проверяв живость
вообще. Апстрим это прямо запрещает: «Never infer process identity from argv
substrings» (hermes_cli/AGENTS.md; баг-класс ~10 fleet-update issues).

Здесь используется канонический матчер апстрима
`gateway.status.looks_like_gateway_command_line`, который держит обе формы
запуска и не срабатывает на самом pgrep.

Использование (в stdout — PID'ы, по одному в строке; пусто = не найден):
    GATEWAY_PIDS=$(hermes-gateway-pids.py)     # сколько угодно, без ошибки
    hermes-gateway-pids.py --count             # только количество (для if)
    hermes-gateway-pids.py --quiet             # ничего не печатать, код возврата

Код возврата: 0 — найден хотя бы один, 1 — не найден, 2 — ошибка окружения
(матчер недоступен). Не подменяем «не найден» на «нашёл» и наоборот: при
недоступном импорте честный код 2, чтобы вызывающий не решил, что процесс мёртв.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# HERMES_HOME может быть не экспортирован в cron — берём из профиля по умолчанию.
AGENT_DIR = Path.home() / ".hermes" / "hermes-agent"
# В cron `python3` — это /usr/bin/python3, где пакет hermes НЕ установлен.
# Матчер живёт в venv Hermes, поэтому интерпретатор выбирается явно, иначе
# помощник откажет (код 2) ровно там, где нужна проверка.
VENV_PYTHON = AGENT_DIR / "venv" / "bin" / "python"
_REEXEC_FLAG = "HERMES_GATEWAY_PIDS_REEXEC"


def _load_matcher():
    """Импорт канонического матчера. None = окружение сломано (код 2)."""
    if not AGENT_DIR.is_dir():
        return None
    try:
        if str(AGENT_DIR) not in sys.path:
            sys.path.insert(0, str(AGENT_DIR))
        from gateway.status import looks_like_gateway_command_line
    except Exception:
        return None
    return looks_like_gateway_command_line


def _reexec_under_venv() -> None:
    """Перезапуск под интерпретатором venv, если текущий — не тот.

    Cron отдаёт `/usr/bin/python3`, где `gateway` не импортируется: без
    re-exec помощник отвечал бы «матчер недоступен» именно там, где
    watchdog обязан проверять живость. Один ре-исп, без цикла.
    """
    if os.environ.get(_REEXEC_FLAG):
        return  # уже пробовали — дальше только честный отказ
    if os.path.realpath(sys.executable) == os.path.realpath(str(VENV_PYTHON)):
        return  # уже правильный интерпретатор
    if not VENV_PYTHON.exists():
        return
    env = dict(os.environ, **{_REEXEC_FLAG: "1"})
    os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), os.path.abspath(__file__), *sys.argv[1:]], env)


def live_gateway_pids(matcher) -> list[int]:
    """PID'ы процессов, чья полная cmdline — настоящий `gateway run`.

    `pgrep` здесь ТОЛЬКО сужает множество (дёшево), а решение принимает
    канонический матчер по полной cmdline: сам по себе pgrep и есть тот
    argv-substring-хак, который мы чиним. Полный скан /proc стоит ~1.6 с
    (204 процесса), pgrep+матчер — ~1 мс, а watchdog крутится каждые 5 минут,
    liveness — каждые 2.

    Только наш HERMES_HOME: чужой gateway с другого install не считается.
    """
    import subprocess

    from gateway.status import _read_process_cmdline  # каноническое чтение cmdline

    try:
        found = subprocess.run(
            ["pgrep", "-f", "gateway"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    # pgrep может найти и нас самих (в cmdline есть слово 'gateway') —
    # это не страшно: решение всё равно принимает матчер.
    candidates = [int(tok) for tok in found.stdout.split() if tok.isdigit()]

    pids: list[int] = []
    for pid in candidates:
        if pid in (1, os.getpid()):
            continue
        cmdline = _read_process_cmdline(pid)
        if not cmdline or not matcher(cmdline):
            continue
        # принадлежность install'у: путь к агенту в cmdline
        if str(AGENT_DIR) not in cmdline:
            continue
        pids.append(pid)
    return pids


def main(argv: list[str]) -> int:
    _reexec_under_venv()
    matcher = _load_matcher()
    if matcher is None:
        # Окружение недоступно → честный отказ, а не «процесс мёртв».
        print(
            "gateway-pids: канонический матчер недоступен "
            f"({AGENT_DIR} не найден или импорт не удался)",
            file=sys.stderr,
        )
        return 2
    pids = live_gateway_pids(matcher)
    if "--count" in argv:
        print(len(pids))
    elif "--quiet" not in argv:
        for pid in pids:
            print(pid)
    return 0 if pids else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
