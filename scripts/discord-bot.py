#!/usr/bin/env python3
"""discord-bot.py — C5: Discord control-plane bot (MODULE_DISCORD_BOT, OFF by default).

Minimal v1: message commands mapped to the SAME webhook.py handlers as the
Telegram poller (shared logic layer — handlers return strings, no TG calls).
Requires discord.py; deploy.sh creates a dedicated venv
(~/.hermes/discord-venv) and installs it when the module is enabled.

Config (~/.hermes/.env):
  DISCORD_BOT_TOKEN         — bot token (Discord Developer Portal -> Bot)
  DISCORD_ALLOWED_USER_IDS  — comma-separated Discord user ids (empty = open,
                              for debugging only — same semantics as the TG bot)
  DISCORD_ALERT_CHANNEL_ID  — optional default channel for proactive alerts

Tokens are never printed. Discord message limit is 2000 chars — long reports
are truncated.
"""
import asyncio
import os
import sys

import discord
from discord.ext import commands

HERMES_SCRIPTS = os.path.expanduser("~/.hermes/scripts")
if HERMES_SCRIPTS not in sys.path:
    sys.path.insert(0, HERMES_SCRIPTS)
import webhook  # noqa: E402  — shared handler library (returns strings)

TOKEN = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip().strip('"\'')
ALLOWED = {x.strip() for x in
           (os.environ.get("DISCORD_ALLOWED_USER_IDS") or "").split(",") if x.strip()}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents, help_command=None)


def authorized(ctx) -> bool:
    """Empty ALLOWED_USER_IDS = open mode (debug/incidents only) — same as TG bot."""
    return not ALLOWED or str(ctx.author.id) in ALLOWED


def cmd(name: str, handler, *args):
    """Register a prefix command that runs a webhook handler in a worker thread."""
    @bot.command(name=name)
    async def _h(ctx, *a):  # noqa: ANN001 — discord.py signature
        if not authorized(ctx):
            await ctx.send("🚫 Нет доступа.")
            return
        async with ctx.typing():
            result = await asyncio.to_thread(handler, *args)
        await ctx.send(result[:2000] if result else "🤷 Пустой ответ")
    _h.__name__ = f"cmd_{name}"
    return _h


cmd("health", webhook.handle_health_status)
cmd("integrations", webhook.handle_integrations_check)
cmd("integrations_all", webhook.handle_integrations_all)
cmd("watchdog", webhook.handle_watchdog_status)
cmd("uptime", webhook.handle_uptime)
cmd("deepcheck", webhook.handle_deep_check)


@bot.command(name="help")
async def _help(ctx):
    if not authorized(ctx):
        await ctx.send("🚫 Нет доступа.")
        return
    await ctx.send("Argus commands: /health /integrations /integrations_all "
                   "/watchdog /uptime /deepcheck")


@bot.event
async def on_ready():
    print(f"[discord-bot] logged in as {bot.user}", flush=True)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("🤔 Неизвестная команда. /help")
    else:
        await ctx.send(f"❌ Ошибка: {error}")


if __name__ == "__main__":
    if not TOKEN:
        print("[discord-bot] DISCORD_BOT_TOKEN is empty — exiting", flush=True)
        sys.exit(1)
    bot.run(TOKEN)
