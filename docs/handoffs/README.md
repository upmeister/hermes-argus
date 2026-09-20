# Handoffs and implementation contracts

This directory contains active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-21

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `r2c-static-discovery-compat-contract.md` — **R2c.1 NOW / READY**

Completed:

- R1a — **DONE / PR #29**
- R1b — **DONE / PR #31**
- R1c — **DONE / PR #42**
- R2a malformed YAML fail-safe — **DONE / PR #44**
- OA0/OA1/OA1b/OA-close — **COMPLETE**

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

## R2a accepted baseline

```text
candidate head = 6241543d96e93cfbe197706dcbf316fbbc72b58d
merged main    = 7b78e9369be72d9a5f08de267ccfc62604710f79
CI #86         = success
probes         = 131 pass / 0 fail
swap tests     = 8 pass / 0 fail
```

All six changed blobs match candidate and merged main. One P1 and one P2 from
Pytna were fixed in the single remediation.

## Release-oriented execution order

```text
R1c DONE
 -> R2a DONE
 -> R2c.1 NOW
 -> RR0 legacy/personal-dependency reduction
 -> RR1 installer/dependency/managed-cron
 -> RR2 runtime i18n: en + ru
 -> RR3 release acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0
```

Post-RC:

- R2c.2 bounded auxiliary coverage;
- low-risk archive/docs cleanup.

Deferred/separate:

- R2b gateway-liveness redesign;
- MP0-MP5 multi-profile track;
- OA2 dynamic account-status shadow.

## Current upstream authority

```text
Hermes stable = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
warning-source main = 64c7da592d43a9f155ea8606865d9ae1eda3222b
```

Stable itself confirms R2c.1 semantics:
`fallback_providers` ordered first, legacy `fallback_model` appended with
route dedupe.

## Current contracts

Current:

- `r2c-static-discovery-compat-contract.md` — R2c.1 only

Queued:

- RR0 contracts — to be split from
  `docs/research/2026-09-21-pre-release-legacy-audit.md` after R2c.1

Completed:

- `r2a-malformed-yaml-contract.md`
- `r1c-authorization-header-argv-contract.md`
- OA contracts

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

## Workflow

```text
one selected contract
 -> one implementation/research pass
 -> one focused review
 -> at most one remediation by default
 -> exact-head reread
 -> merge/decision OR blocker
```

Out-of-scope review findings are recorded, not automatically implemented.
