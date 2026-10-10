# ChatGPT Chat MCP 上線驗收流程

此流程驗證已部署的 MCP 是否真的能從 ChatGPT Chat 被發現、認證並呼叫。它適用於會影響 MCP 部署、endpoint、bearer authentication、工具註冊或 ChatGPT Site 連線設定的變更。

## 驗收原則

1. 部署成功、CI 通過、`/health` 回應正常或 MCP `tools/list` 成功，都只證明各自的檢查範圍；不能證明 ChatGPT Chat 可以使用 MCP。
2. 正式驗收必須使用 Computer Use 操作 ChatGPT Chat，並在該對話中實際呼叫已連線的 AI Travel Planner MCP 工具。
3. curl、MCP Inspector、直接呼叫 Railway endpoint、Site connector/API 測試不能代替這項 ChatGPT Chat 驗收。
4. ChatGPT 無法開啟、Site 不可用、工具未出現或無法完成工具呼叫時，結果是「未通過／未驗收」；記錄阻塞並修復後重測，不得以其他 smoke test 宣稱通過。
5. 使用不會寫入或公開行程的唯讀工具。不得為了 smoke test 呼叫 `plan_trip`、`publish_trip_site` 或其他會建立、覆寫、部署或公開資料的工具。

## Computer Use 操作前核對

每次使用 Computer Use 前，先以瀏覽器分頁清單及畫面確認以下項目，不依賴前一次操作留下的分頁或焦點：

1. 確認使用中的瀏覽器名稱，以及目標分頁的完整網址和頁面標題。
2. 確認畫面上的產品、repo 或 Site 名稱與本次任務一致。例如 AI Travel Planner 驗收必須確認頁面不是其他專案的 ChatGPT 對話或 GitHub repo。
3. 若網址、標題或頁面內容任一項不符，先停止，不輸入文字、不點擊、不送出；改用已確認的正確分頁或新分頁。
4. 點擊或輸入後重新讀取頁面狀態，確認網址、標題或主要畫面確實出現預期變化。動作回報成功本身不算驗證成功。
5. 若動作進入搜尋框、錯誤 repo、錯誤對話或其他非預期位置，立即停止後續操作，清除已輸入的臨時文字（若安全可確認），回報實際情況並重新核對正確目標。

瀏覽器驗收紀錄應記下目標網站網址、頁面標題、repo／Site 名稱、執行的唯讀動作及動作後觀察到的結果。不要記錄 cookie、登入資訊、憑證或無關私人對話。

## 部署後操作

