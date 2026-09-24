# R2c.1 contract — canonical top-level fallback chain inventory

Status: **NOW / READY FOR IMPLEMENTATION**

## 1. Exact authority

Argus baseline:

```text
main = 5c38fa2381a11974d5b3691def8b5c7fa7849f81
R2a/R2a.1 = CLOSED
PR #47 candidate = 25601493e9bd2986b09f55a82dbe9837843bf30c
CI #92 = success
probes = 133/133
swap tests = 8/8
```

Hermes authority:

```text
stable = v2026.9.21 / v0.21.4
stable tag commit = d337b736aa1e8ebecfab043842d13e4a2d2f48a3
warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
```

Stable behavior is implementation authority. Main is warning/research only.

## 2. Demonstrated compatibility gap

Current Argus `scripts/integration-discover.py` inventories only one legacy
fallback:

```text
cfg.fallback_model -> model:fallback
```

It does not inventory the canonical ordered `fallback_providers` chain.

Hermes stable defines `get_fallback_chain()` as:

1. parse `fallback_providers` first;
2. preserve configured order;
3. parse legacy `fallback_model` afterwards;
4. append only routes not already seen;
5. route identity is provider + model + normalized base_url.

The stable fallback CLI persists only `fallback_providers` and removes the
legacy key.

This is a supported-stable false-negative, not a warning-source-main feature.

## 3. Stable static semantics to reproduce

Implement only the small pure/static subset needed for Argus inventory.

### Accepted source shapes

For each of `fallback_providers` and legacy `fallback_model`:

- a mapping is treated as one candidate;
- a list is treated as an ordered candidate list;
- other top-level shapes contribute no fallback entries;
- non-mapping list items are ignored.

For each candidate mapping:

- normalize provider as `str(value or "").strip()`;
- normalize model as `str(value or "").strip()`;
- ignore the candidate if either becomes empty;
- if `base_url` is a string, trim surrounding whitespace and trailing `/`.

Do not import Hermes to obtain this behavior.

### Merge order

```text
canonical fallback_providers
 -> unique legacy fallback_model entries
```

Canonical entries win because they are seen first.

### Deduplication identity

Equivalent routes are equal by:

```text
lower(trimmed provider)
lower(trimmed model)
lower(trimmed + trailing-slash-normalized base_url)
```

Deduplication may inspect raw configured values in memory, but secret-bearing
raw values must never be persisted or printed.

## 4. Argus entity representation

Preserve the existing single-fallback key where practical:

```text
first rung       -> model:fallback
second rung      -> model:fallback:1
third rung       -> model:fallback:2
...
```

Every rung remains an informational `activemodel` entity with:

- `role: fallback`;
- normalized `provider`;
- normalized `model`;
- existing non-secret `key_env` when present.

A safe/sanitized `base_url` may be retained so otherwise-equal routes can be
distinguished in the discovery snapshot. If retained, use the existing
`sanitize_url()` boundary; never emit URL userinfo or secret query values.

Do not copy arbitrary fallback-entry fields. In particular, never persist
inline `api_key` or credential material.

Entity insertion order must preserve the effective chain order.

## 5. Change semantics

The representation must be deterministic across repeated runs.

Required outcomes:

- adding a rung produces a bounded added/changed diff;
- removing a rung produces a bounded removed/changed diff;
- reordering rungs produces deterministic positional changes;
- canonical + legacy duplicates do not create duplicate entities;
- legacy-only single fallback preserves the old `model:fallback` surface.

Do not invent a new schema solely for R2c.1.

## 6. R2a/R2a.1 compatibility

R2c.1 must not weaken accepted discovery fail-safe behavior.

A degraded authoritative `config.yaml` attempt must still:

- skip normal extraction;
- preserve last-good inventory;
- avoid false fallback remove/add storms;
- keep consumers fail-closed.

Community `plugin.yaml` shape handling from R2a.1 remains unchanged.

Legacy pre-R2a snapshots remain readable.

## 7. Static inventory is not runtime truth

Configured fallback order is inventory evidence, not proof that Hermes used a
particular route for a request.

Runtime fallback observation stays owned by `fallback-tracker-v2.py`.

Hermes stable and watched main both still emit the restore marker Argus
currently consumes:

```text
Primary runtime restored for new turn: ...
```

No fallback-tracker rewrite is authorized.

## 8. Warning-source main boundary

Current main adds `scoped_fallback_chain()` for pinned/unpinned route owners,
including delegated children and cron-style owners.

That behavior is newer than the supported stable authority and materially
expands config ownership semantics.

R2c.1 MUST NOT add:

- delegated-child fallback inventory;
- cron/job fallback inventory;
- inherited/pinned fallback semantics;
- generalized scoped route ownership.

Those belong to R2c.2 after RC if they demonstrate operator value.

## 9. Owner surface

Primary:

- `scripts/integration-discover.py`.

