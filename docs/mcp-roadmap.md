# AI Travel Planner MCP 長期目標

## 方向

持續開發、測試、審查與合併本 repository，直到 AI Travel Planner MCP 能在一般 ChatGPT Chat 中穩定完成有根據的旅行規劃；之後仍持續依實際使用回饋改善，不把一次部署或單項測試當作終點。

這是本 repo 的長期產品目標。每輪工作從最新 `origin/main`、尚未完成的 GitHub Issues 與正式環境證據出發，完成相關實作、測試、review、一般 merge、部署與可執行的驗收，並把新發現記回 repo 或對應 Issue。

## 「MCP 正常可用」的驗收範圍

1. ChatGPT 一般 Chat 能發現並認證私人 AI Travel Planner MCP，能呼叫適當工具；本機 stdio 和正式 Railway Streamable HTTP 入口各自可驗證。
2. 對話能逐題補齊必要資訊，只使用使用者明確提供的內容，不猜日期、旅客、預算、住宿、路線或營業狀態。使用者能留空住宿，也可自行提供住宿資料；沒有資料就保留空白與未驗證狀態。
3. 正式 `plan_trip` 使用可追溯的 live source evidence 建立 Canonical Trip，將景點與可驗證餐點排入每日行程，正確表示未知路線、營業時間、價格與完整度；不以候選數量或頂層 `complete` 字串取代內容驗收。
4. 持久化、讀取、驗證與本機頁面 renderer 使用同一份有效 Canonical Trip。外部 provider 資料的保存、 attribution、保留期限與公開輸出須符合各來源的現行規則。
5. 公開網站是獨立的明確使用者動作；未經單獨同意不得發布。經同意後，MCP 發布工具須產生預期 GitHub Pages 網址，等待 Pages 部署，再用瀏覽器確認網頁內容。
6. 安全性與服務設定可持續維護：Railway endpoint、Bearer 認證、工具 schema、GitHub 發布憑證、資料 volume、healthcheck 和部署來源均須有最新且不含 secret 值的紀錄。

## 驗收證據分層

1. 單元／整合測試證明指定程式情境；recorded/mock provider 測試不得標成 live provider 或正式 ChatGPT 驗收。
2. CI、服務 health、MCP `tools/list`、CLI 或 MCP Inspector 證明各自的基礎設施範圍，不能取代 ChatGPT 一般 Chat 實際呼叫。
3. 涉及 MCP 部署、連線、工具或認證的變更，依 [`ChatGPT Chat MCP 上線驗收流程`](chatgpt-mcp-live-verification.md) 使用 Computer Use 在一般 ChatGPT Chat 驗收。維護者已明確要求由 agent 使用同一個 Chrome 視窗直接處理，並找到 repo 的測試 Chat；不得改用 Work 或另開視窗。外掛未明確附加、沒有實際工具來源／回應證據時，不得把模型文字回答當作 MCP 通過。
4. 涉及網站的外連、版型或互動時，依 repo `AGENTS.md` 的瀏覽器規格，以實際瀏覽器操作和畫面檢查驗收；靜態檢查或被攔截的 popup 不算目標網站可用證據。

## 最新正式環境與一般 Chat 檢查（2026-10-10）

### 2026-10-10 PR #290 部署後 get_trip 一般 Chat 驗收

