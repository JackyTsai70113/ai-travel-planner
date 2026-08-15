# Dynamic conditions

Dynamic conditions are immutable, provider-neutral snapshots supplied through `ValidationContext`. The loader accepts recorded JSON; planner and validator never call a live provider or read the system clock. Every evaluation therefore requires an explicit timezone-aware `condition_evaluated_at` and `ConditionPolicy`.

## Provider contract

Adapters normalize provider payloads into a condition kind, targeted place IDs, status, structured `SourceProvenance`, valid interval, optional forecast horizon, eligibility windows, and soft penalty. Provenance records `provider`, `source_url`, timezone-aware `retrieved_at`, `evidence_class`, and `source_type`; a provider label alone is not sufficient evidence. The loader can read the earlier single-`source` recorded shape for compatibility, but newly recorded inputs must use structured provenance. Raw provider payloads do not enter planner logic. Forecast evidence is a prediction, never a guaranteed fact. Community reports use `experience` evidence and can only contribute a soft experience signal.

## Freshness and coverage

The policy's `max_age` is measured from `retrieved_at` to the explicit evaluation time. A stale record, unknown status, missing interval coverage, or exceeded forecast horizon emits `condition.unverified`/`condition.stale`; unknown is never treated as safe. Tide and daylight require the complete scheduled interval to fit inside one eligibility window, including boundary equality.

## Hard and soft fallback

Only an unavailable authoritative closure, disaster, or volcanic record is a hard exclusion by default. Weather, crowd, community, and non-authoritative unavailable signals remain warnings plus deterministic score penalties. This prevents a weather forecast from silently becoming a closure. Missing or stale inputs remain visible warnings rather than fabricated availability.

Issue #30 owns the upstream provider/source evidence normalization boundary. This module consumes its provider-neutral recorded output and does not change Canonical Trip V1 or embed provider-specific fields in Trip schema.
