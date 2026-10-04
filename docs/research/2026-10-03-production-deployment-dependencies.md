# Production deployment dependency audit — 2026-10-03

Status: **RESEARCH COMPLETE / RR1 PLANNING INPUT**

## Follow-up after RR1a — current installer planning input

The original production snapshot below is retained with its recorded baseline.
RR1a is now merged as [PR #68](https://github.com/upmeister/hermes-argus/pull/68),
but **not deployed**, per the maintainer. Its managed-cron/count/restore source
changes resolve D4 in the repository; runtime read-back remains an operator
task. Do not describe either the new cron or its removal of old recovery as
verified on production yet.

The maintainer accepted Netdata as an **optional extension**. The
[monitoring-source map](../monitoring-sources.md) shows that watchdog metrics
come from the OS and Netdata's actual data consumer is Analyzer's trend block.
Removing unintended quick-check/UI requirements is still source work.

The later heartbeat-backends audit reports separation of the dedicated
heartbeat and infrastructure clones. That supersedes the earlier legacy Git
directory observation below; other config-reader fallbacks are not thereby
verified. [Heartbeat review](2026-10-03-heartbeat-delivery-roadmap.md) preserves
that audit's facts separately from the later native-Cronping delivery decision.

This report is the consolidated input for a **later installer contract**.
It does not admit all these changes into one implementation task:

| Installer prerequisite / outcome | Remaining work | Tracking |
| --- | --- | --- |
| Optional Netdata/GitHub | Resolve absent/configured/broken reporting before adding package offers | [DEBT-007](../BACKLOG.md#debt-007) |
| Analyzer collector / standalone Discord | Supply correct files and actual-interpreter imports | [DEBT-008](../BACKLOG.md#debt-008) |
| Full L3 setup | Generic operator-created Hermes job/model/destination recipe | [DEBT-009](../BACKLOG.md#debt-009) |
| Host lifecycle and elevated actions | Dashboard applicability, linger, sudo, network policy and bounded rotation | [DEBT-010](../BACKLOG.md#debt-010) |
| Provider setup claims | Correct unimplemented provisioning/native-alert statements | [DEBT-012](../BACKLOG.md#debt-012) |
| Configured Telegram transport | Apply runtime proxy in every existing affected sender | [DEBT-013](../BACKLOG.md#debt-013) |
| External heartbeat secret channel | Keep ping tokens out of child argv | [DEBT-014](../BACKLOG.md#debt-014) |
| Explicit heartbeat backend/delivery setup | Later heartbeat cycle with native provider-bot setup guide | [DEBT-016](../BACKLOG.md#debt-016), [DEBT-017](../BACKLOG.md#debt-017) |
| Public GitHub behavior | Reconcile actual shipped workflow and claimed alert behavior | [DEBT-018](../BACKLOG.md#debt-018) |
| Installer itself | Module-specific OS/interpreter/Hermes preflight, private config, module-neutral post-deploy gates | Frozen RR1b module-runtime contract in progress; broader installer task later |

Netdata may be offered/documented without making it a baseline dependency.
No replacement time-series stack or personal proxy infrastructure is required
by this decision. The current installer still needs versioned-update and
bounded-uninstall work under RR1c/RR1d after payload/ownership are settled.

## Evidence and limits

Read-only inspection of the maintainer's production deployment on 2026-10-03
(local date; the SSH observations started on 2026-10-02 UTC): repository and
runtime templates, user/system units, user/root cron, Hermes cron job metadata,
package/import availability, notification configuration, and cached-artifact
freshness. No deploy, service restart, cron update, notification test, provider
probe, or credential refresh was performed.

```text
Argus checkout = 2588581a27234b6e0be2b38b29e39f29476d328e (PR #65 merged)
Hermes checkout = 0a374d167424cdc730ce9761368b62255b551e58
OS target = Ubuntu 24.04
```

Hermes production is a canary checkout. This observation does not replace the
supported-stable authority recorded in `AGENTS.md`, and production success
alone does not prove clean-install compatibility with supported stable.

The production Argus tracked tree was clean. All inspected manifest script
copies matched source after bounded placeholder normalization. The one unit
exception was the Hermes-owned gateway base unit, which deploy intentionally
preserves. This is a wiring audit, not a full end-to-end health certification.
Private addresses, credentials, recipient identities, raw commands/prompts,
response payloads, logs, and topology are deliberately absent from this note.

## Conclusion

**The complete production monitoring environment cannot currently be reproduced
by installing Argus alone.** Most monitoring code is shipped, but several
support services, an Analyzer collector copy, L3 scheduling, log rotation, and
operator prerequisites were supplied separately.

The smallest public product is an existing-Hermes observer with a managed
schedule and explicit optional integrations. Reproducing the maintainer's whole
host/network stack is a separate deployment project.

## Dependency and ownership map

| Component | Production evidence | Argus installation today | New-user deployment choice |
| --- | --- | --- | --- |
| Linux/systemd, user manager and cron | User services persist with linger; cron is active | Bootstrap checks `cron`; assumes systemd/user bus | Declare Ubuntu 24.04; verify user-manager availability and explain linger before claiming reboot persistence |
| Hermes checkout, venv, gateway | Installed independently; gateway unit is Hermes-owned | Argus uses Hermes executable and matcher, preserves existing gateway base unit | Install Hermes through its own workflow, then preflight its actual home/version/venv; never duplicate its runtime/credential resolver |
| Hermes dashboard | Active; Argus polls and restarts it | CORE supplies a fallback unit and memory drop-ins, but does not install dashboard dependencies or automatically activate it | Establish whether dashboard is required by the selected CORE surface; verify its prerequisites and activation rather than accepting a dormant unit file |
| OS tools/Python | Production has tools that bootstrap does not enumerate | Bootstrap explicitly checks only git, curl, python3, python3-yaml and cron | Map commands/imports per enabled module; distinguish base Ubuntu tools from optional venv, TLS, networking and provisioning tools |
| Integration discovery and v2 health-check | Current scripts and canonical config path watcher deployed | Shipped by INTEGRATIONS; most cron jobs are still proposal-only | Managed schedule plus module-aware preflight; monitored providers/MCP/plugin services remain operator/Hermes-owned targets |
| Netdata metrics/trends | Distribution Netdata Agent 1.43.2 active; API readable at the configured address | Neither installed nor offered; Analyzer consumes its data API | Optional existing Agent adoption and documented vendor installation; distinguish unavailable optional trends from an expected-but-broken Agent |
| Native Netdata notifications | Agent alarm evaluation exists; inspected notification files/runtime had no configured Telegram token/recipient | No notification provisioning; historical webhook comments describe a different configuration | Treat direct Telegram delivery as unverified; choose and configure a separate native Agent channel only when requested, with a separately authorized delivery test |
| Telegram alert/control plane | Poller and an explicit proxy are configured | Bot scripts/unit shipped; account, bot, recipient and proxy must preexist | Operator creates bot and supplies runtime credentials; direct transport is default, an existing HTTP proxy is optional |
| Personal egress stack | Smart-proxy scripts, path-manager timer, Tor, sing-box and Xray are external services | Not in Argus manifests | Keep external; use direct egress where available or an operator-provided proxy. Do not install the maintainer's routing stack as an Argus prerequisite |
| Network guard and elevated actions | Guard/baseline exist; production has passwordless sudo | Guard is in default CORE; no portable privilege or host-policy setup | RR1 must define its privileges and applicability before enabling rollback on a new host; a general multi-interface host is not evidence of a broken network |
| Analyzer raw-metrics collector | Analyzer uses an old copy in Hermes scripts, different from current source | Current collector is installed only into home scripts | Fix the consumer/manifest path in a bounded RR1b patch; installing Analyzer must also supply its actual collector |
| L3 agent analysis and delivery | An enabled Hermes cron job contains the analysis prompt and delivery configuration | ANALYZER deploys scripts and an OS-cron state update, but does not create that Hermes job | Document a separate, optional operator-created Hermes job; ship a generic recipe before advertising automatic L3 analysis. No second LLM scheduler |
| External dead-man heartbeat | Runtime credentials activate Cronping and GitHub; Git checkout uses bounded legacy fallback | Heartbeat client shipped; GH provisioning is optional and needs `gh`; DMS requires external setup | Operator provisions one backend and keys; confirm client schedule plus external alert policy. A local heartbeat cannot prove detection of complete host loss |
| Discord control plane | Dedicated venv/unit exists | Conditional `discord.py` venv install and unit are shipped; shared `webhook.py` is currently deployed only by TG_BOT | Ship/preflight shared bot dependencies even when TG_BOT is OFF; check python3-venv and PyYAML in the actual interpreter, account/token/intents |
| Local service monitoring | Consumer, snapshot and operator manifest exist | Collector/consumer and narrow cron reconciliation shipped | Operator authors the manifest; observed applications, Docker and other host services are targets, not components to install automatically |
| Log rotation | System logrotate configuration and timer exist | No logrotate template/manifest/bootstrap integration | Add bounded Argus-owned log rotation in RR1b or document a verified existing policy; scheduling alone must not imply bounded logs |
| Legacy wrappers, infrastructure sync and backups | User cron still invokes an external quick-check wrapper, infra sync, application backup and vault jobs | Not installed by Argus | Preserve them during cron migration. Operator reviews redundant wrapper/infra jobs; backups and unrelated sync remain outside Argus ownership |

Repository ownership evidence: [bootstrap](../../install.sh),
[deployment manifests and schedule generation](../../deploy.sh),
[Analyzer collector](../../scripts/health-analyzer.py),
[Netdata data API reader](../../scripts/health_netdata.py),
[quick compatibility checker](../../scripts/health-check-integrations.sh),
[network guard](../../scripts/network-guard.sh),
[remediation](../../scripts/auto-remediate.sh),
[bot status](../../scripts/webhook.py),
[heartbeat](../../scripts/heartbeat.sh), and
[systemd templates](../../modules/systemd/).

## Concrete gaps remaining after RR0

### D1 — Netdata is still an implicit default-path dependency

RR0a made the service-level self-health check conditional, but
`health-check-integrations.sh:run_quick()` still unconditionally requires a
Netdata API `200`. CORE calls that quick checker when INTEGRATIONS is ON.
`webhook.py:handle_watchdog()` also marks an absent Netdata API as failed when
Hermes exists. Thus a default CORE+INTEGRATIONS install without Netdata can
still report failure.

The same quick check requires a GitHub token even when no optional GitHub
feature was configured. Module-aware dependency reporting must cover these
paths as well as `watchdog-health.sh`; installing Netdata for everyone merely
to hide this coupling would contradict the optional-component contract.

### D2 — Analyzer collector wiring is masked by old production state

`health-analyzer.py` resolves its collector under Hermes scripts.
`CORE_HOME_SCRIPTS` places `collect-metrics.sh` under home scripts, and the
ANALYZER manifest omits it. The production Hermes-script copy exists but does
not match the current template. An empty collector stdout can be interpreted
as an absence of issues because `collect_metrics()` does not check exit status.
This is a clean-install correctness gap; do not paper over it by copying an
untracked personal file into a release fixture.

### D3 — scheduled files do not equal the complete L3 workflow

The active Hermes analysis job is separate from Argus' hourly
`health-analyzer.py --update` OS-cron job. Its prompt and delivery remain in
Hermes, which should keep owning the scheduler and provider behavior.
Installing ANALYZER currently reproduces structured state updates, not the
maintainer's complete autonomous analysis/digest workflow.

Discord has a second optional-module coupling: `discord-bot.py` imports
`webhook`, but that library is deployed only under TG_BOT. Its isolated venv
also does not inherit system PyYAML, used by the shared registry view. Existing
production with both bots enabled masks this clean-install problem.

### D4 — managed cron conflicts with historical count-based recovery

`run_quick()` flags any user crontab with fewer than seven lines, irrespective
of enabled modules. `auto-remediate.sh` can replace the whole user crontab from
`backups/crontab-known-good.txt` under the same heuristic. This can resurrect
disabled jobs and overwrite independent operator changes. RR1a must explicitly
retire these two assumptions while introducing an Argus-owned block.

### D5 — scheduling/defaults do not supply host-policy setup

The network guard's routing/DNS baseline and privileged rollback are in CORE,
but its policy reflects the personal egress environment. Netdata, dashboard
activation, sudo, linger and logrotate also have independent lifecycle/owner
requirements. These need explicit preflight/applicability decisions in RR1b;
do not infer permission to modify another user's routing from CORE being ON.

The bootstrap's syntax gate always expects the CORE watchdog file, even when
CORE is OFF. Likewise, dashboard liveness still guards the literal default
port while its HTTP target is configurable. These need explicit module/target
acceptance in RR1b, not proof supplied by old production files.

### D6 — configured delivery values are not uniformly loaded

Gateway/dashboard liveness read bot/chat fields from `.env`, but obtain
`TELEGRAM_PROXY` only from inherited environment. Their generated cron entries
do not source `.env`. The weekly update sender loads `.env` but does not apply
the explicit Telegram proxy option. Configuring a proxy in the operator's
runtime file therefore does not by itself establish consistent delivery across
these callers. This was source-checked, not tested by sending production alerts.

Cronping/DMS ping URLs still put their token-bearing URL in curl arguments
(`heartbeat.sh`). Record this existing secret-handling debt separately; the
audit does not authorize a transport patch or reading live secret argv.

## Legacy follow-up evidence

DEBT-004 cannot be closed just from the OS crontab. A disabled Hermes
`no_agent` job still references the full integration checker. The active user
cron wrapper calls `--quick`. Keep the full-mode deletion deferred until the
operator retires or migrates that saved Hermes job as well.

The canonical discovery path watcher is enabled/active and the old watcher is
absent. However the GitHub heartbeat still uses the legacy-directory fallback.
Consequently DEBT-005 is only partially migrated and must stay open.

## Public deployment recommendation

These are documentation profiles, not new module flags or installer modes:

1. **Baseline:** Hermes already installed, Argus CORE+INTEGRATIONS, managed
   schedule, declared OS dependencies and explicit Telegram alert credentials
   when delivery is desired. Netdata and GitHub checks must become
   expectation-aware before declaring this profile clean-install ready.
2. **Host visibility:** optional existing Netdata Agent, API read-back,
   Analyzer collector and Argus log rotation. Native Netdata notifications are
   a separate delivery integration, not a replacement for the Argus watchdog.
3. **L3 analysis:** the host-visibility profile plus an operator-created Hermes
   analysis job with a public recipe, configured model and chosen destination.
   Existing structured Analyzer state remains useful without that agent job.
4. **Reachability:** use direct outbound access where possible; configure an
   existing proxy where required. Keep the personal smart-proxy/tunnel policy
   independent of Argus. Telegram and Discord are alternative control planes,
   not silent dependencies of each other.
5. **Host-loss detection:** optional external heartbeat backend with its own
   alert policy. Keep application backup/vault sync outside the Argus schedule.

Retain Netdata rather than building a competing time-series collector. Its
native packages provide the Agent; direct Agent Telegram notification requires
its own channel configuration. Use the official installation/configuration
workflow and verify the API contract on the selected version:
[native packages](https://learn.netdata.cloud/docs/netdata-agent/installation/linux/native-linux-distribution-packages),
[Telegram Agent notification](https://learn.netdata.cloud/docs/alerts-%26-notifications/notifications/agent-dispatched-notifications/telegram),
[Agent notification reference](https://learn.netdata.cloud/docs/alerts-%26-notifications/notifications/agent-dispatched-notifications/agent-notifications-reference).
The audited distribution version is evidence, not a version to pin indefinitely.

The documented Cronping Management API auto-provisioning is not implemented
in the inspected deploy path. Existing token-based pinging works independently;
new-user instructions must require operator provisioning until a separate
contract supplies that feature.

GitHub provisioning additionally needs operator-installed `gh`, author identity
and a working Git upstream. `MODULE_GH_HEARTBEAT` creates assets;
`MODULE_HEARTBEAT` schedules the producer. Setup instructions placing repository
ownership only in deploy config must also establish the runtime `.env` value
read by the producer. Do not label a provisioned repository as a live backend.

For users needing only basic pressure/disk/service checks, existing Argus
watchdog checks provide a smaller alternative; they do not supply Netdata's
historical charts/trends. Prometheus/Grafana or a bundled tunnel stack would
increase the installation surface without resolving these local wiring gaps.

Systemd documents linger as the mechanism keeping a user manager available
after logout and starting it at boot:
[loginctl](https://www.freedesktop.org/software/systemd/man/252/loginctl.html).
Report this prerequisite honestly rather than enabling it during an audit.

## RR1 consequences

```text
RR0a/b/c: merged; maintainer reports deployment, checkout/wiring inspected
RR1a: managed cron and retirement of whole-crontab recovery/count heuristic
RR1b: dependency/preflight/config, Analyzer collector, optional-service truth,
      network-policy applicability, log rotation and L3 setup documentation
RR1c: versioned installation/update
RR1d: bounded uninstall/resource migration
RR2: runtime i18n
RR3: clean-install/upgrade/uninstall acceptance
```

This sequence records the audit's original planning result. RR1a is now
complete in source, not deployed. RR1b module-runtime implementation is in
progress; the broader subdivision and separate heartbeat setup cycle are
[discussion input](2026-10-03-heartbeat-delivery-roadmap.md). Findings and
release prerequisites are indexed in [the backlog](../BACKLOG.md).
