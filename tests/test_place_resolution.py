import json
from itertools import permutations
from pathlib import Path

from src.places import NavigationPoint, PlaceObservation, resolve_places, select_navigation_target
from src.schemas import validate_trip


FIXTURE = Path("fixtures/places/japan-place-observations.json")


def _observations():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        PlaceObservation(
            observation_id=row["observation_id"],
            name=row["name"],
            kind=row["kind"],
            provenance=row["provenance"],
            aliases=tuple(row.get("aliases", [])),
            identifiers=row.get("identifiers", {}),
            address=row.get("address"),
            coordinates=tuple(row["coordinates"]) if row.get("coordinates") else None,
        )
        for row in rows
    ]


def test_multilingual_observations_resolve_by_normalised_official_url():
    resolution = resolve_places(_observations())
    dazaifu = [decision for decision in resolution.decisions if decision.observation_id.startswith("dazaifu")]
    assert len({decision.canonical_place_id for decision in dazaifu}) == 1
    assert all(decision.state == "resolved" for decision in dazaifu)
    place = next(place for place in resolution.places if "Dazaifu Tenmangu" in place.aliases)
    assert place.name == "太宰府天満宮"
    assert len(place.field_provenance["name"]) == 2
    reversed_place = next(
        place for place in resolve_places(reversed(_observations())).places
        if "Dazaifu Tenmangu" in place.aliases
    )
    assert reversed_place.to_dict() == place.to_dict()


def test_complete_resolution_output_is_deterministic_for_input_permutations():
    baseline = resolve_places(_observations())
    baseline_places = [place.to_dict() for place in baseline.places]
    baseline_decisions = list(baseline.decisions)
    for order in permutations(_observations()):
        result = resolve_places(order)
        assert [place.to_dict() for place in result.places] == baseline_places
        assert list(result.decisions) == baseline_decisions


def test_chain_branches_remain_separate_and_reservation_links_to_branch():
    resolution = resolve_places(_observations())
    decisions = {decision.observation_id: decision for decision in resolution.decisions}
    assert decisions["chain-hakata"].canonical_place_id == decisions["reservation-hakata"].canonical_place_id
    assert decisions["chain-tenjin"].canonical_place_id != decisions["chain-hakata"].canonical_place_id


def test_reservation_reference_alone_is_not_place_identity():
    provenance = {"source_type": "provider", "provider": "booking", "retrieved_at": "2026-08-01T00:00:00Z", "status": "confirmed"}
    result = resolve_places([
        PlaceObservation("reservation-a", "店家", "restaurant", provenance, identifiers={"reservation_reference": "same-ref"}),
        PlaceObservation("reservation-b", "店家", "restaurant", provenance, identifiers={"reservation_reference": "same-ref"}),
    ])
    assert len(result.places) == 2
    assert all(item.state == "clarification_required" for item in result.decisions)


def test_reservation_collision_does_not_bridge_different_google_places():
    provenance = {"source_type": "provider", "provider": "booking", "retrieved_at": "2026-08-01T00:00:00Z", "status": "confirmed"}
    result = resolve_places([
        PlaceObservation("branch-a", "連鎖店", "restaurant", provenance, identifiers={"google_place_id": "branch-a", "reservation_reference": "collision"}),
        PlaceObservation("branch-b", "連鎖店", "restaurant", provenance, identifiers={"google_place_id": "branch-b", "reservation_reference": "collision"}),
    ])
    assert len(result.places) == 2
    assert len({item.canonical_place_id for item in result.decisions}) == 2


def test_shared_brand_identifiers_do_not_merge_conflicting_google_branches():
    official = {"source_type": "official", "provider": "brand", "retrieved_at": "2026-08-01T00:00:00Z", "status": "confirmed"}
    for shared in (
        {"official_url": "https://chain.example/", "google_place_id": "branch-a"},
        {"provider_reference": "brand-page", "google_place_id": "branch-a"},
    ):
        other = dict(shared, google_place_id="branch-b")
        result = resolve_places([
            PlaceObservation("branch-a", "Chain A", "restaurant", official, identifiers=shared),
            PlaceObservation("branch-b", "Chain B", "restaurant", official, identifiers=other),
        ])
        assert len(result.places) == 2
        assert all(item.state == "clarification_required" for item in result.decisions)
        assert all(item.confidence < 1 for item in result.decisions)


