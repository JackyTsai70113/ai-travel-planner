# Canonical Trip V1 contract

`Trip V1` is the only source of truth for a planned trip. Planner output, validator results, renderer input, trip storage, maps and budget views must all consume the same document. Renderers may derive presentation-only state, but must not write a separate itinerary or make travel decisions.

The machine-readable contract is [`src/schemas/trip_v1.schema.json`](../src/schemas/trip_v1.schema.json). It uses JSON Schema Draft 2020-12 and serializes directly as JSON. YAML may be used for authoring only when it converts without information loss to the same JSON object.

## Core boundaries

- `candidate_sets` contains research candidates. Every dynamic research record includes `provenance` with a provider, retrieval time, status, and optional URL/confidence.
- `days[].items` contains only selected itinerary decisions (`selection_status: "selected"`) and references places and optional transport legs by ID from `candidate_sets`.
- `selected` records selected candidate IDs without mutating or reclassifying the candidate data.
- `overrides` represent user decisions. `preserve_on_replan` is deliberately constrained to `true`, so a replanner must carry these decisions forward unless the user explicitly changes/removes them.

## Time, money, and provenance rules

- `local_timezone` is an IANA timezone, such as `Asia/Tokyo`.
- Scheduled timestamps are ISO 8601 values with an explicit UTC offset. This makes their local interpretation unambiguous even when a trip crosses timezones.
- Every monetary object is `{ "amount": number, "currency": "ISO-4217 code" }`; the trip budget also declares its default currency.
- Dynamic or researched facts carry `retrieved_at`, `provider`, `source_type`, and a `status`. Critical facts can also retain a source URL and confidence score.

## Validation and example

`src.schemas.validate_trip` provides dependency-free contract-invariant validation for ingestion and tests. It validates the trip IANA timezone, explicit item offsets, monetary currencies, and itinerary references. A JSON Schema implementation can additionally validate the complete structural contract.

The complete fixture at [`fixtures/trips/japan-5-day-trip-v1.json`](../fixtures/trips/japan-5-day-trip-v1.json) is a five-day Japan family trip. It demonstrates traveller data, hard/soft preferences, candidate POIs/restaurants/hotels/flights/transport, selected itinerary items, budget, provenance, violations, and a preserved user override.
