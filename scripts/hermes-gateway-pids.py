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
import subprocess
import sys
import tempfile
from pathlib import Path

# Контракт A (2026-10-25): корень установки привязывается к выбранной
# установке ($HERMES_DIR / $HERMES_HOME / ~/.hermes — та же цепочка, что у
# адаптера hermes-runtime.py), а не только к домашнему профилю: иначе при
# нестандартном home помощник и адаптер разошлись бы по разным установкам.
def _agent_dir() -> Path:
    base = (os.environ.get("HERMES_DIR") or os.environ.get("HERMES_HOME")
            or (Path.home() / ".hermes"))
    return Path(base) / "hermes-agent"


AGENT_DIR = _agent_dir()
# Интерпретатор Hermes больше не фиксирован как venv/bin/python — PM-установка
# v0.22.5 удаляет in-checkout venv после коммита поколения зависимостей. Выбор
# рантайма делает адаптер hermes-runtime.py (опубликованный лаунчер или
# легаси-venv), резолв — на каждый запуск.
RUNTIME_ADAPTER = Path(__file__).resolve().parent / "hermes-runtime.py"
_REEXEC_FLAG = "HERMES_GATEWAY_PIDS_REEXEC"
# Файл, куда потомок пишет свой ИТОГОВЫЙ код работы. Отличает «помощник
# отработал и честно ответил (в т.ч. 1 = не найден)» от «запуск под рантаймом
# не удался» (креш python без нашего кода тоже выходит с кодом 1): нет файла —
# окружение, честный код 2, не ложное «не найден».
_RESULT_ENV = "HERMES_GATEWAY_PIDS_RESULT"


def _mark_result(rc: int) -> None:
    """Потомок фиксирует выполненную работу (вызывается только с env-меткой)."""
    path = os.environ.get(_RESULT_ENV)
    if not path:
        return
    try:
        with open(path, "w", encoding="ascii") as f:
            f.write(str(rc))
    except OSError:
        pass


def _reexec_under_runtime():
    """Запуск себя под рантаймом Hermes, если матчер здесь не импортируется.

    Cron отдаёт `/usr/bin/python3`, где `gateway` может не импортироваться:
    без re-exec помощник отвечал бы «матчер недоступен» именно там, где
    watchdog обязан проверять живость. Один подпроцесс через адаптер, без
    цикла: адаптер резолвит текущую установку (лаунчер или легаси-venv) и
    exec'ает этот же скрипт под выбранным интерпретатором; stdout/stderr
    проходят наружу как свои. Возвращает False, если работать будем сами.
    Код результата (когда работу выполнил потомок) выходит через sys.exit:
    0/1 — только при подтверждённом файлом итоге; любой другой исход —
    окружение, честный код 2, не «процесс мёртв» и не ложное «не найден»."""
    if os.environ.get(_REEXEC_FLAG):
        return False  # уже под рантаймом — работаем сами
    if not RUNTIME_ADAPTER.is_file():
        return False  # модуль-only установка без адаптера: честный отказ ниже
    try:
        fd, result_path = tempfile.mkstemp(prefix="hermes-gwp-")
        os.close(fd)
    except OSError:
        # Нет временного хранилища — нельзя отличить честный 1 от креша:
        # честный отказ (код 2 через matcher-None), не ложное «не найден».
        return False
    env = dict(os.environ, **{_REEXEC_FLAG: "1", _RESULT_ENV: result_path})
    try:
        rc = subprocess.call(
            [sys.executable, str(RUNTIME_ADAPTER), "run-script",
             os.path.abspath(__file__), *sys.argv[1:]], env=env)
        try:
            with open(result_path, encoding="ascii") as f:
                child_rc = int(f.read().strip() or "999")
        except (OSError, ValueError):
            child_rc = 999  # итог не подтверждён — запуск не удался
    except OSError:
        return False  # exec не удался — честный отказ ниже, не крах
    finally:
        try:
            os.unlink(result_path)
        except OSError:
            pass
    sys.exit(child_rc if child_rc in (0, 1) else 2)


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


def live_gateway_pids(matcher) -> list[int]:
    """PID'ы процессов, чья полная cmdline — настоящий `gateway run`.

    `pgrep` здесь ТОЛЬКО сужает множество (дёшево), а решение принимает
    канонический матчер по полной cmdline: сам по себе pgrep и есть тот
    argv-substring-хак, который мы чиним. Полный скан /proc стоит ~1.6 с
    (204 процесса), pgrep+матчер — ~1 мс, а watchdog крутится каждые 5 минут,
    liveness — каждые 2.

    Только наш HERMES_HOME: чужой gateway с другого install не считается.
    """
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
    if not _reexec_under_runtime():
        matcher = _load_matcher()
        if matcher is None:
            # Окружение недоступно → честный отказ, а не «процесс мёртв».
            print(
                "gateway-pids: канонический матчер недоступен "
                f"({AGENT_DIR} не найден или импорт не удался)",
                file=sys.stderr,
            )
            _mark_result(2)
            return 2
        pids = live_gateway_pids(matcher)
        rc = 0 if pids else 1
        _mark_result(rc)
        if "--count" in argv:
            print(len(pids))
        elif "--quiet" not in argv:
            for pid in pids:
                print(pid)
        return rc
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
