# R1b contract — keep Telegram bot tokens out of shell child argv

Status: **DONE / MERGED IN PR #31 — HISTORY / EXECUTION EVIDENCE**

Original baseline: `main` after merged R1a PR #29 (`02777a9506c6ccaa09d0b2972c0ccf13fb8e9a36`).\n\nFinal R1b merge baseline: `main = 2238928c64b9751a0cb5c8be33b7765c5c228dfd` after PR #31. No further R1b implementation is authorized without a demonstrated regression.

Read first:

1. repository `AGENTS.md`;
2. `docs/handoffs/2026-09-17-next-steps-execution-baseline.md`;
3. this contract;
4. current source/tests on the exact branch head.

## 1. Problem

Active/deployable shell notifier paths construct Telegram Bot API URLs containing a bot token and pass the expanded URL to a spawned `curl` process.

Typical current shape:

```text
curl ... "https://api.telegram.org/bot${WATCHDOG_BOT_TOKEN}/sendMessage" ...
```

The token is therefore observable in child-process argv (`ps`, `/proc/<pid>/cmdline`) for the lifetime of the request.

R1a fixed the same leak class in deploy/GitHub-heartbeat paths. R1b fixes only the remaining active **shell + child-process HTTP** instances.

## 2. Outcome

After R1b, no active/deployable shell Telegram invocation may place the expanded bot token in a spawned child argv.

Preserve the existing notification behavior of every changed path.

This is an argv-leak repair, **not** a notification architecture project.

## 3. Phase 0 — exact baseline and inventory first

Before editing, record:

```text
ARGUS_BASE=<exact main sha>
R1B_BRANCH_HEAD=<current branch sha>
```

Then inventory the current repository for active/deployable shell paths that satisfy **all** of:

1. spawn `curl` (or another child HTTP client);
2. use a Telegram Bot API URL containing a bot token value;
3. can be installed/run by current Argus modules or operational scripts;
4. therefore expose that value in child argv.

Start with repository search for `api.telegram.org/bot`, `WATCHDOG_BOT_TOKEN`, `BOT_TOKEN`, `TG_API`, and `curl`, then inspect each hit rather than assuming search results are active leaks.

Known candidates from the current repository include forms in scripts such as:

- `send-monitoring-report.sh`
- `dashboard-liveness.sh`
- `ssl-expiry-check.sh`
- `integration-discover-wrapper.sh`
- `gateway-liveness.sh`
- `check-updates.sh`
- `auto-remediate.sh`
- `watchdog-health.sh`
- `network-guard.sh`
- `health-check-v2-wrapper.sh`
- `health-check-integrations.sh`
- `hermes-watchdog.sh`

This list is a discovery hint, **not authorization to edit every file**. Confirm current activity and actual argv exposure first.

Historical/dead/legacy-only paths are reported separately and do not automatically enter the patch.

### Inventory receipt

Before implementation, produce a compact table:

```text
path | active/deployable? | invocation shape | token reaches child argv? | action
```

Allowed actions:

```text
FIX
NO LEAK
PYTHON/IN-PROCESS — OUT OF R1b
LEGACY/DEAD — REPORT ONLY
UNKNOWN — STOP/ASK MAINTAINER if material
```

## 4. Classify request shapes before patching

Do not treat every file as a unique design problem.

Group FIX call sites by observable request shape, for example:

- form-encoded `sendMessage`;
- JSON `sendMessage`;
- request whose response body/message id is consumed;
- multiple Telegram methods (`sendMessage`, `pinChatMessage`, etc.);
- retry loop / status-code capture;
- proxy vs no-proxy;
- silent notification flags / parse modes.

The exact groups come from current source. Do not invent a taxonomy larger than the code requires.

Tests should prove each **distinct shape**. They do not need one giant custom harness per file when several files are mechanically equivalent.

## 5. Preferred patch shape

Use the smallest local transformation that keeps the token-bearing URL out of argv while leaving `curl` and the existing request wiring intact.

A preferred candidate where compatible with the existing invocation is feeding the sensitive URL through curl config on stdin, e.g. conceptually:

```text
printf '<bounded curl config containing URL>\n' | curl -K - <existing non-secret argv>
```

The exact implementation must preserve current curl semantics and safely encode the config value. Do not assume a proposed form is correct without a focused real-curl parser/behavior probe.

Other local mechanisms are acceptable if they satisfy the same property without adding a shared subsystem.

### Required invariant

```text
secret/token value may exist in the shell process memory/stdin/config pipe
but must not appear in spawned child argv
```

Do not move the token from argv into a new world-readable temp file or log.

## 6. Preserve behavior exactly

For each changed request shape, preserve all behavior that currently matters, including where present:

- HTTP method;
- Telegram method/path (`sendMessage`, `pinChatMessage`, etc.);
- proxy selection and proxy type;
- connect/max timeout;
- retry count/order;
- JSON vs form encoding;
- `Content-Type`;
- chat id;
- text/message body;
- parse mode;
- `disable_notification` / silent behavior;
- response capture and HTTP-code parsing;
- message-id extraction;
- current success/failure handling.

