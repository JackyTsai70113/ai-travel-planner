# Travel intent contract

`src.intent.parse_trip_request(text)` is the boundary between a natural-language
user request and the research/planning pipeline. It emits `TripRequest` (also
exported as `TravelIntent`), not a Canonical Trip document.

The contract preserves `raw_text` and attaches `FieldProvenance` records with
the source substring and character offsets for every extracted field. Missing
facts are represented by `None` plus a `MissingField`; conflicting explicit
signals are represented by `AmbiguousField`. The parser does not set unstated
defaults, research POIs, calculate routing facts, or create itinerary days.

`hard_constraints` and `soft_preferences` use the existing
`src.planner.contracts.HardConstraint` and `SoftPreference` types. Consumers
can pass `intent.planner_constraints()` directly to the existing planner
boundary. Required and forbidden places currently map to the corresponding
planner hard-constraint kinds; a relaxed pace maps to `low_fatigue` as a soft
preference.
