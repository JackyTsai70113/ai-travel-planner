# Source evidence priority

## Boundary

Source adapters fetch and normalize facts into the existing Trip V1 `candidate_sets` contract. They never receive or change `days`, therefore cannot turn research into an itinerary decision. `CandidateStore` tracks the operational lifecycle (`fetched`, `normalized`, `selected`, `rejected`) outside Trip V1; only its canonical candidate payload may enter `candidate_sets`.

Every dynamic candidate must retain the existing provenance object: `source_type`, `provider`, `retrieved_at`, and `status`, plus URL, confidence, or note where available. Freshness is assessed by the caller with a category-appropriate maximum age; a stale fact remains traceable but must not be treated as current confirmation.

## Evidence priority

| Fact type | First-choice evidence | Community use | Rule |
| --- | --- | --- | --- |
| Closures, opening hours, entry rules, safety advisories | Official operator, municipality, tourism authority | May flag a possible change | Community reports cannot replace an official operational fact. Keep both provenance records if they conflict and mark the community fact `reported` or `unverified`. |
| Fares, schedules, availability, reservations | Carrier, hotel, venue, booking provider | Discovery only | Confirm against the responsible provider before planning a hard constraint. |
| Route duration and distance | Routing provider with query timestamp | Practical context only | Do not convert anecdotal travel time into confirmed routing data. |
| Restaurant queues, stroller access, crowding, practical tips | Venue/provider when published | Primary supplementary evidence | Keep as `community` / `reported`; it may influence soft scoring, never silently change hours or reservation policy. |
| Attractions and descriptive content | Official tourism/operator sources | Supplemental perspective | Preserve provider and retrieval time for each assertion. |

## Japan-first normalization

Use `place.name` and `place.address` as Unicode strings, preserving Japanese plus a useful English or Chinese display name when supplied by the evidence. Do not add Tabelog, Google, or scraper-specific score fields to Trip V1: adapters must translate only fields already in the schema (price range, opening-hours note, reservation, queue risk, child-friendly, parking where supported). Raw provider payloads remain outside the planner contract.

## Conflict and selection

1. Store each independently sourced candidate with its own provenance; do not overwrite a higher-priority fact.
2. Planner may use `confirmed` official/provider facts for hard constraints. `reported` community facts are soft signals.
3. Mark a candidate selected only after it has been normalized; the planner then writes the final Trip selection through existing IDs, not by mutating research evidence.
