# OA1 contract — generic static account-auth discovery

Status: **DONE / MERGED IN PR #35**

Final reviewed/merged receipt:

```text
reviewed PR head = abb7ceecd805fe4c4ffc1f90248a562be88de051
merged main      = cfa6c535518e3d3ad9b78c20d442335f48e84fd6
CI run #61       = success
```

The four changed blobs match exactly between reviewed head and merged main.

Baseline:

```text
hermes-argus main = c8c3b66c26913481e2fef54195678490f2a96e96
OA0 / PR #33 = DONE / MERGED
OA0 decision = STATIC ONLY
supported Hermes stable = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
```

Upstream warning source observed 2026-09-19:

```text
Hermes main = 1e4952ddba1bc585416ad43438d60183380035cd
latest stable remains v2026.9.14
```

Read first:

1. repository `AGENTS.md`;
2. `docs/handoffs/2026-09-17-next-steps-execution-baseline.md`;
3. `docs/research/oa0-account-auth-discovery-research.md`;
4. this contract;
5. current `scripts/integration-discover.py`;
6. current `scripts/health-check-v2.py`;
7. relevant current probes/tests.

## 1. Problem

OA0 demonstrated a current user-visible false negative:

- Argus layer 4 uses a fixed `OAUTH_FLOWS` roster;
- it only recognizes flat `auth.json.providers.<id>.access_token`;
- supported Hermes stores OpenAI/Codex auth in nested provider state and/or
  `credential_pool.openai-codex[]`;
- a working primary Codex account can therefore be absent from Argus inventory.

OA0 also established a semantic constraint that current Argus violates:

```text
persisted credential evidence present
!= logged in
!= healthy
```

Today `health-check-v2.py` maps every `type=oauth` snapshot entity to an
`oauth` primitive that returns `ok, "logged in"` without a runtime auth
check. OA1 must not extend that false-green behavior to newly discovered
static account-auth evidence.

## 2. Required outcome

Implement the smallest static-only production fix that:

1. discovers persisted OAuth/account-auth identities structurally from
   `auth.json`, including nested singleton state and credential-pool OAuth
   rows;
2. fixes the demonstrated OpenAI/Codex false negative;
3. no longer depends on the fixed `OAUTH_FLOWS` roster as the primary
   existence model;
4. preserves existing `oauth:<id>` entity IDs and schema-v2 compatibility;
5. never emits secret-derived material;
6. makes static account-auth evidence **non-green / non-login-authoritative**
   in health reporting;
7. performs no Hermes import, subprocess, network call, credential resolution,
   refresh, or write.

OA1 is an inventory/evidence fix, not an auth health-check project.

## 3. Owner surface

Primary owner:

```text
scripts/integration-discover.py
```

Necessary adjacent owner:

```text
scripts/health-check-v2.py
```

because the current `oauth` primitive would otherwise turn new static
evidence into a false `healthy/logged in` verdict.

Allowed adjacent files:

- focused probes/tests;
- comments/docs needed to describe the semantics;
- `scripts/webhook.py` **only if** a changed health verdict cannot be rendered
  truthfully by its existing skipped/unknown handling. Prefer no webhook
  change: current schema-v2 rendering already treats skipped/unknown as
  non-green.

Do not widen into a general credential inventory.

## 4. Structural discovery rules

### 4.1 Provider-state evidence

Inspect `auth.json.providers` generically by provider/store key.

Recognize only credential shapes for which the structure itself provides
reasonable account/OAuth evidence.

At minimum support the demonstrated/current shapes:

```text
providers.<id>.access_token / refresh_token
providers.<id>.tokens.access_token / refresh_token
```

Do not serialize any value.

Do not assume an arbitrary `access_token` field proves OAuth when the
supported-tag taxonomy shows that shape can be ambiguous. Prefer structural
signals such as refresh-token/account-token grouping.

If a supported-tag provider uses an access-token-only singleton shape that
would regress when the fixed roster is removed, a **minimal, explicitly named
compatibility exception** is allowed only when:

- exact-tag source evidence demonstrates the exception is necessary;
- it is documented as compatibility, not the new discovery architecture;
- it has a focused regression fixture.

Do not replace `OAUTH_FLOWS` with a larger hard-coded provider roster.

### 4.2 Credential-pool evidence

Inspect `auth.json.credential_pool` generically by store key.