- PR #290「fix: show itinerary time ranges and unknown transfers」已一般 merge；main commit 為 `af09ace9ba0137b97aa2f621398ac5a27a168547`。Railway `ai-traveller` production deployment `1b895e44-1d6d-4be2-98f0-fb10168797ee` 狀態 `SUCCESS`，來源 SHA 與 main 相同；部署時間為 `2026-10-10T08:58:41.404Z`。
- 2026-10-10 在同一 Chrome 視窗、一般 ChatGPT Chat「解析旅遊請求」中，確認使用者訊息附有 `AI Travel Planner MCP`，實際唯讀呼叫 `get_trip` 一次。工具回傳 `status=ok`、時區 `Asia/Tokyo (UTC+09:00)`，五天共 25 個排程項目（10 個景點、15 餐）；回答逐日列出每項的當地開始／結束時間及 Place ID。
- ChatGPT 明確解釋 `schedule.origin_unknown` 共 5 項，表示首段抵達／起點交通未驗證；活動時間不含未驗證的抵達交通或每日返回住宿交通，並指出不可視為已確認能由機場趕上首個活動，或可在最後活動結束時抵達住宿。此為 PR #290 的 ChatGPT UI 行為驗收通過。
- 回答也如實呈現住宿未設定、`budget.limit_status=unlimited`、`budget.total_status=incomplete` 與 `budget.incomplete`；明確說明 JPY 0 是已知費用小計，不是總旅費。另揭露 3 項 `schedule.poi_candidate_unselected`。住宿留空符合目前需求，不視為缺陷。
- 本次只呼叫 `get_trip`；未呼叫 `get_place_details` 或其他工具，未寫入、修改或發布行程。此驗收證明 ChatGPT 能讀取並清楚呈現現有行程及其未知狀態，不代表交通、住宿、營業時間或旅費已完整驗證，也不代表此行程已達完整規劃目標。

### 2026-10-10 一題一答規劃入口 Chat 驗收

- 在同一 Chrome 視窗的既有一般 ChatGPT Chat「解析旅遊請求」中，確認訊息附有 `AI Travel Planner MCP`，送出不含日期、人數、預算、出發地與交通方式的「我想安排倉敷五天四夜」需求，要求先解析並一次只問一題。
- ChatGPT 實際呼叫 `parse_trip_request`，回報倉敷及 5 天 4 夜，將未提供的欄位保留為未解析／未提供。第一題只詢問旅行日期，並提供沿用同一對話先前提過日期、更改日期或日期未定三個選項；未列出多題清單。
- 在同一對話確認日期後，ChatGPT 保留已確認日期，接著只詢問旅客人數，並提供「仍是 6 位成人＋1 位 2 歲幼兒」或人數有變動的選項。這驗證兩輪答案累積與單題追問。
- 目前只確認了日期與旅客人數，流程仍清楚表示尚未開始規劃或寫入行程；未呼叫 `plan_trip` 或其他寫入工具，未規劃、寫入、修改或發布行程。尚未驗證補齊所有必要欄位後的確認摘要及後續規劃流程。

### 2026-10-10 多輪規格確認與偏好問答修正

- 在同一 Chrome 視窗、既有一般 ChatGPT 測試對話「解析旅遊請求」繼續驗收：https://chatgpt.com/c/6ac9f9c2-00cc-83e8-9619-f92441a513ab。多輪問答涵蓋日期、旅客、出發地、交通、預算與偏好。對未提供的同行長輩資訊以文字回答未知後，ChatGPT 明確保留為 `unknown`，沒有假設長輩狀況。
- 流程在第 17 題已詢問住宿房間分配，接著第 18 題又問住宿地點便利性，與「住宿功能放棄、留空且不搜尋」的既定需求不符。收到明確提醒後，最終摘要才將住宿地點、名稱、房間數、房型、偏好及已選 Place ID 保留為 `null`／`[]`，並承諾不搜尋、不再填住宿。這些不必要的住宿追問由本次修改禁止。
- 第 21 題在使用者作答前，選項「購物中心、Outlet、長時間逛街」已呈勾選狀態。測試取消該選項、改選保留未知後，ChatGPT 明確說明不會推斷旅客不喜歡購物、溫泉或遊樂設施。預選或高亮項目不可視為使用者已確認的偏好。
- 最終回覆產生可讀摘要，標示「需求彙整完成・等待確認」，保留未決的航班時間、租車台數／車型、長輩行動能力、其他排除活動、每日結束時間及費用；並寫明住宿欄位空白、未開始規劃。未按最終確認，這次延續對話沒有呼叫 `plan_trip`、`get_trip` 或其他讀寫發布工具。
- MCP server instructions 與 `plan_a_trip` prompt 現在要求只追問安全規劃所需資訊、必要欄位補齊後摘要並等待確認、未經使用者表達不得詢問或搜尋住宿，以及未經明確選擇不得採用 UI 預選偏好。此為對話指引修正，不改動既有行程資料，也不啟用住宿搜尋。

### 2026-10-10 parser 修正部署與一般 Chat 驗收

