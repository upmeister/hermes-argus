---
title: C1a implementation contract — bounded Hermes discovery shadow bridge
status: ready-for-agent-loop
project: hermes-argus
date: 2026-09-16
basis: ADR 0002 / B1b Agent-Analyst ACCEPT
---

# C1a implementation contract — bounded Hermes discovery shadow bridge

## 1. Outcome

C1a productionizes only the C0-proven, B1b-accepted Hermes discovery facets in **shadow mode**:

```text
identity
config_health
effective_config
```

The bridge runs beside the existing static discovery path. It records Hermes-backed metadata, compatibility state, provenance and reconciliation evidence, but it MUST NOT change health verdicts, Telegram alerts, existing static-discovery authority, or integration behavior.

C1a is evidence collection for a later C1b authority decision. It is not the authority cutover.

Architecture source of truth:

```text
docs/adr/0002-hermes-discovery-sync-boundary.md
```

C1a MUST preserve ADR 0001's regular verification budget. Discovery/sync remains a separate operational class.

## 2. Fresh-baseline gate

Before implementation, record all of:

```text
ARGUS_BASE=<exact current main after B1b is merged>
B1B_ADR_HEAD=2c88b2c1797b6af9c7bc75c6f64fa65892fa4b3c
HERMES_PRODUCTION=<revision actually installed on peetna-aws>
HERMES_UPSTREAM=<fresh upstream main/release>
```

The B1b review source-verified production candidate `af4a3eba` and observed upstream `416a8177c25d87aa9929dfcf31f7964137d7fcdd`, but neither value is a permanent implementation assumption. ZCode/Pytna MUST read the actual production installation before coding against the seam.

Reconfirm on the exact production revision:

- `hermes_cli.config.load_config_readonly` exists;
- `hermes_cli.config.read_user_config_raw` exists and can distinguish current raw parse failure from effective fallback;
- `hermes_cli.config.get_config_path` exists;
- accepted config loading does not require network, external-process spawn, token refresh, provider discovery or model generation;
- observed writes stay inside the accepted `bounded_hermes_bootstrap_only` class;
- no new metadata-only resolved-credential seam changes B1b's excluded-facet decision.

If any effect or seam materially differs from B1b/C0, STOP. Record the contradiction instead of silently widening the budget.

## 3. Required reading

Before implementation/review:

1. `AGENTS.md`;
2. ADR 0001;
3. ADR 0002;
4. `docs/experiments/c0-runtime-bridge-contract.md`;
5. `experiments/c0-runtime-bridge/README.md` and converged C0 implementation;
6. `scripts/integration-discover.py`;
7. `scripts/integration-discover-wrapper.sh`;
8. current deploy/module manifests and `config/config.env.template`;
9. current `tests/probes.py` conventions.

The C0 code is evidence and a reference implementation. Production code MUST NOT import from `experiments/c0-runtime-bridge/` at runtime.

## 4. Frozen C1a decisions

### C1 — Shadow means no authority change

During C1a:

```text
existing static discovery = production behavior
Hermes bridge           = shadow evidence only
```

The bridge MUST NOT:

- replace or delete `integration-snapshot.json`;
- alter existing added/removed/changed alert semantics;
- feed `health-check-v2.py` verdicts;
- reset or increment health hysteresis;
- change `/integrations` authority or green/red status;
- suppress static OAuth/plugin-manifest coverage;
- auto-remediate anything.

### C2 — Exactly three child facets

Automatic child execution is allowlisted to:

```text
identity
config_health
effective_config
```

Do not add `runtime_route`, `provider_registry`, auth resolvers, credential pools, OAuth status builders, `providers.list_providers()`, plugin-manager discovery or any equivalent executable provider enumeration.

### C3 — One profile per process

One short-lived child handles exactly one caller-selected Hermes profile. The parent supplies a validated stable `profile_id`, explicit `HERMES_HOME`, and explicit `HOME`.

