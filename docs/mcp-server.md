# MCP travel planner service

## Remote ChatGPT deployment

The repository contains a Streamable HTTP backend and a Worker artifact for a
private ChatGPT Site. The Worker serves ChatGPT at
`/mcp`; it requires the trusted `oai-authenticated-user-id` header, then forwards
only MCP POST requests to the configured backend using `MCP_BACKEND_TOKEN`.
ChatGPT Sites supplies user authentication at its edge. Do not expose the Python
backend publicly without setting a random `MCP_BACKEND_TOKEN` of at least 32
characters.

Deploy the repository's `Dockerfile` on Railway and set `MCP_BACKEND_TOKEN` to a
random value of 32 or more characters. Set the production provider credentials
needed by `src.application.production` in Railway's secret environment settings;
without them `plan_trip` returns `configuration_missing`. Railway must expose its
HTTP service on the assigned `PORT` and pass the `/health` health check.

For the ChatGPT-facing Site, set `MCP_BACKEND_URL` to the Railway HTTPS origin
(without a path) and set `MCP_BACKEND_TOKEN` to the same secret in the Sites
runtime environment. Run `npm run build:site-mcp` and
runtime environment (`sites_update_environment_variables`). Then follow this
repeatable publish/connect sequence using the connected Sites and Plugin
Management operations:

1. Create a short-lived source write credential with
   `sites_create_source_repository_write_credential(project_id)`; use its
   returned remote URL, branch, and token only in the credential-safe Sites
   source workflow. Never store the token in this repository.
2. Run `npm run build:site-mcp` and `npm run validate:site-mcp`; the artifact
   is produced at `dist/`. Push the exact source commit to the Site source
   branch and pass that full commit SHA and the artifact path to
   `sites_save_version_and_deploy_private`.
3. Wait until the returned deployment status is `succeeded`. Check
   `has_mcp=true` and `url` on the deployment result.
4. Call `sites_get_site(project_id, include_mcp_connection=true)`. Pass its
   returned `mcp_connection.plugin_id` unchanged to
   `plugin_management_suggest_plugins`. The account user completes the
   connection in ChatGPT, then verifies a read-only call to `parse_trip_request`
   or `get_trip` from a chat that has selected this app.

The artifact declares `site-worker/index.js` as the Worker entrypoint at
`/mcp`. Keep the Site private and let ChatGPT Sites provide authentication; the
worker does not implement a second OAuth flow. After any source change, rebuild,
validate, push, save, and deploy a new version before reconnect verification.

The default `MCP_TRANSPORT=stdio` remains for local clients. Set
`MCP_TRANSPORT=streamable-http` for the Railway container.

The Python MCP server exposes the existing travel planning boundaries through
the official MCP Python SDK. Locally it defaults to stdio; Railway runs it as
Streamable HTTP. Source/configuration files alone do not mean the backend or
ChatGPT Site is deployed: the production URL and plugin become usable only
after both hosting operations above succeed.

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
- `invalid_input`: whitespace-only request passed directly to the tool function; includes a short `message`.
- MCP schema rejection (`isError=true`): missing/wrong argument types, empty string (`minLength`), or more than 20,000 characters (`maxLength`). These inputs do not reach the tool function.

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
- `error`: unreadable file or invalid JSON; message does not contain file contents.
- MCP schema rejection (`isError=true`): missing/wrong argument types or a `trip_id` outside the published pattern. These inputs do not reach the tool function.

Side effects and retries: read-only; safe to retry.

### `plan_trip`

Input schema: `{ "type":"object", "required":["request","trip_id"], "properties":{"request":{"type":"string","minLength":1,"maxLength":20000},"trip_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9-]{0,79}$"},"confirm_write":{"type":"boolean","default":false}} }`.

Output statuses (checked in this order when the arguments pass the published JSON Schema):

- `invalid_input`: unsafe `trip_id` passed directly to the tool function.
- `needs_clarification`: includes parsed `intent`, `missing_fields`, `ambiguous_fields`, and `constraint_issues`; no provider calls or writes.
- `configuration_missing`: lists missing environment variable names only; no provider call or fixture fallback.
- `confirmation_required`: configuration is present but `confirm_write` is false; no provider call or write.
- `complete`: includes `trip_id`, stage names/statuses, and warning `code`/`stage`/`path` only.
- `incomplete`: includes a generic message; provider exception text and warning message text are deliberately omitted.
- MCP schema rejection (`isError=true`): missing/wrong argument types, empty or more than 20,000 character request, malformed `trip_id`, or non-boolean `confirm_write`. These inputs do not reach the tool function.

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
