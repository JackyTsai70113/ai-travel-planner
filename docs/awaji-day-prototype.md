# 淡路島一日遊 prototype

預覽入口：`/awaji-day-prototype/`（由 Vite dev server 提供；目前是 isolated preview route，不修改 production composition root）。

本 prototype 只載入既有 `web/public/trips/awaji-2026/public-bundle.json`（runtime URL：`/trips/awaji-2026/public-bundle.json`）的 2026-08-28 day data。畫面保留 `しあわせのパンケーキ` 的已確認名稱，但將地點與 duration 明確標示為待補；沒有新增地址、停車或 reservation fact。若 bundle 無法載入，畫面會使用同一日的最小 fallback，並顯示 fallback data status。

設計取 `ai_kyushu` 的 desktop sidebar、top bar、day selector、timeline 與現場 quick actions；刻意改用既有 `setouchi-awaji` 的海藍、青綠、留白與波浪 motif，避免複製熊本內容或做成照片／card wall。Hero、時間軸和 amber unresolved reservation 形成主要資訊層級，mobile 以 390px 為優先並保留 44px action hit area。

尚未實作：完整五日資料、地圖／自駕 hub、預約操作、住宿詳情、潮汐、budget、Japanese、Handbook 與 production routing。#88 完成後，應由 integration owner 將此 prototype 的可重用 visual pattern 收斂進 canonical `TripApp` / `ItineraryPage`，不要建立第三套 data source of truth。

人工 review 建議：`npm run dev -- --host 127.0.0.1` 後開啟 `/awaji-day-prototype/`，檢查 1440×900、390×844、430×932；確認 mobile 無 horizontal overflow，且 5 秒內能看出今日主要活動與 17:45 待確認預約。
