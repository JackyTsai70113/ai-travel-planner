# ChatGPT MCP 正式環境現況與已知問題

最後查證：2026-10-09。本文記錄本 repo MCP 部署與實際工具呼叫的觀察結果，不代表規劃品質已達可交付標準。

## 最新正式狀態與查證紀錄（2026-10-09）

### 最新查證補充（2026-10-09）

- 重新查詢 Railway 後，production 目前 Online，部署 `aa3ef82c-f4ec-401d-9417-9d6e1aba59aa` 為 `SUCCESS`，實際 source commit 是 `530144f23546776088975f796e3cc2c18d1f8641`；`origin/main` 的 `e8b29a1` 及其後續文件提交均為 Railway `SKIPPED`，因為沒有變更 watched files。故本文件下方標示 `5b2b003` 的區段是歷史快照，不是目前 runtime。
- 維護者提供的一般 ChatGPT Chat 對話紀錄證明 ChatGPT 實際呼叫 `parse_trip_request`、`plan_trip`、`get_trip`、`publish_trip_site`。該對話中的解析回覆將明確提供的桃園出發地顯示為 `null`。同一份完整需求在本機 parser 與目前連線的正式 MCP connector 重測均得到 `origin=桃園`、倉敷、2026-11-01 至 2026-11-05、6 位成人與 1 位 2 歲幼兒、無上限預算、自駕，且 `missing_fields=[]`。正式連線測試是 backend evidence，不能取代或抹除 ChatGPT 對話中不同的回覆；來源差異尚待查明。
- 使用者提供的 ChatGPT 對話中，`publish_trip_site` 曾回 `not_ready`，包含候選景點、餐段與費用完整度訊息。後來以已確認的 `confirm_public_publish=true`、`confirm_overwrite=true` 對同一 `trip_id` 呼叫正式 MCP，結果為 `already_published`、`commit_sha=null`、`deployment_status=not_required`，沒有新的覆寫或部署。其後比對目前公開 bundle 與最新 `get_trip`，兩者同為 5 天、10 個景點、15 筆餐點；目前 `already_published` 與既有頁面內容相符。先前 `not_ready` 回覆當時採用的資料版本未記錄，故不把它當成目前仍需重新發布的阻塞。
- 用 Computer Use 在既有單一 Chrome 視窗開啟公開頁 `https://jackytsai70113.github.io/ai-travel-planner/trips/kurashiki-2026-11-live-20261008/#/today/2026-11-01`，確認頁面可讀，並看到 `Nagayamon Coffee`、`大原美術館`、`Caty Cafe`、`大橋家住宅`、`Momiji-dō` 與 Google Maps 地點標示。這證明現有公開頁目前可用，不代表剛才的呼叫建立了新版本。
- #179 已修正狀態敘述：一般 Chat 工具呼叫及公開頁可用性已有證據；尚待釐清 ChatGPT 與正式 connector 的解析回覆差異，並確認 ChatGPT 能呼叫 `get_place_details` 以列出即時地點名稱。既有公開頁已與最新 Trip 同步，無須再次發布。依據使用者指示，不要求重做已提供的相同流程。

