from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp import Client, ClientSession
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from src.application.production import ProductionIncompleteError
from src.mcp_server.github_pages import PublishResult
from src.renderer.build_site import build_site
from src.mcp_server.server import (
    _consume_remote_request,
    _place_details_needed,
    _public_trip_summary,
    _github_pages_origin,
    _consume_public_place_monthly_budget,
    _published_scheduled_google_place_ids,
    _read_limited_asgi_body,
    build_trip_site_tool,
    get_trip_tool,
    get_place_details_tool,
    mcp,
    parse_trip_request_tool,
    plan_trip_tool,
    publish_trip_site_tool,
    validate_trip_tool,
)
from src.orchestrator import StageName, StageReport, StageStatus, WarningRecord


class MCPTravelServerTests(unittest.TestCase):
    def test_public_place_usage_budget_persists_only_month_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            usage_path = Path(directory) / "usage.json"
            self.assertTrue(_consume_public_place_monthly_budget(usage_path, month="2026-10", limit=2))
            self.assertTrue(_consume_public_place_monthly_budget(usage_path, month="2026-10", limit=2))
            self.assertFalse(_consume_public_place_monthly_budget(usage_path, month="2026-10", limit=2))
            self.assertEqual({"month": "2026-10", "count": 2}, json.loads(usage_path.read_text()))
            self.assertTrue(_consume_public_place_monthly_budget(usage_path, month="2026-11", limit=2))

    def test_public_place_lookup_is_allowlisted_to_scheduled_published_bundle_places(self) -> None:
        bundle = {
            "trip_id": "demo-trip",
            "days": [{"date": "2026-01-01", "items": [{"place_id": "google-poi"}]}],
            "places": [
                {"id": "google-poi", "google_place_id": "ChIJ-scheduled"},
                {"id": "unused-candidate", "google_place_id": "ChIJ-unselected"},
            ],
        }

        class Response:
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self, limit): return json.dumps(self.value).encode()

        with patch("src.mcp_server.server.urlopen", side_effect=[
            Response([{"slug": "demo-trip", "canonical_url": "trips/demo-trip"}]), Response(bundle),
        ]) as fetch:
            allowed = _published_scheduled_google_place_ids("demo-trip", "https://example.test/site")
        self.assertEqual({"ChIJ-scheduled"}, allowed)
        self.assertEqual(2, fetch.call_count)
        self.assertIn("https://example.test/site/trips/demo-trip/public-bundle.json", fetch.call_args_list[1].args[0].full_url)
        self.assertEqual("https://example.test", _github_pages_origin("https://example.test/site"))
        with patch("src.mcp_server.server.urlopen") as fetch:
            self.assertEqual(set(), _published_scheduled_google_place_ids("../private", "https://example.test/site"))
        fetch.assert_not_called()

    def test_remote_rate_limit_is_per_user_and_resets_by_window(self) -> None:
        windows: dict[str, tuple[int, float]] = {}
        for _ in range(120):
            self.assertTrue(_consume_remote_request("user-a", 10.0, windows))
        self.assertFalse(_consume_remote_request("user-a", 10.0, windows))
        self.assertTrue(_consume_remote_request("user-b", 10.0, windows))
        self.assertTrue(_consume_remote_request("user-a", 70.0, windows))

    def test_streamed_body_without_content_length_is_limited_by_actual_size(self) -> None:
        async def read_large_body():
            messages = [
                {"type": "http.request", "body": b"x" * (4 * 1024 * 1024), "more_body": True},
                {"type": "http.request", "body": b"y", "more_body": False},
            ]

            async def receive():
                return messages.pop(0)

            return await _read_limited_asgi_body(receive, 4 * 1024 * 1024)

        self.assertIsNone(asyncio.run(read_large_body()))

    def test_protocol_lists_tools_resources_and_prompts(self) -> None:
        async def check() -> None:
            async with Client(mcp) as client:
                tools = await client.list_tools()
                resources = await client.list_resources()
                prompts = await client.list_prompts()
                by_name = {tool.name: tool for tool in tools.tools}
                self.assertTrue(
                    {
                        "parse_trip_request",
                        "validate_trip",
                        "get_trip",
                        "get_place_details",
                        "plan_trip",
                        "build_trip_site",
                        "publish_trip_site",
                    }.issubset(by_name)
                )
                self.assertTrue(all(tool.description for tool in by_name.values()))
                self.assertIn("place_details_needed array is the authoritative list", by_name["get_trip"].description)
                self.assertIn("call get_place_details once for each listed ID", by_name["get_trip"].description)
                self.assertIn("Each detail call makes one live Places request", by_name["get_trip"].description)
                self.assertIn("include Google Maps and third-party attribution", by_name["get_place_details"].description)
                self.assertIn("may incur usage charges", by_name["get_place_details"].description)
                self.assertIn("一題一答", by_name["plan_trip"].description)
                self.assertIn("不要把 parser JSON 原樣當成回答", by_name["plan_trip"].description)
                self.assertIn("公開發布必須另行取得確認", by_name["plan_trip"].description)
                self.assertIn("After a successful plan_trip, call get_trip", mcp.instructions)
                self.assertIn("Read get_trip.place_details_needed", mcp.instructions)
                self.assertIn("Google Maps and third-party attribution", mcp.instructions)
                self.assertIn("google_place_id", by_name["get_place_details"].input_schema["properties"]["place_id"]["description"])
                self.assertEqual(
                    by_name["parse_trip_request"].input_schema["properties"]["request"][
                        "maxLength"
                    ],
                    20_000,
                )
                self.assertEqual(
                    by_name["validate_trip"].input_schema["properties"]["trip"]["type"],
                    "object",
                )
                self.assertEqual(
                    by_name["get_trip"].input_schema["properties"]["trip_id"][
                        "pattern"
                    ],
                    r"^[a-z0-9][a-z0-9-]{0,79}$",
                )
                self.assertEqual(
                    by_name["plan_trip"].input_schema["properties"]["confirm_write"][
                        "default"
                    ],
                    False,
                )
                self.assertIs(
                    by_name["publish_trip_site"].input_schema["properties"]["confirm_public_publish"]["default"],
                    False,
                )
                self.assertIs(
                    by_name["publish_trip_site"].input_schema["properties"]["confirm_overwrite"]["default"],
                    False,
                )
                self.assertIn(
                    "travel-planner://capabilities",
                    {str(resource.uri) for resource in resources.resources},
                )
                self.assertIn(
                    "plan_a_trip", {prompt.name for prompt in prompts.prompts}
                )
                prompt = await client.get_prompt(
                    "plan_a_trip", {"request": "plan details"}
                )
                self.assertIn(
                    "Use parse_trip_request before plan_trip", str(prompt.messages)
                )
                self.assertIn("After a successful plan_trip, call get_trip", str(prompt.messages))
                self.assertIn("get_place_details", str(prompt.messages))
                self.assertIn(
                    "then call plan_trip with confirm_write=true",
                    str(prompt.messages),
                )

        asyncio.run(check())

    def test_stdio_subprocess_handshake_and_tool_call(self) -> None:
        async def check() -> None:
            project = Path(__file__).parent.parent.resolve()
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "src.mcp_server.server"],
                cwd=str(project),
                env={**os.environ, "PYTHONPATH": str(project)},
            )
            async with Client(parameters) as client:
                self.assertEqual(client.server_info.name, "ai-travel-planner")
                result = await client.call_tool(
                    "parse_trip_request", {"request": "台北出發去大阪"}
                )
                self.assertEqual(result.structured_content["status"], "parsed")

        asyncio.run(check())

    def test_streamable_http_requires_internal_token_and_serves_tools(self) -> None:
        import http.client
        import urllib.error
        import urllib.request

        project = Path(__file__).parent.parent.resolve()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        token = "t" * 40
        server_env = {
            **os.environ,
            "PYTHONPATH": str(project),
            "MCP_TRANSPORT": "streamable-http",
            "BEARER_TOKEN": token,
            "PORT": str(port),
            "RAILWAY_PUBLIC_DOMAIN": "travel.example.test",
        }
        for name in (
            "GOOGLE_MAPS_API_KEY",
            "OPENROUTESERVICE_API_KEY",
        ):
            server_env.pop(name, None)
        process = subprocess.Popen(
            [sys.executable, "-m", "src.mcp_server.server"],
            cwd=project,
            env=server_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        endpoint = f"http://127.0.0.1:{port}/mcp"
        try:
            for _ in range(100):
                if process.poll() is not None:
                    self.fail("HTTP MCP server exited during startup")
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2).read()
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.05)
            with self.assertRaises(urllib.error.HTTPError) as unauthenticated:
                urllib.request.urlopen(urllib.request.Request(endpoint, data=b"{}", method="POST", headers={"Authorization": f"Bearer {token}"}), timeout=2)
            self.assertEqual(unauthenticated.exception.code, 401)
            unauthenticated.exception.close()
            public_lookup = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/public/trips/demo-trip/places/ChIJ-place",
                headers={"Origin": "https://untrusted.example"},
            )
            with self.assertRaises(urllib.error.HTTPError) as blocked_public_lookup:
                urllib.request.urlopen(public_lookup, timeout=2)
            self.assertEqual(blocked_public_lookup.exception.code, 403)
            self.assertEqual("no-store, max-age=0", blocked_public_lookup.exception.headers.get("Cache-Control"))
            blocked_public_lookup.exception.close()
            wrong_host = urllib.request.Request(
                endpoint,
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    }
                ).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "oai-authenticated-user-id": "test-user",
                    "Host": "untrusted.example.test",
                    "Content-Type": "application/json",
                },
            )
            with self.assertRaises(urllib.error.HTTPError) as rejected_host:
                urllib.request.urlopen(wrong_host, timeout=2)
            self.assertEqual(rejected_host.exception.code, 421)
            rejected_host.exception.close()
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.putrequest("POST", "/mcp")
            connection.putheader("Authorization", f"Bearer {token}")
            connection.putheader("oai-authenticated-user-id", "test-user")
            connection.putheader("Content-Length", str(4 * 1024 * 1024 + 1))
            connection.endheaders()
            too_large = connection.getresponse()
            self.assertEqual(too_large.status, 413)
            too_large.read()
            connection.close()

            chunked = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
            chunked.putrequest("POST", "/mcp")
            chunked.putheader("Authorization", f"Bearer {token}")
            chunked.putheader("oai-authenticated-user-id", "test-user")
            chunked.putheader("Transfer-Encoding", "chunked")
            chunked.endheaders()
            chunked.send(b"400000\r\n" + b"x" * (4 * 1024 * 1024) + b"\r\n")
            chunked.send(b"1\r\ny\r\n0\r\n\r\n")
            chunked_too_large = chunked.getresponse()
            self.assertEqual(chunked_too_large.status, 413)
            chunked_too_large.read()
            chunked.close()

            async def exercise_remote_protocol():
                import httpx2

                headers = {
                    "Authorization": f"Bearer {token}",
                    "oai-authenticated-user-id": "test-user",
                    "Host": "travel.example.test",
                }
                async with httpx2.AsyncClient(headers=headers) as http_client:
                    async with streamable_http_client(endpoint, http_client=http_client) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()
                            tools = await client.list_tools()
                            resources = await client.list_resources()
                            prompts = await client.list_prompts()
                            parsed = await client.call_tool(
                                "parse_trip_request",
                                {"request": "從台北出發去大阪，停留三天。"},
                            )
                            missing_configuration = await client.call_tool(
                                "plan_trip",
                                {
                                    "request": "從台北出發，2026/04/01 到 2026/04/05 去東京，2大1小（6歲），預算8萬台幣，搭電車，想去東京迪士尼，不要太累。",
                                    "trip_id": "mcp-http-missing-config",
                                    "confirm_write": True,
                                },
                            )
                            return (
                                tools,
                                resources,
                                prompts,
                                parsed,
                                missing_configuration,
                            )

            tools, resources, prompts, parsed, missing_configuration = asyncio.run(
                exercise_remote_protocol()
            )
            self.assertIn("parse_trip_request", {tool.name for tool in tools.tools})
            self.assertIn(
                "travel-planner://capabilities",
                {str(resource.uri) for resource in resources.resources},
            )
            self.assertIn("plan_a_trip", {prompt.name for prompt in prompts.prompts})
            self.assertEqual(parsed.structured_content["status"], "parsed")
            self.assertEqual(
                missing_configuration.structured_content["status"],
                "configuration_missing",
            )
            self.assertEqual(
                missing_configuration.structured_content["missing"],
                [
                    "GOOGLE_MAPS_API_KEY",
                    "OPENROUTESERVICE_API_KEY",
                ],
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def test_request_parser_is_reachable_over_mcp_and_keeps_unknowns(self) -> None:
        async def check() -> None:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "parse_trip_request",
                    {
                        "request": "台灣出發，2026/04/01 到 2026/04/05 去東京，2大1小（6歲），預算8萬台幣，搭電車，想去東京迪士尼，不要太累。"
                    },
                )
                payload = result.structured_content
                self.assertIsNotNone(payload)
                self.assertEqual(payload["status"], "parsed")
                self.assertEqual(payload["intent"]["start_date"], "2026-04-01")
                kurashiki = await client.call_tool(
                    "parse_trip_request",
                    {"request": "日本岡山縣倉敷五天四夜。日期：2026/11/01～2026/11/05。旅客：6位成人、1位2歲幼兒。預算：暫不設限制。"},
                )
                parsed_kurashiki = kurashiki.structured_content["intent"]
                self.assertEqual(parsed_kurashiki["destinations"], ["倉敷"])
                self.assertEqual(parsed_kurashiki["regions"], ["岡山縣"])
                self.assertEqual(parsed_kurashiki["start_date"], "2026-11-01")
                self.assertEqual(parsed_kurashiki["end_date"], "2026-11-05")
                self.assertEqual(parsed_kurashiki["travelers"], {"adults": 6, "children": 1, "child_ages": [2]})
                self.assertEqual(parsed_kurashiki["budget_status"], "unlimited")
                self.assertEqual(parsed_kurashiki["missing_fields"], [])
                empty_request = await client.call_tool(
                    "parse_trip_request", {"request": ""}
                )
                self.assertTrue(empty_request.is_error)
                oversized_request = await client.call_tool(
                    "parse_trip_request", {"request": "x" * 20_001}
                )
                self.assertTrue(oversized_request.is_error)
                whitespace_request = await client.call_tool(
                    "parse_trip_request", {"request": "   \n"}
                )
                self.assertEqual(
                    whitespace_request.structured_content["status"], "invalid_input"
                )
                malformed_trip_id = await client.call_tool(
                    "get_trip", {"trip_id": "../escape"}
                )
                self.assertTrue(malformed_trip_id.is_error)
                malformed_plan = await client.call_tool(
                    "plan_trip",
                    {"request": "trip", "trip_id": "../escape"},
                )
                self.assertTrue(malformed_plan.is_error)
                invalid_trip = await client.call_tool(
                    "validate_trip", {"trip": {"schema_version": "wrong"}}
                )
                self.assertEqual(invalid_trip.structured_content["status"], "invalid")

        asyncio.run(check())

    def test_trip_summary_uses_allowlist_and_omits_private_candidate_data(self) -> None:
        trip = {
            "schema_version": "trip-v1",
            "id": "sample",
            "title": "Sample",
            "local_timezone": "Asia/Tokyo",
            "flight_search_url": "https://www.google.com/travel/flights?hl=zh-TW",
            "budget": {
                "currency": "JPY",
                "categories": {"hotel": {"amount": 0, "currency": "JPY"}},
                "total": {"amount": 0, "currency": "JPY"},
                "total_status": "incomplete",
                "limit_status": "unlimited",
            },
            "date_range": {
                "start_date": "2026-01-01",
                "end_date": "2026-01-01",
                "private_booking": "secret",
            },
            "candidate_sets": {
                "places": [
                    {
                        "id": "p1",
                        "name": "Park",
                        "kind": "poi",
                        "phone": "private",
                        "raw": {"secret": "hidden"},
                    }
                ]
            },
            "days": [
                {
                    "date": "2026-01-01",
                    "items": [
                        {
                            "id": "i1",
                            "kind": "visit",
                            "place_id": "p1",
                            "start_at": "10:00",
                            "booking_reference": "secret",
                        }
                    ],
                }
            ],
            "validation": [
                {
                    "code": "warning",
                    "severity": "warning",
                    "path": "/days",
                    "message": "secret",
                }
            ],
            "private": "must not escape",
        }
        result = _public_trip_summary(trip)
        encoded = json.dumps(result)
        self.assertIn("Park", encoded)
        self.assertIn("google.com/travel/flights", encoded)
        self.assertEqual(result["budget"]["limit_status"], "unlimited")
        self.assertEqual(result["budget"]["total_status"], "incomplete")
        self.assertEqual(result["budget"]["summary"], "未設定預算上限；已知費用小計 JPY 0（部分費用尚未取得）")
        self.assertNotIn("secret", encoded)
        self.assertNotIn("private", encoded)
        self.assertEqual(
            result["validation"],
            [{"code": "warning", "severity": "warning", "path": "/days"}],
        )

    def test_get_place_details_is_transient_and_handles_provider_failure(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-key"}), patch(
            "src.mcp_server.server.GooglePlacesAdapter.get_place_details",
            return_value={"status": "available", "attribution": "Google Maps", "details": {"name": "Transient"}},
        ) as lookup:
            result = get_place_details_tool("ChIJ-place")
        self.assertEqual("available", result["status"])
        lookup.assert_called_once_with("ChIJ-place")
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-key"}), patch(
            "src.mcp_server.server.GooglePlacesAdapter.get_place_details",
            side_effect=RuntimeError("provider error"),
        ):
            result = get_place_details_tool("ChIJ-place")
        self.assertEqual({"status": "unavailable", "reason": "provider_request_failed", "retryable": True}, result)
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": ""}):
            missing = get_place_details_tool("ChIJ-place")
        self.assertEqual({"status": "configuration_missing", "missing": ["GOOGLE_MAPS_API_KEY"]}, missing)

    def test_place_details_followups_include_only_distinct_scheduled_places_without_names(self) -> None:
        summary = {
            "days": [
                {
                    "items": [
                        {"place": {"google_place_id": "ChIJ-scheduled"}},
                        {"place": {"google_place_id": "ChIJ-scheduled"}},
                        {"place": {"google_place_id": "ChIJ-named", "name": "Known name"}},
                        {"place": {"google_place_id": "ChIJ-blank-name", "name": "   "}},
                        {"place": {"google_place_id": "bad id"}},
                    ]
                }
            ]
        }
        self.assertEqual(
            ["ChIJ-scheduled", "ChIJ-blank-name"],
            _place_details_needed(summary),
        )

    def test_legacy_trip_reads_and_site_builds_sanitize_without_rewriting_history(self) -> None:
        fixture = json.loads((Path(__file__).parent.parent / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
        place = fixture["candidate_sets"]["places"][0]
        place.update({
            "google_place_id": "ChIJ-place",
            "provenance": {
                "source_type": "provider", "provider": "Google Places API (New)",
                "source_url": "https://maps.google.test/place", "retrieved_at": "2026-10-08T00:00:00+00:00", "status": "confirmed",
            },
        })
        fixture["days"][0]["items"][0]["place_id"] = place["id"]
        with tempfile.TemporaryDirectory() as temp:
            trips, sites = Path(temp) / "trips", Path(temp) / "sites"
            source = trips / fixture["id"] / "trip.json"
            source.parent.mkdir(parents=True)
            original = json.dumps(fixture, ensure_ascii=False, indent=2)
            source.write_text(original, encoding="utf-8")
            with patch("src.mcp_server.server._TRIPS_DIR", trips.resolve()), patch(
                "src.mcp_server.server._SITE_DIR", sites.resolve()
            ):
                summary = get_trip_tool(fixture["id"])
                built = build_trip_site_tool(fixture["id"], confirm_write=True)
            html = (sites / fixture["id"] / "index.html").read_text(encoding="utf-8")
            self.assertEqual("ok", summary["status"])
            self.assertEqual(["ChIJ-place"], summary["place_details_needed"])
            self.assertNotIn("name", summary["trip"]["days"][0]["items"][0]["place"])
            self.assertEqual("ChIJ-place", summary["trip"]["days"][0]["items"][0]["place"]["google_place_id"])
            self.assertEqual("built", built["status"])
            self.assertNotIn(place["name"], html)
            self.assertIn("query_place_id", html)
            self.assertEqual(original, source.read_text(encoding="utf-8"))

    def test_public_publisher_keeps_id_and_html_omits_google_details(self) -> None:
        from src.google_places_storage import durable_trip
        nested = durable_trip({
            "candidate_sets": {
                "places": [{
                    "id": "google:place",
                    "kind": "poi",
                    "provenance": {"provider": "Google Places API (New)"},
                    "place": {
                        "id": "google:place",
                        "google_place_id": "ChIJ-nested",
                        "kind": "poi",
                        "name": "Transient nested name",
                        "address": "Transient nested address",
                    },
                }]
            }
        })
        nested_place = nested["candidate_sets"]["places"][0]["place"]
        self.assertEqual("ChIJ-nested", nested_place["google_place_id"])
        self.assertNotIn("name", nested_place)
        self.assertNotIn("address", nested_place)

        fixture = json.loads((Path(__file__).parent.parent / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
        for index, day in enumerate(fixture["days"], start=1):
            day["items"].append({
                "id": f"meal-{index}", "kind": "meal", "place_id": "ramen-shop",
                "start_at": f"{day['date']}T12:00:00+09:00", "end_at": f"{day['date']}T13:00:00+09:00",
                "selection_status": "selected",
            })
        place = fixture["candidate_sets"]["places"][0]
        place["google_place_id"] = "ChIJ-place"
        place["provenance"] = {
            "source_type": "provider", "provider": "Google Places API (New)",
            "source_url": "https://maps.google.test/place", "retrieved_at": "2026-10-08T00:00:00+00:00", "status": "confirmed",
        }
        fixture["days"][0]["items"][0]["place_id"] = place["id"]
        stored = durable_trip(fixture)
        stored_place = stored["candidate_sets"]["places"][0]
        self.assertEqual("ChIJ-place", stored_place["google_place_id"])
        self.assertNotIn("name", stored_place)
        self.assertNotIn("address", stored_place)
        self.assertNotIn("source_url", stored_place["provenance"])
        from src.request_site import trip_to_public_bundle
        bundle = trip_to_public_bundle(stored)
        self.assertTrue(any(p.get("google_place_id") == "ChIJ-place" for p in bundle["places"]))

        html = build_site(fixture)
        self.assertIn("query_place_id", html)

    def test_google_projection_preserves_user_trip_and_notes(self) -> None:
        from src.google_places_storage import durable_trip

        source = json.loads((Path(__file__).parent.parent / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
        source["title"] = "使用者自訂的九州旅行"
        source["days"][0]["summary"] = "第一天：保留我的安排"
        source["days"][0]["items"][0]["notes"] = "使用者備註：抵達後先休息"
        source["traveler_profile"]["children"][0]["notes"] = "幼兒午睡時段不可排活動"
        source["overrides"][0]["notes"] = "使用者核准的住宿選擇"
        place = source["candidate_sets"]["places"][0]
        place["id"] = "google-candidate-id"
        place.update({
            "google_place_id": "ChIJ-keep-exactly",
            "name": "Google 暫時名稱",
            "address": "Google 暫時地址",
            "coordinates": {"latitude": 33.1, "longitude": 130.1},
            "provenance": {"source_type": "provider", "provider": "Google Places API (New)"},
            "field_provenance": {
                "accessibility_notes": [{
                    "source_type": "user_input", "provider": "traveler",
                    "retrieved_at": "2026-10-08T00:00:00+09:00", "status": "confirmed",
                }],
            },
            "accessibility_notes": "使用者補充：入口有階梯，需帶斜坡板",
        })
        original_place = json.loads(json.dumps(place, ensure_ascii=False))
        source["validation"] = [{
            "code": "schedule.poi_candidate_unselected",
            "severity": "warning",
            "message": "候選景點「Google 暫時名稱」未排入：未能驗證所需的營業時間或路線。",
            "path": "/candidate_sets/places/google-candidate-id/schedule",
            "context": {"name": "Google 暫時名稱", "address": "Google 暫時地址"},
        }]

        stored = durable_trip(source)
        stored_place = stored["candidate_sets"]["places"][0]
        self.assertEqual("ChIJ-keep-exactly", stored_place["google_place_id"])
        self.assertNotIn("name", stored_place)
        self.assertNotIn("address", stored_place)
        self.assertNotIn("coordinates", stored_place)
        self.assertEqual("使用者補充：入口有階梯，需帶斜坡板", stored_place["accessibility_notes"])
        self.assertEqual("使用者自訂的九州旅行", stored["title"])
        self.assertEqual("第一天：保留我的安排", stored["days"][0]["summary"])
        self.assertEqual("使用者備註：抵達後先休息", stored["days"][0]["items"][0]["notes"])
        self.assertEqual("幼兒午睡時段不可排活動", stored["traveler_profile"]["children"][0]["notes"])
        self.assertEqual("使用者核准的住宿選擇", stored["overrides"][0]["notes"])
        stored_text = json.dumps(stored, ensure_ascii=False)
        self.assertNotIn("Google 暫時名稱", stored_text)
        self.assertNotIn("Google 暫時地址", stored_text)
        self.assertEqual("schedule.poi_candidate_unselected", stored["validation"][0]["code"])
        self.assertEqual("/candidate_sets/places/google-candidate-id/schedule", stored["validation"][0]["path"])
        self.assertNotIn("context", stored["validation"][0])
        self.assertIn("Google Places 候選未排入", stored["validation"][0]["message"])
        public_ready = json.loads(json.dumps(stored, ensure_ascii=False))
        public_ready["candidate_sets"]["places"] = [{
            "id": "google-candidate-id", "google_place_id": "ChIJ-keep-exactly", "kind": "poi",
            "provenance": {"provider": "Google Places API (New)"},
        }]
        public_ready["candidate_sets"]["restaurants"] = []
        public_ready["candidate_sets"]["hotels"] = []
        from src.request_site import trip_to_public_bundle
        public_text = json.dumps(trip_to_public_bundle(public_ready), ensure_ascii=False)
        self.assertNotIn("Google 暫時名稱", public_text)
        self.assertNotIn("Google 暫時地址", public_text)
        self.assertIn("google-candidate-id", stored["validation"][0]["path"])
        self.assertEqual(original_place, source["candidate_sets"]["places"][0])

    def test_place_details_returns_google_and_provider_attribution_without_storing(self) -> None:
        detail_response = {
            "status": "available",
            "attribution": "Google Maps",
            "third_party_attributions": [{"provider": "Example Data Provider", "text": "Map data"}],
            "details": {"name": "Current place name"},
        }
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-key"}), patch(
            "src.mcp_server.server.GooglePlacesAdapter.get_place_details",
            return_value=detail_response,
        ) as lookup:
            result = get_place_details_tool("ChIJ-place")
        self.assertEqual("available", result["status"])
        self.assertEqual("Google Maps", result["attribution"])
        self.assertEqual(detail_response["third_party_attributions"], result["third_party_attributions"])
        lookup.assert_called_once_with("ChIJ-place")

    def test_tool_errors_are_structured_and_writes_need_confirmation(self) -> None:
        parsed = parse_trip_request_tool("")
        self.assertEqual(parsed["status"], "invalid_input")
        invalid = validate_trip_tool({"schema_version": "wrong"})
        self.assertEqual(invalid["status"], "invalid")
        with tempfile.TemporaryDirectory() as temp:
            trips = Path(temp) / "trips"
            sites = Path(temp) / "sites"
            trip_path = trips / "demo-trip" / "trip.json"
            trip_path.parent.mkdir(parents=True)
            fixture = (
                Path(__file__).parent.parent / "fixtures/trips/japan-5-day-trip-v1.json"
            )
            trip_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
            with (
                patch("src.mcp_server.server._TRIPS_DIR", trips.resolve()),
                patch("src.mcp_server.server._SITE_DIR", sites.resolve()),
            ):
                self.assertEqual(get_trip_tool("../escape")["status"], "error")
                self.assertEqual(
                    build_trip_site_tool("demo-trip")["status"], "confirmation_required"
                )
                self.assertFalse(sites.exists())
                built = build_trip_site_tool("demo-trip", confirm_write=True)
                self.assertEqual(built["status"], "built")
                self.assertTrue((sites / "demo-trip" / "index.html").is_file())

    def test_public_trip_publish_requires_separate_consent_and_github_credential(self) -> None:
        consent = publish_trip_site_tool("demo-trip")
        self.assertEqual(consent["status"], "confirmation_required")
        self.assertIn("publicly accessible", consent["message"])

        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            missing = publish_trip_site_tool("demo-trip", confirm_public_publish=True)
        self.assertEqual(missing, {"status": "configuration_missing", "missing": ["GITHUB_TOKEN"]})

    def test_public_trip_publish_returns_pages_url_after_explicit_confirmation(self) -> None:
        fixture = json.loads((Path(__file__).parent.parent / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
        trip_id = fixture["id"]
        result_value = PublishResult(
            "publish_accepted", "JackyTsai70113/ai-travel-planner", "family-trip",
            "https://jackytsai70113.github.io/ai-travel-planner/trips/family-trip/", "commit-sha",
        )
        with tempfile.TemporaryDirectory() as temp:
            trips = Path(temp) / "trips"
            trip_path = trips / trip_id / "trip.json"
            trip_path.parent.mkdir(parents=True)
            trip_path.write_text(json.dumps(fixture), encoding="utf-8")
            with (
                patch("src.mcp_server.server._TRIPS_DIR", trips.resolve()),
                patch.dict(os.environ, {"GITHUB_TOKEN": "private-test-token"}),
                patch("src.mcp_server.server.GitHubPagesPublisher.publish", return_value=result_value) as publish,
            ):
                published = publish_trip_site_tool(
                    trip_id, "family-trip", confirm_public_publish=True
                )
        self.assertEqual(published["status"], "publish_accepted")
        self.assertEqual(published["url"], result_value.url)
        publish.assert_called_once()

    def test_public_trip_publish_sanitizes_google_places_details_before_github_io(self) -> None:
        fixture = json.loads((Path(__file__).parent.parent / "fixtures/trips/japan-5-day-trip-v1.json").read_text(encoding="utf-8"))
        for index, day in enumerate(fixture["days"], start=1):
            day["items"].append({
                "id": f"meal-{index}", "kind": "meal", "place_id": "ramen-shop",
                "start_at": f"{day['date']}T12:00:00+09:00", "end_at": f"{day['date']}T13:00:00+09:00",
                "selection_status": "selected",
            })
        fixture["candidate_sets"]["places"][0]["provenance"] = {
            "source_type": "provider", "provider": "Google Places API (New)",
            "retrieved_at": "2026-10-08T00:00:00+00:00", "status": "confirmed",
        }
        fixture["candidate_sets"]["places"][0]["name"] = "Google Ephemeral Name"
        fixture["candidate_sets"]["places"][0]["google_place_id"] = "ChIJ-place"
        trip_id = fixture["id"]
        with tempfile.TemporaryDirectory() as temp:
            trips = Path(temp) / "trips"
            trip_path = trips / trip_id / "trip.json"
            trip_path.parent.mkdir(parents=True)
            trip_path.write_text(json.dumps(fixture), encoding="utf-8")
            with (
                patch("src.mcp_server.server._TRIPS_DIR", trips.resolve()),
                patch.dict(os.environ, {"GITHUB_TOKEN": "private-test-token"}),
                patch("src.mcp_server.server.GitHubPagesPublisher.publish", return_value=PublishResult(
                    "publish_accepted", "JackyTsai70113/ai-travel-planner", "family-trip",
                    "https://example.test/trips/family-trip/", "commit-sha",
                )) as publish,
            ):
                result = publish_trip_site_tool(
                    trip_id, "family-trip", confirm_public_publish=True
                )
        self.assertEqual("publish_accepted", result["status"])
        self.assertTrue(publish.called)
        published_trip = publish.call_args.args[0]
        published_text = json.dumps(published_trip, ensure_ascii=False)
        self.assertNotIn("Google Ephemeral Name", published_text)
        self.assertEqual("ChIJ-place", published_trip["candidate_sets"]["places"][0]["google_place_id"])

    def test_plan_status_is_incomplete_when_any_stage_is_incomplete(self) -> None:
        request = "2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算8萬日圓，自駕"

        for stage_status, expected_status in (
            (StageStatus.INCOMPLETE, "incomplete"),
            (StageStatus.PENDING, "incomplete"),
            (StageStatus.FAILED, "incomplete"),
            (StageStatus.SUCCEEDED, "complete"),
        ):
            result = SimpleNamespace(
                succeeded=True,
                trip={"budget": {"currency": "JPY", "categories": {}, "total": {"amount": 0, "currency": "JPY"}, "total_status": "incomplete", "limit_status": "unlimited"}},
                stages=tuple(
                    StageReport(
                        stage_name,
                        stage_status
                        if stage_name is StageName.RESEARCH
                        else StageStatus.SUCCEEDED,
                    )
                    for stage_name in StageName
                ),
                warnings=(WarningRecord("schedule.route_unknown", "每日首段路線尚未驗證。", StageName.PLANNER, "/days/0"),),
            )

            class Runner:
                def run(self, _intent):
                    return result

            with (
                patch(
                    "src.mcp_server.server.missing_required_configuration",
                    return_value=[],
                ),
                patch(
                    "src.mcp_server.server.create_production_orchestrator",
                    return_value=Runner(),
                ),
            ):
                output = plan_trip_tool(request, "mcp-plan-status", confirm_write=True)

            self.assertEqual(output["status"], expected_status)
            self.assertEqual(output["budget_summary"], "未設定預算上限；已知費用小計 JPY 0（部分費用尚未取得）")
            self.assertEqual(len(output["stages"]), len(StageName))
            self.assertEqual(output["stages"][0]["status"], stage_status.value)
            self.assertEqual(output["warnings"][0]["message"], "每日首段路線尚未驗證。")

    def test_plan_returns_specific_production_incomplete_reason(self) -> None:
        request = "2026/4/10到2026/4/14 台北出發德島五天四夜，2大，預算不限，自駕"
        reason = "route-aware scheduling requires verified opening hours"
        with (
            patch("src.mcp_server.server.missing_required_configuration", return_value=[]),
            patch("src.mcp_server.server.create_production_orchestrator", side_effect=ProductionIncompleteError(reason)),
        ):
            output = plan_trip_tool(request, "mcp-incomplete-reason", confirm_write=True)
        self.assertEqual(output["status"], "incomplete")
        self.assertEqual(output["message"], reason)

    def test_plan_clarification_returns_one_question_without_starting_research(self) -> None:
        with (
            patch("src.mcp_server.server.missing_required_configuration") as configuration,
            patch("src.mcp_server.server.create_production_orchestrator") as create_runner,
        ):
            output = plan_trip_tool(
                "我想安排倉敷五天四夜",
                "qa-preflight",
                confirm_write=True,
            )

        self.assertEqual(output["status"], "needs_clarification")
        self.assertGreater(len(output["missing_fields"]), 1)
        self.assertEqual(
            output["next_question"],
            "請提供確切的出發與返程日期（YYYY/MM/DD）。",
        )
        configuration.assert_not_called()
        create_runner.assert_not_called()

    def test_plan_reports_missing_provider_configuration_without_fixture_fallback(
        self,
    ) -> None:
        request = "從台北出發，2026/04/01 到 2026/04/05 去東京，2大1小（6歲），預算8萬台幣，搭電車，想去東京迪士尼，不要太累。"
        with patch.dict("os.environ", {}, clear=True):
            result = plan_trip_tool(request, "mcp-test-trip", confirm_write=True)
        self.assertEqual(result["status"], "configuration_missing")
        self.assertEqual(
            result["missing"],
            [
                "GOOGLE_MAPS_API_KEY",
                "OPENROUTESERVICE_API_KEY",
            ],
        )

        async def check_protocol() -> None:
            with patch.dict("os.environ", {}, clear=True):
                async with Client(mcp) as client:
                    protocol_result = await client.call_tool(
                        "plan_trip",
                        {
                            "request": request,
                            "trip_id": "mcp-test-trip",
                            "confirm_write": True,
                        },
                    )
            self.assertEqual(
                protocol_result.structured_content["status"],
                "configuration_missing",
            )
            self.assertEqual(
                protocol_result.structured_content["missing"],
                result["missing"],
            )

        asyncio.run(check_protocol())

    def test_plan_requires_write_confirmation_before_constructing_live_providers(
        self,
    ) -> None:
        request = "從台北出發，2026/04/01 到 2026/04/05 去東京，2大1小（6歲），預算8萬台幣，搭電車，想去東京迪士尼，不要太累。"
        with (
            patch(
                "src.mcp_server.server.missing_required_configuration", return_value=[]
            ),
            patch(
                "src.mcp_server.server.create_production_orchestrator"
            ) as create_runner,
        ):
            result = plan_trip_tool(request, "mcp-test-trip", confirm_write=False)
        self.assertEqual(result["status"], "confirmation_required")
        create_runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
