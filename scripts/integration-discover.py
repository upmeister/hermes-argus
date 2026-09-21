#!/usr/bin/env python3
"""integration-discover.py — extract+diff сущностей интеграций Hermes.

Читает config.yaml (providers.key_env, custom_providers, mcp_servers, ${VAR})
и имена ключей .env (НЕ значения) → снимок JSON. Diff с прошлым снимком →
события added/removed/changed. exit 0 = тишина, 2 = есть события.

R2a: malformed/wrong-shape config.yaml — не крах и не «пустой валидный конфиг».
Снапшот несёт конверт discovery (status ok|degraded, reason_code, attempted_at,
last_good_at); при деградации инвентаризация last-good замораживается как есть
(никаких ложных removed/changed), свежесть updated не переписывается. Первый
переход ok→degraded и восстановление degraded→ok — отчётные события (exit 2),
повтор идентичной деградации — тихий (exit 0). Сырой текст ошибки парсера в
вывод не попадает: в config.yaml могут быть секреты.
"""
import json, os, re, sys, hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from datetime import datetime, timezone
from pathlib import Path

HERMES_DIR = Path(os.environ.get("HERMES_DIR", Path.home() / ".hermes"))
CONFIG = HERMES_DIR / "config.yaml"
ENV_FILE = HERMES_DIR / ".env"
STATE_DIR = HERMES_DIR / "state"
SNAPSHOT = STATE_DIR / "integration-snapshot.json"
REGISTRY = STATE_DIR / "registry.yaml"
AUTH_JSON = HERMES_DIR / "auth.json"

# ── OA1: структурные свидетельства account-auth из auth.json (только static) ──
# Детект — статическая структура, никаких вызовов `hermes auth status`: он
# ротирует refresh-токены как сайд-эффект (research 2026-09-07). OA1-дискавери
# генерик (без ростера провайдеров): providers.<id> — свидетельство account/
# OAuth, когда несёт refresh_token (flat; формы nous/minimax) или вложенный
# блок tokens.{access_token,refresh_token} (формы Codex/xAI);
# credential_pool.<id>[] — строки с persisted auth_type "oauth" (или legacy
# строки без auth_type, но с refresh_token). Голый access_token сам по себе —
# НЕ свидетельство: blob в форме access_token может быть API-key креденшалом
# (таксономия OA0). Явные auth_type "api_key" строки — вне OA1. Значения
# никогда не попадают в вывод; наличие свидетельства — НЕ login/health
# (health-check-v2 проецирует oauth-сущности в skipped).

def _nonempty_credential(value) -> bool:
    """Учётное поле креденшала — только непустая строка (значение не используется)."""
    return isinstance(value, str) and bool(value.strip())


def _provider_state_is_account_auth(state) -> bool:
    if not isinstance(state, dict):
        return False
    if _nonempty_credential(state.get("refresh_token")):
        return True
    tokens = state.get("tokens")
    # Форма Codex/xAI: рантайм требует ОБЕ части токен-пары, поэтому неполный
    # блок tokens (только access_token или только refresh_token) — не
    # свидетельство.
    return isinstance(tokens, dict) and (
        _nonempty_credential(tokens.get("access_token"))
        and _nonempty_credential(tokens.get("refresh_token")))


def _pool_rows_are_account_auth(rows) -> bool:
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if "auth_type" in row:
            # Сильное свидетельство — только строковый "oauth". Любое другое
            # ПРИСУТСТВУЮЩЕЕ значение (api_key, неизвестное, null/""/не-строка)
            # — вне OA1: weak-fallback разрешён лишь при физическом отсутствии
            # ключа (contract §4.2), null/""/False — malformed, не "отсутствие".
            auth_type = row.get("auth_type")
            if isinstance(auth_type, str) and auth_type.strip().lower() == "oauth":
                return True
            continue
        # Legacy-строка: ключа auth_type нет, но есть refresh_token.
        if _nonempty_credential(row.get("refresh_token")):
            return True
    return False


