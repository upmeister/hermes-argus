# OA0 contract — research generic Hermes account-auth discovery

Status: **NOW / RESEARCH ONLY — NO PRODUCTION IMPLEMENTATION**

Baseline:

```text
hermes-argus main = 2238928c64b9751a0cb5c8be33b7765c5c228dfd
R1b / PR #31 = DONE / MERGED
supported Hermes stable target = v2026.9.14 / Hermes Agent v0.21.3
```

Fresh Hermes `main` may be inspected as an early-warning source, but it is not the compatibility authority for this research.

Read first:

1. repository `AGENTS.md`;
2. `docs/handoffs/2026-09-17-next-steps-execution-baseline.md`;
3. this contract;
4. current `scripts/integration-discover.py`;
5. upstream Hermes auth/provider sources at the exact supported tag;
6. current project roadmap/instructions supplied by the maintainer.

## 1. Problem

Argus currently has a hard-coded OAuth flow list and assumes configured OAuth state is represented by:

```text
auth.json.providers.<provider>.access_token
```

That assumption is already false for a currently used provider.

Current Hermes Codex auth can be represented under:

```text
providers.openai-codex.tokens.*
credential_pool.openai-codex[]
```

while current Argus checks only a flat `access_token` field. The result is a user-visible false negative: a working primary OpenAI/Codex account can be absent from Argus integration discovery.

This is sufficient evidence to promote auth discovery from the old R2c.3 "audit only if needed" note into a dedicated research track.

## 2. Research question

Find the smallest durable way for Argus to answer:

> Which Hermes model/account authentication providers are configured or connected?

without recreating Hermes credential resolution.

OA0 must determine whether future implementation should use:

```text
A. generic static auth-store structure only
B. static structure + a Hermes-owned external status seam
C. neither, because the available seams are too side-effectful or unstable
```

OA0 does **not** implement the winning design.

## 3. Scope: what "all OAuth" means here

In scope:

- model/inference account providers;
- account-style auth used by provider selection;
- singleton provider auth state;
- credential-pool auth state;
- externally managed account providers only insofar as Hermes itself includes them in its provider/account catalog.

Out of scope for OA0:

- MCP OAuth;
- Spotify/tool OAuth;
- memory-provider OAuth;
- dashboard/user identity;
- connector/session auth;
- arbitrary third-party OAuth files unrelated to model/provider selection;
- multi-profile implementation.

Do not flatten every OAuth-shaped thing in Hermes into one Argus entity class.

Also distinguish:

```text
OAuth as the login/acquisition flow
!=
OAuth as the persisted/runtime credential type
```

For example, a provider may use OAuth/PKCE to obtain a credential that Hermes subsequently treats as a normal API-key pool entry. OA0 should classify the runtime/provider-auth semantics Hermes exposes, not merely the historical acquisition method.

## 4. Known evidence to reproduce, not assume

The research must independently verify against the exact supported Hermes tag:

### Argus today

Current `scripts/integration-discover.py` contains:

- a fixed `OAUTH_FLOWS` tuple;
- static `auth.json` reading;
- detection of `providers.<flow>.access_token`;
- separate Copilot env-key handling.

### Hermes Codex

Verify the current supported-tag storage and read paths for OpenAI/Codex, including:

- singleton provider state shape;
- credential-pool shape;
- which form is authoritative/preferred for status;
- whether pool-only credentials are considered logged in/configured.

### Hermes provider/account catalog

Verify whether `GET /api/providers/oauth` exists in the supported tag and document:

- how its provider universe is built;
- whether plugin-added account providers can enter the list;
- response fields;
- profile parameter behavior if present;
- how status is computed per provider;
- authentication/access requirements for a local caller.

Do not treat a docstring as sufficient proof of side-effect behavior.

## 5. Static auth-store taxonomy

Build a compact taxonomy of persisted model/account auth evidence that Argus could inspect without importing Hermes.

At minimum investigate these shapes where they exist:

```text
providers.<id>.access_token
providers.<id>.refresh_token
providers.<id>.tokens.access_token
providers.<id>.tokens.refresh_token

credential_pool.<id>[]
  auth_type
  access_token
  refresh_token
  source
```

Also identify important account providers whose authoritative state lives outside those shapes, such as provider-owned/external files or CLIs.

For every shape/provider class, record:

```text
provider/example
supported-tag storage path
does identity survive without reading secret values?
generic structural rule possible?
false-positive risk
false-negative risk
would OA1 need provider-specific knowledge?
```

