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


def extract_entities():
    cfg = load_yaml(CONFIG)
    env = env_names(ENV_FILE)
    entities = {}

    for name, p in (cfg.get("providers") or {}).items():
        if isinstance(p, dict) and p.get("key_env"):
            entities[f"provider:{name}"] = {
                "type": "provider", "name": name, "key_env": p["key_env"],
                "key_present": env.get(p["key_env"], False),
                "base_url": p.get("base_url", "")}

    for i, p in enumerate(cfg.get("custom_providers") or []):
        if isinstance(p, dict) and p.get("key_env"):
            nm = p.get("name") or p.get("base_url") or f"legacy-{i}"
            entities[f"provider:{nm}"] = {
                "type": "provider", "name": str(nm), "key_env": p["key_env"],
                "key_present": env.get(p["key_env"], False),
                "base_url": p.get("base_url", "")}

    for name, s in (cfg.get("mcp_servers") or {}).items():
        if isinstance(s, dict):
            url = s.get("url", "")
            entities[f"mcp:{name}"] = {
                "type": "mcp", "name": name,
                "transport": "http" if url else "stdio",
                "url": url if url else s.get("command", "")}

    try:
        for m in re.finditer(r"\$\{([A-Z_0-9]+)\}", CONFIG.read_text()):
            v = m.group(1)
            entities[f"envref:{v}"] = {"type": "envref", "name": v,
                                       "key_present": env.get(v, False)}
    except FileNotFoundError:
        pass
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
    events = diff_entities(old_snap.get("entities", {}) if old_snap else {}, entities)

    tmp = SNAPSHOT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    tmp.replace(SNAPSHOT)

    report = {"updated": snap["updated"], "total_entities": len(entities),
              "total_env_keys": len(env), "events": events}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    out = os.environ.get("DISCOVER_REPORT", "")
    if out:
        Path(out).write_text(text)
    print(text)
    sys.exit(2 if events else 0)


if __name__ == "__main__":
    main()
