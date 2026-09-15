# ADR 0002: Hermes discovery/sync boundary

- **Status:** Proposed (→ Accepted on the Agent-Analyst gate)
- **Date:** 2026-09-15
- **Basis:** C0 bounded Hermes runtime bridge spike (contract:
  `docs/experiments/c0-runtime-bridge-contract.md`; experiment:
  `experiments/c0-runtime-bridge/`)
- **Related:** ADR 0001 (`docs/adr/0001-integration-evidence-policy.md`)
- **Next:** C1a shadow-bridge contract, after the analyst gate

## Status

**Proposed.** This ADR is the B1b decision record produced from the completed
C0 spike. It is intentionally architecture-only: no production wiring is
authorized by accepting this ADR.

C0 archival baselines, recorded as historical evidence (not assumed current):

- Argus C0 archival merge: `19aa9f2b54ec8b97bbf0d6b2e8c478656e74c89`;
- converged C0 experiment head: `3d48e2f`;
- production Hermes revision exercised by C0: `b6b53c69`;
- C0 final decision: overall **MODIFY**.

B1b review re-read the current baselines and recorded them below
(Compatibility and baselines). Historical SHAs appear in this ADR only as
evidence references.

## Context

Argus is an external watchdog and verification-policy layer around Hermes.
The existing architecture rule remains:

```text
Hermes owns runtime truth.
Argus owns verification policy.
```

ADR 0001 defines evidence claims, canonical verdicts, failure semantics, and
the side-effect budgets for regular/live/deep verification. It deliberately
keeps regular verification strongly bounded; in particular, regular checks do
not gain a general permission to mutate runtime state merely because an
upstream library performs bootstrap writes.

Before C0, Argus reconstructed a substantial part of Hermes
configuration/runtime state from static files (`config.yaml`, `.env`,
`auth.json`, generated registry metadata, plugin manifests). That approach is
independent and cheap but duplicates Hermes semantics and can drift as
profile/provider/runtime behavior changes.

C0 tested whether a short-lived subprocess running under Hermes's own Python
environment could expose a safe, redacted subset of Hermes-owned truth without
importing Hermes into the long-lived Argus watchdog.

### C0 facts that drive this ADR

The converged C0 evidence established:

1. **Process isolation works when explicit.** One child per profile with
   explicit `HERMES_HOME` and `HOME`, an environment allowlist, bounded
   timeout/output, and fail-closed parsing avoided cross-profile state bleed
   in A→B and B→A tests.
2. **Config facets add useful coverage.** Hermes-backed config inspection
   exposed fallback-provider and auxiliary model semantics that static Argus
   did not fully represent, and it converted malformed-config behavior from a
   static discovery crash into structured degradation.
3. **Hermes config loading is not `write:none`.** On a truly fresh profile
   home, canonical config loading creates bounded local bootstrap/backup
   artifacts (`SOUL.md`, `audio_cache/`, `backups/config/`).
4. **Runtime route resolution is stronger and riskier than metadata
   discovery.** It can materialize credentials internally and touch auth
   state. C0 demonstrated bounded behavior only for selected explicit
   named-provider paths, not for the full OAuth/pool/external-process routing
   ladder.
5. **Provider registry discovery executes plugin code.**
   `providers.list_providers()` imports executable user/provider plugin code;
   a hanging plugin required the outer harness timeout, and plugin failures
   are silently swallowed by discovery.
6. **Resolved credential presence is not safely canonical in metadata mode.**
   Static `.env` presence and Hermes runtime credential resolution are
   different semantics; C0 did not establish a side-effect-free canonical API
   for resolved credential presence.
7. **Static discovery still has useful coverage.** Existing OAuth metadata
   was visible statically while C0 intentionally left OAuth runtime
   resolution out of scope.

The decision therefore is not to adopt a general runtime introspection
bridge. It is to adopt a **bounded discovery/sync boundary** and keep
stronger runtime behavior outside the default path.

## Decision

### 1. Verification tiers and discovery/sync are separate concepts

ADR 0001 remains authoritative for regular/live/deep **verification**.

B1b introduces a separate operational class:

```text
discovery/sync
```

`discovery/sync` obtains and reconciles configuration/runtime metadata. It is
**not a health check**: it does not itself prove `transport`, `authenticated`,
`semantic`, or `active`, and it does not directly produce a
`healthy`/`failed` verdict.

This separation is deliberate:

```text
regular verification != Hermes discovery/sync
```

Regular verification does **not** gain `write: local` permission from this
ADR.

### 2. The Hermes boundary is a short-lived process boundary

Long-lived Argus processes MUST NOT import Hermes runtime modules directly.

The accepted pattern is:

```text
Argus discovery orchestrator
    -> absolute Hermes Python/runtime
    -> one short-lived child for exactly one profile
    -> explicit HOME + HERMES_HOME
    -> allowlisted environment
    -> requested metadata facets only
    -> bounded stdout/stderr + timeout
    -> fail-closed validated JSON
```

