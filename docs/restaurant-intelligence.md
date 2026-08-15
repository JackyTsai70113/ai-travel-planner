# Restaurant intelligence

## Canonical boundary

`src.opening_hours` owns the provider-neutral opening-hours snapshot used by
both planner eligibility and deterministic validation. A snapshot can express:

- IANA restaurant timezone and explicit `fresh`, `stale`, `unverified`, or
  `conflicting` state;
- multiple weekly intervals per weekday, explicit closed weekdays, and regular
  holiday notes;
- overnight/24-hour intervals through `closes_day_offset`, without non-standard
  clock values such as `24:00` or `29:00`;
- optional `last_order_at` cutoffs;
- date-specific `open`, `closed`, or `unverified` special hours;
- provenance and lower-authority alternatives.

All scheduled timestamps must include an offset. Eligibility converts the full
meal interval into the restaurant's IANA timezone and requires it to fit within
one confirmed interval. Split-hour gaps, closed weekdays, special closures, and
meals starting after last order are rejected. Stale, unknown, and conflicting
snapshots are not selectable by the production composer. The validator reads
the same snapshot and retains `opening_hours.closed` as the final safety gate.
A fresh mapping without its own restaurant timezone is treated as unverified;
the timestamp offset or Trip timezone is never silently substituted. The
planner penalizes unverified restaurant hours by default and can use
`UnverifiedRestaurantHoursPolicy.BLOCK` when every scheduled meal must have
confirmed hours.

## Sources and reconciliation

Google Places API (New) supplies provider rating aggregates, review counts,
price level, cuisine/category, business status, `regularOpeningHours`, the
seven-day `currentOpeningHours`/`specialDays` view, and `timeZone.id`. The
adapter retains original rating scale and evidence provenance and does not emit
raw Google fields.

Hot Pepper Gourmet Web Service is an optional Japan-specific official API
integration. Configure `HOTPEPPER_API_KEY`; it is not part of the required
production environment. The adapter maps documented genre, dinner budget,
open/close note, child, non-smoking, parking, and canonical URL fields. Its
free-text hours never become structured/fresh. Applications displaying its data
must show `Powered by ホットペッパーグルメ Webサービス`.
The text label links to `http://webservice.recruit.co.jp/` as required by the
provider's published credit HTML.

`OfficialRestaurantFeedAdapter` is the normalized seam for restaurant-operated
feeds or CMS exports. Every record must declare an existing canonical lowercase
place ID; the system never merges by a weak name match. Fresh official
operational facts take priority over provider facts. Lower-authority facts and
all source provenance remain auditable. The location-rich place record remains
source-coherent with its own provenance rather than relabeling copied provider
coordinates as official. Official priority does not extend to rating, cuisine,
or other quality/discovery scalars; provider/community evidence wins those
fields and conflicting values remain alternatives. Contradictory facts at the same winning
authority become `conflicting`, which blocks meal selection.

Legacy aggregate `rating`, `rating_source`, and `review_count` are selected as
one source bundle so a count can never be attached to another provider's
rating. Count-only or source-only evidence from another record remains an
alternative. Equal-authority quality sources use retrieved-at freshness and a
stable source/value key, never opening-hours freshness or input order.
Reconciliation is audit-idempotent: existing source provenance is expanded and
fact alternatives are stable-key deduplicated on repeated runs.

Aggregate restaurant ratings are separate from dish evidence. Every rating
retains its original minimum/maximum scale; review count is retained when the
provider supplies it and otherwise remains absent rather than becoming zero.
Every recommended dish requires complete provenance. Adapters do not invent
ratings or dishes.

## Offline verification

All adapter tests inject recorded JSON clients. The CI workflow runs Python
3.13 and `python -m pytest -q`; tests never require provider credentials or a
live network request.