C1a may support only the currently monitored/default production profile operationally. The data model MUST be profile-keyed, but multi-profile fan-out is not required and must not be smuggled into scope.

### C4 — Parent owns containment and state

The Argus parent owns:

- absolute interpreter selection;
- child environment construction;
- timeout, kill and reap;
- stdout/stderr byte caps;
- strict JSON parsing/schema validation;
- duplicate-key rejection;
- profile binding validation;
- effect-budget validation;
- secret/canary validation in tests;
- reconciliation with static evidence;
- provenance;
- shadow-state persistence;
- compatibility classification.

The child owns only allowlisted extraction from the accepted Hermes config seams.

### C5 — No ambient interpreter or secret inheritance

The production bridge MUST invoke an **explicit absolute Hermes Python** selected by configuration/deployment discovery. Do not resolve `python`, `python3`, `hermes` or arbitrary commands through ambient `PATH` for the child.

The child environment is built from an allowlist. Parent credentials, proxy variables, notification tokens and arbitrary shell environment MUST NOT be inherited.

Reserved execution/location variables (`HOME`, `HERMES_HOME` and equivalent profile selectors) cannot be overridden by user-supplied passthrough.

Hermes may read its own selected profile files through its canonical config path; materialized secret values MUST never be serialized.

### C6 — Effect budget is enforced, not merely documented

Accepted child budget:

```text
network = none
additional_process_spawn = none
token_refresh = none
quota = none
llm = false
remote_write = none
plugin_or_user_code_execution = none
local_write = bounded_hermes_bootstrap_only
```

The production child MUST retain C0-style effect observation sufficient to detect unexpected socket connects, subprocess creation and write targets.

Allowed Hermes-owned write class is limited to behavior freshly demonstrated on the target revision, initially expected to be paths equivalent to:

```text
$HERMES_HOME/SOUL.md
$HERMES_HOME/audio_cache/**
$HERMES_HOME/backups/config/**
```

Do not expand this allowlist because a test failed. Any newly observed write class is `compatibility_degraded` and a review stop until explained and accepted.

Argus parent persistence of its own shadow snapshot is separate from child/Hermes effects and must be confined to Argus-owned state under the selected Hermes `state/` directory (matching current project convention).

### C7 — Allowlist extraction is the security boundary

Do not serialize broad Hermes config/runtime objects and then recursively redact them.

`effective_config` may emit only reviewed non-secret shapes, initially:

- primary model/provider identity;
- fallback model/provider references, including the newer `fallback_providers` semantics covered by C0;
- auxiliary model/task references, including roles present on the current Hermes revision (e.g. vision/compression/title-generation when configured);
- declared MCP name + transport class; for stdio, command basename and bounded arg count only; for URL transports, sanitized endpoint identity only;
- named/custom provider identity + sanitized endpoint identity + declarative auth/source class;
- `${ENV}` descriptors containing variable name and booleans such as declared/present/expanded, never the materialized value.

No absolute home paths, full commands, arbitrary args, environment mappings, auth headers, raw exception reprs, credentials, token fingerprints, raw config text or plugin object representations.

### C8 — config_health must distinguish current parse truth from effective fallback

A non-empty/effective config object is not enough for `config_health=ok`.

At minimum classify:

```text
ok
partial / config_parse_fallback
compatibility_degraded / hermes_import_failed
compatibility_degraded / hermes_api_incompatible
```

The exact schema may add bounded reason codes, but malformed current YAML MUST NOT look canonical merely because Hermes can serve defaults or last-known-good state.

### C9 — Separate shadow state

Suggested state files (names may be adapted to repository conventions without changing semantics):

```text
$HERMES_HOME/state/hermes-discovery-shadow.json
$HERMES_HOME/state/hermes-discovery-reconciliation.json
```

They MUST NOT overwrite `integration-snapshot.json`.

