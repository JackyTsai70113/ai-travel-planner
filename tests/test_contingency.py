import copy
import unittest
from pathlib import Path

from src.contingencies import analyze_contingencies


FIXTURE = Path("fixtures/trips/japan-5-day-trip-v1.json")


class ContingencyAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trip = Path(FIXTURE).read_text(encoding="utf-8")

    def _trip(self):
        from json import loads

        return loads(self.trip)

    def test_recorded_trip_generates_rain_queue_and_delay_contingencies(self):
        result = analyze_contingencies(self._trip())
        triggers = {item["trigger"] for item in result["contingencies"]}
        self.assertIn("rain", triggers)
        self.assertIn("queue", triggers)
        self.assertIn("delay", triggers)

    def test_delay_alternative_includes_validation_and_route_impact(self):
        result = analyze_contingencies(self._trip())
        delays = [item for item in result["contingencies"] if item["trigger"] == "delay" and item["status"] == "available"]
        self.assertTrue(delays, "expected at least one available delay alternative for recorded fixture")
        delay = delays[0]
        self.assertTrue(delay["alternatives"])
        alt = delay["alternatives"][0]
        self.assertIn("validation", alt)
        self.assertIn("route_impact", alt)
        self.assertIn("outcome", alt["validation"])

    def test_no_viable_backup_is_explicit(self):
        trip = self._trip()
        trip["candidate_sets"]["places"] = [trip["candidate_sets"]["places"][3]]
        result = analyze_contingencies(trip)
        self.assertTrue(any(item["status"] == "unavailable" for item in result["contingencies"]))

    def test_analyzer_is_deterministic_and_non_mutating(self):
        trip = self._trip()
        backup = copy.deepcopy(trip)
        _ = analyze_contingencies(trip)
        self.assertEqual(trip, backup)


if __name__ == "__main__":
    unittest.main()
