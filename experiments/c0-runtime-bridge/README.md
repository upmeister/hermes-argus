# C0 runtime bridge experiment

Bounded experiment for the C0 gate: what is the maximum useful slice of
Hermes-owned runtime truth that Argus can obtain through a short-lived Hermes
subprocess without violating Argus regular-tier side-effect policy, leaking
secrets, or creating a second Hermes runtime?

Frozen contract: `docs/experiments/c0-runtime-bridge-contract.md`.
Handoff: `docs/handoffs/c0-runtime-bridge-zcode.md`.

This code is an experiment: it must never be wired into `deploy.sh`, cron,
systemd or normal Argus health/discovery execution, and it is deliberately
not part of `tests/probes.py` or `argus-ci`.

## Layout

```text
experiments/c0-runtime-bridge/
  harness.py    parent-side containment: env allowlist, explicit HERMES_HOME,
                timeout/kill/reap, stdout/stderr byte caps, fail-closed
                envelope parsing, canary leak scan
  bridge.py     child-side entrypoint: facet registry + allowlisted envelope
                emission (no Hermes import yet — step 1)
  probes.py     containment probes with synthetic fake children
  fixtures/     Hermes fixture homes and plugin sentinels (steps 2–5)
```

## Run

```bash
python3 experiments/c0-runtime-bridge/probes.py
```

Works on POSIX and Windows. The same probes are re-run on `peetna-aws` before
any Hermes-backed facet is attempted.

## Status — step 2 (identity + config_health under containment)

Server setup (dedicated, production untouched): Hermes clone at the production
revision `b6b53c69` in `~/c0-spike/hermes-src`, own venv; the only non-stdlib
dependency the config seam needed was `pyyaml` (compatibility-surface fact).

`bridge.py` now installs a Python audit hook before any Hermes import and
records `socket.connect` / `subprocess.Popen` / write-mode file opens inside
the child; the envelope carries them as `effects` (bounded to 50 entries).

Hermes-backed probe results (server, `probes_hermes.py`, 7 pass / 0 fail):

- `mustpass_hermes_identity_facet` — version from the Hermes manifest
  (`0.21.2`), recorded source revision, no home paths serialized;
- `mustpass_profile_isolation_ab_sequential` — profiles A/B report their own
  primary model, no cross-profile bleed (gate 1);
- `mustpass_explicit_home_respected` — the child sees only the requested
  HERMES_HOME under the allowlisted environment (gate 7);
- `mustpass_malformed_config_not_ok` — broken config.yaml surfaces as
  `partial / config_parse_fallback` (raw parse raised ScannerError) instead of
  the loader's silent last-known-good/defaults fallback — facet B works;
- `mustpass_secret_nondisclosure_canary` — .env canary and the declared
  `${ENV}` value never reach stdout/stderr/envelope (gate 2);
- `mustpass_import_drift_fail_closed` — a missing Hermes module yields
  `compatibility_degraded / hermes_import_failed`, envelope stays valid
  (gate 5);
- `observation_config_load_write_effects_bounded` — in the observed scenario
  (fresh fixture home, first load) `load_config_readonly()` performed no
  writes at all (audit + filesystem snapshot); facts recorded for the
  effect-budget decision.

## Status — step 1 (harness containment)

Implemented and probed locally (no Hermes involved):

- environment allowlist with no parent-secret inheritance
  (`mustpass_env_allowlist_no_inheritance`);
- bounded timeout with deterministic kill/reap
  (`mustpass_timeout_bounded_cleanup`);
- fail-closed handling of malformed / duplicated / empty output
  (`mustpass_malformed_output_fail_closed`);
- child crash and pre-JSON exit containment
  (`mustpass_child_crash_containment`);
- output caps on both streams (`mustpass_output_cap_enforced`);
- canary leak scan self-check (`mustpass_canary_scan_selfcheck`);
- explicit profile-home passthrough, sequential runs without bleed
  (`mustpass_profile_home_passthrough`);
- write-detection mechanism self-check (OBSERVATION)
  (`observation_write_detector_selfcheck`);
- bridge envelope contract with no Hermes import
  (`mustpass_bridge_envelope_contract`).

MUST-PASS gates 1, 2, 8, 9, 10 of the contract get their full, real
verification when Hermes-backed facets run (steps 2+); the mechanisms they
rely on (canary scan, env allowlist, write detector) are validated here.

## Next steps (per the handoff sequence)

1. step 2 — identity + config-health facets (`hermes_cli.config.load_config_readonly` et al.),
   run under containment on `peetna-aws` with fixture homes;
2. step 3 — effective-config allowlist extraction, `${ENV}` fixtures;
3. step 4 — runtime-route facet with full effect observation;
4. step 5 — provider-discovery negative control (plugin sentinels);
5. step 6 — coverage comparison vs `scripts/integration-discover.py`
   and the compatibility-surface inventory;
6. step 7 — evidence receipt and the Питна adversarial review loop.
