# Production deployment checklist

Production lives on `peetna-aws`. The maintainer authorizes every deployment;
review PASS or merge does not authorize it. The preferred execution path is
the resident Pytna agent through the Peetna MCP, because it has the production
runtime context. A local SSH/Linux deployment is a fallback for the
maintainer.

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
