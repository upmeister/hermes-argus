#!/usr/bin/env python3
"""hermes-runtime.py — установка-привязанный адаптер запуска Hermes для Argus.

Контекст (контракт A, 2026-10-25): Hermes PM начиная с v0.22.5 после коммита
поколения зависимостей УДАЛЯЕТ старый in-checkout `venv/`; публикуется
стабильный лаунчер `<checkout>/.hermes/bin/hermes` (shell-обёртка над store
Python), который сам выбирает актуальное поколение при каждом старте. Argus
жёстко прописывал `hermes-agent/venv/bin/...` в preflight, MCP-дефолте,
gateway-помощнике и юнитах — валидная PM-установка без легаси-venv отвергалась
или становилась ненаблюдаемой.

Границы адаптера (намеренно узкие):
  - привязка к КОНФИГУРИРУЕМОМУ корню установки ($HERMES_DIR/hermes-agent,
    по умолчанию ~/.hermes/hermes-agent), а не к произвольному `hermes` в PATH;
  - опубликованный лаунчер ЕСТЬ → используется он; он есть, но не работает —
    явный отказ, БЕЗ отката на протухший venv (A3);
  - лаунчера НЕТ → легаси-раскладка: in-tree `venv/bin/{python,hermes}` (A2);
  - машинная граница лаунчера `--print-runtime-command` (JSON-список argv,
    «Resolve this installation's launch command») используется по назначению —
    для РЕЗОЛВА рантайм-интерпретатора установки на каждый запуск. Вход
    лаунчера исполняет entry point hermes_cli.main; вариант `--module runpy`
    передаёт аргумент как ИМЯ МОДУЛЯ (подтверждено на реальной v0.22.5,
    python 3.14: `python -m runpy <путь>` ищет модуль, а не файл), поэтому
    скрипты Argus запускаются компоновкой апстримовской формы (как в
    hermes_cli/venv_sync.py): checkout на sys.path + `import hermes_bootstrap`
    (активация выбранного поколения зависимостей) + `runpy.run_path`. Скрипт
    получает полный рантайм Hermes: без него канонический матчер
    `gateway.status` не импортируется (модульно тянет ruamel.yaml).
    Интерпретатор НИКОГДА не кэшируется и не персистится — смена
    поколения/repin Python подхватывается при следующем запуске (A4).

Режимы:
  hermes <args...>               exec CLI Hermes через выбранный лаунчер
  run-script <script> [args...]  exec скрипта Argus под рантайм-интерпретатором
  check                          capability-проба preflight (ничего не мутирует)

Коды возврата: 0 — успех; 2 — рантайм недоступен/не работает; 3 — лаунчер
вернул некорректные данные; 64 — ошибка использования. Диагностика — только
классификация причины, без сырого вывода дочернего процесса: в диагностике
лаунчера нет места секретам, но и не нам её пересказывать (A3).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Резолв лаунчера вызывает настоящий код Hermes (импорты + возможный
# launch-time repair); граница обязана быть ограниченной.
LAUNCH_QUERY_TIMEOUT = 60

# Компоновка запуска скрипта Argus под рантаймом (та же форма, что строит
# сам апстрим в hermes_cli/venv_sync.py: sys.path.insert + runpy.run_path).
# hermes_bootstrap — штатный вход лаунчера: активирует выбранное поколение
# зависимостей и закрепляет HERMES_HOME на каждый старт. Ничего из
# внутренней кухни PM не копируется.
BOOTSTRAP_CODE = (
    "import sys, runpy; "
    "sys.path.insert(0, sys.argv.pop(1)); "
    "import hermes_bootstrap; "
)
RUNNER_CODE = BOOTSTRAP_CODE + (
    "script = sys.argv.pop(1); sys.argv[0] = script; "
    "runpy.run_path(script, run_name='__main__')"
)

RC_OK = 0
RC_RUNTIME = 2
RC_MALFORMED = 3
RC_USAGE = 64


def hermes_root() -> Path:
    """Корень установки Hermes: `$HERMES_DIR`/`$HERMES_HOME`/~/.hermes +
    hermes-agent. Никакого PATH. HERMES_DIR — соглашение Argus, HERMES_HOME —
    Hermes (его выставляют юниты); оба должны означать один и тот же home,
    чтобы все потребители установки соглашались о корне."""
    base = (os.environ.get("HERMES_DIR") or os.environ.get("HERMES_HOME")
            or (Path.home() / ".hermes"))
    return Path(base) / "hermes-agent"


def published_launcher(root: Path) -> Path | None:
    """Опубликованный лаунчер `<root>/.hermes/bin/hermes` или None, если его нет.

    Висячая ссылка — НЕ «отсутствие» (lexists): сломанный лаунчер отлится в
    явный отказ ниже, а не в молчаливый откат на легаси-venv. Неисполняемый
    файл — тоже НЕ «отсутствие»."""
    path = root / ".hermes" / "bin" / "hermes"
    return path if (path.exists() or path.is_symlink()) else None


class RuntimeUnavailable(Exception):
    """Рантайм недоступен (нет установки/venv/не исполняется) — код 2."""
    rc = RC_RUNTIME


class RuntimeMalformed(Exception):
    """Лаунчер ответил, но данные непригодны — код 3."""
    rc = RC_MALFORMED


def _require_executable(path: Path, what: str) -> None:
    if not path.is_file():
        raise RuntimeUnavailable(f"{what} отсутствует: {path}")
    if not os.access(path, os.X_OK):
        raise RuntimeUnavailable(f"{what} не исполняем: {path}")


def resolve_cli_argv(root: Path) -> list[str]:
    """argv для запуска CLI Hermes (`hermes <args>`). Не исполняет."""
    launcher = published_launcher(root)
    if launcher is not None:
        _require_executable(launcher, "опубликованный лаунчер Hermes")
        return [str(launcher)]
    venv_hermes = root / "venv" / "bin" / "hermes"
    _require_executable(root / "venv" / "bin" / "python", "интерпретатор Hermes venv")
    _require_executable(venv_hermes, "Hermes-исполняемый venv")
    return [str(venv_hermes)]


def _query_runtime_command(launcher: Path) -> list[str]:
    """Машинная граница `--print-runtime-command` → JSON-argv лаунчера."""
    try:
        proc = subprocess.run(
            [str(launcher), "--print-runtime-command"],
            capture_output=True, text=True, timeout=LAUNCH_QUERY_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeUnavailable(
            f"лаунчер не ответил за {LAUNCH_QUERY_TIMEOUT}s (--print-runtime-command)") from None
    except OSError as exc:
        raise RuntimeUnavailable(f"лаунчер не запустился: {exc.__class__.__name__}") from None
    if proc.returncode != 0:
        # Классификация без сырого дампа: код возврата достаточен для
        # оператора (починка — штатным workflow Hermes, не Argus).
        raise RuntimeUnavailable(f"лаунчер завершился с кодом {proc.returncode}")
    try:
        argv = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeMalformed(
            "лаунчер вернул не-JSON (--print-runtime-command)") from None
    if not isinstance(argv, list) or len(argv) < 4:
        raise RuntimeMalformed(
            "argv лаунчера непригоден: ожидался непустой список строк "
            f"[interpreter, ...], получено "
            f"{type(argv).__name__} длиной {len(argv) if isinstance(argv, list) else 'n/a'}")
    if not all(isinstance(tok, str) and tok for tok in argv):
        raise RuntimeMalformed("argv лаунчера содержит не-строковые токены")
    # Классификация без пересказа содержимого ответа лаунчера (A3): сам путь
    # может быть произвольными данными ответа, не публикуем его в диагностику.
    if not Path(argv[0]).is_file():
        raise RuntimeMalformed(
            "интерпретатор из argv лаунчера отсутствует на диске")
    if not os.access(argv[0], os.X_OK):
        raise RuntimeMalformed(
            "интерпретатор из argv лаунчера не исполняем")
    return argv


def resolve_runtime_interpreter(root: Path) -> str:
    """Путь к рантайм-интерпретатору установки на ЭТОТ запуск.

    Managed: argv[0] машинной границы лаунчера (store Python, переживает
    смену поколений и repin — потому что резолвится заново каждый раз).
    Легаси: in-tree `venv/bin/python`."""
    launcher = published_launcher(root)
    if launcher is not None:
        _require_executable(launcher, "опубликованный лаунчер Hermes")
        return _query_runtime_command(launcher)[0]
    venv_python = root / "venv" / "bin" / "python"
    _require_executable(venv_python, "интерпретатор Hermes venv")
    return str(venv_python)


def cmd_check(root: Path) -> int:
    """Capability-проба preflight: без CLI/API, с активацией managed runtime.

    Managed: прогоняется реальная граница `--print-runtime-command` (это
    выполняет код Hermes-лаунчера), затем штатный bootstrap. Legacy:
    существование+исполнимость venv-пар и безобидный `import sys`."""
    try:
        launcher = published_launcher(root)
        if launcher is not None:
            interpreter = resolve_runtime_interpreter(root)
            try:
                probe = subprocess.run(
                    [interpreter, "-I", "-c", BOOTSTRAP_CODE +
                     "print('argus-runtime-ready')", str(root)],
                    capture_output=True, text=True, timeout=LAUNCH_QUERY_TIMEOUT,
                    check=False)
            except (subprocess.TimeoutExpired, OSError) as exc:
                raise RuntimeUnavailable(
                    f"managed capability: {exc.__class__.__name__}") from None
            if probe.returncode != 0:
                raise RuntimeUnavailable(f"managed capability: код {probe.returncode}")
            if "argus-runtime-ready" not in probe.stdout.splitlines():
                raise RuntimeUnavailable("managed capability: выполнение не подтверждено")
            print(f"check: managed layout, launcher {launcher}, "
                  f"runtime capability verified (not API/login health)")
            return RC_OK
        venv_python = root / "venv" / "bin" / "python"
        _require_executable(venv_python, "интерпретатор Hermes venv")
        _require_executable(root / "venv" / "bin" / "hermes", "Hermes-исполняемый venv")
        try:
            probe = subprocess.run(
                [str(venv_python), "-c", "import sys; sys.exit(0)"],
                capture_output=True, text=True, timeout=LAUNCH_QUERY_TIMEOUT,
                check=False)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise RuntimeUnavailable(
                f"проба интерпретатора не выполнилась: "
                f"{exc.__class__.__name__}") from None
        if probe.returncode != 0:
            raise RuntimeUnavailable(
                f"интерпретатор Hermes не работает (код {probe.returncode})")
        print("check: legacy layout, venv interpreter работоспособен")
        return RC_OK
    except (RuntimeUnavailable, RuntimeMalformed) as exc:
        print(f"hermes-runtime: {exc}", file=sys.stderr)
        print("   Argus не устанавливает Hermes: почините установку штатным "
              "workflow Hermes и повторите.", file=sys.stderr)
        return getattr(exc, "rc", RC_RUNTIME)


def _exec(argv: list[str]) -> None:
    """exec без шелла; неудача исполнения — bounded отказ (код 2), не traceback."""
    try:
        os.execve(argv[0], argv, dict(os.environ))
    except OSError as exc:
        raise RuntimeUnavailable(
            f"запуск резолвнутого рантайма не удался ({exc.__class__.__name__})") from None


def cmd_hermes(root: Path, args: list[str]) -> int:
    if not args:
        print("hermes-runtime: режим `hermes` требует аргументов CLI",
              file=sys.stderr)
        return RC_USAGE
    argv = resolve_cli_argv(root) + args
    _exec(argv)


def cmd_run_script(root: Path, args: list[str]) -> int:
    if not args:
        print("hermes-runtime: режим `run-script` требует путь к скрипту",
              file=sys.stderr)
        return RC_USAGE
    script = Path(args[0])
    if not script.is_absolute():
        print(f"hermes-runtime: путь к скрипту обязан быть абсолютным: {script}",
              file=sys.stderr)
        return RC_USAGE
    if not script.is_file():
        print(f"hermes-runtime: скрипт не найден: {script}", file=sys.stderr)
        return RC_USAGE
    interpreter = resolve_runtime_interpreter(root)
    # -I: изоляция от окружения вызывающего (окружение cron не протекает в
    # рантайм). Managed: RUNNER_CODE ставит checkout на sys.path, импортирует
    # hermes_bootstrap (активация поколения + HERMES_HOME) и исполняет скрипт
    # через runpy.run_path — каталог скрипта становится sys.path[0] (соседи
    # импортируются). Legacy — venv python запускает скрипт напрямую, как и
    # прежний запуск под venv.
    if published_launcher(root) is not None:
        argv = [interpreter, "-I", "-c", RUNNER_CODE,
                str(root), str(script), *args[1:]]
    else:
        argv = [interpreter, str(script), *args[1:]]
    _exec(argv)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return RC_OK if argv else RC_USAGE
    mode, rest = argv[0], argv[1:]
    root = hermes_root()
    if not root.is_dir():
        print(f"hermes-runtime: не найден корень установки Hermes: {root}",
              file=sys.stderr)
        return RC_RUNTIME
    try:
        if mode == "check":
            return cmd_check(root)
        if mode == "hermes":
            return cmd_hermes(root, rest)
        if mode == "run-script":
            return cmd_run_script(root, rest)
    except (RuntimeUnavailable, RuntimeMalformed) as exc:
        # Bounded-отказ для ВСЕХ режимов: классификация причины без сырого
        # вывода дочернего процесса и без traceback (A3).
        print(f"hermes-runtime: {exc}", file=sys.stderr)
        return exc.rc
    print(f"hermes-runtime: неизвестный режим {mode!r} "
          f"(ожидались: hermes | run-script | check)", file=sys.stderr)
    return RC_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
