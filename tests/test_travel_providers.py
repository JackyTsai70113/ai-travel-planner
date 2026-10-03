from datetime import date, datetime, timezone
import unittest

from src.sources import AmadeusClient, AmadeusHotelAdapter, HotelSearchQuery, Occupancy, ProviderError


NOW = datetime(2026, 8, 10, 8, tzinfo=timezone.utc)


class RecordedTransport:
    def __init__(self): self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "hotel-offers" in url:
            return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Fixture Hotel", "latitude": 33.59, "longitude": 130.4}, "offers": [{"id": "O1", "price": {"total": "30000", "currency": "JPY", "taxes": [{"amount": "1500"}]}, "room": {"typeEstimated": {"category": "SUPERIOR"}}, "policies": {"cancellations": [{"description": {"text": "Refundable before arrival"}}]}}]}]}
        raise AssertionError(url)


class TravelProviderTests(unittest.TestCase):
    def setUp(self):
        self.transport = RecordedTransport()
        self.client = AmadeusClient(self.transport, {"AMADEUS_CLIENT_ID": "id", "AMADEUS_CLIENT_SECRET": "secret"})

    def test_hotel_normalizes_occupancy_stay_price_and_policy(self):
        query = HotelSearchQuery("FUK", date(2026, 10, 1), date(2026, 10, 3), Occupancy(2, (2,)), currency="JPY", hotel_ids=("H1",), room_quantity=2, room_quantity_explicit=True)
        candidate = AmadeusHotelAdapter(self.client, NOW).search(query).candidates[0][1]
        self.assertEqual({"adults": 2, "child_ages": [2], "rooms": 2}, candidate["occupancy"])
        self.assertIn("roomQuantity=2", self.transport.calls[-1][1])
        self.assertEqual(15000.0, candidate["nightly_cost"]["amount"])
        self.assertEqual(30000.0, candidate["total_cost"]["amount"])
        self.assertEqual(1500.0, candidate["taxes_fees"]["amount"])
        self.assertEqual("Refundable before arrival", candidate["cancellation_policy"])
        self.assertEqual({"latitude": 33.59, "longitude": 130.4}, candidate["place"]["coordinates"])

    def test_missing_optional_hotel_credentials_raise_provider_error(self):
        missing = AmadeusClient(self.transport, {})
        query = HotelSearchQuery("FUK", date(2026, 10, 1), date(2026, 10, 3), Occupancy(1), hotel_ids=("H1",))
        with self.assertRaisesRegex(ProviderError, "AMADEUS"):
            AmadeusHotelAdapter(missing).search(query)

    def test_invalid_occupancy_and_stay_dates_are_rejected(self):
        with self.assertRaises(ValueError): Occupancy(0)
        with self.assertRaises(ValueError): HotelSearchQuery("FUK", date(2026, 10, 2), date(2026, 10, 2), Occupancy(1))


if __name__ == "__main__":
    unittest.main()
