import json
from datetime import datetime, timezone
from pathlib import Path

from src.operations import build_handbook


FIXTURE = Path("fixtures/trips/japan-5-day-trip-v1.json")
NOW = datetime(2026, 4, 10, tzinfo=timezone.utc)
PROVENANCE = {"source_type": "official", "provider": "Official provider", "source_url": "https://example.test/operations", "retrieved_at": "2026-04-09T00:00:00+00:00", "status": "confirmed"}


def test_five_day_handbook_derives_navigation_and_only_canonical_place_references():
    handbook = build_handbook(_trip(), {"place_operations": [{"place_id": "dazaifu", "entrance": "東門", "parking": "P1", "mapcode": "55 364 112", "phone": "092-922-8225", "provenance": PROVENANCE}, {"place_id": "invented", "phone": "secret", "provenance": PROVENANCE}]}, now=NOW)
    assert len(handbook["daily_operations"]) == 5
    assert handbook["daily_operations"][2]["stop_place_ids"] == ["dazaifu"]
    assert "google.com/maps/dir" in handbook["daily_operations"][2]["google_maps_url"]
    assert handbook["place_operations"] == [{"entrance": "東門", "parking": "P1", "mapcode": "55 364 112", "phone": "092-922-8225", "provenance": PROVENANCE, "place_id": "dazaifu", "place_name": "太宰府天滿宮", "freshness": {"state": "fresh", "retrieved_at": PROVENANCE["retrieved_at"]}}]


def test_reservations_are_redacted_and_recheck_list_is_present():
    handbook = build_handbook(_trip(), {"reservations": [{"kind": "hotel", "place_id": "hakata-hotel", "confirmationCode": "ABCDEF1234", "email": "family@example.test", "phone": "09012345678", "guest_name": "王小明", "passport_number": "A123456789", "nested": {"access_code": "private"}, "provenance": PROVENANCE}]}, now=NOW)
    reservation = handbook["reservations"][0]
    assert reservation["confirmation_display"] == "…1234"
    rendered = json.dumps(handbook, ensure_ascii=False)
    for secret in ("ABCDEF1234", "family@example.test", "09012345678", "王小明", "A123456789", "private"):
        assert secret not in rendered
    assert {check["kind"] for check in handbook["departure_recheck"]} >= {"route", "conditions", "flight", "reservation"}


def test_dynamic_facts_keep_provenance_and_expose_staleness_without_assuming_open():
    stale = {**PROVENANCE, "retrieved_at": "2026-03-01T00:00:00+00:00"}
    handbook = build_handbook(_trip(), {"conditions": [{"place_id": "dazaifu", "weather": "rain", "rain_plan": "室內替代方案", "provenance": stale}], "supplies": [{"place_id": "dazaifu", "kind": "gas_station", "name": "補給站", "provenance": PROVENANCE}]}, now=NOW)
    assert handbook["conditions"][0]["freshness"]["state"] == "stale"
    assert handbook["supplies"][0]["provenance"]["source_url"] == PROVENANCE["source_url"]
    assert handbook["sources"][0]["freshness"]["state"] == "stale"


def test_missing_provenance_is_visible_as_unknown():
    handbook = build_handbook(_trip(), {"conditions": [{"place_id": "dazaifu", "advisory": "請確認現況"}]}, now=NOW)
    assert handbook["conditions"][0]["freshness"] == {"state": "unknown", "retrieved_at": None}


def test_evidence_without_a_canonical_reference_is_excluded():
    handbook = build_handbook(_trip(), {"reservations": [{"kind": "hotel", "confirmation_number": "not-public", "provenance": PROVENANCE}], "conditions": [{"advisory": "not-public", "provenance": PROVENANCE}], "supplies": [{"kind": "gas_station", "provenance": PROVENANCE}]}, now=NOW)
    assert handbook["reservations"] == handbook["conditions"] == handbook["supplies"] == []


def test_future_and_same_url_evidence_keep_invalid_and_stale_freshness_visible():
    future = {**PROVENANCE, "retrieved_at": "2027-01-01T00:00:00+00:00"}
    stale = {**PROVENANCE, "retrieved_at": "2026-03-01T00:00:00+00:00"}
    handbook = build_handbook(_trip(), {"conditions": [{"place_id": "dazaifu", "advisory": "future", "provenance": future}, {"place_id": "dazaifu", "advisory": "stale", "provenance": stale}]}, now=NOW)
    assert [item["freshness"]["state"] for item in handbook["conditions"]] == ["invalid", "stale"]
    assert [item["freshness"]["state"] for item in handbook["sources"]] == ["invalid", "stale"]


def _trip():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))