The parent owns profile selection, timeout, output caps, termination, schema
validation, provenance, diffing, state persistence, alerts, and compatibility
classification. The child owns only the narrow Hermes-backed metadata
extraction required by accepted facets. A child MUST NOT infer or switch to
another profile when an explicit profile home is supplied.

Note on seam stability (re-verified at review time): the config seams
(`load_config_readonly`, `read_user_config_raw`, `get_config_path`) and the
provider discovery machinery exist unchanged in production Hermes `af4a3eba`
(v0.21.3) and upstream `5910de20`. `get_hermes_home()` gained a non-breaking
context-local override layer — the explicit-`HERMES_HOME` contract is
unaffected.

### 3. Accepted first-production facets

The first production bridge may contain only these C0-proven facet classes:

#### `identity` — accepted

Bounded non-secret identity metadata: Hermes version/revision and bridge
schema/revision. It MUST NOT expose absolute profile paths, hostnames,
environment dumps, or arbitrary module representations.

#### `config_health` — accepted for discovery/sync only

Hermes config seams plus a raw-parse/degradation signal distinguish:

- successful current config parse;
- fallback/default/last-known-good behavior;
- incompatible import/API behavior;
- malformed config.

A successfully returned config object MUST NOT be treated as proof that the
current user config parsed successfully.

#### `effective_config` — accepted for discovery/sync only

An explicit allowlist of non-secret configuration semantics, initially
limited to fields justified by C0/C1 coverage work:

- primary model identity/provider metadata;
- fallback model/provider references;
- auxiliary model/task references;
- declared MCP names and transport class, where extraction neither connects
  to nor executes the server;
- configured provider/custom-provider identity and sanitized endpoint /
  auth-class metadata;
- `${ENV}` reference descriptors without materialized secret values.

The bridge MUST use allowlist extraction. Broad serialization followed by
recursive redaction is not an accepted security boundary.

### 4. Discovery/sync has a narrow, explicit effect budget

Accepted config facets may have this budget:

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

`bounded_hermes_bootstrap_only` means writes caused by the accepted canonical
config-loading path inside the explicitly selected Hermes home, such as the
bootstrap/backup behavior demonstrated by C0. Note that Hermes-written config
backups (`backups/config/`) contain a full copy of the config, secrets
included — this is Hermes-owned behavior and is documented here, not
introduced by Argus.

The budget does NOT authorize:

- arbitrary Argus writes through the child;
- auth-state rotation or refresh;
- external secret helper execution;
- provider plugin execution;
- writes outside the selected Hermes home;
- making regular verification writable.

If a future Hermes version expands effects beyond this budget, the facet
becomes `compatibility_degraded` until re-reviewed.

### 5. Facets excluded from the first production bridge

#### `runtime_route` — deferred / non-default

Do not productionize `resolve_runtime_provider` in the initial bridge.
Reasons: it can materialize credential values internally; C0 observed
auth-state writes; only selected explicit named-provider paths were bounded;
the broader routing ladder includes OAuth, pools, and external processes not
proven safe for this execution class. A future diagnostic/live capability may
revisit this with a separate contract.

#### `provider_registry` — prohibited in automatic discovery/sync

Do not call provider discovery APIs that execute bundled/user/pip/legacy
plugin code from the automatic bridge. C0 demonstrated executable user plugin
imports and hang containment, and discovery silently swallows plugin import
errors. This is outside the discovery/sync budget.

#### Resolved credential presence — unsupported

Do not claim canonical resolved credential presence unless Hermes exposes a
metadata-only seam whose effect/security contract is separately demonstrated
(no such seam exists at the reviewed revisions). Static key/file presence may
still be reported as static evidence, but it MUST NOT be mislabeled as
Hermes-resolved credential truth.

### 6. Authority and provenance are first-class

Every discovered entity/field that can come from multiple sources MUST
preserve provenance. At minimum distinguish:

```text
hermes-effective
argus-static
legacy-static
```

The exact vocabulary may be normalized during C1, but the semantic rule is
fixed:

- accepted Hermes facets are authoritative for the Hermes-owned fields they
  actually expose;
- Argus static discovery remains authoritative for Argus-owned/local metadata
  and may retain coverage not yet present in the bridge;
- static fallback MUST NOT silently masquerade as Hermes runtime truth when
  the bridge is degraded.

When Hermes-backed discovery fails, Argus may preserve lower-authority static
information for continuity, but it MUST also surface the
compatibility/degradation state.

### 7. Migration is shadow-first, then authority cutover

The first production use of the bridge MUST be shadow/reconciliation mode:

- existing discovery behavior remains operational;
- bridge output is computed independently;
- entity/field parity and semantic differences are recorded;
- the bridge does not directly change health verdicts or alert semantics;
- no legacy source is deleted merely because the bridge exists.

Only after a reviewed parity/coverage gate may selected Hermes-owned fields
switch authority to `hermes-effective`. Cleanup of superseded static
reconstruction is a later focused change and must show parity/coverage before
deletion.

