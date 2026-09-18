# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-19**

This document translates the stabilization roadmap into bounded repository work. Agents may perform only the named task currently assigned by the maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Prefer:

1. proven stable external status owned by Hermes;
2. static user-visible configuration/state;
3. stable Hermes CLI output where no machine interface exists;
4. logs already required for product behavior.

Do not introduce a Hermes runtime-import bridge.

## Exact current baseline

```text
Argus main = c8c3b66c26913481e2fef54195678490f2a96e96
OA0 / PR #33 = merged
OA0 decision = STATIC ONLY

Hermes stable authority = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d

2026-09-19 upstream warning source:
Hermes main = 1e4952ddba1bc585416ad43438d60183380035cd
latest stable remains v2026.9.14
```

## Current execution order

```text
OA1 generic static account-auth discovery     NOW
 -> OA-close exact-main acceptance
 -> OA PHASE COMPLETE

OA2 Hermes status shadow                      CLOSED / UPSTREAM-GATED

then:
R1c Authorization-header argv debt
 -> R2a malformed YAML
 -> R2c bounded static compatibility
 -> R3 cleanup/stabilization
```

R2b gateway liveness remains deferred.

Multi-profile remains separate.

## OA0 decision now authoritative

PR #33 demonstrated:

- working OpenAI/Codex can be invisible to current Argus;
- nested `providers.<id>.tokens.*` and OAuth `credential_pool.<id>[]` are
  useful static evidence surfaces;
- static evidence can be stale and cannot prove login/health;
- `GET /api/providers/oauth` is not suitable for Argus polling on supported
  v0.21.3;
- OA production direction is `STATIC ONLY`.

Research report:

```text
docs/research/oa0-account-auth-discovery-research.md
```

## 2026-09-19 upstream watch

Latest stable remains v0.21.3, so the supported compatibility authority did
not move.

Fresh `main` is 602 commits ahead of the OA0-observed `d177b119...` and
partially improves one OA2 blocker:

- pool-first OAuth status now uses credential-pool `peek()` as an observation
  and explicitly avoids the older select/bench behavior.

OA2 still stays closed because on fresh `main`:

- Codex status can still reach `resolve_codex_runtime_credentials()`;
- expiring Codex credentials can still refresh and successful refresh persists
  rotated tokens;
- Qwen status still refresh-validates;
- OAuth responses still include `token_preview`;
- `/api/providers/oauth` is still not registered on the machine bearer-token
  route;
- plugin/account provider universe remains bounded by upstream catalog rules.

Other Argus external seams remain intact:

- fallback activation marker unchanged;
- primary restore marker unchanged;
- `hermes mcp test` still prints `Connected (...ms)` and
  `Tools discovered: N`.

Fresh `main` also added credential-pool reclaim behavior for live sessions
after quota cooldown, reinforcing that cooldown state is Hermes runtime state,
not an Argus health verdict.

## Current selected contract

```text
docs/handoffs/oa1-static-account-auth-discovery-contract.md
```

OA1 is the only authorized production task.

## OA1 ownership

Primary:

```text
scripts/integration-discover.py
```

Necessary adjacent surface:

```text
scripts/health-check-v2.py
```

Reason: current health code turns every static `oauth` snapshot entity into
`ok / logged in`. Extending discovery without correcting that projection
would create new false greens and directly violate OA0.

Preferred health projection for evidence-only OAuth rows is an existing
schema-v2 non-green result such as `skipped`, with a truthful detail that
login/health is not verified.

## OA1 product boundary

OA1 should:

- detect provider-state flat/nested OAuth evidence;
- detect generic pool rows with persisted `auth_type=oauth`;
- preserve a bounded legacy fallback only where justified;
- preserve `oauth:<id>` identity and existing Copilot behavior;
- keep equivalent singleton/pool storage movement from creating noisy changes;
- emit no secret-derived fields;
- keep static auth evidence non-green.

OA1 should not:

- ingest `auth_type=api_key` pool rows into `oauth:*`;
- read external CLI/keychain/cloud credential stores;
- normalize provider aliases;
- rename/migrate schema-v2;
- call Hermes, network or OAuth endpoints;
- implement OA2;
- implement profiles.

## OA2 authority

OA2 is not queued implementation.

Use:

```text
docs/handoffs/oa2-hermes-status-shadow-reopen-gate.md
```

It may be reconsidered only after a stable/tagged upstream version satisfies
the documented refresh-free/no-write/no-network, headless-auth and no-secret
response conditions.

## OA closeout

After OA1 merges, run:

```text
docs/handoffs/oa-close-account-auth-acceptance-contract.md
```

Closeout is expected to be docs/acceptance only. It does not authorize a second
auth implementation project.

Successful closeout sets R1c as the next selected task.

## Global non-goals

- runtime bridge revival;
- provider/plugin execution for discovery;
- credential resolution or refresh in Argus;
- universal credential inventory;
- external CLI/keychain/cloud auth probing;
- generalized auth adapter framework;
- OA2 polling;
- multi-profile implementation inside OA1;
- gateway timestamp liveness revival.

## Required agent loop

```text
one assigned contract
 -> one implementation pass
 -> focused tests
 -> one focused adversarial review
 -> at most one remediation by default
 -> exact-head reread
 -> merge recommendation OR blocker
```

Out-of-scope findings are recorded, not automatically fixed.

## Evidence rule

Every implementation PR states:

```text
problem -> evidence -> smallest patch -> preserved semantics -> explicit non-goals
```

For OA1, tests must specifically prove the secret boundary and the
non-green/static-evidence health semantics, not just entity appearance.

Before merge recommendation, refresh the PR body to the exact candidate head.

## Canonical task contracts

Current:

- `oa1-static-account-auth-discovery-contract.md`

After OA1:

- `oa-close-account-auth-acceptance-contract.md`

Closed:

- `oa2-hermes-status-shadow-reopen-gate.md`

Completed:

- `oa0-account-auth-discovery-research-contract.md`
- R1 contracts

Queued:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md`
