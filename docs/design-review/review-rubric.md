# Design review rubric

此 rubric 用於 Awaji release candidate 的獨立人工 review。Gallery build、visual diff、accessibility automation 與本文件是互補 gate；任何一項不能單獨宣告 design complete。

## 評分方式

每項記錄 pass、finding 或 accepted limitation。Finding 必須綁定 issue 或 fix commit；accepted limitation 必須寫出影響範圍與 owner。以下任一 blocker 未處理，不得宣告通過：誤導性的成功狀態、核心操作在 390px 不可用、狀態只靠顏色、長文字被截斷、offline/error 破壞主要 layout。

## 視覺與資訊階層

1. 5 秒內可辨識 trip、日期、目前狀態與主要行動。
2. primary、secondary、tertiary 資訊有清楚層級，不以大量小灰字堆疊。
3. 頁面有 hero、timeline、tabs、drawer 或其他節奏差異，不是所有 section 都是同一種 card wall。
4. 重要資訊不需展開多層；source、freshness、細節採漸進揭露。

## 目的地感與信任

1. Setouchi/Awaji、generic Japan、fallback 三種 theme 可辨識且不改變 status 語意。
2. 圖片或 motif 支援目的地理解，不壓過行程與操作；無圖片時仍完整。
3. confirmed、estimated、unverified、stale、conflict、unresolved、invalid/error 有文字語意。
4. source 與 last checked 可找到；preview、invalid、不完整資料不使用誤導成功文案。

## 現場使用與長輩可讀性

1. 390px 單手可找到今日行程、下一站、Maps、住宿、預約與緊急資訊。
2. 互動目標至少約 44px；sticky UI 不遮內容，safe area 正確。
3. 200% zoom、keyboard focus、forced colors（若平台支援）仍能辨識與操作。
4. 主字級與 line-height 適合長輩；狀態不只靠顏色；長日文、地址、電話與 URL 不截斷。

## Failure、motion 與品質證據

1. loading、empty、offline cached、offline unavailable、broken image、bundle error 都有保留 layout 的狀態。
2. reduced-motion 移除非必要動畫；print summary 隱藏導覽並保留核心內容。
3. 390、430、768、1440 四種 viewport 與三種 theme 使用 deterministic fixture review。
4. 每個 unexplained visual diff 都有 finding；每次 review 記錄 exact SHA、artifact、範圍、結果、修正與 accepted limitations。
