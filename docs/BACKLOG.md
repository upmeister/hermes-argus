# Project backlog

This file is the repository's durable backlog for known technical debt,
deferred maintenance, and follow-up work discovered during implementation or
review. The repository remains the source of truth; a GitHub issue is an
optional working handle for a task, not a second canonical backlog.

## How to use it

Add a finding as soon as a builder or reviewer identifies it and the finding is
outside the active contract or intentionally deferred. Each entry records the
source, the reason it is deferred, and the trigger that should bring it back.

Use a GitHub issue when a task needs discussion, an implementation PR, or a
visible external report. Link the issue here when one exists. Close or update
the backlog entry in the same change that changes its status.

Release gates and active implementation contracts stay in
[`docs/ROADMAP.md`](ROADMAP.md) and
[`docs/handoffs/README.md`](handoffs/README.md). Do not duplicate their
acceptance criteria here.

## Open items

### DEBT-001 — adopt `hermes mcp test` exit-code semantics

- **Status:** deferred maintenance
- **Source:** PR #59 focused review; Hermes stable v0.21.5
- **Evidence:** the `check_mcp` comment still describes the exit code as
  always zero, while supported Hermes returns `0` for connected, `1` for a
  connection failure, and `3` when the server is missing.
- **Required follow-up:** correct the stale comment and decide whether Argus
  should use the exit code as an additional signal while preserving the
  established output-marker compatibility path.
- **Trigger:** schedule as a separate maintenance task before changing
  `check_mcp`, or when Hermes changes the command contract again.
- **Scope guard:** do not fold this into MCP disabled-server handling or an
  unrelated health-check change.
