# C0 experiment contract — bounded Hermes runtime bridge

- Status: **implementation handoff / experimental gate**
- Canonical copy: committed to the repository at `docs/experiments/c0-runtime-bridge-contract.md`; this vault file is the drafting mirror.
- Project: `upmeister/hermes-argus`
- Argus baseline: `f17fb3a50927629abc49546fcacf5564c1e3f07d`
- Hermes upstream baseline for contract drafting: `3f86ed75dad1933036c52018e991dbd839837126`
- Related decision: ADR 0001 (`docs/adr/0001-integration-evidence-policy.md`)
- Next decision if successful: B1b / ADR 0002

## 1. Purpose

C0 is an **experiment**, not a production feature and not a commitment to a Hermes runtime bridge.

The question is:

> What is the maximum useful slice of Hermes-owned runtime truth that Argus can obtain through a short-lived Hermes subprocess without violating Argus regular-tier side-effect policy, leaking secrets, or creating a second Hermes runtime?

The experiment may legitimately conclude that only a subset of the proposed bridge is safe/useful. `MODIFY` is a successful result when it narrows the bridge to facets that are demonstrably canonical and bounded.

This contract freezes the **questions, safety invariants, evidence requirements and decision criteria**. It deliberately does **not** freeze the final Hermes import list or require a particular bridge implementation.

## 2. Architecture boundary

The existing project rule remains authoritative:

```text
Hermes owns runtime truth.
Argus owns verification policy.
```

For C0 this becomes:

```text
Argus harness
  -> explicit Hermes Python + explicit HERMES_HOME
  -> one short-lived child per profile
  -> allowlisted, sanitized facet output only
  -> evidence receipt
```

The child process may use Hermes internals **only as experimental compatibility seams**. Argus must not import Hermes runtime modules into its long-lived watchdog process.

The parent/harness owns:

- Hermes Python/source selection;
- explicit `HERMES_HOME`;
- safe profile label;
- environment allowlist;
- requested facet list;
- timeout;
- stdout/stderr size limits;
- termination and failure classification.

The child must not infer a different active profile when an explicit profile home is supplied.

## 3. Scope

### In scope

- profile/home isolation;
- profile-aware effective config reads;
- config parse/degradation visibility;
- selected runtime provider/model/API-mode metadata where safely obtainable;
- credential **metadata only** (configured/present/source class), never values;
- facet-level compatibility/error reporting;
- containment of crashes, hangs, incompatible imports and malformed output;
- secret non-disclosure;
- side-effect observation;
- coverage comparison against current `scripts/integration-discover.py`;
- maintenance-surface measurement: number and stability of Hermes seams used.

### Out of scope

- production deployment;
- changing `integration-discover.py` or health-check consumers;
- B1b acceptance;
- D0b claims/effects implementation;
- generic adapter framework (D1);
- live provider health calls;
- model generation;
- MCP connect/tools-list;
- token refresh;
- secret rotation;
- external-secret hydration as a normal bridge path;
- arbitrary provider/plugin execution as a regular-tier capability.

## 4. Frozen hypotheses

### H1 — profile isolation

With one child process per explicit `HERMES_HOME`, profile-dependent caches, ContextVars, config and credential state do not bleed across profiles.

### H2 — config authority gain

A Hermes-owned config API can provide a more canonical profile-aware/effective view than Argus raw YAML reconstruction for at least one real configuration class.

### H3 — bounded regular-mode effects

At least one useful bridge mode/facet can execute with:

```text
network = none
process_spawn = only the bridge child itself
additional child process spawn = false
external secret hydration = false
token_refresh = none
quota = none
llm = false
write = none
plugin/user code execution = none
```

`PYTHONDONTWRITEBYTECODE=1` (or equivalent) should be used so Python bytecode cache writes do not invalidate the no-write experiment.

### H4 — secret non-disclosure

Secret values do not reach:

- stdout;
- stderr;
- bridge JSON;
- exception text/repr;
- argv;
- result files;
- logs produced by the experiment.