1. 確認 GitHub Actions 中此變更所需的 CI 全部通過，並記下預期部署的 `main` commit SHA。
2. 在 Railway 確認最新正式環境 deployment 為成功狀態，記下 deployment ID、狀態、完成時間，以及 Railway 顯示的 deployed/source commit SHA。確認它與預期的 `main` SHA 完全一致。若 Railway 沒有提供 commit SHA，必須保存可稽核且能明確連結該 deployment 與該 `main` SHA 的部署紀錄或 workflow 證據；沒有此對應證據就標記「未驗收」。使用既有 Railway 驗證文件中的正式服務資訊；不要在紀錄中抄錄變數值或憑證。
3. 使用 Computer Use 在既有 Chrome 視窗開啟 ChatGPT 一般 Chat，優先使用 repo 已記錄的專案測試 Chat。若 composer 沒有明確顯示 `AI Travel Planner MCP` 標籤，從該 MCP 外掛詳情頁按「在對話中試用」啟動 Chat；只有 composer 可見外掛標籤才繼續。單從「＋」工具清單點選後，若 composer 沒有標籤，不可假設外掛已附加。輸入含中文的 prompt 時使用貼上，避免鍵盤輸入遺失字元；貼上後確認外掛標籤仍存在。
4. 若本次新增或修改 MCP 工具，先到 ChatGPT app/plugin 的詳細資料頁執行 Refresh apps，讓 ChatGPT 重新取得工具、描述與 server instructions；這是 OpenAI 自訂 MCP plugin 文件記載的更新方式。之後回到新 Chat 對話確認工具清單。若沒有刷新選項或刷新後工具仍未出現，停止並記錄 discovery/authentication 失敗，不要把 HTTP 測試視作替代通過。參考：[OpenAI：Add a custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server#how-to-use)。
5. 在 ChatGPT 介面確認 MCP 工具可用。本次 production backend 預期有七項工具，包括 `get_place_details`；Codex 或其他 connector 顯示的清單不能代替 ChatGPT Chat 的實際清單。若 ChatGPT 沒有顯示工具清單，實際工具呼叫卡片／應用程式回應需明確標示工具來源及成功結果。
6. 在 Chat 中送出以下唯讀 smoke test，要求 ChatGPT 明確使用 `parse_trip_request`，不要改用模型自行解析：

   `請使用 AI Travel Planner MCP 的 parse_trip_request 工具解析「我想安排倉敷五天四夜」。請直接呼叫工具，不要自行回答或呼叫其他工具。`

7. 在 ChatGPT 的工具呼叫 UI 確認實際呼叫的是 `AI Travel Planner MCP` 的 `parse_trip_request`，並檢視工具回應。確認呼叫成功、回應包含解析狀態與行程意圖，目的地和五天四夜資訊符合輸入；不可只根據模型在工具呼叫之外的文字敘述判定成功。
8. 若本次變更影響 `get_place_details`，額外在 ChatGPT Chat 呼叫一次已排定地點的 Place ID，確認回傳 `available` 和 `Google Maps` attribution。此為即時 Google Places API 請求，可能產生供應商費用；不要以未排入的候選或重複呼叫作驗收。
9. 若此變更影響其他特定工具或資料路徑，再依變更範圍增加安全、唯讀的 ChatGPT Chat 呼叫；不得略過上述基本 smoke test，也不得用寫入型工具作部署健康檢查。若受影響行為只有寫入型工具可觀察，該項行為維持「未驗收」，直到能以無副作用方式驗證。使用者對另一項實際寫入工作的明確授權，只授權該項獨立操作；不能把寫入型呼叫轉作 smoke test，也不能滿足本驗收 gate。
   - 若變更涉及 `get_trip` 的 `place_details_needed`，可另用既有行程做零供應商呼叫的 ChatGPT 驗收：明確要求只呼叫 `get_trip`、只回報該陣列數量，並禁止呼叫 `get_place_details`、重新規劃、寫入或發布。例如：`請直接呼叫 AI Travel Planner MCP 的 get_trip，trip_id 使用 kurashiki-2026-11-live-20261008。只回報工具實際回傳的 place_details_needed 數量；不要呼叫 get_place_details，不要重新規劃，也不要寫入或發布行程。` 此測試只驗證 ChatGPT 是否實際呼叫新版 `get_trip` 並收到欄位；它不驗證即時地點查詢，也不取代第 8 點。
10. 保存足以核對結果的 ChatGPT Chat 截圖或短錄影，以及以下驗收紀錄。截圖需避免顯示帳戶敏感資訊、secret 或無關私人對話。

## 通過條件

以下條件須全部成立：

1. 目標 Railway deployment 是成功狀態，且有可稽核證據證明 deployed/source commit SHA 與此次待驗收的 `main` SHA 完全一致；若平台未提供 SHA，須有等價的明確部署對應證據。
2. ChatGPT Chat 中的私人 Site/plugin 已明確附加於 composer，MCP 工具可見。
3. ChatGPT Chat UI 顯示真實的 `parse_trip_request` 工具呼叫與成功回應。
4. 工具回應的解析意圖符合 smoke test 中的倉敷與五天四夜需求。
5. 驗收證據及阻塞狀態已記錄，沒有把 CLI 或 HTTP smoke test 誤報成 ChatGPT 驗收。

任何一項不成立，ChatGPT MCP runtime 驗收即未通過。若無法取得 ChatGPT Computer Use 工作階段，也標示為「未驗收」，不可推定通過。

## 驗收紀錄格式

在 PR、部署紀錄或相關 Issue 中記錄：

```text
驗收日期（含時區）：
main commit SHA：
Railway deployment ID / 狀態 / 完成時間：
Railway deployed/source commit SHA：
SHA 對應證據：
ChatGPT Site/plugin：AI Travel Planner MCP（私人）
ChatGPT 實際呼叫工具：parse_trip_request
工具呼叫結果：通過 / 未通過 / 未驗收
結果摘要：只記錄解析欄位與錯誤類別，不記錄 secret 或不必要個資
證據：受限存取的截圖／錄影位置，或 PR 中可檢視的證據
阻塞事項：無，或簡述具體失敗點
```

不要將 bearer token、API key、登入憑證、cookie、Authorization header 或使用者私人資料寫入 repo、Issue、PR 或驗收截圖。

## 失敗定位

1. Site/plugin 無法選取或工具清單空白：記錄 ChatGPT UI 的 discovery/authentication 錯誤及發生時間。
2. 工具可見但呼叫失敗：記錄工具名稱、ChatGPT 顯示的錯誤類別、Railway deployment ID 與時間；避免複製任何憑證或完整私人 payload。
3. 呼叫成功但解析意圖不符合輸入：記錄錯誤欄位與最小必要輸入，作為 parser/runtime 行為缺陷處理。
4. 修正或重新部署後，從本流程第 1 步重新驗收，並讓證據對應新的 commit SHA 與 Railway deployment。
