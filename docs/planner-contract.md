# Planner contract

`src.planner` evaluates explicit Canonical Trip V1 candidate documents. It does not schedule raw research candidates: no travel time, opening hours, visit duration, or reservation time is inferred when that fact is absent.

`PlannerInput` accepts candidate trips, a `ValidationContext`, typed `HardConstraint` values, `SoftPreference` values, and a repair iteration ceiling. `PlannerOutput` contains one `CandidatePlan` per input, ranked only after all hard-rule errors have been cleared.

Hard constraints support fixed flight/train or reservation times (`fixed_time` / `reservation_time`), required or forbidden locations, and strict maximum daily duration. Opening hours, impossible transport timing, and strict budget ceilings are enforced from the supplied validator context. Soft preferences are score-only. `low_fatigue` and `few_hotel_changes` have deterministic scoring; preferences without explicit supporting candidate facts remain neutral.

Each replan reapplies `overrides` whose `preserve_on_replan` is true. The repair loop modifies only paths identified by `time.overlap` or `travel_time.insufficient`, then invokes the validator again. Unrepairable violations, or violations remaining after `max_repair_iterations`, produce `PlanState.FAILED`; they are never returned as a best plan.
