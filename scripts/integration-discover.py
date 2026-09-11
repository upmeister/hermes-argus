#!/usr/bin/env python3
"""integration-discover.py — extract+diff сущностей интеграций Hermes.

Читает config.yaml (providers.key_env, custom_providers, mcp_servers, ${VAR})
и имена ключей .env (НЕ значения) → снимок JSON. Diff с прошлым снимком →
события added/removed/changed. exit 0 = тишина, 2 = есть события.
"""
import json, os, re, sys, hashlib
from datetime import datetime, timezone
from pathlib import Path

HERMES_DIR = Path(os.environ.get("HERMES_DIR", Path.home() / ".hermes"))
CONFIG = HERMES_DIR / "config.yaml"
ENV_FILE = HERMES_DIR / ".env"
STATE_DIR = HERMES_DIR / "state"
SNAPSHOT = STATE_DIR / "integration-snapshot.json"
REGISTRY = STATE_DIR / "registry.yaml"
AUTH_JSON = HERMES_DIR / "auth.json"

# OAuth provider flows stored in auth.json providers.<flow> (hermes_cli/auth.py).
# Detection is STATIC (field names / expiry only) — never call `hermes auth
# status`: it rotates refresh tokens as a side effect (research 2026-09-07).
OAUTH_FLOWS = ("nous", "openai-codex", "xai-oauth", "qwen-oauth", "minimax-oauth")


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
    except FileNotFoundError:
        return {}


def env_names(path):
    out = {}
    try:
        for line in path.read_text().splitlines():
            m = re.match(r"^([A-Z_0-9]+)=", line)
            if m:
                out[m.group(1)] = bool(line.split("=", 1)[1].strip())
    except FileNotFoundError:
        pass
    return out


def sanitize_url(url: str) -> str:
    """Strip userinfo and redact credential-looking query params: URL-embedded
    secrets (user:pass@host, ?token=...) must not reach snapshot/stdout
    (probe discover_url_secret_leak)."""
    u = re.sub(r"//[^/\s@]+@", "//<redacted>@<redacted-host>", url or "")
    u = re.sub(r"([?&](?:token|key|api_key|secret|password)=[^&\s]*)",
               r"<redacted>", u, flags=re.IGNORECASE)
    return u


def extract_entities():
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

    # ── Discover v2, layer 4: OAuth / web-token providers ───────────────────
    # Tokens live in auth.json providers.<flow> (nous portal, codex, xai/qwen/
    # minimax oauth) and .env (Copilot). Status is expiry-only — token values
    # are never read or emitted. Copilot nuance: classic GitHub PATs are
    # REJECTED by copilot (validate_copilot_token) — the real OAuth token lands
    # in .env as COPILOT_GITHUB_TOKEN via the device flow.
    try:
        auth = json.loads(AUTH_JSON.read_text()) if AUTH_JSON.exists() else {}
    except (json.JSONDecodeError, OSError):
        auth = {}
    auth_provs = auth.get("providers") or {}
    for flow in OAUTH_FLOWS:
        p = auth_provs.get(flow)
        if isinstance(p, dict) and p.get("access_token"):
            # expires_at is deliberately NOT stored: auth.json rotates on every
            # refresh — a stored expiry produced "changed: oauth nous" noise
            # (Vlad, 2026-09-07).
            entities[f"oauth:{flow}"] = {
                "type": "oauth", "name": flow,
                "active": auth.get("active_provider") == flow}
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
            meta = load_yaml(yml) or {}
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
            entities[f"local:{key}"] = {"type": "local", "name": key, "url": val}

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


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entities, env = extract_entities()
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

    snap = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "config_hash": hashlib.sha256(CONFIG.read_bytes()).hexdigest()[:12] if CONFIG.exists() else "",
        "entities": entities,
        "env_keys": sorted(env.keys()),
    }
    events = [] if baseline else diff_entities(old_snap.get("entities", {}) if old_snap else {}, entities)

    tmp = SNAPSHOT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    tmp.replace(SNAPSHOT)

    report = {"updated": snap["updated"], "total_entities": len(entities),
              "total_env_keys": len(env), "baseline": baseline, "events": events}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    out = os.environ.get("DISCOVER_REPORT", "")
    if out:
        Path(out).write_text(text)
    print(text)
    sys.exit(2 if events else 0)


if __name__ == "__main__":
    main()
