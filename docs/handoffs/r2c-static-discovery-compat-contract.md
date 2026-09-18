# R2c contract — bounded static discovery compatibility with current Hermes

Status: **QUEUED AFTER OA TRACK + R2a**

## Authority note — auth subsection superseded

The former R2c.3 credential/OAuth audit is superseded by:

```text
docs/handoffs/oa0-account-auth-discovery-research-contract.md
```

Reason: the old R2c.3 premise was that no supported-deployment auth identity had yet been demonstrated as invisible. That premise is no longer true: current Argus can miss a working OpenAI/Codex account because Hermes auth storage evolved beyond the old flat singleton assumption.

Do not start a second auth-discovery design under R2c.

Future account-auth implementation belongs to OA1/OA2 only after OA0 research and maintainer approval.

## Problem retained by R2c

Current Argus static discovery still reflects older Hermes configuration assumptions in a few non-auth places.

The retained concrete drift is:

1. `fallback_providers` is the canonical ordered primary fallback chain;
2. legacy `fallback_model` remains accepted for compatibility;
3. registry metadata is curated Argus check/catalog data, not complete Hermes runtime truth;
4. auxiliary-role coverage should remain bounded to demonstrated operator value.

This task updates only static metadata with clear operational value. It does not recreate Hermes provider/runtime resolution.

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

## R2c.3 — retired

Credential/OAuth/account-auth work has moved to the OA track.

See:

```text
OA0 research
 -> maintainer decision
 -> OA1 generic structural auth discovery
 -> OA2 optional Hermes-owned status shadow/enrichment
```

Do not add credential-pool parsing under R2c.

## Registry semantics

`registry.yaml` is an Argus curated check/catalog input, not proof of the complete Hermes integration surface.

`scripts/gen-registry.py` currently derives much of its metadata from the static `OPTIONAL_ENV_VARS` data source. Fresh Hermes can augment provider/plugin env metadata elsewhere, and not every documented environment setting is represented by that static block.

Required outcome: comments/docs must state this limitation clearly so future agents do not attempt to reach “100% Hermes integration coverage” by expanding the generator architecture.

No registry redesign is required by this contract.

## Acceptance criteria

- fixture with ordered `fallback_providers` produces stable ordered static metadata;
- legacy `fallback_model` fixture remains supported;
- secrets never appear in discovery output;
- valid existing discovery semantics unrelated to fallback remain unchanged;
- no Hermes imports, provider/plugin execution, credential resolution, token refresh, network, or subprocess bridge;
- registry scope limitation is documented;
- no account-auth/OAuth implementation is added here;
- `argus-ci` green.

## Non-goals

- runtime route truth;
- account-auth discovery (OA track);
- all auxiliary tasks;
- all Hermes providers;
- plugin provider execution;
- auth validation during discovery;
- C1 bridge revival;
- multi-profile support;
- fallback-tracker rewrite.

## Stop condition

Stop if “correct static discovery” begins to require upstream internal imports, provider registry execution, credential materialization, a new adapter framework, broad schema migration, or account-auth work already owned by OA0/OA1/OA2. Report the uncovered semantic gap instead.
