# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-20**

This document translates the stabilization/release roadmap into bounded
repository work. Agents may perform only the named task currently selected by
the maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Do not introduce a Hermes runtime-import bridge to improve discovery or health
coverage.

## Exact current baseline

```text
Argus main = f1ddadab40c9eb30900491c480f28a6c80756484

R1a / PR #29 = DONE
R1b / PR #31 = DONE
OA phase / PR #40 = COMPLETE

R1c = NOW
```

Supported Hermes authority:

```text
v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
warning-source main = f88c6fc46e1c1c61ae8fdc0d7fb10ec8ad949aab
```

## Current execution order

```text
R1c Authorization-header argv debt        NOW
 -> R2a malformed YAML
 -> R2c.1 fallback_providers compatibility
 -> RR1 installer/dependency/managed-cron
 -> RR2 runtime i18n (en + ru)
 -> RR3 release acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0

R2c.2 auxiliary coverage                 AFTER RC
R3 reduction/stabilization               AFTER RC
OA2 dynamic account status               CLOSED / UPSTREAM-GATED
R2b gateway liveness                     DEFERRED
MP*                                       SEPARATE
```

## Current selected contract

```text
docs/handoffs/r1c-authorization-header-argv-contract.md
```

## R1c current evidence

Current source still demonstrates child-argv Authorization exposure in two
production owners.

### scripts/health-check-integrations.sh

- generic `check_url` expands `-H "$auth_header"`;
- full authenticated checks include OpenCode, Firecrawl, GitHub, Groq and
  OpenRouter;
- quick GitHub directly expands `Authorization: token ...`.

The same helper already uses `curl -K -` stdin for secret-bearing URLs.
R1c must not fix headers by regressing token-bearing URL secrecy.

### scripts/ai-deep-check.py

`curl_json()` builds:

```text
-H Authorization: Bearer <token>
```

inside subprocess argv.

### safe reference

`health-check-v2.py` already uses stdin-fed `-H @-`.

## R1c success condition

```text
Authorization still reaches the request
AND
Authorization secret is absent from child argv
AND
existing Telegram secret-URL protection is unchanged
```

No generic HTTP subsystem.

## Release direction

After R1c:

1. R2a makes malformed YAML explicit degraded state instead of crash/false
   empty inventory;
2. R2c.1 adopts canonical ordered `fallback_providers` statically;
3. release-readiness hardens install/dependencies/managed cron/update/uninstall;
4. runtime human-facing UI becomes localizable in English and Russian;
5. clean Ubuntu/versioned-release acceptance gates `v0.1.0-rc.1`.

Public documentation remains English-only. Existing Russian runtime deployments
must remain supported.

## 2026-09-20 upstream watch

Fresh Hermes main has moved substantially since the earlier OA watch.

Convergence:

- Codex status is now documented read-only and uses a read-only resolver;
- Nous exposes a refresh-free local status snapshot;
- xAI status avoids refresh-on-observation.

Remaining OA2 blockers:

- Qwen status still refresh-validates;
- the dashboard OAuth response still includes `token_preview`;
- `/api/providers/oauth` still lacks the required supported machine-token
  route;
- latest stable is still v0.21.3.

Credential-pool runtime semantics continue to grow more complex, reinforcing
the Argus boundary rather than motivating a duplicate resolver.

Fallback activation/restore markers and MCP-test output remain compatible.

## Global non-goals for R1c

- runtime bridge revival;
- OAuth/OA2 implementation;
- malformed-YAML changes;
- fallback config changes;
- installer/cron work;
- i18n;
- multi-profile implementation;
- unrelated cleanup.

## Workflow

```text
one R1c implementation pass
 -> one focused Pytna review
 -> at most one remediation
 -> exact-head reread
 -> merge OR blocker
```

Production deploy remains a separate maintainer action.
