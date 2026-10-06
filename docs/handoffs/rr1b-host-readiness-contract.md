# RR1b contract — installer preflight, private config and host applicability

Status: **IMPLEMENTED / FOURTH PASS PUSHED — AWAITING RE-REVIEW**. First review
by promptql (external, maintainer-selected) on head `36f4dc4` returned
BLOCKED-FOR-MAINTAINER with four in-scope blockers (H1 symlink/explicit-missing
config, H3 ANALYZER Hermes-home, H4 granular-grant false-pass, H5
`install --help` write check) plus docs fixes. The maintainer authorized one
more bounded pass; the remediation is on `feat/rr1b-host-readiness` and awaits
re-review.

This is the second focused RR1b slice. The preceding module/runtime truth
slice is merged as PR #71 and remains not deployed. This contract covers the
remaining installer and host-readiness findings that were explicitly left out
of B1–B4.

Implementation baseline: `4b74471389eaa8d6b0d4bd4f748a2c5a13524f4d` (`main`,
PR #71 merged). The builder must refresh `origin/main` and record the exact
baseline before coding.

Actual baseline used: `7245cf98076e7b643c835ad1fd0205198a0d586b` (`main` with
PR #71 merged plus the two documentation commits that followed it), branch
`feat/rr1b-host-readiness`. Not deployed.

Focused reviewer: **Codex**.

Production risk: **high** — this changes bootstrap failure conditions,
secret-bearing configuration handling, scheduled network remediation
applicability and host log retention.

Merge authority: **maintainer merge after reviewer PASS**. This contract does
not authorize deployment, service restart, privilege changes on production or
changes to the maintainer's live network policy.

## Problem, evidence and smallest patch

The clean installer currently creates an ignored `config.env` without checking
its owner or mode, calls `systemctl --user` without a prerequisite gate, and
ships the production-specific network guard whenever CORE is enabled. It also
creates several append-only files under `~/.hermes/logs` without installing or
verifying a bounded rotation policy.

The production dependency audit records the same gaps as D5 and DEBT-010. The
roadmap also requires private permissions for secret-bearing configuration and
an honest Hermes home/user-manager preflight before a public clean-install
claim.

The smallest patch is a fail-closed preflight that follows the already chosen
module manifests, one explicit opt-in for the existing network guard, private
mode/owner checks for the deploy-time config, and one Argus-owned logrotate
policy using the host's existing logrotate scheduler. It does not install
Hermes or the maintainer's egress stack and does not grant privileges.

## Decision table

| ID | Source/evidence | Agreed behavior | Acceptance scenario |
| --- | --- | --- | --- |
| H1 | `install.sh` copies `config.env`; `.gitignore` only prevents Git tracking | Create/check deploy-time config as a regular file owned by the invoking user with no group/other permissions before sourcing it; reject unsafe files without printing values | A fresh config is created owner-only; a group-readable, world-readable or foreign-owned fixture stops with an actionable error and no secret canary in output/argv |
| H2 | CORE and optional bot/discovery units use the user systemd manager; bootstrap calls `systemctl --user` unconditionally | Preflight the actual selected user-unit surfaces before writing/enabling them; require a usable user manager and report linger/reboot persistence explicitly; never enable linger automatically | A fixture with no user bus fails before the unit gate; a fixture with `Linger=no` cannot report reboot-persistent readiness; a usable manager reaches the existing unit path |
| H3 | Hermes executable/home and dashboard target are assumed by deployed templates and liveness scripts | For modules that consume Hermes-owned paths, verify the configured home, executable/interpreter capability and a non-empty host plus integer port 1–65535; do not install, start or reconfigure Hermes | Missing Hermes executable or malformed target fails preflight with the selected module named; a stopped dashboard remains a runtime observation, not a bootstrap false success |
| H4 | `network-guard.sh` encodes the maintainer's interface/routing policy and uses non-interactive sudo for rollback | Make the existing guard an explicit `MODULE_NETWORK_GUARD` opt-in, OFF in the public template/defaults. When ON, preflight its command and narrowly required non-interactive privilege applicability; when OFF, do not schedule or freshly install it | CORE+INTEGRATIONS with the default config has no network-guard cron line; ON without the required host policy fails closed; ON with a fixture policy schedules exactly one guard job |
| H5 | Argus cron jobs append to `~/.hermes/logs`; production rotation is external and absent from manifests | Install one Argus-owned logrotate policy for Argus file logs: daily, 7 archived rotations, rotate at 50M, compress with delayed compression, and append-safe `copytruncate`; make no claim over systemd journal policy | A clean install has the policy and a successful dry-run for the configured Hermes home; missing/unusable logrotate is an actionable install failure; no secret values enter the policy or receipt |

Every acceptance rule above is about installation truth. Runtime health checks
remain responsible for reporting a stopped dashboard or a later network
failure.

## Scope

### H1 — private deploy-time configuration

Keep `config.env` ignored and local. When the installer creates it, create it
with an owner-only mode. When a caller supplies an existing config file, check
that it is a regular file owned by the effective installation user and that
group/other permissions do not grant access before sourcing it. A refusal must
name the failed property and a remediation path without echoing configuration
values.

Apply the same safety boundary to the direct deploy path when it is given a
config file. Environment-variable fallback remains available for controlled
non-file invocations, but secret values must stay out of argv, stdout/stderr,
temporary persistent files and generated receipts. Do not move Hermes `.env`
ownership into Argus or redesign credential storage.

### H2 — user manager and persistence preflight

Use the selected module surface already known by `deploy.sh`; do not create a
second module/default table in the installer. A module that writes or enables
a user systemd unit requires a reachable user manager before its post-deploy
unit path is reported as ready. A missing user bus, missing runtime directory or
equivalent manager failure must stop with an actionable diagnostic rather than
falling through to a raw `systemctl --user` error.

Read the current user's linger state when the platform exposes it. Do not turn
linger on automatically and do not claim reboot persistence when it is `no` or
unknown. If a selected user-unit surface cannot persist without linger, the
installer must stop before claiming a successful ready installation and print
the manual operator action. Existing legacy Argus/Hermes units remain under
their current owner and are not migrated by this contract.

### H3 — Hermes home and dashboard applicability

For every enabled module that reads `$HERMES_DIR` or installs a Hermes user
unit, validate the resolved home and the executable/interpreter path that the
installed surface will use. The check may report the discovered Hermes version,
but it does not select a release channel or enforce the RR1c version policy.

Validate `HERMES_HOST` as non-empty and `HERMES_PORT` as an integer from 1
through 65535, and use those values as the liveness target in the deployed
templates. A live HTTP request is not required for installation and a stopped
dashboard is not repaired here. Argus may install its declared
fallback/drop-in templates, but must not install Hermes, resolve Hermes
credentials, start or rewrite a Hermes-owned base service, or silently replace
the configured target with the historical default port.

### H4 — network-guard applicability

The network guard is an existing host-policy tool, not a portable default
dependency. Add the smallest explicit module selection needed to express that
fact: `MODULE_NETWORK_GUARD`, OFF by default in the public template and in
deploy's fallback defaults. CORE keeps the general watchdog/liveness surface;
the guard is deployed and scheduled only when this flag is ON.

When the flag is ON, fail closed unless the host has the commands used by the
guard and a narrowly sufficient non-interactive privilege policy for its
rollback operations: `resolvectl revert`, `ip route flush table` and
`ip rule del`, with the exact argument boundary checked without executing a
rollback.
The preflight must not mutate routes, DNS, interfaces or sudoers. It must not
grant global sudo, install the smart-proxy/tunnel stack or infer applicability
from the presence of multiple interfaces. Existing
production users who rely on the guard must set the flag explicitly before a
future deployment; this contract does not perform that migration.

When the flag is OFF, a stale file from an older deployment may remain under
the existing bounded ownership rules, but no new install or managed cron
schedule may make it active. The receipt and deployment checklist must show the
flag and the resulting schedule separately from CORE.

### H5 — bounded Argus file-log rotation

Use the distribution's existing `logrotate` mechanism rather than adding a
second scheduler or a long-running rotation service. Install one clearly
Argus-owned policy for the configured `$HERMES_DIR/logs/*.log` files. The
policy must use the fixed bounds of daily rotation, seven archived copies, a
50M size threshold, `compress`, `delaycompress` and `copytruncate`, and must
tolerate absent/empty files. The receipt and public deployment checklist must
repeat these bounds.

The policy covers Argus file logs only. systemd journal retention, Hermes log
ownership and unrelated `/var/log` files remain external. If installing the
policy requires an existing package or scoped sudo write, preflight that
requirement and fail with a repair instruction; do not broaden sudo policy.
The policy path is an Argus-owned resource for a later RR1d uninstall decision.

## Explicit non-goals

- installing Hermes, its virtual environment, dashboard dependencies or
  provider credentials;
- enabling linger automatically, changing sudoers globally or changing the
  host's routing/DNS/tunnel/smart-proxy policy;
- configuring Netdata or native Cronping/Telegram delivery;
- creating the Hermes L3 analysis job, model, prompt or destination (DEBT-009);
- fixing Telegram proxy propagation (DEBT-013) or heartbeat token-in-argv
  handling (DEBT-014);
- versioned install/update, uninstall or resource migration (RR1c/RR1d);
- rotating systemd journals or unrelated operator/application logs;
- changing watchdog thresholds, network rollback policy, alert hysteresis or
  module behavior outside the selected network-guard ownership split;
- adding a generic dependency registry, host-policy framework or new
  persistent state format.

## Required red-capable probes

1. Config creation and unsafe-file fixtures: H1 is RED on baseline and GREEN
   on the candidate; the canary secret is absent from output, argv and receipt.
2. User-manager fixtures: unavailable bus, unknown/no linger and usable manager
   produce distinct, actionable outcomes; no unit is reported ready after a
   failed prerequisite.
3. Hermes preflight fixtures: missing home/executable, invalid host/port and a
   valid stopped target exercise H3 without a live production request.
4. Network-guard fixtures: default CORE does not schedule the guard; explicit
   ON with insufficient privilege fails closed; explicit ON with the declared
   fixture policy schedules the guard once.
5. Logrotate fixture: the generated policy names only the configured Argus log
   path, passes a dry-run/parser check, enforces the chosen bounds and contains
   no credential values.
6. Existing RR1b B1–B4 probes and the repository verification commands remain
   green. No live notification, route mutation, service restart or production
   deployment is a test step.

Prove the relevant installer and schedule regressions RED against baseline
`4b744713` before making them GREEN. Use isolated Linux fixtures or CI shims;
Windows shell limitations are not a substitute for Linux evidence.

## Builder receipt and review

The builder receipt must include:

- exact baseline and candidate head;
- H1–H5 decision-table mapping and selected module/default behavior;
- the user-manager/linger and Hermes preflight evidence, with private values
  redacted;
- the explicit network-guard privilege/applicability rule and migration note;
- the exact logrotate path, retention/size bounds and parser/dry-run result;
- RED/GREEN fixture results, standard checks and required CI;
- changed files, out-of-scope findings linked to `docs/BACKLOG.md` cards and
  `Production actions: None`.

The focused review prioritizes secret exposure through config or diagnostics,
false-green bootstrap completion, accidental linger/sudo/network mutation,
network-guard activation on an unsuitable host, log policy scope/retention,
legacy-unit ownership and drift between module selection and schedule. Return
`PASS-TO-MAINTAINER`, `REMEDIATE` or `BLOCKED-FOR-MAINTAINER`; allow at most one
bounded remediation pass.
