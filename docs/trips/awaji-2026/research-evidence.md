# Research evidence（awaji-2026 trust ledger）

## Issue 97 Sheet 匯入

- 使用者確認輸入：Google Sheet「淡路島・德島五天四夜行程表」。
- 2026-08-23 讀取三頁：「行程總覽」「8.29-8.31 詳細執行」「出發前確認清單」。
- Sheet 僅作匯入依據；`trip.json` 是唯一 runtime source，網站 bundle 不直接讀 Sheet。
- Day 3–5 依詳細執行頁的時間門轉入 canonical itinerary。
- Day 1–2 已逐列轉入午餐、忍里、CRAFT CIRCUS、日落散步、夜間採買、RURAL、夢舞台、海之教堂與水御堂；總覽未提供精確時間者，以 `estimated` 規劃窗口呈現，不標成 confirmed。

## 使用者確認事實

- 旅程：2026-08-27～2026-08-31，6 位成人、1 位幼兒。
- 航班：JX834 於 8/27 10:30 抵達 UKB；JX1835 於 8/31 12:45 自 UKB 起飛。
- 8/27、8/28 住宿：Awaji Riverside Terrace in Shizuki 780，兵庫県淡路市志筑780-12。
- 8/29 住宿：1-chōme-3-44-3 Kanazawa，徳島県徳島市金沢1丁目3-44-3。
- 8/30 住宿：ザ ロイヤルパーク キャンバス 神戸三宮，兵庫県神戸市中央区下山手通2丁目3番1号。
- 已訂位：8/27 18:30 Garb Costa Orange。
- 已訂位：8/28 13:00 浮世離れの鯛ドロボー。
- 已訂位：8/28 17:45 幸せのパンケーキ 淡路島テラス。17:45 來自 Sheet；店名、地址兵庫県淡路市尾崎42-1 與 official URL 來自官方店舖頁 `https://magia.tokyo/shop`，來源分層不混用。
- 已訂位：8/30 12:50 うずしおクルーズ（福良港）。

## 估計值與資料狀態

- `candidate_sets.transport_legs` 的 departure／arrival 來自 Sheet 規劃窗口，provenance.status 一律為 `estimated`。
- Day 3–5 的 Sheet 車程範圍採上限作 `transfer_minutes`，時間窗多出的部分另列 `buffer_minutes`；Day 5 飯店至 Toyota 為車程 35 分、緩衝 10 分，不把 45 分全稱為車程。
- public bundle 的 `estimated_duration_minutes` 由 departure／arrival 推導，不在 canonical trip 另存第二份分鐘數。
- 每段 provenance note 包含導航方式、延誤切點與長輩／幼兒注意。
- Google Maps directions 是無 API key 的起點／終點連結；即時路況以使用者開啟導航當下為準。
- Day 1–2 非固定預約的時間尚未由官方或使用者精確確認，不可呈現為 confirmed。

## 出發前必須重查

- T-72h：8/27–8/31 天氣、雷雨、熱中症警戒與鳴門風浪。
- T-48h：12:50 觀潮船運航、阿波舞夜公演、眉山纜車、高速與大橋管制。
- T-48h：Ocean Terrace、S BRICK、うずの丘、Nojima Scuola、淡路 SA 摩天輪臨時營業。
- T-24h：Alphard 實車尺寸、飯店合作停車、Toyota 還車與 T1→T2 動線。
- 出發當日：所有逐段車程與事故壅塞用即時導航重算；未知值不得視為零。

## Checklist 保存方式

- trip-v1 schema 沒有 checklist 欄位，因此原始 30 項清單保存在 canonical override path `/operations/pretrip_checklist`。
- `build_awaji_public_bundle.py` 僅 allowlist 輸出 `id`、`completed`、`timing`、`item`、`action`、`fallback`、`contact`。
