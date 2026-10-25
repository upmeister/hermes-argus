# Hermes upstream watch — 2026-10-25

Follow-up: the maintainer accepted the restart scope through RR1c/RR1d.
The [programme](../handoffs/2026-10-25-restart-through-rr1.md) now owns the
selected sequence; this report remains the dated evidence, not task authority.

Status: **research snapshot; no supported-version promotion, implementation,
deployment, or new contract selection.** The previously accepted Argus
authority remains the one in `AGENTS.md` until a separate compatibility
decision changes it.

## Snapshot and method

| Item | Observed value |
| --- | --- |
| Previous Argus stable authority | `v2026.9.24 / v0.21.5`, `f97608f178d1ffeca59860195ab7da295f7c8e5f` |
| Latest published stable | `v0.22.5`, `bf0203a794a07aac3ff764972ab9087baa4e4f4e` |
| Publication | 2026-10-23 05:28:45 UTC; release notes call it the October 22 release |
| Warning-source main sampled | `ad249d9cac01d57523d2a9832810de88f5cf35ee` |
| Stable advancement | GitHub compare reports 16,231 commits ahead of the old authority |
| Main advancement | GitHub compare reports 1,111 commits ahead of the sampled stable |

Sources: [published release](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.5),
[old authority to stable](https://github.com/NousResearch/hermes-agent/compare/f97608f178d1ffeca59860195ab7da295f7c8e5f...bf0203a794a07aac3ff764972ab9087baa4e4f4e),
[stable to sampled main](https://github.com/NousResearch/hermes-agent/compare/bf0203a794a07aac3ff764972ab9087baa4e4f4e...ad249d9cac01d57523d2a9832810de88f5cf35ee).
Commit counts describe repository activity, not the number of Argus changes
required. GitHub's compare payload truncates its commit listing at 10,000 for
the larger comparison; `ahead_by` is the separately reported count.

The six recorded seams were inspected in source at the immutable stable SHA,
then compared with the previous authority and the sampled main. Argus source
was read from the merged PR #75 implementation tree. No Hermes code, live
provider probe, credential refresh, or production command was executed.
This is source compatibility research, not a passing deployment acceptance
test or a statement about which Hermes version is actually installed on the VPS.

## S1 — top-level fallback inventory: a real, bounded mismatch

Stable preserves the source order (`fallback_providers`, then legacy
`fallback_model`), mapping/list handling, model normalization and base-URL
normalization. However, `_entry_identity()` now canonicalizes provider aliases
using `hermes_cli.providers.normalize_provider()` instead of merely
lowercasing the provider. This is the substantive change in this file since
the old authority.

Example: two entries for the same model and endpoint named `opencode-zen` and
`opencode` collapse into one Hermes fallback slot. Argus's current
`scripts/integration-discover.py` keeps both because its identity uses
`provider.lower()`. That can duplicate inventory entries and shift the
subsequent `model:fallback:<index>` identities. This is inventory drift; it
does not prove provider health or a runtime routing failure.

Sources: [fallback normalization](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/fallback_config.py#L15-L36),
[chain identity and ordering](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/fallback_config.py#L118-L146),
[canonical aliases](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/providers.py#L128-L170),
[Argus inventory](https://github.com/upmeister/hermes-argus/blob/f433c53/scripts/integration-discover.py#L341-L364).

Smallest proposed work: a separate bounded S1 compatibility contract, with an
alias-pair regression case and an explicit choice of how to obtain Hermes's
canonical identity. Do not silently copy an expanding provider roster or
turn discovery into another runtime resolver. The report does not choose or
implement that mechanism. Non-alias chain behavior needs no rewrite.

## S2 — scoped fallback: stable rules retained

The pinned-owner, inheritance, explicit-empty-list and malformed-entry rules
remain unchanged. A declared chain now passes through the alias-aware S1
normalizer. R2c.2 is still additional coverage, not an emergency fix to the
top-level inventory. Its pre-existing post-RC position need not change solely
because upstream has accumulated many commits.

Source: [scoped fallback policy](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/fallback_config.py#L149-L172).

## S3 — MCP command: current parser still matches

`cmd_mcp_test()` still returns 0 for connection, 1 for connection failure and
3 for a server absent from config. Its connected, tool-count and failure
markers remain the English literals Argus parses. `_success()` and `_error()`
print through the ANSI-color helper; this source path does not translate those
messages. General Hermes localization therefore does not by itself establish
a current MCP parsing break.

The old Argus comment claiming the exit code is always zero remains wrong.
Adopting the exit codes while preserving the existing compatibility markers
would be a small maintenance task, not a reason to redesign MCP probing.

Sources: [MCP test](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/mcp_config.py#L836-L881),
[print helpers](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/mcp_config.py#L187-L191),
[color helper](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/colors.py#L26-L30),
[Argus parser](https://github.com/upmeister/hermes-argus/blob/f433c53/scripts/health-check-v2.py#L374-L392).

## S4 — disabled MCP servers: preserve the already merged fix

`mcp_server_enabled()` retains default-on behavior for absent, null and
unparseable values. The explicit test command still does not call that helper
before probing. Argus PR #59 already handles the operator's disabled intent;
the durable seam document's statement that Argus reads nothing is stale.
Do not re-open the old gap as unimplemented work.

Sources: [boolean semantics](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/tools/mcp_tool_common.py),
[explicit probe](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/mcp_config.py#L836-L881),
[merged fix](https://github.com/upmeister/hermes-argus/pull/59).

## S5 — fallback logs: literals and logger identities survived

Both parser dependencies remain present: the pool-attachment message is
logged by `agent.chat_completion_helpers`; the restore message is logged by
`agent.agent_runtime_helpers`. Activation was refactored through
`agent.route_binding.bind_route_entry()`, but that binder calls the original
pool-rebinding helper, preserving the logging module identity.

Sources: [pool-attachment logging](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/agent/chat_completion_helpers.py#L1876-L1895),
[binder](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/agent/route_binding.py#L20-L80),
[primary restoration](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/agent/agent_runtime_helpers.py#L1465-L1483).

No source-level marker break was found. This does not make the current tracker
complete runtime coverage: its hop signal is conditional on attaching a pool
with credentials, and pre-agent fallbacks have a separate notice path. Those
are coverage boundaries, not newly demonstrated regressions. Multi-profile
log routing and real installed log formatting still need a compatibility
rehearsal before claiming support for the latest release.

## S6 — OAuth observation: gate still not satisfied

The provider listing still includes `token_preview`; its handler does not
invoke the machine-token guard used on mutation routes. The Qwen status path
still calls credential resolution with `refresh_if_expiring=True`, which can
refresh and save credentials. Nous listing explicitly uses a local,
refresh-free getter, an improvement that does not satisfy the aggregate OA2
gate. No inference is made here about absence of all surrounding web-session
authentication; the missing requirement is the project's supported,
machine-authenticated, refresh-free, no-secret observation contract.

Sources: [OAuth status-card fields and dispatch](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/web_routers/oauth.py#L360-L430),
[list handler](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/web_routers/oauth.py#L671-L693),
[Qwen status and refresh](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/auth_qwen.py#L115-L146).

OA2 should remain closed/upstream-gated. Static account-auth evidence remains
inventory evidence, not a substitute for live login verification.

## Trends and architectural implications

### Installation and gateway seams missing from the old watch list

**Managed environments are the higher-priority compatibility issue.** The new
`pm/environments.py` did not exist at the old authority. Its stable contract
selects the committed dependency environment and explicitly says the old
in-checkout `venv`/`.venv` is deleted after a generation is committed. The
installation launcher supports the checkout's `.hermes/bin/hermes` entrypoint.
Argus deploy preflight, MCP binary default, gateway helper and service
templates still assume `hermes-agent/venv/bin/...`. A valid PM installation
without that legacy directory will therefore violate Argus's assumptions.
This is a demonstrated layout incompatibility, not proof that an existing
machine retaining the old venv is already broken.

Sources: [environment selection](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/pm/environments.py#L275-L294),
[installation command](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/_launchers.py#L87-L120),
[Argus interpreter assumption](https://github.com/upmeister/hermes-argus/blob/f433c53/scripts/hermes-gateway-pids.py#L32-L70),
[Argus MCP binary default](https://github.com/upmeister/hermes-argus/blob/f433c53/scripts/health-check-v2.py#L40-L45).

The strict `gateway.status.looks_like_gateway_command_line` and private
`_read_process_cmdline` imports still exist. Hermes also has a broader
runtime-command matcher (run or in-process restart) and profile-aware
`resolve_gateway_liveness()`. Those helpers already existed at the old
authority: they are existing scope/coverage choices, not new removals or
breaks. Argus's hardcoded installation path and process filtering should be
rehearsed against the actual selected install/profile before adapting it.
Do not introduce a generic multi-profile runtime resolver under the heading
of a local launcher fix.

Source: [gateway identity and liveness](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/gateway/status.py#L646-L655).

The parent reconnaissance also ran Argus's registry generator against the
v0.22.5 source into a temporary artifact: it completed with 153 environment
entries and 9 kit entries. This demonstrates that source scanning still runs;
it does not establish complete runtime integration discovery or authorize
replacing the repository's generated registry.

### Direction

1. **More runtime authority belongs inside Hermes.** Provider aliases,
   credential scopes and named-profile inheritance make independent Argus
   reconstruction increasingly expensive. The current ownership split remains
   appropriate: consume bounded observations and label their scope honestly.
   Hermes still uses `providers` and `credential_pool` sections in `auth.json`,
   but named profiles may inherit root credentials. Reading only one static
   file must not be presented as the complete effective credential set.
   [Auth-store ownership and inheritance](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/auth.py#L830-L960).

2. **Native telemetry is a potential source, not an external watchdog
   replacement.** Hermes already has optional OTLP gateway/platform/cron
   metrics, including busy/drainable state and scheduler heartbeat age. The
   exporter is deliberately in-process and fail-open: a dead Hermes process
   cannot report its own outage. Keep external liveness, host observation,
   failure counters and independent heartbeat delivery in Argus. Assess a
   small consumer only if it replaces demonstrably fragile existing parsing;
   do not add an OTLP backend/dependency merely because the surface exists.
   This telemetry existed at the old authority too; it is not a new feature
   introduced since the pause.
   [Health exporter and gauges](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/agent/monitoring/gateway_health_export.py#L1-L61).

3. **Plugin extraction and lifecycle changes require surface-based checks.**
   The latest release notes describe migration of MCP serving and other
   integrations into plugins, plus changes to sign-in and updater behavior.
   MCP serving is different from the MCP client-test command Argus uses;
   those release notes alone do not imply a broken Argus MCP probe. Future
   watch passes should also check installation layout, profile/gateway
   identity and plugin-owned integration inventory, which the original six
   seams do not cover adequately.
   [Release notes](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.5).

## Main warning-source check

At the sampled main SHA, `fallback_config.py`, `mcp_config.py`,
`mcp_tool_common.py`, `agent_runtime_helpers.py`, `web_routers/oauth.py` and
`auth_qwen.py` are byte-identical to the stable files inspected above.
`chat_completion_helpers.py` has unrelated streaming/headed-browser cleanup
changes; both fallback marker paths remain intact. This limited comparison
does not certify the whole of main or promote it to implementation authority.

## Recommended next decision

Before an upstream-version bump or public installer work, select a bounded
launcher compatibility contract against `v0.22.5` and rehearse the existing
gateway/interpreter/home assumptions on a clean supported Linux installation.
Resolve the proven S1 alias drift in a separate small inventory contract.
Keep the remaining release sequence and OA2/R2c.2 scope
unchanged unless that rehearsal establishes a concrete blocker. No evidence
from S1–S6 justifies rewriting Argus as a whole.
