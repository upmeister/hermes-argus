# A — Hermes 0.22.5 launch and inventory compatibility

Status: **selected first implementation contract**, after the
[programme docs PR](2026-10-25-restart-through-rr1.md) merges.
Production risk: **medium** (launch paths and discovery identity).
Merge authority: **maintainer after Codex PASS**. Reviewer: **Codex**.
No deployment is authorized. One implementation PR covers both compatibility
defects; this is not a general Hermes compatibility layer.

## Problem -> evidence -> smallest patch

Hermes PM may remove the in-checkout venv after committing an environment;
Argus hardcodes that path in preflight, the MCP default, gateway helper and
service templates. A valid v0.22.5 install can therefore be rejected or become
unobservable. Hermes also canonicalizes provider aliases for fallback dedupe,
while Argus only lowercases them. See the
[immutable upstream evidence](../research/2026-10-25-hermes-upstream-watch.md).

Smallest patch: one installation-bound launch adapter shared by affected
callers, plus a bounded static alias-data read in discovery. Retain the current
module selection, process matcher, evidence schema, probe behavior and fallback
source ordering. No dependency or new persistent state format is admitted.

## Owning paths and architecture

- `deploy.sh`, affected `modules/systemd/` templates,
  `scripts/hermes-gateway-pids.py`, `scripts/health-check-v2.py`, their existing
  launch callers, and `scripts/integration-discover.py`; targeted probes in
  `tests/probes.py` and status docs. Inventory all callers before editing.
- At most **one new production entrypoint**, `scripts/hermes-runtime.py`, if
  a shared adapter is necessary. Keep its operation set limited to launching
  the existing Hermes CLI and existing Argus Python scripts. Deploy it with
  every module that consumes it, including CORE-only and TG_BOT-only cases.
- Bind to the configured installation root (`HERMES_DIR/hermes-agent`), not
  an arbitrary `hermes` on PATH. Prefer that root's `.hermes/bin/hermes` when
  published. CLI invocations go through it. For existing Python-script
  consumers use its `--print-runtime-command --module runpy -- <script>`
  boundary, parse the returned argv list, then execute it without a shell.
  Confirm actual v0.22.5 argv behavior in the Linux rehearsal. Resolve at each
  launch; never persist a versioned interpreter or dependency-generation path.
- An absent published launcher may use the existing in-tree venv convention
  for the legacy layout. A present but unusable published launcher is an
  explicit failure, not permission to pick stale dependencies. Preserve
  gateway-helper rc 0/1/2: environment failure is not process death.
- Existing Hermes-owned base units remain preserved. Update Argus's fallback
  templates and owned consumers only. No bootstrap/PM repair implementation,
  integrity checks, interpreter downloads, global PATH surgery or new daemon.

Alias inventory uses the installed source's literal `_ALIAS_GROUPS` in
`hermes_cli/providers.py`, read with stdlib AST/literal evaluation and checked
as string-to-string-sequence data. Do not import providers, execute source,
copy a provider roster into Argus, or extend the reader into a generic source
interpreter. Apply alias normalization only to fallback dedupe identity;
retain the first entry's displayed fields and the existing model/base-URL
normalization. Missing/unreadable/unrecognized alias source on the supported
target degrades discovery through its existing last-good envelope, with a
non-secret reason; it must not publish false removals or claim canonical
dedupe. No new store or schema version. This targets v0.22.5 behavior; the
legacy **layout** control does not claim every historical Hermes version.

## Acceptance

| ID | Scenario | Required result |
| --- | --- | --- |
| A1 | v0.22.5 managed layout, no checkout `venv`, unrelated Hermes on PATH | Preflight and enabled consumers use the selected installation; MCP invocation and gateway matcher reach the intended runtime |
| A2 | Valid legacy layout; published launcher absent | Existing CLI/script operations work; module defaults and stopped-service semantics are preserved |
| A3 | Published launcher fails, times out or returns malformed command data | Bounded actionable failure, no raw child diagnostic/secret dump, no stale-venv fallback, no false gateway-dead classification |
| A4 | Managed environment changes between two launches | Second launch resolves the current environment; generated units/cron contain no generation-specific path |
| A5 | CORE-only, INTEGRATIONS-only, TG_BOT-only; existing Hermes base units | Every consumer has its adapter; imports use its actual runtime; base units remain byte-identical |
| A6 | Same model/endpoint under `opencode-zen` and `opencode`; distinct endpoints; legacy `fallback_model` | Alias pair dedupes in first-entry order; distinct endpoints remain distinct; top-level and legacy-source ordering retained |
| A7 | Malformed/missing alias data; unknown custom provider; credential canary in config | Failed read preserves last-good state and reports degradation; unknown provider identity remains lowercased; no source execution or secret output |
| A8 | Existing disabled MCP, MCP output markers, fallback parser fixtures and registry generator | Existing semantics stay green; registry generation runs into a temp file; no hand-edited generated entries |

Use fixtures for argv/environment selection, generation switching, malformed
data, and module-only deploys. Reproduce A1/A6 failures against refreshed
baseline. Include a clean isolated Ubuntu 24.04 rehearsal using an intentionally
installed v0.22.5 checkout/launcher, with no provider credentials or live MCP
servers. Demonstrate the adapter with harmless scripts and matcher imports;
fixture-only success cannot establish upstream-launcher compatibility.

Run repository minimum checks, syntax checks for every changed shell/Python
entrypoint, relevant module probes, and `argus-ci`. No production commands,
auth-status calls, notification sends or Hermes update/install on the VPS.

## Receipt and exit

Record install layout, selected launcher boundary, script/CLI argv examples
without private data, affected callers, A1–A8 evidence and residual limits.
After PASS, the implementation PR may propose v0.22.5 as the supported baseline
and update AGENTS/roadmap/handoffs/seams/changelog together; never advertise
multi-profile, packaged desktop, Docker or Nix coverage from this Linux scope.
Close [DEBT-024](../BACKLOG.md#debt-024) and
[DEBT-025](../BACKLOG.md#debt-025) in source only when their evidence passes.
B becomes next after merge; production remains pending.

Reviewer focus: stale-generation capture, differing installation roots,
accidental secrets in command diagnostics, dependency gaps under module-only
installs, alias failures turning into removals, and expanded runtime ownership.
If this requires a second new entrypoint, source compatibility framework or
hundreds of lines of adapter plumbing, stop for scope/value review.
