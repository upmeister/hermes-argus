# R1c contract — Authorization headers out of child argv

Status: **DONE / PR #42 — ACCEPTED**

## Exact baseline

```text
Argus main = f1ddadab40c9eb30900491c480f28a6c80756484
OA phase = COMPLETE

R1a / PR #29 = DONE
R1b / PR #31 = DONE
R1c = current selected task
```

Supported Hermes authority at activation:

```text
stable = v2026.9.14 / v0.21.3
warning-source main = f88c6fc46e1c1c61ae8fdc0d7fb10ec8ad949aab
```

R1c was a bounded public-release security gate and is closed.

Accepted receipt:

```text
candidate head = b477d2bbd4d892b3fee97dd188110d4c7bbff94e
merged main = 133931a8242de0e61cecace5f75905bf63615383
CI #81 = success
probes = 115/115
swap tests = 8/8
```

All four changed blobs match between candidate and merged main. The final
Pytna remediation changed only `tests/probes.py`; production behavior was
unchanged.

## 1. Problem

Active Argus paths still place Authorization values in child-process argv.

Demonstrated owners:

```text
scripts/health-check-integrations.sh
scripts/ai-deep-check.py
```

### Shell surface

`health-check-integrations.sh` currently has two demonstrated leak shapes.

The generic helper expands an auth header into curl argv:

```bash
${auth_header:+-H "$auth_header"}
```

Active full-check callers include:

- OpenCode Go;
- Firecrawl;
- GitHub;
- Groq;
- OpenRouter.

The quick GitHub check also directly uses:

```text
-H "Authorization: token <secret>"
```

### Python surface

`ai-deep-check.py` currently constructs:

```python
["-H", f"Authorization: Bearer {token}"]
```

for both catalog and chat requests.

On a local multi-process system, these values may be visible through process
listing / proc-style command-line observation while curl is alive.

## 2. Required outcome

For every demonstrated R1c owner:

```text
Authorization value reaches the intended HTTP request
AND
Authorization value never appears in child argv
```

Preserve all existing request semantics unless a behavior is inseparable from
the leak fix:

- URL;
- method;
- proxy;
- retry count/delay;
- timeout;
- payload;
- HTTP status parsing;
- response parsing;
- failure classification.

No provider health semantics change is authorized.

## 3. Important existing safe patterns

### health-check-v2.py reference

`scripts/health-check-v2.py` already demonstrates one acceptable pattern:

```text
curl -H @-
header delivered through subprocess stdin
```

Use it as design evidence, not as permission to refactor health-check-v2.

### Telegram / curl config stdin

`health-check-integrations.sh` already keeps token-bearing Telegram URLs out of
argv by sending curl config through:

```text
-K -
```

This means stdin is already a security-sensitive transport in the generic shell
helper.

**Do not naively add a second independent stdin consumer.**

If the shell fix uses curl config stdin, it must safely carry every required
secret-bearing field through one coherent input path. If it uses another
mechanism, prove that both the existing secret URL and the new Authorization
header remain absent from argv.

Do not regress R1b while fixing R1c.

## 4. Owner surface

Primary production owners:

- `scripts/health-check-integrations.sh`;
- `scripts/ai-deep-check.py`.

Allowed adjacent files:

- `tests/probes.py`;
- `CHANGELOG.md`.

A small dedicated test helper is allowed only if a red-capable argv/proc probe
cannot be expressed cleanly in `tests/probes.py`.

No other production file is authorized unless exact current-source evidence
shows a live R1c leak in that file. Stop and report before widening scope.

## 5. Shell requirements

Cover all demonstrated authenticated curl paths.

### Generic full checks

The helper must continue to support:

- unauthenticated URL checks;
- authenticated URL checks;
- optional proxy;
- existing retry loop;
- existing status collection.

The secret Authorization value must not be present in curl argv.

### Quick GitHub

The quick GitHub request must also avoid secret-bearing argv while preserving:

- current endpoint;
- expected HTTP 200 behavior;
- status-page hint behavior;
- current timeouts.

### Token-bearing URL compatibility

The existing Telegram getMe URL path must remain secret-safe.

A fix that removes Authorization from argv but moves a Telegram bot token into
argv fails R1c.

## 6. Python requirements

For `ai-deep-check.py`:

- GET catalog checks keep the same request behavior;
- POST chat checks keep the same JSON payload behavior;
- Bearer value is delivered without appearing in child argv;
- retries/timeouts/parsing stay unchanged;
- no token value is printed or returned in reports.

A subprocess stdin header is acceptable.

Do not replace curl with a new HTTP dependency in R1c.

## 7. Required proof

Use synthetic canaries only.

At minimum, add probes for:

1. full shell authenticated helper:
   - canary absent from captured curl argv;
   - intended header is still delivered to the curl shim/input channel.

2. quick GitHub:
   - canary absent from argv;
   - Authorization header still delivered.

3. shell compatibility:
   - token-bearing Telegram URL canary remains absent from argv;
   - unauthenticated checks still work;
   - proxy/options are preserved.

4. Python GET:
   - Bearer canary absent from subprocess argv;
   - header still delivered.

5. Python POST:
   - Bearer canary absent from subprocess argv;
   - payload/request semantics remain intact.

6. artifact boundary:
   - canary absent from stdout/stderr/reports generated by the focused probes.

Prefer a red-capable long-lived curl shim or proc/cmdline observation so the
test proves the actual child-argv property rather than merely source syntax.

## 8. Regression gates

Run at minimum:

```bash
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
python3 -m py_compile scripts/health-check-v2.py scripts/gen-registry.py tests/probes.py
bash -n deploy.sh scripts/health-check-integrations.sh
git diff --check
```

CI must be green on the exact candidate head.

## 9. Non-goals

R1c does not authorize:

- a generic HTTP client abstraction;
- a notification framework;
- changing Python urllib/in-process paths without child argv exposure;
- credential storage/rotation changes;
- OAuth status work;
- R2a malformed-YAML work;
- R2c fallback inventory work;
- installer/cron/release work;
- i18n;
- new dependencies;
- Hermes runtime imports or patches.

## 10. Review focus

Pytna should prioritize:

1. a remaining Authorization canary in child argv;
2. a fix that no longer sends the Authorization header;
3. R1b regression: token-bearing Telegram URL returns to argv;
4. one active full/quick provider path omitted;
5. deep-check GET or POST behavioral drift;
6. secret material newly appearing in stdout/stderr/report;
7. scope expansion into a shared transport subsystem.

One focused review. At most one remediation by default.

## 11. ZCode receipt

```markdown
# R1c outcome

## Exact baseline/head

## Leak inventory
- health-check-integrations:
- quick GitHub:
- ai-deep-check:

## Implementation
- shell secret transport:
- Python secret transport:

## Secret-in-argv proof
- shell full:
- quick GitHub:
- Telegram URL compatibility:
- Python GET:
- Python POST:

## Behavior preservation
- proxy/retries/timeouts:
- payload/status parsing:

## Artifact secret scan

## Tests / CI

## Changed files

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR PYTNA | BLOCKED
```

## 12. Pytna receipt

```markdown
# R1c review

## Exact head reviewed

## Leak reproduction / red capability

## Remaining argv leaks
- none | concrete paths

## Request-behavior preservation

## R1b regression check

## Scope review

## Recommendation
PASS-TO-MERGE | REMEDIATE | BLOCKED-FOR-MAINTAINER
```
