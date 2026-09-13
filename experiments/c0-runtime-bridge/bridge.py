#!/usr/bin/env python3
"""bridge.py — C0 bridge child entrypoint (experimental compatibility seam).

Runs inside a short-lived child process with an explicit HERMES_HOME and an
allowlisted environment built by harness.py. It prints exactly one allowlisted
JSON envelope to stdout and nothing else. Facets are independent: one facet's
failure must not invalidate others, and a facet that cannot be obtained safely
reports an explicit unsupported/degraded state instead of guessed data (C0
experiment contract section 5).

Step 1 (containment): no Hermes import happens here yet — the harness probes
use fake children, and this entrypoint only proves the envelope contract.
Hermes-backed facet loaders are added in step 2+ behind the same registry.

Forbidden as the primary safety mechanism (contract section 5):
json.dumps(config) / vars(runtime) / repr(runtime) — the boundary is
allowlist extraction, never broad serialization followed by redaction.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BRIDGE_SCHEMA = 1
BRIDGE_REVISION = "step1-containment"

# Facet loaders are registered here; each returns a facet dict:
# {"state": ..., "authority": ..., "api": ..., "reason_code": ..., "data": {...}}
FACET_LOADERS: dict[str, object] = {}


def _facet_unsupported(reason_code: str, authority: str = "unknown") -> dict:
    return {"state": "unsupported", "authority": authority,
            "reason_code": reason_code, "data": {}}


def facet_identity(profile_id: str) -> dict:
    """Hermes revision/version metadata. Requires a Hermes import (step 2);
    honestly unsupported until that seam is exercised under containment."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


def facet_config_health(profile_id: str) -> dict:
    """Distinguish 'loader returned data' from 'parse failure/degraded'.
    Requires hermes_cli.config.load_config_readonly (step 2)."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


def facet_effective_config(profile_id: str) -> dict:
    """Allowlisted effective-config fields for the coverage comparison
    (step 3). Never broad serialization; never secret values."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


def facet_runtime_route(profile_id: str) -> dict:
    """Canonical route resolution metadata (step 4); regular-safe only if the
    resolver provably stays inside the regular-mode effect budget."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


def facet_provider_registry(profile_id: str) -> dict:
    """Negative control (step 5): plugin discovery is NOT presumed safe;
    a RED observation here is the correct outcome for regular mode."""
    return _facet_unsupported("hermes_import_not_enabled_in_step1", "argus")


FACET_LOADERS.update({
    "identity": facet_identity,
    "config_health": facet_config_health,
    "effective_config": facet_effective_config,
    "runtime_route": facet_runtime_route,
    "provider_registry": facet_provider_registry,
})


def build_envelope(facets: dict, profile_id: str, hermes_revision: str) -> dict:
    return {
        "schema": BRIDGE_SCHEMA,
        "source": {
            "hermes_revision": hermes_revision,
            "bridge_revision": BRIDGE_REVISION,
            "profile_id": profile_id,
        },
        "facets": facets,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C0 bridge child (experiment)")
    ap.add_argument("--facets", default="",
                    help="comma-separated facet names; empty = all registered")
    args = ap.parse_args(argv)

    hermes_home = os.environ.get("HERMES_HOME", "")
    # The child must not infer a profile when an explicit home is supplied —
    # and must not run at all without one (harness always provides it).
    if not hermes_home:
        envelope = build_envelope(
            {"bridge": {"state": "error", "authority": "argus",
                        "reason_code": "missing_explicit_hermes_home",
                        "data": {}}},
            profile_id="unspecified", hermes_revision="unknown")
        json.dump(envelope, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    requested = [f.strip() for f in args.facets.split(",") if f.strip()]
    names = requested or list(FACET_LOADERS)
    profile_id = os.path.basename(os.path.normpath(hermes_home)) or "profile"

    facets = {}
    for name in names:
        loader = FACET_LOADERS.get(name)
        if loader is None:
            facets[name] = {"state": "error", "authority": "argus",
                            "reason_code": "unknown_facet", "data": {}}
            continue
        try:
            facets[name] = loader(profile_id)
        except Exception as exc:  # fail-closed: an unknown facet error must
            # stay inside the envelope, never become a crash before JSON.
            facets[name] = {"state": "error", "authority": "argus",
                            "reason_code": "facet_crashed",
                            "data": {"exception_class": type(exc).__name__}}
    envelope = build_envelope(facets, profile_id, hermes_revision="unknown")
    json.dump(envelope, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
