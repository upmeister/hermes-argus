# Handoffs and implementation contracts

This directory contains both active implementation contracts and historical handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-18

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `r1b-telegram-secret-argv-contract.md` — **NEXT / READY**

Queued after R1b:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md` — earlier `gateway_state.json.updated_at` migration direction was disproven by production/upstream evidence; research only until a stable external liveness seam is demonstrated.

Parent/history:

- `r1-secret-in-argv-contract.md` — original combined R1 contract; R1a is complete in PR #29 and R1b now has a dedicated contract.

An agent must not implement multiple contracts in one PR unless the maintainer explicitly combines them.

## Current execution order

```text
R1a  DONE / PR #29
 -> R1b Telegram shell argv
 -> R2a malformed YAML
 -> R2c bounded static discovery
 -> R3 stabilization/reduction
```

Multi-profile work remains a separate near-term product track and must not be pulled into these contracts.

## Historical / superseded

The following remain evidence only:

- `b1b-adr0002-agent-handoff.md`
- `b1b-adr0002-implementation-contract.md`
- `c0-runtime-bridge-zcode.md`
- `c1a-shadow-bridge-agent-handoff.md`
- `c1a-shadow-bridge-implementation-contract.md`

In particular, C1a/C1b runtime-bridge productionization is **superseded**. PR #27 was closed without merge on 2026-09-17 by architecture decision.

Do not interpret language inside historical documents such as “next step”, “ready”, “remediate”, or C1b authority-cutover instructions as current authorization.

## Agent workflow

```text
maintainer selects one active contract
 -> implementation
 -> focused review
 -> at most one remediation by default
 -> exact-tree reread
 -> merge recommendation OR blocker
```

If a second remediation is required, stop and return the exact blocker to the maintainer. A maintainer may explicitly authorize a narrow additional remediation; that approval is task-specific.

Before merge recommendation, refresh the PR description/evidence receipt so it describes the actual exact candidate head.

If an active task conflicts with a historical handoff, the active baseline and `AGENTS.md` win.
