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
