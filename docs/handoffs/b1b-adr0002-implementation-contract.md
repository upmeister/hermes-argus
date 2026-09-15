---
title: B1b implementation contract — ADR 0002 Hermes discovery/sync boundary
status: ready-for-agent-loop
project: hermes-argus
date: 2026-09-16
---

# B1b implementation contract — ADR 0002 Hermes discovery/sync boundary

## 1. Outcome

B1b is a **docs/architecture implementation task**, not a production runtime task.

The required outcome is an accepted ADR 0002 that converts the completed C0 evidence into a stable project boundary for the next implementation wave.

Primary target:

```text
docs/adr/0002-hermes-discovery-sync-boundary.md
```

The ADR must be sufficient for a later C1a implementation contract to be written without re-deciding the C0 architecture.

## 2. Fresh-baseline gate

Before editing, record:

- current Argus `main` SHA;
- presence/read-back of the archival C0 merge (historical evidence baseline `19aa9f2...`, but do not assume current `main` equals it);
- production Hermes revision actually installed on the monitored system;
- current upstream Hermes `main`/release used as drift signal;
- whether the Hermes seams exercised by C0 still exist with materially similar behavior.

If current source contradicts a frozen decision below, stop and record:

```text
new source/runtime fact -> affected decision -> proposed amendment
```

Do not silently rewrite the contract around new behavior.

## 3. Required reading

Before drafting/review:

1. `AGENTS.md`;
2. `docs/adr/0001-integration-evidence-policy.md`;
3. `docs/experiments/c0-runtime-bridge-contract.md`;
4. C0 experiment code/readme under `experiments/c0-runtime-bridge/`;
5. final C0 evidence receipt/report;
6. current `scripts/integration-discover.py`;
7. project conventions / agent instructions;
8. relevant architecture/backlog notes describing `Hermes owns runtime truth; Argus owns verification policy`.

## 4. Frozen B1b decisions

Unless a fresh source/runtime fact materially contradicts them, ADR 0002 MUST preserve these decisions.

### D1 — Keep the architecture ownership rule

```text
Hermes owns runtime truth.
Argus owns verification policy.
```

The bridge reduces duplicated Hermes semantics. It does not move Argus alert/evidence policy into Hermes.

### D2 — Discovery/sync is not regular verification

Do not weaken ADR 0001's regular verification budget.

Define `discovery/sync` as a separate metadata reconciliation operation. It does not itself establish health claims/verdicts.

### D3 — Process boundary is mandatory

No long-lived Argus process imports Hermes runtime modules.

One explicit profile per short-lived child, with parent-owned containment.

### D4 — Accepted initial facets

Initial production bridge scope is limited to:

```text
identity
config_health
effective_config
```

`config_health` and `effective_config` are accepted only within the bounded discovery/sync effect budget.

### D5 — Bounded local writes are allowed only for discovery/sync

The config facets may perform Hermes-owned bootstrap/backup writes inside the explicitly selected Hermes home.

This permission does not propagate to regular health checks or arbitrary child behavior.

### D6 — Exclude strong runtime facets

Initial automatic bridge MUST NOT productionize:

```text
runtime_route
provider_registry
resolved credential presence
```

Rationale must cite C0 evidence: credential/auth-state behavior, plugin code execution/hang, and lack of a metadata-only resolved-credential seam.

### D7 — Shadow-first migration

C1a must run bridge and existing discovery side-by-side before authority cutover.

The ADR must prohibit immediate replacement/deletion of static discovery.

### D8 — Provenance and compatibility degradation are visible

Static fallback may preserve continuity but must not masquerade as Hermes canonical truth when the bridge is degraded.

### D9 — Dual baseline policy

Record both:

- production Hermes compatibility target;
- current upstream drift signal.

Do not treat historical C0 upstream SHA as permanently canonical.

### D10 — No production action in B1b

No deploy, cron/systemd change, discovery wiring, or health behavior change belongs in this PR.

## 5. ADR content requirements

ADR 0002 must contain at least:

```text
Status
Context
C0 evidence summary
Decision
Operational classes / relation to ADR 0001
Process boundary
Accepted facets
Effect budget
Excluded facets
Authority/provenance
Shadow migration
Trigger/cadence guidance
Compatibility behavior
Dual baseline policy
Secret/serialization invariants
Consequences
Rejected alternatives
Follow-up work
```

The ADR may be shorter than the supplied analyst draft, but it must not remove a frozen decision merely for brevity.

## 6. Required semantic invariants

### Invariant A — no second Hermes runtime

