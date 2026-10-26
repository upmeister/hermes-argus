# Readiness and observation correctness

Status: **maintainer-selected next task**, 2026-10-26; implementation starts
after this docs PR merges. One implementation PR covers the local fixes and
recovery documentation below. The earlier A/B/C programme is source-complete
through PR #79 (`fd947a0`); C remains not deployed.

Production risk: **medium** — preflight decisions, process observation and
existing network-remediation reporting; no network-policy change.
Merge authority: **maintainer after Codex PASS**.
Builder: maintainer-assigned coder. Focused reviewer: **Codex**.
This contract authorizes isolated implementation/testing, not production deploy,
restart, route/DNS changes or real notifications. Refresh `origin/main` and
record the actual base; planning baseline is `fd947a06bccc8af60a9ad90f3515c7d91d9b2ed3`.

## Accepted decisions

| ID | Source | Selected behavior | Acceptance |
| --- | --- | --- | --- |
| D1 | Maintainer, 2026-10-26: accepted assessment plan, requested docs PR for its first task | One bounded correctness batch: DEBT-030, DEBT-028, DEBT-022, plus DEBT-031 recovery recipe/rehearsal | G1–G4 below; later release work is not admitted |
| D2 | Same message: local WSL/VMware for Linux tests, possible production trial at the end | Local Linux first; production is a separately authorized final operation | Target Ubuntu 24.04 evidence, exact environment receipt, no production fault injection |
| D3 | Repository invariant and DEBT-028 | Observation error is unknown, not absence or recovery | Helper rc 2 and gateway consumer preservation of prior evidence |
| D4 | Existing guard policy; accepted truthful-rollback fix | Report attempted actions and actual command results without changing policy | Per-command failure plus aggregate honest alert/state; breaker bounds unchanged |
| D5 | Contract C explicitly excludes automatic rollback | Recover the demonstrated pre-write failure manually; stop on mixed/ambiguous runtime | Documented procedure passes the original V1/V2 fixture without data loss |