Strong pool evidence:

```text
persisted auth_type == "oauth"
```

Bounded legacy compatibility:

```text
auth_type absent
AND a non-empty refresh_token field is structurally present
```

may count as weak OAuth/account evidence if the implementation keeps the
result conservative and a focused fixture proves the intended case.

Explicit `auth_type == "api_key"` rows are **OUT OF OA1 scope** and must not
be emitted as `oauth:*` entities. OA0 documented them as a broader persisted
credential universe, but the current product defect is account/OAuth
visibility. Expanding all API-key pool rows would create a new credential
inventory feature and duplicate existing provider/env discovery.

Malformed/non-list pool sections and malformed rows must be ignored safely,
not crash discovery.

### 4.3 Identity and deduplication

Entity identity remains:

```text
oauth:<store-provider-id>
```

Use the provider/store key as the identity. Do not import Hermes alias
normalizers.

When the **same exact id** has evidence in both `providers` and
`credential_pool`, emit one entity.

Do not emit source/provenance fields whose value can oscillate between
singleton and pool and create noisy `changed` events. The entity should stay
stable when an identity moves between equivalent static storage surfaces.

Known alias drift such as `xai` vs `xai-oauth` is not solved here. Do not
invent a hard-coded alias map in OA1. Record any duplicate/raw-id observation
as a bounded known limitation for later R2c/MP work.

### 4.4 Active marker

Preserve the existing `active` field semantics:

```text
active = auth.json.active_provider == entity provider id
```

This is static selection metadata only.

It must never be described as proof that the provider is logged in, usable or
healthy.

### 4.5 Copilot compatibility

Preserve current Copilot behavior unless a concrete OA1 regression requires a
local adjustment:

- `COPILOT_GITHUB_TOKEN` -> existing `oauth:copilot`;
- plain `GH_TOKEN` / `GITHUB_TOKEN` -> existing `pat-only` state.

Do not fold Copilot external/keychain discovery into the generic auth-store
reader.

## 5. Snapshot output semantics

Keep the existing entity type and id family for compatibility:

```json
{
  "type": "oauth",
  "name": "<provider-id>",
  "active": false
}
```

Avoid adding unstable fields merely because OA0 observed them.

In particular do not emit:

- access_token;
- refresh_token;
- agent_key;
- secret_fingerprint;
- token preview;
- credential id/label;
- account email;
- expiry/last-refresh timestamps;
- source path containing private/user-specific data;
- cooldown timestamps/status as an Argus verdict.

The JSON parser necessarily materializes `auth.json` values in the local
process; OA1's security property is that no secret value or derivative is
copied into Argus state, events, logs, tests, PR receipts, or child argv.

## 6. Health/report semantic correction

This is required acceptance, not optional cleanup.

For an ordinary static `oauth` entity:

- do **not** return `ok`;
- do **not** say `logged in`;
- do **not** infer health from token presence/expiry.

Use the smallest schema-v2-compatible non-green projection already supported by
the report/UI. The preferred minimum is:

```text
status: skipped
detail: persisted credential evidence present; login/health not verified
```

or an equivalently truthful existing-schema result.

Keep the special Copilot `pat-only` case `unconfigured`.

The quick/full integration renderers must not turn evidence-only OAuth rows into
an all-green report. Existing schema-v2 skipped/unknown rendering should be
reused where possible.

Do not create a new auth network primitive.

## 7. Required fixtures / acceptance tests

At minimum prove all of the following with synthetic credentials only.

### Discovery

1. **flat positive control** — existing supported flat OAuth state remains
   visible with the same entity id;
2. **nested Codex singleton** — `providers.openai-codex.tokens.*` produces
   `oauth:openai-codex`;
3. **pool-only Codex** — `credential_pool.openai-codex[]` with
   `auth_type=oauth` produces `oauth:openai-codex`;
4. **future/generic pool provider** — an arbitrary synthetic provider id with
   `auth_type=oauth` is discovered without adding the id to production code;
5. **same-id dedupe** — singleton + pool evidence for the same provider emits
   one entity;
6. **storage-shape stability** — moving the same provider identity from
   singleton-only to pool-only does not create a changed entity merely because
   provenance changed;
7. **api-key negative control** — `auth_type=api_key` pool rows do not become
   `oauth:*`;
