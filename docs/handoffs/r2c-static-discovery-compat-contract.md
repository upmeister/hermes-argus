# R2c contract — bounded static discovery compatibility with current Hermes

Status: **R2c.1 NOW / READY FOR IMPLEMENTATION**

## Exact baseline

```text
Argus main = 7b78e9369be72d9a5f08de267ccfc62604710f79

R2a / PR #44 = DONE
R2a candidate = 6241543d96e93cfbe197706dcbf316fbbc72b58d
R2a CI #86 = success
R2a probes = 131/131
R2a swap tests = 8/8
```

Hermes authority:

```text
stable = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
warning-source main = 64c7da592d43a9f155ea8606865d9ae1eda3222b
```

## 1. Demonstrated compatibility gap

Current Argus only inventories:

```text
cfg.fallback_model -> model:fallback
```

and ignores the canonical ordered `fallback_providers` chain.

This is a real false-negative against the supported stable release, not merely
fresh-main drift.

Hermes stable `v2026.9.14` and fresh main both define
`get_fallback_chain()` with the same semantics:

1. read `fallback_providers` first and preserve its order;
2. append valid legacy `fallback_model` entries afterwards;
3. deduplicate equivalent provider/model/base_url routes.

The Hermes fallback CLI persists only `fallback_providers` and removes
`fallback_model`.

Therefore a normal current Hermes configuration can have all fallback rungs
invisible to Argus.

## 2. R2c.1 selected scope

R2c.1 updates **static top-level fallback inventory only**.

Primary owner:

- `scripts/integration-discover.py`.

Allowed adjacent:

- `tests/probes.py`;
- `CHANGELOG.md`.

`health-check-v2.py` may be touched only if the existing informational
`active_models` projection would otherwise destroy the newly represented
chain order/identity. Stop and report before expanding further.

Not owners:

- `fallback-tracker-v2.py`;
- `webhook.py` absent a concrete local rendering regression;
- `registry.yaml` / `gen-registry.py` absent a demonstrated fallback bug.

## 3. Static chain semantics

Implement the smallest pure/static equivalent needed for inventory.

### Canonical source

Accept `fallback_providers` as the primary ordered chain.

A valid entry requires non-empty string:

```text
provider
model
```

Malformed/non-mapping entries are ignored rather than crashing discovery.

### Legacy append

After canonical entries, append valid `fallback_model` entries.

Keep minimum compatibility with the stable Hermes semantics. Both dict and list
forms may be accepted if doing so stays local and simple.

### Deduplication

Equivalent routes should appear once.

Bounded identity:

```text
provider + model + normalized/sanitized base_url identity
```

Do not import Hermes' helper merely to obtain this behavior.

Case/whitespace normalization may follow the obvious stable static semantics,
but do not grow a compatibility framework around obscure provider aliases.

### Ordered entity representation

Keep the old single-fallback surface stable where practical.

Preferred positional keys:

```text
first rung      -> model:fallback
additional rung -> model:fallback:1
                   model:fallback:2
                   ...
```

All remain informational `activemodel` entities with role `fallback`.
Insertion/report order must preserve configured chain order.

A different equally small key shape is acceptable only if it preserves:

- deterministic order;
- stable identity across repeated runs;
- legacy single-entry compatibility;
- meaningful diff behavior on reorder.

### Route metadata / secret boundary

If `base_url` is retained in snapshot metadata to distinguish routes, it must
use the existing URL sanitization boundary. Userinfo and secret query values
must never enter snapshot/report/event output.

Do not persist credential material or provider-resolved runtime metadata.

## 4. Static inventory is not runtime truth

Do not claim the configured chain is the route Hermes actually used.

Runtime observation stays owned by `fallback-tracker-v2.py`.

Fresh main still emits the restore marker Argus currently consumes:

```text
Primary runtime restored for new turn: ...
```

No fallback-tracker rewrite is authorized by R2c.1.

## 5. R2a compatibility

R2c.1 must preserve the new discovery fail-safe semantics.

A degraded snapshot/config attempt must not:

- run fallback extraction on invalid config as if it were healthy;
- overwrite last-good inventory;
- create a false fallback remove/add storm;
- bypass consumer fail-closed behavior.

Legacy pre-R2a snapshots remain readable according to the accepted R2a contract.

## 6. Required red-capable probes

At minimum:

1. canonical 3-rung `fallback_providers` fixture appears in configured order;
2. canonical + legacy fixture: canonical entries first, unique legacy appended;
3. duplicate canonical/legacy provider/model/base_url route appears once;
4. legacy-only single fallback preserves the old `model:fallback` behavior;
5. malformed chain/list entries are ignored safely;
6. chain reorder produces deterministic positional changes rather than random
   identity churn;
7. two otherwise-equal routes with distinct safe base URLs remain
   distinguishable if base_url participates in identity;
8. URL userinfo/secret query canaries are absent from snapshot/report/events;
9. unrelated provider/MCP/OAuth discovery behavior remains unchanged;
10. R2a degraded-state/last-good behavior remains unchanged;
11. no Hermes imports, subprocess, network, provider/plugin execution or
    credential resolution is added.

Whenever practical, run the new canonical-chain probe against the pre-R2c.1
baseline and record the red result.

## 7. R2c.2 — deferred

Auxiliary-role expansion remains **AFTER RC**.

Do not enumerate every upstream auxiliary/delegation/MoA/cron role merely
because fresh Hermes has one.

Add a role later only when it materially changes operator understanding or a
real incident demonstrates monitoring value.

## 8. Account-auth subsection — retired

Credential/OAuth/account-auth work remains owned by OA0/OA1/OA2.

Do not add credential-pool parsing under R2c.

## 9. Registry semantics

`registry.yaml` remains curated Argus check/catalog metadata, not a complete
Hermes runtime registry.

Do not redesign the generator to chase “100% Hermes integration coverage” in
R2c.1.

## 10. Non-goals

R2c.1 does not authorize:

- runtime route truth;
- fallback tracker changes;
- R2c.2 auxiliary/delegation/MoA coverage;
- Hermes imports or provider registry execution;
- account-auth/OA2 changes;
- RR0 legacy cleanup;
- installer/i18n work;
- broad schema migration.

## 11. Stop condition

Stop if the patch begins to require:

- upstream runtime imports;
- provider/plugin execution;
- credential materialization;
- broad health/report schema changes;
- a new adapter framework;
- RR0 cleanup to make R2c.1 work.

Report the concrete incompatibility instead.

## 12. ZCode receipt

```markdown
# R2c.1 outcome

## Exact baseline/head

## Upstream semantics verified
- stable:
- fresh main:

## Static chain implementation
- canonical order:
- legacy append:
- dedupe identity:
- entity key/shape:

## Compatibility
- legacy-only:
- malformed entries:
- R2a degradation:

## Secret boundary
- base_url/query/userinfo:

## No-effects proof
- Hermes imports:
- subprocess:
- network/provider/plugin execution:

## Tests / red capability / CI

## Changed files

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR PYTNA | BLOCKED
```

## 13. Pytna focus

Prioritize:

1. canonical order lost;
2. legacy entry replaces/precedes canonical incorrectly;
3. duplicate route appears twice;
4. old single-fallback shape breaks needlessly;
5. route secrets appear in snapshot/report/event output;
6. runtime tracker/Hermes imports enter the patch;
7. R2a degraded-state behavior regresses;
8. RR0 cleanup gets mixed into R2c.1.

Recommendation:

```text
PASS-TO-MERGE | REMEDIATE | BLOCKED-FOR-MAINTAINER
```
