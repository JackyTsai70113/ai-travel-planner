# AI Travel Planner

AI 旅遊規劃平台：自動研究、最佳化行程、驗證時間與預算，並產生旅遊網站。

## Product goal

輸入目的地、日期、人數、預算與偏好後，系統應能：

1. 研究機票、住宿、景點、餐廳、交通與旅遊內容。
2. 建立候選清單與來源證據。
3. 以時間、路程、營業時間、預算與旅客限制產生可執行行程。
4. 驗證並修復不合理的 itinerary。
5. 以單一結構化 Trip 資料生成 mobile-first 旅遊網站。

## Local setup and planning command

This project uses only the Python standard library at runtime.  For production
research, export these documented provider credentials before running a plan:

```sh
export GOOGLE_MAPS_API_KEY='...'
export YOUTUBE_API_KEY='...'
export AMADEUS_CLIENT_ID='...'
export AMADEUS_CLIENT_SECRET='...'
export OPENROUTESERVICE_API_KEY='...'
# Optional Japan restaurant discovery source:
export HOTPEPPER_API_KEY='...'
```

Run the end-user entrypoint with a natural-language request:

```sh
python -m src.cli plan --request '幫我規劃 5 天 4 夜德島＋神戶，2 大 1 個 2 歲小孩，台北出發，自駕，不要太累，預算 8 萬。'
```

Missing credentials return an explicit `configuration_missing` result.  The
command never silently replaces production providers with fixture data.  For a
local recorded demonstration only, add `--demo`; it writes
`trips/<trip-id>/trip.json` and `site/<trip-id>/index.html`:

```sh
python -m src.cli plan --demo --trip-id tokushima-kobe --request '德島＋神戶五天四夜，2大1個2歲小孩，自駕，預算8萬'
open site/tokushima-kobe/index.html
```

The current provider adapters are Google Places, YouTube Data API, Amadeus
Self-Service, OpenRouteService, and the optional official Hot Pepper Gourmet
Web Service. Hot Pepper output must be displayed with
`Powered by ホットペッパーグルメ Webサービス`;
its free-text hours remain unverified until a structured source confirms them.
Provider responses remain unverified
until retrieved; no automatic booking or payment is performed.  CI uses
recorded/mock data and never calls these APIs.

Restaurant quality, price, dishes, and operational facts remain separate and
retain their original provenance. Planner and validator use the same
timezone-aware opening-hours snapshot, including split/overnight intervals,
regular closures, last order, and date-specific exceptions. See
[`Restaurant intelligence`](docs/restaurant-intelligence.md).

## Deployment

GitHub Pages is deployed from the canonical fixture on every push to `main`.
The public site is https://jackytsai70113.github.io/ai-travel-planner/ .  Pages
must be configured with the GitHub Actions build source; the workflow enables
that setting and uses `configure-pages`, `upload-pages-artifact`, and
`deploy-pages`.

## Frontend runtime

The `web/` package has one production entrypoint: `web/src/main.tsx` starts the
canonical `TripApp`. The build artifact is produced from `web/index.html` and
the same React route used by local preview, CI, and Pages deployment. Runtime
bundle loading is registry-driven and validates the public bundle before
rendering it; user edits use trip-scoped local storage and never mutate the
Canonical Trip.

Run the frontend quality gate with:

```sh
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npx --prefix web playwright install chromium
npm --prefix web run test:e2e
```

To add a page, extend `web/src/app/route-registry.ts`, add a page component,
wire it in `web/src/app/TripApp.tsx`, and add a route regression test. See
[`Frontend runtime architecture`](docs/architecture/frontend-runtime.md) for
the ownership boundaries and migration inventory.

## Canonical Trip data contract

[`Trip V1`](docs/canonical-trip-v1.md) 是 planner、validator、renderer、trip storage、map 與 budget 的唯一 source of truth。候選研究資料位於 `candidate_sets`，而最終行程只透過 ID 參照並保留在 `days`，兩者不可混用。

## Routing / ordering

路由與 POI 排序使用 provider-neutral 的 [`Routing and optimizer V1`](docs/routing-optimizer-v1.md)。路程查無資料會明確保留為 `unknown` 並交給 validator，不會被當成零分鐘。

## Natural-language request parsing

[`Travel intent contract`](docs/travel-intent-contract.md) keeps free-form user
requests separate from research and itinerary construction. The parser extracts
only explicit request facts and records field-level source provenance.

## Flight / hotel search

