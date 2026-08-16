# Research evidence (awaji-2026 trust ledger)

## 使用者確認事實（高優先）

- 2026-08-27～2026-08-31（五天四夜）
- 航班：JX834（8/27 抵達 UKB 10:30；出發時間未提供）、JX1835（8/31 12:45 起飛；返台到達時間未提供）
- 住宿順序與退房日
  - Awaji Riverside Terrace in Shizuki ×2 夜
  - 徳島別荘ホテル2 ×1 夜
  - The Royal Park Canvas Kobe Sannomiya ×1 夜
- 8/28 17:45 固定預約：名稱已確認為 `しあわせのパンケーキ`，地點與 duration 待補

## 已確認來源欄位（可回溯）

- 選定景點與住宿欄位使用 `selected_*` evidence mapping
- 航段、住宿、固定預約、移動每一筆皆有 `reference_id` 對應 `evidence.json`
- `trip.json` 僅保留可追溯欄位為 confirmed，未明確來源欄位一律改為 unresolved / unverified

## 仍需補齊的官方/研究證據

- 航班是否為 StarLux（XiamenAir 需要明確否認）
- 淡路島與鳴門潮汐與天候官方窗口（每筆需有 `validity_interval` 與 `freshness`）
- 住宿與主要景點的停車、兒童友善、取消規則、路線成本、還車備援
- Google Maps 清單逐筆原始 snapshot hash + 取回時間

## evidence ledger 策略

- 每筆 `evidence.json` entry 必含：
  - `reference_id`
  - `source_type` / `provider` / `title` / `source_url`
  - `supports`、`support`-level `confidence`
  - `retrieved_at`
  - `validity.valid_from` / `validity.valid_until` / `freshness`
  - `visibility`（`public` / `private` / `internal`）
  - `conflict`（有衝突時填寫，無衝突為 `null`）
- 未經驗證或未補齊欄位不得輸出為 confirmed；統一以 `unresolved` 或 `estimated` 標記
