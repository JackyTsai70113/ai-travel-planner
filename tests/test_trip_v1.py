import copy
import json
from pathlib import Path
import unittest

from src.schemas import TripValidationError, validate_trip


FIXTURE = Path(__file__).parents[1] / "fixtures/trips/japan-5-day-trip-v1.json"


class TripV1Tests(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_json_round_trip(self):
        validate_trip(self.trip)
        restored = json.loads(json.dumps(self.trip, ensure_ascii=False))
        validate_trip(restored)
        self.assertEqual(restored, self.trip)

    def test_invalid_timezone_is_rejected(self):
        trip = copy.deepcopy(self.trip)
        trip["local_timezone"] = "Japan/Tokyo"
        with self.assertRaisesRegex(TripValidationError, "valid IANA timezone"):
            validate_trip(trip)

    def test_missing_currency_is_rejected(self):
        trip = copy.deepcopy(self.trip)
        del trip["budget"]["total"]["currency"]
        with self.assertRaisesRegex(TripValidationError, "missing currency"):
            validate_trip(trip)

    def test_invalid_itinerary_reference_is_rejected(self):
        trip = copy.deepcopy(self.trip)
        trip["days"][0]["items"][0]["place_id"] = "unknown-place"
        with self.assertRaisesRegex(TripValidationError, "does not reference"):
            validate_trip(trip)


if __name__ == "__main__":
    unittest.main()
