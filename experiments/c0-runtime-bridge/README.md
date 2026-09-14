# C0 runtime bridge experiment

Bounded experiment for the C0 gate: what is the maximum useful slice of
Hermes-owned runtime truth that Argus can obtain through a short-lived Hermes
subprocess without violating Argus regular-tier side-effect policy, leaking
secrets, or creating a second Hermes runtime?

Frozen contract: `docs/experiments/c0-runtime-bridge-contract.md`.
Handoff: `docs/handoffs/c0-runtime-bridge-zcode.md`.

This code is an experiment: it must never be wired into `deploy.sh`, cron,
systemd or normal Argus health/discovery execution, and it is deliberately
not part of `tests/probes.py` or `argus-ci`.

## Layout

```text
experiments/c0-runtime-bridge/
  harness.py    parent-side containment: env allowlist, explicit HERMES_HOME,
                timeout/kill/reap, stdout/stderr byte caps, fail-closed
                envelope parsing, canary leak scan
  bridge.py     child-side entrypoint: facet registry + allowlisted envelope
                emission (no Hermes import yet — step 1)
  probes.py     containment probes with synthetic fake children
  fixtures/     Hermes fixture homes and plugin sentinels (steps 2–5)
```

## Run

```bash
python3 experiments/c0-runtime-bridge/probes.py
```

Works on POSIX and Windows. The same probes are re-run on `peetna-aws` before
any Hermes-backed facet is attempted.

## Status — review remediation 2+3 (Питна adversarial loop)

Two review loops complete. Loop 1 (boundary defects, fixes by the reviewer,
transferred and verified): model-identity ref descriptors, fail-closed
env=None, reserved-env-key protection, hard output cap. Loop 2 (residual
P1s, fixes by ZCode):

- config_health / effective_config: a ${VAR} primary model is emitted as a
  ref descriptor; a broken raw config is `partial / config_parse_fallback`,
  never a canonical ok;
- parse_envelope: truncated/output-limited results rejected outright;
  non-empty facets required;
- profile_id is caller-supplied (`--profile-id`), never derived from the
  HERMES_HOME path;
- provider_registry with user plugins reports
  `partial / discovery_swallows_plugin_errors` (an authoritative ok was an
  unproven claim);
- key_cmd external-secret-helper sentinel added: config facets and the
  named-custom resolver path do not execute the helper (marker absent,
  spawn=0) — recorded facts;
- isolation B→A order automated; canary sweep is full-channel (stdout,
  stderr, envelope, argv, fixture files minus declared carriers).

Loop 3 (reviewer follow-up, applied): `parse_envelope` rejects
stderr-truncated, duplicate-key, and missing-effects envelopes; the caller
profile label rejects path/control-unsafe values (`invalid_profile_id`); the
canary sweep excludes only `backups/config/*`, not arbitrary `backups/*`.

Effect budget (honest statement): config/effective/runtime facets are NOT
`write: none` — Hermes bootstraps `SOUL.md`, `audio_cache`, `backups/config`
and (resolver) auth-state files inside the Hermes home; config backups
contain the full config including secrets (Hermes design, documented).
Facet proposal after remediation 2: identity GO; config_health/
effective_config MODIFY (write budget); runtime_route MODIFY/non-regular;
provider_registry DROP from regular; overall MODIFY.

Final server counts: probes 10/10 (Windows + Linux), probes_hermes 18/18,
coverage 7/7.

## Status — step 6 (coverage comparison)

`coverage.py` runs static Argus discovery (`integration-discover.py` @ the
recorded Argus revision, pointed at the fixture via `HERMES_DIR`) and the
bridge facets against the same fixtures, comparing with hand-coded expected
facts. Server result: **7/7 scenarios executed — parity 3, bridge_gain 3,
static_gain 1** (full JSON: `~/c0-spike/coverage-results.json` on
peetna-aws).

- parity: providers_named, mcp_declarations, env_ref (+ the canonical
  expansion fact on the bridge side);
- bridge_gain: model_refs (static misses `fallback_providers` and
  `auxiliary.title_generation`), malformed_config (canonical
  `partial/config_parse_fallback` vs an unstructured static-discover crash),
  user_plugin (runtime-registered provider visible only to the bridge —
  with the facet-E code-execution RED caveat);
- static_gain: oauth_metadata (out of C0 scope for the bridge, honestly
  recorded).

## Status — step 5 (provider_registry negative control)

`facet_provider_registry` calls `providers.list_providers()` (lazy
`_discover_providers`: entry points → bundled → `$HERMES_HOME/plugins/
model-providers/<name>/` exec_module → legacy files) and emits bounded
catalog metadata (count, name sample, sentinel registration fact).

Sentinel probes (user plugins in the fixture home):

- **code execution proven**: a marker-writing user plugin is imported by
  discovery (marker written, sentinel registered into the 49-provider
  registry) — the expected RED for the regular-mode decision;
- a raising user plugin is reported as `partial /
  discovery_swallows_plugin_errors`; an earlier intermediate run showed
  `state=ok / discovery_executed`, but that result is superseded;
- a hanging user plugin is killed by the bounded timeout deterministically —
  gate 3 holds on the real plugin path.

## Status — step 4 (runtime_route under containment)

`facet_runtime_route` calls the canonical resolver
(`resolve_runtime_provider`) only with explicit requested provider names from
the effective config (a blind "auto" resolution could walk the OAuth ladder
and is out of the regular experiment budget). Emits allowlisted metadata per
named provider: `provider` class, `requested_provider`, model, `api_mode`,
sanitized endpoint identity, and a **tri-state** `credential_present`
(`no` / `placeholder` / `yes`) — the resolver's returned credential value is
classified in the child and discarded, never serialized.