Writes are atomic. On child failure, preserve the last good shadow snapshot only if it is explicitly marked stale and the current compatibility/degradation observation is stored separately; never silently present last-good as current.

### C10 — Existing static wrapper remains behaviorally authoritative

Preferred trigger integration is a guarded shadow hook in the current discovery wrapper rather than a second independent alerting system:

```text
run existing static discovery -> capture its report + rc
if shadow enabled:
    run bounded shadow collector with stdout suppressed from legacy report
    log/store shadow result; ignore it for legacy rc/alert decision
continue existing legacy rc/Telegram behavior unchanged
```

Important invariants:

- shadow execution happens before any legacy early-return if the trigger is intended to refresh shadow state;
- shadow failure cannot change the static process exit class;
- shadow stdout/stderr cannot contaminate the static report parsed by Telegram formatting;
- no shadow alert is sent in C1a;
- a timeout adds only bounded latency and must not strand the wrapper lock;
- the existing static snapshot must still update even when shadow is broken.

A separate systemd unit/path is acceptable only if it demonstrably has lower coupling and preserves the same no-alert/no-authority guarantees. Do not duplicate filesystem-trigger races casually.

### C11 — Shadow is opt-in at deployment

Add an explicit configuration switch, default OFF in repository templates, e.g.:

```text
HERMES_DISCOVERY_SHADOW=0
```

and an explicit absolute Hermes interpreter/config knob if current deployment cannot resolve it safely.

Merging C1a code does not authorize enabling shadow on production. Production enablement requires maintainer/user authorization after exact-host read-back.

## 5. Shadow envelope

The child envelope MUST be versioned and strict. Suggested logical shape:

```json
{
  "schema": 1,
  "profile_id": "default",
  "facets": {
    "identity": {},
    "config_health": {},
    "effective_config": {}
  },
  "effects": {
    "network": [],
    "process_spawn": [],
    "writes": []
  }
}
```

The parent adds observation metadata and compatibility/provenance rather than trusting the child to declare its own authority.

Reject whole child results on at least:

- invalid JSON;
- duplicate keys;
- more than one top-level envelope;
- empty/missing requested facets;
- wrong schema/types;
- profile mismatch;
- stdout or stderr truncation/output cap;
- timeout/crash;
- unexpected effect class;
- forbidden/unknown facet;
- unsafe profile id;
- known-canary disclosure in tests.

## 6. Provenance and reconciliation schema

C1a compares only **mapped semantic fields**. It must not pretend every static entity has a Hermes equivalent.

Every mapped observation should preserve:

```text
profile_id
entity_id / semantic_key
field
hermes_value_or_descriptor
static_value_or_descriptor
hermes_authority = hermes-effective
static_authority = argus-static | legacy-static
relation
reason_code
```

Allowed relation vocabulary should be small and machine-readable, for example:

```text
equal
bridge_gain
static_retained
semantic_difference
not_comparable
degraded
```

Definitions:

- `equal` — same normalized safe semantic value;
- `bridge_gain` — accepted Hermes facet sees a mapped fact static discovery does not;
- `static_retained` — static-only coverage intentionally remains (not a bridge defect), notably OAuth metadata and declarative plugin manifests unless separately mapped;
- `semantic_difference` — both sources claim comparable semantics but disagree;
- `not_comparable` — source concepts differ and must not be scored as parity;
- `degraded` — Hermes-backed observation is unavailable/incompatible; static evidence may remain visible with lower authority.

Do not reduce reconciliation to a single percentage that hides source-specific gaps.

## 7. Initial mapping matrix

At minimum reconcile these families where both sides are meaningful:

