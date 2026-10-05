from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp import Client, ClientSession
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from src.orchestrator import StageName, StageReport, StageStatus

from src.mcp_server.server import (
    _public_trip_summary,
    build_trip_site_tool,
    get_trip_tool,
    mcp,
    parse_trip_request_tool,
    plan_trip_tool,
    validate_trip_tool,
    _consume_remote_request,
    _read_limited_asgi_body,
)


class MCPTravelServerTests(unittest.TestCase):
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

    def test_streamable_http_requires_internal_token_and_serves_tools(self) -> None:
        import urllib.error
        import urllib.request
        import http.client

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
                stages=tuple(
                    StageReport(
                        stage_name,
                        stage_status
                        if stage_name is StageName.RESEARCH
                        else StageStatus.SUCCEEDED,
                    )
                    for stage_name in StageName
                ),
                warnings=(),
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
            self.assertEqual(len(output["stages"]), len(StageName))
            self.assertEqual(output["stages"][0]["status"], stage_status.value)

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
