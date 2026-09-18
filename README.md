# hermes-argus

**Always-watching guardian for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Argus keeps every tool and integration your Hermes relies on in working order —
and tells you the moment something degrades. Hermes itself may continue running
while a provider falls back, an MCP server dies, or a self-hosted service
disappears. Argus makes those failures visible.

## What it does

- **Integration discovery** — watches `config.yaml` and known integration/auth
  state so meaningful configuration changes are visible without requiring an
  Argus restart.
- **Fallback cascade tracking** — parses agent logs and alerts on the first
  primary-model failure, on reaching a free-tier model, and on recovery.
- **Watchdog & liveness** — binary checks every 2–5 min (systemd units, disk,
  swap, cron integrity) with auto-restart on hangs and Telegram alerts.
- **Memory limits via systemd drop-ins** — MemoryHigh/Max/SwapMax presets so a
  runaway agent never kills the whole VM.
- **Dead-man's switch** — external heartbeat (GitHub Actions / Dead Man's
  Snitch / Cronping) so a dead VM still gets noticed.

## Requirements

- Linux VPS
- Hermes Agent installed
- A Telegram bot for alerts (Discord support planned)

## Quick start

```bash
git clone https://github.com/upmeister/hermes-argus.git
cd hermes-argus
cp config/config.env.template config.env
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
— merge them into your crontab; deploy never touches it directly.

## Development baseline

Argus is in a stabilization-first phase. The C1a Hermes runtime shadow-bridge
direction was stopped and PR #27 was closed without merge; those documents
remain historical evidence, not active implementation authority.

R1a secret-in-argv work is complete in PR #29. R1b Telegram child-argv secret
exposure is complete in PR #31.

The current selected task is **OA0: account-auth discovery research**.

A demonstrated product gap motivated the reprioritization: current static
discovery uses a fixed OAuth provider list and expects a flat
`auth.json.providers.<id>.access_token`, while supported Hermes can represent
OpenAI/Codex credentials in nested provider token state and/or the credential
pool. A working primary Codex account can therefore be invisible to Argus.

OA0 is research-only. It must decide whether the next implementation should use
generic static auth-store structure alone or combine that static baseline with a
bounded Hermes-owned external status seam. It does **not** authorize a runtime
bridge, credential refresh, provider resolution, or OA1/OA2 production code.

Before contributing work, read:

1. `AGENTS.md` — mandatory scope control;
2. `docs/handoffs/README.md` — active vs historical handoffs;
3. `docs/handoffs/2026-09-17-next-steps-execution-baseline.md`;
4. exactly one maintainer-selected active task contract.

Current bounded sequence:

```text
R1a deploy secret-in-argv                  DONE / PR #29
R1b Telegram child-argv secret exposure   DONE / PR #31

OA0 account-auth discovery research        NOW
 -> maintainer decision
 -> OA1 generic structural auth discovery
 -> OA2 optional Hermes status shadow/enrichment

then:
R1c demonstrated Authorization-header argv debt
 -> R2a malformed YAML fail-safe discovery
 -> R2c bounded fallback/static discovery
 -> reduction / v0.1 stabilization
```

OA1/OA2 are not authorized merely because they appear in the roadmap; OA0 must
finish first and the maintainer must select a new contract.

The earlier R2b proposal to use `gateway_state.json.updated_at` freshness for
gateway liveness remains **deferred**: production/upstream evidence proved that
a healthy idle gateway does not continuously advance that field.

Multi-profile monitoring is near-term product work but intentionally separate
from these tasks. OA0 may record whether a candidate upstream seam is
profile-aware, but it must not implement profile monitoring.

## Status

Pre-release, under active development. Breaking changes expected before v0.1.

## License

MIT — see LICENSE. Independent community project, not affiliated with or
endorsed by Nous Research.