| Semantic family | Hermes shadow | Static source | Expected C1a treatment |
|---|---|---|---|
| primary model/provider | effective_config | `model:primary` | comparable |
| fallback model/provider refs | effective_config | current fallback entities | comparable where static represents same field; bridge gain recorded otherwise |
| auxiliary task model refs | effective_config | current aux subset | comparable for shared roles; bridge gain for missing static roles |
| declared MCP names/transport | effective_config | `mcp:*` | comparable after normalization |
| named/custom provider declarations | effective_config | `provider:*` | compare identity/sanitized endpoint only; no resolved credential truth |
| env references | effective_config descriptors | `envref:*` | compare declared/presence semantics carefully; materialized values forbidden |
| OAuth metadata | intentionally absent | `oauth:*` | `static_retained`, not parity failure |
| plugin manifests | intentionally no executable registry | `plugin-provider:*` | `static_retained`, not parity failure |
| registry-only tool/env integrations | intentionally absent unless config facet naturally exposes them | `envkey:*` | `static_retained` |

C1a implementation MUST document any normalization rules rather than making ad-hoc string comparisons.

## 8. Input signature and cadence

Shadow runs under the existing change-driven discovery cadence plus its periodic safety run, but may avoid unnecessary Hermes child execution using a cheap safe input signature.

The signature may include non-secret metadata/hashes of relevant files, but MUST NOT serialize config/.env/auth content into logs or argv.

A cache/signature hit must never suppress a required compatibility recheck after any of:

- Hermes executable/revision change;
- bridge schema/revision change;
- selected profile change;
- config signature change.

## 9. Production code shape

Exact names may follow repository conventions, but the implementation should separate concerns approximately as:

```text
scripts/hermes-discovery-bridge.py     # short-lived Hermes child only
scripts/hermes-discovery-shadow.py     # Argus parent/containment/reconcile/state
scripts/integration-discover-wrapper.sh # tiny guarded trigger hook if chosen
tests/probes.py                        # production regression/containment probes
config/config.env.template             # opt-in + explicit interpreter if needed
CHANGELOG.md                            # user-visible shadow capability
```

Do not make the long-lived bot/webhook/watchdog import Hermes.

Do not copy experimental files wholesale while retaining dead facets (`runtime_route`, `provider_registry`). Production child code should expose no callable path to excluded facets.

## 10. Required tests

### Parent containment

- environment allowlist / no parent-secret inheritance;
- reserved HOME/HERMES_HOME cannot be overridden;
- explicit absolute child interpreter;
- timeout kill + deterministic reap;
- stdout and stderr hard byte caps;
- crash/import-error containment;
- malformed/empty/multi-envelope/duplicate-key fail closed;
- unsafe profile id rejected without reflecting it unsafely;
- A→B and B→A profile isolation;
- no legacy wrapper rc/report/alert semantic change when shadow succeeds/fails/times out.

### Accepted Hermes facets

On synthetic profile homes using the actual target Hermes revision:

- identity bounded output;
- malformed config => `config_parse_fallback`, never ok;
- fallback-provider coverage;
- auxiliary role coverage including current roles;
- MCP sanitization;
- provider endpoint sanitization;
- `${ENV}` materialized value never serialized;
- inline api keys never serialized;
- `.env` canaries never serialized;
- no key-command helper execution;
- no network;
- no additional process spawn;
- only freshly accepted bounded Hermes bootstrap writes.

### Negative-control safety tests

Fixtures MUST include executable provider/plugin sentinels and helper-command sentinels. Running all automatic C1a facets must leave their marker files absent. This proves production code did not accidentally reintroduce provider/plugin discovery or external secret helpers.

### Reconciliation

Port/extend the seven C0 coverage scenarios into production tests, but assert the C1a relation vocabulary rather than only counts. Include explicit expected `static_retained` cases for OAuth/plugin metadata.

### Secret surfaces

Canary scan at least:

```text
child stdout
child stderr
parsed envelope
parent shadow snapshot
reconciliation snapshot
logs produced by the test harness
child argv
Hermes-written files except the explicitly acknowledged secret-bearing backups/config carrier
```

