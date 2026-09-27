#!/usr/bin/env python3
"""local_services_check.py — консьюмер снимка локальной топологии (schema-1).

Контракт: docs/handoffs/local-services-contract.md (docs PR #55, merged).
Сравнивает operator-манифест ожидаемых systemd --user юнитов с observed-снимком
service-status-snapshot.py и ведёт узкий алерт-контур:

  healthy = свежий валидный снимок явно перечисляет цель и systemd active
  failed  = свежий валидный снимок: inactive/failed при expect=active
  unknown = устаревший/нечитаемый/битый источник, юнита нет в снимке или
            состояние неконclusive. unknown НИКОГДА не снимает алерт.

Алерт — после двух ПОДРЯД РАЗНЫХ свежих снимков с failed (разные
generated_at). Один и тот же снимок, прочитанный дважды, — одно наблюдение.
Один свежий healthy после алерта — одно сообщение о восстановлении и сброс.
Производитель недоступен после настроенных целей — дедуплицированный
диагностик после двух отдельных попыток сбора, не «наблюдаемый сбой сервиса».

Границы (намеренно НЕ делаем): никаких старт/стоп/рестартов, никаких сетевых
проб, никакого вывода топологии (контейнеры/порты/адреса) наружу; модуль OFF —
мгновенный выход без чтения состояния (защита и от забытой cron-строки).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
MANIFEST_PATH = Path.home() / ".config" / "hermes-argus" / "local-services.json"
SNAPSHOT_PATH = Path.home() / ".hermes" / "state" / "service-status.json"
STATE_PATH = Path.home() / ".hermes" / "state" / "local-services-state.json"
LOCK_PATH = Path.home() / ".hermes" / "state" / "local-services-check.lock"
SILENCE_PATH = Path.home() / ".hermes" / "logs" / "auto-remediate-state" / "silence-until.txt"

MANIFEST_MAX_BYTES = 64 * 1024
SNAPSHOT_MAX_BYTES = 2 * 1024 * 1024
FRESHNESS_SECONDS = 12 * 60      # 12 минут при 5-минутной коллекции
FUTURE_SKEW_SECONDS = 120        # допуск на расхождение часов
LOCK_STALE_SECONDS = 240         # старше — считаем crash-остатком и ломаем

SUPPORTED_SOURCES = ("systemd_user",)
SUPPORTED_EXPECTS = ("active",)
INCONCLUSIVE_ACTIVE = ("activating", "deactivating", "reloading", "maintenance", "unknown")
FAILED_ACTIVE = ("inactive", "failed")

# Маркер отсутствия user-systemd из продюсера (service-status-snapshot.py):
# schema-1 не доказывает полный обход юнитов, поэтому пустой/ошибочный источник
# — «неизвестно», а не «здорово».
USER_SYSTEMD_UNAVAILABLE = "(user systemd недоступен)"

TELEGRAM_TIMEOUT = 30
DOCS_URL = "https://github.com/upmeister/hermes-argus/blob/main/docs/local-services.md"


# ── Конфигурация модуля ──────────────────────────────────────────────────────

def config_env_paths() -> list[Path]:
    return [Path.home() / "hermes-argus" / "config.env",
            Path.home() / "hermes-vps-kit" / "config.env"]


def read_config_env() -> dict[str, str]:
    """MODULE_* значения из config.env (та же эвристика, что webhook.py)."""
    mods: dict[str, str] = {}
    for path in config_env_paths():
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("MODULE_") and "=" in line:
                    key, _, value = line.partition("=")
                    mods[key.strip()] = value.strip().strip('"').upper()
        except OSError:
            continue
        break
    return mods


def module_enabled() -> bool:
    """Canonical flag MODULE_LOCAL_SERVICES, default OFF even when unset.

    Env-переменная главнее config.env: deploy.sh экспортирует config.env, а
    cron-запуски видят только config.env. Значение проверяется при каждом
    запуске — забытая «ручная» cron-строка после ON→OFF становится no-op."""
    value = os.environ.get("MODULE_LOCAL_SERVICES")
    if value is None:
        value = read_config_env().get("MODULE_LOCAL_SERVICES", "OFF")
    return value.strip().strip('"').upper() == "ON"


# ── Манифест ожидаемых целей (operator-owned, deploy никогда не перезаписывает)

def load_manifest(path: Path | None = None) -> tuple[dict | None, str]:
    """Strict v1-валидация. (None, "") — манифест отсутствует или пуст
    (unconfigured onboarding), (None, reason) — configuration error."""
    path = MANIFEST_PATH if path is None else path
    if not path.exists():
        return None, ""
    try:
        if path.stat().st_size > MANIFEST_MAX_BYTES:
            return None, f"manifest exceeds {MANIFEST_MAX_BYTES} bytes"
        raw = path.read_text(encoding="utf-8", errors="strict")
    except OSError as exc:
        return None, f"manifest unreadable: {exc.__class__.__name__}"
    except UnicodeDecodeError:
        return None, "manifest is not valid UTF-8"
    if not raw.strip():
        return None, ""
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"manifest is not valid JSON: {exc.msg}"
    if not isinstance(manifest, dict):
        return None, "manifest is not an object"
    if manifest.get("schema") != SCHEMA or isinstance(manifest.get("schema"), bool):
        return None, f"unsupported manifest schema {manifest.get('schema')!r}"
    unknown_keys = sorted(set(manifest) - {"schema", "targets"})
    if unknown_keys:
        return None, f"unsupported manifest keys: {', '.join(unknown_keys)}"
    targets = manifest.get("targets")
    if not isinstance(targets, list):
        return None, "manifest targets must be a list"
    if not targets:
        return None, ""
    seen_ids: set[str] = set()
    seen_units: set[tuple[str, str]] = set()
    for index, target in enumerate(targets):
        reason = _validate_target(target, index, seen_ids, seen_units)
        if reason:
            return None, reason
    return manifest, ""


def _validate_target(target: object, index: int, seen_ids: set[str],
                     seen_units: set[tuple[str, str]]) -> str:
    if not isinstance(target, dict):
        return f"targets[{index}] is not an object"
    if set(target) != {"id", "label", "source", "name", "expect"}:
        return (f"targets[{index}] must contain exactly "
                "id, label, source, name, expect")
    tid = target["id"]
    if not isinstance(tid, str) or not tid.strip() or len(tid) > 64:
        return f"targets[{index}].id must be a non-empty string up to 64 chars"
    if any(ord(ch) < 32 for ch in tid):
        return f"targets[{index}].id contains control characters"
    if tid in seen_ids:
        return f"targets[{index}].id duplicates {tid!r}"
    seen_ids.add(tid)
    label = target["label"]
    if not isinstance(label, str) or not label.strip() or len(label) > 80:
        return f"targets[{index}].label must be a non-empty string up to 80 chars"
    if any(ord(ch) < 32 for ch in label):
        return f"targets[{index}].label contains control characters"
    if target["source"] not in SUPPORTED_SOURCES:
        return f"targets[{index}].source {target['source']!r} is not supported"
    name = target["name"]
    if not isinstance(name, str) or not _valid_service_name(name):
        return (f"targets[{index}].name {name!r} is not a plain .service unit name")
    if (target["source"], name) in seen_units:
        return f"targets[{index}] duplicates unit {name!r}"
    seen_units.add((target["source"], name))
    if target["expect"] not in SUPPORTED_EXPECTS:
        return f"targets[{index}].expect {target['expect']!r} is not supported"
    return ""


def _valid_service_name(name: str) -> bool:
    if not name.endswith(".service") or len(name) > 128:
        return False
    stem = name[: -len(".service")]
    if not stem or any(ord(ch) < 32 or ord(ch) == 127 for ch in stem):
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.@-\\")
    return all(ch in allowed for ch in stem)


# ── Снимок производителя ─────────────────────────────────────────────────────

def load_snapshot(path: Path | None = None, now: float | None = None
                  ) -> tuple[dict | None, str]:
    """Bounded read + строгая валидация schema-1. (None, reason) — unknown;
    reason описывает состояние для UI и диагностики, не для алерта."""
    now = time.time() if now is None else now
    path = SNAPSHOT_PATH if path is None else path
    try:
        size = path.stat().st_size
    except OSError:
        return None, "snapshot missing"
    if size > SNAPSHOT_MAX_BYTES:
        return None, f"snapshot exceeds {SNAPSHOT_MAX_BYTES} bytes"
    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
        snapshot = json.loads(raw)
    except OSError as exc:
        return None, f"snapshot unreadable: {exc.__class__.__name__}"
    except UnicodeDecodeError:
        return None, "snapshot is not valid UTF-8"
    except json.JSONDecodeError:
        return None, "snapshot is not valid JSON"
    if not isinstance(snapshot, dict):
        return None, "snapshot is not an object"
    if snapshot.get("schema") != SCHEMA or isinstance(snapshot.get("schema"), bool):
        return None, f"unsupported snapshot schema {snapshot.get('schema')!r}"
    generated_at = snapshot.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        return None, "snapshot generated_at missing"
    try:
        generated = datetime.fromisoformat(generated_at)
    except ValueError:
        return None, "snapshot generated_at is not an ISO timestamp"
    if generated.tzinfo is None:
        return None, "snapshot generated_at is not timezone-aware"
    age = now - generated.timestamp()
    if age < -FUTURE_SKEW_SECONDS:
        return None, "snapshot generated_at is in the future"
    if age > FRESHNESS_SECONDS:
        return None, f"snapshot is stale (age {int(age)}s)"
    services = snapshot.get("services")
    if not isinstance(services, dict) or not isinstance(services.get("user"), list):
        return None, "snapshot services.user is missing or malformed"
    for row in services["user"]:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) \
                or not isinstance(row.get("active"), str):
            return None, "snapshot services.user row is malformed"
    return snapshot, ""


def user_source_unavailable(snapshot: dict) -> bool:
    """Явный маркер продюсера: user-менеджер недоступен (cron-контекст без
    XDG_RUNTIME_DIR и т.п.). Схема-1 не отличает «юнита нет» от «источника
    нет» — оба случая остаются unknown, это только причина для UI."""
    return any(row.get("name") == USER_SYSTEMD_UNAVAILABLE
               for row in snapshot.get("services", {}).get("user", []))


def evaluate_target(target: dict, snapshot: dict) -> tuple[str, str]:
    """(verdict, observed) по одной цели. Вердикты строго из контракта."""
    name = target["name"]
    rows = snapshot.get("services", {}).get("user", [])
    if user_source_unavailable(snapshot):
        return "unknown", "source unavailable"
    row = next((r for r in rows if r.get("name") == name), None)
    if row is None:
        # Отсутствие строки в ином валидном снимке — подозрение на удалённый
        # юнит, но не подтверждённый not-found: unknown, никакого алерта.
        return "unknown", "unit missing from snapshot"
    observed = row.get("active", "unknown")
    if target.get("expect") == "active":
        if observed == "active":
            return "healthy", observed
        if observed in FAILED_ACTIVE:
            return "failed", observed
    return "unknown", observed


# ── Telegram delivery (тот же транспорт/прокси-политика, что у poller'а) ─────

def telegram_credentials() -> tuple[str, str, str]:
    token = os.environ.get("WATCHDOG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("WATCHDOG_CHAT_ID", "").strip()
    allowed = os.environ.get("WATCHDOG_ALLOWED_USER_ID", "").strip()
    return token, chat_id, allowed


def _telegram_http(token: str, payload: dict) -> dict:
    """Тот же транспорт, что у poller'а: smart-proxy по умолчанию (прямой
    api.telegram.org мёртв во время блокировок), таймаут 30с. Токен живёт
    только в URL процесса, не в argv."""
    proxy = os.environ.get("TELEGRAM_PROXY", "http://127.0.0.1:8444").strip()
    if proxy:
        os.environ["HTTPS_PROXY"] = proxy
        os.environ.pop("https_proxy", None)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TELEGRAM_TIMEOUT) as resp:
        return json.loads(resp.read())


def send_telegram(text: str) -> tuple[bool, str]:
    """Отправка в мониторинг-чат. (False, reason) — operational gap: отсутствие
    креденшелов/allowlist или недоставленный HTTP-запрос НИКОГДА не считается
    успешной нотификацией."""
    token, chat_id, allowed = telegram_credentials()
    if not allowed:
        return False, "WATCHDOG_ALLOWED_USER_ID is not set — local services fail closed"
    if not token or not chat_id:
        return False, "WATCHDOG_BOT_TOKEN/WATCHDOG_CHAT_ID are not configured"
    payload = {"chat_id": chat_id, "text": text, "disable_notification": False}
    try:
        response = _telegram_http(token, payload)
    except Exception as exc:
        return False, f"telegram send failed: {exc.__class__.__name__}"
    if not (isinstance(response, dict) and response.get("ok") is True):
        return False, "telegram API did not accept the message"
    return True, ""


def silence_active() -> bool:
    """Тот же mute-файл, что /silence в боте. Тишина глушит отправку, но не
    меняет state: после тишины следующий свежий failed-наблюдаемый снова
    алертит ровно один раз."""
    try:
        until = int(SILENCE_PATH.read_text(encoding="utf-8").strip())
        return until > int(time.time())
    except (OSError, ValueError):
        return False


# ── Состояние (module-owned, атомарная запись) ──────────────────────────────

def load_state() -> dict:
    try:
        if STATE_PATH.stat().st_size <= MANIFEST_MAX_BYTES:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(state, dict) and state.get("schema") == SCHEMA \
                    and isinstance(state.get("targets"), dict) \
                    and isinstance(state.get("blind"), dict):
                return state
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {"schema": SCHEMA, "targets": {}, "blind": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(STATE_PATH)


def _target_state(state: dict, tid: str) -> dict:
    return state["targets"].setdefault(
        tid, {"failed_ids": [], "alerted": False, "alert_attempts": 0})


# ── Обработка одного цикла ───────────────────────────────────────────────────

def process(manifest: dict, snapshot: dict, snapshot_reason: str, now: float,
            send=send_telegram, muted: bool | None = None) -> list[str]:
    """Один производственный цикл. Возвращает log-строки. Мутирует state.

    Идентичность наблюдения — generated_at снимка: тот же файл, прочитанный
    повторно, не второй провал. unknown сохраняет состояние как есть."""
    state = load_state()
    muted = silence_active() if muted is None else muted
    log: list[str] = []

    # Blind monitoring: только когда цели настроены. Две отдельные попытки
    # сбора подряд без свежего валидного снимка — один дедуплицированный
    # диагностика-эпизод; выход из слепоты — только по реальным новым данным.
    blind = state["blind"]
    if snapshot is None:
        blind["consecutive_unknown_runs"] = int(blind.get("consecutive_unknown_runs", 0)) + 1
        runs = blind["consecutive_unknown_runs"]
        if runs >= 2 and not blind.get("diag_sent"):
            text = (f"🖥 Локальные сервисы: наблюдение недоступно "
                    f"({snapshot_reason}); попыток подряд: {runs}. "
                    "Статусы целей неизвестны, сервисные алерты приостановлены.")
            if muted:
                log.append(f"blind diagnostic muted by silence (runs={runs})")
            else:
                ok, reason = send(text)
                if ok:
                    blind["diag_sent"] = True
                    log.append("blind diagnostic sent")
                else:
                    log.append(f"blind diagnostic not delivered: {reason}")
        for target in manifest["targets"]:
            log.append(f"{target['id']}: unknown ({snapshot_reason})")
        save_state(state)
        return log

    if blind.get("diag_sent"):
        text = ("🖥 Локальные сервисы: наблюдение восстановлено — "
                "получен свежий валидный снимок.")
        if muted:
            log.append("blind recovery muted by silence")
        else:
            ok, reason = send(text)
            log.append("blind recovery sent" if ok
                       else f"blind recovery not delivered: {reason}")
    blind["consecutive_unknown_runs"] = 0
    blind["diag_sent"] = False

    # Цели, исчезнувшие из манифеста, не живут в state вечно: живое состояние
    # только по текущим id, иначе алерт-память расходится с манифестом.
    live_ids = {t["id"] for t in manifest["targets"]}
    for stale_id in list(state["targets"]):
        if stale_id not in live_ids:
            del state["targets"][stale_id]

    generated_at = snapshot["generated_at"]
    age_min = max(int((now - _snapshot_epoch(generated_at)) // 60), 0)

    for target in manifest["targets"]:
        tid = target["id"]
        verdict, observed = evaluate_target(target, snapshot)
        tstate = _target_state(state, tid)
        tstate["last_verdict"] = verdict
        log.append(f"{tid}: {verdict} (systemd {observed})")
        if verdict == "failed":
            if generated_at not in tstate["failed_ids"]:
                tstate["failed_ids"] = (tstate["failed_ids"] + [generated_at])[-2:]
            if len(tstate["failed_ids"]) >= 2 and not tstate["alerted"]:
                unit = target["name"]
                text = (f"🖥 Локальные сервисы: ❌ {target['label']} ({unit}) — "
                        f"systemd {observed}, ожидался active. "
                        f"Снимок {age_min} мин назад. "
                        "Системный статус, не оценка приложения.")
                if muted:
                    log.append(f"{tid}: alert muted by silence")
                    continue
                ok, reason = send(text)
                tstate["alert_attempts"] = int(tstate.get("alert_attempts", 0)) + 1
                if ok:
                    tstate["alerted"] = True
                    log.append(f"{tid}: alert sent")
                else:
                    log.append(f"{tid}: alert not delivered: {reason}")
        elif verdict == "healthy":
            if tstate.get("alerted") and not muted:
                text = (f"🖥 Локальные сервисы: ✅ {target['label']} "
                        f"({target['name']}) — systemd active. "
                        f"Снимок {age_min} мин назад.")
                ok, reason = send(text)
                log.append(f"{tid}: recovery sent" if ok
                           else f"{tid}: recovery not delivered: {reason}")
            # Тишина глушит доставку, но не «восстановление»: если алерт был
            # активен, состояние храним и доставим одно восстановление после
            # тишины (real fresh evidence уже есть — снимок healthy).
            if not (tstate.get("alerted") and muted):
                tstate["failed_ids"] = []
                tstate["alerted"] = False
                tstate["alert_attempts"] = 0
        # unknown: состояние не трогаем — никогда не сбрасывает и не усиливает.
    save_state(state)
    return log


def _snapshot_epoch(generated_at: str) -> float:
    return datetime.fromisoformat(generated_at).timestamp()


# ── Одиночный инстанс (перекрытие cron-запусков не должно дублировать) ──────

class _Lock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def __enter__(self):
        try:
            if self.path.exists():
                age = time.time() - self.path.stat().st_mtime
                if age > LOCK_STALE_SECONDS:
                    self.path.unlink(missing_ok=True)
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode())
            return True
        except FileExistsError:
            return False
        except OSError:
            self.fd = None
            return True  # не можем залочить — не блокируем мониторинг

    def __exit__(self, *exc):
        if self.fd is not None:
            try:
                os.close(self.fd)
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def main(argv: list[str] | None = None) -> int:
    if not module_enabled():
        print("local_services_check: MODULE_LOCAL_SERVICES is OFF — no-op",
              file=sys.stderr)
        return 0
    manifest, manifest_reason = load_manifest()
    if manifest is None:
        if manifest_reason:
            print(f"local_services_check: manifest configuration error: "
                  f"{manifest_reason}", file=sys.stderr)
            return 2
        print("local_services_check: manifest absent/empty — unconfigured",
              file=sys.stderr)
        return 0
    now = time.time()
    snapshot, snapshot_reason = load_snapshot(now=now)
    with _Lock(LOCK_PATH) as acquired:
        if not acquired:
            print("local_services_check: previous run still active — skipped",
                  file=sys.stderr)
            return 0
        for line in process(manifest, snapshot, snapshot_reason, now):
            print(f"local_services_check: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
