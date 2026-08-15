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

    def test_unscheduled_restaurant_candidate_does_not_require_catalog_duplicate(self):
        trip = copy.deepcopy(self.trip)
        restaurant = copy.deepcopy(trip["candidate_sets"]["restaurants"][0])
        restaurant["place"]["id"] = "independent-restaurant"
        trip["candidate_sets"]["restaurants"].append(restaurant)
        validate_trip(trip)

    def test_place_navigation_contract_is_additive_and_valid(self):
        validate_trip(self.trip)
        place = next(item for item in self.trip["candidate_sets"]["places"] if item["id"] == "dazaifu")
        self.assertEqual(place["navigation_points"][0]["kind"], "parking")
        self.assertNotEqual(place["navigation_points"][0].get("coordinates"), place.get("coordinates"))

    def test_navigation_point_requires_a_routing_reference(self):
        mutations = (
            lambda point, place: (point.pop("coordinates"), point.pop("mapcode")),
            lambda point, place: point.update(coordinates={"latitude": 91, "longitude": 130}),
            lambda point, place: point.update(kind="runway"),
            lambda point, place: point.update(unexpected=True),
            lambda point, place: place.update(resolution={"state": "maybe", "confidence": 0.5}),
            lambda point, place: place.update(resolution={"state": "resolved", "confidence": 1.1}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                trip = copy.deepcopy(self.trip)
                place = next(item for item in trip["candidate_sets"]["places"] if item["id"] == "dazaifu")
                mutate(place["navigation_points"][0], place)
                with self.assertRaises(TripValidationError):
                    validate_trip(trip)

    def test_empty_field_provenance_is_rejected(self):
        trip = copy.deepcopy(self.trip)
        place = next(item for item in trip["candidate_sets"]["places"] if item["id"] == "dazaifu")
        place["field_provenance"] = {"name": []}
        with self.assertRaisesRegex(TripValidationError, "non-empty"):
            validate_trip(trip)


if __name__ == "__main__":
    unittest.main()
