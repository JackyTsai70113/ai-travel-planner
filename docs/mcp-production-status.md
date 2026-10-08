# ChatGPT MCP 正式環境現況與已知問題

最後查證：2026-10-08。本文記錄本 repo MCP 部署與實際工具呼叫的觀察結果，不代表規劃品質已達可交付標準。

## 2026-10-08 PR #225 部署後狀態

- PR #225 以一般 merge commit 將 `main` 更新為 `941b8c5c4e1cfc66e539d43cff29c0f80b4fc908`；GitHub Actions 的 `python`、`pytest`、`mcp-site` 均成功。本機 Python 3.13 驗證：production composition 24 passed、完整 pytest 367 passed / 288 subtests passed、`python -m unittest discover -s tests -q` 252 tests OK，`git diff --check` 通過。
- 此變更修正住宿自動搜尋已停用後的過時行程 provenance：住宿留空時只說明住宿欄位、未驗證的首段／返回交通，以及未納入預算的住宿與當地交通費；不再聲稱系統曾搜尋但找不到住宿。
- Railway `ai-traveller` production deployment `7a6a3ad2-496e-4f9d-a148-332209be76a6` 使用上述 main commit，狀態 `SUCCESS`；正式 `/health` 回 HTTP 200、內文 `ok`。
- 此次已驗證本機、CI、部署及 health；沒有在 ChatGPT Chat 執行新的 `plan_trip`。#180 的正式規劃驗收仍由維護者自行在一般 ChatGPT Chat 輸入倉敷 prompt，檢查新 Canonical Trip 的每日餐點與 warning 後才能關閉。
- 目前開啟的服務能力 issues 仍為 #180、#179、#199；各自的未完成驗收範圍見下文。

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

## 目前開啟的 Issues 與可推進範圍

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
- This fixes the previously observed absence of visible map-link attribution in those views. PR #208 later added and deployed public Terms/Privacy pages, which were opened in Chrome. Neither change establishes that every displayed place fact came from Places API or that Places-derived content has compliant retention and rehosting behavior. #199 remains open pending that data-lifecycle review.

### Issue #179 驗收流程

1. 維護者在 GitHub 建立 fine-grained PAT，只授權 `JackyTsai70113/ai-travel-planner` repository 的 `Contents: Read and write`，將其設為 Railway service secret `GITHUB_TOKEN`。已確認變數存在，且 GitHub REST 唯讀 repo 查詢回報 `permissions.push=true`；不得將 token 寫入 repo、issue、聊天工具參數或 CI log。
2. 確認 Railway 使用至少包含 PR #191 merge commit `0a948bcfb8dcb6089e9f1daf16adad1e469b1b15` 的版本，且最新 deployment 狀態為 `SUCCESS`；新增 secret 後等新 deployment 成功，再由維護者重跑 health 與 `tools/list` smoke test。
3. 在 ChatGPT chat 先完成行程規劃。只有使用者明確要求公開分享並確認公開範圍後，才呼叫 `publish_trip_site`，傳入既有 `trip_id`、`confirm_public_publish=true`；更新現有公開內容時還要明確傳 `confirm_overwrite=true`。
4. 工具回傳 `publish_accepted` 與 Pages URL 後，等待 Pages Actions 部署完成，實際開啟網址確認對應行程內容。僅工具接受寫入或回 `pending` 不算完成驗收。
5. 將 deployment 結果、HTTP/瀏覽器可用證據與 commit SHA 記錄回 #179；驗收全部完成後才關閉 issue。

以上只列已觀察問題與外部依賴；#175 已關閉，#180 的正式 ChatGPT Chat 驗收仍待執行。本次沒有以 fixture 代替正式資料，也沒有發布倉敷頁面。
