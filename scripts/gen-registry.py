#!/usr/bin/env python3
"""gen-registry.py — генерирует registry.yaml из текста hermes_cli/config_defaults.py.

Решение 2026-09-06 (план, раздел 12): парсим ТЕКСТ файла (балансный сканер +
ast-валидация блока OPTIONAL_ENV_VARS), НЕ импортируем пакет hermes_cli —
генератор работает на любой машине без установленного Hermes и без side
effects init-цепочки. Запускается на сервере (там живёт config_defaults.py),
результат registry.yaml коммитится в корень репо.

Использование:
  python3 scripts/gen-registry.py [--source PATH] [--out PATH] [--hermes-version V]

Только stdlib. Детерминированный вывод (кроме meta.generated_at).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SOURCE = Path.home() / ".hermes" / "hermes-agent" / "hermes_cli" / "config_defaults.py"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "registry.yaml"

# Free-флаг: провайдер/модель на free-тире (regex из плана, раздел 10)
FREE_RE = re.compile(r"(?:^|[:\-_/])free(?:$|[:\-_/])", re.IGNORECASE)

# Провайдеры без free-маркера в имени — явный free-флаг. Заполняется вручную
# по данным fallback-tracker (план, раздел 10). Ревью Питной 06.09: на сервере
# список пуст — free-тиры это MODEL-уровень (minimax-m3 через opencode-go),
# провайдер OPENCODE_GO_API_KEY обслуживает и платные primary-модели, помечать
# его целиком free = ложь. Модельный список (explicit_free_models) — вопрос B3.
EXPLICIT_FREE_PROVIDERS: list[str] = []

# kit-группы argus: ключи, которые деплоит сам kit (предложение ZCode,
# сверить на ревью). check — примитив health-check-v2 по умолчанию.
KIT_ENTRIES = [
    {"key": "WATCHDOG_BOT_TOKEN", "group": "watchdog", "check": "env",
     "description": "Токен Telegram-бота мониторинга"},
    {"key": "WATCHDOG_CHAT_ID", "group": "watchdog", "check": "env",
     "description": "Чат для алертов мониторинга"},
    {"key": "HERMES_BOT_TOKEN", "group": "watchdog", "check": "env",
     "description": "Токен основного бота Hermes (команды /logs)"},
    {"key": "HERMES_BOT_UID", "group": "watchdog", "check": "env",
     "description": "Telegram UID владельца (доступ к командам)"},
    {"key": "TELEGRAM_PROXY", "group": "proxy", "check": "tcp",
     "description": "Smart-proxy для Telegram (по умолчанию 127.0.0.1:8444)"},
    {"key": "DMS_SNITCH", "group": "infra", "check": "env",
     "description": "ID snitch Dead Man's Snitch"},
    {"key": "DMS_API_KEY", "group": "infra", "check": "env",
     "description": "API-ключ Dead Man's Snitch"},
    {"key": "GH_TOKEN", "group": "infra", "check": "env",
     "description": "GitHub PAT для gh-heartbeat"},
]

HELPER_WHITELIST = {"_env", "_prov", "_tool", "_msg", "_skill", "_setting", "_base_url"}

# Порядок полей записи в registry.yaml (детерминированный)
FIELD_ORDER = ("description", "prompt", "category", "help", "url", "tools",
               "password", "advanced")


# ── Извлечение блока ────────────────────────────────────────────────────────

def extract_block(text: str) -> str:
    """Балансный сканер: блок OPTIONAL_ENV_VARS = { ... } с учётом строк."""
    m = re.search(r"^OPTIONAL_ENV_VARS\s*=\s*", text, re.M)
    if not m:
        sys.exit("FATAL: OPTIONAL_ENV_VARS не найден в источнике")
    start = text.index("{", m.end())
    depth = 0
    quote = ""
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                quote = ""
            continue
        if c in "\"'":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    sys.exit("FATAL: блок OPTIONAL_ENV_VARS не закрыт")


# ── Вычисление блока ────────────────────────────────────────────────────────

def build_helpers() -> dict:
    """Реэмплементация хелперов config_defaults.py (строго по исходнику)."""
    _OMIT = object()

    def _env(description, prompt, **keys):
        return {"description": description, "prompt": prompt, **keys}

    def _category(category, password, advanced):
        def make(description, prompt, url=_OMIT, *, help=_OMIT, tools=_OMIT,
                 password=password, advanced=advanced):
            d = {"description": description, "prompt": prompt}
            d.update((k, v) for k, v in (("help", help), ("url", url), ("tools", tools))
                     if v is not _OMIT)
            if password is not None:
                d["password"] = password
            d["category"] = category
            if advanced:
                d["advanced"] = True
            return d

        return make

    def _base_url(name, prompt_name=None):
        prompt = f"{prompt_name or name} base URL (leave empty for default)"
        return _prov(f"{name} base URL override", prompt, None, password=False)

    _prov = _category("provider", password=True, advanced=True)
    _tool = _category("tool", password=True, advanced=False)
    _msg = _category("messaging", password=False, advanced=False)
    _skill = _category("skill", password=True, advanced=True)
    _setting = _category("setting", password=False, advanced=False)

    return {
        "_env": _env,
        "_prov": _prov,
        "_tool": _tool,
        "_msg": _msg,
        "_skill": _skill,
        "_setting": _setting,
        "_base_url": _base_url,
    }


def eval_block(block: str, helpers: dict) -> dict:
    """ast-парсинг + строгая валидация + eval в песочнице (без builtins).

    Разрешены только вызовы whitelist-хелперов с константами (строки, булевы,
    числа, None) и списками констант — всё остальное Fatal.
    """
    tree = ast.parse(block, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in HELPER_WHITELIST):
                sys.exit(f"FATAL: вызов вне whitelist (line {node.lineno})")
        elif isinstance(node, ast.Name):
            if node.id not in HELPER_WHITELIST:
                sys.exit(f"FATAL: имя вне whitelist: {node.id}")
        elif not isinstance(node, (ast.Expression, ast.Dict, ast.Constant, ast.List,
                                   ast.Load, ast.keyword)):
            sys.exit(f"FATAL: узел {type(node).__name__} не разрешён (line {node.lineno})")
    return eval(compile(tree, "<registry>", "eval"), {"__builtins__": {}}, dict(helpers))


# ── YAML-эмиттер ────────────────────────────────────────────────────────────
# Строки/скаляры через json.dumps (JSON double-quoted строки валидны в YAML),
# списки — JSON flow, словари — block-style. Детерминированно.

def yscalar(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def yinline(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def ydict(d: dict, indent: str = "") -> list[str]:
    lines = []
    for k, v in d.items():
        key = k if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) else json.dumps(k, ensure_ascii=False)
        if isinstance(v, dict):
            lines.append(f"{indent}{key}:")
            lines.extend(ydict(v, indent + "  "))
        elif isinstance(v, list):
            lines.append(f"{indent}{key}: {yinline(v)}")
        else:
            lines.append(f"{indent}{key}: {yscalar(v)}")
    return lines


def ylist_of_dicts(items: list[dict], indent: str = "  ") -> list[str]:
    lines = []
    for item in items:
        first = True
        for k, v in item.items():
            if v is None:
                continue
            key = k if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) else json.dumps(k, ensure_ascii=False)
            prefix = f"{indent}- " if first else f"{indent}  "
            first = False
            if isinstance(v, list):
                lines.append(f"{prefix}{key}: {yinline(v)}")
            else:
                lines.append(f"{prefix}{key}: {yscalar(v)}")
    return lines


def emit_registry(meta: dict, entries: dict) -> str:
    lines = [
        "# hermes-argus registry — сгенерирован scripts/gen-registry.py, НЕ править руками.",
        "# Источник: OPTIONAL_ENV_VARS из hermes_cli/config_defaults.py (текстовый парсинг).",
        "# Регенерация: python3 scripts/gen-registry.py (на сервере, где установлен Hermes).",
    ]
    lines.extend(ydict({"meta": meta}))
    lines.append(f"free_regex: {yscalar(FREE_RE.pattern)}")
    lines.append(f"explicit_free_providers: {yinline(EXPLICIT_FREE_PROVIDERS)}")
    lines.append("kit_entries:")
    lines.extend(ylist_of_dicts(KIT_ENTRIES, indent="  "))
    lines.append("entries:")
    for key, d in entries.items():
        rec = {"key": key}
        for f in FIELD_ORDER:
            if f in d and d[f] is not None:
                rec[f] = d[f]
        # free = провайдер на free-тире: regex по имени ключа ИЛИ явный список
        # (фикс ревью 06.09: раньше explicit-список учитывался только в принте)
        rec["free"] = (bool(FREE_RE.search(key)) or key in EXPLICIT_FREE_PROVIDERS) \
            if d.get("category") == "provider" else False
        lines.extend(ylist_of_dicts([rec], indent="  "))
    return "\n".join(lines)


# ── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Генератор registry.yaml для hermes-argus")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                    help="путь к config_defaults.py")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="путь к registry.yaml")
    ap.add_argument("--hermes-version", default=None,
                    help="версия Hermes-агента (для meta)")
    args = ap.parse_args()

    text = args.source.read_text(encoding="utf-8")
    block = extract_block(text)
    entries = eval_block(block, build_helpers())

    seen: set[str] = set()
    for key, d in entries.items():
        if key in seen:
            sys.exit(f"FATAL: дубль ключа {key}")
        seen.add(key)
        if "description" not in d or "category" not in d:
            sys.exit(f"FATAL: {key} без description/category")
    if len(entries) < 100:
        print(f"WARNING: подозрительно мало записей: {len(entries)}", file=sys.stderr)

    meta = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": args.source.name,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "entry_count": len(entries),
    }
    if args.hermes_version:
        meta["hermes_version"] = args.hermes_version

    # newline="\n": детерминированный LF-вывод на любой ОС (Windows-трансляция ломает diff)
    args.out.write_text(emit_registry(meta, entries) + "\n", encoding="utf-8", newline="\n")

    cats = Counter(d.get("category") for d in entries.values())
    free_hits = [k for k, d in entries.items()
                 if d.get("category") == "provider"
                 and (bool(FREE_RE.search(k)) or k in EXPLICIT_FREE_PROVIDERS)]
    print(f"OK: {len(entries)} записей + {len(KIT_ENTRIES)} kit -> {args.out}")
    print(f"категории: {dict(cats)}")
    print(f"free по regex: {len(free_hits)}: {free_hits}")


if __name__ == "__main__":
    main()
