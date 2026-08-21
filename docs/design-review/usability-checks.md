# Task-based usability checks

每次 release candidate 由非實作者執行。使用 `web/visual-fixtures/gallery-scenarios.json` 的 recorded fixture，記錄 exact SHA、viewport、theme、執行者、日期與瀏覽器。成功不是只看畫面能載入，而是完成任務並能說明狀態。

| 任務 | 通過條件 | 結果欄位 |
| --- | --- | --- |
| 5 秒內找到今天第一個主要行程 | 首屏指出日期、第一站與下一個主要 action | pass/fail、步驟、混淆 |
| 找到下一站 Google Maps | 兩次互動內開啟正確 destination link | pass/fail、步驟、混淆 |
| 找到今晚住宿地址與停車 | 不需搜尋 source detail 即讀到地址與停車資訊 | pass/fail、步驟、混淆 |
| 找到固定預約與時間 | 可辨識 confirmed 預約、時間與地點 | pass/fail、步驟、混淆 |
| 找到雨天 Plan B 與放棄條件 | 可找到 Plan B、觸發條件與 abandon rule | pass/fail、步驟、混淆 |
| 找到七人座位日文並播放／複製 | phrase、播放與複製 action 均可操作 | pass/fail、步驟、混淆 |
| 找到 119 與緊急日文 | 不依賴顏色即可找到電話與 phrase | pass/fail、步驟、混淆 |
| 離線後找到核心資訊 | cached 行程、住宿、聯絡方式仍可讀；不可用來源有明示 | pass/fail、步驟、混淆 |

## 結果判定

1. 每項 pass：記錄步驟數與完成時間。
2. 每項 fail：建立 finding，記錄觸發畫面、使用者預期、實際結果與修正或接受理由。
3. 沒有執行的任務不可標記 pass；不可用「gallery build passed」代替 task review。
