# Production deployment checklist

Production lives on `peetna-aws`. The maintainer authorizes every deployment;
review PASS or merge does not authorize it. The preferred execution path is
the resident Pytna agent through the Peetna MCP, because it has the production
runtime context. A local SSH/Linux deployment is a fallback for the
maintainer.

## Ops receipt — 2026-10-26

**Checkpoint complete.** The maintainer authorized device tests and deployment
after PR #78. Codex selected current merged `origin/main`
`17b3975927cec11783a314f68e614e7a4d12bb1c`, with successful
[main CI](https://github.com/upmeister/hermes-argus/actions/runs/40255461991).
The resident agent performed the initial inspection. Its deployment run was
cancelled while waiting for a model response, before any deployment command;
Codex then deployed over SSH at **02:05:10 UTC**.

Production risk: **high**, separately authorized by the maintainer. This
documentation receipt has no additional runtime effect. The target contains
RR1a, both RR1b slices and contracts A/B; it is not an authorization to start C.
Here device tests mean checks on the production host; no separate peripheral
device was identified or tested.

- **Before/backup:** old checkout `2588581`; protected backup and before-values
  at `~/.hermes/cache/scratch/argus-ops-20261026T020459Z/` (owner-only).
  It contains exact prior file copies with directory hierarchy, hashes/modes,
  crontab, deploy config, unit properties and the old logrotate policies.
  Private configuration and raw outputs remain on the host, outside Git.
- **Configuration/ownership:** deploy config changed from `664` to `600`.
  CORE, INTEGRATIONS, TG_BOT, DISCORD_BOT, ANALYZER, HEARTBEAT and LOCAL_SERVICES
  retain ON; NETWORK_GUARD was made explicitly ON to preserve the existing
  operational dependency. GH_HEARTBEAT module stays OFF. No Hermes update,
  credential mutation, linger/sudoers change or network-policy change occurred.
  The quick-checker customization was the already-merged removal of the global
  cron-count heuristic; the target retains it. Canonical discovery watcher was
  already active; the inactive legacy watcher needed no migration.
- **Payload:** `deploy.sh` exited 0 and validated 41 deployment writes (including
  repeated shared payloads). An independent comparison matched **35 distinct
  script/unit artifacts** to rendered templates, plus the installed registry
  byte-for-byte to repository `registry.yaml`; no unresolved markers remained.
  Existing Hermes gateway/dashboard base units were preserved.
- **Host/services:** user manager reachable, `Linger=yes`, actual adapter check,
  CLI version and gateway matcher all return 0 on installed Hermes v0.22.5 /
  `bf0203a`. The selected launch path is the published managed launcher
  `~/.hermes/hermes-agent/.hermes/bin/hermes`; legacy venv binaries also remain
  installed but are not the adapter's selected boundary. `daemon-reload`
  completed; Telegram poller and Discord bot restarted
  at 02:05:10 UTC and remained active with zero restarts. Gateway/dashboard PIDs
  were unchanged, memory limits were read back, `NeedDaemonReload=no`, and the
  configured dashboard `/health` returned 200.
- **Log rotation:** the new Argus policy owns 20 explicit paths. Only those
  exact overlapping path lines were removed from the backed-up operator policy;
  its 18 unrelated paths and their policy remain. Individual and global
  `logrotate --debug` checks exit 0; the host logrotate timer is active. No live
  log rotation was forced.
- **Inventory/Analyzer:** discovery exits 0 with status `ok` and 40 entities;
  collector is executable, Analyzer `--update` exits 0 and advances `last_check`.
  The deployed `/watchdog` handler renders Analyzer freshness as `fresh`.
  This does not prove a separately configured Hermes L3 analysis/delivery job.
- **Bounded integration smoke:** no MCP process checks or auth refreshes;
  49 checks: 40 healthy, 2 failed, 2 unconfigured, 5 skipped. Two Telegram
  read-only `getMe` checks pass through the configured route. The same cached
  catalog failures persist: authentication rejection (401) and absent catalog
  routes (404). They remain failures, with configuration/endpoint remediation
  deferred under [DEBT-027](BACKLOG.md#debt-027); no inference about model-call
  success or OAuth runtime health is made.
- **Registry comparison:** the generated v0.22.5 registry has 153 upstream + 9
  kit entries; repository/runtime registry has 154 upstream entries. All 52
  checks built for the current inventory are identical with either registry.
  Source/runtime deployment equality passes; broader registry refresh remains
  a non-blocking source finding [DEBT-029](BACKLOG.md#debt-029).
- **Schedule survival:** one managed block; outside-block bytes match the
  protected before-copy. Real 02:10 and 02:15 UTC ticks advanced fallback and
  heartbeat artifacts; local-services refreshed on both ticks, discovery at
  02:10, and the
  network guard continued its two-minute schedule. The installed cron hash
  remained unchanged across read-backs. Analyzer's hourly producer was exercised
  manually; two hourly ticks are not claimed. Heartbeat acceptance and
  notification delivery remain separate claims: no intentional outage or
  notification send test occurred.

The rollout closes the mixed-artifact checkpoint
[DEBT-026](BACKLOG.md#debt-026). The diagnostic part of DEBT-027 is complete;
its two integrations are not declared healthy. C's admission gate is open.

## Historical restart checkpoint — 2026-10-25

RR1a and both RR1b slices are merged through PR #75. The read-only October 25
inspection found an older PR #65 checkout with mixed runtime artifacts, not a
verified deployment of those merged changes. Follow the
[restart programme Ops checkpoint](handoffs/2026-10-25-restart-through-rr1.md#operations-checkpoint)
after A/B; it does not authorize deploy or notification tests.

Before rollout, resolve the installed quick-checker's difference from source,
read the actual marked cron block, choose network-guard ON/OFF explicitly,
and record launcher, private config, linger and logrotate activation facts.
Keep operator/customized resources until their disposition is approved. Classify
cached integration failures without publishing private identities or payloads.
A future RR1c/d rollout must also follow contract C's preservation decisions.

The failure-injection scenarios below belong in isolated rehearsals by default.
Changing permissions, disabling collectors, stopping services or sending test
alerts on production requires explicit inclusion in the maintainer's authorization;
a generic read-back request does not authorize those mutations.

## Before deployment

1. Confirm the maintainer explicitly authorized this deployment and name the
   exact merged `main` SHA.
2. Reconcile the working copy with GitHub:
   `git fetch origin --prune`, then verify the intended SHA is `origin/main`.
3. Read the merged PR body, its focused-review result, and the relevant
   contract. Check that the implementation receipt and CI result refer to the
   same exact head.
4. Record any production-specific prerequisite, such as a configured module,
   an existing legacy resource, or a required migration step. Do not infer
   production state from a clean local checkout.

For a new machine or a changed module set, read the
[dependency audit](research/2026-10-03-production-deployment-dependencies.md).
Verify the actual interpreter's packages, expected dashboard/Netdata services,
configured delivery route, optional external heartbeat and user-manager
persistence. Netdata API success is not notification delivery evidence, and
Analyzer state freshness is not proof that a Hermes L3 analysis job is installed.
Record log rotation and network-guard privileges/applicability separately.
RR1b now enforces its declared host prerequisites in source; external service,
account and L3 setup remain operator-owned. Verify the installed behavior,
not merely the presence of the newer source contract.

## RR1b module/runtime truth read-back (after the first RR1b deploy)

RR1b changes which files an enabled module owns and what the quick check
considers a failure. These are the observable consequences to read back on the
production host:

1. **Netdata / GitHub expectation.** If this host runs a Netdata agent, the
   quick check and `/watchdog` must still report it when the API stops
   answering. If a surface is genuinely not configured, it must be silent
   rather than reporting a failure. Verify both directions — a check that only
   ever passes is as wrong as one that only ever fails.
2. **Analyzer collector.** With `MODULE_ANALYZER=ON`, confirm
   `~/.hermes/scripts/collect-metrics.sh` exists and that
   `python3 ~/.hermes/scripts/health-analyzer.py --update` exits `0`. Then
   confirm the failure path is honest: temporarily make the collector
   non-executable (or point it at a non-zero exit) and verify the run exits
   non-zero with `ANALYZER_COLLECTOR_FAILED` and that `health-state.json`
   `last_check` does **not** advance. Restore afterwards.
3. **Legacy collector copy.** RR1b stops deploying `~/scripts/collect-metrics.sh`.
   An existing copy is left in place but is no longer owned by Argus and no
   longer read by the Analyzer; it may be removed by the operator once the
   canonical copy is confirmed working.
4. **Discord (only if `MODULE_DISCORD_BOT=ON`).** Confirm `~/scripts/webhook.py`
   exists and was refreshed by this deploy, and that deploy reported the
   `discord-venv` import check. If it warns about missing imports, install them
   into the venv the unit runs and re-check.
5. **Core-off installs (only if `MODULE_CORE=OFF`).** `deploy.sh` must print
   `✅ payload проверен: N файл(ов)` and `install.sh` must reach its completion
   text with `payload: проверен deploy.sh`. A raw `No such file or directory`
   from `bash -n` indicates a gate that never ran correctly.
6. **Deploy fails on a bad payload.** Confirm the deployer's own check is real:
   a deployed file with a syntax error, or a manifest source missing from the
   repository, must make `deploy.sh` exit non-zero with `❌ payload не прошёл
   проверку` / `❌ Манифест требует …`, and `install.sh` must abort with no
   completion text. This is the property that replaced the installer's own
   artifact list.
7. **Discord interpreter check (only if `MODULE_DISCORD_BOT=ON`).** Deploy must
   print either `✅ discord-venv импортирует discord + yaml` or a named
   missing-import warning. If it reports that the import check itself could not
   run, the deploy fails and the module must not be started.

## RR1b host-readiness read-back (after the host-readiness deploy)

The deploy now stops, before writing anything, on a host it cannot honestly
support. Every stop below is intentional — do not "fix" it by relaxing the
check without a maintainer decision.

1. **Private config.** The deploy-time config must be a regular file owned by
   the installing user with no group/other permissions:
   `stat -c '%U %a' config.env` must show your user and `600`. The installer
   creates it owner-only; a group/other-readable or foreign-owned file stops the
   run with the violated property and a repair command (`chmod 600` / `chown`)
   and never echoes configuration values. A symlink is refused at the config
   location on every entry point — including a dangling one on the default
   no-argument path, which would otherwise look like "not found" and fall
   back to environment variables — and an explicitly passed config path that
   does not exist is an error, not a silent environment-variable fallback
   (the no-argument default path keeps the env fallback for a genuinely
   absent file).
   **Production action:** existing production `config.env` is probably `644` —
   run `chmod 600 config.env` before the first host-readiness deploy.
2. **User manager and linger.** Modules that install systemd *user* units
   require a reachable user manager. The deploy prints `linger: yes` only when
   `loginctl show-user "$USER" -p Linger` really is `yes`; on `no` it stops and
   prints the manual action, on unknown it warns that reboot persistence is not
   guaranteed and continues. Argus never runs `loginctl enable-linger` itself —
   check the unit journal to confirm no such call was made.
   **Production action:** if `Linger=no`, the deploy stops before writing any
   unit — there is no "proceed anyway" path. Enable linger manually
   (`sudo loginctl enable-linger "$USER"`) and re-run the deploy; without it
   the deploy refuses to install units it cannot promise to keep running.
3. **Hermes home and target.** For modules that read Hermes-owned paths, read
   back the launch boundary Argus actually uses: on a managed Hermes install
   (v0.22.5+) the published launcher `~/.hermes/hermes-agent/.hermes/bin/hermes`
   resolved by `~/scripts/hermes-runtime.py check`; on a legacy install the
   in-tree `~/.hermes/hermes-agent/venv/bin/{hermes,python}`. Also read back
   the configured `HERMES_HOST` / `HERMES_PORT`. An explicitly empty
   `HERMES_HOST` or a non-integer/out-of-range port is an error, not a silent
   fallback to `127.0.0.1:9119`. ANALYZER does not use the Hermes runtime but
   does require
   the Hermes home directory to exist (it deploys into `~/.hermes/scripts` and
   reads `~/.hermes/logs`) and a system `python3` that actually executes a
   trivial run before anything is written — presence in `PATH` alone is not
   accepted. A stopped
   dashboard is a runtime observation and is not repaired here.
4. **Network guard.** `MODULE_NETWORK_GUARD` is recorded separately from CORE
   and is OFF by default. With OFF, confirm no network-guard entry exists in the
   managed cron block and that `~/scripts/network-guard.sh` was not freshly
   installed. With ON, the deploy fails closed unless `resolvectl` and `ip`
   exist and `sudo -k -n -l <command> <arguments>` succeeds for each probe —
   nothing executed, sudo output not parsed. The flags each carry weight: `-k`
   ignores the invoking user's cached sudo timestamp (with a live timestamp a
   PASSWD rule would otherwise pass the check and fail in cron), `-n` turns a
   password requirement into a failure instead of a prompt, and `-l` only
   lists applicability.
   The probe set is two families. Three probes repeat the invocations the
   guard builds today (`resolvectl revert <candidate-iface>`,
   `ip route flush table 4294967295`, `ip rule del from 127.0.0.1 lookup
   4294967295`). Three sentinel probes use arguments no meaningful granular
   grant would list (`resolvectl revert argus-preflight-sentinel`,
   `ip route flush table 4294967293`, `ip rule del from 203.0.113.1 lookup
   4294967293` — TEST-NET-3). The guard's runtime argument space is unbounded:
   it reverts any future interface, flushes any table named by a foreign rule
   and deletes arbitrary foreign rules. A finite probe set proves
   applicability for the six probed invocations and nothing beyond them — it
   cannot prove unbounded coverage. A grant pinned to specific arguments
   fails the sentinels on a host whose default policy denies unlisted
   commands (the common case); it can still pass where the host's blanket
   policy (for example `NOPASSWD: ALL`) or an explicit enumeration covers the
   sentinel arguments. The grant MUST use argument masks (`revert *`,
   `route flush table *`, `rule del *`) — exactly the form the deploy prints
   in its repair instruction — so the unbounded runtime space is covered by
   construction rather than enumeration. Refused, and therefore a failed
   deploy: a denied command, a `(nobody)` run-as, a grant that does not cover
   the sentinel probes, or a password-requiring grant. No rollback is
   executed and no route, DNS, interface or sudoers entry is mutated by the
   deploy.
   **Boundary:** the `-k/-n/-l` exit-status behavior is verified against real
   sudo 1.9.15p5 (CI fixture) and 1.9.17p2 (local fixture). Other sudo
   implementations (including sudo-rs) and older versions are outside this
   evidence — verify the grant manually before switching the guard on there.
   **Production action:** if this host relies on the guard, set the flag
   explicitly in `config.env` before deploying — the default is deliberately OFF
   and no automatic migration is performed.
5. **File-log rotation.** Confirm `~/.hermes/argus-logrotate.conf` exists and
   was ACTIVATED as `/etc/logrotate.d/argus` (the deploy fails rather than
   reporting success if it could not activate it), enumerates the Argus file
   logs explicitly — Hermes-owned `agent.log` and `gateway.log` must not appear
   in the rotated set — and uses `daily` with `rotate 7` and `maxsize 50M`,
   `compress`, `delaycompress` and `copytruncate`. The parser run happens in
   the preflight, before the deploy writes anything: an unusable `logrotate`
   stops the install with no files deployed. The preflight also performs one
   real write probe: it installs a temporary, valid, empty logrotate policy
   into the scheduler directory through the same mechanism the activation will
   use and removes it immediately. A grant that covers `install` but not the
   target directory, or a read-only scheduler directory, therefore stops the
   deploy before any unit is written; if the probe file itself cannot be
   removed (a grant without `rm`), the deploy prints its path and the
   instruction to delete it — the leftover is a valid empty policy and does
   not break the host scheduler. The probe path is fixed; if something already
   exists there, the deploy stops without writing or removing anything, so a
   pre-existing scheduler-directory file is never overwritten. Confirm with
   the host scheduler
   that rotation actually runs (`logrotate --debug /etc/logrotate.d/argus` must
   exit 0). systemd journal retention, Hermes log ownership and unrelated
   `/var/log` files stay external.
6. **No production-side effects beyond the authorized deploy.** Do not enable
   linger, alter sudoers, change network policy or rotate live logs as part of
   this read-back unless the maintainer separately authorizes it.

## RR1a cron read-back (after the first RR1a deploy)

1. Confirm the managed block is present exactly once:
   `crontab -l | grep -c "# BEGIN HERMES-ARGUS"` must print `1`.
2. Confirm the enabled-module jobs are inside the block and match the
   generator proposal (`CRON_FILE`, if it exists) line for line.
3. Confirm unrelated operator jobs, comments and environment declarations
   survived verbatim, in their original order, outside the block — including
   external wrapper/sync/backup jobs and saved Hermes `no_agent` entries.
4. Confirm no Argus-generated job remains outside the block (legacy forms are
   adopted once); if the deploy reported ambiguous same-script lines, review
   them with the operator before removing anything manually.
5. Rollback path: the pre-RR1a crontab content is recoverable from the
   operator's saved `~/.hermes/backups/crontab-known-good.txt` **manually
   only** — no Argus component installs it automatically anymore.

## RR0c operator migration steps (before the first RR0c deploy)

These steps keep the existing maintainer production behavior unchanged when
the public defaults flip. Run them once on the production host, before
deploying the RR0c baseline:

1. **Telegram egress proxy (B1).** RR0c removes the implicit
   `http://127.0.0.1:8444` fallback: unset `TELEGRAM_PROXY` now means direct
   access. If the host relies on the local smart proxy, add
   `TELEGRAM_PROXY=http://127.0.0.1:8444` to `~/.hermes/.env` and read it back
   (for example via the bot `/settings` view: the value must be shown as set).
   Rollback: unset the variable — all components return to direct access.
2. **GitHub heartbeat repository (B2).** RR0c removes the personal
   `GITHUB_REPO` default: with the variable unset the GitHub heartbeat backend
   stays disabled. If the heartbeat repo is in use, keep/verify
   `GITHUB_REPO=<owner/repo>` in `~/.hermes/.env`. Rollback: unset the
   variable — the backend disables itself.
3. **Discovery unit names (B3).** RR0c installs canonical
   `hermes-argus-config.path`/`hermes-argus-discover.service` files but does
   not touch the active legacy `hermes-vps-kit-*` units. The handoff is
   operator-controlled at any convenient moment:
   `systemctl --user disable --now hermes-vps-kit-config.path` then
   `systemctl --user enable --now hermes-argus-config.path`. Rollback: the
   reverse swap. Until the handoff, discovery continues through the legacy
   unit and the cron fallback.

## Deploy

1. Use the resident production agent on `peetna-aws` when available.
2. Run the repository's `deploy.sh` from the authorized merged checkout with
   the intended module configuration.
3. Keep secrets in runtime files and environment input. Do not put secret
   values in commands, process arguments, PR text, or logs.

## Read back the result

1. Compare installed runtime files with the repository templates and generated
   registry output. Confirm that no `@MARKER@` placeholder remains.
2. Inspect the relevant systemd user units, timers/path units, cron entries,
   and service state. A successful shell exit is not deployment evidence.
3. Run the smallest bounded smoke for the changed module. For monitoring
   changes, read the generated report/log and verify that the expected
   watchdog or health-check path actually ran.
4. Confirm that unrelated operator cron entries, legacy state, and disabled
   modules were not changed.

## Close-out

1. Record the deployed repository SHA, UTC time, executor, changed module, and
   smoke result without recording secrets or production response payloads.
2. If read-back fails, stop and report the concrete failure. Do not silently
   retry a migration or broaden the deployment.
3. Update the state documents in the same change when the deployment changes
   release or contract status.
