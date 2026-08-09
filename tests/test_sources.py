from datetime import datetime, timedelta, timezone
import unittest

from src.sources import (
    CandidateState,
    CandidateStore,
    FixtureCommunityRestaurantAdapter,
    FixtureOfficialPoiAdapter,
    SourceAdapter,
    SourceQuery,
    StaleCandidateError,
    collect_from_adapters,
)
from src.sources.providers import (
    GooglePlacesAdapter,
    ProviderConfigurationError,
    ProviderRequestError,
    YouTubeEvidenceAdapter,
    prioritize_by_authority,
)


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
QUERY = SourceQuery(destination="福岡", categories=("pois", "restaurants"))


class BrokenAdapter(SourceAdapter):
    name = "broken-fixture"

    def fetch(self, query):
        raise RuntimeError("provider timeout")


class SourceAdapterTests(unittest.TestCase):
    def test_fixture_adapters_emit_canonical_provenance(self):
        candidates, failures = collect_from_adapters(
            [FixtureOfficialPoiAdapter(NOW), FixtureCommunityRestaurantAdapter(NOW)], QUERY
        )
        self.assertEqual([], failures)
        self.assertEqual({"places", "restaurants"}, {collection for collection, _ in candidates})
        for _, candidate in candidates:
            provenance = candidate["provenance"]
            self.assertEqual(NOW.isoformat(), provenance["retrieved_at"])
            self.assertIn(provenance["source_type"], {"official", "community"})

    def test_adapter_failure_is_isolated(self):
        candidates, failures = collect_from_adapters(
            [BrokenAdapter(), FixtureOfficialPoiAdapter(NOW)], QUERY
        )
        self.assertEqual(1, len(candidates))
        self.assertEqual("places", candidates[0][0])
        self.assertEqual(["broken-fixture"], [failure.adapter for failure in failures])


class RecordedHttpClient:
    """Recorded API responses: tests must never depend on a live provider."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request_json(self, method, url, *, headers, body=None):
        self.calls.append((method, url, headers, body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ProductionProviderAdapterTests(unittest.TestCase):
    google_recording = {
        "places": [{
            "id": "ChIJ-place", "displayName": {"text": "大濠公園"},
            "formattedAddress": "福岡市中央区", "googleMapsUri": "https://maps.google.test/place",
            "location": {"latitude": 33.586, "longitude": 130.378},
            "regularOpeningHours": {"weekdayDescriptions": ["Monday: 24 hours"]},
        }]
    }

    def test_google_places_normalizes_poi_and_restaurant_without_raw_fields(self):
        client = RecordedHttpClient([self.google_recording, self.google_recording])
        adapter = GooglePlacesAdapter("test-key", http_client=client, now=NOW)
        candidates = list(adapter.fetch(QUERY))
        self.assertEqual(["places", "restaurants"], [item[0] for item in candidates])
        poi = candidates[0][1]
        restaurant = candidates[1][1]
        self.assertEqual("provider", poi["provenance"]["source_type"])
        self.assertEqual(NOW.isoformat(), poi["provenance"]["retrieved_at"])
        self.assertNotIn("rating", poi)
        self.assertEqual("restaurant", restaurant["place"]["kind"])
        self.assertEqual("unknown", restaurant["wait_risk"])
        self.assertEqual("POST", client.calls[0][0])
        self.assertNotIn("test-key", str(client.calls[0][3]))

    def test_missing_credentials_and_provider_errors_are_isolated(self):
        with self.assertRaises(ProviderConfigurationError):
            list(GooglePlacesAdapter(api_key="").fetch(QUERY))
        adapter = GooglePlacesAdapter("test-key", http_client=RecordedHttpClient([ProviderRequestError("quota")]))
        candidates, failures = collect_from_adapters([adapter, FixtureOfficialPoiAdapter(NOW)], SourceQuery("福岡", ("pois",)))
        self.assertEqual(1, len(candidates))
        self.assertEqual("google-places", failures[0].adapter)

    def test_youtube_extracts_reported_evidence_not_operational_candidates(self):
        client = RecordedHttpClient([{"items": [{"id": {"videoId": "abc"}, "snippet": {"title": "福岡 親子旅", "description": "Parking is easy; stroller friendly. Queue after lunch."}}]}])
        evidence = YouTubeEvidenceAdapter("youtube-key", http_client=client, now=NOW).fetch_evidence(QUERY)
        self.assertEqual(1, len(evidence))
        self.assertEqual(("queue", "parking", "stroller", "child"), evidence[0].signals)
        self.assertEqual("community", evidence[0].provenance["source_type"])
        self.assertEqual("reported", evidence[0].provenance["status"])
        self.assertIn("abc", evidence[0].provenance["source_url"])
        self.assertEqual("GET", client.calls[0][0])
        self.assertIn("key=youtube-key", client.calls[0][1])

    def test_authority_priority_preserves_independent_records(self):
        community = list(FixtureCommunityRestaurantAdapter(NOW).fetch(QUERY))[0]
        official = list(FixtureOfficialPoiAdapter(NOW).fetch(QUERY))[0]
        ordered = prioritize_by_authority([community, official])
        self.assertEqual(["places", "restaurants"], [collection for collection, _ in ordered])
        self.assertEqual(2, len(ordered))


class CandidateStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = CandidateStore(now=NOW)
        self.poi = list(FixtureOfficialPoiAdapter(NOW).fetch(QUERY))[0]

    def test_lifecycle_does_not_mutate_canonical_candidate(self):
        collection, candidate = self.poi
        fetched = self.store.ingest(collection, candidate)
        normalized = self.store.normalize(fetched.candidate_id)
        selected = self.store.select(fetched.candidate_id)
        self.assertEqual(CandidateState.FETCHED, fetched.state)
        self.assertEqual(CandidateState.NORMALIZED, normalized.state)
        self.assertEqual(CandidateState.SELECTED, selected.state)
        self.assertNotIn("state", candidate)
        self.assertNotIn("selected", candidate)

    def test_retrieved_at_is_required_and_staleness_is_enforced(self):
        collection, candidate = self.poi
        self.store.ingest(collection, candidate)
        self.assertEqual(1, len(self.store.fresh(timedelta(hours=1), now=NOW + timedelta(minutes=59))))
        with self.assertRaises(StaleCandidateError):
            self.store.require_fresh("ohori-park", timedelta(hours=1), now=NOW + timedelta(hours=1, seconds=1))
        invalid = {**candidate, "provenance": {**candidate["provenance"]}}
        del invalid["provenance"]["retrieved_at"]
        with self.assertRaisesRegex(ValueError, "retrieved_at"):
            CandidateStore(now=NOW).ingest(collection, invalid)

    def test_community_candidate_preserves_reported_provenance(self):
        collection, candidate = list(FixtureCommunityRestaurantAdapter(NOW).fetch(QUERY))[0]
        record = self.store.ingest(collection, candidate)
        self.assertEqual("community", record.candidate["provenance"]["source_type"])
        self.assertEqual("reported", record.candidate["provenance"]["status"])


if __name__ == "__main__":
    unittest.main()