The desired OA1 direction is structural discovery by provider id and credential metadata, not another larger hard-coded provider list.

But do not force genericity if Hermes semantics make it unsafe or misleading; report the boundary.

## 6. Candidate static rule to evaluate

Evaluate, but do not implement, a rule of this form:

```text
provider-state evidence:
  any providers.<id> object containing recognized non-empty credential structure
  -> account-auth identity <id>

pool evidence:
  any credential_pool.<id> entry whose persisted metadata identifies account/OAuth auth
  -> account-auth identity <id>
```

Questions OA0 must answer:

1. Is `auth_type == "oauth"` sufficient for current pool rows?
2. Which legacy/current rows need bounded structural fallback such as presence of `refresh_token`?
3. Can `access_token` alone misclassify API-key-style credentials?
4. Can provider-state blocks remain after logout/revocation and create false positives?
5. Should Argus report `configured`, `connected`, or only `credential evidence present` from static data?
6. Which fields can be inspected without ever emitting/token-fingerprinting secret material?

OA0 must prefer conservative semantics. A static reader may say "credential evidence present" without claiming "healthy" or "logged in".

## 7. Hermes-owned candidate seam: /api/providers/oauth

Research this as a possible **external enrichment/status seam**, not as pre-approved production authority.

Key questions:

1. Is the endpoint present and stable in the supported tag?
2. Does it represent the same model/account provider universe relevant to Argus?
3. Does it include OpenAI/Codex correctly for:
   - singleton auth state;
   - pool-only auth state?
4. Does it include plugin-added account providers?
5. Is it profile-aware in a way that could later help MP0 without implementing profiles now?
6. Is a local non-interactive Argus caller able to access it using an existing supported authentication path?
7. What exact fields are safe/useful to retain?
8. Most importantly: can repeated GETs cause:
   - token refresh;
   - auth-store writes;
   - provider/plugin execution with side effects;
   - external network access;
   - credential materialization?

The endpoint is not accepted merely because it is HTTP.

## 8. Side-effect proof

OA0 must distinguish **source evidence** from **empirical evidence**.

### Source audit

Trace the supported-tag call path for the GET endpoint far enough to identify:

- provider catalog construction;
- status dispatch;
- special provider status helpers;
- generic fallback status helpers;
- plugin/provider loading involved in catalog construction.

Record any path that can perform network, write auth state, refresh a token, or spawn a subprocess.

### Isolated empirical probe

Use a throwaway `HERMES_HOME` / isolated fixture with synthetic credentials only.

A bounded probe may:

- start the minimum real Hermes surface required to call the endpoint, or use the upstream route/test harness if that is the faithful supported seam;
- hash/snapshot the throwaway auth/config state before and after repeated reads;
- use local/synthetic provider fixtures;
- observe whether external network attempts occur using a simple local fixture/deny-by-construction method.

Do **not** build a sandbox, syscall monitor, seccomp policy, audit-hook security boundary, or generalized effect-observation framework.

If a side-effect property cannot be proven cheaply and directly, mark it unknown.

### Production evidence

Read-only production observation may be recorded only if the maintainer/agent already has authorized access and no mutation/login/refresh action is needed.

Never print or copy real token values into research output.

OA0 does not authorize production configuration changes, logout/login, credential rotation, restarts, or enabling new services.

## 9. Compare candidate seams

Produce a decision table covering at least:

| Candidate | Completeness | Side-effect risk | Secret exposure | Plugin/future provider coverage | Profile fit | Maintenance cost | Verdict |
|---|---|---|---|---|---|---|---|
| current hard-coded static list | | | | | | | |
| generic static auth.json structure | | | | | | | |
| `GET /api/providers/oauth` | | | | | | | |
| `hermes auth list` | | | | | | | |
| `GET /api/credentials/pool` | | | | | | | |
| importing Hermes auth/provider internals | | | | | | | |

The purpose is not to find the richest interface. It is to find the smallest interface that gives useful truthful monitoring with low maintenance.

## 10. Required OA0 decision

End the research with exactly one primary recommendation:

### `STATIC ONLY`

Choose when generic static structure covers the product need and the Hermes status seam has unacceptable or unproven effects/coupling.

Expected next task:

```text
OA1 — implement generic structural auth discovery
```

### `STATIC + HERMES STATUS SHADOW`

Choose when generic static structure is safe as the baseline and the external Hermes seam is sufficiently bounded to compare/enrich without becoming the sole source of existence.

Expected next tasks:

```text
OA1 — generic structural auth discovery
OA2 — bounded shadow comparison / enrichment experiment
```

