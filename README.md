# AI Travel Planner

AI 旅遊規劃平台：自動研究、最佳化行程、驗證時間與預算，並產生旅遊網站。

## 產品目標

輸入目的地、日期、人數、預算與偏好後，系統應能：

1. 研究機票、住宿、景點、餐廳、交通與旅遊內容。
2. 建立候選清單與來源證據。
3. 以時間、路程、營業時間、預算與旅客限制產生可執行行程。
4. 驗證並修復不合理的 itinerary。
5. 以單一結構化 Trip 資料生成 mobile-first 旅遊網站。

## 本機設定與規劃指令

本專案執行時只使用 Python 標準函式庫。進行正式資料研究前，請設定下列資料來源憑證：

```sh
export GOOGLE_MAPS_API_KEY='...'
export YOUTUBE_API_KEY='...'
export OPENROUTESERVICE_API_KEY='...'
# Optional Japan restaurant discovery source:
export HOTPEPPER_API_KEY='...'
```

OpenRouteService 正式金鑰、帳號註冊、免費方案限制與 Railway secret 設定，請參閱 [`docs/flight-hotel-providers.md`](docs/flight-hotel-providers.md#openrouteservice-key)。

使用自然語言需求執行使用者入口：

```sh
python -m src.cli plan --request '幫我規劃 5 天 4 夜德島＋神戶，2 大 1 個 2 歲小孩，台北出發，自駕，不要太累，預算 8 萬。'
```

若要把已驗證的 Canonical Trip 加入 registry 驅動的 React 行程網站，請提供完整日期與網站 slug 並執行 `plan-site`：

```sh
python3 -m src.cli plan-site \
  --request '2027/10/20 到 2027/10/22，台北出發名古屋，2 大 1 小，賞楓、自駕、不要太累，預算 8 萬日圓' \
  --trip-id nagoya-autumn-2027 \
  --site-slug nagoya-autumn-2027
```

只提供月份的需求會回傳尚缺的完整日期，不會自行虛構日期。詳見 [`request-to-site`](docs/request-to-site.md)。

缺少憑證時會明確回傳 `configuration_missing`，不會靜默改用 fixture 資料取代正式資料來源。若只要在本機執行留存式展示，請加上 `--demo`；此模式會寫入 `trips/<trip-id>/trip.json` 與 `site/<trip-id>/index.html`：

```sh
python -m src.cli plan --demo --trip-id tokushima-kobe --request '德島＋神戶五天四夜，2大1個2歲小孩，自駕，預算8萬'
open site/tokushima-kobe/index.html
```

## MCP 服務

選用的 MCP server 會將既有需求解析器、Canonical Trip 驗證器、安全行程摘要、正式規劃器與靜態網站 renderer 提供為工具。它支援本機 stdio client，且寫入行程或網站檔案前需要明確確認參數；它不會發布或部署內容。安裝與連線方式請參閱 [`MCP 旅遊規劃服務`](docs/mcp-server.md)。

目前的資料來源 adapter 包含 Google Places、YouTube Data API、OpenRouteService，以及選用的 Hot Pepper Gourmet 官方 Web Service。Hot Pepper 結果必須標示
`Powered by ホットペッパーグルメ Webサービス`;
其自由文字營業時間在結構化資料來源確認前仍未驗證。資料來源回應須實際取得後才能視為已查詢；系統不會自動訂位或付款。CI 使用記錄或 mock 資料，不會呼叫這些 API。

餐廳品質、價格、菜色與營運事實分開保存，並保留各自來源。Planner 與 validator 使用同一份具時區資訊的營業時間快照，包含分段／跨日營業、固定公休、最後點餐時間與特定日期例外。詳見 [`餐廳資料判讀`](docs/restaurant-intelligence.md)。

## 部署

每次推送至 `main` 時，GitHub Pages 都會從 canonical fixture 部署。公開網站為 https://jackytsai70113.github.io/ai-travel-planner/。Pages 必須使用 GitHub Actions 作為建置來源；workflow 會設定此選項，並使用 `configure-pages`、`upload-pages-artifact` 與 `deploy-pages`。

## 前端執行環境

`web/` 套件只有一個正式入口：`web/src/main.tsx` 啟動 canonical `TripApp`。建置產物由 `web/index.html` 產生，並與本機預覽、CI 及 Pages 部署使用相同的 React route。執行時依 registry 載入 bundle，並在呈現前驗證公開 bundle；使用者編輯內容儲存在各行程專屬的 local storage，不會修改 Canonical Trip。

執行前端品質檢查：

```sh
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npx --prefix web playwright install chromium
npm --prefix web run test:e2e
```

新增頁面時，請擴充 `web/src/app/route-registry.ts`、新增頁面元件、在 `web/src/app/TripApp.tsx` 接線，並新增 route regression test。元件責任邊界與遷移清單請參閱 [`前端執行架構`](docs/architecture/frontend-runtime.md)。

## Canonical Trip 資料契約

[`Trip V1`](docs/canonical-trip-v1.md) 是 planner、validator、renderer、trip storage、map 與 budget 的唯一 source of truth。候選研究資料位於 `candidate_sets`，而最終行程只透過 ID 參照並保留在 `days`，兩者不可混用。

## 路線與排序

路由與 POI 排序使用 provider-neutral 的 [`Routing and optimizer V1`](docs/routing-optimizer-v1.md)。路程查無資料會明確保留為 `unknown` 並交給 validator，不會被當成零分鐘。

## 自然語言需求解析

[`旅遊意圖契約`](docs/travel-intent-contract.md) 將自由格式需求與資料研究、行程建構分開。解析器只擷取使用者明確提供的事實，並記錄欄位層級的來源依據。

## 航班與住宿搜尋

Planner 不會擷取機票票價；每份 Canonical Trip 會顯示需求中的航線與日期，並附上 Google Flights 搜尋頁連結。住宿搜尋可使用既有且相容的 Amadeus Self-Service 帳號，但這是選用功能，目前尚未設定替代住宿資料來源。詳見 [`航班與住宿資料來源`](docs/flight-hotel-providers.md)。

## 架構原則

1. Trip 資料是真實來源：網站、地圖、預算與列印內容都由同一份 Trip schema 產生。
2. Research、Planning、Optimization、Validation 各自分層，避免 LLM 同時負責所有決策。
3. 優先使用確定性驗證：時間衝突、路程、營業時間、預算等盡量以可重現規則檢查，不交由另一個 LLM 主觀判斷。
4. 研究結果保留證據：候選景點、餐廳、住宿與交通資訊保留來源與查詢時間。
5. 先支援日本情境並保留擴充性：第一階段優先支援日本旅遊資料來源與使用情境，核心 schema 與 planner 不綁定日本。

## 多代理 GitHub 開發

本 repository 包含改編自 `agentic-dev-collaboration`、以 Issue 為範圍的協作控制流程。多個開發代理可透過各自的 GitHub Issue、branch、pull request 與外部 Git worktree 平行工作，交接或發布前會檢查寫入範圍是否衝突。

驗證固定版本的 framework 與專案覆寫：

```sh
python3 scripts/validate_agent_collaboration.py
```

先判斷變更路由，再為每個 Issue 建立獨立 worktree：

```sh
python3 -m scripts.agent.collaboration route src/intent/parser.py tests/test_travel_intent.py

python3 -m scripts.agent.collaboration prepare 28 \
  --slug request-constraints \
  --write-path 'src/intent/**' \
  --write-path 'tests/test_travel_intent.py'
```

Repository 會拒絕重疊的有效寫入範圍。完成實作後，在該 Issue worktree 執行 `check` 與 `handoff`。`publish` 會推送 branch 並建立一般非 Draft PR，不會自動合併。

完整流程、角色路由、平行工作範例與指令請參閱 [`docs/agents/DEVELOPMENT.md`](docs/agents/DEVELOPMENT.md)。

## 目標流程

```text
使用者需求
  -> 協調器
  -> 研究代理／資料來源介接器
  -> 候選資料庫
  -> 行程規劃器
  -> 路線／時程最佳化器
  -> 確定性驗證器
  -> 修復流程
  -> Trip JSON/YAML
  -> 網站 renderer
  -> GitHub Pages／PWA
```

## Repository 目錄規劃

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

## Issue 52：2026 淡路島黃金行程（進行中）

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

## 第一階段目標

> 輸入「五天四夜 XX 日本行 + 人數 + 預算 + 偏好」後，產生結構化 Trip 資料，驗證時間 / 路程 / 預算，並生成可在旅途中使用的 mobile-first 網站。

`ai_kyushu` 將作為第一份參考行程與 golden output，用來定義實際旅途中需要的資訊密度與網站可用性。

## 靜態行程 renderer

不依賴外部套件的 renderer 會將 Canonical Trip V1 JSON 轉成以手機優先的靜態網站。它只呈現 canonical 欄位與選用的上游衍生 read model，不負責驗證、路線安排、最佳化或正確性計算。

```sh
python3 -m src.renderer.build_site fixtures/trips/japan-5-day-trip-v1.json --output site
open site/index.html
```

頁面包含總覽、行程與預算，並呈現上游 `validation` 訊息、來源依據狀態，以及各來源的 `retrieved_at` 值（資料新鮮度）。推送至 `main` 時，GitHub Pages 會透過 `.github/workflows/deploy-pages.yml` 使用同一份 fixture 建置。