- PR #287「fix: preserve airport origin in trip requests」已一般 merge；main merge commit 為 `84062a346b12c156163001e2d82e658522f34d82`，`python`、`pytest`、`mcp-site` CI 全部成功。本機完整 pytest 為 386 passed、288 subtests passed。
- Railway `ai-traveller` production deployment `5bfd4ae1-8402-4a24-8680-3df8486c1a80` 狀態 `SUCCESS`，source SHA 與 merge commit 相同；正式 `/health` 回 HTTP 200／`ok`。
- 2026-10-10 在同一 Chrome 視窗的 ChatGPT 一般 Chat「解析旅遊請求」中，確認使用者訊息附有 `AI Travel Planner MCP`，實際唯讀呼叫 `parse_trip_request`。工具回 `status=parsed`；`origin=桃園國際機場`，`provenance.origin.text=出發地：桃園國際機場`，完整性驗證 PASS。倉敷、岡山縣、2026-11-01 至 2026-11-05、5 天 4 夜、6 位成人與 1 位 2 歲兒童、不限預算、自駕也正確。沒有呼叫其他工具，未規劃、寫入、修改或發布行程。
- 同一測試 Chat 先前的舊回覆曾把機場名稱截為「桃園」；以上是修正合併並部署後的實際 ChatGPT MCP 工具結果，已確認缺陷修復生效。
- 同一 Chat 的既有唯讀 `get_trip` 驗收仍以後續品質狀態為準：五天共 10 個景點及 15 餐，住宿留空符合目前需求；已知費用小計為 JPY 0、總費用狀態 `incomplete`，另有 10 項驗證警告。這些是行程內容／證據完整度的後續改善項目，不影響本次 parser 修正驗收，也不把未設定住宿視為缺陷。
- 使用 Computer Use 在相同一般 ChatGPT 測試 Chat 執行只讀完整具名流程：`get_trip` 1 次取得行程與 `place_details_needed`，`get_place_details` 25 次查詢所有已排入且缺少獨立名稱來源的地點。25 筆均回 `status=available` 並帶 `Google Maps` attribution，第三方 attribution 皆為空陣列；查詢失敗 0、未遇月額度上限。ChatGPT 在一次回合呼叫限制後續查剩餘 4 筆，沒有重複前 21 筆。僅記錄狀態與數量，不將 Google Places 名稱或詳情持久化到 repo；全程未呼叫寫入／發布工具。

### 2026-10-10 parser 修正前的 ChatGPT Chat 驗收紀錄

- 本機 `main`、`origin/main` 均為 `e76fb5e7e4ffdfcf883291dcdd9b4b8763c3c48b`。PR #285 已一般 merge，`python`、`pytest`、`mcp-site` CI 全部成功；Railway `ai-traveller` production deployment `938d0e9f-5a1b-4f8f-9c02-9938f2ea7e30` 為 `SUCCESS`，source SHA 與 `main` 相同，服務 Online，`/data` volume 掛載仍在。GitHub open Issues 查詢為空。
- 在同一 Chrome 視窗找到既有測試 Chat「解析倉敷行程」。從其一般 composer 的「＋」選單點選外掛後，沒有外掛標籤；該 Chat 後續得到的 parser 文字回覆不列為 MCP 驗收證據。
- 已驗證能明確附加外掛的流程：開啟私人 `AI Travel Planner MCP` 外掛詳情頁，按「在對話中試用」，新的一般 Chat composer 顯示 `AI Travel Planner MCP` 標籤。以貼上方式送出唯讀完整倉敷需求，ChatGPT 回覆標題為「AI Travel Planner MCP 實際解析結果」，並列出工具結果：`status=parsed`、倉敷／岡山縣、2026-11-01 至 2026-11-05、5 天 4 夜、6 位成人、1 位 2 歲兒童、`budget_status=unlimited`、`transport=drive`、`missing_fields=[]`、`ambiguous_fields=[]`、`constraint_issues=[]`。工具將「桃園國際機場」解析為 `origin=桃園`；未呼叫其他工具、未規劃、寫入或發布行程。
- 一般 Chat 測試對話：`https://chatgpt.com/c/6ac9f9c2-00cc-83e8-9619-f92441a513ab`（標題「解析旅遊需求」）。截圖核對到 MCP 實際結果表與 `status: parsed`。不把先前未附加外掛標籤的同類回答列作工具呼叫證據。
- 使用此 ChatGPT 操作流程時，若需以中文送測試 prompt，先保留 composer 內的 MCP 標籤，再將文字貼上；覆寫整個 composer 的操作會移除標籤。每次送出前都重新確認標籤仍在。

