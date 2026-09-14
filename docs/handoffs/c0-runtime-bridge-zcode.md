# C0 runtime bridge — ZCode / Pytna handoff

- Status: **READY FOR ZCODE + PYTNA AUTONOMOUS EXPERIMENT LOOP**
- Repository: `upmeister/hermes-argus`
- Argus planning baseline: `f17fb3a50927629abc49546fcacf5564c1e3f07d` (current `origin/main`; Wave 1 closed — PR #19 `e4a98ec`, #20 `c51bdcb`, #21 `f17fb3a5`)
- Hermes upstream baseline when this brief was written: `3f86ed75dad1933036c52018e991dbd839837126` (the exact revision actually used by the experiment must be verified and recorded in the receipt)

## Outcome requested

Run the bounded C0 experiment defined in:

```text
docs/experiments/c0-runtime-bridge-contract.md
```

Canonical copy lives in the repository at that path. Vault drafting mirrors:
Windows `D:\agenda\projects\hermes-argus\docs\c0-runtime-bridge-experiment-contract.md`,
Peetna mirror `/home/ubuntu/obsidian-vault/projects/hermes-argus/docs/c0-runtime-bridge-experiment-contract.md`.

The deliverable is **evidence for a decision**, not a production bridge.

The final result must tell the next analyst which candidate facets are safe/useful enough for `GO`, which should be narrowed (`MODIFY`), and which should be dropped.

## Required reading

Before editing:

1. root `AGENTS.md`;
2. `docs/adr/0001-integration-evidence-policy.md`;
3. `docs/experiments/c0-runtime-bridge-contract.md`;
4. current `scripts/integration-discover.py`;
5. canonical vault notes: `architecture/2026-09-13-b1a-b1b-d0-proposal.md` (B1b/C0
   architecture, §3 C0 acceptance tests), `plans/2026-09-13-backlog-reconciliation.md`
   (lane dispositions), `docs/c0-runtime-bridge-analyst-note.md` (analyst proposals,
   vault-only). Vault locations: Windows `D:\agenda\projects\hermes-argus\...`,
   Peetna mirror `/home/ubuntu/obsidian-vault/projects/hermes-argus/...`;
6. synchronized Hermes source on `peetna-aws` — a dedicated experiment clone (not the
   production install), pinned to the revision recorded in the receipt. Verify with
   `git -C <clone> rev-parse HEAD` before every run and record the exact revision in
   the receipt.

Relevant Hermes areas currently include, but are not pre-approved as the final import set
(paths relative to the root of the Hermes checkout):

```text
hermes_constants.py
hermes_cli/config.py
hermes_cli/env_loader.py
hermes_cli/runtime_provider.py
providers/__init__.py
providers/base.py
hermes_cli/mcp_config.py
hermes_cli/doctor*.py
agent/secret_scope.py
agent/secret_sources/*
```

Fresh source/runtime facts supersede this list.

## Role split

### ZCode

Own implementation, fixtures, experiment execution and handoff evidence.

### Pytna

Own primary adversarial review, remediation loop and convergence gate. Pytna is the main reviewer for the coding iteration.

### Agent-analyst

Returns after convergence. Do not wait for analyst approval on ordinary implementation choices that do not weaken the frozen experiment contract.

## Delivery & acknowledgement

- This handoff and the frozen contract are delivered to Pytna as repository files
  (`docs/handoffs/c0-runtime-bridge-zcode.md` and
  `docs/experiments/c0-runtime-bridge-contract.md`) via a docs PR, plus an explicit
  notification over the MCP peetna bridge (lane `argus-c0-bridge`; fallback channel:
  `D:\agenda\tools\ask-peetna.sh` over `ssh peetna-aws`).
- Pytna must explicitly acknowledge the handoff (read-back of the notification or a
  PR comment) before the autonomous loop starts. A missed agent-hop hook or a silent
  tool failure must not be mistaken for a delivered handoff.

## Hard constraints

- Use an isolated branch/worktree.
- Keep C0 code out of deployed Argus paths.
- Do not modify `deploy.sh`, cron/systemd or normal health/discovery behavior.
- Do not use real production credentials in fixtures/CI.
- Do not perform provider generation, remote writes or token refresh.
- Do not silently inherit the maintainer's full environment into bridge children.
- Do not serialize broad Hermes objects and then redact them.
- Do not weaken MUST-PASS gates to make observations green.
- Do not turn experimental internal imports into an Accepted B1b contract.

## Suggested implementation shape

Preferred starting point:

```text
experiments/c0-runtime-bridge/
  bridge.py
  harness.py
  fixtures/
  README.md
```

The harness should execute an explicit Hermes Python interpreter, one explicit `HERMES_HOME` per child, with hard timeout and output caps.

Use allowlist serialization in the child. A facet that cannot be obtained safely should return an explicit unsupported/degraded state rather than guessed data.

## First implementation sequence

### Step 1 — harness containment before Hermes imports

Implement/test:

- clean/allowlisted environment;
- explicit `HERMES_HOME`;
- timeout + kill/reap;
- stdout/stderr byte caps;
- malformed JSON handling;
- child crash handling;
- canary leak scan;
- `PYTHONDONTWRITEBYTECODE=1` or equivalent no-bytecode-write setup.

Do this before attempting rich Hermes runtime facets.

### Step 2 — identity + config-health facet

Try the smallest Hermes surface first.

Prove:

- explicit-home behavior;
- profile A/B isolation;
- malformed config is visible as degraded/error rather than a false canonical success;
- no secret values are serialized.

### Step 3 — effective-config facet

Extract only allowlisted fields required for the coverage comparison.

Exercise `${ENV}` fixtures with a deliberately controlled environment and record what Hermes regards as effective config under that environment.

Do not silently call external secret hydration merely to make interpolation complete.

### Step 4 — runtime-route facet

Experimentally use the current canonical resolver where possible.

Before accepting the facet as regular-safe, prove whether resolver execution can:

- materialize credential values;
- invoke auth/OAuth helpers;
- hydrate secret sources;
- execute provider/plugin code;
- spawn processes;
- use network;
- write state.

Emit only allowlisted metadata. Credential values remain forbidden even if present inside the child.

### Step 5 — provider-discovery negative control

Use a user-provider plugin sentinel to determine whether provider profile discovery imports executable code.

If it does, this is expected evidence for rejecting that facet from regular mode — not a reason to hide the observation.

### Step 6 — coverage comparison

For the same fixtures, compare:

```text
expected Hermes truth
current integration-discover.py
C0 facet result
```

Name concrete semantic gains and misses.

## Required adversarial fixtures

At minimum implement equivalents of:

- two profiles with conflicting provider/model values;
- `${C0_CANARY_ENV}` config reference;
- `.env` canary secret;
- malformed config;
- custom provider;
- resolver credential canary;
- plugin marker writer;
- plugin exception;
- plugin hang;
- external secret helper marker;
- child crash before JSON;
- oversized output.

Fixture data must be synthetic.

## Verification depth

The C0 contract distinguishes:

### MUST-PASS

Safety/containment properties. These block acceptance of the affected design.

### OBSERVATION

Questions about Hermes behavior. RED may be the correct result and should change the facet decision, not be patched around.

Keep those categories visible in test/probe names and the final receipt.

## Reviewer guidance for Pytna

After ZCode has a candidate:

1. verify exact Argus and Hermes heads;
2. inspect the child environment construction;
3. verify secrets are absent from argv/stdout/stderr/result/logs;
4. run profile-isolation tests in both orders;
5. run hang/crash/oversized-output cases;
6. independently observe process/network/write behavior for facets proposed as regular-safe;
7. verify no C0 path is wired into production/deploy;
8. challenge each `authority: hermes` statement: identify the exact upstream API that earns that label;
9. challenge each `no side effect` claim with process-boundary evidence where practical;
10. make one remediation loop, then focused re-run of failed/affected gates.

Do not require all OBSERVATION probes to be green. Require their interpretation to be honest.

## Stop / escalation conditions

Stop scope expansion and record a contract contradiction when:

- current Hermes source differs materially from the assumptions in the experiment contract;
- a supposedly read-only API performs an unexpected live/secret/plugin effect;
- a canonical result cannot be obtained without production credentials;
- profile isolation cannot be demonstrated;
- the bridge requires broad private-import traversal;
- a fixture result is nondeterministic or order-dependent after reasonable debugging.

Report:

```text
fact -> impact -> required contract decision -> safe next action
```

## Final handoff receipt

The converged PR/comment must contain:

```markdown
## Baselines
Argus base/head:
Hermes tested revision:
Environment:

## Scope
Changed files:
Non-goals preserved:

## Facet table
| Facet | State | Authority | Hermes seam | Proposed decision |

## MUST-PASS safety gates
| Gate | Evidence | Result |

## OBSERVATION probes
| Probe | Observed fact | Interpretation |

## Side effects observed
Network:
Additional process spawn:
Token refresh:
Secret hydration:
Writes:
Plugin/code execution:

## Secret review
Canary identifiers used:
Output/argv/log scan:

## Coverage comparison
| Scenario | Expected Hermes truth | Static Argus | Bridge | Gain |

## Compatibility surface
Exact imports/symbols + stability notes.

## Findings
P0:
P1:
P2/backlog:

## Production actions
No production action performed.

## Maintainer recommendation
Per-facet GO / MODIFY / DROP proposal.
Overall GO / MODIFY / DROP proposal.

## Next owner
Agent-analyst — independent C0 decision review and B1b input.
```

## Definition of done for the autonomous loop

The ZCode/Pytna loop may stop when:

- the experiment contract has been exercised;
- all MUST-PASS gates have real outcomes;
- observations are recorded without hiding inconvenient effects;
- the coverage matrix exists;
- the compatibility surface is inventoried;
- no unresolved P0/P1 exists inside the agreed spike scope;
- the exact final head + evidence receipt are ready for agent-analyst review.

Do **not** implement ADR 0002 as Accepted in the same loop. B1b is the next architectural decision, based on C0 evidence.
