# 文件與資料更新指南（awaji-2026）

1. 更新事實（航班、住宿、固定預約）：先改 `trips/awaji-naruto-tokushima-kobe-2026/trip.json`。
2. 當天更新要保留 source 與更新時間：同步更新 `meta.updated_at`。
3. 地圖清單：補齊 `map_import` 區塊後，將未成功/待補項目維持 reason code。
4. 不要在 React/前端硬編行程時間：所有真實行程從 `trips/.../trip.json` 來。