Allowed adjacent:

- `tests/probes.py`;
- `CHANGELOG.md`.

`health-check-v2.py` may be touched only if a tiny shape-preservation change
is strictly required to carry already-sanitized informational fallback metadata
without altering health semantics. It is not expected for the core patch.

Not owners:

- `fallback-tracker-v2.py`;
- `webhook.py`;
- `registry.yaml` / `scripts/gen-registry.py`;
- OAuth/account-auth code;
- installer/i18n/RR0 surfaces.

## 10. Required red-capable probes

At minimum:

1. **canonical order**
   - 3-rung `fallback_providers` fixture appears in configured order.

2. **canonical mapping form**
   - a single mapping is accepted as one canonical entry, matching stable
     helper tolerance.

3. **canonical + legacy**
   - canonical entries appear first;
   - unique legacy entries append afterwards.

4. **dedupe identity**
   - case/whitespace variants and trailing-slash-only base_url differences
     deduplicate according to stable identity rules.

5. **distinct route identity**
   - same provider/model with genuinely distinct base URLs remains two routes.

6. **legacy-only compatibility**
   - one valid `fallback_model` preserves the old `model:fallback` key and
     non-secret entity shape.

7. **malformed entry tolerance**
   - non-mapping items and entries missing provider/model are ignored without
     crashing discovery.

8. **reorder determinism**
   - reordering the canonical chain gives deterministic positional diffs.

9. **secret boundary**
   - inline API-key canary and URL userinfo/secret-query canaries are absent
     from snapshot, report, events, stdout and stderr.

10. **R2a regression**
    - degraded authoritative config still preserves last-good fallback
      inventory and does not manufacture fallback removals.

11. **unrelated discovery control**
    - provider/MCP/OAuth/plugin discovery behavior remains unchanged.

12. **no-effects proof**
    - no Hermes imports;
    - no subprocess/network/provider/plugin execution;
    - no credential resolution or refresh.

Run the canonical-chain probe against baseline
`5c38fa2381a11974d5b3691def8b5c7fa7849f81` and record the expected RED
capability failure.

## 11. Regression gates

At minimum:

```bash
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
python3 -m py_compile scripts/integration-discover.py scripts/health-check-v2.py tests/probes.py
bash -n deploy.sh scripts/integration-discover-wrapper.sh
git diff --check
```

Exact candidate-head `argus-ci` must be green.

## 12. Non-goals

R2c.1 does not authorize:

- runtime route claims;
- fallback-tracker changes;
- main-only scoped/delegation/cron fallback support;
- broad auxiliary-role discovery;
- Hermes imports or provider registry execution;
- account-auth/OA2 changes;
- MCP health-check refactoring;
- RR0 cleanup;
- installer/i18n work;
- multi-profile fan-out;
- broad schema migration.

### MCP note

Hermes stable v0.21.4 now gives `hermes mcp test` useful 0/1/3 exit codes.
Argus still parses established output markers and remains compatible. Adopting
the new exit-code seam is a separate maintenance task, not R2c.1 scope.

## 13. Stop condition

Stop and report the concrete incompatibility if the patch begins to require:

- upstream runtime imports;
- provider/plugin execution;
- credential materialization;
- broad health/report schema changes;
- a new adapter/config framework;
- main-only scoped fallback semantics;
- RR0 cleanup to make R2c.1 work.

## 14. Role-based delivery

### Builder

Perform one implementation pass against this contract and return:

```markdown
# R2c.1 implementation receipt

## Exact baseline/head

## Stable semantics verified
- stable tag/commit:
- canonical order:
- legacy append:
- dedupe identity:

## Static chain implementation
- source shapes:
- entity key/shape:
- safe base_url behavior:

## Compatibility
- legacy-only:
- malformed entries:
- R2a degradation:

## Secret boundary

## No-effects proof
- Hermes imports:
- subprocess/network:
- provider/plugin execution:
- credential resolution:

## Tests / red capability / CI

## Changed files

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR FOCUSED REVIEW | BLOCKED
```

### Focused reviewer

Prioritize:

1. canonical order lost;
2. legacy route incorrectly precedes/replaces canonical;
3. dedupe differs from stable provider/model/base_url identity;
4. old single-fallback surface breaks unnecessarily;
5. raw base_url/API-key material leaks into artifacts;
6. R2a last-good/degraded semantics regress;
7. runtime tracker or Hermes imports enter the patch;
8. main-only scoped fallback behavior sneaks into R2c.1;
9. RR0/MCP/OA2 cleanup gets mixed into the patch.

Return:

```text
PASS-TO-MAINTAINER | REMEDIATE | BLOCKED-FOR-MAINTAINER
```

### Maintainer

After review/remediation:

- reread the exact candidate head;
- verify CI and receipt match that head;
- compare changed blobs after merge;
- authorize production deploy separately.
