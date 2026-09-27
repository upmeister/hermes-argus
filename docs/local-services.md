# Local services — opt-in monitoring (proposed)

This page will accompany the local-services feature in `docs/local-services.md`. The read-only topology producer originates in [PR #54](https://github.com/upmeister/hermes-argus/pull/54); it may not have merged or deployed yet. Follow the current implementation contract before using this page as live installation instructions.

Argus reads `~/.hermes/state/service-status.json` and compares selected `systemd --user` service rows against a separate operator-owned policy file. The snapshot alone does not say which units *should* run. `active` proves systemd state, **not application-level health**. This module does not start or stop services. Existing SearXNG integration checks are independent.

## Configuration (after feature ships)

Set `MODULE_LOCAL_SERVICES="ON"` in local `config.env` and apply the supported deployment procedure. The module is OFF by default: no snapshot is collected or refreshed, no service is checked or alerted, and no reply-keyboard button is shown. ON performs an initial collection and refreshes every five minutes; with `MODULE_TG_BOT=ON` and authorized access, "🖥 Локальные сервисы" or `/services` shows the selected services. Do not put your real config, snapshot, private addresses or bot credentials in Git.

Create the operator-owned `~/.config/hermes-argus/local-services.json` (candidate path to freeze with implementation) with `schema: 1` and explicit targets. Vlad's *private-host example* is:

```json
{
  "schema": 1,
  "targets": [
    {"id": "2ch-monitor", "label": "2ch monitor", "source": "systemd_user", "name": "2ch-monitor.service", "expect": "active"},
    {"id": "nail-bot", "label": "Nail bot", "source": "systemd_user", "name": "nail-bot.service", "expect": "active"}
  ]
}
```

These targets are examples, **not public defaults**. No entries are required on a clean install. A discovery helper may suggest entries but may never silently activate them. A missing/empty manifest displays these steps; if the manifest exists but the collector is missing or unable to write a current snapshot, the operator sees `unknown` / collection diagnostics, never a green result. Invalid manifest/snapshot gives an actionable bounded error rather than terminating the bot. A selected service marked inactive/failed in **two consecutive different fresh snapshots** triggers one alert (about ten minutes in normal circumstances); a positive fresh active observation can generate recovery. An unreadable or old snapshot cannot confirm recovery; a prolonged blind state needs its own deduplicated diagnostic.

On OFF, verify that the running collector and any manually installed older cron line are disabled/removed. Existing Argus `deploy.sh` generates a cron proposal, not a complete managed-cron uninstall; a changed flag or a newly generated cron file alone does **not** disable a previously installed job. The new feature must close this gap; do not presume it is solved merely because PR #54's default install is OFF. The bot sends a new reply-keyboard markup after a confirmed toggle, so a previously visible button disappears only after a successful Telegram message. A stale `/services` command is rejected when OFF. If `WATCHDOG_ALLOWED_USER_ID` is not configured, this feature must not expose host status.

Manual/live verification and production deploy, restart or cron changes require Vlad's authorization. The README of the shipped implementation must be consistent with this page; this text is proposed feature documentation, not a claim about currently deployed behavior.