### 2026-10-10 `get_trip` 驗收與出發機場缺陷紀錄（修正前）

- 在同一 Chrome 視窗找到一般 ChatGPT 測試 Chat「解析旅遊請求」，對 composer 內明確附加的 `AI Travel Planner MCP` 送出唯讀 `get_trip`。工具回應 `status=ok`；五天每天各回傳 2 個景點與 3 餐，共 10 個景點、15 餐。住宿狀態為未設定；預算上限 `unlimited`，但 `total_status=incomplete`、已知小計 JPY 0。驗證警告為 `schedule.hotel_missing` 1、`schedule.origin_unknown` 5、`schedule.poi_candidate_unselected` 3、`budget.incomplete` 1。未呼叫 `get_place_details`，未產生額外 Places 查詢、未寫入或發布行程。此結果不把住宿留空視為缺陷，也不把 JPY 0 說成總費用。
- 同一 ChatGPT Chat 的 parse 結果把明確出發地「桃園國際機場」縮成「桃園」。根因是 `src/intent/parser.py` 的來源別名只涵蓋城市名稱。修正後保留完整機場名稱與來源 provenance，並以 parser 及 MCP server 測試鎖定此行為。
- 本機驗證：`uv run --isolated --with-requirements requirements-mcp.txt python -m unittest tests.test_travel_intent tests.test_mcp_server -v` 通過 66 項；`uv run --isolated --with-requirements requirements-mcp.txt python -m unittest discover -s tests -v` 通過 270 項；`uv run --isolated --with pytest --with-requirements requirements-mcp.txt python -m pytest -q` 通過 386 項與 288 subtests。完整 ChatGPT Chat parser 驗收須在修正部署後再做；目前正式端仍運行上一個已記錄版本。

### 2026-10-10 驗收更新

- PR #281 已一般 merge 至 `main`，merge commit `401435b6b9a050b2f306a681f19bda8dd57bf07f`；`python`、`pytest`、`mcp-site` CI 全部成功。本機 unittest 267 項、pytest 383 項（含 288 subtests）通過。Railway production deployment `a8c2a36a-02a8-4c0f-8168-6978f222a550` 對應此 merge commit 且為 `SUCCESS`；`/health` 回 HTTP 200／`ok`。
- 修正部署前以正式 connector 執行的唯讀呼叫回傳 `intent.origin=桃園`；這是 defect baseline，不是目前部署狀態。
- 修正部署前的 ChatGPT「解析倉敷行程」測試 Chat 也曾回 `intent.origin="桃園"`；後續修正部署後的 ChatGPT 一般 Chat 驗收已在上方區段確認回傳完整機場名稱。
- 維護者提供的一般 ChatGPT Chat `get_place_details` 實際呼叫結果為 `status=available`、`details.name=Nagayamon Coffee`、`attribution=Google Maps`、`third_party_attributions=[]`；完成該工具的 ChatGPT UI 驗收。此次唯讀呼叫未規劃、寫入或發布行程。
- 此段記錄當時 #179 的驗收結論；機場名稱截斷問題已由 PR #287 修正，修正後的一般 Chat 驗收見上方最新區段。

### 2026-10-09 歷史核對

### 2026-10-09 後續核對