8. **malformed pool rows** — wrong types/partial rows do not crash discovery;
9. **Copilot compatibility** — current token vs PAT-only behavior remains;
10. **active marker** — exact-id `active_provider` behavior remains static and
    deterministic.

### Secret boundary

Use unmistakable canaries in:

- singleton access/refresh values;
- pool access/refresh values;
- secret_fingerprint;
- credential label/id where fixtures include them.

Assert none of those canaries appears in:

- snapshot JSON;
- diff events/report;
- stdout;
- stderr.

Do not merely assert that a known field is absent; scan the produced artifacts
for the canary values.

### Health semantics

11. a discovered static account-auth entity does **not** increment canonical
    `healthy`;
12. its detail does not contain `logged in`;
13. its canonical report is non-green (skipped/unknown according to the chosen
    existing projection);
14. `pat-only` remains unconfigured;
15. the quick report cannot render "всё в порядке" solely because static OAuth
    evidence exists.

### Standard suite

- `python3 tests/probes.py`;
- syntax/static checks used by CI;
- `git diff --check`;
- `argus-ci` green.

## 8. No network / no Hermes execution proof

OA1 must remain static by construction.

Review the changed path and tests for:

- no `hermes` subprocess;
- no import from Hermes auth/provider modules;
- no HTTP call;
- no token refresh;
- no `auth.json` write;
- no external CLI/keychain/file probing.

A unit/fixture proof is enough. Do not revive C0 effect-tracing infrastructure.

## 9. Explicit non-goals

OA1 does **not**:

- implement OA2 or call `GET /api/providers/oauth`;
- add a generic credential inventory for `auth_type=api_key` pool rows;
- read Codex/Qwen/Claude/Copilot external CLI files;
- inspect OS keychains;
- inspect Vertex ADC, Bedrock IAM or Entra ID chains;
- normalize provider aliases;
- rename `oauth` entities or migrate schema-v2;
- implement multi-profile discovery;
- change fallback tracking;
- implement R1c/R2a/R2c work;
- validate credentials;
- refresh tokens;
- claim "all Hermes auth everywhere".

The delivered product claim is narrower:

> Argus generically sees persisted account/OAuth evidence in Hermes'
> `providers` and `credential_pool` store surfaces, including Codex, without
> claiming runtime login or health.

## 10. Pytna review focus

Review the exact committed OA1 head.

High-value failure modes:

1. Codex still missing from nested or pool-only fixtures;
2. new provider ids still require editing a hard-coded roster;
3. an `api_key` pool row is misclassified as OAuth;
4. source/provenance changes create noisy entity diffs;
5. secret values/fingerprints/labels leak into output or logs;
6. a static auth row still becomes `healthy` / "logged in";
7. Copilot PAT-only semantics regress;
8. malformed auth structures crash discovery;
9. implementation imports/calls Hermes or touches the network;
10. alias handling grows into a provider-normalization subsystem.

Use focused mutation tests when they directly demonstrate one of those failures.

Do not request:

- generic credential adapters;
- external CLI/keychain coverage;
- OA2 shadow polling;
- all API-key pool rows;
- schema rename;
- multi-profile work;
- malicious same-user/plugin defenses.

Default workflow remains one implementation pass -> one focused review -> at
most one remediation by default -> exact-head reread.

If a second remediation is needed, STOP to maintainer unless explicitly
authorized.

## 11. ZCode receipt

```markdown
# OA1 outcome

## Exact baseline/head

## Structural discovery rules
- provider-state:
- pool:
- compatibility exception(s), if any:

## Changed files

## Entity shape / stability

## Health semantic correction

## Tests
- nested singleton:
- pool-only:
- generic future id:
- api-key negative:
- dedupe/storage-shape stability:
- secret canary scan:
- health non-green:
- full probes/CI:

## No-effects review
- Hermes imports:
- subprocess:
- network:
- auth-store writes:

## Known limitations
- aliases:
- external stores/chains:

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR PYTNA | BLOCKED
```

## 12. Pytna receipt

```markdown
# OA1 review

## Exact head reviewed

## Acceptance criteria

## Findings
- P1/P2/P3 only for concrete OA1 failures

## Mutation / negative controls

## Secret boundary

## Health false-green check

## Scope review

## Recommendation
PASS-TO-MERGE | REMEDIATE | BLOCKED-FOR-MAINTAINER
```
