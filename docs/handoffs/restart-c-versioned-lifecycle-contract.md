# C — versioned installation/update and bounded uninstall (RR1c + RR1d)

Status: **next eligible contract; implementation not started**. A+B are merged
and the authorized October 26 [Ops checkpoint](../DEPLOY_CHECKLIST.md#ops-receipt--2026-10-26)
is complete at deployed source `17b3975`.
Authority: [restart programme](2026-10-25-restart-through-rr1.md).
Production risk: **high** (installed resource lifecycle).
Merge authority: **maintainer after Codex PASS**. Reviewer: **Codex**.
One implementation PR joins version selection and resource retirement because
they share the same installation/ownership contract. No production action,
release publication, or Hermes lifecycle operation is authorized.

## Problem -> evidence -> smallest patch

`install.sh` currently clones the default branch or pulls the current checkout.
There is no reproducible Argus version selection and no bounded uninstall.
RR1a/b already establish the schedule and payload surface; A establishes the
Hermes launch boundary. Extend the existing installer for version selection
and reuse deploy's resource declarations for lifecycle operations.

Owning paths: `install.sh`, `deploy.sh`'s payload/resource declarations and
managed cron reconciliation, at most one new `uninstall.sh` entrypoint,
existing config/module templates only where ownership needs clarification,
Linux lifecycle fixtures, CI and public operator docs. Extract a small shared
data-only resource declaration only if needed to avoid two divergent payload
lists; do not build a manifest engine or add a persistent installed-state DB.
No new dependency or state format. Keep ignored `config.env` as configuration.

## Version selection — architect choices for this contract

- `--version <tag>` selects one exact existing Argus release tag, including
  an explicitly named RC; it is mutually exclusive with `--channel`.
- `--channel stable` selects the latest published non-draft, non-prerelease
  GitHub release and resolves its tag to a commit before deploying.
- `--channel edge` explicitly selects refreshed `origin/main` and records its
  exact commit. No silent edge fallback if stable is absent/unreachable.
- No selector means stable. Selection is explicit **per invocation**, with
  no new persisted channel setting. Repeating an RC install therefore uses
  its explicit tag. Document this; do not imply Hermes's channel persistence.
- `install.sh` also handles updates/re-runs; no separate update command.
  A clean source checkout may move to the selected revision; tracked local
  changes, untracked-file collisions, a divergent local branch or an unexpected
  repository remote stop before checkout/deploy. Never stash/reset user work.
  Ignored private config and operator data survive unchanged.
- Stable/edge selection must not implicitly downgrade an existing tagged
  install; report the target and stop. An explicitly named older `--version`
  is an intentional request, visibly labelled a downgrade. No automatic
  rollback or data migration is promised. Exact tag/commit is printed before
  runtime writes; failed selection performs no deployment.
- Resolve/check out the chosen tree, then run **that tree's** installer/deploy
  behavior, avoiding an old in-memory installer deploying a new revision under
  old rules. Bound any self-reexec to one transition and propagate failures.
  Bootstrap dependencies and private-config gates remain honest and idempotent.

No public Argus release exists at the planning baseline. Consequently default
stable will correctly refuse until one is published. Use local fixture tags
and a stub release API for tests; this contract does not authorize publishing
test tags/releases to GitHub. Require a target containing this lifecycle
contract; earlier historical versions are not supported downgrade targets.

## Ownership and uninstall

The uninstall default is a read-only plan; `uninstall.sh --apply` requests the
bounded mutation. Inspect actual installed artifacts independently of today's
module flags, so disabled-but-previously-installed Argus modules are visible.
Use current source declarations plus the already documented legacy names;
there is no filesystem-wide discovery or new migration registry.

| Resource | Allowed behavior |
| --- | --- |
| Argus managed cron block | Remove only its one well-formed marked block; preserve all surrounding jobs and environment lines; malformed/duplicate boundaries stop |
| Exclusively Argus units, drop-ins and script payloads | Preview exact paths; stop/disable only Argus units being removed, remove only demonstrably Argus-owned matching artifacts; changed/ambiguous copies survive with a manual disposition |
| Hermes gateway/dashboard base services | Always preserve their files and running state; remove only explicitly identified Argus drop-ins, with reload requirements reported |
| Argus logrotate policy and scheduler activation copy | Remove matching Argus-owned copies only; preserve foreign/modified entries and the host scheduler |
| Config, Hermes `.env`/auth, state, logs, Argus checkout, bot venv, heartbeat Git checkout | Preserve by default; list retained resources. No purge switch in this contract |
| Hermes, Netdata, proxy/network setup, L3 jobs, external accounts/repositories | Preserve; no credential/API operations, package removal, route changes or user/root crontab replacement |

Matching generated templates for safe removal is an ownership decision, not a
new integrity/security subsystem. Reuse the existing bounded template-render
logic without printing configuration. If identity cannot be established,
preserve the file and report incomplete cleanup; never label it fully removed.
Do not delete entire shared directories. A second apply is idempotent.

Migration is limited to already named Argus resources and canonical cron
adoption. Existing heartbeat-directory compatibility remains; do not move
Git histories or infer that `hermes-infra` belongs entirely to Argus.
The uncertain full checker (DEBT-004) stays. Installation/update must preserve
custom runtime files or stop with a specific operator decision before replacing
them; it must not silently overwrite the mixed production quick checker.
For updates, establish matching ownership against the currently installed
source revision before switching the checkout, then render the target tree;
a legitimate older generated file is not a customization merely because it
differs from the target version. If the installed revision cannot be established,
stop for operator reconciliation instead of inventing installation history.
Do not add cleanup of speculative historical names.

## Acceptance matrix

| ID | Case | Required evidence |
| --- | --- | --- |
| C1 | Fresh stable / explicit RC / edge fixtures | Exact selected SHA is deployed; stable never resolves to main or a prerelease implicitly |
| C2 | No release, unavailable API/tag or malformed metadata | Clear non-success with no runtime/schedule writes; no fallback channel |
| C3 | Same-version rerun and upgrade, default and nondefault module sets | One schedule block, truthful payloads, preserved private config/operator cron, new selected-tree logic actually used |
| C4 | Dirty/divergent checkout, untracked collision, unexpected remote, implicit downgrade | Refusal preserves user work and deployed resources; explicit supported-tag downgrade is labelled |
| C5 | Uninstall plan then apply then repeat | Plan has no mutation; apply removes only proven Argus resources; repeat has no collateral changes |
| C6 | Pre-existing Hermes services, modified Argus script/unit/policy, disabled old module, foreign sentinel files | Hermes stays active/unchanged; ambiguous files and external resources survive; retained/incomplete cleanup is explicit |
| C7 | Legacy schedule/names and malformed managed block | Only documented adoption occurs; operator environment survives; ambiguity stops without partial schedule removal |
| C8 | Checkout/deploy/uninstall step failure | Nonzero result and accurate partial-state report; no false completion, broad restore or hidden retry loop |

Run isolated Ubuntu 24.04 lifecycle tests with local Git remotes/tags, stubbed
release metadata and fixture-owned user-unit/scheduler surfaces, including real
shell/permission behavior where applicable. Standard checks and `argus-ci`
remain required. Wire the lifecycle smoke checks into existing CI; this is the
RR1c/d test surface, not completion of RR3's full product acceptance.

## Receipt, review and stop

Receipt includes exact source/target revisions, CLI behavior, ownership table
mapped to code, C1–C8 outcomes, all retained resources, failure/retry semantics,
and source/deployment status. Reviewer attacks version-selection fallbacks,
old-installer/new-tree execution, custom-file clobbering, lost cron environment,
Hermes service ownership and misleading cleanup success. One remediation.

On merge mark RR1c/d source complete with evidence; report deployment separately
and **stop the selected programme**. RR2, public setup work and RR3 remain later.
If safe ownership needs an install-state format, broad migration machinery,
another production entrypoint or a larger architecture, return a concrete
scope/value blocker rather than silently widening this contract.