- PR #243–#258 功能變更與 PR #259–#261 正式狀態文件均以一般 merge 合併。PR #250 修正入口行程卡片數量的固定測試，PR #252 更新 Places 即時查詢工具指引，PR #256 修正可行備選 POI 被誤報未驗證，PR #258 為無住宿日保留早餐後的路線緩衝。
- 較早一次（PR #265 更新前）的 Railway production runtime source 為 `5b2b003c16201564bcda55edcccbb6d3e5948976`，deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 狀態 `SUCCESS`，服務 Online，`/health` 回 HTTP 200、內文 `ok`；部署使用 Dockerfile `/Dockerfile`，`/data` volume 仍掛載。此為歷史基線，現在的 runtime 請以上方最新查證補充為準。
- 2026-10-08 再次用 Railway CLI 注入既有 `BEARER_TOKEN` 呼叫正式 `tools/list`：HTTP 200，列出 7 個工具，包括 `get_place_details`。以倉敷已排定 Place ID 執行一次正式唯讀 `get_place_details`：HTTP 200、`status=available`、`attribution=Google Maps`、Place ID 相符；輸出只記錄回傳欄位名稱，沒有記錄地點詳細值或憑證。
- 較早一次（2026-10-09）以 Railway CLI 查證時，`ai-traveller` Online、deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 為 `SUCCESS`，source commit `5b2b003c16201564bcda55edcccbb6d3e5948976`；正式 `/health` HTTP 200，唯讀 `tools/list` HTTP 200 並列出七個工具。當時 main 的文件 commit `98ee35a` 對 Railway 為 `SKIPPED`，所以當時 runtime 仍是 `5b2b003`。此紀錄早於 PR #265 的新 runtime。
- 2026-10-09 使用 Computer Use 在一般 ChatGPT「對話」模式驗證：私人 `AI Travel Planner MCP` 出現在「已安裝」清單；外掛詳細頁標示為你的雲端外掛程式，管理設定顯示 OAuth、MCP URL 結尾為 `/mcp`、審查狀態 `DEVELOPMENT`；一般 Chat 的外掛選單亦可選取此 MCP。設定頁另顯示版本 `dev mode`，外掛詳情頁資訊區顯示 `1.0.0`，版本標示不一致，無法由這次 UI 讀值判定是哪個 runtime/tool snapshot 版本。
- 同次一般 Chat UI 操作點擊「重新整理工具」後，按鈕變成 disabled，但沒有可見的成功／失敗訊息；故不記作刷新成功。將外掛加入新的一般 Chat composer 後，畫面保留未送出的外掛標籤；未輸入或送出任何 prompt，未發生 MCP 工具呼叫，也未觀察到工具清單。因此「外掛已安裝、能在一般 Chat 選取」已驗證；「一般 Chat 真的能發現並呼叫工具」仍未驗收。唯讀驗收 prompt 必須由維護者本人輸入。
- 最新本機 MCP 驗證命令 `PYTHONPATH=. uv run --isolated --with-requirements requirements-mcp.txt python -m unittest tests.test_mcp_server -v` 通過 21 項。測試包含真正 stdio 子程序握手與 `parse_trip_request` 呼叫，以及 Streamable HTTP 認證與工具協定；不呼叫外部供應商 API，亦不等於 ChatGPT Chat UI 驗收。
- 同日檢視此 Codex 對話的 AI Travel Planner connector 快照，僅顯示 6 個工具並缺少 `get_place_details`。這是 Codex connector 清單與 Railway 工具清單不同的證據，不能推論一般 ChatGPT Chat 顯示相同清單。OpenAI 自訂 MCP plugin 文件說明可在 app 詳細資料頁 Refresh apps，以取得新工具、描述與 server instructions；已將該步驟加入 [ChatGPT Chat 驗收流程](chatgpt-mcp-live-verification.md)。ChatGPT Chat 實際刷新與工具呼叫尚未驗收。
- Sites 唯讀 `get_site(include_mcp_connection=true)` 確認私人 `AI Travel Planner MCP` Site 為 `active`、目前版本 7，MCP endpoint 結尾為 `/mcp`。此只證明 Site 設定與部署版本存在，不證明 ChatGPT plugin 已刷新工具清單或一般 Chat 可呼叫。
- PR #243 避免 Google Places 候選名稱與地址經由 `validation[].message/context` 殘留於新持久化／發布 projection；保留 Place ID、自有行程與驗證代碼。MCP 指引要求具名呈現已排定地點時即時呼叫 `get_place_details` 並附 attribution。既有原始行程沒有改寫。
- PR #244 不再讓未排入的額外 POI warning 阻止發布。PR #245 允許有已揭露 warning 的行程在明確同意後以 preview 發布；bundle 的 `warning` 與 registry 的 `incomplete` 狀態會保留。錯誤級驗證、沒有餐點的日期與硬性缺項仍阻止發布。
- PR #256 把排程期間可行的未選 POI 區分為備選，不再產生 `schedule.poi_candidate_unselected` 警告；營業時間或可行路線無法驗證的候選仍警告。可行集合僅在排程記憶體中計算，不會加入 Canonical Trip。
- PR #258 在沒有選定住宿時將首個景點最早時間設為 09:30，讓 08:00–09:00 早餐後仍須通過實際 restaurant-to-POI route check；未知路線不會視為零。記錄式無住宿測試在有營業時間和路線證據時排入五天 15 餐。
- PR #258 commit `ce3a5f5` 的 pytest 全套為 377 passed、288 subtests passed；CI `python`、`pytest`、`mcp-site` 三項成功。Railway deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 對應 merge commit `5b2b003c16201564bcda55edcccbb6d3e5948976`，狀態 `SUCCESS`；`/health` HTTP 200。
- 使用者提供的正式 ChatGPT Chat 倉敷規劃結果有每日 2 至 3 筆餐點，共 11 筆；住宿按需求留空。4 個餐段與預算費用估算仍有 warning。#180 原始「每日沒有任何餐點」問題已按新規劃結果結案。
- 2026-10-08 以已連線的唯讀 MCP connector 對相同需求再次呼叫 `parse_trip_request`：`origin=桃園`、目的地倉敷、日期、人數、自駕、`budget_status=unlimited` 均正確，`missing_fields=[]`。使用者提供的 ChatGPT 回答摘要曾列 `origin=null`，此差異未能由正式 MCP parser 重現；connector 呼叫不等於 ChatGPT Chat UI 的回應驗收。
- 同日以唯讀 `get_trip` 讀取 `kurashiki-2026-11-live-20261008`：原版本五天各 2、2、3、2、2 筆餐點（共 11 筆）。之後依已確認規格再次呼叫 `plan_trip(confirm_write=true)` 寫回同一 ID，並唯讀讀回；目前五天各有早餐、午餐、晚餐，共 15 餐，沒有 `meal.period_unselected`。重規劃仍有 3 個 `schedule.poi_candidate_unselected`、5 個 `schedule.origin_unknown`、`schedule.hotel_missing` 與 `budget.incomplete`。Safe response 未含地點名稱、地址、座標或營業時間欄位。此為正式 MCP read/write/read 驗證，不代替 ChatGPT Chat UI 驗收。
- 使用者提供的同一行程曾回報 `publish_trip_site` 為 `not_ready`，訊息列出 10 筆未排入候選景點、4 個未安排早餐餐段與費用不完整。2026-10-08 再以正式 MCP 呼叫同一 `trip_id`、同一 slug、`confirm_public_publish=true`、`confirm_overwrite=false`，工具回 `already_published`，確認既有公開頁存在；沒有覆寫公開頁。公開頁、bundle 與 registry 均回 HTTP 200，registry 為 `preview`／`incomplete`。目前正式 publisher 將這些 warning 保留在不完整預覽中；早先的 `not_ready` 回應與本次正式工具重查結果不一致，來源時點尚無法確認。
- 目前已存在的公開 bundle 有 5 天、10 筆 visit、11 筆 meal，以及 10 個未排入景點候選 warning。這是既有行程的保存狀態；PR #256 不會自動改寫或重新規劃歷史資料。4 個 `meal.period_unselected` 對應四天未安排早餐；`budget.incomplete` 代表費用未完整估算，不代表預算上限未設定。公開頁仍以泛用地點標籤呈現，地點詳情需在使用時即時查詢。
- 2026-10-08 使用使用者已明確確認公開的既有行程，透過已連線 AI Travel Planner MCP 呼叫 `publish_trip_site(trip_id="kurashiki-2026-11-live-20261008", site_slug="kurashiki-2026-11-live-20261008", confirm_public_publish=true)`。工具回 `publish_accepted`，URL 為 `https://jackytsai70113.github.io/ai-travel-planner/trips/kurashiki-2026-11-live-20261008/`，commit `d40c71c84e94c201b5de8a5889fced98abdd250f`，初始 deployment status 為 `pending`。GitHub Pages workflow `37736450625` 成功；該網址以 `curl` 回 HTTP 200，標題為「倉敷 行程｜AI Travel Planner」，registry 標記 `status=preview`、`readiness=incomplete`。這不是一般 ChatGPT Chat UI 或互動瀏覽器驗收。
- 發布 commit 的 Website CI `37736450517` 因 `web/tests/portal-e2e.mjs` 將入口卡片數硬編碼為 5 而失敗；新增第六筆登錄行程後觸發此回歸。PR #250 改為依 `public/trip-registry.json` 動態核對卡片數；PR 的 Python、pytest、MCP site、Website CI 均通過，並以 merge commit `8eec8baa2a7647a197b713cf9305fe71974409a8` 合併。合併後 CI `37737544356` 與 Website CI `37737544402` 均成功，Pages workflow `37737544370` 亦成功。
- #199 已依維護者指定的歷史資料保留範圍結案。既有 Railway 檔案、公開 Pages 內容與 Git 歷史保持原樣；結案不表示歷史內容已清除或重新核驗。
- 先前驗收紀錄：#179 當時是唯一開啟的 issue。維護者確認覆寫後，正式 MCP `publish_trip_site` 回 `publish_accepted`，GitHub commit `3649492fd7f4f09965217c2a3b75c6f45f1bf3b4`；Pages workflow `37742158112` 成功。行程頁、`public-bundle.json` 與 registry 均 HTTP 200；bundle 為 5 天、每天 3 餐（共 15 餐），registry 為 `preview`／`incomplete`。當時記錄的一般 ChatGPT Chat 實際工具呼叫待驗收，現況已由維護者提供的對話紀錄更新，詳見本文件頂端補充。
- 最新連線 MCP connector 的唯讀 `parse_trip_request` 對已確認的倉敷需求回 `parsed`，目的地倉敷、區域岡山縣、日期、人數、桃園出發、不限預算、自駕均正確；唯讀 `get_trip` 回同一 trip ID、5 天、每天 3 餐，並保留上述未完成 warning。這是 Codex connector 的工具呼叫，不可當成一般 ChatGPT Chat UI 驗收。

