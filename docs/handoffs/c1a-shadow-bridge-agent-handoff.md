---
title: C1a handoff — bounded Hermes discovery shadow bridge
status: ready
project: hermes-argus
date: 2026-09-16
owners: [zcode, pytna]
next_gate: agent-analyst
contract: docs/handoffs/c1a-shadow-bridge-implementation-contract.md
---

# C1a handoff — bounded Hermes discovery shadow bridge

## Outcome requested

Implement the first production-shaped Hermes discovery/sync bridge, but keep it strictly in **shadow mode**.

Use:

```text
docs/adr/0002-hermes-discovery-sync-boundary.md
docs/handoffs/c1a-shadow-bridge-implementation-contract.md
```

The bridge may collect only:

```text
identity
config_health
effective_config
```

It must run beside current `integration-discover.py`, preserve provenance and compatibility state, and produce reconciliation evidence for a later C1b authority decision.

It must not change production health/alert authority in this cycle.

## Roles

### ZCode — implementation owner

- branch from the accepted/merged B1b baseline;
- perform the fresh production/upstream re-baseline before editing;
- implement production parent + child boundary from the contract;
- port only accepted C0 mechanisms, not excluded facets;
- add production regression probes;
- preserve legacy discovery behavior exactly;
- produce an exact evidence receipt;
- address Pytna findings through as many remediation loops as needed.

### Pytna — adversarial reviewer / maintainer

- independently inspect the exact production Hermes revision and current Argus base;
- verify that the child cannot reach `runtime_route`, provider/plugin discovery or helper execution;
- attack containment, output parsing, secret surfaces, wrapper behavior, provenance and rollback;
- read back exact remote head and CI after every remediation loop;
- do not let shadow evidence acquire authority by convenience;
- do not enable production shadow without explicit authorization.

### Agent-Analyst — architecture gate

- receives the converged exact-head C1a receipt;
- evaluates whether parity/provenance evidence is strong enough to define C1b;
- decides whether architecture needs amendment before any authority cutover.

## Phase 0 — synchronize prerequisites

B1b PR #25 has passed the Agent-Analyst architecture gate at exact head:

```text
2c88b2c1797b6af9c7bc75c6f64fa65892fa4b3c
```

This C1a contract PR is intentionally stacked on that B1b head while #25 remains open. Before starting implementation, ensure B1b is merged/accepted into the implementation base or rebase the C1a work so ADR 0002 is present exactly once.

Do not implement C1a against a main branch that lacks the accepted ADR and then recreate the ADR by hand.

## Phase 1 — fresh source/runtime baseline

Record:

```text
ARGUS_BASE=
HERMES_PRODUCTION=
HERMES_PYTHON=
HERMES_UPSTREAM=
```

Then answer, with source/runtime evidence:

1. Do `load_config_readonly`, `read_user_config_raw`, and `get_config_path` still exist on production Hermes?
2. Does the accepted config path still stay within the ADR 0002 effect class?
3. Does raw parse failure remain observable without invoking runtime routing?
4. Can the effective fields in the C1a allowlist be extracted without provider registry/plugin import?
5. Is the chosen Hermes Python an absolute path tied to the monitored installation?
6. Has upstream introduced a safer stable metadata seam that materially contradicts B1b?

If the production revision is no longer the B1b-reported `af4a3eba`, that is normal. Test the actual revision; do not pin history merely to make C0 pass again.

## Phase 2 — build the parent containment first

Before Hermes imports, implement and test the parent boundary:

```text
validated profile_id
explicit HERMES_HOME + HOME
absolute Hermes Python
allowlisted environment
hard timeout
kill + reap
stdout/stderr hard caps
strict one-envelope JSON parser
duplicate-key rejection
schema/type validation
profile binding
effect validation
atomic shadow-state write
```

Use synthetic fake children for these tests. If containment is shaky, do not proceed to Hermes-backed facets.

The production parent must not import Hermes.

## Phase 3 — add `identity` and `config_health`

Add only the minimum imports needed for the accepted config seams.

Required observations:

- bounded Hermes identity/version metadata;
- selected profile remains explicit;
- valid current config -> `config_health=ok`;
- malformed current config -> structured partial/degraded signal, never canonical ok merely because effective fallback exists;
- import/API drift -> compatibility degraded;
- no secret values in envelope.

Run against synthetic profile A then B and B then A using the actual production Hermes interpreter/revision.

## Phase 4 — add `effective_config` allowlist

Add only fields enumerated by the contract.

Particular attention:

- primary model/provider;
- fallback references including modern `fallback_providers` semantics;
- all currently supported auxiliary roles relevant to the accepted config surface;
- MCP declaration metadata without connecting/executing;
- named/custom providers as declarative identity + sanitized endpoint/auth class only;
- `${ENV}` descriptors without values.

Do not call provider registry APIs to make provider names prettier or more canonical. Declarative config identity is enough for C1a.

Do not run runtime provider resolution to answer credential questions. Resolved credential presence remains unsupported.

## Phase 5 — prove the negative boundaries

The fixture suite must include:

- a user provider plugin that writes a marker if imported;
- a plugin that would hang if imported;
- a configured external key/helper command that writes a marker if executed;
- secret canaries in `.env`, inline config, endpoint query/userinfo and `${ENV}` materialization paths.

Running all automatic C1a facets must:

```text
leave plugin markers absent
leave helper marker absent
show network=[]
show process_spawn=[]
show only accepted bounded writes
show no canary in Argus-controlled output/state/log surfaces
```

