# R2c contract — bounded static discovery compatibility with current Hermes

Status: **READY FOR IMPLEMENTATION AFTER R2a/R2b**

## Problem

Current Argus static discovery still reflects older Hermes configuration assumptions in a few places. Fresh upstream confirms two important drifts:

1. `fallback_providers` is the canonical ordered primary fallback chain; legacy `fallback_model` remains accepted for compatibility;
2. Hermes auth/credential state increasingly uses credential pools and provider-specific storage, so a fixed list of OAuth singleton paths is not a complete model of all possible auth state.

This task updates only the static metadata that has clear operational value. It does not attempt to recreate Hermes provider/runtime resolution.

## Owner

Primary owner: `scripts/integration-discover.py`.

Related generated metadata: `registry.yaml` / `scripts/gen-registry.py` only for documentation/semantics clarification unless a concrete bug is demonstrated.

`fallback-tracker-v2.py` is NOT in scope merely because fallback configuration changes; its log-event parser is a separate runtime-observation path and remains unchanged unless a current upstream marker actually breaks.

## R2c.1 — canonical fallback chain inventory

Discovery should represent `fallback_providers` in configured order.

Compatibility rule:

- prefer canonical `fallback_providers` when present;
- continue understanding legacy `fallback_model` according to the minimum semantics required to avoid losing existing installations;
- do not call Hermes helpers to normalize/merge the two;
- do not claim the static result is the actual runtime route selected at inference time.

The output must preserve enough identity to show provider/model chain changes without serializing secrets.

## R2c.2 — auxiliary roles: bounded coverage only

Do not enumerate every upstream auxiliary task merely because it exists.

Retain current roles and add another role only when one of these is true:

- it materially changes operator understanding of provider dependency/fallback;
- it is used in the reference deployment;
- a real incident demonstrates missing monitoring value.

This contract does not authorize a full mirror of Hermes auxiliary config.

## R2c.3 — credential/OAuth discovery audit

Before implementation, run a focused static-structure audit against the supported Hermes version:

- which currently used provider/auth identities are visible from redacted `config.yaml`, `.env` key names/presence, and `auth.json` structural metadata;
- whether any integration actually used by the deployment is invisible/misclassified because it exists only in credential-pool state.

If there is no current user-visible gap, stop at evidence/documentation and do not add code.

If a gap exists, the maximum allowed implementation is a redacted structural reader for the minimum required credential-pool metadata (provider identity, credential entry count/type/source class where safely available). Never serialize credential payloads.

Any need to call Hermes auth/provider resolution is a STOP.

## Registry semantics

`registry.yaml` is an Argus curated check/catalog input, not proof of the complete Hermes integration surface.

`scripts/gen-registry.py` currently derives much of its metadata from the static `OPTIONAL_ENV_VARS` data source. Fresh Hermes can augment provider/plugin env metadata elsewhere, and not every documented environment setting is represented by that static block.

Required outcome: comments/docs must state this limitation clearly so future agents do not attempt to reach “100% Hermes integration coverage” by expanding the generator architecture.

No registry redesign is required by this contract.

## Acceptance criteria

- fixture with ordered `fallback_providers` produces stable ordered static metadata;
- legacy `fallback_model` fixture remains supported;
- secrets never appear in discovery output;
- valid existing discovery semantics unrelated to fallback/auth remain unchanged;
- no Hermes imports, provider/plugin execution, credential resolution, token refresh, network, or subprocess bridge;
- credential-pool code is added only when the audit demonstrates an actual supported-deployment gap;
- registry scope limitation is documented;
- `argus-ci` green.

## Non-goals

- runtime route truth;
- all auxiliary tasks;
- all Hermes providers;
- plugin provider execution;
- auth validation during discovery;
- C1 bridge revival;
- multi-profile support (separate near-term backlog);
- fallback-tracker rewrite.

## Stop condition

Stop if “correct static discovery” begins to require upstream internal imports, provider registry execution, credential materialization, a new adapter framework, or broad schema migration. Report the uncovered semantic gap instead.