The acknowledged Hermes backup carrier is excluded from "Argus leak" assertions only because Hermes itself deliberately writes the config copy; its path/effect still must be recorded and bounded.

## 11. C1a acceptance gate

C1a is acceptable only when all are true:

1. old static discovery behavior remains operational and authoritative;
2. shadow code has no path to health verdicts or Telegram change alerts;
3. exact production Hermes target passes accepted-facet containment/effect tests;
4. no unexplained `semantic_difference` remains in fields proposed for eventual authority cutover;
5. expected bridge gains and static-retained families are explicitly classified;
6. no secret canary leaves allowed carriers;
7. plugin/user code and key helpers are not executed;
8. CI/probes pass on exact PR head;
9. production enablement, if performed, has an evidence receipt and read-back;
10. no C1b authority cutover is included.

C1a success does **not** automatically authorize C1b. It produces the evidence package on which the Agent-Analyst can define C1b.

## 12. Deployment authorization and rollout

### Merge boundary

The implementation PR may be reviewed/merged without production enablement.

### Enable boundary

Do not enable `HERMES_DISCOVERY_SHADOW` on peetna-aws without explicit maintainer/user authorization in the implementation cycle.

Before enabling:

- re-read deployed Argus exact head;
- re-read actual Hermes revision and interpreter path;
- run production-Hermes fixture probes outside the real profile;
- verify no new effect class;
- back up/record existing static snapshot metadata (not secret contents in PR/logs).

After enabling:

- run one explicit shadow collection;
- verify static discovery still produces its normal output/exit behavior;
- read back shadow compatibility and reconciliation state;
- verify no Telegram shadow alert;
- inspect only bounded metadata/effects, never dump raw profile secrets.

## 13. Rollback

Rollback must be trivial because authority never moved:

1. set shadow flag OFF / disable the guarded hook;
2. restore prior wrapper if the hook itself caused regression;
3. leave existing static snapshot/discovery untouched;
4. shadow state files may be retained as historical evidence or removed after review;
5. no health-state repair or authority migration is required.

Any C1a implementation that makes rollback require rebuilding static discovery is out of scope.

## 14. Stop conditions

Stop the autonomous implementation/review loop and return to Agent-Analyst if:

- current production Hermes expands accepted facet effects beyond ADR 0002;
- a supposedly accepted config import executes plugin/user code;
- network, token refresh, external process or model/quota activity is required;
- safe output requires broad serialize-then-redact;
- static behavior must change to make shadow collection work;
- production bridge cannot distinguish current malformed config from effective fallback;
- a new upstream metadata API materially changes B1b's architecture;
- reviewers propose adding `runtime_route`/provider registry merely for coverage.

## 15. PR requirements for the implementation cycle

Preferred title:

```text
feat(argus): add bounded Hermes discovery shadow bridge (C1a)
```

PR body must include:

```markdown
## Outcome
## Scope / non-goals
## Fresh baselines
## Architecture / process boundary
## Accepted facets
## Shadow + reconciliation schema
## Effect evidence
## Secret review
## Static-behavior preservation
## Tests and real results
## Production actions
## Rollback/read-back
## Known gaps / static-retained coverage
## Recommendation
READY FOR PYTNA REVIEW | BLOCKED
```

If production shadow was enabled, add exact host evidence. If not, state `No production action performed.`

## 16. Definition of Done

C1a is complete when:

- a reviewed production bridge exists for exactly the three accepted facets;
- process/environment/output/effect boundaries are regression-tested;
- shadow state and provenance/reconciliation state are separate from legacy static state;
- existing static discovery behavior is demonstrably unchanged;
- expected bridge gains and retained static-only coverage are visible;
- exact production Hermes compatibility is tested, not assumed from C0;
- CI is green on exact head;
- Pytna has completed adversarial review/remediation;
- Agent-Analyst receives the exact-head evidence receipt for the C1b decision.
