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

See `docs/` for module reference. Everything is modular — enable only what you
need; anything requiring external services is off by default.

## Status

Pre-release, under active development. Breaking changes expected before v0.1.

## License

MIT — see LICENSE. Independent community project, not affiliated with or
endorsed by Nous Research.
