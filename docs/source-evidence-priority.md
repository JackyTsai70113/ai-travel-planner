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
| Restaurant opening hours, special closures, reservations | Restaurant official site/feed, then current provider data | May flag a possible change | Fresh official operational facts win. Same-authority contradictions are `conflicting` and not selectable. Lower-authority facts remain in alternatives with provenance. |
| Restaurant rating, meal prices, cuisine | Provider on its original scale | Discovery and dish-level experience | Preserve scale, review count, meal context, and provenance. Never compare scores as though provider scales were identical. |
| Restaurant queues, stroller access, crowding, practical tips | Venue/provider when published | Primary supplementary evidence | Keep as `community` / `reported`; it may influence soft scoring, never silently change hours or reservation policy. |
| Attractions and descriptive content | Official tourism/operator sources | Supplemental perspective | Preserve provider and retrieval time for each assertion. |

## Japan-first normalization

Use `place.name` and `place.address` as Unicode strings, preserving Japanese plus a useful English or Chinese display name when supplied by the evidence. Ratings use provider-neutral `ratings` records containing the original value, scale, review count, and provenance. Meal prices use `meal_price_signals`; dish recommendations require their own provenance. Raw provider payloads and provider-specific field names remain outside the planner contract.

## Conflict and selection

1. Reconcile records only when they carry the same canonical place ID. Similar names never trigger an automatic merge.
2. Keep every independent source in `source_provenance`; preserve losing operational values in `alternatives`.
3. Planner may use only `fresh`, non-conflicting structured hours for production meal finalization. `reported` community facts and free-text hours are soft/unverified signals.
4. Mark a candidate selected only after it has been normalized; the planner then writes the final Trip selection through existing IDs, not by mutating research evidence.

## Production research adapters (Issue #16)

`src.sources.GooglePlacesAdapter` uses the documented Google Places API (New)
Text Search endpoint for both POI discovery and restaurant discovery. It
normalizes aggregate rating/review count, price level, category, business
status, IANA timezone, regular hours, and current special hours into canonical
records. Set `GOOGLE_MAPS_API_KEY`; enable Places
API (New), restrict the key, and set Google Cloud quotas/billing appropriate to
the deployment. Google may rate-limit or bill requests; adapter failures are
isolated by `collect_from_adapters`, so fixtures or other providers can still
return results.

`HotPepperGourmetAdapter` uses Recruit's official Hot Pepper Gourmet Web Service
endpoint (`https://webservice.recruit.co.jp/hotpepper/gourmet/v1/`) when the
optional `HOTPEPPER_API_KEY` is configured. It is the Japan-specific quality
source and does not scrape restaurant websites. Cuisine, dinner budget,
child/smoking/parking signals, URL, and provenance are normalized. The API's
free-text `open` and `close` values remain an unverified note; the adapter never
invents structured hours, ratings, or dishes. Any product screen that displays
these records must also display `Powered by ホットペッパーグルメ Webサービス`.

`YouTubeEvidenceAdapter` uses the documented YouTube Data API Search endpoint.
Set `YOUTUBE_API_KEY` with a restricted API key. It emits `ResearchEvidence`,
not candidates: title/description-derived signals such as queue, parking, or
stroller are community `reported` evidence and cannot become confirmed operating
facts. Respect YouTube Data API quota and display/storage terms; the adapter does
not scrape pages, comments, or transcripts.

Never commit either key. CI injects recorded JSON through `JsonHttpClient` and
does not access a live network. If credentials are absent, adapters fail with a
configuration error that is isolated per provider. If either commercial API is
unavailable, retain existing official-source candidates and fixture/recorded
research, then explicitly surface missing coverage rather than inventing facts.

For closures, hours, entry rules, fares, reservations, and temporary controls,
record the responsible operator or tourism authority URL as an `official` source.
`prioritize_by_authority` returns independent records in official → provider →
community order without overwriting lower-priority evidence; consumers must keep
the provenance record and use official facts for hard constraints.
