# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-18**

This document translates the stabilization roadmap into bounded repository work. It is deliberately narrower than a product roadmap: agents may perform only the named task currently assigned by the maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Prefer, in order:

1. stable externally observable status owned by Hermes when its semantics and effects are proven;
2. static user-visible configuration/state files;
3. stable Hermes CLI output where no machine-readable interface exists;
4. log events already required for Argus's product behavior.

Do not introduce a Hermes runtime-import bridge to make discovery more complete.

A proposed upstream seam must be verified against actual supported-version semantics before it becomes monitoring authority. The deferred `gateway_state.json.updated_at` liveness idea remains the cautionary example.

## Current execution order

```text
R1a deploy secret-in-argv                     DONE / PR #29
R1b Telegram child-argv secret exposure       DONE / PR #31

OA0 account-auth discovery research            NOW / RESEARCH ONLY
 -> maintainer decision
 -> OA1 generic structural auth discovery      FUTURE / NOT YET AUTHORIZED
 -> OA2 Hermes status shadow/enrichment        CONDITIONAL / NOT YET AUTHORIZED

then:
R1c demonstrated Authorization-header argv debt
 -> R2a malformed YAML degradation
 -> R2c bounded static discovery compatibility
 -> R3 cleanup/stabilization
```

Deferred:

```text
R2b gateway liveness redesign — research only until a stable external seam is proven
```

Multi-profile support is intentionally separate. OA0 may record profile-aware properties of a candidate Hermes seam because they affect future architectural fit, but must not implement profile monitoring.

## Why OA0 moved ahead of the queued fixes

Current Argus account-auth discovery has a demonstrated product false negative.

`scripts/integration-discover.py` uses a fixed `OAUTH_FLOWS` list and expects `auth.json.providers.<id>.access_token`.

Modern supported Hermes can store OpenAI/Codex auth under nested provider token state and/or `credential_pool.openai-codex`. Therefore a working primary Codex account can be absent from Argus integration inventory.

That concrete gap is more important to current integration correctness than the remaining queued cleanup fixes and is bounded enough for a research-first task.

OA0 is not permission to rebuild Hermes auth semantics. It exists to select the smallest durable observation seam.

## Task ownership map

| Task | Status | Primary owner/surface | Allowed adjacent surfaces |
|---|---|---|---|
| R1a deploy argv | DONE | `deploy.sh` | no follow-up without demonstrated regression |
| R1b Telegram argv | DONE | prior active notifier surfaces | no follow-up without demonstrated regression |
| OA0 account-auth discovery | NOW / RESEARCH | current Argus parser + exact supported Hermes auth/provider sources + isolated throwaway probes | research docs/fixtures only; no production parser implementation |
| OA1 generic static auth discovery | FUTURE | likely `scripts/integration-discover.py` | only after OA0 decision + separate contract |
| OA2 Hermes status shadow | CONDITIONAL | external Hermes status seam if OA0 proves it bounded | only after OA0 decision + separate contract |
| R1c auth-header argv | QUEUED | demonstrated active Authorization-header child argv paths | focused probes/docs; contract still to be written |
| R2a malformed YAML | QUEUED | `scripts/integration-discover.py` | wrapper/tests only if required |
| R2b gateway liveness | DEFERRED | research only | no implementation contract active |
| R2c fallback/static inventory | QUEUED | `scripts/integration-discover.py` | registry docs/generator wording; auth subsection superseded by OA track |
| R3 reduction | LATER | actual dead/duplicate paths | deletion/simplification preferred |

## Current selected contract

The only selected task is:

```text
docs/handoffs/oa0-account-auth-discovery-research-contract.md
```

OA0 is **research only**.

Do not implement OA1 or OA2 in the OA0 PR even if the research result appears obvious.

## OA0 boundary

The research question is:

```text
How should Argus discover all Hermes model/account authentication providers
without recreating Hermes credential resolution?
```

In scope:

- model/inference account providers;
- singleton auth state;
- credential-pool auth state;
- externally managed provider accounts insofar as Hermes includes them in its account/provider catalog;
- the supported-version `GET /api/providers/oauth` seam as a candidate external status source.

Out of scope:

- MCP OAuth;
- Spotify/tool OAuth;
- memory-provider OAuth;
- dashboard/user identity;
- connector/session auth;
- production runtime imports;
- token refresh;
- credential materialization;
- multi-profile implementation.

The research must distinguish static "credential evidence present" from Hermes "logged in/connected" status and from independent health.

## Global non-goals

The following are NOT implied by this baseline:

- C1/C1a/C1b runtime bridge revival;
- production provider/plugin imports for discovery;
- credential resolution or token refresh during Argus discovery;
- historical Hermes revision pinning;
- integrity/sandbox/worktree/interpreter verification;
- generalized notification transport framework;
- generalized auth adapter framework;
- multi-profile implementation inside OA/R1/R2;
- support for every Hermes auxiliary model role;
- flattening MCP/tool/memory OAuth into model-provider auth;
- replacing all static discovery with Hermes internals;
- treating `gateway_state.json.updated_at` freshness as a liveness contract without new evidence.

## R2c auth subsection

The prior R2c.3 credential/OAuth audit is superseded by OA0 because its premise ("no demonstrated current gap") is false.

R2c retains only its bounded fallback/auxiliary/registry responsibilities after the OA track and R2a.

Do not run a second independent auth-discovery design under R2c.

## Required agent loop

For OA0:

```text
one research contract
 -> exact-source audit
 -> bounded isolated probes
 -> one committed research report
 -> one focused adversarial review
 -> at most one remediation by default
 -> exact-head reread
 -> maintainer architecture decision
```

For later implementation tasks, the normal implementation loop remains unchanged.

A reviewer finding outside the assigned contract is recorded as a finding. It does not authorize fixing it.

If an additional remediation is genuinely required after the normal budget, STOP and request a maintainer decision with the exact blocker.

## Stop conditions

Stop and return to the maintainer if OA0 or a queued task requires:

- a new subsystem;
- a new dependency;
- a new persistent state format;
- broad changes outside the named owner surface;
- a second remediation cycle without explicit approval;
- execution/import of Hermes internals as a production dependency;
- credential resolution/refresh merely to discover provider identity;
- real account login/logout or credential rotation;
- a new security boundary/sandbox;
- redesign of discovery into a general compatibility framework.

Research-only isolated execution of the supported Hermes version is allowed when required to understand behavior. It does not authorize that mechanism for Argus production code.

## Evidence rule

Every task must state:

```text
problem -> evidence -> smallest useful seam -> preserved semantics -> explicit non-goals
```

OA0 must distinguish:

```text
source evidence
vs
isolated empirical evidence
vs
unknown/unproven behavior
```

Before final review, refresh the PR body/evidence receipt so it describes the exact candidate head and exact supported Hermes source revision used.

## Canonical task contracts

Current:

- `oa0-account-auth-discovery-research-contract.md`

Queued / future:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md` — auth subsection superseded by OA0
- OA1/OA2 contracts do not yet exist and are not authorized
- R1c contract does not yet exist

Completed/history:

- `r1-secret-in-argv-contract.md`
- `r1b-telegram-secret-argv-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

The maintainer must explicitly select one active contract before implementation begins.
