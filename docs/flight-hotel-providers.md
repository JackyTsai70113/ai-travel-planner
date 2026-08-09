# Flight / hotel search providers

`src.sources.travel` is a read-only search boundary.  It currently implements
the documented Amadeus Self-Service Flight Offers Search and Hotel Offers APIs.
It produces canonical `flights` / `hotels` candidates; neither raw API payloads
nor provider SDK objects reach the planner.  It never purchases tickets or books
rooms.

## Credentials and runtime

Set `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET` in the process environment.
Do not put either value in source control, fixtures, logs, or Trip data.  The
adapter obtains an OAuth token only when a search runs.  The default base URL is
Amadeus's test endpoint; production deployment must deliberately configure the
approved production endpoint and credentials in its secret manager.

Amadeus applies account-specific quota, rate, and inventory limits.  A returned
amount is marked `unverified`: it is a search result, not a guaranteed bookable
price.  Preserve `retrieved_at`; callers choose their freshness window through
`CandidateStore.require_fresh`.  Refresh stale candidates before presenting a
booking decision.

## Inputs, normalization, and fallback

Flight search accepts origin/destination airport codes, dates, direct-flight
filter, currency, adults, and child ages.  When provider timestamps lack an
offset, callers must supply an airport-to-IANA-timezone map so the normalized
candidate has an explicit offset.  Hotel search accepts city, stay dates, room
occupancy including child ages, currency, and optional provider hotel IDs.

Search failures become `AdapterFailure` records.  `collect_travel_searches`
keeps candidates returned by other providers; it does not erase them on one
provider failure.  Configure another provider adapter or retain previous
explicitly stale candidates as a fallback, clearly labelled `stale` or
`unverified`.  CI uses injected recorded responses and never calls the network.
