# Handoffs and implementation contracts

This directory contains both active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-20

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- (none yet — R1c contract to be authored when the maintainer selects the task)

Completed:

- R1a deploy/GitHub-heartbeat secret-in-argv — **DONE / PR #29**
- R1b Telegram child-argv secret exposure — **DONE / PR #31**
- OA0 account-auth research — **DONE / PR #33 / STATIC ONLY**
- OA1 generic static account-auth discovery — **DONE / PR #35**
- OA1b OAuth evidence rendering — **DONE / PR #39**
- OA-close acceptance — **DONE / OA PHASE COMPLETE**

OA phase:

```text
OA0 DONE
OA1 DONE
OA1b DONE
OA-close DONE
OA2 CLOSED / UPSTREAM-GATED

OA PHASE COMPLETE
 -> R1c (next)
```

Queued after the OA phase:

- R1c demonstrated non-Telegram Authorization-header argv debt;
- R2a malformed YAML;
- R2c bounded static compatibility excluding account-auth;
- R3 stabilization/reduction.

Deferred:

- `r2b-gateway-liveness-contract.md`

## OA1 accepted baseline

```text
reviewed PR head = abb7ceecd805fe4c4ffc1f90248a562be88de051
merged main      = cfa6c535518e3d3ad9b78c20d442335f48e84fd6
PR #35           = merged
CI #61           = success
```

The four changed file blobs are identical between reviewed PR head and merged
main.

OA1 preserves the required semantic boundary:

```text
persisted credential evidence present
!= logged in
!= healthy
```

Static account-auth entities now project to a non-green skipped result; Copilot
PAT-only remains unconfigured.

## OA1b accepted baseline

```text
reviewed head = a58075f7cbf21dc2b629e71749dadbe2b3e8972f (PASS-TO-MERGE,
verification run_607ed84e)
merged main   = 12739f8c4fbd597606653281a6c4b1898a2b00a4
PR #39        = merged
probes        = 109 pass / 0 fail
```

OAuth auth-evidence renders as informational
(`🔐 … — учётные данные обнаружены · runtime-статус не проверяется`) in both
bot views; generic skipped rows keep `⏸`; the full-view 4000-character cap
cuts whole lines and never drops failure/unknown rows or the OAuth evidence
block (red-capable probes committed).

## OA2 status

OA2 is closed and upstream-gated.

See:

```text
oa2-hermes-status-shadow-reopen-gate.md
```

Latest stable remains Hermes v0.21.3 / `v2026.9.14`. Fresh main is
`00570550f37e9082676955d50f65c7d9ba846cc9` (+927 since the previous watch);
`auth_codex.py` / `web_routers/oauth.py` changed upstream (partial refresh-free
improvement for nous listing), but `token_preview`, refresh and persist paths
remain and no stable release satisfies the reopen conditions. OA2 remains
closed.

## Current contracts

Current:

- (none yet — R1c contract to be authored when the maintainer selects the task)

Completed:

- `oa-close-account-auth-acceptance-contract.md`
- `oa1b-oauth-evidence-rendering-contract.md`
- `oa1-static-account-auth-discovery-contract.md`
- `oa0-account-auth-discovery-research-contract.md`
- R1a/R1b contracts

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

Queued:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

## Workflow

```text
one selected contract
 -> one implementation/research/acceptance pass
 -> one focused review
 -> at most one remediation by default
 -> exact-tree reread
 -> merge/decision OR blocker
```

Closeout and acceptance passes stay docs/acceptance only. If they discover a
functional regression, stop and return it to the maintainer instead of
silently turning an acceptance pass into another implementation PR.

Before merge recommendation, refresh the PR body/evidence receipt to the exact
candidate head.
