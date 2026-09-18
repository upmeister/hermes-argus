# hermes-argus

**Always-watching guardian for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Argus keeps every tool and integration your Hermes relies on in working order —
and tells you the moment something degrades. Hermes itself fails silently: a
provider switches to fallback without a word, an MCP server dies, a self-hosted
service disappears — and the agent keeps running without it. Argus makes those
failures loud.

## What it does

- **Integration discovery** — watches `config.yaml` (systemd.path + cron safety
  net); when you add or remove a key/provider/MCP server, Argus notices and
  alerts. No restart needed.
- **Fallback cascade tracking** — parses agent logs and alerts on the first
  primary-model failure, on reaching a free-tier model, and on recovery.
- **Watchdog & liveness** — binary checks every 2–5 min (systemd units, disk,
  swap, cron integrity) with auto-restart on hangs and Telegram alerts.
- **Memory limits via systemd drop-ins** — MemoryHigh/Max/SwapMax presets so a
  runaway agent never kills the whole VM.
- **Dead-man's switch** — external heartbeat (GitHub Actions / Dead Man's
  Snitch / Cronping) so a dead VM still gets noticed.

## Requirements

- Linux VPS (any size — "weak VPS" is where it shines, but power is irrelevant)
- Hermes Agent installed
- A Telegram bot for alerts (Discord support planned)

## Quick start

```bash
git clone https://github.com/upmeister/hermes-argus.git
cd hermes-argus
cp config/config.env.template config.env   # fill in your values
./deploy.sh
```

See the Modules section below. Deploy installs only what you enable — anything
requiring external services is off by default.

## Modules

`deploy.sh` deploys by explicit manifests, filtered by `MODULE_*` flags in
`config.env` (see `config/config.env.template`):

| Flag | Installs | Default |
|------|----------|---------|
| `MODULE_CORE` | watchdog, liveness checks, auto-remediate, network-guard, ssl-expiry, check-updates | ON |
| `MODULE_INTEGRATIONS` | integration discovery (+ systemd.path watcher), fallback cascade tracker | ON |
| `MODULE_TG_BOT` | interactive Telegram control-plane bot (poller + webhook) | OFF |
| `MODULE_ANALYZER` | L3 health-analyzer ecosystem (LLM log analysis) | OFF |
| `MODULE_HEARTBEAT` | external dead-man's switch (Dead Man's Snitch / GitHub) | OFF |

Cron lines for enabled modules are generated to `/tmp/hermes-argus-crontab.txt`
— merge them into your crontab, deploy never touches it directly.

## Development baseline

Argus is currently in a stabilization-first phase. C1a runtime-bridge
productionization remains stopped.

R1a is complete in PR #29; R1b is complete in PR #31.

OA0 account-auth research is complete in PR #33 with decision **STATIC ONLY**.
The demonstrated problem is that current discovery can miss a working
OpenAI/Codex account because Hermes auth state is now nested and/or pool-backed.

The current selected implementation task is **OA1: generic static account-auth
discovery**.

OA1 must preserve the semantic boundary established by OA0:

```text
persisted credential evidence present
!= logged in
!= healthy
```

That includes correcting the current health projection that labels any static
`oauth` entity as healthy/logged-in.

Current bounded sequence:

```text
OA0 DONE / PR #33 / STATIC ONLY
 -> OA1 static account-auth discovery       NOW
 -> OA-close exact-main acceptance
 -> OA PHASE COMPLETE

OA2 status shadow                           CLOSED / UPSTREAM-GATED

then:
R1c Authorization-header argv debt
 -> R2a malformed YAML
 -> R2c bounded fallback/static discovery
 -> reduction / v0.1 stabilization
```

Latest supported Hermes stable remains v0.21.3 / `v2026.9.14`. Fresh upstream
`main` has partially improved the status-side-effect problem found by OA0, but
the endpoint still does not satisfy the OA2 reopen gate; do not poll it.

Before contributing work, read:

1. `AGENTS.md`;
2. `docs/handoffs/README.md`;
3. `docs/handoffs/2026-09-17-next-steps-execution-baseline.md`;
4. exactly one maintainer-selected task contract.

Current contract:

```text
docs/handoffs/oa1-static-account-auth-discovery-contract.md
```

Multi-profile remains a separate track.

## Status

Pre-release, under active development. Breaking changes expected before v0.1.

## License

MIT — see LICENSE. Independent community project, not affiliated with or
endorsed by Nous Research.