- PR #275 已一般 merge，merge commit `75d01ce3b084fe1abce79faf7138e93769139c88`；CI `python`、`pytest`、`mcp-site` 全部成功。本機 `PYTHONPATH=. uv run --isolated --with-requirements requirements-mcp.txt python -m unittest tests.test_mcp_server -v` 通過 24 項。變更補強 server instructions、工具描述與 `plan_a_trip` prompt：最終回答不得直接貼 raw JSON，應以繁中按日期／當地時間整理景點與餐點，揭露未完成狀態且不捏造住宿或未知事實。
- Railway production deployment `25435d1b-489f-450f-a7e3-9a0dcab04ef6` 使用上述 merge commit，狀態 `SUCCESS`；`/health` HTTP 200／`ok`，正式 MCP initialize 回傳新 server instructions，`tools/list` HTTP 200 並列出七項工具，`parse_trip_request` 與 `get_trip` 描述含新增可讀回覆規則。ChatGPT 外掛設定頁「重新整理工具」按鈕載入後恢復可按，但沒有成功／失敗提示；一般 Chat composer 仍選取 `AI Travel Planner MCP` 且空白，未代維護者送出 prompt，故新規則的 ChatGPT UI 行為尚未驗收。
- PR #272 merge commit `f587daf184f7ceb86e37cf26ad9fec4d948ac6b5` 的 Railway production deployment `f4518767-1659-4ffb-a6cb-91f54aa56d6c` 為 `SUCCESS`，source SHA 相同；服務 Online，`/health` 回 HTTP 200／`ok`。GitHub CI 的 `python`、`pytest`、`mcp-site` 全部成功。
- 部署後的正式 MCP `get_trip` 回應新增 `place_details_needed`，對倉敷已排程行程列出 25 個去重後的 Google Place ID；這次沒有呼叫詳情 API、寫入行程或產生 Google Places 詳情查詢。
- 維護者提供的一般 ChatGPT Chat 紀錄包含真實 MCP 呼叫：`parse_trip_request`、`plan_trip`、`get_trip` 與 `publish_trip_site`；因此一般 Chat 的工具發現、認證與呼叫已有直接使用紀錄。ChatGPT 的解析結果曾將明確寫出的桃園出發地回傳為 null。以完全相同請求在本機 parser 與目前正式 MCP connector 重測，皆得到 `origin=桃園`、目的地倉敷、正確日期、人數、無上限預算、自駕與空的 `missing_fields`。差異仍需調查，不能用 backend 結果替代 ChatGPT 回覆。
- 維護者提供的較早 ChatGPT 對話中 `publish_trip_site` 回 `not_ready`。本次以已連線 MCP connector 對同一 trip ID 呼叫 `confirm_public_publish=true`、`confirm_overwrite=true`，結果是 `already_published`、沒有 commit SHA、沒有部署；未發生新覆寫。隨後讀取公開 bundle，確認五天、10 個景點、每天 3 餐共 15 餐，與最新 `get_trip` 相符。既有頁面目前已反映最新行程，沒有再次發布的需要；先前 `not_ready` 回覆所用行程版本未保存。
- PR #272 部署後再次使用 Computer Use 刷新 ChatGPT 工具：按鈕載入約 12 秒後恢復可按，沒有結果提示，因此不能宣稱快照已刷新。同一 Chrome 視窗的一般「對話」composer 仍已選取 `AI Travel Planner MCP` 且保持空白；維護者尚未輸入或送出此次部署的驗收 prompt。
- Computer Use 在單一 Chrome 視窗實際讀取既有倉敷公開頁首日，看到 `Nagayamon Coffee`、`大原美術館`、`Caty Cafe`、`大橋家住宅`、`Momiji-dō` 和 Google Maps 標示。該次 `already_published` 呼叫沒有建立新的 Pages 部署。
- 當時 #179 追蹤解析結果差異與 `get_place_details` 的一般 ChatGPT Chat 驗收；後者已由維護者於 2026-10-10 提供成功工具呼叫結果，現況以本節「2026-10-10 驗收更新」為準。