Findings (server, Hermes `b6b53c69`):

- the resolver returns the upstream **`no-key-required` placeholder** when a
  named custom provider has no key — a naive `bool(api_key)` misreads it as a
  materialized credential (caught and fixed in this step; upstream itself
  normalizes it in `model_switch.py` / `config_migrations.py`);
- an inline `api_key` provider materializes to `credential_present: "yes"`
  with `credential_source: pool:custom:inline`; the value never leaves the
  child (canary scans clean);
- resolver execution wrote `SOUL.md`, `backups/config/...`, `auth.lock` and
  `auth.json.tmp.*` into the fixture home; an earlier intermediate run
  reported no writes before the later effect tracing, and is superseded by
  the current effect-budget statement above;
- **isolation hardening**: without `HOME` in the child environment,
  `Path.home()` falls back to the passwd entry (the real maintainer home) —
  any Hermes code resolving `~` could escape the fixture. `build_child_env`
  now sets `HOME` to the fixture home;
- no network and no additional process spawns were observed for the named
  custom provider path (`network=[]`, `spawn=[]`).

Historical intermediate step-4 results: `probes_hermes.py` — **11 pass / 0
fail**; containment `probes.py` 9/9 on both platforms. Current counts are
listed in the remediation status above.

## Status — step 3 (effective_config allowlist)

`facet_effective_config` emits only allowlisted fields for the coverage
comparison — primary model, fallback provider names, named providers
(sanitized `scheme://host/path` endpoint identity + credential source class
and presence, never key values), declared MCP servers (transport class,
command basename, args count; URL sanitized), auxiliary task models. Values
that are `${VAR}` templates in the raw file are emitted as ref descriptors
(`var` name + `expanded`/`present` booleans) — the materialized value never
leaves the child even when expansion succeeded.

Server results (9 pass / 0 fail, `probes_hermes.py`):

- `mustpass_effective_config_allowlist` — exact allowlist emission; the
  inline `api_key`, the MCP URL query token, the aux ${VAR} value and the
  dotenv canary are all absent from every channel; URLs sanitized;
- `observation_env_expansion_behavior` — declared variable:
  `expanded=true, present=true`; undeclared: `expanded=false` (Hermes
  preserves the `${VAR}` template); value stays in the child in both cases;
- all step-2 probes remain green (no regressions).

## Status — step 2 (identity + config_health under containment)

Server setup (dedicated, production untouched): Hermes clone at the production
revision `b6b53c69` in `~/c0-spike/hermes-src`, own venv; the only non-stdlib
dependency the config seam needed was `pyyaml` (compatibility-surface fact).

`bridge.py` now installs a Python audit hook before any Hermes import and
records `socket.connect` / `subprocess.Popen` / write-mode file opens inside
the child; the envelope carries them as `effects` (bounded to 50 entries).

Hermes-backed probe results (server, `probes_hermes.py`, 7 pass / 0 fail):

- `mustpass_hermes_identity_facet` — version from the Hermes manifest
  (`0.21.2`), recorded source revision, no home paths serialized;
- `mustpass_profile_isolation_ab_sequential` — profiles A/B report their own
  primary model, no cross-profile bleed (gate 1);
- `mustpass_explicit_home_respected` — the child sees only the requested
  HERMES_HOME under the allowlisted environment (gate 7);
- `mustpass_malformed_config_not_ok` — broken config.yaml surfaces as
  `partial / config_parse_fallback` (raw parse raised ScannerError) instead of
  the loader's silent last-known-good/defaults fallback — facet B works;
- `mustpass_secret_nondisclosure_canary` — .env canary and the declared
  `${ENV}` value never reach stdout/stderr/envelope (gate 2);
- `mustpass_import_drift_fail_closed` — a missing Hermes module yields
  `compatibility_degraded / hermes_import_failed`, envelope stays valid
  (gate 5);
- `observation_config_load_write_effects_bounded` — this was an earlier
  intermediate observation before later exact runs showed bounded writes;
  the current effect-budget facts are listed above.

## Status — step 1 (harness containment)

Implemented and probed locally (no Hermes involved):

- environment allowlist with no parent-secret inheritance
  (`mustpass_env_allowlist_no_inheritance`);
- bounded timeout with deterministic kill/reap
  (`mustpass_timeout_bounded_cleanup`);
- fail-closed handling of malformed / duplicated / empty output
  (`mustpass_malformed_output_fail_closed`);
- child crash and pre-JSON exit containment
  (`mustpass_child_crash_containment`);
- output caps on both streams (`mustpass_output_cap_enforced`);
- canary leak scan self-check (`mustpass_canary_scan_selfcheck`);
- explicit profile-home passthrough, sequential runs without bleed
  (`mustpass_profile_home_passthrough`);
- write-detection mechanism self-check (OBSERVATION)
  (`observation_write_detector_selfcheck`);
- bridge envelope contract with no Hermes import
  (`mustpass_bridge_envelope_contract`).

MUST-PASS gates 1, 2, 8, 9, 10 of the contract get their full, real
verification when Hermes-backed facets run (steps 2+); the mechanisms they
rely on (canary scan, env allowlist, write detector) are validated here.

## Next steps (per the handoff sequence)

1. step 2 — identity + config-health facets (`hermes_cli.config.load_config_readonly` et al.),
   run under containment on `peetna-aws` with fixture homes;
2. step 3 — effective-config allowlist extraction, `${ENV}` fixtures;
3. step 4 — runtime-route facet with full effect observation;
4. step 5 — provider-discovery negative control (plugin sentinels);
5. step 6 — coverage comparison vs `scripts/integration-discover.py`
   and the compatibility-surface inventory;
6. step 7 — evidence receipt and the Питна adversarial review loop.