def _account_auth_ids(auth) -> list:
    """Отсортированные id провайдеров с persisted account/OAuth
    свидетельствами. Тот же id в providers и credential_pool даёт одну
    идентичность; битые секции/строки игнорируются (не роняют дискавери)."""
    if not isinstance(auth, dict):
        return []
    ids = set()
    providers = auth.get("providers")
    if isinstance(providers, dict):
        ids.update(str(pid) for pid, state in providers.items()
                   if _provider_state_is_account_auth(state))
    pool = auth.get("credential_pool")
    if isinstance(pool, dict):
        ids.update(str(pid) for pid, rows in pool.items()
                   if _pool_rows_are_account_auth(rows))
    return sorted(ids)


def load_registry():
    """registry.yaml (deployed by INTEGRATIONS module) — source of known keys.
    Missing registry only disables layer 2 (envkey entities)."""
    try:
        import yaml
        return yaml.safe_load(REGISTRY.read_text()) or {}
    except Exception:
        return {}


def load_yaml(path):
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError):
        # YAMLError (R2a): community plugin.yaml с битым YAML не должен ронять
        # весь дискавери — пропускается как непрочитанный источник. Авторитетный
        # config.yaml идёт через load_config(), где деградация — явная.
        return {}


# Стабильные reason_code деградации config.yaml (R2a). Вывод сырого исключения
# парсера запрещён — в config.yaml могут быть секреты.
DISC_REASON_SYNTAX = "config_yaml_syntax"
DISC_REASON_SHAPE = "config_yaml_shape"
DISC_REASON_UNREADABLE = "config_unreadable"


def load_config():
    """Авторитетный config.yaml → (cfg, status, reason_code).

    status "ok": cfg — словарь; отсутствие файла сохраняет существующую
    семантику ({} как «нет конфига»). status "degraded": файл есть, но не
    парсится или верхний уровень не словарь — cfg {} и стабильный reason_code.
    Деградация НИКОГДА не маппится в валидный пустой конфиг (R2a): это создало
    бы ложную массу removed-событий."""
    if not CONFIG.exists():
        return {}, "ok", ""
    try:
        import yaml
        with open(CONFIG, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        return {}, "ok", ""
    except yaml.YAMLError:
        return {}, "degraded", DISC_REASON_SYNTAX
    except UnicodeError:
        # Битая кодировка (Pytna R2a-1 Finding 1): файл есть, но не читается
        # как UTF-8 — деградация, не traceback.
        return {}, "degraded", DISC_REASON_UNREADABLE
    except OSError:
        return {}, "degraded", DISC_REASON_UNREADABLE
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return {}, "degraded", DISC_REASON_SHAPE
    return data, "ok", ""


def env_names(path):
    out = {}
    try:
        for line in path.read_text().splitlines():
            m = re.match(r"^([A-Z_0-9]+)=", line)
            if m:
                value = line.split("=", 1)[1].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                out[m.group(1)] = bool(value)
    except FileNotFoundError:
        pass
    return out


_SECRET_QUERY_NAMES = re.compile(
    r"^(?:token|key|api[-_]?key|secret|password|passwd|auth|authorization|"
    r"credential|signature|sig|access[-_]?token|client[-_]?secret)$",
    re.IGNORECASE,
)


def _sanitize_unparsed_url(value: str) -> str:
    """Best-effort redaction for values that are not absolute URLs."""
    value = re.sub(
        r"(?i)(?P<prefix>(?:\?|&)\s*(?:token|key|api[-_]?key|secret|password|"
        r"passwd|auth|authorization|credential|signature|sig|access[-_]?token|"
        r"client[-_]?secret)\s*=)[^&\s]*",
        r"\g<prefix><redacted>",
        value,
    )
    # Commands and other non-URL strings may still contain URL userinfo.
    return re.sub(r"(?P<scheme>://)(?:[^/@\s]+@)(?P<host>[^/\s]+)",
                  r"\g<scheme>\g<host>", value)


def sanitize_url(url: str) -> str:
    """Return a valid URL with userinfo removed and query secrets redacted."""
    value = str(url or "")
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return _sanitize_unparsed_url(value)

        # Rebuild netloc from hostname/port so username and password cannot
        # survive. Accessing .port also validates malformed port values.
        hostname = parts.hostname
        if not hostname:
            return _sanitize_unparsed_url(value)
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = parts.port
        netloc = hostname if port is None else f"{hostname}:{port}"

        query = []
        for name, item in parse_qsl(parts.query, keep_blank_values=True):
            query.append((name, "<redacted>" if _SECRET_QUERY_NAMES.fullmatch(name) else item))
        return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), parts.fragment))
    except (TypeError, ValueError):
        return _sanitize_unparsed_url(value)


