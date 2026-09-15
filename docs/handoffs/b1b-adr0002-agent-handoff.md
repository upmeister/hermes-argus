---
title: B1b handoff — ADR 0002 Hermes discovery/sync boundary
status: ready
project: hermes-argus
date: 2026-09-16
owners: [zcode, pytna]
next_gate: agent-analyst
---

# B1b handoff — ADR 0002 Hermes discovery/sync boundary

## Outcome requested

Turn the accepted C0 decision record into a concise, durable repository ADR and return an exact-head docs-only PR for the final Agent-Analyst gate.

Use the implementation contract:

```text
docs/handoffs/b1b-adr0002-implementation-contract.md
```

Suggested ADR target:

```text
docs/adr/0002-hermes-discovery-sync-boundary.md
```

A draft ADR is supplied with this handoff. Treat it as architecture input, not unquestionable text: wording may be improved, but frozen decisions from the contract may change only when a fresh source/runtime fact contradicts them.

## Roles

### ZCode — implementation/coding agent

- create an isolated branch/worktree;
- perform fresh baseline reads;
- adapt the draft into repository style;
- keep the PR docs-only;
- run required source/CI checks;
- address Pytna review comments;
- maintain an exact evidence receipt.

### Pytna — primary reviewer/maintainer

- independently re-read current Argus and relevant Hermes seams;
- challenge the ADR against C0 evidence and ADR 0001;
- verify exact head, changed files and CI;
- run as many autonomous remediation cycles with ZCode as necessary;
- do not authorize production wiring as part of B1b.

### Agent-Analyst — final architecture gate

- the designated Agent-Analyst for this cycle is the ChatGPT analyst in the current project workflow;
- review the converged exact-head ADR after the ZCode↔Pytna loop;
- check that C0 evidence was neither overstated nor weakened;
- issue ACCEPT / MODIFY with specific architecture findings;
- after acceptance, prepare/approve the C1a shadow-bridge implementation contract.

**Important:** an additional reviewer such as PromptQL is supplemental. It does not consume or replace the Agent-Analyst gate unless the user explicitly says so.

## Phase 0 — fresh re-baseline

Before editing, record all four:

```text
ARGUS_MAIN=<current remote main SHA>
C0_ARCHIVAL_BASELINE=19aa9f2b54ec8b97bbf0d6b2e8c478656e74c89
HERMES_PRODUCTION=<actual installed revision>
HERMES_UPSTREAM=<current upstream main/release>
```

Also verify that the current repository still contains/read-backs:

- ADR 0001;
- C0 contract/handoff;
- archival C0 experiment artifacts/evidence;
- current `integration-discover.py` behavior relevant to the ADR.

Do not assume the historical C0 production Hermes `b6b53c69` is still installed.

## Phase 1 — contradiction check

Before polishing prose, answer:

1. Does current production Hermes still require a process boundary for the seams we intend to use?
2. Do the accepted config seams still exhibit the same broad effect class (bounded local bootstrap/backup; no required network/plugin execution in the accepted path)?
3. Has upstream introduced a stable metadata-only API that would materially invalidate the decision to defer resolved credential presence or runtime route?
4. Has provider discovery stopped executing plugin code? If not demonstrably changed, preserve the DROP decision.
5. Does ADR 0001 still define regular verification in a way that should remain stricter than discovery/sync?

If any answer contradicts the contract, document the source/runtime fact and pause architecture convergence until the amendment is explicit.

## Phase 2 — draft ADR 0002

The ADR should make the following readable without needing the whole C0 report:

```text
why static-only Argus is insufficient
why a broad runtime bridge is too strong
why process isolation is mandatory
why discovery/sync is separate from health verification
which facets are accepted now
which facets are deferred/prohibited
what side effects are allowed
how provenance/fallback works
why migration is shadow-first
how compatibility/upstream drift is handled
```

Keep the ADR durable. Do not include mutable worklog detail, reviewer thread IDs, transient paths, or large test transcripts.

Historical SHAs may appear only as evidence references; current baselines belong primarily in the PR receipt.

## Phase 3 — scoped repository updates

Expected changed files should be approximately:

```text
docs/adr/0002-hermes-discovery-sync-boundary.md
AGENTS.md                                  # only if a small ADR link/boundary note is useful
<existing docs index>                      # only if one already exists
```

If the implementation contract/handoff themselves are being committed as part of the docs PR, include them intentionally and state that in scope.

Unexpected changes under `scripts/`, `tests/`, `.github/`, deploy manifests, systemd, registry or generated files are a stop signal for this PR.

## Phase 4 — Pytna adversarial review

Pytna should explicitly challenge these failure modes:

### Boundary challenge

Could a future agent read ADR 0002 and reasonably conclude that regular health checks may write to Hermes home? If yes, wording is wrong.

### Authority challenge

Could bridge failure silently cause static output to be presented as canonical Hermes truth? If yes, wording is wrong.

### Scope-creep challenge

Could `runtime_route` or `providers.list_providers()` be added to automatic discovery merely because they are canonical Hermes functions? If yes, wording is wrong.

### Migration challenge

Could C1 immediately delete/replace static OAuth or other static coverage? If yes, wording is wrong.

### Compatibility challenge

Does the ADR distinguish the actually installed production Hermes revision from current upstream drift? If no, wording is incomplete.

### Historical-evidence challenge

Does the ADR falsely imply C0 satisfied `write:none`? If yes, reject. The whole architectural point is that it did not.

## Phase 5 — verification

Run at least:

```bash
git diff --check
python3 tests/probes.py
```

Then read back the remote PR head and required CI status.

Record exact:

```text
base SHA
head SHA
changed files
CI/check results
review/remediation cycles
```

No deploy or production smoke is required for a docs-only B1b PR. Do not perform one merely to satisfy the general deployed-change DoD.

## Phase 6 — return to Agent-Analyst

Do not report merely "ADR done".

Return this receipt:

```markdown
## B1b outcome

## Fresh baselines
- Argus main/base:
- PR head:
- production Hermes:
- upstream Hermes:

## Changed files

## Frozen decisions
- D1 ownership rule: CONFIRMED / AMENDED
- D2 discovery vs verification: CONFIRMED / AMENDED
- D3 process boundary: CONFIRMED / AMENDED
- D4 accepted facets: CONFIRMED / AMENDED
- D5 effect budget: CONFIRMED / AMENDED
- D6 excluded facets: CONFIRMED / AMENDED
- D7 shadow migration: CONFIRMED / AMENDED
- D8 provenance/degradation: CONFIRMED / AMENDED
- D9 dual baseline: CONFIRMED / AMENDED
- D10 no production action: CONFIRMED

## New source/runtime facts

## Pytna adversarial findings

## Remediation cycles

## Verification

## Open follow-ups

## Production actions
No production action performed.

## Recommendation
READY FOR AGENT-ANALYST | BLOCKED
```

## Non-goals to keep visible

B1b does **not** implement C1a.

Do not in this loop:

- move C0 bridge into production paths;
- alter discovery behavior;
- add new bot UI;
- fix unrelated UI comments from manual testing;
- fix A1/A2 security issues;
- fix malformed static discovery YAML behavior;
- deploy Argus archival C0 main;
- add runtime-route/provider-registry functionality.

All of these may be valid work, but mixing them into ADR 0002 destroys the architecture gate.

## Next task after acceptance

After Agent-Analyst acceptance of B1b, prepare **C1a: bounded Hermes discovery/sync bridge in shadow mode** with only:

```text
identity
config_health
effective_config
```

C1a must have its own implementation contract, parity/provenance schema, rollback/read-back plan, and production authorization boundary.
