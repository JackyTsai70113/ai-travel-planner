import json
import socket
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.sources import (
    FactEvidence,
    FactKind,
    FactStatus,
    OperationalFact,
    SourceAuthority,
    evaluate_last_admission,
    evaluate_temporary_closure,
    parse_official_fixture,
    reconcile_facts,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "official-sites"
NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def make_fact(
    value,
    *,
    subject_id="place-1",
    kind=FactKind.LAST_ADMISSION,
    authority=SourceAuthority.OFFICIAL,
    retrieved_at=NOW,
    source_url="https://official.example/fact",
    status=FactStatus.CONFIRMED,
    valid_from=None,
    valid_until=None,
):
    return OperationalFact(
        subject_id=subject_id,
        kind=kind,
        value=value,
        evidence=FactEvidence(
            source_type=authority,
            provider=f"{authority.value}-source",
            source_url=source_url,
            retrieved_at=retrieved_at,
        ),
        valid_from=valid_from,
        valid_until=valid_until,
        status=status,
    )


class OfficialFixtureParserTests(unittest.TestCase):
    def test_two_recorded_fixture_profiles_parse_offline(self):
        cases = (
            (
                "fukuoka-museum-tourism.json",
                "tourism-site-v1",
                "fukuoka-city-museum",
                FactKind.TEMPORARY_CLOSURE,
            ),
            (
                "kyushu-road-advisory.json",
                "operator-advisory-v1",
                "aso-scenic-road",
                FactKind.ROAD_CLOSURE,
            ),
        )

        with patch.object(socket, "socket", side_effect=AssertionError("live network")):
            for filename, profile, subject_id, expected_kind in cases:
                with self.subTest(profile=profile):
                    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
                    self.assertEqual(json.loads(text)["profile"], profile)
                    result = parse_official_fixture(text, profile)
                    self.assertEqual(result.errors, ())
                    self.assertTrue(result.facts)
                    self.assertIn(subject_id, {fact.subject_id for fact in result.facts})
                    self.assertIn(expected_kind, {fact.kind for fact in result.facts})
                    self.assertTrue(
                        all(
                            fact.evidence.source_type == SourceAuthority.OFFICIAL
                            for fact in result.facts
                        )
                    )

    def test_parser_failure_returns_errors_without_trusted_values(self):
        malformed_inputs = (
            ("not json", "tourism-site-v1"),
            ('{"records": "not-a-list"}', "tourism-site-v1"),
            ('{"advisories": [{}]}', "operator-advisory-v1"),
            ('{"records": []}', "unknown-profile"),
        )

        for text, profile in malformed_inputs:
            with self.subTest(profile=profile, text=text):
                result = parse_official_fixture(text, profile)
                self.assertEqual(result.facts, ())
                self.assertTrue(result.errors)

    def test_invalid_fact_fields_are_not_filled_or_confirmed(self):
        recorded = json.dumps(
            {
                "site": "official",
                "retrieved_at": "2026-08-01T00:00:00Z",
                "records": [
                    {
                        "subject_id": "place-1",
                        "source_url": "https://official.example/place-1",
                        "facts": {
                            "last_admission": None,
                            "not_a_supported_fact": "invented",
                        },
                    }
                ],
            }
        )

        result = parse_official_fixture(recorded, "tourism-site-v1")

        self.assertEqual(result.facts, ())
        self.assertEqual(len(result.errors), 2)

    def test_closure_facts_require_boolean_values(self):
        for kind in ("temporary_closure", "road_closure"):
            with self.subTest(kind=kind):
                recorded = json.dumps(
                    {
                        "site": "official",
                        "retrieved_at": "2026-08-01T00:00:00Z",
                        "records": [
                            {
                                "subject_id": "place-1",
                                "source_url": "https://official.example/place-1",
                                "facts": {kind: "yes"},
                            }
                        ],
                    }
                )

                result = parse_official_fixture(recorded, "tourism-site-v1")

                self.assertEqual(result.facts, ())
                self.assertTrue(result.errors)

    def test_last_admission_requires_valid_iso_local_time(self):
        recorded = json.dumps(
            {
                "site": "official",
                "retrieved_at": "2026-08-01T00:00:00Z",
                "records": [
                    {
                        "subject_id": "place-1",
                        "source_url": "https://official.example/place-1",
                        "facts": {"last_admission": "25:00"},
                    }
                ],
            }
        )

        result = parse_official_fixture(recorded, "tourism-site-v1")

        self.assertEqual(result.facts, ())
        self.assertTrue(result.errors)


class AuthorityReconciliationTests(unittest.TestCase):
    def test_official_wins_provider_and_community_conflict_deterministically(self):
        community = make_fact(
            "18:00",
            authority=SourceAuthority.COMMUNITY,
            source_url="https://community.example/place-1",
        )
        provider = make_fact(
            "17:30",
            authority=SourceAuthority.PROVIDER,
            source_url="https://provider.example/place-1",
        )
        official = make_fact("17:00")

        forward = reconcile_facts([community, official, provider], now=NOW)[0]
        reverse = reconcile_facts([provider, official, community], now=NOW)[0]

        for result in (forward, reverse):
            self.assertEqual(result.value, "17:00")
            self.assertEqual(
                result.selected.evidence.source_type, SourceAuthority.OFFICIAL
            )
            self.assertEqual(result.status, FactStatus.CONTRADICTORY)
            self.assertEqual(result.selected.status, FactStatus.CONTRADICTORY)
            self.assertEqual(len(result.evidence), 3)

    def test_provider_beats_community_when_official_is_absent(self):
        community = make_fact("17:00", authority=SourceAuthority.COMMUNITY)
        provider = make_fact("17:00", authority=SourceAuthority.PROVIDER)

        result = reconcile_facts([community, provider], now=NOW)[0]

        self.assertEqual(result.status, FactStatus.CONFIRMED)
        self.assertEqual(result.selected.evidence.source_type, SourceAuthority.PROVIDER)

    def test_stale_selected_official_is_never_confirmed(self):
        official = make_fact(
            "17:00",
            retrieved_at=NOW - timedelta(days=31),
        )
        provider = make_fact(
            "17:00",
            authority=SourceAuthority.PROVIDER,
            retrieved_at=NOW,
        )

        result = reconcile_facts(
            [provider, official], now=NOW, max_age=timedelta(days=30)
        )[0]

        self.assertEqual(result.selected.evidence.source_type, SourceAuthority.OFFICIAL)
        self.assertEqual(result.status, FactStatus.STALE)
        self.assertNotEqual(result.status, FactStatus.CONFIRMED)

    def test_explicit_contradictory_fact_is_never_confirmed(self):
        fact = make_fact("17:00", status=FactStatus.CONTRADICTORY)

        result = reconcile_facts([fact], now=NOW)[0]

        self.assertEqual(result.status, FactStatus.CONTRADICTORY)
        self.assertNotEqual(result.selected.status, FactStatus.CONFIRMED)

    def test_future_evidence_is_not_a_current_contradiction(self):
        future_official = make_fact(
            "16:00",
            valid_from=NOW + timedelta(days=1),
            valid_until=NOW + timedelta(days=30),
        )
        current_provider = make_fact(
            "17:00",
            authority=SourceAuthority.PROVIDER,
            valid_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(hours=1),
        )

        result = reconcile_facts([future_official, current_provider], now=NOW)[0]

        self.assertEqual(result.status, FactStatus.UNVERIFIED)

    def test_fresh_explicit_stale_fact_is_not_promoted_to_confirmed(self):
        result = reconcile_facts(
            [make_fact("17:00", status=FactStatus.STALE)], now=NOW
        )[0]

        self.assertEqual(result.status, FactStatus.STALE)

    def test_fresh_explicit_unverified_fact_is_not_promoted_to_confirmed(self):
        result = reconcile_facts(
            [make_fact("17:00", status=FactStatus.UNVERIFIED)], now=NOW
        )[0]

        self.assertEqual(result.status, FactStatus.UNVERIFIED)

    def test_future_retrieval_timestamp_is_not_confirmed(self):
        result = reconcile_facts(
            [make_fact("17:00", retrieved_at=NOW + timedelta(minutes=1))], now=NOW
        )[0]

        self.assertEqual(result.status, FactStatus.UNVERIFIED)


class SharedOperationalEvaluationTests(unittest.TestCase):
    def test_temporary_closure_uses_confirmed_applicable_window(self):
        closure = make_fact(
            True,
            kind=FactKind.TEMPORARY_CLOSURE,
            valid_from=datetime(2026, 8, 15, 3, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 8, 15, 21, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(evaluate_temporary_closure([closure], NOW))
        self.assertIsNone(
            evaluate_temporary_closure(
                [closure], datetime(2026, 8, 16, 0, 0, tzinfo=timezone.utc)
            )
        )
        self.assertIsNone(
            evaluate_temporary_closure(
                [make_fact(True, kind=FactKind.TEMPORARY_CLOSURE,
                           status=FactStatus.CONTRADICTORY)],
                NOW,
            )
        )

    def test_road_closure_uses_the_same_shared_closure_interface(self):
        road_closure = make_fact(True, kind=FactKind.ROAD_CLOSURE)

        self.assertTrue(evaluate_temporary_closure([road_closure], NOW))

    def test_malformed_confirmed_closure_value_is_unknown(self):
        malformed = make_fact(
            "false",
            kind=FactKind.TEMPORARY_CLOSURE,
            status=FactStatus.CONFIRMED,
        )

        self.assertIsNone(evaluate_temporary_closure([malformed], NOW))

    def test_last_admission_returns_only_confirmed_applicable_valid_time(self):
        admission = make_fact(
            "17:00",
            valid_from=datetime(2026, 7, 1, tzinfo=timezone.utc),
            valid_until=datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
        )

        self.assertEqual(
            evaluate_last_admission([admission], date(2026, 8, 15)).isoformat(),
            "17:00:00",
        )
        self.assertIsNone(
            evaluate_last_admission([admission], date(2027, 1, 1))
        )
        self.assertIsNone(
            evaluate_last_admission(
                [make_fact("17:00", status=FactStatus.STALE)], date(2026, 8, 15)
            )
        )
        self.assertIsNone(
            evaluate_last_admission([make_fact("invalid")], date(2026, 8, 15))
        )

    def test_temporary_closure_does_not_leak_between_subjects(self):
        other_place_closure = make_fact(
            True,
            subject_id="place-2",
            kind=FactKind.TEMPORARY_CLOSURE,
        )

        self.assertIsNone(
            evaluate_temporary_closure(
                [other_place_closure], NOW, subject_id="place-1"
            )
        )

    def test_last_admission_does_not_leak_between_subjects(self):
        other_place_admission = make_fact("16:00", subject_id="place-2")

        self.assertIsNone(
            evaluate_last_admission(
                [other_place_admission], date(2026, 8, 15), subject_id="place-1"
            )
        )

    def test_last_admission_valid_and_malformed_conflict_is_unknown_in_any_order(self):
        valid = make_fact("17:00")
        malformed = make_fact("not-a-time")

        for facts in ([valid, malformed], [malformed, valid]):
            with self.subTest(order=[fact.value for fact in facts]):
                self.assertIsNone(
                    evaluate_last_admission(facts, date(2026, 8, 15))
                )

    def test_different_confirmed_last_admissions_are_unknown_in_any_order(self):
        earlier = make_fact("16:30")
        later = make_fact("17:00")

        for facts in ([earlier, later], [later, earlier]):
            with self.subTest(order=[fact.value for fact in facts]):
                self.assertIsNone(
                    evaluate_last_admission(facts, date(2026, 8, 15))
                )

    def test_identical_confirmed_last_admissions_return_deterministic_time(self):
        first = make_fact("17:00", source_url="https://official.example/a")
        second = make_fact("17:00", source_url="https://official.example/b")

        for facts in ([first, second], [second, first]):
            with self.subTest(order=[fact.evidence.source_url for fact in facts]):
                result = evaluate_last_admission(facts, date(2026, 8, 15))
                self.assertIsNotNone(result)
                self.assertEqual(result.isoformat(), "17:00:00")


if __name__ == "__main__":
    unittest.main()
