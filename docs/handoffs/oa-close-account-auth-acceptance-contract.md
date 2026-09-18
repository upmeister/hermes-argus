# OA-close contract — account-auth phase acceptance and handoff

Status: **AFTER OA1 / CLOSEOUT ONLY**

This is a small final acceptance/docs task. It is not a second auth
implementation project.

## Preconditions

Run only after OA1 is merged.

Expected state:

```text
OA0 = DONE / STATIC ONLY
OA1 = DONE / merged
OA2 = CLOSED / upstream-gated
```

## Purpose

Close the OA phase with an exact-main acceptance read and make the next active
task unambiguous.

The closeout must answer:

1. Does merged OA1 make the demonstrated Codex identity visible from both
   nested singleton and pool-only fixtures?
2. Does a generic synthetic OAuth pool provider work without adding a provider
   name to production code?
3. Do explicit API-key pool rows remain outside `oauth:*`?
4. Does storage movement between equivalent same-id provider/pool evidence avoid
   noisy identity changes?
5. Can any secret canary appear in Argus snapshot/events/report/log output?
6. Are static account-auth rows non-green and never described as "logged in"?
7. Does Copilot PAT-only behavior remain intact?
8. Does merged main still perform zero Hermes imports/network/refresh/writes in
   account-auth discovery?
9. Is OA2 still upstream-gated under the latest stable Hermes release?

## Allowed work

Preferred result: docs-only acceptance receipt plus roadmap/index updates.

Code changes are allowed only for a demonstrated OA1 regression that directly
fails one of the acceptance items above. If such a regression exists, STOP and
return it as an OA1 blocker/remediation decision rather than silently turning
closeout into a new implementation PR.

## Required evidence

- exact merged Argus main SHA;
- exact latest stable Hermes tag/version;
- `python3 tests/probes.py`;
- required CI green;
- focused OA1 acceptance fixtures;
- no-secret canary result;
- exact health-report result for static OAuth evidence;
- quick upstream check of the OA2 reopen gate.

No production deployment is required for merge.

If the maintainer separately authorizes deployment, a read-only production
observation may confirm `oauth:openai-codex` appears after the next discovery
run. Deployment/restart/auth mutation is not part of this contract.

## Documentation updates

On successful closeout:

- mark OA0 DONE / PR #33;
- mark OA1 DONE with its PR and merge SHA;
- mark OA2 CLOSED / UPSTREAM-GATED;
- mark OA phase COMPLETE;
- set R1c as the next selected task;
- retain known misses:
  external CLI/keychain/ambient-cloud auth not represented in Hermes'
  persisted auth store;
- retain raw provider-id/alias limitation for later R2c/MP work;
- keep `oauth` entity naming debt documented but do not migrate schema.

## Pytna focus

This closeout does not need another broad architecture review.

Review only:

- exact merged OA1 behavior vs acceptance;
- false-green regression;
- secret-output regression;
- accidental OA2/runtime dependency;
- stale roadmap/authority pointers.

No new auth coverage wishlist.

## Outcome

Exactly one:

```text
OA PHASE COMPLETE -> R1c
OA1 REGRESSION -> return to maintainer
OA2 REOPEN TRIGGER FOUND -> research only, maintainer decision
```
