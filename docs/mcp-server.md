# MCP travel planner service

## Remote ChatGPT deployment

本 repo 持續開發目標與驗收範圍見[AI Travel Planner MCP 長期目標](mcp-roadmap.md)；最新正式環境連線證據、倉敷 production run 實測結果與未解 issues，整理於[ChatGPT MCP 正式環境現況](mcp-production-status.md)。

## 已查證的 Railway production endpoint（2026-10-05）

- Railway backend origin：`https://ai-traveller-production-732b.up.railway.app`
- Health endpoint：`https://ai-traveller-production-732b.up.railway.app/health`（實測 HTTP 200，本文回應 `ok`）
- Streamable HTTP MCP endpoint：`https://ai-traveller-production-732b.up.railway.app/mcp`

唯讀驗證已透過 Railway CLI 注入既有 `BEARER_TOKEN` 呼叫 `tools/list` 與 `parse_trip_request`，均回 HTTP 200。直接不帶授權呼叫 `/mcp` 回 HTTP 401 是預期行為；後端同時要求 bearer token 與 Sites Worker 提供的 `oai-authenticated-user-id`。ChatGPT 應連接私人 Site Worker；Railway backend 是 Worker 的後端目標，不是公開的 Site URL。可重複的 smoke test 指令記錄於 [Railway 部署設定](../.railway/README.md#正式服務網址與驗證)。

The repository contains a Streamable HTTP backend and a Worker artifact for a
private ChatGPT Site. The Worker serves ChatGPT at `/mcp`; it requires the
trusted `oai-authenticated-user-id` header, then forwards only MCP POST requests
to the configured backend using `BEARER_TOKEN`. ChatGPT Sites supplies user
authentication at its edge. Do not expose the Python backend publicly without
setting a random `BEARER_TOKEN` of at least 32 characters.

Deploy the repository's root `Dockerfile` on Railway and set `BEARER_TOKEN` to a
random value of 32 or more characters. Attach a Railway volume to the backend
service at `/data`; both Canonical Trips (`/data/trips`) and generated site
files (`/data/site`) live there across deployments. Run one replica because
Railway volumes are not shared with replicas. Set the production provider
credentials needed by `src.application.production` in Railway's secret
environment settings; without them `plan_trip` returns `configuration_missing`.
Railway must expose its HTTP service on the assigned `PORT` and pass the
`/health` health check. After planning a trip, restart/redeploy the service and
verify that `get_trip` still returns that trip.

若要由 ChatGPT 發布已完成的行程網站，需另外設定 Railway secret
`GITHUB_TOKEN`。此值必須是只授予此 repository `Contents: Read and write`
的 fine-grained personal access token；不要使用寬權限 classic token，也不要
把 token 放進程式碼、MCP arguments 或 GitHub issue。GitHub branch protection
若禁止此 token 更新 `main`，工具會回報發布失敗，不會強制覆寫 branch。
此處的 Railway `GITHUB_TOKEN` 是由維護者建立的 fine-grained PAT，不能填
GitHub Actions 每次執行時自動產生的 `GITHUB_TOKEN`；後者發出的 push event
不會啟動另一個 workflow。請先在 GitHub 為此 repository 建立 fine-grained
PAT，將唯一必要的 repository permission 設為 Contents: Read and write，然後
只把它加入 Railway secret manager。可參閱 [fine-grained token API 權限表](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens)
與 [GITHUB_TOKEN 對 workflow 觸發的限制](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs)。

以下變數有預設值，只有 repository、branch 或 Pages 網址不同時才需要加到
Railway：

| Railway 變數 | 預設值 | 用途 |
| --- | --- | --- |
| `GITHUB_REPOSITORY` | `JackyTsai70113/ai-travel-planner` | 要寫入 Pages 資料的 repository。 |
| `GITHUB_PAGES_BRANCH` | `main` | 現有 Pages workflow 部署的分支。 |
| `GITHUB_PAGES_BASE_URL` | `https://jackytsai70113.github.io/ai-travel-planner` | 工具回傳的 Pages 網址根目錄。 |

只有獨立呼叫 `publish_trip_site` 並傳入 `confirm_public_publish=true` 才會
把行程公開。沒有錯誤級驗證或硬性缺項的 Canonical Trip 可發布為網站預覽；
若仍有未安排餐段或費用估算不完整等已揭露警告，registry readiness 會保留
`incomplete`，bundle 狀態保留 `warning`，不會標成完整行程。現有 slug
若已屬於別的 trip 會拒絕；同一 trip 的內容更新還需
`confirm_overwrite=true`。網站 bundle 與 registry 會由同一 Git commit 原子
更新。成功回應的 `status=publish_accepted` 代表 GitHub 已接受 commit，
`deployment_status=pending` 代表 Pages Actions 部署仍在進行；待 workflow
成功後該網址才會提供新版內容。這個工具不訂房、不付款，也不會自動發布。

公開行程頁的 Google 地點名稱由 Railway 後端即時查詢，不保存至 bundle。發布器會把 Railway 自動提供的 `RAILWAY_PUBLIC_DOMAIN` 寫成公開 API 根網址；`PUBLIC_URL` 是 ChatGPT Site Worker 網址，不可拿來代替這個 API 網址。後端只允許 GitHub Pages 的來源網站、公開 registry 已列出的行程，以及每日行程中實際排入的 Place ID；API key 留在 Railway。回應使用 `Cache-Control: no-store`，頁面只在記憶體中顯示 Google Maps 名稱與 attribution。每個來源每分鐘最多 60 次，且 `/data` 記錄不含個人或地點識別資訊的月總次數，上限為 1,000 次；達上限或記錄檔異常時停止查詢。這些是 Places Details API 請求，可能產生 Google Cloud 費用；免費額度或其他 API 用量會影響實際帳單。

`.railway/railway.ts` sets `builder` to `DOCKERFILE` and `dockerfilePath` to the
root `/Dockerfile`, so this service does not need `RAILWAY_DOCKERFILE_PATH`. If
the Dockerfile is moved, update the IaC definition; the variable is an
alternative way to configure a non-default path.
`PUBLIC_URL` is a custom Railway service variable, not a Railway-provided
variable. Set it to the published ChatGPT Site origin (or use the live URL
returned by Sites), then form the public MCP address as `${PUBLIC_URL%/}/mcp`
when needed. Do not use the Site URL as the Worker's backend address.

The `.railway/railway.ts` project definition imports Railway's TypeScript IaC
SDK and manages the GitHub source, preserved secret variables, `/data` volume,
Dockerfile, health check, restart policy, and replica count. Install the root
JavaScript development dependencies before opening or planning that file:

```sh
npm install
railway config plan
```

`railway config plan` only previews differences. Review its output before
running `railway config apply`. The root `railway.json` was migrated into
`.railway/railway.ts` and removed so the service has one configuration source.
The imported environment variables use `preserve()` so planning does not read
or replace secret values. If the plan proposes deleting variables, changing
the GitHub source, or detaching the `/data` volume, stop and reconcile the IaC
definition before applying it.

The Streamable HTTP transport keeps DNS-rebinding protection enabled. It
automatically allows Railway's injected `RAILWAY_PUBLIC_DOMAIN`, plus local
loopback hosts for development. If using an additional custom hostname, set
`MCP_ALLOWED_HOSTS` to a comma-separated list of exact `Host` values (hostnames
without a scheme or path); do not disable host validation.

For the ChatGPT-facing Site, set `MCP_BACKEND_URL` to the Railway HTTPS origin
(without a path) and set `BEARER_TOKEN` to the same secret in the Sites runtime
environment using `sites_update_environment_variables`. The Worker adds `/mcp`
when forwarding, and accepts a backend URL that already ends in `/mcp` without
duplicating it. Then run
`npm run build:site-mcp` and `npm run validate:site-mcp`; the artifact is
produced at `dist/`. Follow this repeatable publish/connect sequence using
the connected Sites and Plugin Management operations:

1. Create a short-lived source write credential with
   `sites_create_source_repository_write_credential(project_id)`; use its
   returned remote URL, branch, and token only in the credential-safe Sites
   source workflow. Never store the token in this repository.
2. Push the exact source commit to the Site source
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

MCP changes run the Python, framework, and MCP Site Worker checks. Frontend lint,
browser tests, and GitHub Pages deployment run only when website code, trip data,
or static-site build inputs change.

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

Production planning requires `GOOGLE_MAPS_API_KEY` and `OPENROUTESERVICE_API_KEY`. `YOUTUBE_API_KEY` is optional; without it, or when YouTube times out or rejects the request, planning continues and returns a Research warning. YouTube community evidence cannot establish operational facts. MCP trip summaries keep the user's budget ceiling separate from how much of the trip cost is priced. The OpenRouteService account and key setup are described in [`flight-hotel-providers.md`](flight-hotel-providers.md). Flight prices are not fetched; the Canonical Trip and rendered page show the route/date summary beside a general Google Flights search-page link. Lodging is not searched automatically. `plan_trip` does not yet convert a lodging name in free text into a Canonical Trip lodging candidate; unknown lodging routes or costs remain unverified/incomplete. Pass secrets through the MCP host environment; never place credentials in tool arguments. Missing required credentials return their environment variable names without attempting provider calls or substituting fixtures.

## Tools

| Tool | Behavior | Side effects |
| --- | --- | --- |
| `parse_trip_request` | Extracts only facts stated in the request, including missing and ambiguous fields. | None |
| `validate_trip` | Runs Canonical Trip V1 schema validation and deterministic itinerary validation. | None |
| `get_trip` | Returns an allowlisted summary for a safe trip ID, including scheduled items and persisted Google Place IDs; omits raw provider records, booking details, free-form notes, and arbitrary fields. Use `get_place_details` when a current Google-sourced display name or operational detail is needed. | None |
| `get_place_details` | Fetches current Places details for one saved Google Place ID for this request only; returns `Google Maps` and supplied third-party attribution. The response is never written to trip storage or site files. | One live Google Places Details request per call; shares a persistent monthly cap of 1,000 service-routed requests with the public page lookup; none in repo storage. |
| 公開行程地點名稱 API | 公開頁只對當前區段已排入行程且尚無自有名稱的地點呼叫 Railway 唯讀端點；端點再以 Places API 的 `id,displayName,attributions` 欄位遮罩查詢。 | 無 bearer token，但限制精確 GitHub Pages Origin、公開 registry、排定 Place ID、每來源頻率與共用每月 1,000 次上限；`no-store`，名稱僅留在頁面記憶體。每次會使用一次 Places Details API。 |
| `plan_trip` | 以繁體中文一題一答補齊必要資訊；只依使用者已明確回答的內容規劃，不回傳 parser JSON 充當最終回答。 | 必要欄位未補齊時只回傳一個 `next_question` 且不啟動研究；完整後須先取得私有檔案寫入確認，再以 `confirm_write=true` 建立或覆寫 Canonical Trip 和靜態網站。若使用者明確要求規劃後公開網站並回傳網址，須在寫入前的摘要確認中說明公開發布；確認後以 `confirm_public_publish=true` 一併呼叫 `plan_trip`，規劃成功後工具會自動發布並回傳 `publication.url`，避免依賴模型是否另行呼叫發布工具。規劃未成功時不發布；既有公開頁內容不同時仍須另行確認覆寫。 |
| `build_trip_site` | Validates and renders an existing Canonical Trip. | Requires `confirm_write=true`; writes a local static site only. Never publishes. |
| `publish_trip_site` | Publishes a Canonical Trip as a public preview. Warning-only incomplete trips keep `incomplete` readiness and visible warnings. | Requires explicit `confirm_public_publish=true`; hard validation errors and required missing sections still refuse publication. Existing-trip replacement separately requires `confirm_overwrite=true`. |

### Chat planning result flow

`plan_trip` returns the result status, stage outcomes, budget summary and warnings; it does not include the full itinerary. After a successful plan, call `get_trip` with the returned `trip_id` to read scheduled dates and items. The durable trip may contain only a Google Place ID for a Google-sourced place. When the chat response needs its current display name, address or opening details, call `get_place_details` with that raw `google_place_id`; include the returned `Google Maps` and any third-party attribution with the details. If the query is unavailable, say so and keep the place ID/map link; do not recover stale details from saved files or guess. These detail calls are read-only but each makes a live provider request.

When a traveler explicitly asks to plan a trip, publish its website publicly, and return the URL, treat that request as public-publishing consent. Include the public release in the pre-planning summary and wait for confirmation before `plan_trip` writes private trip/site files. After confirmation, call `plan_trip` with both `confirm_write=true` and `confirm_public_publish=true`; on successful planning it publishes and returns the publication result, including the actual `url`, in the same tool response. Then return that URL as a clickable link and explain `deployment_status`: `pending` means deployment of the new commit is still running, and `not_required` means the identical public page already exists and this call started no deployment. These are the deployment status values this tool returns. If publication was not explicitly requested, pass `confirm_public_publish=false` and ask separately before publishing. `confirm_write=true` by itself is never public-publishing consent. If the result is `overwrite_confirmation_required`, ask separately whether to replace the existing public page because its contents differ. Only after an explicit yes, call `publish_trip_site` with `confirm_public_publish=true` and `confirm_overwrite=true`, then return its URL. If publication is refused or fails, explain the returned status and do not invent a URL.

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

- `ok`: `{ "status":"ok", "trip": {"schema_version","id","title","local_timezone","date_range","days","validation"} }`; each place is projected to `id`, `google_place_id`, optional independently sourced `name`, `kind`, each item to `id`, `kind`, `start_at`, `end_at`, `status`, and findings to `code`, `severity`, `path`.
- `not_found`: safe `trip_id` was not found.
- `invalid`: stored trip could not be projected to the allowlisted summary.
- `error`: unreadable file or invalid JSON; message does not contain file contents.
- MCP schema rejection (`isError=true`): missing/wrong argument types or a `trip_id` outside the published pattern. These inputs do not reach the tool function.

Side effects and retries: read-only; safe to retry.

The safe projection may include only a Google Place ID, not a display name. If the traveler requests a readable itinerary or named scheduled places, call `get_place_details` once for each distinct scheduled Google Place ID without an independently sourced name; do not call it for unselected candidates. Each call performs a live provider request and may incur usage charges. Details must remain in the current response and include the returned Google Maps and third-party attribution; never write them to the trip or site.

### `get_place_details`

Input schema: `{ "type":"object", "required":["place_id"], "properties":{"place_id":{"type":"string","minLength":1,"maxLength":256,"pattern":"^(?:places/)?[A-Za-z0-9_-]+$"}} }`. Accepts the exact saved Google Place ID (or its `places/` resource-name form).

Output statuses:

- `available`: current normalized Places details for this call, with `attribution: "Google Maps"` and API-supplied third-party attributions.
- `unavailable`: provider request failed; no stale saved details are used. `retryable` indicates whether a later request may succeed; provider response bodies are not returned or recorded.
- `configuration_missing`: `GOOGLE_MAPS_API_KEY` is absent.
- `invalid_input` or MCP schema rejection: the value is not a supported Place ID.

Output statuses also include `monthly_limit_reached`: the shared monthly service budget of 1,000 Google Places requests has been reached; this result is returned before any provider request is made.

Side effects and retries: consumes one unit from the persistent monthly service budget before making one live Places Details request; response is request-scoped and is not written to logs, trip JSON, rendered HTML, or public bundle. MCP details calls and public page lookups share the same counter. Failed provider calls also consume one unit because the provider may have received the request. Retries make a new provider request and may incur usage charges. The cap covers only requests routed through this Railway service, not other applications or services using the same Google Cloud project/key. The counter stores only UTC month and aggregate count.

### `plan_trip`

Input schema: `{ "type":"object", "required":["request","trip_id"], "properties":{"request":{"type":"string","minLength":1,"maxLength":20000},"trip_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9-]{0,79}$"},"confirm_write":{"type":"boolean","default":false},"confirm_public_publish":{"type":"boolean","default":false}} }`.

Output statuses (checked in this order when the arguments pass the published JSON Schema):

- `invalid_input`: unsafe `trip_id` passed directly to the tool function.
- `needs_clarification`: includes parsed `intent`, `missing_fields`, `ambiguous_fields`, and `constraint_issues`; no provider calls or writes.
- `configuration_missing`: lists missing environment variable names only; no provider call or fixture fallback.
- `confirmation_required`: configuration is present but `confirm_write` is false; no provider call or write. If public publication was also explicitly requested and confirmed, pass both confirmation flags as true in the confirmed call.
- `complete`: returned only when the orchestrator produced trip and site outputs and every reported stage is `succeeded`; includes `trip_id`, stage names/statuses, and warning `code`/`stage`/`path` only. When `confirm_public_publish=true`, also includes `publication`, the result from `publish_trip_site`; `publish_accepted` and `already_published` include the actual `url` and `deployment_status`.
- `incomplete`: returned when the orchestrator cannot produce outputs or any reported stage is not `succeeded`. A produced but degraded trip still includes `trip_id`, stage statuses, and warning `code`/`stage`/`path`; provider exception text and warning message text are deliberately omitted. When `confirm_public_publish=true`, publication is not attempted and `publication` is `{ "status":"not_attempted", "reason":"plan_incomplete" }`.
- Nested `publication` statuses: publication configuration or validation errors are returned inside the otherwise successful planning result. `overwrite_confirmation_required` means the same trip's existing public page has different content; ask the traveler to confirm the public replacement separately, then call `publish_trip_site` with `confirm_public_publish=true` and `confirm_overwrite=true`. A pending deployment means GitHub accepted the commit but Pages may not yet serve the update.
- MCP schema rejection (`isError=true`): missing/wrong argument types, empty or more than 20,000 character request, malformed `trip_id`, or non-boolean `confirm_write` or `confirm_public_publish`. These inputs do not reach the tool function.

Side effects and retries: with `confirm_write=true`, performs live provider research and may create or replace `trips/<trip_id>/trip.json` and `site/<trip_id>/index.html`. With both confirmation flags true and a complete plan, it also attempts the public GitHub Pages publication; publishing an existing changed page still requires separate `confirm_overwrite=true` approval through `publish_trip_site`. Before either local write, the storage projection retains exact Google Place IDs and the user's itinerary/notes while removing Google Places details. MCP adds no automatic retry. A client retry repeats live provider calls and can replace those files; the tool is non-idempotent. The confirmation flags are explicit tool arguments, not an authorization mechanism: the MCP host must obtain the corresponding user confirmation first.

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

### `publish_trip_site`

輸入包含 `trip_id`、可選的 `site_slug`、`confirm_public_publish`（預設
`false`）與 `confirm_overwrite`（預設 `false`）。公開旅程可能揭露目的地、
日期、同行人數與行程內容；只有使用者明確要求公開並確認後，才將
`confirm_public_publish` 設為 `true`。

輸出狀態：

- `confirmation_required`：尚未確認公開；不讀取 trip，也不呼叫 GitHub。
- `configuration_missing`：Railway 缺少 `GITHUB_TOKEN`。
- `not_found`、`invalid`、`not_ready`：trip 不存在、Canonical schema 無效，
  或含有硬性驗證缺項；不會寫入 repository。
- `conflict`：slug 指向另一個 Pages 來源或另一個 trip；不會覆寫。
- `overwrite_confirmation_required`：同一 trip 已有公開網站但內容不同，需在
  使用者同意更新後再傳入 `confirm_overwrite=true`。
- `publish_accepted`：GitHub 已接受單一 commit，回傳網站網址與 commit SHA；
  Pages workflow 尚未完成時 `deployment_status` 為 `pending`。
- `already_published`：同一 trip 的公開 bundle 已完全一致，沒有新 commit。
- `publish_failed`：GitHub API 拒絕或無法連線；錯誤不會包含 token 或 response body。

Side effects：以非 force update 更新 `GITHUB_PAGES_BRANCH`。bundle 與 registry
在同一 tree/commit 中寫入。內容採用 `src.request_site` 的 public allowlist，
不提交 Canonical Trip 原始 JSON、provider payload 或 MCP secrets。相同內容重試
不會再建立 commit；改變已公開內容必須明確設 `confirm_overwrite=true`。
發布前會套用與持久化相同的 `durable_trip` 投影：移除 Google Places 詳細資料與
Google 回傳網址，保留原始 Place ID、使用者自有行程／筆記，以及具獨立來源欄位
證據的資料。只有經投影後仍含不可持久化 Places 詳細資料的內容才會被拒絕；單有
Google Places provenance 或 Place ID 不會阻擋新發布。這不會改寫既有公開 bundle
或 Git 歷史。欄位期限及歷史資料範圍見
[`Google Places 資料生命週期盤點`](google-places-data-lifecycle.md)。

The resource `travel-planner://capabilities` returns the schema version, stage list, Canonical Trip source-of-truth statement, and a concise side-effect summary for each tool. The `plan_a_trip(request)` prompt instructs the host to resolve ambiguity and preserve unknown values before using `plan_trip`.

MCP tool annotations and `confirm_write` are client-facing safeguards, not authorization controls. Run the local service only for a trusted MCP host. The server does not expose arbitrary file paths, raw source payloads, private booking data, external publication, or credential values.

## Verify

```sh
PYTHONPATH=. python -m unittest tests.test_mcp_server -v
```

Tests use an in-memory MCP client and a real stdio subprocess client. No provider credentials or external APIs are used by the test suite.
