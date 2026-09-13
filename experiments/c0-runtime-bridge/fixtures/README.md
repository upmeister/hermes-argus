# C0 fixtures

This directory will hold the Hermes fixture-home builders and plugin sentinels
required by the C0 contract section 7 (handoff steps 2–5):

- two profiles (A/B) with conflicting provider/model config;
- a config containing `${C0_CANARY_ENV}`;
- a canary secret in a profile `.env`;
- a malformed `config.yaml`;
- a custom-provider fixture;
- a resolver-returned canary credential;
- user-provider plugin sentinels (marker writer / hang / raise);
- an external-secret helper sentinel that writes a marker.

All fixture data is synthetic; canary values are dummy markers only. The
containment probes in the parent directory use throwaway fake children and do
not depend on this directory yet.
