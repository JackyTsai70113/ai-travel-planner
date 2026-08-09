# Deterministic itinerary validator

`src.validator.validate_itinerary` consumes a canonical Trip V1 document and optional explicit, already-derived inputs. It never calls a routing or place-data provider and never changes the trip document.

```python
from src.validator import ValidationContext, validate_itinerary

result = validate_itinerary(trip, ValidationContext(travel_minutes={...}, opening_hours={...}))
```

The result serializes as `{ "outcome": "valid|invalid|incomplete", "violations": [...] }`. Each violation contains stable `code`, `severity`, `message`, and JSON-pointer `path` fields. Any error is `invalid`; warnings with no errors are `incomplete`; no violations is `valid`.

## Derived input contract

- `travel_minutes[(from_place_id, to_place_id)]` is a non-negative route duration. An absent route is `travel_time.unverified`.
- `opening_hours[place_id]` is a sequence of `OpeningInterval(weekday, opens_at, closes_at)`, using Monday `0` through Sunday `6` and local wall times. An absent scheduled visit or meal is `opening_hours.unverified`.
- `budget_limit=BudgetLimit(amount, currency)` is an optional explicit cap. The validator always checks the Trip V1 category arithmetic and currency consistency.

The default registry runs time overlap, travel time, opening hours, and budget rules in that order. Construct `RuleRegistry` and call `register(rule)` to add deterministic rules; each rule receives `(trip, context)` and returns violations.
