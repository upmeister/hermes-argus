# B — existing delivery and evidence correctness

Status: **implemented on one task branch, Codex review pending**. Base:
`f30ef67de81eaf3c162be002a38e0b37a7b31e70` (main after the contract A
merge). Production risk: **medium** (existing delivery paths and operator
verdicts).
Merge authority: **maintainer after Codex PASS**. Reviewer: **Codex**.
One PR, three local fixes; no deployment or live notification tests.

## Problem -> evidence -> smallest patch

[DEBT-014](../BACKLOG.md#debt-014): Cronping/DMS ping secrets occur in curl
argv. [DEBT-013](../BACKLOG.md#debt-013): liveness cron senders do not load the
configured Telegram proxy, and the update notifier does not apply it.
[DEBT-019](../BACKLOG.md#debt-019): `/watchdog` marks any readable Analyzer
state green even when its successful collection timestamp is stale.

Reuse the existing curl stdin configuration pattern, load/apply the existing
proxy in the named senders, and add a timestamp decision to the existing
Analyzer UI consumer. No new entrypoint, dependency, notification abstraction,
configuration knob or persistent state is admitted.

Owning paths: `scripts/heartbeat.sh`, `scripts/gateway-liveness.sh`,
`scripts/dashboard-liveness.sh`, `scripts/check-updates.sh`, Analyzer rendering
in `scripts/webhook.py`, targeted probes and accompanying status/docs. Follow
all callsites within those senders (including recovery) so the same defect
does not survive in a sibling path. Other runtime findings are reported.

## Behavior and acceptance

| ID | Behavior | Discriminating evidence |
| --- | --- | --- |
| B1 | Cronping/DMS URLs travel only through stdin curl config; retain existing method, timeout, success/failure and backend-selection semantics | Stub curl records argv and protected stdin separately: token canaries absent from argv/output/logs, intended URL delivered unchanged, both backend failures still visible |
| B2 | Existing `TELEGRAM_PROXY` configuration reaches gateway/dashboard alert and recovery sends, plus update notification | Cron-like empty environment plus configured `.env` uses the proxy; absent proxy uses direct mode; quoted values retain the existing convention; no new personal default |
| B3 | Secret-bearing Telegram URL/header fields remain out of argv while B2 changes transport | Canary assertions cover all named sending branches, direct/proxy mode and failures; transport settings are not dumped in receipts |
| B4 | Analyzer freshness reflects successful collection timestamp, not file mtime | Fresh success remains fresh; an old valid state is visibly stale/neutral, preserving its timestamp and issues; a newly touched stale file remains stale |
| B5 | Missing/malformed timestamp, future timestamp, absent/unreadable state | No green success; explicit unavailable/invalid evidence, with absent-module behavior preserved; no clearing watchdog failure counters or writing collection state |

Architectural choice for review: reuse the watchdog's existing **7200 seconds**
as the UI freshness bound, without a new setting. Let `age = now_utc -
last_check_utc` in seconds, using the timezone-aware ISO timestamp (accept
`Z`/offset). `0 <= age <= 7200` is fresh; `age > 7200` is stale; negative age,
missing timezone or invalid timestamp is unavailable/invalid. A green mark
describes collection freshness, not absence of active issues or proof that
the external Hermes L3 job delivered anything. Keep active issue warnings.
Do not change the producer, its on-failure last-good preservation, or the
watchdog's own thresholds/hysteresis.

Boundary examples, evaluated at a fixed clock:

| Age (seconds) | UI freshness |
| --- | --- |
| -1 | invalid/future, not green |
| 0 | fresh |
| 7199 | fresh |
| 7200 | fresh |
| 7201 | stale |
| unparsable / timezone absent | unavailable, not green |

The accepted plan included a diagnosis of two production failed checks.
Track that separately under [DEBT-027](../BACKLOG.md#debt-027) and the Ops
checkpoint. Their unknown cause does not authorize unrelated fixes in B.

## Verification and handoff

Demonstrate B1, B2 and B4 RED on the baseline and GREEN on the candidate, using
existing fixture infrastructure and stub transports. No real provider/network
request or Telegram message is a test fixture. Run repository minimum checks,
`bash -n` on all changed senders, compile the changed Python consumer and run
required `argus-ci`. Test the actual shared rendering used by Telegram/Discord,
not a second implementation in the test.

Receipt: exact base/head, B1–B5 evidence, the timestamp boundary cases, changed
send branches and resolved-source versus deployed status for DEBT-013/014/019.
Reviewer checks credentials in argv on both success/failure paths, silent
proxy fallback, age rounding/boundaries and green states built from stale or
invalid evidence. One remediation maximum under the programme rules.

Keep backend activation by existing credential sets, GH heartbeat template
behavior, native Cronping setup, L3 provisioning, localization, network-guard
rollback reporting and Discord deepcheck ownership outside this PR. After
merge the next gate is production reconciliation; no automatic deployment.
