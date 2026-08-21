# 出發前刷新清單

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
3. 確認每筆固定預約有 unresolved note（名稱/地點/持續時間）並可回到 evidence

## 出發當日

1. 命令：`python3 scripts/build_awaji_public_bundle.py --trip-path trips/awaji-naruto-tokushima-kobe-2026/trip.json --output /tmp/awaji-bundle.json`
2. 以最新 bundle 的 `refresh_schedule.next_refresh_at` 作為最後重查時間點
3. 重核 `Day 5` 返程流程：加油、還車、候機與長者/幼兒接送順序