def test_provider_references_are_namespaced_by_provider():
    provider_a = {"source_type": "provider", "provider": "catalog-a", "retrieved_at": "2026-08-01T00:00:00Z", "status": "confirmed"}
    provider_b = {"source_type": "provider", "provider": "catalog-b", "retrieved_at": "2026-08-01T00:00:00Z", "status": "confirmed"}
    result = resolve_places([
        PlaceObservation("catalog-a", "First", "poi", provider_a, identifiers={"provider_reference": "123"}),
        PlaceObservation("catalog-b", "Second", "poi", provider_b, identifiers={"provider_reference": "123"}),
    ])
    assert len(result.places) == 2
    assert len({item.canonical_place_id for item in result.decisions}) == 2


def test_name_only_matches_require_clarification_instead_of_auto_merge():
    provenance = {"source_type": "community", "provider": "notes", "retrieved_at": "2026-08-01T00:00:00Z", "status": "unverified"}
    resolution = resolve_places([
        PlaceObservation("one", "中央公園", "poi", provenance),
        PlaceObservation("two", "中央公園", "poi", provenance),
    ])
    assert len(resolution.places) == 2
    assert all(decision.state == "clarification_required" for decision in resolution.decisions)
    assert all(decision.clarification for decision in resolution.decisions)


def test_authority_merge_records_coordinate_conflict_and_preserves_navigation_point():
    official = {"source_type": "official", "provider": "venue", "retrieved_at": "2026-08-01T00:00:00Z", "status": "confirmed"}
    provider = {"source_type": "provider", "provider": "maps", "retrieved_at": "2026-08-02T00:00:00Z", "status": "reported"}
    parking = NavigationPoint("venue-parking", "parking", "P1", (33.0, 130.0), mapcode="12 345 678*90", provenance=official)
    result = resolve_places([
        PlaceObservation("official", "会場", "poi", official, identifiers={"google_place_id": "venue-1"}, coordinates=(33.1, 130.1), navigation_points=(parking,)),
        PlaceObservation("maps", "Venue", "poi", provider, identifiers={"google_place_id": "venue-1"}, coordinates=(33.2, 130.2)),
    ])
    place = result.places[0]
    assert place.coordinates == (33.1, 130.1)
    assert place.coordinate_conflicts[0]["coordinates"] == {"latitude": 33.2, "longitude": 130.2}
    target = select_navigation_target(place, "driving")
    assert target["navigation_point_id"] == "venue-parking"
    assert target["coordinates"] == {"latitude": 33.0, "longitude": 130.0}
    assert place.coordinates != parking.coordinates


def test_identifier_provenance_is_bound_to_each_identifier_and_schema_valid():
    observations = _observations()[:2]
    place = resolve_places(observations).places[0]
    rendered = place.to_dict()
    identifiers = {item["value"]: item["provenance"]["provider"] for item in rendered["identifiers"]}
    assert identifiers["https://www.dazaifutenmangu.or.jp/"] == "Dazaifu Tenmangu"
    assert identifiers["https://www.dazaifutenmangu.or.jp"] == "travel video"
    assert all(rendered["field_provenance"].values())

    trip = json.loads(Path("fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
    trip["candidate_sets"]["places"].append(rendered)
    validate_trip(trip)


def test_navigation_selector_supports_walking_meeting_and_main_fallback():
    provenance = {"source_type": "official", "provider": "venue", "retrieved_at": "2026-08-01T00:00:00Z", "status": "confirmed"}
    points = (
        NavigationPoint("venue-exit", "station_exit", coordinates=(1.0, 2.0), provenance=provenance),
        NavigationPoint("venue-entrance", "entrance", coordinates=(3.0, 4.0), provenance=provenance),
        NavigationPoint("venue-meeting", "meeting_point", phone="+81-90-1234-5678", provenance=provenance),
    )
    place = resolve_places([PlaceObservation(
        "venue", "Venue", "poi", provenance, identifiers={"google_place_id": "venue"},
        coordinates=(5.0, 6.0), navigation_points=points,
    )]).places[0]
    assert select_navigation_target(place, "walking")["navigation_point_id"] == "venue-entrance"
    assert select_navigation_target(place, "meeting")["navigation_point_id"] == "venue-meeting"
    main = select_navigation_target(place, "main")
    assert main == {"place_id": place.id, "kind": "main", "coordinates": {"latitude": 5.0, "longitude": 6.0}}
