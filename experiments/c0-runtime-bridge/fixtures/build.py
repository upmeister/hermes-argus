"""build.py — synthetic fixture Hermes homes for the C0 adversarial matrix.

All data is synthetic; canaries are dummy markers only (contract section 7:
"no production credential or live endpoint is required by tests"). Builders
return the fixture-home path and never touch anything outside `root`.
"""
from __future__ import annotations

from pathlib import Path

CANARY_SECRET = "C0_DUMMY_CANARY_SECRET"
CANARY_ENV_VAR = "C0_CANARY_ENV"
CANARY_ENV_VALUE = "c0-declared-env-value"

PROFILE_A_YAML = 'model:\n  default: "alpha-provider/model-a"\n'
PROFILE_B_YAML = 'model:\n  default: "beta-provider/model-b"\n'
PROFILE_ENVREF_YAML = 'model:\n  default: "${C0_CANARY_ENV}"\n'
MALFORMED_YAML = 'model:\n  default: "broken\n'

FULL_EFFECTIVE_YAML = (
    'model:\n'
    '  default: "alpha-provider/model-a"\n'
    'fallback_providers:\n'
    '  - "beta-provider"\n'
    'providers:\n'
    '  alpha:\n'
    '    base_url: "https://alpha.invalid/v1"\n'
    '    key_env: "ALPHA_API_KEY"\n'
    '  inline:\n'
    '    base_url: "https://inline.invalid/v1"\n'
    '    api_key: "C0_DUMMY_INLINE_KEY"\n'
    'mcp_servers:\n'
    '  time:\n'
    '    command: "uvx"\n'
    '    args: ["mcp-server-time"]\n'
    '  notion:\n'
    '    url: "https://mcp.notion.invalid/mcp?token=C0_DUMMY_QUERY_TOKEN"\n'
    'auxiliary:\n'
    '  title_generation:\n'
    '    model: "${C0_AUX_MODEL_VAR}"\n'
)


def _home(root: Path, name: str, config_yaml: str | None,
          env_text: str | None) -> Path:
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    if config_yaml is not None:
        (home / "config.yaml").write_text(config_yaml, encoding="utf-8",
                                          newline="\n")
    if env_text is not None:
        (home / ".env").write_text(env_text, encoding="utf-8", newline="\n")
    return home


def profile_a(root: Path) -> Path:
    """Profile A with a canary secret in .env (never loaded in metadata mode)."""
    return _home(root, "profile-a", PROFILE_A_YAML,
                 f"ALPHA_API_KEY={CANARY_SECRET}\n")


def profile_b(root: Path) -> Path:
    """Profile B conflicting with profile A."""
    return _home(root, "profile-b", PROFILE_B_YAML, None)


def profile_envref(root: Path) -> Path:
    """Config referencing ${C0_CANARY_ENV} on the allowlisted primary-model
    path; the variable itself comes from the allowlisted child environment,
    never from a secret store."""
    return _home(root, "profile-envref", PROFILE_ENVREF_YAML, None)


def profile_full_effective(root: Path) -> Path:
    """Rich allowlist fixture: primary/fallback models, named providers
    (key_env + inline api_key), stdio and http MCP servers (the http URL
    carries a dummy query token), an auxiliary model as a ${VAR} template,
    and a canary .env that metadata mode never loads."""
    return _home(root, "profile-full", FULL_EFFECTIVE_YAML,
                 f"ALPHA_API_KEY={CANARY_SECRET}\n")


def profile_malformed(root: Path) -> Path:
    """Broken config.yaml (unterminated quote -> YAML parse error)."""
    return _home(root, "profile-malformed", MALFORMED_YAML, None)