- Railway production deployment `aa3ef82c-f4ec-401d-9417-9d6e1aba59aa` 為 `SUCCESS`，source commit `530144f23546776088975f796e3cc2c18d1f8641`（PR #265 merge commit）。後續 main 只有倉敷公開行程投影與驗收文件變更，未改動 Railway 監看的 backend source。`/health` 回 HTTP 200／`ok`；透過 Railway CLI 注入環境變數但不輸出值，正式 `tools/list` 回 HTTP 200 並列出七項工具：`parse_trip_request`、`validate_trip`、`get_trip`、`get_place_details`、`plan_trip`、`build_trip_site`、`publish_trip_site`。
- 2026-10-09 使用 AI Travel Planner MCP 明確覆寫既有倉敷公開行程。`publish_trip_site` 回 `publish_accepted`，commit `4380781d3cf91cd41656176769b2c2403feb03c6`；Pages workflow `37832158960` 成功。使用同一個 Chrome 視窗實際打開公開頁與 D1，看到即時載入的 `大原美術館`、`Caty Cafe`、`大橋家住宅` 等名稱，以及 Google Maps 標示。公開 bundle 有 `place_details_api_base_url` 和 Place ID，未持久化 Google 地點名稱。此次只更新公開投影，未改寫行程內容；行程仍標示住宿與費用未完成。
- 較早的 Computer Use 快照只確認外掛已安裝且可選取；當時點擊「重新整理工具」後按鈕持續 disabled、沒有完成提示，composer 保持空白。此快照早於維護者提供的一般 ChatGPT Chat 實際 MCP 呼叫紀錄；目前結果與尚待釐清差異以上方「2026-10-09 後續核對」為準。
- 2026-10-09 透過已連線的 MCP connector 唯讀呼叫 `parse_trip_request`，輸入「我想安排倉敷五天四夜」；回傳 `status=parsed`、目的地倉敷、5 天 4 夜，並只將旅客數與預算列為缺少資訊。這是正式 MCP backend smoke test，不是 ChatGPT Chat UI 驗收。

## 歷史基線（2026-10-09，合併 PR #265 前）

