# MCP travel planner service

The repository exposes its existing travel planning boundaries through the official MCP Python SDK. The server supports local stdio transport; it is not a public hosted endpoint.

## Install and run

From the repository root, install the optional MCP dependency and start the server:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-mcp.txt
PYTHONPATH=. python -m src.mcp_server.server
```

The process waits for an MCP client on stdin/stdout. Do not print application output to stdout while using stdio. Set `TRAVEL_PLANNER_TRIPS_DIR` and `TRAVEL_PLANNER_SITE_DIR` before starting if files should live outside the repository defaults (`trips/` and `site/`).

Example local MCP client configuration:

```json
{
  "mcpServers": {
    "ai-travel-planner": {
      "command": "/absolute/path/to/repo/.venv/bin/python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/absolute/path/to/repo",
      "env": {
        "PYTHONPATH": "/absolute/path/to/repo"
      }
    }
  }
}
```

Production planning also needs the provider credentials documented in the README. Pass them through the MCP host's process environment; never place credentials in tool arguments. Missing credentials return their environment variable names without attempting provider calls or substituting fixtures.

## Tools

| Tool | Behavior | Side effects |
| --- | --- | --- |
| `parse_trip_request` | Extracts only facts stated in the request, including missing and ambiguous fields. | None |
| `validate_trip` | Runs Canonical Trip V1 schema validation and deterministic itinerary validation. | None |
| `get_trip` | Returns an allowlisted summary for a safe trip ID; omits raw provider records, booking details, free-form notes, and arbitrary fields. | None |
| `plan_trip` | Runs the existing production orchestrator; returns clarification or configuration status before attempting planning. | Requires `confirm_write=true`; then writes the Canonical Trip and static site locally. Never publishes. |
| `build_trip_site` | Validates and renders an existing Canonical Trip. | Requires `confirm_write=true`; writes a local static site only. Never publishes. |

Tool names, typed input arguments, returned status values, and human-readable descriptions are the MCP contract. `travel-planner://capabilities` describes the planning boundaries and tool effects. The `plan_a_trip` prompt instructs the host to resolve ambiguity and preserve unknown values before using a write tool.

MCP tool annotations and `confirm_write` are client-facing safeguards, not authorization controls. Run the local service only for a trusted MCP host. The server does not expose arbitrary file paths, raw source payloads, private booking data, external publication, or credential values.

## Verify

```sh
PYTHONPATH=. python -m unittest tests.test_mcp_server -v
```

Tests use an in-memory MCP client and a real stdio subprocess client. No provider credentials or external APIs are used by the test suite.
