# Heartbeat delivery and RR1 review — 2026-10-03

Status: **DISCUSSION INPUT / NO IMPLEMENTATION CONTRACT SELECTED**

## Decisions and provenance

| ID | Authority | Meaning | Documentation destination |
| --- | --- | --- | --- |
| D1 | Latest maintainer message | RR1a is complete in source; not deployed yet | Roadmap and deployment status remain distinct |
| D2 | Latest maintainer message | Netdata stays an optional enhancement | Monitoring-source page, README, installer requirements |
| D3 | Latest maintainer message | Consolidate installation findings; contract the installer changes later | Existing dependency report is updated, not replaced by a second audit |
| D4 | Latest maintainer message and clarification | Plan a separate Cronping -> Telegram webhook/delivery cycle and public heartbeat setup docs | Backlog and proposed heartbeat track |
| D4a | Mid-task maintainer preference | Prefer notifications from bot Argus to avoid a second Telegram sender | Bridge is the preferred path; external hosting and delivery policy remain open |
| D5 | Latest maintainer message | Discuss the revised roadmap before new builder contracts | All new RR1 subdivisions/heartbeat config semantics below are proposals |

Input: the maintainer's vault note
`projects/hermes-argus/research/2026-10-03-heartbeat-backends-audit`, the existing
[Argus dependency report](2026-10-03-production-deployment-dependencies.md), and
repository source at `ed3661f` after RR1a / PR #68. Account/configuration
observations below are attributed to that audit; no provider/account or
production re-probe was performed for this document. Secrets, private repo
names, hostnames, recipients and response bodies are excluded.

## What changed relative to the earlier dependency report

- The later heartbeat audit reports that the dedicated GitHub heartbeat clone
  and the infrastructure-sync clone were separated. That supersedes the earlier
  observation of a shared legacy directory; do not repeat the migration or
  conclude that unrelated legacy config readers are gone.
- The audit reports working GitHub Telegram outage delivery. Cronping receives
  pings but lacks the configured Telegram integration; DMS is not active.
  A successful heartbeat ping and a configured external notification route
  are different acceptance steps.
- `MODULE_HEARTBEAT` owns the client schedule. `MODULE_GH_HEARTBEAT` controls
  optional provisioning. Current `heartbeat.sh` pings every backend whose
  credentials exist; it has no explicit backend-selection setting.
- Existing Cronping comments claim Management API provisioning that is absent
  from deploy. Public documentation must describe implemented setup rather
  than this historical claim.

These observations are evidence for configuration/setup work, not proof of a
particular future backend-selection policy. The vault design is explicitly a
proposal: one primary plus a second backend, or an explicit list, still needs
a maintainer decision. A simultaneous redundant backend is not automatic
failover simply because it is named `fallback`.

## Public GitHub template is not the production workflow

The audit describes a five-minute workflow with a ten-minute threshold,
deduplication and pinning. The repository's
[`heartbeat-alert.yml`](../../modules/gh-heartbeat/heartbeat-alert.yml) instead
checks every fifteen minutes, uses an age greater than 900 seconds, and sends
again on each stale run; it has no corresponding dedup/recovery/pin state.
Repository secret names also differ from the audited older production setup.

Do not copy private production workflow/credentials into the public template
or advertise production behavior as the new-user default. Contract the
desired public behavior explicitly and test the shipped template. This is
[DEBT-018](../BACKLOG.md#debt-018).

## Receiver placement is part of the dead-man requirement

The intended chain is:

```text
monitored host -> heartbeat backend
                       |
                  missing/recovery event
                       |
                external webhook receiver -> Telegram
```

Putting the only receiver on the monitored VPS cannot satisfy complete-host
loss delivery. Before contracting a bridge, choose another failure domain:
an independently hosted receiver or provider-native delivery. The existing
GitHub path stays separate pending that decision.

A bridge contract must settle provider event schema/authentication, bounded
payload handling, secret-safe Telegram delivery, duplicate/reordered events,
outage/recovery semantics, deployment ownership, failure reporting and a
synthetic end-to-end delivery scenario. These are admission criteria for the
requested receiver, not permission for a generalized notification platform.
Do not send real alerts or create integrations during documentation work.

## Public provider documentation re-check

The [Cronping integration guide](https://cronping.com/docs/integrations)
documents native Telegram delivery through Cronping's own bot: a dashboard
setup link opens Telegram and the user starts that bot in the target chat.
It describes OAuth for Slack/Discord, not for Telegram. This corrects the
vault audit's Telegram-OAuth description; no custom receiver is needed for
the documented provider-bot route.

The same guide documents a JSON POST webhook with example status/timestamps,
but does not specify webhook authentication, retries or ordering guarantees.
The [Management API guide](https://cronping.com/docs/management-api)
documents listing integrations and assigning existing IDs to heartbeats.
Integration-creation API capability is unverified, rather than proven absent.
The authenticated account audit must not be repeated just to answer that
documentation question.

A custom bridge provides control of the Argus sender/format but adds an external
deployment owner. The maintainer prioritizes bot Argus, making the bridge the
preferred planning path. Native delivery remains the smaller fallback option
if the maintainer later accepts a provider bot. The bridge requires no second
Telegram poller: an external handler can call
[`sendMessage`](https://core.telegram.org/bots/api#sendmessage) from bot Argus.

Its additional costs are independent hosting/lifecycle, receiving endpoint
authentication, handling duplicates/reordered recovery, and the behavior when
Telegram fails. A small synchronous handler can be sufficient, but cannot
promise durable delivery or deduplication without an explicitly scoped design.
Cronping's undocumented retry/auth properties must not become contract facts.

The [DMS webhook reference](https://deadmanssnitch.com/docs/integrations/webhooks)
documents Basic authentication, a thirty-second timeout with retry on timeout,
and unordered delivery. These are DMS facts, not Cronping guarantees; the
Cronping receiver contract must validate its own provider assumptions.

## Proposed next work, for discussion

Keep RR1a complete and keep its deployment as a separate operator task.
The existing RR1b umbrella is too broad for one implementation PR. Suggested
focused slices, with final IDs/order chosen when contracts are accepted:

1. **Runtime dependency truth:** optional Netdata/GitHub expectations, actual
   Analyzer collector, independent Discord payload/imports, consistent loading
   of the configured delivery route. Split further if owners/acceptance do not
   fit one local patch ([DEBT-007/008/013](../BACKLOG.md)).
2. **Installer preflight/config:** module-specific commands and interpreter
   imports, Hermes home/version/capabilities, module-neutral gates, private
   config, sudo contract. Use the dependency report as an explicit checklist.
3. **Host lifecycle/setup:** user manager/linger, bounded log rotation,
   dashboard expectation and network-guard applicability, plus operator-owned
   L3 setup. Do not make the personal egress stack a public prerequisite.
4. **Heartbeat cycle in parallel:** decide backend selection and receiver
   placement, then contract the selected bridge, secret-safe producer and
   public setup/verification documentation. Reconcile the shipped GitHub
   template and production claims as a separate bounded disposition.
5. **RR1c/RR1d:** retain versioned installation/update and limited uninstall/
   migration after the actual payload and ownership surfaces are settled.

RR2 runtime localization and RR3 clean-install/release acceptance remain after
RR1. A usable documented Telegram heartbeat path and the secret-argv debt need
an explicit disposition before advertising the public release. Native
Cronping provider delivery remains an alternative to the preferred Argus-bot
bridge. Hosting and failure policy are discussion choices; requesting a bridge
cycle is not an authorization to deploy it.