def extract_entities(cfg=None):
    # cfg=None: legacy in-process callers (probes) читают CONFIG сами;
    # main() всегда передаёт уже разобранный load_config() результат.
    if cfg is None:
        cfg = load_yaml(CONFIG)
    env = env_names(ENV_FILE)
    entities = {}

    # providers: key_env (runtime key) OR inline api_key (presence only, never
    # stored); base_url falls back to the `api` field (live example:
    # opencode-go-safety keeps its endpoint in `api`, not `base_url`)
    for name, p in (cfg.get("providers") or {}).items():
        if isinstance(p, dict) and (p.get("key_env") or p.get("api_key")):
            key_env = p.get("key_env") or ""
            key_present = bool(p.get("api_key")) or env.get(key_env, False)
            entities[f"provider:{name}"] = {
                "type": "provider", "name": name, "key_env": key_env,
                "key_present": key_present,
                "base_url": sanitize_url(p.get("base_url") or p.get("api") or "")}

    for i, p in enumerate(cfg.get("custom_providers") or []):
        if isinstance(p, dict) and (p.get("key_env") or p.get("api_key")):
            nm = sanitize_url(str(p.get("name") or p.get("base_url") or f"legacy-{i}"))
            key_env = p.get("key_env") or ""
            key_present = bool(p.get("api_key")) or env.get(key_env, False)
            entities[f"provider:{nm}"] = {
                "type": "provider", "name": str(nm), "key_env": key_env,
                "key_present": key_present,
                "base_url": sanitize_url(p.get("base_url") or p.get("api") or "")}

    for name, s in (cfg.get("mcp_servers") or {}).items():
        if isinstance(s, dict):
            url = s.get("url", "")
            entities[f"mcp:{name}"] = {
                "type": "mcp", "name": name,
                "transport": "http" if url else "stdio",
                "url": sanitize_url(url if url else s.get("command", ""))}

    try:
        for m in re.finditer(r"\$\{([A-Z_0-9]+)\}", CONFIG.read_text()):
            v = m.group(1)
            entities[f"envref:{v}"] = {"type": "envref", "name": v,
                                       "key_present": env.get(v, False)}
    except FileNotFoundError:
        pass

    # ── Discover v2, layer 2: registry-driven env keys ──────────────────────
    # Any registry key set in .env = a configured integration (tools, messaging,
    # built-in AI providers...). Excluded: kit keys (the engine checks those via
    # kit_entries) and keys already represented above (provider key_env / envref)
    # — otherwise the same key would be reported twice.
    reg = load_registry()
    kit_keys = {k.get("key") for k in reg.get("kit_entries", []) if isinstance(k, dict)}
    covered = set()
    for e in entities.values():
        if e.get("key_env"):
            covered.add(e["key_env"])
        if e.get("name") and e.get("type") == "envref":
            covered.add(e["name"])
    for e in reg.get("entries", []):
        k = e.get("key", "")
        if not k or k in kit_keys or k in covered:
            continue
        if env.get(k, False):
            entities[f"envkey:{k}"] = {
                "type": "envkey", "name": k,
                "category": e.get("category", "setting"),
                "free": e.get("free", False),
                "description": e.get("description", ""),
                "check_url": e.get("check_url", ""),
                "check_auth": e.get("check_auth", ""),
                "check_mode": e.get("check_mode", "")}

    # ── Discover v2, layer 3: active model references ───────────────────────
    # What is ACTUALLY used (deep-check target): model/fallback_model/auxiliary.
    # The primary model lives in model.default (not model.model).
    def model_ref(eid, role, section, use_default_key=False):
        if isinstance(section, dict):
            model = section.get("default", "") if use_default_key else section.get("model", "")
            if model:
                entities[eid] = {
                    "type": "activemodel", "role": role,
                    "provider": section.get("provider", ""),
                    "model": model,
                    "key_env": section.get("key_env", "")}

    model_ref("model:primary", "primary", cfg.get("model") or {}, use_default_key=True)
    model_ref("model:fallback", "fallback", cfg.get("fallback_model") or {})
    aux = cfg.get("auxiliary") or {}
    if isinstance(aux, dict):
        for role in ("vision", "compression"):
            model_ref(f"model:{role}", role, aux.get(role) or {})

    # ── Discover v2, layer 4: account-auth evidence (OA1, static) ───────────
    # Генерик-чтение auth.json без ростера (хелперы OA1 выше): identity = ключ
    # стора, один entity на id даже при свидетельствах в обеих секциях, без
    # provenance-поля — переезд идентичности между singleton и pool не должен
    # создавать changed-шум. Copilot нюанс: classic GitHub PAT отвергается
    # copilot (validate_copilot_token) — настоящий OAuth-токен попадает в .env
    # как COPILOT_GITHUB_TOKEN через device flow.
    try:
        auth = json.loads(AUTH_JSON.read_text()) if AUTH_JSON.exists() else {}
    except (json.JSONDecodeError, OSError):
        auth = {}
    for pid in _account_auth_ids(auth):
        # expires_at сознательно НЕ сохраняем: auth.json ротируется при каждом
        # refresh — сохранённый expiry давал шум "changed: oauth nous"
        # (Vlad, 2026-09-07).
        entities[f"oauth:{pid}"] = {
            "type": "oauth", "name": pid,
            "active": auth.get("active_provider") == pid}
    if env.get("COPILOT_GITHUB_TOKEN", False):
        entities["oauth:copilot"] = {"type": "oauth", "name": "copilot",
                                     "active": False}
    elif env.get("GH_TOKEN", False) or env.get("GITHUB_TOKEN", False):
        # A plain PAT cannot drive Copilot — surface as misconfigured
        entities["oauth:copilot"] = {"type": "oauth", "name": "copilot",
                                     "active": False, "status": "pat-only"}

    # ── Discover v2, layer 5: community model-provider plugins ──────────────
    # plugins/model-providers/<name>/plugin.yaml is static metadata (name,
    # description); runtime registration lives in the plugin __init__.py.
    # Live example: clinepass (Vlad 2026-09-07 — was invisible to /integrations).
    plugins_dir = HERMES_DIR / "plugins" / "model-providers"
    if plugins_dir.is_dir():
        for d in sorted(plugins_dir.iterdir()):
            yml = d / "plugin.yaml"
            if not yml.is_file():
                continue
            # R2a.1: community metadata никогда не роняет дискавери —
            # нечитаемый/битый/не-словарный plugin.yaml пропускает плагин;
            # валидный mapping сохраняет прежнюю семантику. Отдельное чтение
            # с guard'ом: load_yaml() не отличает «битый YAML» от «пустого
            # mapping», а skip требуется именно для битого.
            try:
                import yaml
                meta = yaml.safe_load(yml.read_text(encoding="utf-8"))
            except (yaml.YAMLError, UnicodeError, OSError):
                continue
            if not isinstance(meta, dict):
                continue
            name = str(meta.get("name") or d.name)
            entities[f"plugin-provider:{name}"] = {
                "type": "plugin-provider", "name": name,
                "description": str(meta.get("description", ""))[:140]}

    # Literal URL-ключи (self-hosted: SearXNG, LM Studio, Ollama, Honcho self...).
    # Hermes знает их как OPTIONAL_ENV_VARS; юзер пишет значение прямо в config.yaml
    # (НЕ ${VAR}) — потому отдельный extract-канал (урок 2026-09-06: диспетчер
    # молчал на SearXNG, пока не добавили этот канал).
    KNOWN_URL_KEYS = (
        "SEARXNG_URL", "SEARXNG_BASE_URL", "HONCHO_BASE_URL", "OLLAMA_BASE_URL",
        "LM_BASE_URL", "LMSTUDIO_BASE_URL", "FIRECRAWL_API_URL", "CAMOFOX_URL",
    )
    for key in KNOWN_URL_KEYS:
        val = cfg.get(key)
        if isinstance(val, str) and val.startswith("http"):
            entities[f"local:{key}"] = {
                "type": "local", "name": key, "url": sanitize_url(val)}

    return entities, env