下方依時間排列的 PR／部署紀錄是當時狀態快照；其中舊 issue 開啟狀態與舊 deployment ID 不代表目前狀態。以上方「目前正式狀態」和當前 GitHub／Railway 資料為準。

## 2026-10-08 PR #235 合併後 MCP 驗證

- PR #235 以一般 merge commit 合併，`main` 為 `9219ffbda35d82d547324038e0f47cfdc5178659`。PR 的 `python`、`pytest`、`mcp-site`、`website` checks 均成功；同 SHA 的 GitHub Pages deploy workflow 亦成功。
- Railway `ai-traveller` production deployment `90208905-5cea-46a9-bf2a-eb8b4aa9f11f` 使用相同 source commit，狀態 `SUCCESS`。正式 `/health` 回 HTTP 200、內文 `ok`。
- Railway CLI 注入既有 `BEARER_TOKEN` 後，MCP `tools/list` 回 HTTP 200，共 7 個工具，包含 `get_place_details`。單次唯讀 production `get_place_details` 回 HTTP 200、`status=available`、署名 `Google Maps`，並回傳 Place ID；輸出只記錄資料欄位名稱，沒有保存或記錄地點詳情或 secret 值。
- 後續唯讀呼叫 production `parse_trip_request`，輸入完整倉敷需求，回 HTTP 200、`status=parsed`、目的地 `倉敷`、區域 `岡山縣`、日期 `2026-11-01` 至 `2026-11-05`、6 位成人、1 位兒童及年齡 2、不限預算、`missing_fields=[]`。此為 Railway 直連工具呼叫，不是 ChatGPT UI 驗收。
- 後續唯讀 `get_trip(trip_id="kurashiki-2026-11")` 回 HTTP 200、5 天、0 個餐點；經安全摘要投影後沒有回傳 Google 地點名稱。此查詢沒有寫入或重建來源檔，亦不代表舊 Railway 檔案或舊公開頁已被清除。
- ChatGPT Chat UI 本次未驗收：Computer Use 回報 Mac 已鎖定且無法自動解鎖。沒有輸入或代送 prompt；因此不能把直接呼叫 Railway MCP endpoint 說成 ChatGPT Chat 通過。最新 UI 驗收仍依 [`ChatGPT Chat MCP 上線驗收流程`](chatgpt-mcp-live-verification.md) 待維護者本人執行。
- PR #236 的文件 merge commit 為 `72d0dbf196c1e6ffc048cd75194c9f829439b65b`，PR #237 後續文件 merge commit 為 `37aacd2e43a67689b4b36b5e3b9fedb90fdc2f00`；兩者都沒有改變 MCP 程式。上述 Railway deployment 對應最近一次後端程式 commit `9219ffbda35d82d547324038e0f47cfdc5178659`。
- #180：無住宿情境的排餐程式與 recorded regression 已部署；正式新 `plan_trip` 每日餐點和完整度仍待一般 ChatGPT Chat 驗收。舊 `kurashiki-2026-11` 記錄不是新規劃結果。
- #179：publisher 已部署、`GITHUB_TOKEN` repo push 權限先前已唯讀確認；尚未對任何實際行程做明確公開確認、Pages publish 與瀏覽器網址驗收。
- #199：新寫入與輸出採 Place ID／自有行程投影、詳細資料即時查詢。依維護者要求，既有 Railway 檔案、已發布 Pages bundle 與 Git 歷史未刪除或改寫；舊公開頁可能仍含歷史 Places 詳細資料，所以 issue 保持開啟。
- 長期目標和完成條件持續記錄於 [`AI Travel Planner MCP 長期目標`](mcp-roadmap.md)。

## 2026-10-08 PR #230 Railway 部署與後端唯讀驗證

