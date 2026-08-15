# Official-site operational facts

## Boundary and contract

`src.sources.official` accepts recorded JSON text and never opens a network
connection. `TourismSiteParser` and `OperatorAdvisoryParser` normalize two
explicit fixture profiles into `OperationalFact`. Raw HTML and provider payloads
do not cross into planner or validator code. Invalid JSON, missing provenance,
unknown fact kinds, invalid dates, and null values produce errors and no invented
fact.

Each fact records a `FactKind`, value, validity window, retrieval time, source
authority, provider, URL, and optional excerpt. Its status is one of `confirmed`,
`stale`, `contradictory`, or `unverified`. Consumers choose a category-appropriate
maximum age and call `status_at`; passing the age limit or `valid_until` changes a
fact to stale. Community facts cannot become confirmed through freshness alone.

`reconcile_facts` groups facts by subject and kind, orders sources official,
provider, then community, and uses retrieval time and URL as deterministic tie
breakers. It preserves every input record. If applicable evidence disagrees, the
official value remains the deterministic selection but the result is
`contradictory`, never `confirmed`. Stale selected evidence remains `stale`.

Planner and validator may share the pure `is_temporarily_closed` and
`last_admission_at` functions. Both accept a keyword-only `subject_id` and use
only confirmed, applicable facts for that exact subject. For compatibility it
may be omitted only when the input contains exactly one subject; an ambiguous
multi-subject input returns `None`. Stale, contradictory, malformed, or absent
evidence also returns `None`.

## Compliance and recording

Before recording a page, verify its robots policy, terms of use, copyright,
rate-limit guidance, and whether an official API or downloadable notice is the
permitted source. Identify the responsible operator, retain the canonical URL,
retrieval timestamp, relevant validity text, and the smallest permitted excerpt.
Do not bypass authentication, access controls, CAPTCHAs, or technical blocks.
Production fetching belongs in a separately reviewed acquisition layer with a
descriptive user agent, bounded rate, caching, and audit logs.

The repository fixtures are synthetic recorded profiles. They are stable test
inputs, are not proof of current venue operations, and CI must not refresh them
from the network.

## Freshness and fallback

Freshness is an explicit caller policy. Temporary closures, road restrictions,
same-day advisories, and last admission generally require shorter review windows
than stable accessibility or age policies. Always honor an official
`valid_until`; never extend it because no replacement was found. Surface stale
coverage as unknown and schedule a permitted re-check outside CI.

If automated recording is prohibited, unavailable, ambiguous, or fails parsing,
use an authorized human entry. The operator must capture subject, typed value,
official URL, retrieval time, validity dates, and a short supporting note. The
entry remains `unverified` until independently checked against the official
source; missing fields must stay unknown rather than receiving defaults.
