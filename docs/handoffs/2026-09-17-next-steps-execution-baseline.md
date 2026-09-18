# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-19**

This document translates the stabilization roadmap into bounded repository
work. Agents may perform only the named task currently assigned by the
maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Do not introduce a Hermes runtime-import bridge to improve discovery.

## Exact current baseline

```text
Argus main = cfa6c535518e3d3ad9b78c20d442335f48e84fd6

R1a / PR #29 = DONE
R1b / PR #31 = DONE
OA0 / PR #33 = DONE / STATIC ONLY
OA1 / PR #35 = DONE / MERGED

OA1 reviewed head = abb7ceecd805fe4c4ffc1f90248a562be88de051
OA1 CI run #61 = SUCCESS
```

All four OA1 changed file blobs match exactly between the reviewed PR head and
merged main.

Supported Hermes authority:

```text
v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
```

2026-09-19 warning-source watch:

```text
Hermes main = 03c9fc892f5cf3f2e02aa4a4888a30ae292d256d
latest stable remains v2026.9.14
```

The account-auth/OAuth router/provider catalog/dashboard token-auth sources
relevant to OA2 are unchanged from the previous
`1e4952ddba1bc585416ad43438d60183380035cd` watch. OA2 is still closed.

## Current execution order

```text
OA1b OAuth evidence rendering                NOW
 -> OA-close exact-main acceptance
 -> OA PHASE COMPLETE
 -> R1c Authorization-header argv debt
 -> R2a malformed YAML
 -> R2c bounded static compatibility
 -> R3 cleanup/stabilization

OA2 Hermes status shadow                     CLOSED / UPSTREAM-GATED
R2b gateway liveness                         DEFERRED
MP*                                           SEPARATE
```

## OA1 final maintainer gate

OA1 is accepted.

Verified:

- structural identity discovery no longer depends on `OAUTH_FLOWS`;
- nested Codex singleton and pool-only Codex are covered;
- arbitrary synthetic OAuth pool id is covered without production roster edit;
- explicit `api_key`, unknown auth type and malformed rows do not enter
  `oauth:*`;
- same-id singleton/pool evidence produces a stable entity;
- secret canaries are scanned across snapshot/report/stdout/stderr and health
  output;
- static auth evidence is `skipped`, not `healthy / logged in`;
- Copilot PAT-only remains `unconfigured`;
- no Hermes/network/refresh/write dependency was introduced;
- PR-head CI static checks and regression probes passed.

One non-blocking P3 documentation nit remains: `run_check()`'s docstring still
lists only `ok | fail | unconfigured` even though `skipped` is now a valid
return. Do not open an OA1 remediation only for this line; fix opportunistically
when that function is next touched.

## Current selected contract

```text
docs/handoffs/oa1b-oauth-evidence-rendering-contract.md
```

OA-close is paused pending OA1b. Production confirmed that the conservative
`skipped` verdict is rendered misleadingly as bare "пропущено" for OAuth
evidence. OA1b fixes only presentation; canonical health semantics remain
unchanged.

## OA-close acceptance

Required outcome:

1. re-read exact merged main;
2. run the focused OA1 acceptance fixtures and full regression suite against
   that exact tree;
3. confirm secret-canary and false-green properties;
4. confirm OA2 reopen gate remains closed under latest stable/upstream watch;
5. update authority docs to:
   `OA PHASE COMPLETE -> R1c`.

If any functional OA1 acceptance item fails, stop and return an OA1 regression
to the maintainer. Do not silently patch production code inside closeout.

No production deploy/restart/login/logout/credential mutation is authorized.

## OA2 authority

Use:

```text
docs/handoffs/oa2-hermes-status-shadow-reopen-gate.md
```

OA2 requires a stable/tagged refresh-free, no-write/no-provider-network,
headless-authenticated, no-secret status seam before it may be reopened.

## Global non-goals

- runtime bridge revival;
- OA2 polling;
- auth validation/refresh;
- universal credential inventory;
- external CLI/keychain/cloud auth probing;
- schema rename;
- provider alias normalization;
- multi-profile implementation in OA-close;
- unrelated cleanup.

## Workflow

```text
one closeout pass
 -> exact-main evidence
 -> one focused review
 -> docs-only completion OR blocker
```

If closeout requires production code, stop to maintainer.

## Canonical contracts

Current:

- `oa-close-account-auth-acceptance-contract.md`

Completed:

- `oa1-static-account-auth-discovery-contract.md`
- `oa0-account-auth-discovery-research-contract.md`

Closed:

- `oa2-hermes-status-shadow-reopen-gate.md`

Queued:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

## OA1b production finding

Observed after deploy:

```text
⏸ oauth nous — пропущено
⏸ oauth openai-codex — пропущено
```

This is not an auth failure. It is a renderer bug: OAuth persisted evidence is
correctly canonical `skipped` because runtime health is unverified, but the
bot displays the generic skipped label without the evidence context.

Current contract:

```text
docs/handoffs/oa1b-oauth-evidence-rendering-contract.md
```

OA-close resumes only after OA1b passes.
