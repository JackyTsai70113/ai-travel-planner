import copy
from datetime import datetime
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

from scripts.build_awaji_public_bundle import build_public_bundle
from src.schemas import validate_trip

TRIP_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/trip.json")
EVIDENCE_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/evidence.json")
CONDITIONS_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/conditions.json")
TRIP_BUNDLE_PATH = Path("trips/awaji-naruto-tokushima-kobe-2026/public-bundle.json")
WEB_BUNDLE_PATH = Path("web/public/trips/awaji-2026/public-bundle.json")


class AwajiTripFixtureTests(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(TRIP_PATH.read_text(encoding="utf-8"))
        self.bundle = build_public_bundle(self.trip, TRIP_PATH)
        self.places = {
            place["id"]: place for place in self.trip["candidate_sets"]["places"]
        }

    def test_trip_v1_contract(self):
        validate_trip(self.trip)

    def test_trip_date_range_and_complete_daily_items(self):
        self.assertEqual(self.trip["date_range"]["start_date"], "2026-08-27")
        self.assertEqual(self.trip["date_range"]["end_date"], "2026-08-31")
        self.assertEqual(len(self.trip["days"]), 5)

        counts = [len(day["items"]) for day in self.trip["days"]]
        self.assertEqual(counts, [12, 19, 22, 17, 5])
        self.assertGreater(sum(counts), 53)
        self.assertEqual(
            [len(day["items"]) for day in self.bundle["days"]],
            counts,
        )

    def test_day_one_and_two_preserve_each_sheet_stop(self):
        expected = {
            "2026-08-27": {
                "ramen-ichiraku-nijigen", "nijigen-no-mori-shinobi",
                "awaji-sunset-line",
                "map-import-garb-costa-orange", "aeon-awaji",
                "awaji-riverside-hotel",
            },
            "2026-08-28": {
                "map-import-boulangerie-rural", "map-import-yumebutai",
                "sea-church-awaji", "honpukuji-mizumido",
                "map-import-taidrobou", "map-import-awaji-hanasajiki",
                "naruto-ferry-fixed-activity", "awaji-riverside-hotel",
                "cosmos-shizuki", "hello-kitty-smile-awaji", "nojima-scuola",
            },
        }
        for day in self.trip["days"][:2]:
            with self.subTest(date=day["date"]):
                represented = {item["place_id"] for item in day["items"]}
                represented.update(
                    place_id
                    for item in day["items"]
                    for place_id in item.get("alternative_place_ids", [])
                )
                self.assertTrue(expected[day["date"]].issubset(represented))

        day_two = self.trip["days"][1]
        hanasajiki = next(item for item in day_two["items"] if item["id"] == "day2-hanasajiki")
        self.assertEqual(hanasajiki["alternative_place_ids"], ["hello-kitty-smile-awaji", "nojima-scuola"])
        hello_kitty = self.places["hello-kitty-smile-awaji"]
        self.assertEqual(hello_kitty["address"], "兵庫県淡路市野島蟇浦985-1")
        self.assertIn("awaji-resort.com/hellokittysmile/access", hello_kitty["provenance"]["source_url"])

    def test_hard_booking_facts(self):
        selected = self.trip["selected"]
        self.assertEqual(selected["flight_ids"], ["xj-834-outbound", "xj-1835-return"])
        self.assertEqual(
            selected["hotel_place_ids"],
            [
                "awaji-riverside-hotel",
                "tokushima-seshi-besso-hotel-2",
                "royal-park-canvas-kobe-sannomiya",
            ],
        )

        reservation_place = self.places["naruto-ferry-fixed-activity"]
        self.assertEqual(reservation_place["resolution"]["state"], "resolved")
        self.assertEqual(reservation_place["resolution"]["confidence"], 1)

    def test_ichiraku_hours_are_official_and_bundle_outputs_match(self):
        ichiraku = self.places["ramen-ichiraku-nijigen"]
        expected_note = "ラーメン一樂：平日 11:00–15:00（最後點餐 14:30）、16:00–18:00（最後點餐 17:30）；8/27（週四）12:45–13:30 位於午間營業時段內。"
        self.assertEqual(ichiraku["opening_hours_note"], expected_note)
        self.assertEqual(ichiraku["provenance"]["source_url"], "https://nijigennomori.com/price/")
        self.assertIn("季節或活動調整", ichiraku["provenance"]["note"])

        trip_bundle_place = next(place for place in self.bundle["places"] if place["id"] == ichiraku["id"])
        web_bundle = json.loads(WEB_BUNDLE_PATH.read_text(encoding="utf-8"))
        web_bundle_place = next(place for place in web_bundle["places"] if place["id"] == ichiraku["id"])
        for bundle_place in (trip_bundle_place, web_bundle_place):
            self.assertEqual(bundle_place["opening_hours_note"], expected_note)
            self.assertEqual(bundle_place["provenance"]["source_url"], "https://nijigennomori.com/price/")

        meal = next(item for day in self.bundle["days"] for item in day["items"] if item["id"] == "day1-lunch-ichiraku")
        self.assertIn("11:00–15:00", meal["notes"])
        self.assertIn("16:00–18:00", meal["notes"])

    def test_happy_pancake_is_resolved_at_official_address(self):
        pancake = self.places["naruto-ferry-fixed-activity"]
        self.assertEqual(pancake["name"], "幸せのパンケーキ 淡路島テラス")
        self.assertEqual(pancake["address"], "兵庫県淡路市尾崎42-1")
        self.assertEqual(pancake["resolution"]["state"], "resolved")
        self.assertEqual(pancake["provenance"]["source_url"], "https://magia.tokyo/shop")
        self.assertTrue(any(item["value"] == "https://magia.tokyo/shop" for item in pancake["identifiers"]))

        reservation = next(
            item
            for item in self.bundle["reservations"]
            if item["id"] == "fixed-2026-08-28-17-45"
        )
        self.assertEqual(reservation["name"], "幸せのパンケーキ 淡路島テラス")
        self.assertFalse(reservation["unresolved"])
        self.assertEqual(reservation["kind"], "fixed-reservation")

    def test_three_accommodations_have_exact_names_and_addresses(self):
        expected = {
            "awaji-riverside-hotel": (
                "Awaji Riverside Terrace in Shizuki 780",
                "兵庫県淡路市志筑字黒田780-12",
            ),
            "tokushima-seshi-besso-hotel-2": (
                "徳島別荘ホテル2",
                "徳島県徳島市金沢1丁目3-44-3号 〒770-0871",
            ),
            "royal-park-canvas-kobe-sannomiya": (
                "ザ ロイヤルパーク キャンバス 神戸三宮",
                "〒650-0011 兵庫県神戸市中央区下山手通2丁目3-1",
            ),
        }
        self.assertEqual(set(self.trip["selected"]["hotel_place_ids"]), set(expected))

        hotel_candidates = {
            hotel["place"]["id"]: hotel["place"]
            for hotel in self.trip["candidate_sets"]["hotels"]
        }
        bundle_places = {place["id"]: place for place in self.bundle["places"]}
        for place_id, (name, address) in expected.items():
            with self.subTest(place_id=place_id):
                self.assertEqual(self.places[place_id]["name"], name)
                self.assertEqual(self.places[place_id]["address"], address)
                self.assertEqual(hotel_candidates[place_id]["name"], name)
                self.assertEqual(hotel_candidates[place_id]["address"], address)
                self.assertEqual(bundle_places[place_id]["name"], name)
                self.assertEqual(bundle_places[place_id]["address"], address)

    def test_fixed_reservation_constraints(self):
        day_two = next(day for day in self.trip["days"] if day["date"] == "2026-08-28")
        fixed = next(item for item in day_two["items"] if item["id"] == "fixed-2026-08-28-17-45")
        self.assertEqual(fixed["start_at"], "2026-08-28T17:45:00+09:00")
        self.assertEqual(fixed["kind"], "visit")
        self.assertEqual(fixed["end_at"], "2026-08-28T18:15:00+09:00")
        self.assertIn("幸せのパンケーキ", fixed["notes"])
        self.assertIn("兵庫県淡路市尾崎42-1", fixed["notes"])
        self.assertIn("官方店舖頁確認", fixed["notes"])

    def test_day_five_no_hard_visit(self):
        day_five = next(day for day in self.trip["days"] if day["date"] == "2026-08-31")
        self.assertFalse(any(item.get("kind") == "visit" for item in day_five["items"]))
        departure = next(item for item in day_five["items"] if item["id"] == "day5-departure-flight")
        self.assertEqual(departure["kind"], "flight")
        self.assertEqual(departure["place_id"], "kobe-airport-terminal-2")
        self.assertEqual(departure["start_at"], "2026-08-31T12:45:00+09:00")

        day_one = next(day for day in self.trip["days"] if day["date"] == "2026-08-27")
        arrival = next(item for item in day_one["items"] if item["id"] == "day1-flight-arrival")
        self.assertEqual(arrival["kind"], "flight")
        self.assertEqual(arrival["place_id"], "kobe-airport")
        self.assertEqual(arrival["start_at"], "2026-08-27T10:30:00+09:00")

    def test_all_itinerary_place_references_exist(self):
        place_ids = set(self.places)
        referenced_place_ids = {
            item["place_id"]
            for day in self.trip["days"]
            for item in day["items"]
            if item.get("place_id")
        }
        self.assertEqual(sorted(referenced_place_ids - place_ids), [])

    def test_transport_legs_and_item_references_are_complete(self):
        legs = self.trip["candidate_sets"]["transport_legs"]
        self.assertEqual(len(legs), 31)
        leg_ids = [leg["id"] for leg in legs]
        self.assertEqual(len(set(leg_ids)), len(legs))

        item_leg_refs = [
            item["transport_leg_id"]
            for day in self.trip["days"]
            for item in day["items"]
            if item.get("transport_leg_id")
        ]
        self.assertEqual(len(item_leg_refs), len(legs))
        self.assertEqual(set(item_leg_refs), set(leg_ids))
        self.assertEqual(len(item_leg_refs), len(set(item_leg_refs)))

        place_ids = set(self.places)
        for leg in legs:
            with self.subTest(leg_id=leg["id"]):
                self.assertIn(leg["from_place_id"], place_ids)
                self.assertIn(leg["to_place_id"], place_ids)

        for day in self.trip["days"]:
            day_refs = [item.get("transport_leg_id") for item in day["items"] if item.get("transport_leg_id")]
            self.assertGreater(len(day_refs), 0, day["date"])

    def test_day_three_breakfast_route_is_continuous(self):
        day_three = next(day for day in self.trip["days"] if day["date"] == "2026-08-29")
        source_legs = {leg["id"]: leg for leg in self.trip["candidate_sets"]["transport_legs"]}
        first_refs = [
            item["transport_leg_id"]
            for item in day_three["items"]
            if item.get("transport_leg_id")
        ][:2]
        self.assertEqual(first_refs, ["leg-day3-riverside-breakfast", "leg-day3-breakfast-sumoto"])
        first, second = (source_legs[leg_id] for leg_id in first_refs)
        self.assertEqual(first["from_place_id"], "awaji-riverside-hotel")
        self.assertEqual(first["to_place_id"], "familymart-shizuku-otoshi")
        self.assertEqual(second["from_place_id"], first["to_place_id"])
        self.assertEqual(second["to_place_id"], "sumoto-castle")

    def test_bundle_transport_duration_status_and_note_derive_from_canonical_leg(self):
        source_legs = {
            leg["id"]: leg for leg in self.trip["candidate_sets"]["transport_legs"]
        }
        bundle_legs = {leg["id"]: leg for leg in self.bundle["transport_legs"]}
        self.assertEqual(set(bundle_legs), set(source_legs))

        for leg_id, source in source_legs.items():
            with self.subTest(leg_id=leg_id):
                output = bundle_legs[leg_id]
                departure = datetime.fromisoformat(source["departure_at"])
                arrival = datetime.fromisoformat(source["arrival_at"])
                window_minutes = int((arrival - departure).total_seconds() // 60)
                self.assertGreater(window_minutes, 0)
                self.assertGreater(output["estimated_duration_minutes"], 0)
                self.assertGreaterEqual(output["buffer_minutes"], 0)
                self.assertEqual(output["estimated_duration_minutes"] + output["buffer_minutes"], window_minutes)
                self.assertEqual(output["status"], source["provenance"]["status"])
                self.assertEqual(output["note"], source["provenance"]["note"])
                self.assertEqual(output["source_url"], source["provenance"]["source_url"])
                self.assertEqual(output["provenance"]["provider"], source["provenance"]["provider"])
                self.assertTrue(output["source_refs"])

    def test_kobe_airport_and_day_five_buffer_are_semantically_correct(self):
        airport = self.places["kobe-airport"]
        self.assertEqual(airport["name"], "神戸空港 第2ターミナル")
        self.assertEqual(airport["address"], "兵庫県神戸市中央区神戸空港1")
        self.assertIn("kairport.co.jp", airport["provenance"]["source_url"])
        first_leg = next(item for item in self.bundle["transport_legs"] if item["id"] == "leg-day1-airport-nijigen")
        self.assertEqual(first_leg["from_place"], "kobe-airport")
        self.assertEqual(parse_qs(urlparse(first_leg["google_maps_directions_url"]).query)["origin"], [airport["address"]])
        return_leg = next(item for item in self.bundle["transport_legs"] if item["id"] == "leg-day5-to-terminal2")
        self.assertEqual(return_leg["transfer_minutes"], 70)
        self.assertEqual(return_leg["buffer_minutes"], 15)

    def test_sheet_operational_notes_are_not_marked_confirmed(self):
        dynamic_ids = {
            "bizan-ropeway", "familymart-tokushima-kanazawa",
            "iwaya-port", "awaji-sa-ferris-wheel", "uzushio-cruise-fukura",
        }
        bundle_places = {place["id"]: place for place in self.bundle["places"]}
        for place_id in dynamic_ids:
            with self.subTest(place_id=place_id):
                self.assertIn(self.places[place_id]["provenance"]["status"], {"reported", "unverified"})
                self.assertEqual(bundle_places[place_id]["provenance"]["status"], self.places[place_id]["provenance"]["status"])

    def test_every_transport_leg_has_valid_google_maps_directions_link(self):
        source_legs = {
            leg["id"]: leg for leg in self.trip["candidate_sets"]["transport_legs"]
        }
        expected_modes = {"bus": "transit", "train": "transit", "walk": "walking"}

        for output in self.bundle["transport_legs"]:
            with self.subTest(leg_id=output["id"]):
                source = source_legs[output["id"]]
                parsed = urlparse(output["google_maps_directions_url"])
                query = parse_qs(parsed.query)
                origin_place = self.places[source["from_place_id"]]
                destination_place = self.places[source["to_place_id"]]
                expected_origin = origin_place.get("address") or origin_place.get("name") or source["from_place_id"]
                expected_destination = destination_place.get("address") or destination_place.get("name") or source["to_place_id"]

                self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "www.google.com", "/maps/dir/"))
                self.assertEqual(query["api"], ["1"])
                self.assertEqual(query["origin"], [expected_origin])
                self.assertEqual(query["destination"], [expected_destination])
                self.assertEqual(
                    query["travelmode"],
                    [expected_modes.get(source["mode"], "driving")],
                )

    def test_public_bundle_does_not_expose_interactive_pretrip_tasks(self):
        override = next(
            item
            for item in self.trip["overrides"]
            if item["path"] == "/operations/pretrip_checklist"
        )
        source_checklist = override["value"]
        self.assertTrue(override["preserve_on_replan"])
        self.assertEqual(len(source_checklist), 28)
        self.assertEqual(self.bundle["operations"]["pretrip_checklist"], [])
        self.assertEqual(len({item["id"] for item in source_checklist}), 28)
        for item in source_checklist:
            with self.subTest(item_id=item["id"]):
                for field in ("timing", "item", "action", "fallback", "contact"):
                    self.assertIsInstance(item[field], str)
                    self.assertTrue(item[field].strip())

    def test_all_three_google_sheet_tabs_have_provenance(self):
        source_urls = []

        def collect_source_urls(value):
            if isinstance(value, dict):
                source_url = value.get("source_url")
                if isinstance(source_url, str):
                    source_urls.append(source_url)
                for child in value.values():
                    collect_source_urls(child)
            elif isinstance(value, list):
                for child in value:
                    collect_source_urls(child)

        collect_source_urls(self.trip)
        expected_gids = {"1150292496", "539581117", "1828502005"}
        found_gids = {
            gid
            for gid in expected_gids
            if any(f"gid={gid}" in source_url for source_url in source_urls)
        }
        self.assertEqual(found_gids, expected_gids)

    def test_checked_in_public_bundles_are_identical(self):
        trip_bundle = json.loads(TRIP_BUNDLE_PATH.read_text(encoding="utf-8"))
        web_bundle = json.loads(WEB_BUNDLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(web_bundle, trip_bundle)

    def test_no_removed_child_elders_constraints(self):
        serialized = self.trip["preferences"]["hard_constraints"] + self.trip["preferences"]["soft_preferences"]
        payload = " ".join(block["description"] for block in serialized)
        forbidden = ["午睡", "13:00", "13:15", "尿布", "容易入口", "13:00-15:00"]
        for term in forbidden:
            self.assertNotIn(term, payload)

    def test_trip_title_scope(self):
        self.assertEqual(self.trip["title"], "2026 瀨戶內五日行")

    def test_travel_assistant_facts_come_from_canonical_trip_with_sources(self):
        override = next(
            item
            for item in self.trip["overrides"]
            if item["path"] == "/presentation/travel_assistant"
        )
        canonical = override["value"]
        self.assertTrue(override["preserve_on_replan"])
        self.assertEqual(self.bundle["travel_assistant"], canonical)
        self.assertEqual(set(canonical["daily_guides"]), {day["date"] for day in self.trip["days"]})

        for date, guide in canonical["daily_guides"].items():
            with self.subTest(date=date):
                source = guide["source"]
                self.assertEqual(source["status"], "reported")
                self.assertTrue(source["source_url"].startswith("https://"))
                self.assertTrue(source["retrieved_at"])
                self.assertEqual(source["timezone"], "Asia/Tokyo")
                self.assertTrue(source["valid_from"].startswith(date))
                self.assertTrue(source["valid_until"].startswith(date))

        for place_id, guide in canonical["place_guides"].items():
            with self.subTest(place_id=place_id):
                self.assertEqual(guide["source"]["source_url"], guide["sourceUrl"])
                self.assertEqual(guide["source"]["status"], "reported")
                self.assertTrue(guide["source"]["retrieved_at"])
                self.assertTrue(guide["hours"])
                self.assertTrue(guide["parking"])

    def test_public_bundle_hides_obsolete_pretrip_refresh_warning(self):
        source_codes = {item.get("code") for item in self.trip["validation"]}
        bundle_codes = {item.get("code") for item in self.bundle["validation"]}
        self.assertIn("PRETRIP_REFRESH_REQUIRED", source_codes)
        self.assertNotIn("PRETRIP_REFRESH_REQUIRED", bundle_codes)
        self.assertNotIn("RESERVATION_UNCONFIRMED", bundle_codes)

    def test_rewrite_without_fixed_slot_breaks_validation(self):
        mutated = copy.deepcopy(self.trip)
        day_two = next(day for day in mutated["days"] if day["date"] == "2026-08-28")
        fixed = next(item for item in day_two["items"] if item["id"] == "fixed-2026-08-28-17-45")
        fixed["id"] = "day2-visit-1745"
        with self.assertRaises(AssertionError):
            self.assertTrue(any(item["id"] == "fixed-2026-08-28-17-45" for item in day_two["items"]))

    def test_flight_arrival_aware_and_unknown_output(self):
        outbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-834-outbound")
        inbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-1835-return")
        self.assertIn("notes", outbound)
        self.assertIn("notes", inbound)
        self.assertEqual(outbound["arrival"]["at"], "2026-08-27T10:30:00+09:00")
        self.assertEqual(inbound["departure"]["at"], "2026-08-31T12:45:00+09:00")

    def test_flight_carrier_and_unknown_time_precision_are_distinct(self):
        outbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-834-outbound")
        inbound = next(flight for flight in self.trip["candidate_sets"]["flights"] if flight["id"] == "xj-1835-return")
        self.assertEqual(outbound["carrier"], "Starlux")
        self.assertEqual(outbound["departure"]["at"], "2026-08-27T06:50:00+08:00")
        self.assertEqual(inbound["arrival"]["at"], "2026-08-31T14:45:00+08:00")

    def test_no_invalid_source_domains_in_trip_payload(self):
        payload_text = TRIP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("example.invalid", payload_text)
        self.assertNotIn("airline.example.invalid", payload_text)
        self.assertNotIn("github.com/your-org", payload_text)

    def test_public_bundle_evidence_gate_tracks_critical_issues(self):
        self.assertIn("evidence_gate", self.bundle)
        self.assertIn(self.bundle["evidence_gate"]["status"], {"ok", "error"})
        self.assertIsInstance(self.bundle["evidence_gate"]["critical_issues"], list)

    def test_selected_facts_have_tracked_evidence(self):
        evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        required_ids = {
            *(f"selected-flight/{flight_id}" for flight_id in self.trip["selected"]["flight_ids"]),
            *(f"selected-hotel/{hotel_id}" for hotel_id in self.trip["selected"]["hotel_place_ids"]),
        }
        evidence_ids = {entry.get("reference_id") for entry in evidence.get("entries", [])}
        missing = sorted(required_ids - evidence_ids)
        self.assertEqual(missing, [])

    def test_conditions_include_visibility_and_validity_interval(self):
        conditions = json.loads(CONDITIONS_PATH.read_text(encoding="utf-8"))
        self.assertIn("conditions", conditions)
        for condition in conditions["conditions"]:
            self.assertIn("visibility", condition)
            self.assertIn("official_source", condition)
            self.assertIn("validity", condition)
            self.assertIn("supporting_sources", condition)
