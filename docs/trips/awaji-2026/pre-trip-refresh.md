# 出發前刷新清單

本文件配合 canonical override `/operations/pretrip_checklist`。網站勾選狀態只保存在瀏覽器本機；來源清單仍由 `trip.json` 產生。

## T-7

1. 命令：`python3 scripts/build_awaji_public_bundle.py --trip-path trips/awaji-naruto-tokushima-kobe-2026/trip.json --output /tmp/awaji-bundle.json`
2. 更新 `trips/awaji-naruto-tokushima-kobe-2026/evidence.json`
   - 檢查航班起落、住宿退房/退房時間、交通成本
   - 更新 `validity` / `freshness` / `retrieved_at`

## T-3

1. 命令：`python3 scripts/build_awaji_public_bundle.py --trip-path trips/awaji-naruto-tokushima-kobe-2026/trip.json --output /tmp/awaji-bundle.json`
2. 命令：`python3 -m json.tool trips/awaji-naruto-tokushima-kobe-2026/evidence.json`
3. 逐條補齊潮汐、降雨、閉園/開園窗口並寫入 `trips/awaji-naruto-tokushima-kobe-2026/conditions.json`

## T-1

1. 命令：`python3 scripts/build_awaji_public_bundle.py --trip-path trips/awaji-naruto-tokushima-kobe-2026/trip.json --output web/public/trips/awaji-2026/public-bundle.json`
2. 再核：`/conditions` 欄位 `visibility=public` 與 `validity_interval` 是否可被重新查核
3. 確認四筆固定預約仍為 resolved：Garb 18:30、鯛ドロボー 13:00、幸せのパンケーキ 17:45、うずしおクルーズ 12:50
4. 逐段車程仍標為 `estimated`，不得把 Google Maps 即時結果回寫成無時間戳的 confirmed 值

## 出發當日

1. 命令：`python3 scripts/build_awaji_public_bundle.py --trip-path trips/awaji-naruto-tokushima-kobe-2026/trip.json --output /tmp/awaji-bundle.json`
2. 以最新 bundle 的 `refresh_schedule.next_refresh_at` 作為最後重查時間點
3. 重核 `Day 5` 返程流程：加油、還車、候機與長者/幼兒接送順序
