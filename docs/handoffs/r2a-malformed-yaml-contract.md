# R2a contract — fail-safe malformed YAML discovery

Status: **READY FOR IMPLEMENTATION**

## Problem

The authoritative static `scripts/integration-discover.py` can fail ungracefully on malformed `config.yaml`. C0/C1a demonstrated that this is a real product gap: malformed configuration should become structured degradation, not crash discovery or leave stale state looking current.

## Owner

Primary owner: `scripts/integration-discover.py`.

Adjacent paths allowed only when required to preserve current wrapper/report behavior:

- `scripts/integration-discover-wrapper.sh`
- `tests/probes.py`

## Required behavior

When `config.yaml` is malformed or not parseable as the expected mapping:

1. discovery must not traceback to the operator;
2. it must not silently treat malformed config as an empty healthy config;
3. it must produce an explicit degraded/partial observation using the existing snapshot/report vocabulary where possible;
4. previous-good discovery state must not be presented as freshly authoritative without a stale/degraded marker;
5. static sources that remain independently readable may still be reported, provided provenance/degradation makes the config failure visible.

Prefer the smallest behavior that fits the existing schema. Do not introduce a new schema version solely for this bug.

## Evidence semantics

The implementation must distinguish at least:

```text
config parsed normally
config file missing (existing semantics)
config present but malformed / wrong top-level shape
```

Malformed config is not equivalent to “no integrations configured.”

## Acceptance criteria

- fixture: valid YAML preserves current output semantics;
- fixture: syntactically malformed YAML exits through the normal discovery path without traceback and records degradation;
- fixture: valid YAML with an unexpected top-level type fails safe rather than being treated as healthy empty config;
- no Hermes imports or subprocess bridge;
- no network/process/token-refresh side effects;
- existing added/removed/changed alert semantics remain unchanged for valid config;
- `argus-ci` green.

## Non-goals

- canonical Hermes config normalization;
- repairing/reformatting user YAML;
- importing `hermes_cli.config`;
- C1/C1a bridge revival;
- generalized config validation framework;
- multi-profile fan-out;
- expanding provider/auxiliary discovery in the same patch.

## Stop condition

If a clean fix appears to require schema redesign, runtime Hermes imports, or broad changes to wrapper alert logic, stop and return the concrete incompatibility to the maintainer.
