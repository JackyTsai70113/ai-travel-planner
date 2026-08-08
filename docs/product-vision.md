# Product Vision

## North star

使用者只需要描述旅行需求，例如：

> 規劃五天四夜的日本四國行，2 大 1 位兩歲小孩，台北出發，可以自駕，不要太累，預算 8 萬。

系統應自動完成研究、比較、規劃、驗證與網站輸出，產生可在旅途中直接查閱的行程網站。

## V1 user journey

1. 使用者輸入目的地、日期、人數、預算與偏好。
2. 系統研究交通、住宿、景點、餐廳與路線。
3. 系統保留候選項與來源證據。
4. Planner 產生候選行程。
5. Optimizer 依路程、成本、疲勞與偏好排序。
6. Validator 檢查時間、營業時間、交通與預算。
7. 不可行的行程進入 repair loop。
8. 產生 canonical Trip JSON/YAML。
9. Renderer 產生 mobile-first 網站。

## Required trip website capabilities

- Overview：航班、住宿、重要提醒、每日摘要。
- Itinerary：逐日時段、停留時間、交通時間、備案。
- Map：景點、餐廳、飯店、停車與每日路線。
- Transportation：自駕 / 大眾運輸 / 步行資訊。
- Food：餐廳候選、價格、評價、排隊風險、親子資訊。
- Budget：機票、住宿、交通、餐飲、門票與預備金。
- Handbook：訂位資訊、日文、緊急資訊、packing、注意事項。
- Offline-friendly：旅途中弱網路情境仍能查看核心內容。

## Japan-first research coverage

### Flights
- 航班時刻
- fare / baggage / cabin rules
- airport transfer cost and time

### Hotels
- room price
- child policy
- parking
- check-in/out
- location convenience

### Restaurants
- Tabelog-like quality signal
- Google review signal
- price
- reservation
- waiting risk
- child friendliness
- smoking
- parking
- opening hours

### POIs
- official tourism / official site
- opening hours
- ticket price
- closure / reservation information
- parking
- stroller / accessibility notes

### Community research
- YouTube
- Japanese blogs
- Reddit / forums where useful
- congestion / queue / real-world tips

Community evidence may enrich planning, but official sources take priority for critical operational facts.

## Golden reference

`JackyTsai70113/ai_kyushu` is the first reference trip. Its useful travel-day information should become structured fields or renderer capabilities rather than being copied as one-off code.

## Success criteria for first usable release

Given a realistic Japan trip request, the system can produce a complete multi-day itinerary where:
- no mandatory time conflicts exist;
- route durations are accounted for;
- critical opening / reservation constraints are represented;
- budget totals are computable;
- sources are traceable;
- user overrides survive replanning;
- the output website is usable on a phone during travel.