Argus never reimplements profile/provider/auth routing in order to avoid calling Hermes. Static fallbacks can exist, but their authority is explicit and lower for Hermes-owned semantics.

### Invariant B — no false authority on degradation

This is forbidden:

```text
Hermes bridge failed -> static parser produced something -> report as Hermes truth
```

This is acceptable:

```text
Hermes bridge compatibility_degraded
+ lower-authority static metadata preserved
+ provenance/degradation surfaced
```

### Invariant C — no plugin execution in automatic bridge

No provider registry API that executes user/bundled/pip plugin code belongs in automatic discovery/sync.

### Invariant D — allowlist extraction, not serialize-then-redact

The future bridge contract must be designed around allowed output fields.

### Invariant E — C0 experiment artifacts remain historical evidence

Do not rewrite C0 history to make the final architecture look inevitable. The ADR should preserve that C0 discovered contradictions and led to `MODIFY`.

## 7. Scope

### In scope

- new ADR 0002;
- tiny link/reference update to `AGENTS.md` if needed so future agents discover ADR 0002;
- tiny documentation index/reference update if the repository already maintains one;
- documentation-only clarification of the C0→B1b→C1 sequence.

### Out of scope

- moving experimental C0 code into `scripts/`;
- wiring a bridge into `integration-discover.py`;
- changing systemd/cron/deploy manifests;
- fixing malformed YAML discovery crash;
- implementing C1a/C1b;
- implementing D0b adapters;
- changing ADR 0001 semantics except a minimal cross-reference if strictly necessary;
- deleting static discovery/provider metadata;
- production deployment.

If an out-of-scope bug is discovered, record it as a follow-up instead of fixing it in B1b.

## 8. Acceptance checks

### Source/read-back

- exact PR head identified;
- changed-file list matches docs-only scope;
- ADR path and references read back from remote PR head;
- no accidental runtime/deploy/test code changes.

### Architecture consistency

Reviewer must explicitly verify:

1. ADR 0001 regular budget remains unchanged;
2. `discovery/sync` cannot be confused with a health verdict-producing check;
3. accepted/excluded facets match C0 evidence;
4. provider registry executable discovery is excluded;
5. `runtime_route` is not smuggled back into automatic bridge scope;
6. static fallback cannot claim Hermes authority during compatibility degradation;
7. shadow-first migration is explicit;
8. production and upstream Hermes baselines are separately named;
9. no production action is authorized by B1b itself.

### Repository checks

At minimum:

```bash
git diff --check
python3 tests/probes.py
```

Run the repository's required CI/status checks on the exact PR head. If current project instructions define additional docs/static checks, run those too.

The regression suite is not evidence that the architecture wording is correct; it is only a guard against accidental repository breakage.

## 9. Stop conditions

Stop the autonomous loop and escalate if:

- current production Hermes behavior materially contradicts C0 assumptions;
- current upstream removed/replaced the config seams in a way that changes the architecture choice;
- ADR 0001 would need a substantive policy rewrite rather than a cross-reference;
- implementing the ADR would require production code changes to make the text true;
- reviewers cannot agree whether an effect belongs to verification vs discovery/sync.

## 10. PR requirements

Preferred logical commit / PR title:

```text
docs(argus): define Hermes discovery sync boundary
```

PR body must include:

```markdown
## Outcome
## Scope / non-goals
## C0 evidence basis
## Fresh baselines
## Frozen decisions confirmed
## Changed files
## Verification
## Contradictions / amendments
## Production actions
No production action performed.
## Next step
C1a shadow bridge contract, after analyst gate.
```

## 11. Analyst gate identity

For this B1b handoff, **Agent-Analyst** means the user-designated ChatGPT analyst in the current hermes-argus architecture workflow.

An additional external reviewer (for example PromptQL) may be consulted and its findings may be useful, but it does **not** satisfy or replace this analyst gate unless the user explicitly reassigns the role.

The primary reviewer/maintainer remains Pytna. ZCode and Pytna may complete multiple autonomous implementation/review/remediation cycles before returning the converged candidate.

## 12. Definition of Done

B1b is complete when:

- fresh Argus/production-Hermes/upstream-Hermes baselines are recorded;
- ADR 0002 exists on an exact reviewed PR head;
- Pytna confirms the ADR matches C0 evidence and ADR 0001 boundaries;
- required CI is green;
- no production/runtime behavior changed;
- outstanding follow-ups are recorded rather than smuggled into scope;
- the Agent-Analyst can read the final exact-head ADR and either accept it or identify a specific architecture contradiction.
