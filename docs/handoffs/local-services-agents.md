# Local services — agent handoff

**Contract:** `docs/handoffs/local-services-contract.md`. **Operator doc:** `docs/local-services.md`. **Prerequisite:** [snapshot producer PR #54](https://github.com/upmeister/hermes-argus/pull/54) merged and read back on `main`. At docs PR creation PR #54 was still OPEN: do not treat its CI success, an attempted merge or a deployed host copy as a merged prerequisite. Refresh SHA/status before proceeding. This handoff does not authorize code-PR merge, deploy, production restarts or accepting release risk.

## The narrow task

Deliver a single opt-in `MODULE_LOCAL_SERVICES` module, OFF by default, owning **the producer as well as the checker**. ON creates a snapshot immediately and every 5 minutes; two consecutive *distinct new* snapshots confirming a configured user unit inactive/failed yield one alert. Compare only explicitly configured `2ch-monitor.service` and `nail-bot.service` for Vlad's operator manifest (neither is a public default). OFF must stop production, comparison, alerts and hide the reply-keyboard button **also after ON → OFF with an already installed cron line**. Do not change self-hosted SearXNG integration, install a plugin framework or add service control.

## Sequence and roles (informed by nail-bot, governed by Argus AGENTS.md)

1. **Docs gate / builder:** introduce role and relevant available/unavailable skills; read `AGENTS.md`, `docs/handoffs/README.md`, contract, ADR 0001, actual code/tests and relevant focused vault context. Check producer PR #54 status, merge SHA and file/schema read-back on current main; if still open, STOP, notify Vlad and await merge. Verify this specifically assigned docs-only PR head/diff and required checks, with no conflicting contract. Argus `AGENTS.md` permits merging an explicitly assigned accepted docs contract PR before implementation; the PR text itself does not authorize other merges. Read back docs merge and synchronize implementation branch from main.
2. **Builder:** one bounded implementation PR. Start with red-capable tests. Show `problem → evidence → smallest patch → owning path → non-goals`. Existing cron is printed but installed manually; explicitly address ON→OFF while keeping unrelated crontab. Run exact-head static, behavior and CI checks. If fixing OFF needs a generic installer/cron redesign or other STOP condition in `AGENTS.md`, stop and ask Vlad.
3. **Focused independent reviewer:** attack false green on missing/stale/partial snapshots, source unavailable marker, duplicate observation hysteresis, alert delivery, config/deploy/keyboard transition, authentication open mode, old-stale button and SearXNG regression. One review, at most one focused remediation, exact-head recheck. Reviewer findings beyond contract are noted, not auto-built.
4. **External analyst:** receive final implementation PR/head and reviewer evidence; independently check contract compliance and missing tests. Exchange via available MCP if agreed; GitHub PR is evidence bus. The mandatory fail-closed UX-C3 external MCP gate in nail-bot does not automatically apply to Argus.
5. **Maintainer Vlad:** decides merge of implementation PR, production deploy/restart and risk. CI green is not live cron, Telegram or systemd read-back.

## Builder/reviewer receipt in code PR

```text
CONTRACT DOCS PR / MERGED MAIN:
PRODUCER PR #54 / MERGED SHA / SCHEMA READ-BACK:
BASELINE / EXACT CODE HEAD:
IMPLEMENTATION SCOPE + FILES:
ON/OFF: default; running ON→OFF; legacy cron; new install:
COLLECTION: immediate ON; each 5min; failure behavior; stale reads:
MANIFEST: two explicit targets; location; absent/malformed:
VERDICTS: active/inactive/missing/unavailable/unknown:
ALERTS: distinct fresh observation IDs; two consecutive fails; recovery/unknown:
TELEGRAM: effective toggle; sent markup; stale button; error/onboarding; auth:
REGRESSION: existing SearXNG and integrations:
EVIDENCE: actual commands/results; exact-head CI; manual/live NOT TESTED:
FINDINGS: severity + in-scope/introduced/inherited/environment:
CHANGE VERDICT: PASS | BLOCK
RELEASE RISK: CLEAR | ACCEPTANCE_REQUIRED | BLOCK
ROLLBACK, PROD READ-BACK AND NEXT OWNER:
```

Never commit Vlad's raw topology snapshot, private IPs, tokens or production configuration. Don't silently widen scope or claim that a proposed cron line is installed. Ask Vlad before any production action.