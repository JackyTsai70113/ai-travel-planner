# Architecture

## 1. Goal

AI Travel Planner 的核心不是「讓 LLM 寫一篇行程」，而是建立一條可驗證、可重現、可擴充的旅遊規劃 pipeline。

```text
User Intent
  -> Orchestrator
  -> Research
  -> Candidate Store
  -> Planner
  -> Optimizer
  -> Validator
  -> Repair
  -> Canonical Trip Model
  -> Renderer
```

## 2. Bounded responsibilities

### Orchestrator
負責理解輸入需求、建立 planning context、決定需要執行哪些 research jobs，並協調後續階段。不得直接決定最終景點順序或偷偷修改 validator 結果。

### Research / Source adapters
只負責蒐集與正規化事實，例如：
- flights
- hotels
- POIs
- restaurants
- opening hours
- parking
- route duration
- weather / closure advisories
- YouTube / blog / official tourism evidence

每筆研究資料需保留 source URL / provider、retrieved_at、confidence 或 evidence metadata。

### Candidate Store
保存尚未進入正式行程的候選項目。Research output 與 final itinerary 必須分開，避免候選資訊被誤當已決策內容。

### Planner
根據 user preferences、hard constraints、candidate set 建立一個或多個 itinerary candidates。

### Optimizer
負責排序與成本函數，例如：
- travel time
- detour cost
- waiting risk
- budget
- fatigue
- location clustering
- preference score

不得自行發明缺少的營業時間或交通資訊。

### Validator
以 deterministic checks 優先驗證：
- 時間重疊
- travel-time feasibility
- opening hours
- flight / train / reservation deadlines
- daily duration
- budget totals
- mandatory constraints
- missing required fields

Validator 必須回傳 machine-readable violations，而非只回自然語言。

### Repair loop
接收 validator violations，要求 planner 修復特定問題。修復後需重新驗證，並限制最大迭代次數。

### Canonical Trip Model
最終唯一 source of truth。Web、map、budget、print/PDF、offline view 等皆從此資料模型生成。

### Renderer
不得內嵌旅遊決策邏輯。只負責將 canonical trip model 呈現成 mobile-first UI。

## 3. Proposed modules

```text
src/
├── agents/       # orchestration / research role wrappers
├── sources/      # provider adapters: Google, YouTube, Tabelog-like sources, routing...
├── schemas/      # canonical data contracts
├── planner/      # candidate itinerary generation
├── optimizer/    # scoring / ordering / routing optimization
├── validator/    # deterministic feasibility checks
└── renderer/     # trip model -> web output
```

`agents` 不應成為所有邏輯的垃圾桶；domain logic 應落在 planner / optimizer / validator / sources。

## 4. Hard vs soft constraints

### Hard constraints
不可違反，例如：
- arrival / departure time
- reservation time
- attraction opening hours
- hotel check-in constraints where relevant
- maximum budget if user marks it strict
- required / forbidden locations
- impossible travel duration

### Soft constraints
可納入 scoring，例如：
- 不要太累
- 小孩友善
- 停車方便
- 少排隊
- 喜歡自然景
- 少搬飯店
- 餐廳品質

Planner 必須先滿足 hard constraints，再最佳化 soft constraints。

## 5. Data integrity rules

1. 不允許 renderer 成為第二份 itinerary source of truth。
2. 不允許 LLM 產生的 travel time 未經 routing source 或明確 fallback 標記就成為 confirmed data。
3. 動態資料需保存查詢時間。
4. research evidence 與 user overrides 不可互相覆寫而失去 provenance。
5. monetary values 必須保留 currency。
6. times 必須保留 timezone 或明確屬於 trip local timezone。

## 6. Initial non-goals

V1 不做：
- 自動刷卡訂房 / 訂票
- 自動完成餐廳訂位
- production-grade scraping farm
- 即時背景重新規劃
- 全球所有國家的資料源支援

先完成可靠的 Japan-first planning -> validation -> website pipeline。
