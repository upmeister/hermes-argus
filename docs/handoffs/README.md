# Handoffs and implementation contracts

This directory contains both active implementation contracts and historical handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — 2026-09-17

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract:
   - `r1-secret-in-argv-contract.md`
   - `r2a-malformed-yaml-contract.md`
   - `r2b-gateway-liveness-contract.md`
   - `r2c-static-discovery-compat-contract.md`

An agent must not implement multiple contracts in one PR unless the maintainer explicitly combines them.

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
 -> at most one remediation
 -> exact-tree reread
 -> merge recommendation OR blocker
```

If an active task conflicts with a historical handoff, the active baseline and `AGENTS.md` win.