- PR #230 已以一般 merge commit 合併，`main` 為 `fe0ae02047c05488a2cafb03f37bc646add6cf67`。變更只設定 Railway backend 的 `build.watchPatterns`，使 `Dockerfile`、`requirements-mcp.txt`、`requirements-mcp-server.txt`、`src/**`、`trips/**` 變更才觸發後端部署；網站、測試及文件變更不觸發後端部署。
- `railway config plan` 原先只列 1 項 `build.watchPatterns` 更新，0 add、0 destroy；`railway config apply --yes` 後再次執行 plan，結果為設定已同步、無待套用變更。配置 plan 未涉及變數、GitHub 來源或 `/data` volume。
- Railway deployment `522e831d-be9b-4dd4-aa75-d016b6ec058d` 對應 `fe0ae02047c05488a2cafb03f37bc646add6cf67`，狀態 `SUCCESS`；正式服務 Online，`/health` 回 HTTP 200、內文 `ok`。deployment image digest 與前一個部署相同；`/data` volume 仍掛載，使用量 33 MB / 500 MB。
- 以 Railway CLI 注入既有 `BEARER_TOKEN` 執行唯讀 MCP 後端檢查，未輸出 token：`tools/list` HTTP 200，列出 `parse_trip_request`、`validate_trip`、`get_trip`、`plan_trip`、`build_trip_site`、`publish_trip_site`；`parse_trip_request` HTTP 200，輸入「我想安排倉敷五天四夜」回 `parsed`、目的地倉敷、5 天 4 夜。
- 以 Railway CLI 注入既有 `OPENROUTESERVICE_API_KEY`，呼叫 adapter 現用的 HeiGIT `api.heigit.org/openrouteservice/v2/matrix/driving-car`，使用供應商文件中的 Heidelberg 範例座標執行單次唯讀矩陣請求。回應 route `available`、189 秒、889 公尺，確認 production key 可用於新網域；這不代表倉敷實際路線、營業時間或餐點排程已驗收。
- PR #230 不修改 MCP runtime、tool schema 或 ChatGPT Site 設定。本次沒有在一般 ChatGPT Chat 送出新 prompt；因此未把上述 HTTP smoke test 誤報為 ChatGPT UI 驗收。#180 的新 `plan_trip` 每日餐點驗收仍由維護者在一般 ChatGPT Chat 執行並回報。
- 目前仍開啟 #180、#179、#199；正式規劃／餐點、GitHub Pages 發布、Google Places 資料生命週期的未完成範圍分別見下文。

## 2026-10-08 PR #225 部署後狀態

- PR #225 以一般 merge commit 將 `main` 更新為 `941b8c5c4e1cfc66e539d43cff29c0f80b4fc908`；GitHub Actions 的 `python`、`pytest`、`mcp-site` 均成功。本機 Python 3.13 驗證：production composition 24 passed、完整 pytest 367 passed / 288 subtests passed、`python -m unittest discover -s tests -q` 252 tests OK，`git diff --check` 通過。
- 此變更修正住宿自動搜尋已停用後的過時行程 provenance：住宿留空時只說明住宿欄位、未驗證的首段／返回交通，以及未納入預算的住宿與當地交通費；不再聲稱系統曾搜尋但找不到住宿。
- Railway `ai-traveller` production deployment `7a6a3ad2-496e-4f9d-a148-332209be76a6` 使用上述 main commit，狀態 `SUCCESS`；正式 `/health` 回 HTTP 200、內文 `ok`。
- 此次已驗證本機、CI、部署及 health；沒有在 ChatGPT Chat 執行新的 `plan_trip`。#180 的正式規劃驗收仍由維護者自行在一般 ChatGPT Chat 輸入倉敷 prompt，檢查新 Canonical Trip 的每日餐點與 warning 後才能關閉。
- 目前開啟的服務能力 issues 仍為 #180、#179、#199；各自的未完成驗收範圍見下文。

## 2026-10-08 Railway volume inventory 與網站 attribution

- PR #227 已以一般 merge commit `63aace248eb3e91d840d7c6a2e03a940ea070644` 合併；GitHub Pages deployment `37715791303` 成功。部署後以瀏覽器開啟正式 Awaji 每日行程頁，在 375、390、430、1200、1366、1440、1920px 檢查 Google 官方 98×18 logo、10px 水平／5px 垂直留白及水平溢出，七種寬度均通過。
- PR #228 已以一般 merge commit `9fcb177524788bc3ee5df43d0401d7817aae22e8` 更新資料生命週期盤點文件；`python`、`pytest`、`mcp-site` CI 均成功。透過已登入 Railway CLI SSH 對 production `/data` 執行唯讀 JSON metadata inventory，只輸出檔案數、欄位存在數及 trip ID，沒有輸出地點內容或憑證值。
- inventory 時 Railway service `ai-traveller` Online，volume 使用量 33 MB / 500 MB。volume 只有 1 份 Canonical Trip 與 1 個行程 HTML：`kurashiki-2026-11`。該 Trip 有 40 個景點、20 個餐廳、0 個住宿候選；60 個候選均有 Google Places API (New) provenance、名稱、地址與座標，20 個另含 opening hours、rating、ratings 與 field provenance。五天的每日行程仍為 0 個 meal item。細節見 [`Google Places 資料生命週期盤點`](google-places-data-lifecycle.md)。
- 這是 2026-10-08 合併 PR #239 前的單一時點唯讀 inventory；inventory 本身未刪除或改寫 Places 欄位。PR #239 已對合併後新資料實施 0 日保存與輸出投影；既有 Railway 行程、公開 bundle 和 Git 歷史仍依維護者指示原樣保留。#199 已結案，結案不代表歷史資料已清理或重新核驗。
- 以上均未執行新的 ChatGPT `plan_trip` 或公開行程。#180 仍待維護者在一般 ChatGPT Chat 執行新規劃並檢查每日餐點；#179 仍待明確確認發布一份符合 readiness 的 Trip，驗證 Pages deployment 與網址。不得用網站 CI、health check 或此次 volume inventory 取代這兩項驗收。

## 2026-10-08 PR #223 合併後正式狀態

