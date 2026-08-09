from datetime import date, datetime, timedelta, timezone
import unittest

from src.sources import (AmadeusClient, AmadeusFlightAdapter, AmadeusHotelAdapter,
                         FlightSearchQuery, HotelSearchQuery, Occupancy, ProviderError,
                         CandidateStore, collect_travel_searches)


NOW = datetime(2026, 8, 10, 8, tzinfo=timezone.utc)


class RecordedTransport:
    def __init__(self): self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url.endswith("/v1/security/oauth2/token"):
            return 200, {"access_token": "recorded-token"}
        if "flight-offers" in url:
            return 200, {"data": [{"id": "1", "itineraries": [{"segments": [{"carrierCode": "CI", "number": "110", "departure": {"iataCode": "TPE", "at": "2026-10-01T08:00:00"}, "arrival": {"iataCode": "FUK", "at": "2026-10-01T11:15:00"}}]}], "price": {"grandTotal": "42000.00", "currency": "JPY"}, "travelerPricings": [{"fareDetailsBySegment": [{"brandedFare": "ECONOMY", "includedCheckedBags": {"quantity": 1}}]}]}]}
        if "hotel-offers" in url:
            return 200, {"data": [{"hotel": {"hotelId": "H1", "name": "Fixture Hotel", "latitude": 33.59, "longitude": 130.4}, "offers": [{"id": "O1", "price": {"total": "30000", "currency": "JPY", "taxes": [{"amount": "1500"}]}, "room": {"typeEstimated": {"category": "SUPERIOR"}}, "policies": {"cancellations": [{"description": {"text": "Refundable before arrival"}}]}}]}]}
        raise AssertionError(url)


class TravelProviderTests(unittest.TestCase):
    def setUp(self):
        self.transport = RecordedTransport()
        self.client = AmadeusClient(self.transport, {"AMADEUS_CLIENT_ID": "id", "AMADEUS_CLIENT_SECRET": "secret"})

    def test_flight_normalizes_timezones_price_baggage_and_transfers(self):
        query = FlightSearchQuery("TPE", "FUK", date(2026, 10, 1), Occupancy(2, (2,)), currency="JPY", airport_timezones={"TPE": "Asia/Taipei", "FUK": "Asia/Tokyo"})
        result = AmadeusFlightAdapter(self.client, NOW).search(query)
        candidate = result.candidates[0][1]
        self.assertEqual("flights", result.candidates[0][0])
        self.assertEqual("2026-10-01T08:00:00+08:00", candidate["departure"]["at"])
        self.assertEqual("2026-10-01T11:15:00+09:00", candidate["arrival"]["at"])
        self.assertEqual(42000.0, candidate["cost"]["amount"])
        self.assertTrue(candidate["direct"])
        self.assertEqual({"quantity": 1}, candidate["baggage"])
        self.assertEqual("unverified", candidate["price_status"])
        self.assertNotIn("secret", str(candidate))
        store = CandidateStore(now=NOW)
        store.ingest("flights", candidate)
        self.assertEqual("stale", store.price_status(candidate["id"], max_age=timedelta(minutes=1), now=NOW + timedelta(minutes=2)))

    def test_hotel_normalizes_occupancy_stay_price_and_policy(self):
        query = HotelSearchQuery("FUK", date(2026, 10, 1), date(2026, 10, 3), Occupancy(2, (2,)), currency="JPY", hotel_ids=("H1",))
        candidate = AmadeusHotelAdapter(self.client, NOW).search(query).candidates[0][1]
        self.assertEqual({"adults": 2, "child_ages": [2]}, candidate["occupancy"])
        self.assertEqual(15000.0, candidate["nightly_cost"]["amount"])
        self.assertEqual(30000.0, candidate["total_cost"]["amount"])
        self.assertEqual(1500.0, candidate["taxes_fees"]["amount"])
        self.assertEqual("Refundable before arrival", candidate["cancellation_policy"])
        self.assertEqual({"latitude": 33.59, "longitude": 130.4}, candidate["place"]["coordinates"])

    def test_credentials_and_provider_failures_are_explicit_and_isolated(self):
        missing = AmadeusClient(self.transport, {})
        query = FlightSearchQuery("TPE", "FUK", date(2026, 10, 1), Occupancy(1), airport_timezones={"TPE": "Asia/Taipei", "FUK": "Asia/Tokyo"})
        with self.assertRaisesRegex(ProviderError, "AMADEUS"):
            AmadeusFlightAdapter(missing).search(query)
        healthy = AmadeusFlightAdapter(self.client, NOW)
        result = collect_travel_searches([lambda: (_ for _ in ()).throw(ProviderError("timeout")), lambda: healthy.search(query)])
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(1, len(result.failures))

    def test_invalid_occupancy_and_stay_dates_are_rejected(self):
        with self.assertRaises(ValueError): Occupancy(0)
        with self.assertRaises(ValueError): HotelSearchQuery("FUK", date(2026, 10, 2), date(2026, 10, 2), Occupancy(1))


if __name__ == "__main__":
    unittest.main()
