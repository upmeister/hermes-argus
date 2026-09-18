# Handoffs and implementation contracts

This directory contains both active implementation contracts and historical handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-18

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `oa0-account-auth-discovery-research-contract.md` — **NOW / RESEARCH ONLY**

Completed:

- R1a deploy/GitHub-heartbeat secret-in-argv — **DONE / PR #29**
- R1b Telegram child-argv secret exposure — **DONE / PR #31**

Queued only after OA0 returns a maintainer-reviewed decision:

- OA1 generic structural account-auth discovery — implementation contract not yet authorized;
- OA2 Hermes account-status shadow/enrichment — only if OA0 recommends it and a separate contract is approved;
- R1c demonstrated non-Telegram Authorization-header argv debt;
- R2a malformed YAML;
- R2c bounded static compatibility excluding the superseded auth-audit subsection.

Deferred:

- `r2b-gateway-liveness-contract.md` — research only until a stable external liveness seam is demonstrated.

Parent/history:

- `r1-secret-in-argv-contract.md` — original combined R1 record;
- `r1b-telegram-secret-argv-contract.md` — completed R1b contract retained as execution evidence.

An agent must not implement multiple contracts in one PR unless the maintainer explicitly combines them.

## Current execution order

```text
R1a  DONE / PR #29
R1b  DONE / PR #31

OA0  NOW — account-auth discovery research
 -> maintainer decision
 -> OA1 generic static auth discovery
 -> OA2 shadow/enrichment only if OA0 authorizes it

then:
R1c demonstrated Authorization-header argv debt
 -> R2a malformed YAML
 -> R2c bounded static discovery (fallback/registry/aux only)
 -> R3 stabilization/reduction
```

OA0 itself is research-only. Its presence does not authorize OA1/OA2 production code.

Multi-profile work remains a separate near-term product track. OA0 may record profile-related properties of an external seam, but must not implement profile monitoring.

## R2c auth subsection superseded

The old `r2c-static-discovery-compat-contract.md` included an R2c.3 credential/OAuth audit that assumed no demonstrated user-visible gap.

That premise is no longer true: a working OpenAI/Codex account can be invisible to current Argus static discovery because Hermes auth storage evolved.

OA0 supersedes R2c.3 for all account-auth discovery decisions.

The remaining R2c fallback/auxiliary/registry work stays queued after R2a unless the maintainer changes ordering again.

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
 -> research or implementation, according to that contract
 -> focused review
 -> at most one remediation by default
 -> exact-tree reread
 -> merge/research decision OR blocker
```

If a second remediation is required, stop and return the exact blocker to the maintainer. A maintainer may explicitly authorize a narrow additional remediation; that approval is task-specific.

Before merge recommendation, refresh the PR description/evidence receipt so it describes the actual exact candidate head.

If an active task conflicts with a historical handoff, the active baseline and `AGENTS.md` win.