Do not normalize inconsistent existing behavior merely because multiple files are being touched.

If an existing behavior is demonstrably broken, report it separately unless it is required to satisfy the R1b acceptance criteria.

## 7. Explicit non-goals

R1b does NOT authorize:

- a generic Telegram/notification library;
- a shared transport subsystem;
- replacing curl globally;
- retry-policy unification;
- proxy-policy cleanup;
- message-format cleanup;
- changing Telegram payload schema;
- Python `urllib` notifier rewrites where the URL is built in-process and no child argv leak exists;
- webhook/poller refactors merely for stylistic consistency;
- credential rotation;
- secret storage redesign;
- R2 discovery fixes;
- gateway-liveness redesign;
- multi-profile support;
- unrelated shell cleanup.

Do not add a new production entrypoint for R1b.

## 8. Tests / acceptance criteria

### A. Repository inventory closes the demonstrated class

After the patch, a fresh repository audit must find no active/deployable shell child invocation where the expanded Telegram bot token is passed in child argv.

Search results alone are not proof: inspect aliases/constructed variables such as `TG_API` where needed.

### B. Canary argv proof

For every distinct changed invocation shape:

- run the actual shell path or the smallest faithful function/fixture path;
- use a synthetic token canary;
- capture child `curl` argv with a PATH shim or equivalent bounded fixture;
- assert the canary is absent from argv;
- assert the expected non-secret request wiring remains present.

Do not use real credentials.

### C. Real curl seam probe

At least once for the chosen sensitive-URL delivery mechanism, exercise the installed/CI `curl` parser against a non-routable/local fixture or another mutation-safe target so tests prove the syntax actually works.

Include a negative control or mutation test sufficient to show the probe would fail if the token-bearing URL moved back into argv or the config input became invalid.

Do not contact Telegram with real credentials.

### D. Behavioral parity by request shape

For each distinct shape changed, assert the relevant preserved semantics from section 6.

Use compact fixtures. Do not create a generalized HTTP simulation framework.

### E. Leak surfaces

The synthetic token must not be newly written to:

- repository files;
- logs;
- stdout/stderr from normal test/deploy execution;
- world-readable temp files.

Protected ephemeral pipe/stdin content is acceptable.

### F. Baseline checks

Run at least:

```bash
bash -n <all changed shell files>
python3 tests/probes.py
git diff --check
```

and normal `argus-ci` on the PR head.

## 9. Scope budget

R1b may touch multiple existing shell notifier files because the demonstrated bug class is duplicated across those files.

That does **not** authorize a new abstraction merely because the edits look repetitive.

Repetition is acceptable here when the alternative creates a new production subsystem.

Before adding any shared helper/source file, STOP and return this evidence to the maintainer:

```text
number of active call sites
number of distinct request shapes
why local transformations are unsafe or unmaintainable
proposed shared boundary
new production coupling introduced
```

No shared helper is authorized by this contract.

## 10. Review instructions — Pytna

Review the exact committed PR head against this contract, not against a broader idealized notification architecture.

Focus on:

1. any remaining active shell token-in-child-argv leak;
2. malformed/unsafe curl-config or stdin delivery;
3. behavior drift in request shapes actually changed;
4. token migration into logs/temp files;
5. false-success/failure handling introduced by the patch;
6. tests that can pass while the leak remains.

Use mutation/failure injection when it directly tests those properties.

Do not request:

- generic notification abstractions;
- Python notifier rewrites without argv evidence;
- unrelated retry/proxy/message cleanup;
- expansion into different secret surfaces not implicated by the changed code unless a direct regression is demonstrated.

One focused review -> at most one remediation by default. A second remediation requires an explicit maintainer decision.

## 11. ZCode implementation receipt

Before review, return:

```markdown
## R1b outcome

## Exact baseline/head
- base:
- head:

## Inventory
| path | active | shape | argv leak | action |

## Request-shape groups

## Changed files

## Secret delivery mechanism

## Preserved behavior

## Tests
- argv canary:
- real curl seam:
- negative/mutation control:
- behavior parity:
- full probes:
- CI:

## Leak review

## Out-of-scope findings

## Production actions
No production action performed.

## Recommendation
READY FOR PYTNA | BLOCKED
```

Before final merge recommendation, refresh the PR body/evidence receipt so it describes the exact candidate head after remediation, not the initial implementation.

## 12. Stop conditions

STOP and return to the maintainer if R1b requires any of:

- a generic/shared notification transport subsystem;
- a new dependency;
- a new daemon/service/production entrypoint;
- broad request-semantics changes;
- credential-store redesign;
- unexpectedly invasive changes outside shell notifier paths + focused tests/docs;
- a second remediation cycle without explicit maintainer approval.

A concrete out-of-scope bug should be recorded as a follow-up; it does not grant permission to absorb that work into R1b.