- 長期目標已整理於 [`AI Travel Planner MCP 長期目標`](mcp-roadmap.md)：持續開發、測試、審查及合併，直到一般 ChatGPT Chat 可穩定完成有根據的旅行規劃；mock、healthcheck 或 CI 不能代替正式 ChatGPT 工具驗收。
- PR #220 已以一般 merge commit 將 `main` 更新為 `508d40c7d5ebb9e20d64d7ddfe9d75088065cbe9`。CI 的 `mcp-site`、`pytest`、`python` 均成功；完整本機測試為 365 passed、288 subtests passed。該版將 plan_trip 的逐題確認、明確寫入同意及公開發布同意分開寫入 MCP 工具說明。
- Railway `ai-traveller` production deployment `50a9d4d1-36dd-4447-a973-317f8f024b73` 對應此 main 版本，狀態 `SUCCESS`，且沒有待套用設定。
- 部署後以連線中的私人 MCP 對既有 `kurashiki-2026-11` 執行唯讀 `get_trip`。讀回仍是五天各一個 `visit`、沒有 `meal`；總預算狀態 `incomplete`，五個景點營業時間均有 `opening_hours.unverified`，並有兩筆 `research.provider_failed`。這是舊行程紀錄，不是新 `plan_trip` 執行，不能用來驗收 #180 的新規劃流程。
- #180 正式驗收仍需維護者在一般 ChatGPT Chat 輸入新的倉敷 `plan_trip` prompt，之後檢查新 Canonical Trip 的每日餐點及警告。一般 ChatGPT Chat 的正式 prompt 由維護者自行輸入；本次沒有代送 prompt，也沒有執行會寫入正式行程的 `plan_trip`。
- 住宿自動搜尋需求已由維護者放棄並關閉 #175。住宿可留空，也可由使用者提供；不得因缺少住宿而阻擋規劃，不得推測住宿費用或不存在的住宿接駁路線。
- 目前仍開啟的服務能力 issues 為 #180（待一般 ChatGPT Chat 新規劃驗收）、#179（待明確授權公開行程並驗證 Pages URL）、#199（Places 資料保存、既有資料處置與公開再託管尚未完成）。
- PR #223 已以一般 merge commit 將 `main` 更新為 `8288fb611276289ed08b135746243b74a65bec54`。Google Places 的 POI 與 restaurant 類別查詢現在各自隔離；任一類別失敗會保留另一類別已成功的候選，並以類別名稱記錄失敗，讓規劃仍能回報不完整狀態。Recorded 回歸驗證為 `367 passed, 288 subtests passed`，`python -m unittest discover -s tests -q` 為 252 tests passed，GitHub Actions 的 `python`、`pytest`、`mcp-site` 均成功。
- Railway production deployment `7a634e82-0357-47d9-b95d-f4e043dd246d` 使用上述 main commit，狀態 `SUCCESS`；正式 `/health` 回 HTTP 200、內文 `ok`。此為部署與服務健康檢查，不證明新倉敷 live `plan_trip` 會排入每日餐點。
- 部署後嘗試用 Computer Use 查看一般 ChatGPT Chat 驗收分頁；Chrome 仍是原有單一分頁，但 macOS 回報已鎖定且不能自動解鎖。沒有輸入或送出任何 prompt；新版 provider 行為的 ChatGPT Chat `plan_trip` 驗收仍待維護者本人在一般 Chat 發起。

## 2026-10-08 PR #215、#216 合併後基線（歷史）

- 長期目標已整理於 [`AI Travel Planner MCP 長期目標`](mcp-roadmap.md)：持續開發、測試、審查及合併，直到一般 ChatGPT Chat 可穩定完成有根據的旅行規劃；mock、healthcheck 或 CI 不能代替正式 ChatGPT 工具驗收。
- PR #215 的基線 commit `b0676515f62af85ee048bff94e82dc80319986be` 曾部署至 Railway deployment `cb92a197-1ff9-4ec8-a79f-6e499b0d0f75`，狀態 `SUCCESS`。PR #216 接著以一般 merge commit 將 `main` 更新為 `85e1ddd4891c753201db41730d2107e954746782`；CI 的 `mcp-site`、`pytest`、`python` 均成功，完整本機測試為 364 passed、288 subtests passed，production/planner 子集為 60 passed。
- Railway `ai-traveller` deployment `16a9ee13-3f23-4f7c-b775-5a382e40e4ef` 對應 `85e1ddd` 且狀態 `SUCCESS`；正式 `/health` 回 HTTP 200、內文 `ok`。此次只修改 GitHub Pages 發布路徑，沒有完成 ChatGPT Chat 的即時工具驗收。
- PR #215 的 recorded/mock production composition 覆蓋排三餐、無回程餐點保留候選與 warning、住宿留空時排可行餐點且不虛構接駁。沒有在新的倉敷 `plan_trip` live run 上驗證；ChatGPT 一般 Chat 的正式倉敷 prompt／工具呼叫仍待維護者自行輸入並回報。
- PR #218 已以一般 merge commit 更新 `main` 至 `a5d1609d560b7d6777b206ca6befda412faabacb`，修正倉敷 parser 的 destination provenance；Railway deployment `a50c0355-a5fc-45f8-93e4-b6b26047fda7` 對應此 commit 且狀態 `SUCCESS`。部署後以連線中的私人 MCP `parse_trip_request` 唯讀呼叫確認目的地／來源依據、縣市、日期、旅客、桃園出發、自駕與不限預算均正確；此呼叫未執行規劃，也不取代一般 ChatGPT Chat `plan_trip` 驗收。
- Railway `GITHUB_TOKEN` 已由遮蔽變數清單確認存在；前次正式執行個體的 GitHub REST 唯讀檢查回報 `permissions.push=true`。尚未經 ChatGPT 確認行程公開、等待 Pages 部署及瀏覽器開啟該行程網址；#179 保持開啟。
- GitHub Issue #175 已依維護者決定關閉；自動住宿搜尋不再是需求。住宿可留空；住宿若由使用者提供，未經驗證的地址、價格與交通仍須保持未驗證。
- 當時開啟的服務能力 issues：#180、#179、#199；目前狀態見本文件最上方的 PR #220 後正式狀態。
- PR #216 已加入動態 publisher guard 和欄位生命週期盤點文件。明確含 Google Places API (New) 候選／欄位 provenance 的發布會被阻擋；此防線只阻擋新 GitHub Pages 發布，沒有處理 Railway 私有持久資料與既有公開 bundle。

