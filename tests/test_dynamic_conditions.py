import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from pathlib import Path
import unittest

from src.conditions import ConditionKind, ConditionPolicy, ConditionRequirement, ConditionSnapshot, ConditionStatus, EvidenceClass, load_condition_snapshot, evaluate_conditions


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures/conditions"
DT = datetime.fromisoformat


class DynamicConditionTests(unittest.TestCase):
    def test_all_recorded_fixtures_load_without_network_access(self):
        snapshots = [load_condition_snapshot(FIXTURES / f"{name}.json") for name in ("weather", "tide", "daylight", "closure")]
        self.assertEqual([snapshot.records[0].kind.value for snapshot in snapshots], ["weather", "tide", "daylight", "closure"])
        with self.assertRaises(FrozenInstanceError):
            snapshots[0].records[0].source = "changed"
        self.assertEqual(snapshots[0].records[0].provenance.source_type, "official-forecast")

    def test_loader_rejects_naive_timestamps(self):
        payload = json.loads((FIXTURES / "weather.json").read_text())
        payload["records"][0]["provenance"]["retrieved_at"] = "2026-04-10T08:00:00"
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            load_condition_snapshot(payload)

    def test_tide_requires_full_interval_containment_in_eligibility_window(self):
        snapshot = load_condition_snapshot(FIXTURES / "tide.json")
        policy = ConditionPolicy(max_age=timedelta(days=1))
        good = evaluate_conditions(snapshot, "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), policy)
        boundary = evaluate_conditions(snapshot, "ohori-park", DT("2026-04-11T12:00:00+09:00"), DT("2026-04-11T13:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), policy)
        self.assertEqual(good.findings, ())
        self.assertEqual(boundary.findings[0].code, "condition.tide.outside_window")
        self.assertEqual(boundary.findings[0].severity, "error")

    def test_daylight_accepts_contained_interval_and_rejects_interval_past_sunset(self):
        snapshot = load_condition_snapshot(FIXTURES / "daylight.json")
        policy = ConditionPolicy(max_age=timedelta(days=1))
        good = evaluate_conditions(snapshot, "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), policy)
        bad = evaluate_conditions(snapshot, "ohori-park", DT("2026-04-11T18:30:00+09:00"), DT("2026-04-11T19:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), policy)
        self.assertEqual(good.findings, ())
        self.assertEqual(bad.findings[0].code, "condition.daylight.outside_window")

    def test_missing_stale_and_forecast_horizon_are_unverified(self):
        weather = load_condition_snapshot(FIXTURES / "weather.json")
        required = ConditionSnapshot(weather.records, (ConditionRequirement("dazaifu", ConditionKind.WEATHER),))
        missing = evaluate_conditions(required, "dazaifu", DT("2026-04-12T10:00:00+09:00"), DT("2026-04-12T11:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy())
        stale = evaluate_conditions(weather, "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T11:00:00+09:00"), DT("2026-04-11T09:00:01+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        horizon_record = replace(weather.records[0], forecast_until=DT("2026-04-11T12:00:00+09:00"))
        horizon = evaluate_conditions(ConditionSnapshot((horizon_record,)), "ohori-park", DT("2026-04-11T13:00:00+09:00"), DT("2026-04-11T14:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertEqual(missing.findings[0].code, "condition.unverified")
        self.assertEqual(stale.findings[0].code, "condition.stale")
        self.assertEqual(horizon.findings[0].code, "condition.unverified")
        self.assertEqual(horizon.soft_penalty, 0)
        self.assertNotIn("condition.weather.risk", {finding.code for finding in horizon.findings})

    def test_weather_is_soft_but_authoritative_closure_is_hard(self):
        policy = ConditionPolicy(max_age=timedelta(days=1))
        weather = evaluate_conditions(load_condition_snapshot(FIXTURES / "weather.json"), "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), policy)
        closure = evaluate_conditions(load_condition_snapshot(FIXTURES / "closure.json"), "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), policy)
        self.assertEqual(weather.soft_penalty, 3.5)
        self.assertEqual(weather.findings[0].severity, "warning")
        self.assertEqual(closure.findings[0].severity, "error")

    def test_explicit_unknown_is_unverified(self):
        weather = load_condition_snapshot(FIXTURES / "weather.json")
        unknown = replace(weather.records[0], status=ConditionStatus.UNKNOWN)
        result = evaluate_conditions(ConditionSnapshot((unknown,)), "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertEqual(result.findings[0].code, "condition.unverified")
        self.assertEqual(result.soft_penalty, 0)

    def test_unknown_tide_is_unverified_not_an_outside_window_error(self):
        tide = load_condition_snapshot(FIXTURES / "tide.json").records[0]
        unknown = replace(tide, status=ConditionStatus.UNKNOWN)
        result = evaluate_conditions(ConditionSnapshot((unknown,)), "ohori-park", DT("2026-04-11T12:00:00+09:00"), DT("2026-04-11T13:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertIn("condition.unverified", {finding.code for finding in result.findings})
        self.assertFalse(any(finding.severity == "error" for finding in result.findings))
        self.assertNotIn("condition.tide.outside_window", {finding.code for finding in result.findings})

    def test_experience_closure_can_only_be_a_soft_signal(self):
        closure = load_condition_snapshot(FIXTURES / "closure.json").records[0]
        provenance = replace(closure.provenance, evidence_class=EvidenceClass.EXPERIENCE, source_type="community-report")
        community_closure = replace(closure, provenance=provenance, soft_penalty=2)
        result = evaluate_conditions(ConditionSnapshot((community_closure,)), "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertEqual(result.findings[0].severity, "warning")
        self.assertEqual(result.soft_penalty, 2)

    def test_invalid_scheduled_interval_is_rejected(self):
        snapshot = load_condition_snapshot(FIXTURES / "weather.json")
        with self.assertRaisesRegex(ValueError, "end must be after start"):
            evaluate_conditions(snapshot, "ohori-park", DT("2026-04-11T12:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy())

    def test_partial_overlap_with_fresh_authoritative_closure_is_hard(self):
        closure = load_condition_snapshot(FIXTURES / "closure.json").records[0]
        partial = replace(closure, valid_from=DT("2026-04-11T11:30:00+09:00"), valid_until=DT("2026-04-11T13:00:00+09:00"))
        result = evaluate_conditions(ConditionSnapshot((partial,)), "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertIn("condition.closure.closed", {finding.code for finding in result.findings})
        self.assertIn("condition.unverified", {finding.code for finding in result.findings})

    def test_experience_tide_window_is_advisory_not_hard(self):
        tide = load_condition_snapshot(FIXTURES / "tide.json").records[0]
        provenance = replace(tide.provenance, evidence_class=EvidenceClass.EXPERIENCE, source_type="community-report")
        advisory = replace(tide, provenance=provenance, soft_penalty=2)
        result = evaluate_conditions(ConditionSnapshot((advisory,)), "ohori-park", DT("2026-04-11T12:00:00+09:00"), DT("2026-04-11T13:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertFalse(any(finding.severity == "error" for finding in result.findings))
        self.assertEqual(result.soft_penalty, 2)

    def test_newer_community_available_does_not_mask_authoritative_closure(self):
        closure = load_condition_snapshot(FIXTURES / "closure.json").records[0]
        community_provenance = replace(
            closure.provenance, evidence_class=EvidenceClass.EXPERIENCE,
            source_type="community-report", retrieved_at=DT("2026-04-10T08:30:00+09:00"),
        )
        community_available = replace(closure, id="community-open", provenance=community_provenance, status=ConditionStatus.AVAILABLE)
        result = evaluate_conditions(ConditionSnapshot((closure, community_available)), "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertIn("condition.closure.closed", {finding.code for finding in result.findings})

    def test_duplicate_soft_sources_use_strongest_penalty_once(self):
        weather = load_condition_snapshot(FIXTURES / "weather.json").records[0]
        other = replace(weather, id="weather-second-source", soft_penalty=2)
        result = evaluate_conditions(ConditionSnapshot((weather, other)), "ohori-park", DT("2026-04-11T10:00:00+09:00"), DT("2026-04-11T12:00:00+09:00"), DT("2026-04-10T09:00:00+09:00"), ConditionPolicy(max_age=timedelta(days=1)))
        self.assertEqual(result.soft_penalty, 3.5)
        self.assertEqual(sum(finding.code == "condition.weather.risk" for finding in result.findings), 1)


if __name__ == "__main__":
    unittest.main()