### 8. Discovery/sync cadence is change-driven and bounded

The bridge is not part of each regular health loop. Preferred triggers:

- relevant Hermes config/profile change;
- explicit/manual rescan;
- bounded periodic fallback for missed filesystem events.

A cheap safe input signature may suppress unnecessary child execution when
nothing relevant changed. The existing change-driven discovery model
(`systemd.path` plus periodic fallback) is compatible with this decision.

### 9. Compatibility is explicit, not silent fallback

Internal Hermes APIs are treated as unstable compatibility seams unless
upstream explicitly declares otherwise. On import/API/schema breakage,
timeout, malformed bridge output, or effect-budget violation:

```text
compatibility = degraded
```

Argus MUST preserve this fact in discovery state/reporting. It may retain
static information with lower authority, but it must not silently reinterpret
that information as canonical Hermes truth.

### 10. Two baselines are maintained

For each bridge implementation/review cycle record:

1. **production compatibility target** — the Hermes revision actually
   installed on the monitored system;
2. **upstream drift signal** — current upstream `main` or relevant release at
   review time.

The production target determines immediate compatibility; upstream drift
determines maintenance risk and whether a seam should be revalidated before
rollout. Baselines recorded at B1b review time:

```text
production Hermes: af4a3eba (v0.21.3)
upstream Hermes main: 5910de20
```

Neither is frozen as permanently canonical.

### 11. Secret and serialization boundary

The production bridge MUST retain the C0 security model:

- explicit safe profile ID supplied by the parent; never derived from an
  untrusted path basename; validated (bounded, ASCII, path/control-safe);
- environment allowlist, not inherited parent environment; reserved
  `HOME`/`HERMES_HOME` cannot be overridden;
- no secret-bearing argv; no environment/header/body dumps;
- sanitized endpoint metadata only;
- `${ENV}` values represented as references/presence metadata, never emitted
  values;
- duplicate JSON keys, truncated streams, empty facets, malformed schemas and
  oversized output fail closed;
- canary scans cover the output/error/result/argv/file surfaces claimed by
  the implementation.

## Consequences

### Positive

- Argus reduces duplicated Hermes config semantics without becoming a second
  Hermes runtime.
- Profile isolation is enforced by the OS process boundary rather than
  relying on long-lived Python global/cache discipline.
- Config drift and malformed-config failures become explicit
  compatibility/discovery states instead of silent wrong truth or crashes.
- Existing static discovery remains available for coverage areas not yet
  safely exposed by Hermes.
- ADR 0001's strict regular verification budget remains intact.

### Costs

- Discovery causes bounded bootstrap/backup writes in the selected Hermes
  home (including config backups that contain secrets).
- The bridge depends on a small unstable internal Hermes API surface that
  requires compatibility probes.
- Shadow/parity migration takes longer than a direct replacement.
- Some desirable runtime facts (resolved credential state, executable
  provider registry semantics) remain intentionally unavailable.

## Rejected alternatives

### Import Hermes directly into the long-lived Argus watchdog

Hermes contains process-global caches, ContextVars, plugin discovery,
profile-sensitive state and rapidly changing internal seams. C0 reinforced
the value of one-profile-per-process isolation.

### Treat the whole runtime resolver as the canonical bridge

C0 did not prove the full route/auth ladder inside an acceptable automatic
effect budget; the resolver can materialize credentials and touch auth state.

### Use `providers.list_providers()` for canonical provider discovery

It executes plugin code and can hang or silently swallow plugin failures.

### Loosen regular verification to permit Hermes bootstrap writes

Discovery/sync is a separate operation class; regular health policy remains
strict.

### Replace static discovery immediately

C0 found both bridge gains and static-only coverage. Migration must be
shadow-first and provenance-aware.

### Treat static fallback as canonical when the bridge breaks

It recreates the false-authority problem the bridge is meant to reduce.

## Follow-up work

1. **C1a — production bridge in shadow mode:** `identity + config_health +
   effective_config` only, with its own implementation contract,
   parity/provenance schema, rollback/read-back plan and production
   authorization boundary.
2. Fix the static `integration-discover.py` malformed-YAML crash as a
   separate narrow Argus bugfix (still present; C0 coverage scenario
   `malformed_config`).
3. Define the C1 reconciliation/provenance schema and parity gate.
4. **C1b — authority cutover** for fields whose bridge coverage is
   demonstrated.
5. Keep `runtime_route`, executable provider discovery and resolved
   credential presence out until separately contracted.
6. Continue D0b specialized evidence enrichment independently where it does
   not depend on unresolved Hermes runtime semantics.

## Decision summary

```text
C0 experiment                ACCEPTED / overall MODIFY
identity                     GO
automatic config discovery   GO with bounded discovery/sync budget
regular health write budget  unchanged
runtime_route                deferred / non-default
provider_registry            prohibited in automatic bridge
resolved credential presence unsupported without a new safe Hermes seam
migration                    shadow first, authority cutover later
```
