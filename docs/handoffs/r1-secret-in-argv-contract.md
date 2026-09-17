# R1 parent contract — demonstrated secret-in-argv paths

Status: **R1a DONE / R1b SPLIT TO DEDICATED CONTRACT**

This file is the parent record for the R1 secret-in-argv work. Do not use it as the primary implementation brief for new work.

Current state:

- **R1a deploy/GitHub-heartbeat argv exposure:** DONE, merged in PR #29 (`main` squash `02777a9506c6ccaa09d0b2972c0ccf13fb8e9a36`).
- **R1b active shell Telegram argv exposure:** NEXT, use `docs/handoffs/r1b-telegram-secret-argv-contract.md`.

## Original problem classes

Argus demonstrated two concrete classes of secret exposure to process listings:

1. `deploy.sh` put secret substitution values in child argv and GitHub heartbeat provisioning/push paths carried secret values in argv;
2. multiple active shell Telegram notification paths put bot tokens inside request URLs passed to `curl`.

R1a closed class 1. R1b owns class 2.

## R1a outcome — complete

Primary owner was `deploy.sh`.

Merged behavior:

- template substitution values, including secrets, are fed through a protected temporary sed script and `sed -f` so child argv contains only the script path;
- GitHub heartbeat secrets are fed to supported `gh secret set` stdin semantics rather than secret-bearing argv;
- heartbeat push uses an in-memory git credential helper instead of a token-bearing URL;
- explicit failure gating prevents failed secret provisioning from reporting the heartbeat ready.

R1a is closed unless a concrete regression is demonstrated.

## R1b — use the dedicated contract

The remaining shell Telegram leak class has a broader duplicated owner surface and therefore has its own bounded implementation/review contract:

```text
docs/handoffs/r1b-telegram-secret-argv-contract.md
```

That contract requires inventory-first classification, fixes only active/deployable child-argv leaks, preserves existing request semantics, and forbids creating a generic notification subsystem.

Do not implement R1b from the looser candidate list below without reading the dedicated contract.

## Historical R1b discovery hints

Known shell candidates included scripts such as:

- `scripts/send-monitoring-report.sh`
- `scripts/dashboard-liveness.sh`
- `scripts/ssl-expiry-check.sh`
- `scripts/integration-discover-wrapper.sh`
- `scripts/gateway-liveness.sh`
- `scripts/check-updates.sh`
- `scripts/auto-remediate.sh`
- `scripts/watchdog-health.sh`
- `scripts/network-guard.sh`
- other enabled shell paths found by repository search for `api.telegram.org/bot`.

These are hints only. Current source must determine whether each path is active and whether a token really reaches child argv.

Python `urllib` paths do not automatically count as argv exposure because URL construction occurs in-process. Do not rewrite them merely for consistency unless a concrete child-process leak is demonstrated.

## Shared R1 invariants

- no real credentials in tests/reports;
- synthetic canaries prove the actual leak surface;
- notification/deploy behavior is preserved unless an existing demonstrated bug must be fixed for correctness;
- no generic notification or transport framework;
- no credential rotation/storage redesign;
- `argus-ci` remains green;
- production actions require separate authorization.

## Stop condition

If a remaining secret-in-argv fix requires a new shared transport subsystem or broad behavioral rewrite, stop and return the inventory + blocker to the maintainer instead of widening R1 automatically.
