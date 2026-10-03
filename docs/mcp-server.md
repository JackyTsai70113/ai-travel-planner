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

## Tool contract

MCP `tools/list` publishes the following JSON schemas from the server's Python type declarations. Every tool result is a JSON object in `structuredContent` and JSON text in `content`.

### `parse_trip_request`

Input schema:

```json
{"type":"object","required":["request"],"properties":{"request":{"type":"string","minLength":1,"maxLength":20000}}}
```

Output statuses:

- `parsed`: `{ "status":"parsed", "intent": <TravelIntent.as_dict()> }`; the intent includes fields, provenance, missing fields, ambiguities, and constraint issues.
- `invalid_input`: empty/whitespace-only or oversized request; includes a short `message`.
- MCP schema rejection (`isError=true`): wrong argument types or JSON Schema `minLength`/`maxLength` violation.

Side effects and retries: none. Repeating the same request is deterministic.

### `validate_trip`

Input schema: `{ "type":"object", "required":["trip"], "properties":{"trip":{"type":"object","additionalProperties":true}} }`. `trip` must satisfy the Canonical Trip V1 contract.

Output statuses:

- `valid`, `incomplete`, or `invalid`: `{ "status": <outcome>, "findings": [{"code","severity","message","path","context","repairable"}] }`.
- `invalid` with `stage="schema"` and `message` when Canonical Trip V1 shape validation fails.
- MCP schema rejection (`isError=true`) when `trip` is not a JSON object.

Side effects and retries: none. Validation is deterministic for the same trip and uses an empty external routing/conditions context, so absent derived evidence remains incomplete/unknown.

### `get_trip`

Input schema: `{ "type":"object", "required":["trip_id"], "properties":{"trip_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9-]{0,79}$"}} }`.

Output statuses:

- `ok`: `{ "status":"ok", "trip": {"schema_version","id","title","local_timezone","date_range","days","validation"} }`; each place is projected to `id`, `name`, `kind`, each item to `id`, `kind`, `start_at`, `end_at`, `status`, and findings to `code`, `severity`, `path`.
- `not_found`: safe `trip_id` was not found.
- `invalid`: stored trip could not be projected to the allowlisted summary.
- `error`: invalid identifier, unreadable file, or invalid JSON; message does not contain file contents.
- MCP schema rejection (`isError=true`): missing or malformed `trip_id`.

Side effects and retries: read-only; safe to retry.

### `plan_trip`

Input schema: `{ "type":"object", "required":["request","trip_id"], "properties":{"request":{"type":"string","minLength":1,"maxLength":20000},"trip_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9-]{0,79}$"},"confirm_write":{"type":"boolean","default":false}} }`.

Output statuses (checked in this order):

- `invalid_input`: unsafe `trip_id` or oversized request.
- `needs_clarification`: includes parsed `intent`, `missing_fields`, `ambiguous_fields`, and `constraint_issues`; no provider calls or writes.
- `configuration_missing`: lists missing environment variable names only; no provider call or fixture fallback.
- `confirmation_required`: configuration is present but `confirm_write` is false; no provider call or write.
- `complete`: includes `trip_id`, stage names/statuses, and warning `code`/`stage`/`path` only.
- `incomplete`: includes a generic message; provider exception text and warning message text are deliberately omitted.

Side effects and retries: with `confirm_write=true`, performs live provider research and may create or replace `trips/<trip_id>/trip.json` and `site/<trip_id>/index.html`. MCP adds no automatic retry. A client retry repeats live provider calls and can replace those files; the tool is non-idempotent. `confirm_write` is an explicit tool argument, not an authorization mechanism.

### `build_trip_site`

Input schema: `{ "type":"object", "required":["trip_id"], "properties":{"trip_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9-]{0,79}$"},"confirm_write":{"type":"boolean","default":false}} }`.

Output statuses:

- `not_found`: canonical trip file is absent.
- `invalid`: JSON cannot be read or Canonical Trip V1 schema validation fails; includes a message.
- `confirmation_required`: no site output is written.
- `invalid_input`: resolved output path escapes the configured site directory.
- `built`: includes `trip_id` and the local `site_path`.
- MCP schema rejection (`isError=true`): malformed arguments.

Side effects and retries: `confirm_write=true` writes or replaces only the local `index.html`; it never deploys. Repeating with the same trip is idempotent if the trip data has not changed. The MCP layer performs no automatic retry.

The resource `travel-planner://capabilities` returns the schema version, stage list, Canonical Trip source-of-truth statement, and a concise side-effect summary for each tool. The `plan_a_trip(request)` prompt instructs the host to resolve ambiguity and preserve unknown values before using `plan_trip`.

MCP tool annotations and `confirm_write` are client-facing safeguards, not authorization controls. Run the local service only for a trusted MCP host. The server does not expose arbitrary file paths, raw source payloads, private booking data, external publication, or credential values.

## Verify

```sh
PYTHONPATH=. python -m unittest tests.test_mcp_server -v
```

Tests use an in-memory MCP client and a real stdio subprocess client. No provider credentials or external APIs are used by the test suite.
