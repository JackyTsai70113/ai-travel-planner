# AI Travel Planner

AI 旅遊規劃平台：自動研究、最佳化行程、驗證時間與預算，並產生旅遊網站。

## Product goal

輸入目的地、日期、人數、預算與偏好後，系統應能：

1. 研究機票、住宿、景點、餐廳、交通與旅遊內容。
2. 建立候選清單與來源證據。
3. 以時間、路程、營業時間、預算與旅客限制產生可執行行程。
4. 驗證並修復不合理的 itinerary。
5. 以單一結構化 Trip 資料生成 mobile-first 旅遊網站。

## Canonical Trip data contract

[`Trip V1`](docs/canonical-trip-v1.md) 是 planner、validator、renderer、trip storage、map 與 budget 的唯一 source of truth。候選研究資料位於 `candidate_sets`，而最終行程只透過 ID 參照並保留在 `days`，兩者不可混用。

## Architecture principles

- **Trip data is the source of truth**：網站、地圖、預算與列印內容都從同一份 Trip schema 產生。
- **Research != Planning != Optimization != Validation**：研究、規劃、最佳化與驗證分層，避免 LLM 同時負責所有決策。
- **Deterministic validation first**：時間衝突、路程、營業時間、預算等盡量使用可重現規則驗證，不讓另一個 LLM 主觀判定。
- **Evidence-backed research**：候選景點、餐廳、住宿與交通資訊應保留來源與查詢時間。
- **Japan-first, extensible later**：第一階段優先支援日本旅遊資料源與使用情境，但核心 schema 與 planner 不綁定日本。

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
