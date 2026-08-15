from datetime import datetime, timedelta, timezone
import unittest

from src.sources import (
    AdapterFailure,
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
    HotPepperGourmetAdapter,
    OfficialRestaurantFeedAdapter,
    ProviderConfigurationError,
    ProviderRequestError,
    YouTubeEvidenceAdapter,
    prioritize_by_authority,
)
from src.restaurant_intelligence import restaurant_intelligence


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
QUERY = SourceQuery(destination="福岡", categories=("pois", "restaurants"))


class BrokenAdapter(SourceAdapter):
    name = "broken-fixture"

    def fetch(self, query):
        raise RuntimeError("provider timeout")


class NestedFailureAdapter(SourceAdapter):
    name = "nested-fixture"

    def fetch(self, query):
        return list(FixtureOfficialPoiAdapter(NOW).fetch(query))

    def drain_failures(self):
        return (AdapterFailure("nested-provider", "partial provider timeout"),)


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

    def test_nested_adapter_failure_is_reported_without_discarding_candidates(self):
        candidates, failures = collect_from_adapters([NestedFailureAdapter()], QUERY)
        self.assertEqual(1, len(candidates))
        self.assertEqual(["nested-provider"], [failure.adapter for failure in failures])


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

    def test_google_restaurant_normalizes_rating_reviews_and_split_opening_hours(self):
        restaurant_recording = {
            "places": [{
                "id": "ChIJ-restaurant", "displayName": {"text": "水曜日定休食堂"},
                "rating": 4.6, "userRatingCount": 321, "primaryType": "japanese_restaurant",
                "timeZone": {"id": "Asia/Tokyo"},
                "regularOpeningHours": {"periods": [
                    {"open": {"day": 1, "hour": 11, "minute": 30}, "close": {"day": 1, "hour": 14, "minute": 0}},
                    {"open": {"day": 1, "hour": 17, "minute": 30}, "close": {"day": 1, "hour": 21, "minute": 0}},
                ]},
            }]
        }
        client = RecordedHttpClient([self.google_recording, restaurant_recording])
        restaurant = list(GooglePlacesAdapter("test-key", http_client=client, now=NOW).fetch(QUERY))[1][1]
        self.assertEqual(4.6, restaurant["rating"])
        self.assertEqual("Google Places", restaurant["rating_source"])
        self.assertEqual(321, restaurant["review_count"])
        self.assertEqual("japanese_restaurant", restaurant["cuisine"])
        self.assertEqual("fresh", restaurant["opening_hours"]["status"])
        self.assertEqual("Asia/Tokyo", restaurant["opening_hours"]["timezone"])
        self.assertEqual([
            {"weekday": 0, "opens_at": "11:30", "closes_at": "14:00"},
            {"weekday": 0, "opens_at": "17:30", "closes_at": "21:00"},
        ], restaurant["opening_hours"]["intervals"])
        self.assertNotIn("regularOpeningHours", str(restaurant))

    def test_google_rating_does_not_invent_zero_reviews_when_count_is_absent(self):
        recording = {"places": [{
            "id": "RatingOnly", "displayName": {"text": "評価のみ"}, "rating": 4.2,
            "timeZone": {"id": "Asia/Tokyo"}, "regularOpeningHours": {"periods": []},
        }]}
        restaurant = list(GooglePlacesAdapter(
            "key", http_client=RecordedHttpClient([self.google_recording, recording]), now=NOW,
        ).fetch(QUERY))[1][1]
        self.assertEqual(4.2, restaurant["ratings"][0]["value"])
        self.assertNotIn("review_count", restaurant["ratings"][0])
        self.assertNotIn("review_count", restaurant)

    def test_google_special_hours_timezone_cross_midnight_and_canonical_id(self):
        recording = {"places": [{
            "id": "ChIJ_Mixed-Case", "displayName": {"text": "深夜食堂"}, "rating": 4.1,
            "userRatingCount": 22, "priceLevel": "PRICE_LEVEL_MODERATE", "businessStatus": "OPERATIONAL",
            "timeZone": {"id": "Asia/Tokyo"},
            "regularOpeningHours": {"periods": [
                {"open": {"day": 3, "hour": 22}, "close": {"day": 4, "hour": 2}},
            ]},
            "currentOpeningHours": {
                "periods": [{"open": {"day": 3, "hour": 12, "date": {"year": 2026, "month": 8, "day": 26}}, "close": {"day": 3, "hour": 13, "date": {"year": 2026, "month": 8, "day": 26}}}],
                "specialDays": [
                    {"date": {"year": 2026, "month": 8, "day": 26}},
                    {"date": {"year": 2026, "month": 8, "day": 27}},
                ],
            },
        }]}
        restaurant = list(GooglePlacesAdapter("key", http_client=RecordedHttpClient([self.google_recording, recording]), now=NOW).fetch(QUERY))[1][1]
        self.assertEqual("google-chij_mixed-case", restaurant["place"]["id"])
        self.assertEqual(5.0, restaurant["ratings"][0]["scale_max"])
        self.assertEqual("PRICE_LEVEL_MODERATE", restaurant["meal_price_signals"][0]["label"])
        self.assertEqual(1, restaurant["opening_hours"]["intervals"][0]["closes_day_offset"])
        self.assertNotIn(3, restaurant["opening_hours"]["closed_weekdays"])
        self.assertEqual(["open", "closed"], [item["status"] for item in restaurant["opening_hours"]["special_hours"]])
        self.assertNotIn("currentOpeningHours", str(restaurant))

    def test_google_always_open_period_without_close_is_safe(self):
        recording = {"places": [{
            "id": "AlwaysOpen", "displayName": {"text": "24h"}, "timeZone": {"id": "Asia/Tokyo"},
            "regularOpeningHours": {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]},
        }]}
        restaurant = list(GooglePlacesAdapter("key", http_client=RecordedHttpClient([self.google_recording, recording]), now=NOW).fetch(QUERY))[1][1]
        self.assertEqual(7, len(restaurant["opening_hours"]["intervals"]))
        self.assertTrue(all(item["closes_day_offset"] == 1 for item in restaurant["opening_hours"]["intervals"]))

    def test_hotpepper_recording_normalizes_quality_signals_but_not_free_text_hours(self):
        payload = {"results": {"shop": [{
            "id": "J001234", "name": "博多食堂", "address": "福岡市", "lat": 33.59, "lng": 130.40,
            "genre": {"name": "居酒屋"}, "budget": {"average": "3001～4000円", "name": "3001～4000円"},
            "open": "月～火 17:00～翌1:00", "close": "水曜日", "child": "お子様連れ歓迎",
            "non_smoking": "全面禁煙", "parking": "駐車場なし", "urls": {"pc": "https://hotpepper.example/shop"},
        }]}}
        client = RecordedHttpClient([payload])
        result = list(HotPepperGourmetAdapter("hotpepper-key", http_client=client, now=NOW).fetch(QUERY))[0][1]
        self.assertEqual("hotpepper-j001234", result["place"]["id"])
        self.assertEqual("居酒屋", result["cuisine"])
        self.assertEqual("dinner", result["meal_price_signals"][0]["meal"])
        self.assertTrue(result["child_friendly"])
        self.assertFalse(result["parking_available"])
        self.assertEqual("non_smoking", result["smoking_policy"])
        self.assertEqual("unverified", result["opening_hours"]["status"])
        self.assertEqual([], result["opening_hours"]["intervals"])
        self.assertEqual(["水曜日"], result["opening_hours"]["regular_holidays"])
        self.assertIn("水曜日", result["opening_hours"]["note"])
        self.assertNotIn("rating", result)
        self.assertNotIn("recommended_dishes", result)
        self.assertIn("Powered by ホットペッパーグルメ Webサービス", result["attributions"])
        self.assertIn("key=hotpepper-key", client.calls[0][1])

    def test_official_feed_requires_exact_canonical_place_id(self):
        records = [
            {"place_id": "google-exact", "name": "公式店", "source_url": "https://restaurant.example/", "opening_hours": {"status": "fresh", "timezone": "Asia/Tokyo", "intervals": []}},
            {"place_id": "Google-Bad", "name": "別店", "source_url": "https://restaurant.example/bad"},
        ]
        results = list(OfficialRestaurantFeedAdapter(records, now=NOW).fetch(QUERY))
        self.assertEqual(1, len(results))
        self.assertEqual("official", results[0][1]["provenance"]["source_type"])

    def test_recommended_dishes_require_explicit_source_provenance(self):
        candidate = {"place": {"id": "restaurant", "name": "Restaurant", "kind": "restaurant"}}
        enriched = restaurant_intelligence(candidate, recommended_dishes=(
            {"name": "鯛めし", "note": "晚餐限定", "provenance": {"provider": "Official menu", "retrieved_at": NOW.isoformat(), "source_type": "official", "status": "confirmed", "confidence": 0.9}},
            {"name": "無來源料理"},
        ))
        self.assertEqual("鯛めし", enriched["recommended_dishes"][0]["name"])
        self.assertNotIn("無來源料理", str(enriched))

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