A timeout successfully killing a plugin is **not** success in C1a: the plugin must never have been invoked.

## Phase 6 — wire shadow execution without behavior change

Integrate shadow collection into the existing change-driven flow under a default-OFF feature flag.

Before changing the wrapper, capture fixture behavior of the current wrapper for at least:

```text
static rc=0 / no changes
static rc=2 / changes + alert path
static discover failure
missing Telegram credentials
```

After the hook is added, repeat the matrix with shadow:

```text
disabled
success
degraded
crash
timeout
malformed result
```

For every row, legacy output/rc/alert decision must remain what it was without shadow. Shadow must only write its own state/log evidence.

Do not add a C1a Telegram notification merely because degradation feels important; user-facing behavior belongs to a later explicitly reviewed step.

## Phase 7 — reconciliation/provenance

Implement the contract's mapped semantic comparison rather than whole-snapshot equality.

Expected classifications from C0/B1b include:

```text
bridge_gain      fallback/aux semantics static does not fully represent
static_retained  OAuth metadata
static_retained  declarative plugin manifest metadata
```

These are not automatically bugs.

Unexpected comparable disagreement is `semantic_difference` and must carry enough sanitized context to debug the mapping without dumping raw config or secrets.

Never replace a degraded Hermes observation with static data and label it `hermes-effective`.

## Phase 8 — full regression + exact-head review

At minimum run:

```bash
python3 -m py_compile <all changed Python files>
bash -n <all changed shell files>
python3 tests/probes.py
git diff --check
```

Also run the production-Hermes fixture suite required by the contract and record its exact interpreter/revision.

Pytna must inspect the remote PR head, not only a local worktree.

## Phase 9 — optional production shadow enablement

Implementation and production enablement are separate approvals.

Unless the maintainer/user explicitly authorizes deployment during this cycle:

```text
Production actions: none.
```

If authorization is given, follow the contract's enable/read-back sequence. Do not treat merge approval as deployment authorization.

The first production run must prove that:

- legacy static discovery still behaves normally;
- shadow state appears separately;
- compatibility is explicit;
- reconciliation contains only sanitized metadata;
- no shadow Telegram alert occurred;
- effect observations remain within budget.

## Pytna adversarial checklist

### 1. Authority attack

Can any consumer accidentally read shadow output as the canonical integration snapshot? If yes, block.

### 2. Wrapper isolation attack

Can shadow failure alter static exit code, suppress/update the static snapshot incorrectly, change alert formatting or hold the lock indefinitely? If yes, block.

### 3. Interpreter attack

Can config/env injection select arbitrary executable code instead of the intended Hermes Python? If yes, block.

### 4. Environment attack

Can notification credentials, proxy secrets, `PYTHONPATH`, loader variables or parent secrets reach the child unintentionally? If yes, block.

### 5. Plugin attack

Can any accepted facet indirectly trigger `providers.list_providers()`, plugin manager loading, entry points or user plugin import? Sentinel must prove no.

### 6. Helper attack

Can `${ENV}`, provider config or a key-command reference execute an external helper? Sentinel must prove no.

### 7. Serialization attack

Could a new nested Hermes field leak because code serializes broadly then redacts? The design must be constructive allowlisting.

### 8. Write-budget attack

Are writes merely observed, or actually checked against allowed classes and selected home? Writes outside the selected profile or new path classes are blockers.

### 9. Malformed-config attack

Can current broken YAML still produce `config_health=ok` via fallback/default/last-known-good state? If yes, block.

### 10. False parity attack

Are OAuth/plugin/static-only families being counted as bridge failures, or are semantically different fields being compared as strings? If yes, fix mapping before using parity evidence.

### 11. Rollback attack

Can shadow be disabled without reconstructing legacy state or undoing an authority migration? If no, C1a has exceeded scope.

## Evidence receipt to return

```markdown
# C1a evidence receipt

## Outcome

## Fresh baselines
- Argus base:
- PR head:
- production Hermes revision:
- production Hermes Python:
- upstream Hermes drift signal:

## Changed files

## Facets
- identity:
- config_health:
- effective_config:

## Containment
- profile isolation:
- env allowlist:
- timeout/reap:
- output caps:
- malformed-output handling:

## Effects
- network:
- spawn:
- token refresh:
- plugin/user code:
- helper execution:
- writes:

## Secret review

## Reconciliation
- equal:
- bridge_gain:
- static_retained:
- semantic_difference:
- not_comparable:
- degraded:

## Legacy behavior preservation

## Tests / CI

## Pytna findings

## Remediation cycles

## Production actions

## Rollback/read-back

## Open gaps

## Recommendation
READY FOR AGENT-ANALYST | BLOCKED
```

Do not return only counts; include the meaningful semantic differences and effect observations.

## Non-goals

Do not in C1a:

- perform C1b authority cutover;
- delete/reduce static discovery coverage;
- fix the malformed-YAML static parser bug unless separated into its own PR;
- add runtime routing or resolved credential status;
- execute provider/plugin registries;
- change health schema/verdict semantics;
- add generic adapter framework work;
- bundle unrelated D0b work;
- redesign bot UI;
- broaden to multiple Hermes profiles without a separate need/evidence case.

## Next step

After a converged C1a receipt, Agent-Analyst decides whether to draft **C1b authority cutover** and exactly which mapped Hermes-owned fields, if any, are ready to move from `argus-static` to `hermes-effective` authority.