## 2026-10-08 過期行程封存修正部署

- PR #212 以一般 merge commit `bd59a6585846ee6df4b088c34cf4b7bcbc550708` 合併至 `main`。修改後，結束日期早於瀏覽器使用者當地日期的已發布行程會移到「封存 / 歷史」，並顯示封存狀態。
- GitHub Pages 部署 workflow [37664897575](https://github.com/JackyTsai70113/ai-travel-planner/actions/runs/37664897575) 對應相同 main SHA，狀態 `success`。以 Chrome 開啟正式首頁 `https://jackytsai70113.github.io/ai-travel-planner/`，確認「2026 淡路島五日行」（2026-08-27 至 2026-08-31）位於「封存 / 歷史」，沒有列在「精選 / 當前」。桌機 1200/1366/1440/1920px 與手機 375/390/430px 均無水平溢出。
- Railway `ai-traveller` production deployment `b369f5f5-baac-4c10-8567-e42ef1afd412` 狀態 `SUCCESS`、instance `RUNNING`，source commit 為同一 SHA。正式 `/health` 回 HTTP 200、內文 `ok`。本次變更只修改網站目錄分類，未變更 MCP 工具或認證；沒有在 ChatGPT Chat 送出新 prompt 或呼叫 MCP。
- 此次前端修正沒有解除下方 #175、#179、#180、#199 的既有阻塞，四張 issue 仍開啟。

## 2026-10-08 本輪重驗

- ChatGPT Chat 使用已連線的私人 `AI Travel Planner MCP` 呼叫 `parse_trip_request`，輸入「岡山縣倉敷五天四夜，6 位成人、1 位 2 歲幼兒，預算不設限制」。回應解析出目的地倉敷、區域岡山縣、5 天 4 夜、6 位成人、1 位 2 歲幼兒、`budget_status=unlimited`，`missing_fields=[]`。此為唯讀呼叫，未執行研究、寫入或公開行程。
- Railway OAuth connector 對正式 project `ai-traveller` / `production` 以遮蔽值模式列出變數名稱。已存在 `BEARER_TOKEN`、`GITHUB_TOKEN`、`GOOGLE_MAPS_API_KEY`、`OPENROUTESERVICE_API_KEY`、`PUBLIC_URL`、`YOUTUBE_API_KEY`；清單僅提供名稱，沒有讀取任何 secret 值。
- PR #204 已合併至 `8fbe0639d5fd341cbcc764979ff9e19cae30c6c2`，CI、Website CI、GitHub Pages deploy 均成功。首次檢視舊分頁仍顯示舊內容；強制重新載入後，GitHub Pages 首頁顯示新文案「頁面公開狀態與行程完成度分開呈現；公開預覽不代表行程已確認。」及「公開預覽」狀態。這只驗證公開目錄標籤，沒有改動或發布任何行程。
- 當時記錄的四張 issue 狀態已過期：#175 後續依維護者決定關閉自動住宿搜尋需求；#179、#180、#199 的目前狀態見本文件最上方。

## 2026-10-08 GitHub Pages 發布憑證更新

- 維護者已將 repository-scoped GitHub fine-grained token 設為 Railway `ai-traveller` production 的 `GITHUB_TOKEN`。Railway OAuth connector 的遮蔽值清單已確認變數名稱存在；沒有讀取 token 值。
- 新版 Railway deployment `95e9d527-d335-44fd-8669-6e2f49e3e2d2` 狀態為 `SUCCESS`，service 為 Online；正式 `/health` 回 HTTP 200、內文 `ok`。
- 維護者透過 Railway SSH 在正式執行個體發出 GitHub REST `GET /repos/JackyTsai70113/ai-travel-planner` 唯讀查詢。只輸出存在布林值與權限布林值，未輸出 token；回應 HTTP 200、repository identity 相符、`permissions.push=true`。這驗證該憑證可讀取目標 repo 且 GitHub 回報有 push 權限，沒有執行寫入。
- 尚未在 ChatGPT Chat 呼叫 `publish_trip_site`，也沒有指定並確認要公開的行程；所以 GitHub Pages 發布、Actions 部署及最終行程網址仍未驗收。依維護者要求，ChatGPT prompt 由使用者自行輸入。

## 2026-10-08 後續正式環境與網站檢查

- Railway `ai-traveller` production deployment `55396464-1724-47db-b4ae-5bb53c815cd2` 狀態為 `SUCCESS`；正式 `/health` 回 HTTP 200、內文 `ok`。未帶認證的 `/mcp` 回 HTTP 401，符合 MCP 端點認證要求。
- 當時重新檢查 Railway production 變數名稱時，尚無 `GITHUB_TOKEN`，因此沒有執行 GitHub Pages 發布。2026-10-08 後續憑證狀態見上方「GitHub Pages 發布憑證更新」。
- 以 Chrome 開啟正式 `terms.html` 與 `privacy.html`，兩頁均正常載入且互有連結。首頁與既有淡路島行程頁的政策連結已在 PR #208 部署後確認。
- 現有 ChatGPT 對話紀錄包含透過私人 `AI Travel Planner MCP` 成功呼叫 `parse_trip_request` 的倉敷結果。依維護者要求，本輪只讀取該既有結果，沒有在 ChatGPT 輸入或送出新 prompt。
- #199 的公開條款／隱私頁工作已完成；剩餘範圍是 Google Places provider facts 寫入持久化 Canonical Trip、既有資料保存／處置與公開再託管的政策盤點。公開頁上線本身不等於 Places 資料生命週期已解決。

## ChatGPT 連線狀態

- 私人 ChatGPT Site 已連到此 repo 的 Railway MCP backend；使用者曾在自己的 ChatGPT chat 中選取並呼叫 AI Travel Planner MCP 工具。
- Railway backend origin：`https://ai-traveller-production-732b.up.railway.app`。
- MCP endpoint：`https://ai-traveller-production-732b.up.railway.app/mcp`。
- `/health` 的最近記錄驗證為 HTTP 200；未帶授權直接呼叫 `/mcp` 回 HTTP 401 是預期行為。
- 2026-10-08 部署紀錄：Railway deployment `a9a03231-37f2-46cc-8a15-4cdc379f7224` 為 `SUCCESS`，source commit 為 `62ae026ce9f55b2a7a39bc24f95ec7a4130c63b0`；replica 為 Online，Dockerfile 為 `/Dockerfile`、healthcheck 為 `/health`、volume 掛載在 `/data`。部署後正式 `/health` 回 HTTP 200、內文 `ok`。該部署 manifest 確認 Railway 實際使用 On Failure、10 次重試；IaC 移除與 Railway 預設重複的明確覆寫後，`railway config plan` 回報無變更。完整驗證方式見 [Railway 驗證紀錄](../.railway/README.md#正式服務網址與驗證)。
- 2026-10-08 部署後使用 Computer Use 在 ChatGPT Chat 以外掛選單明確選取私人 `AI Travel Planner MCP`，使用者訊息顯示該 Site 連結，並要求只呼叫 `parse_trip_request`。實際回應 `status=parsed`、目的地倉敷、5 天 4 夜，且列出未提供旅客人數與預算。另一次唯讀呼叫 `publish_trip_site` 傳入測試 trip ID 與 `confirm_public_publish=false`，回傳 `status=confirmation_required`；沒有讀取行程檔、執行 `plan_trip` 或公開發布。瀏覽器操作前已核對 Chrome、ChatGPT 對話網址／標題及 AI Travel Planner MCP 名稱，操作後確認結果出現在同一對話。
- 同日只列出 Railway 正式服務變數名稱以確認缺漏，未讀取或輸出 secret 值；清單沒有 `GITHUB_TOKEN`。尚未執行任何公開行程寫入。
- 不在 repo、Issue 或文件記錄任何 secret 值。ChatGPT Chat 呼叫由維護者使用已連線的使用者環境實際執行；其餘 backend 驗證亦由維護者執行。

## Provider 實測

- Google Places API (New)：Railway 正式環境以倉敷查詢回 HTTP 200，取得 18 筆 place ID。此前曾有 HTTP 403 `PERMISSION_DENIED`；2026-10-05 重測已可用。文件不保存 API key，也不宣稱取得的結果就是使用者 GCP 畫面中的完整 key 字串比對結果。
- YouTube Data API：獨立 smoke test 曾回 HTTP 200、3 筆影片；實際 `plan_trip` 當次研究出現 TLS handshake timeout。因此，單次成功 smoke test 不代表每次 production research 都穩定。
- 住宿搜尋：2026-10-05 production run 沒有住宿候選。2026-10-08 維護者決定放棄自動住宿搜尋；後續實作已進入 main，住宿為選填，無住宿時不推測房況、價格或住宿接駁路線。
- Google Flights 僅提供搜尋連結、不擷取票價；倉敷輸出含「桃園 → 倉敷」的 Google Flights 搜尋連結。`candidate_sets.flights` 為空是目前設計，不代表行程沒有航班搜尋入口。

## 倉敷 production run 證據

輸入：日本岡山縣倉敷，2026-11-01 至 2026-11-05，6 位成人、1 位 2 歲幼兒，預算不設上限，自駕，出發地桃園國際機場；trip ID `kurashiki-2026-11`。

2026-10-05 對正式 MCP 呼叫 `plan_trip(confirm_write=true)` 後的觀察：

- MCP HTTP 200，工具最上層回 `status=complete`。
- Canonical Trip 通過 Trip V1 schema validation；日期、旅客資料與 Google Flights 搜尋連結存在。
- 五天每日各只有一筆 `visit` 景點，沒有餐點或餐廳行程項目。
- 研究候選集合有 20 筆餐廳、40 筆景點、0 筆住宿；沒有選定住宿。
- `research` 與 `validator_repair` stage 回報 `incomplete`。警告包括 YouTube timeout、住宿搜尋不可用、五個景點營業時間未確認，以及 `budget.incomplete`。
- 使用者明確表示預算不設上限，但該 Canonical Trip 的總額仍為 JPY 0、狀態 `incomplete`。
- Railway volume 有 `/data/trips/kurashiki-2026-11/trip.json` 和 `/data/site/kurashiki-2026-11/index.html`。
- Railway HTML 已有 Google Flights 連結；它不是 GitHub Pages 上可分享的行程頁。
- repo `web/public/trip-registry.json` 和 `web/public/trips/requested/` 沒有此 trip，因此目前沒有對應的 GitHub Pages 網址。

本次輸出暴露「頂層 complete 與未完成 stage/內容並存」的狀態問題。不可只憑 `status=complete` 宣稱行程完整。

## 歷史 issue 狀態快照（此段保留舊驗收紀錄）

以下狀態已於 2026-10-08 依 GitHub issue list 和正式環境證據核對：

- [#153 遠端 ChatGPT MCP hosting 與連線](https://github.com/JackyTsai70113/ai-travel-planner/issues/153)：已關閉；Railway backend 與私人 ChatGPT Site 的工具呼叫已實際成功。這不代表完整行程規劃功能已全部驗收。
- [#175 住宿供應來源](https://github.com/JackyTsai70113/ai-travel-planner/issues/175)：已依維護者決定關閉；不再尋找或呼叫自動住宿搜尋來源。住宿可以留空，未來由旅客提供住宿資料時也不可推測房況或費用。
- [#180 餐廳候選沒有排入每日用餐行程](https://github.com/JackyTsai70113/ai-travel-planner/issues/180)：production run 曾有 20 筆餐廳候選，但每日沒有餐點。後續實作已支援住宿留空時安排可由景點間路線驗證的餐點；仍需由維護者在一般 ChatGPT Chat 執行新的正式 `plan_trip`，確認新 Canonical Trip 每日餐點與未完成警告後才能關閉。
- [#179 MCP 規劃結果沒有對應的 GitHub Pages 網址](https://github.com/JackyTsai70113/ai-travel-planner/issues/179)：PR #189、#191 已加入並部署 `publish_trip_site` 與發布 readiness gate。Railway production 有 `GITHUB_TOKEN`，且 GitHub REST 唯讀 repo 查詢曾回報 `permissions.push=true`；尚未經 ChatGPT 明確確認發布行程或驗證 Pages 網址，因此 issue 保持開啟。
- [#199 Google Places 資料保存與公開展示政策待確認](https://github.com/JackyTsai70113/ai-travel-planner/issues/199)：PR #208 已新增並部署可公開直達的使用條款與隱私權政策頁面，Chrome 已確認正式頁可載入；這完成公開揭露頁，不表示 Places 資料保存與公開重用已合規。Places provider facts 仍進入可持久化 Canonical Trip；各欄位資料生命週期、既有資料處置與公開再託管仍待盤點。

#### #199 公開條款與隱私頁

- 預定正式網址：`https://jackytsai70113.github.io/ai-travel-planner/terms.html` 與 `https://jackytsai70113.github.io/ai-travel-planner/privacy.html`。
- 使用條款說明服務用途、行程資訊限制、明確公開確認流程及 Google Maps／Google Earth End User Additional Terms 與 Google Privacy Policy。
- 隱私權政策說明旅行需求與生成行程的後端保存、使用 Google／OpenRouteService／YouTube 的用途、公開 Pages 資料及第三方安全紀錄；Google Places 內容保存限制仍依 Google 現行政策。
- PR #208 合併及 Pages 部署後，已用 Chrome 開啟以上兩個正式網址，並檢查首頁與行程頁頁尾連結。#199 仍須等資料處理與公開展示盤點完成再驗收。

#### #199 attribution re-check after PR #206

- PR #206 was merged as `e9a189c9e90c5981659ef26e34a6abbbd158195a`. It adds a visible, untranslated `Google Maps` label to map links in the itinerary and lodging candidate views, using 12px normal-weight text.
- Post-deployment Chrome check on `https://jackytsai70113.github.io/ai-travel-planner/trips/awaji-2026/` opened the `每日行程` section and confirmed the map link is visible with label `Google Maps`, exact case, computed 12px/400 styling, and no horizontal overflow at 1200px.
- This fixes the previously observed absence of visible map-link attribution in those views. PR #208 later added and deployed public Terms/Privacy pages, which were opened in Chrome. Those earlier UI checks did not establish field-level sources or retention behavior; PR #239 subsequently added request-scoped Places details and durable/public projections for newly processed trips. #199 is closed, while historical files and Pages remain unchanged by explicit instruction.

### Issue #179 驗收流程

#### 最新驗收更新（2026-10-09）

- `main` merge commit `530144f23546776088975f796e3cc2c18d1f8641` 由 Railway deployment `aa3ef82c-f4ec-401d-9417-9d6e1aba59aa` 成功部署；部署來源 SHA 為 `530144f`。`/health` 回 HTTP 200／`ok`；正式 `tools/list` 回 HTTP 200，含七項工具（含 `get_place_details`）。
- 使用 MCP 覆寫 `kurashiki-2026-11-live-20261008` 成功，`publish_trip_site` 回 `publish_accepted`，commit `4380781d3cf91cd41656176769b2c2403feb03c6`。GitHub Pages workflow `37832158960` 成功，網址為 https://jackytsai70113.github.io/ai-travel-planner/trips/kurashiki-2026-11-live-20261008/。
- 使用 Computer Use 在同一 Chrome 視窗實際檢查該頁總覽及 D1。頁面渲染出即時地點名稱（例如 `大原美術館`、`Caty Cafe`、`大橋家住宅`）與 Google Maps 標示。公開 bundle 含 Places API base URL 和 Place ID，未持久化 Google 地點名稱。既有行程資料未重規劃；住宿、費用等原有 incomplete 狀態仍存在。
- 一般 ChatGPT Chat 外掛清單與選擇器顯示私人 `AI Travel Planner MCP`；設定頁顯示 OAuth 與 Railway `/mcp` URL。按「重新整理工具」後按鈕 disabled，但沒有結果提示，因此不能判定刷新成功。新對話 composer 已選取該 MCP 且保持空白；依維護者要求未輸入或送出 prompt，也未看到 ChatGPT UI 的真實工具呼叫。
- 已連線的 MCP connector 對 `parse_trip_request` 執行唯讀 smoke test，輸入「我想安排倉敷五天四夜」；回傳 `status=parsed`、`destinations=["倉敷"]`、5 天 4 夜，`missing_fields` 僅含旅客與預算。此結果驗證 backend parser 回應，不替代 ChatGPT Chat UI 工具呼叫。

倉敷行程的發布路徑已驗證完成：使用者確認覆寫後，正式 `publish_trip_site` 接受行程，Pages workflow `37742158112` 成功，公開 URL 與 bundle 均已驗證。行程維持 `preview`／`incomplete`，因住宿、部分起點與費用資料仍未驗證。發布工具與 `GITHUB_TOKEN` 設定不再是 #179 的阻塞。

2026-10-09 的未完成驗收如下：

1. Railway production deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 為 `SUCCESS`，source commit `5b2b003c16201564bcda55edcccbb6d3e5948976`；`/health` 與正式 `tools/list` 均回 HTTP 200，列出七項工具。
2. 一般 ChatGPT「對話」模式已確認私人 `AI Travel Planner MCP` 出現在已安裝外掛清單、設定頁可見 OAuth 與 `/mcp` endpoint，且一般 Chat 外掛選單可選取。設定頁 Refresh tools 按鈕被點擊後呈 disabled，沒有成功／失敗提示，故刷新結果不確定；ChatGPT UI 未顯示工具清單，也沒有真實工具呼叫。
3. 維護者必須本人在該一般 Chat 輸入 [`ChatGPT Chat 驗收流程`](chatgpt-mcp-live-verification.md) 的唯讀 `parse_trip_request` prompt。已選取的外掛標籤留在空白 composer；沒有輸入或送出任何 prompt。
4. 以瀏覽器實際開啟倉敷公開網址並核對行程頁內容與互動；HTTP 200 不足以通過此項。
5. 保存不含帳戶敏感資訊或其他私人對話的 UI 證據，更新本節與 #179。以上完成後才關閉 #179。