def diff_entities(old, new):
    events = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            events.append({"event": "added", "key": k, "entity": new[k]})
        elif k not in new:
            events.append({"event": "removed", "key": k, "entity": old[k]})
        elif old[k] != new[k]:
            events.append({"event": "changed", "key": k, "old": old[k], "entity": new[k]})
    return events


def _discovery_entity(status: str, reason_code: str) -> dict:
    return {"type": "discovery", "name": "discovery",
            "status": status, "reason_code": reason_code}


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # --baseline: write the snapshot WITHOUT diff/alerts. Used after discover
    # upgrades that add whole new entity layers (lesson 2026-09-06: a first run
    # without baseline produced a 181-alert storm for the fallback tracker).
    baseline = "--baseline" in sys.argv

    old_snap = None
    if SNAPSHOT.exists():
        try:
            old_snap = json.loads(SNAPSHOT.read_text())
        except Exception:
            old_snap = None

    # Legacy pre-R2a snapshots carry no discovery envelope; they were
    # successful runs and count as "ok" for transition semantics.
    prev_disc = (old_snap or {}).get("discovery")
    if not isinstance(prev_disc, dict):
        prev_disc = {}
    prev_status = prev_disc.get("status", "ok")
    if prev_status not in ("ok", "degraded"):
        prev_status = "ok"

    cfg, disc_status, disc_reason = load_config()
    now = datetime.now(timezone.utc).isoformat()
    events = []

    if disc_status == "ok":
        entities, env = extract_entities(cfg)
        env_keys = sorted(env.keys())
        updated = now
        config_hash = hashlib.sha256(CONFIG.read_bytes()).hexdigest()[:12] \
            if CONFIG.exists() else ""
        disc_env = {"status": "ok", "reason_code": "",
                    "attempted_at": now, "last_good_at": now}
        if not baseline:
            events = diff_entities(
                old_snap.get("entities", {}) if old_snap else {}, entities)
        if prev_status == "degraded":
            # Восстановление всегда отчётное — даже при пустом diff сущностей
            # и даже в --baseline-прогоне: baseline глушит entity-diff, но не
            # обязательный degraded→ok переход (Pytna R2a-1 Finding 2).
            # Инвентаризация сравнивается с last-good: замороженные на время
            # деградации entities и есть last-good, поэтому «буря remove/add»
            # из-за malformed-интервала невозможна.
            events.insert(0, {
                "event": "discovery_recovered", "key": "discovery",
                "entity": _discovery_entity("ok", "")})
    else:
        # Деградация: last-good инвентаризация замораживается дословно.
        # updated/config_hash/entities/env_keys остаются last-good — stale
        # состояние НЕ выглядит свежим, потому что конверт discovery помечает
        # его degraded и attempted_at != updated.
        if old_snap is not None:
            entities = old_snap.get("entities") or {}
            env_keys = old_snap.get("env_keys") or []
            updated = old_snap.get("updated") or ""
            config_hash = old_snap.get("config_hash") or ""
        else:
            entities, env_keys, updated, config_hash = {}, [], "", ""
        last_good_at = prev_disc.get("last_good_at") or \
            (old_snap.get("updated") if old_snap else None)
        disc_env = {"status": "degraded", "reason_code": disc_reason,
                    "attempted_at": now, "last_good_at": last_good_at or None}
        # Первый переход ok→degraded отчётный даже в --baseline-прогоне:
        # baseline глушит ТОЛЬКО entity-diff (R2a baseline follow-up).
        # Повтор идентичной деградации тихий (без cron-спама); смена
        # reason_code — отчётная.
        if prev_status != "degraded" or \
                prev_disc.get("reason_code") != disc_reason:
            events.append({
                "event": "discovery_degraded", "key": "discovery",
                "entity": _discovery_entity("degraded", disc_reason)})

    snap = {
        "updated": updated,
        "config_hash": config_hash,
        "entities": entities,
        "env_keys": env_keys,
        "discovery": disc_env,
    }

    tmp = SNAPSHOT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    tmp.replace(SNAPSHOT)

    report = {"updated": snap["updated"], "total_entities": len(entities),
              "total_env_keys": len(env_keys), "baseline": baseline,
              "events": events, "discovery": snap["discovery"]}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    out = os.environ.get("DISCOVER_REPORT", "")
    if out:
        Path(out).write_text(text)
    print(text)
    sys.exit(2 if events else 0)


if __name__ == "__main__":
    main()
