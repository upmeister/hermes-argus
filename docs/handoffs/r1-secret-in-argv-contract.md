# R1 contract — remove demonstrated secret-in-argv paths

Status: **READY FOR IMPLEMENTATION**

## Problem

Argus currently exposes some secrets to process listings by embedding them in child-process argv. Two concrete classes are already demonstrated on `main`:

1. `deploy.sh` puts `WATCHDOG_BOT_TOKEN` / related substituted values directly inside `sed -e ...` arguments;
2. multiple active Telegram notification paths put bot tokens inside the request URL passed to `curl`.

The goal is to remove those demonstrated argv exposures without redesigning deployment or notifications.

## Scope

### R1a — deploy substitution

Primary owner: `deploy.sh`.

Replace secret-bearing command-line substitution with a mechanism where secret values are not present in child argv.

Preserve:

- generated file contents;
- placeholder semantics;
- module selection;
- file permissions;
- idempotent redeploy behavior.

Non-secret substitutions may remain command-line substitutions if that is the smallest change.

### R1b — active notification paths

Audit only active production/deployable notifier paths that construct Telegram API URLs containing `WATCHDOG_BOT_TOKEN` (or equivalent bot token) and spawn a child process with that URL.

Current known shell candidates include, but are not limited to:

- `scripts/send-monitoring-report.sh`
- `scripts/dashboard-liveness.sh`
- `scripts/ssl-expiry-check.sh`
- `scripts/integration-discover-wrapper.sh`
- `scripts/gateway-liveness.sh`
- `scripts/check-updates.sh`
- `scripts/auto-remediate.sh`
- `scripts/watchdog-health.sh`
- `scripts/network-guard.sh`
- other enabled shell paths found by a repository search for `api.telegram.org/bot`.

Python `urllib` paths do not automatically count as argv exposure because URL construction occurs in-process. Do not rewrite them merely for consistency unless a concrete child-process leak is demonstrated.

## Preferred implementation shape

Use local fixes in existing files.

Acceptable examples include feeding sensitive headers/config/request metadata over stdin or a protected temporary/config file when the called tool supports it. If Telegram's token must remain in the URL by protocol design, the important property is that the URL containing the token must not appear in a spawned process argv.

Do not create a generic notification library as part of R1.

## Acceptance criteria

1. A synthetic secret marker used by tests does not appear in argv of child processes spawned by the changed code paths.
2. Existing notification payload, proxy, chat ID, parse mode, silent/non-silent behavior and retry/timeout semantics remain unchanged unless an existing test proves they were already wrong.
3. Deploy still renders the same output for ordinary placeholders.
4. No secret values are newly written to repository files, logs, stdout/stderr, or world-readable temp files.
5. `argus-ci` remains green.

## Test guidance

Tests should focus on argv capture with a canary value and behavior equivalence. Do not build a generalized taint engine.

Minimum useful probes:

- deploy substitution canary absent from child argv;
- representative shell Telegram notifier canary absent from child argv;
- no regression in generated file content / request method + payload wiring.

A repository search may be used to identify remaining shell call sites, but the task ends when active deployable leak paths are fixed. Dead/archived paths should be reported separately rather than expanding R1 automatically.

## Non-goals

- Telegram API redesign;
- switching HTTP clients globally;
- unifying all notifications;
- rewriting Python notifier code that does not leak via argv;
- rotating/replacing credentials;
- multi-profile support;
- C1 bridge work.

## Stop condition

If fixing the active shell paths requires a shared transport subsystem or widespread behavioral rewrite, stop and return the inventory + blocker to the maintainer.