Source evidence: [independent assessment](../research/2026-10-26-programme-review-and-next-plan.md),
[DEBT-030](../BACKLOG.md#debt-030), [DEBT-028](../BACKLOG.md#debt-028),
[DEBT-022](../BACKLOG.md#debt-022), [DEBT-031](../BACKLOG.md#debt-031).
The assessment's passing WSL run used Ubuntu 26.04.1/Python 3.14.4. It is
additional evidence, not a replacement for the supported Ubuntu 24.04 target.

## Problem -> evidence -> smallest patch -> owning paths

- **Managed capability:** a launcher returning executable `/bin/false` passes
  `check`, then fails `run-script`. Add one harmless bounded managed activation
  check in `scripts/hermes-runtime.py`, preserving the existing launch boundary.
  `deploy.sh` is in scope only for this capability gate/diagnostics if needed.
- **Process observation:** `live_gateway_pids()` maps failed/timed-out `pgrep`
  to an empty list. Correct this in `scripts/hermes-gateway-pids.py` and verify
  its two consumers: `scripts/hermes-watchdog.sh`, `scripts/gateway-liveness.sh`.
  The watchdog recovery loop currently treats unseen prior problems as recovered;
  preserve only the affected gateway evidence on unknown observations.
- **Rollback truth:** `scripts/network-guard.sh` ignores individual sudo exit
  statuses but logs success. Keep its operations and policy, add truthful
  per-action/aggregate reporting using transient results and existing fields.
- **Recovery:** existing C correctly refuses a retry when checkout V2 and
  runtime V1 disagree. Add the tested operator procedure to
  `docs/DEPLOY_CHECKLIST.md` and exercise it in `tests/test_lifecycle.py`.
  Runtime installer changes are not admitted by this documentation slice.

Other named paths: focused fixtures in `tests/probes.py`, relevant existing
watchdog tests, and status/operator docs. No new production entrypoint,
dependency, configuration knob, persistent state format or generalized helper
framework. Reuse existing process timeouts, launch code, counters and fixtures.

## G1 — prove managed runtime capability

After resolving the installation-bound interpreter, run a harmless capability
probe through the same managed bootstrap activation used by `run-script`.
Interpreter existence/execute permission and valid JSON alone are insufficient.
The probe must execute Python and activate the selected dependency environment;
it must not enter the Hermes CLI, run a provider/MCP check, refresh credentials,
load plugins for discovery, install/repair Hermes or contact an external API.
Normal Hermes-owned bootstrap semantics remain Hermes-owned; do not reimplement
or bypass them to manufacture a successful probe.

Use the existing finite timeout convention for both launcher resolution and
the capability subprocess, with no retries/new timeout setting. A nonzero exit,
execution error or timeout fails readiness before runtime payload/unit/cron
writes. Preserve malformed-launcher versus unavailable-runtime classifications,
the valid legacy path, and refusal to fall back from a broken published launcher.
Diagnostics expose a safe class/exit status, never raw child stdout/stderr or
credential canaries. A healthy probe makes no runtime-health/API-login claim.

## G2 — preserve unknown process observations

| Observation | Helper result |
| --- | --- |
| `pgrep` rc 0 with valid candidate PIDs; canonical matcher finds a gateway | rc 0, existing PID/count/quiet output |
| Successful candidate scan, all candidates filtered out/disappeared | rc 1, existing confirmed-absence output |
| `pgrep` rc 1 and empty output (normal no-match result) | rc 1 |
| Missing command, execution error, timeout, signal termination, rc 2/3 or another error | rc 2, classified diagnostic, no PID/count masquerading as an observation |
| Successful scan with structurally invalid/empty PID output | rc 2, not confirmed absence |

Keep the canonical matcher and installation-root filtering. A process
disappearing between candidate enumeration and cmdline read remains an ordinary
scan race; no new process-identity subsystem. Preserve the existing reexec
sentinel propagation so rc 2 survives the parent/child boundary.

In both callers rc 2 means the gateway check was unavailable. It must neither
declare the gateway dead nor start a restart because of that observation.
For an existing `gateway_proc` problem, keep its alerted/failure/recovery
counters unchanged and emit no recovery on an unknown cycle. The next valid
alive/absent sample follows existing policy. Limit this fix to gateway evidence;
do not redesign other watchdog recovery rules or the state format.

## G3 — distinguish rollback attempts, command results and observed state

Inspect every existing `sudo -n resolvectl revert`, `ip route flush table`
and `ip rule del` result. Emit a success log only for a successful invocation;
failed invocations get a clear failure record with safe command kind/status.
Do not include raw stderr, credential values or private host output in receipts.

The final notification distinguishes attempted remediation from successful
remediation and says when any action failed, including mixed-success batches.
Existing post-action DNS/rule checks are a separate observation: a clean
post-check cannot turn a failed command into a claim that Argus successfully
performed it. The existing `rolled_back` field may be `yes` only when all
attempted actions succeeded **and** existing post-checks are clear; otherwise
it remains `no`. Preserve the state schema. No new persisted per-action ledger.

Continue the existing set/order of attempted actions; no new commands, privilege
grants, route matching, retries, DNS policy, baseline capture or notification
transport. Keep `MODULE_NETWORK_GUARD` opt-in and the H4 preflight boundary.
The existing breaker counts one attempted remediation cycle, not successful
commands: preserve its current `actions_hour`/`last_action` handling, threshold
2, window 3600 seconds and reset comparison. Failed attempts must not evade
the breaker. Correct user-facing wording to say attempts where necessary;
do not change cadence, normal exit policy or introduce a new alert channel.

## G4 — document and rehearse bounded C recovery

Reproduce: install V1; select V2; fail user-manager preflight before runtime
writes; verify checkout V2/runtime V1; retry and observe ownership refusal.
Record old/selected SHAs and the failed phase from the operator's existing
receipt/Git history. Never infer the installed version from current HEAD alone.

The recipe must first prove that runtime files still match the known old source
and the checkout has no operator changes/collisions. For that proven case,
restore only the source checkout to the recorded old revision using ordinary
non-forcing Git checkout, then invoke the reviewed target lifecycle installer
from a temporary target checkout/worktree with an explicit supported selector.
This gives its ownership gate the correct old baseline while executing the
target installer. Validate these exact steps in the fixture before publishing
them as a working procedure; do not use the old installer by accident.

If there were partial runtime writes, unknown provenance or custom-file
differences, stop and report the exact reconciliation needed. This contract
does not promise general recovery of mixed installations, overwrite custom
files, stash/reset work, add a rollback flag/state DB, or run uninstall to repair
an upgrade. A protected operator backup/receipt is allowed in the local
rehearsal; no secrets or backup contents enter the repository.

## Acceptance and local evidence

| ID | Required discriminating cases |
| --- | --- |
| G1 | Valid managed and legacy; executable-but-failing interpreter; bootstrap failure; capability timeout; no stale-venv fallback; child-output canary absent; failed preflight before payload/unit/cron writes |
| G2 | `pgrep` 0/1/2/3, missing executable, timeout, malformed stdout; canonical match/filtered candidates; direct and reexec helper modes; seeded gateway failure -> unknown -> valid alive with no premature recovery/reset/restart |
| G3 | Every action kind succeeds/fails; mixed results; failed action with clear post-check; successful commands with remaining violations; no false-success log/alert/state; attempts still reach the unchanged breaker; transports stubbed |
| G4 | Demonstrated V1/V2 failure then documented recovery to correct target; private config/operator cron/files preserved; custom/mixed/unknown state stops; no new state or installer feature |

Use local **WSL or VMware on the maintainer's computer**, with disposable
Ubuntu 24.04 and its native Linux filesystem (ext4). Fixtures isolate HOME,
cron, units and route/DNS commands. Network/sudo/Telegram failure simulations
use stubs; do not apply them to the workstation's live network. One suitable
local virtualization path is sufficient; testing both products is not required.
WSL without a functional user systemd manager can run fixture checks, but must
not be reported as an actual systemd readiness rehearsal. VMware is an option
when the needed local host behavior cannot be exercised in WSL.

Show G1–G3 RED against the recorded baseline and GREEN on the candidate. G4 is
a recovery/documentation acceptance case, not a requirement to make an already
honest refusal disappear. Include one harmless managed check on an intentionally
installed supported Hermes v0.22.5 launcher in the local disposable environment;
do not download/repair Hermes on production as part of testing. Record OS,
filesystem, user, Python/Hermes versions, real versus stubbed surfaces and skips.

Run repository minimum checks, syntax for all changed entrypoints, relevant
watchdog fixtures, `python3 tests/test_lifecycle.py` and required `argus-ci`.
No extra test framework. Existing full-suite evidence is regression coverage,
not a substitute for the new failure cases.

## Handoff, review and optional production finish

Builder supplies exact base/head, G1–G4 mapping, local Linux evidence, safe
before/after outcomes, and linked backlog dispositions. Reviewer **Codex**
checks those cases and the named callers, secret channels, unchanged guard
policy/counters and the runnable recovery recipe. One focused review, at most
one bounded remediation, one exact-tree reread; then PASS-TO-MAINTAINER or
blockers. No repeated review waves or adjacent workstreams.

Before merge, prepare completion wording in the implementation PR: source
complete when merged, production still pending until its own receipt. Update
handoffs/roadmap/AGENTS/changelog/backlog/checklist and vault consistently.
Do not leave an implemented/awaiting-review pointer as the merged status.

After local tests and required CI pass, the executor may prepare a concrete
final production plan for the maintainer: exact merged SHA, whether C is
included, files/services affected, safe read-back and any requested send test.
The suggestion to try production at the end is not an authorization to choose
those mutations now. A separately authorized production trial uses positive
smoke/read-back; pgrep/sudo failures, route/DNS mutation, unavailable-runtime
injection, update interruption and uninstall remain local-only test cases.
Follow [DEPLOY_CHECKLIST](../DEPLOY_CHECKLIST.md). Production acceptance cannot
substitute for missing local evidence.

After the implementation receipt, stop. C rollout, public setup/heartbeat
policy, registry refresh, Discord payload decisions, RR2/RR3, OAuth/multi-profile,
new telemetry and gateway-liveness redesign require their own selected scope.
