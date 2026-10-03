from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from src.mcp_server.server import (
    _public_trip_summary,
    build_trip_site_tool,
    get_trip_tool,
    mcp,
    parse_trip_request_tool,
    plan_trip_tool,
    validate_trip_tool,
)


class MCPTravelServerTests(unittest.TestCase):
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
                        "plan_trip",
                        "build_trip_site",
                    }.issubset(by_name)
                )
                self.assertTrue(all(tool.description for tool in by_name.values()))
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
        self.assertNotIn("secret", encoded)
        self.assertNotIn("private", encoded)
        self.assertEqual(
            result["validation"],
            [{"code": "warning", "severity": "warning", "path": "/days"}],
        )

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
                "YOUTUBE_API_KEY",
                "AMADEUS_CLIENT_ID",
                "AMADEUS_CLIENT_SECRET",
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