This remains required even when a Hermes API materializes a credential value internally.

### H5 — fault containment

Import failure, API incompatibility, malformed config, child crash, timeout, oversized output and malformed JSON do not break Argus/harness state. They become explicit facet or bridge degradation.

### H6 — measurable coverage gain

The bridge produces materially more accurate/canonical information than current static Argus discovery for at least one supported real-world scenario.

### H7 — maintainable seam

The useful subset depends on a small, named Hermes API surface that can be independently compatibility-tested. A bridge requiring broad private-module traversal or duplicated Hermes routing logic fails this hypothesis.

## 5. Facet model

C0 must not emit one undifferentiated "runtime snapshot". Each independently attempted capability is a **facet** with its own authority and compatibility state.

Minimum envelope shape:

```json
{
  "schema": 1,
  "source": {
    "hermes_revision": "...",
    "bridge_revision": "...",
    "profile_id": "safe-label"
  },
  "facets": {
    "config_health": {
      "state": "ok",
      "authority": "hermes",
      "api": "hermes_cli.config.load_config_readonly",
      "data": {}
    }
  }
}
```

Allowed facet states:

```text
ok
partial
unsupported
compatibility_degraded
error
```

A facet failure must not silently downgrade or invalidate unrelated successful facets.

### Candidate facet A — identity

Allowed metadata only:

- Hermes revision/version if safely available;
- bridge contract/schema version;
- caller-supplied safe `profile_id`.

Do not serialize absolute home paths, hostnames or environment dumps by default.

### Candidate facet B — config health

The experiment must distinguish:

```text
config loader returned data
```

from:

```text
active config parse failure / fallback / degraded interpretation
```

A returned dict is not by itself proof that the current user config parsed successfully.

### Candidate facet C — effective config

Serialize only an explicit allowlist of fields needed for comparison, for example:

- primary model provider/model;
- fallback model provider/model;
- auxiliary vision/compression provider/model;
- declared MCP names + transport class, if obtainable without connecting;
- configured custom-provider identities;
- selected non-secret routing metadata.

Forbidden as the primary safety mechanism:

```python
json.dumps(config)
vars(runtime)
repr(runtime)
```

or equivalent broad serialization followed by best-effort redaction.

The safety boundary is **allowlist extraction**, not recursive cleanup after the fact.

### Candidate facet D — runtime route

May experimentally call Hermes runtime resolution, but the bridge may emit only approved non-secret fields, such as:

```text
provider
requested_provider
model identity
api_mode
sanitized endpoint identity/class
credential_present (boolean or tri-state)
credential_source_class (if safely known)
```

Raw API keys, tokens, headers and credential objects are forbidden even transiently in the serialized result object.

If canonical route resolution requires effects outside the regular budget, this facet should become `unsupported` or be assigned to a future higher tier rather than weakening C0 safety rules.

### Candidate facet E — provider registry (negative-control / observation)

Provider discovery is **not** presumed safe for regular mode.

C0 should intentionally test whether first access to provider profiles executes bundled/user/pip provider plugin code. If executable discovery is observed, record it and reject this facet from regular-mode bridge scope.

A RED observation here can be the correct experimental outcome.

### Credential metadata model

Keep these concepts separate:

```text
credential source configured
credential resolved/present
credential value
```

Argus may receive only the first two where demonstrated safe. It never receives the third.

If resolved presence cannot be obtained canonically without secret hydration or other forbidden effects, report it as unsupported in regular mode.

## 6. Two classes of tests

C0 must distinguish **MUST-PASS safety gates** from **OBSERVATION probes**.

### MUST-PASS safety gates

Failure of any item below means the current bridge design is not acceptable:

1. explicit profile isolation;
2. canary secret never appears in output/argv/logs/errors;
3. child timeout is bounded and cleanup is deterministic;
4. malformed/partial child output fails closed;
5. child crash/import error does not crash the harness;
6. output-size limit is enforced;
7. bridge cannot silently switch profile/home;
8. no production credential or live endpoint is required by tests;
9. no persistent write occurs in the baseline metadata mode;
10. no network, token refresh, external-secret helper or plugin/user-code execution occurs in any facet claimed to fit regular mode.

### OBSERVATION probes

These may legitimately demonstrate that a candidate facet is unsafe or unsuitable:

- does `load_config_readonly()` itself spawn/process/network/write under the fixture?
- how does `${ENV}` expansion behave with an allowlisted environment?
- can config parse failure/fallback be observed canonically?
- does runtime provider resolution materialize credentials?
- does runtime provider resolution cause auth/secret-source activity?
- does provider discovery execute user/bundled/pip plugin code?
- which APIs read process-global state or mutate caches?
- which imports break across synchronized Hermes revisions?

A failed observation does **not** authorize weakening a MUST-PASS gate. It changes the facet decision.

## 7. Required fixtures / adversarial matrix

At minimum:

| Fixture | Required evidence |
|---|---|
| profile A and profile B with different model/provider config | no cross-profile bleed; correct explicit-home result |
| config containing `${C0_CANARY_ENV}` | document allowlisted-env expansion behavior |
| canary secret in profile `.env` | no secret disclosure |
| malformed `config.yaml` | no false `ok`; explicit degraded/config-error observation |
| custom provider fixture | compare canonical route/config gain vs static Argus |
| runtime resolver returns/contains canary credential | only presence/source metadata emitted |
| user provider plugin writes marker file | detect plugin code execution |
| user provider plugin sleeps/hangs | parent timeout/output/kill containment |
| user provider plugin raises | facet/bridge degradation, no harness crash |
| external secret command writes marker file | detect accidental hydration/process execution |
| forced child crash before JSON | fail-closed compatibility result |
| oversized stdout/stderr fixture | hard output cap |
| two sequential child runs for distinct profiles | no cache/module-state bleed |

Where practical, add a network sentinel that proves absence of outbound connect attempts for regular-mode facets. Reviewer-side Linux tracing/sandboxing may be used; the contract fixes what must be demonstrated, not the specific tracing tool.

## 8. Coverage comparison

C0 is not successful merely because the bridge works.

For every relevant fixture/scenario, record:

```text
expected Hermes truth
current Argus integration-discover result
C0 facet result
coverage gain / no gain / regression
```

At least these current static areas should be considered:

- configured providers;
- custom providers;
- primary/fallback/auxiliary model references;
- MCP declarations;
- env references/credential presence metadata;
- OAuth/provider metadata;
- user model-provider plugins.

The final evidence receipt should summarize the number of scenarios in which static Argus is correct versus the bridge, and name the semantic gains rather than relying on a single percentage.

## 9. Compatibility surface inventory

Every Hermes seam touched by the experiment must be recorded with:

```text
module path
symbol
what it is used for
what authority it provides
observed effects
whether it is public/stable or internal/unstable
failure behavior when unavailable
```

Private/internal import paths are not treated as stable API merely because C0 can import them today.

## 10. Environment and process contract

The harness should begin from an explicit environment allowlist rather than inheriting the full maintainer/production environment.

Allow only what is required for Python/runtime operation plus declared fixture variables. In particular, tests must prove that unrelated parent secrets are not inherited into the child.

The child invocation should include explicit profile home and should avoid shell interpolation of secret material.

Conceptually:

```text
<safe-env> \
PYTHONDONTWRITEBYTECODE=1 \
HERMES_HOME=<fixture-home> \
<absolute-hermes-python> <bridge-entrypoint> --facet ...
```

The exact CLI is implementation-owned unless it weakens a frozen safety property.

## 11. Decision rules

The analyst/maintainer assigns each facet and the overall spike one of:

### GO

Only when all relevant MUST-PASS gates hold and:

- profile isolation is demonstrated;
- secret non-disclosure is demonstrated;
- regular-mode effect budget is demonstrated for the accepted facets;
- failures are bounded/degraded explicitly;
- there is measurable coverage/correctness gain over static Argus;
- the accepted Hermes seam set is small and explicit.

### MODIFY

Use when a safe/useful subset exists but broader bridge ambitions violate the contract.

Example valid result:

```text
effective_config -> GO
config_health -> GO
runtime_route -> conditional / non-regular
provider_registry -> DROP from regular bridge
credential_resolved_presence -> unsupported without hydration
```

### DROP

Use when:

- useful canonical state requires forbidden hydration/plugin/network/token effects;
- safe facets do not materially improve current Argus coverage;
- secret/profile isolation cannot be proved;
- the private API surface is too broad/fragile;
- maintaining the shim is clearly worse than bounded duplicate parsing.

## 12. Stop / contradiction rule

The experiment contract is frozen when implementation begins.

ZCode or Pytna may request an amendment only with a concrete source/runtime fact, recorded as:

```text
fact -> contract impact -> proposed amendment -> affected tests/facets
```

Do not silently weaken safety assertions to make the spike green.

A production credential, real provider mutation, token refresh or deployment is never required to complete C0. If a claim cannot be proved without such an action, mark it `not tested` / unsupported and escalate the decision.

## 13. Required evidence receipt

The final handoff to the analyst must contain:

```markdown
## Baselines
- Argus base/head
- Hermes base/head actually tested
- Python/runtime environment

## Facet results
- facet -> state -> authority -> Hermes API seam

## Safety gates
- gate -> exact command/probe -> result

## Observation probes
- probe -> observed fact

## Side effects
- network
- process spawn
- token refresh
- quota/LLM
- writes
- code/plugin execution

## Secret review
- canaries used
- stdout/stderr/JSON/argv/log scan result

## Coverage comparison
- scenario -> Hermes truth -> static Argus -> bridge

## Compatibility surface
- exact imports/symbols and stability notes

## Findings
- P0/P1 blockers
- P2/backlog

## Production
No production action performed.

## Recommendation
- per-facet GO / MODIFY / DROP proposal
- overall GO / MODIFY / DROP proposal
```

## 14. Roles

### ZCode — coding/integration agent

- implement the experimental harness/bridge in an isolated branch/worktree;
- build fixtures and executable probes;
- collect exact results;
- do not reinterpret failed observations into success;
- hand off to Pytna with the receipt above.

### Pytna — primary reviewer / maintainer gate

- run the autonomous implementation/review/remediation loop with ZCode;
- adversarially verify MUST-PASS gates;
- add process-boundary tracing/sandbox evidence where useful;
- verify exact head and evidence receipt;
- do not merge C0 into a production path merely because the spike passes.

### Agent-analyst

- does not participate in every coding loop;
- reviews the converged candidate + evidence receipt after the major iteration;
- compares results with upstream/source and this frozen contract;
- issues per-facet and overall `GO / MODIFY / DROP`;
- drafts B1b/ADR 0002 only from demonstrated facts.

## 15. Expected artifact layout

Preferred experimental layout (implementation may adjust names, but keep the spike outside deployed paths):

```text
experiments/
  c0-runtime-bridge/
    bridge.py
    harness.py
    fixtures/
    README.md

docs/
  experiments/
    c0-runtime-bridge-contract.md
  handoffs/
    c0-runtime-bridge-zcode.md
```

Do not wire the C0 code into `deploy.sh`, cron, systemd or normal Argus health/discovery execution.

## 16. Acceptance of C0 itself

C0 is complete when:

- the frozen experiment contract has been exercised;
- every MUST-PASS gate has a real result;
- every candidate facet has an authority/effect/compatibility decision;
- coverage is compared against current Argus static discovery;
- the exact Hermes seams are inventoried;
- Pytna has completed the primary verification cycle;
- the agent-analyst has enough evidence to issue `GO / MODIFY / DROP` and begin or reject B1b.

C0 is **not** complete merely when a bridge script prints plausible JSON.