### `BLOCKED / NEEDS UPSTREAM SEAM`

Choose only if neither option can truthfully solve the demonstrated gap within Argus's architecture boundary.

Do not invent a runtime-import bridge as the fallback.

## 11. Expected future entity semantics

OA0 should recommend the minimum semantics, not redesign schema-v2.

Preferred distinction:

```text
static evidence -> configured / credential evidence present
Hermes status   -> connected/logged_in status when proven safe
health checks   -> actual usable/healthy verdict
```

Do not make credential presence equal health.

Do not emit:

- access tokens;
- refresh tokens;
- token previews;
- token fingerprints;
- account email;
- credential ids/labels unless a later product need is separately approved;
- rapidly rotating expiry timestamps that create noisy integration diffs.

If the existing entity name `oauth` is semantically imperfect, record that as schema debt. OA0 does not authorize a rename/migration.

## 12. OA0 deliverables — ZCode

OA0 is research-only. The deliverable should be a committed research report, preferably under `docs/research/` or another existing non-production documentation area approved by repository conventions.

Return:

```markdown
# OA0 outcome

## Exact baselines
- Argus main:
- Hermes stable tag + resolved SHA:
- Hermes main observed SHA (warning only):

## Demonstrated Argus gap
- current parser assumption:
- Codex actual supported-tag shapes:
- why current detection misses it:

## Scope definition
- model/account auth in scope:
- excluded OAuth domains:

## Hermes auth storage taxonomy
| provider/class | singleton shape | pool shape | external source | static generic rule? | notes |

## /api/providers/oauth seam
- supported tag:
- provider-universe construction:
- status dispatch:
- access/auth requirements:
- profile behavior:
- plugin behavior:

## Side-effect analysis
### source audit
### isolated empirical probe
### unknowns

## Candidate comparison
| candidate | completeness | effects | maintenance | recommendation |

## Proposed OA1 semantics
- what static discovery may claim:
- structural rules:
- secret fields explicitly discarded:
- known misses:

## OA2 gate
- safe enough for shadow? yes/no
- exact whitelisted fields:
- polling/usage constraints:
- stop conditions:

## Decision
STATIC ONLY | STATIC + HERMES STATUS SHADOW | BLOCKED / NEEDS UPSTREAM SEAM

## Out-of-scope findings

## Production actions
No production mutation performed.

## Recommendation for next contract
```

Do not submit an OA1 implementation in the OA0 research PR.

## 13. Review instructions — Pytna

Review the exact committed OA0 research head.

Challenge concrete claims:

1. Is the Codex false-negative mechanism demonstrated from exact supported-tag source/state?
2. Does the storage taxonomy miss a current model/account credential class that changes the decision?
3. Does the proposed static rule confuse credential presence with login/health?
4. Are legacy structural heuristics broad enough to create obvious false positives?
5. Does the endpoint side-effect analysis actually follow its status helpers/plugin catalog path?
6. Does any empirical probe prove the property claimed, or only a weaker fixture?
7. Does the recommendation reintroduce internal Hermes imports/plugin execution into production?
8. Is any real secret copied into the report/tests?
9. Did OA0 accidentally expand into MCP/tool/memory OAuth or multi-profile implementation?

Pytna may request a focused additional fixture/source check when it changes the OA0 decision.

Pytna must not request:

- a universal credential framework;
- adversarial same-user plugin sandboxing;
- full Hermes auth reimplementation;
- exhaustive coverage of every OAuth domain;
- OA1 production code as part of OA0;
- multi-profile implementation.

Default workflow remains one focused review and at most one remediation unless the maintainer explicitly authorizes another.

## 14. Stop conditions

STOP and return to the maintainer if OA0 starts requiring:

- a production Hermes runtime-import bridge;
- credential resolution/refresh to discover identity;
- real account login/logout;
- credential rotation;
- a sandbox/security-emulation subsystem;
- a new daemon/service;
- schema migration;
- MCP/tool/memory OAuth expansion;
- multi-profile implementation;
- broad upstream pin/compatibility machinery.

Research may inspect upstream internals and use isolated throwaway Hermes execution to understand them. That does not authorize those internals as an Argus production dependency.

## 15. Non-goals

OA0 does not:

- fix R1c Authorization-header argv leaks;
- implement malformed-YAML handling;
- implement `fallback_providers`;
- change fallback tracking;
- change Argus notification behavior;
- implement profiles;
- replace static integration discovery;
- promise support for every future Hermes provider automatically.

The result should narrow the next implementation, not create a new platform.