Flight and hotel candidates use provider-neutral models and retain price
freshness, provenance, occupancy, and explicit timezones. The current
production-capable Amadeus adapter, credential handling, limits, and no-booking
boundary are documented in [`docs/flight-hotel-providers.md`](docs/flight-hotel-providers.md).

## Architecture principles

- **Trip data is the source of truth**：網站、地圖、預算與列印內容都從同一份 Trip schema 產生。
- **Research != Planning != Optimization != Validation**：研究、規劃、最佳化與驗證分層，避免 LLM 同時負責所有決策。
- **Deterministic validation first**：時間衝突、路程、營業時間、預算等盡量使用可重現規則驗證，不讓另一個 LLM 主觀判定。
- **Evidence-backed research**：候選景點、餐廳、住宿與交通資訊應保留來源與查詢時間。
- **Japan-first, extensible later**：第一階段優先支援日本旅遊資料源與使用情境，但核心 schema 與 planner 不綁定日本。

## Multi-agent GitHub development

The repository includes an Issue-scoped collaboration control plane adapted
from `agentic-dev-collaboration`. Multiple development agents can work in
parallel through separate GitHub Issues, branches, pull requests, and external
Git worktrees while write ownership is checked before handoff or publication.

Validate the pinned framework and project overlay:

```sh
python3 scripts/validate_agent_collaboration.py
```

Route a proposed change, then prepare one isolated worktree per Issue:

```sh
python3 -m scripts.agent.collaboration route src/intent/parser.py tests/test_travel_intent.py

python3 -m scripts.agent.collaboration prepare 28 \
  --slug request-constraints \
  --write-path 'src/intent/**' \
  --write-path 'tests/test_travel_intent.py'
```

The repository rejects overlapping active write scopes. After implementation,
run `check` and `handoff` inside that Issue worktree. `publish` pushes the
branch and opens a regular non-Draft PR; it never auto-merges.

The complete lifecycle, role routing, parallel ownership examples, and exact
commands are in [`docs/agents/DEVELOPMENT.md`](docs/agents/DEVELOPMENT.md).

## Target pipeline

```text
User request
  -> Orchestrator
  -> Research agents / source adapters
  -> Candidate store
  -> Planner
  -> Route / schedule optimizer
  -> Deterministic validator
  -> Repair loop
  -> Trip JSON/YAML
  -> Website renderer
  -> GitHub Pages / PWA
```

## Planned repository layout

```text
ai-travel-planner/
├── docs/
├── trips/
├── src/
│   ├── agents/
│   ├── sources/
│   ├── planner/
│   ├── optimizer/
│   ├── validator/
│   ├── schemas/
│   └── renderer/
├── web/
└── tests/
```

## Issue 52: Awaji 2026 Golden Trip (in-progress)

### 核心檔案

- `trips/awaji-naruto-tokushima-kobe-2026/trip.json`
- `trips/awaji-naruto-tokushima-kobe-2026/public-bundle.json`
- `trips/awaji-naruto-tokushima-kobe-2026/evidence.json`
- `trips/awaji-naruto-tokushima-kobe-2026/conditions.json`
- `docs/trips/awaji-2026/`
- `scripts/build_awaji_public_bundle.py`
- `scripts/check-awaji-contamination.py`

### 快速操作

```sh
python3 scripts/build_awaji_public_bundle.py \
  --trip-path trips/awaji-naruto-tokushima-kobe-2026/trip.json \
  --output trips/awaji-naruto-tokushima-kobe-2026/public-bundle.json

python3 scripts/check-awaji-contamination.py
```

Issue 52 直接發布於本 repo 既有 GitHub Pages 的子路徑：
`https://jackytsai70113.github.io/ai-travel-planner/trips/awaji-2026/`

## First milestone

> 輸入「五天四夜 XX 日本行 + 人數 + 預算 + 偏好」後，產生結構化 Trip 資料，驗證時間 / 路程 / 預算，並生成可在旅途中使用的 mobile-first 網站。

`ai_kyushu` 將作為第一個 reference trip / golden output，用來定義實際旅途中需要的資訊密度與網站可用性。

## Static trip renderer

The dependency-free renderer turns Canonical Trip V1 JSON into a mobile-first
static site. It only presents canonical fields and optional upstream derived
read models; it does not validate, route, optimise, or calculate correctness.

```sh
python3 -m src.renderer.build_site fixtures/trips/japan-5-day-trip-v1.json --output site
open site/index.html
```

The page includes Overview, Itinerary, and Budget. It surfaces upstream
`validation` messages, provenance status, and each source's `retrieved_at`
value (source freshness). GitHub Pages runs this same fixture build on pushes
to `main` via `.github/workflows/deploy-pages.yml`.