- Railway MCP runtime source SHA 為 `5b2b003c16201564bcda55edcccbb6d3e5948976`，deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 狀態 `SUCCESS`；正式服務 Online，`/health` 回 HTTP 200、內文 `ok`。正式後端此前 `tools/list` 回 HTTP 200、7 個工具。
- 2026-10-08 以 Railway CLI 再次核對七項工具，並對已排定 Place ID 呼叫一次 `get_place_details`；正式工具回 HTTP 200、`available`、`Google Maps` attribution。此 Codex connector 快照只有六項工具，缺少 `get_place_details`；此差異不代表 ChatGPT Chat 的工具清單。OpenAI 自訂 MCP plugin 文件指出 app 詳細資料頁可 Refresh apps 取得更新的工具描述和 server instructions；ChatGPT Chat 實際刷新與呼叫仍待驗收，詳細程序見[上線驗收流程](chatgpt-mcp-live-verification.md)。
- 2026-10-09 以 Railway CLI 核對正式服務 Online、deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 為 `SUCCESS`、source commit `5b2b003c16201564bcda55edcccbb6d3e5948976`；`/health` 回 HTTP 200，正式 `tools/list` 回 HTTP 200 並列出七項工具。`main` 的 `98ee35a` 後續變更僅為文件，Railway 對這些 commit 回報 `SKIPPED`（no changes to watched files）。
- 2026-10-09 使用 Computer Use 在一般 ChatGPT「對話」模式確認私人 `AI Travel Planner MCP` 出現在已安裝外掛清單、設定頁顯示 OAuth 與 `/mcp` endpoint，並可由一般 Chat 的外掛選單選取。外掛設定頁的「重新整理工具」按鈕被點擊後呈 disabled，畫面沒有成功或失敗通知；不可據此宣稱工具快照已刷新。一般 Chat 的新對話 composer 現留有未送出的 `AI Travel Planner MCP` 外掛標籤，尚未輸入或送出 prompt，亦未看到 MCP tool call 或工具回應。一般 Chat 的實際工具呼叫仍須由維護者本人輸入 [`ChatGPT Chat 驗收流程`](chatgpt-mcp-live-verification.md) 所列唯讀 prompt。
- 2026-10-09 本機命令 `PYTHONPATH=. uv run --isolated --with-requirements requirements-mcp.txt python -m unittest tests.test_mcp_server -v` 通過 21 項，含 stdio 子程序及 Streamable HTTP 驗證。測試與 Railway HTTP 檢查都不取代一般 ChatGPT Chat UI 的真實 MCP 工具呼叫。
- PR #243 至 #258 已以一般 merge 合併。PR #250 修正網站 E2E 將行程卡數寫死為 5 的回歸；PR #252 更新 `get_trip` 與 `get_place_details` 的工具說明；PR #256 修正可排入但未被選中的景點備選項不再造成未驗證警告；PR #258 在住宿留空時將首個景點最早排至 09:30，為早餐後已驗證路線保留 30 分鐘。
- PR #243 修正持久化／發布投影中 Google Places 候選驗證訊息殘留名稱與 context 的問題，並要求 ChatGPT 對已排定且缺少獨立名稱來源的 Place ID 使用即時 `get_place_details`。既有行程原始檔未改寫；讀取與未來投影會套用清理。
- PR #244 讓未排入候選景點的 warning 不阻止發布。PR #245 允許只有可揭露 warning 的行程以 preview 公開；網站 bundle 保留 `warning`，registry readiness 保留 `incomplete`。錯誤級驗證、沒有任何餐點的日期與其他硬性缺項仍拒絕發布。
- PR #258 commit `ce3a5f5` 的完整 pytest 通過：377 passed、288 subtests passed；CI 的 unittest、pytest、mcp-site 三項均成功。Railway deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 使用 merge commit `5b2b003c16201564bcda55edcccbb6d3e5948976` 且狀態 `SUCCESS`，`/health` HTTP 200。No-lodging recorded provider fixture 排入 5 天早餐、午餐、晚餐，路線與營業時間驗證仍有效。
- 使用者提供的 ChatGPT Chat 正式規劃結果顯示倉敷五天每日有 2 至 3 筆餐點，共 11 筆；住宿留空。仍有 4 個未安排餐段、費用估算不完整 warning。Issue #180 原始「每日完全沒有餐點」問題已據此結案；這些 warning 仍須如實呈現。
- Issue #179 仍開啟。2026-10-08 已透過 AI Travel Planner MCP 將使用者明確核准的倉敷行程發布為 `preview`／`incomplete`。覆寫後公開頁的 Pages workflow `37742158112` 成功，頁面、bundle 與 registry 均已驗證。2026-10-09 一般 ChatGPT UI 已證明私人外掛已安裝且可選取；真正的 `parse_trip_request` 工具呼叫和公開行程頁的互動式瀏覽器檢查仍未完成。未代替維護者輸入或送出 prompt。
- Issue #179 仍開啟。維護者明確確認覆寫後，正式 MCP 成功發布重規劃版本：每天早餐、午餐、晚餐均已排入，共 15 餐；仍保留 3 個未排 POI 候選、5 個住宿／起點未知警告、`schedule.hotel_missing` 和 `budget.incomplete`。GitHub Pages workflow `37742158112` 成功，行程頁與 bundle 回 HTTP 200，registry 為 `preview`／`incomplete`。一般 ChatGPT Chat 工具刷新／呼叫及互動瀏覽器視覺驗收待完成；本次 Computer Use 因 macOS 鎖定且唯一 Chrome 分頁為 ai-video 對話，未操作該分頁。
- Issue #199 已依維護者指定範圍結案：新資料生命週期防線已部署；既有 Railway 行程、Pages 頁面與 Git 歷史保持原樣、不刪除或改寫。結案不表示歷史內容已清除、逐欄重新驗證或作出法律合規結論。
- 目前唯一開啟的服務能力 issue 為 #179。2026-10-09 已在一般 ChatGPT「對話」模式確認私人 MCP 已安裝且可選取，並將其標籤留在空白 composer；尚未輸入 prompt 或完成實際 MCP 呼叫。公開行程頁的互動式瀏覽器檢查也待完成。維護者明確要求由本人輸入驗收 prompt。
- 使用者已明確保留 ChatGPT 一般 Chat prompt 由本人輸入。2026-10-09 已在同一個 Chrome 視窗開啟新的 ChatGPT 一般 Chat，確認對話模式，並在 composer 選取 `AI Travel Planner MCP`；未輸入或代送 prompt。公開 URL 與 bundle 已 HTTP 驗證，但互動式頁面檢查及一般 Chat 真實工具呼叫仍未完成。

## 更新規則

每次重要 merge 或正式驗收後，更新本文件基線與 [`ChatGPT MCP 正式環境現況`](mcp-production-status.md)，並更新對應 GitHub Issue。記錄 commit SHA、命令與結果、Railway deployment ID/status、實際 ChatGPT 工具名稱／結果、瀏覽器 URL／觀察；只記錄 secret 變數名稱，不記錄 secret 值。
