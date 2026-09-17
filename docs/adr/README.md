# Architecture decision records

## Current authority

- `0001-integration-evidence-policy.md` — **active policy** for evidence/verdict discipline where applicable.
- `0002-hermes-discovery-sync-boundary.md` — **historical evidence / superseded implementation direction**.

ADR 0002 remains valuable because it records C0 findings about Hermes config loading, plugin/provider execution, credential semantics and process isolation. Its C1a/C1b production migration direction was superseded by the 2026-09-17 stabilization decision after PR #27 demonstrated an unfavorable value/complexity ratio.

Current implementation authority is:

```text
AGENTS.md
+ docs/handoffs/2026-09-17-next-steps-execution-baseline.md
+ one maintainer-selected active task contract
```

Do not resume C1/C1a/C1b or infer authority cutover from ADR 0002 without a new explicit maintainer decision.
