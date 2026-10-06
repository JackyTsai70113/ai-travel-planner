# ChatGPT Chat MCP 上線驗收流程

此流程驗證已部署的 MCP 是否真的能從 ChatGPT Chat 被發現、認證並呼叫。它適用於會影響 MCP 部署、endpoint、bearer authentication、工具註冊或 ChatGPT Site 連線設定的變更。

## 驗收原則

1. 部署成功、CI 通過、`/health` 回應正常或 MCP `tools/list` 成功，都只證明各自的檢查範圍；不能證明 ChatGPT Chat 可以使用 MCP。
2. 正式驗收必須使用 Computer Use 操作 ChatGPT Chat，並在該對話中實際呼叫已連線的 AI Travel Planner MCP 工具。
3. curl、MCP Inspector、直接呼叫 Railway endpoint、Site connector/API 測試不能代替這項 ChatGPT Chat 驗收。
4. ChatGPT 無法開啟、Site 不可用、工具未出現或無法完成工具呼叫時，結果是「未通過／未驗收」；記錄阻塞並修復後重測，不得以其他 smoke test 宣稱通過。
5. 使用不會寫入或公開行程的唯讀工具。不得為了 smoke test 呼叫 `plan_trip`、`publish_trip_site` 或其他會建立、覆寫、部署或公開資料的工具。

## 部署後操作

1. 確認 GitHub Actions 中此變更所需的 CI 全部通過，並記下預期部署的 `main` commit SHA。
2. 在 Railway 確認最新正式環境 deployment 為成功狀態，記下 deployment ID、狀態、完成時間，以及 Railway 顯示的 deployed/source commit SHA。確認它與預期的 `main` SHA 完全一致。若 Railway 沒有提供 commit SHA，必須保存可稽核且能明確連結該 deployment 與該 `main` SHA 的部署紀錄或 workflow 證據；沒有此對應證據就標記「未驗收」。使用既有 Railway 驗證文件中的正式服務資訊；不要在紀錄中抄錄變數值或憑證。
3. 使用 Computer Use 開啟 ChatGPT 的實際 Chat 介面，建立一個新對話，選取私人 `AI Travel Planner MCP` Site/plugin。
4. 在 ChatGPT 介面確認 MCP 工具可用。若工具沒有出現，停止並記錄 discovery/authentication 失敗，不要把 HTTP 測試視作替代通過。
5. 在 Chat 中送出以下唯讀 smoke test，要求 ChatGPT 明確使用 `parse_trip_request`，不要改用模型自行解析：

   `請使用 AI Travel Planner MCP 的 parse_trip_request 工具解析「我想安排倉敷五天四夜」。請直接呼叫工具，不要自行回答或呼叫其他工具。`

6. 在 ChatGPT 的工具呼叫 UI 確認實際呼叫的是 `AI Travel Planner MCP` 的 `parse_trip_request`，並檢視工具回應。確認呼叫成功、回應包含解析狀態與行程意圖，目的地和五天四夜資訊符合輸入；不可只根據模型在工具呼叫之外的文字敘述判定成功。
7. 若此變更影響其他特定工具或資料路徑，再依變更範圍增加一個安全、唯讀的 ChatGPT Chat 工具呼叫；不得略過上述基本 smoke test，也不得用寫入型工具作部署健康檢查。若受影響行為只有寫入型工具可觀察，未經本次任務明確授權不得呼叫該工具；該項受影響行為維持「未驗收」，直到能在無副作用的方式下驗證或取得明確授權。
8. 保存足以核對結果的 ChatGPT Chat 截圖或短錄影，以及以下驗收紀錄。截圖需避免顯示帳戶敏感資訊、secret 或無關私人對話。

## 通過條件

以下條件須全部成立：

1. 目標 Railway deployment 是成功狀態，且有可稽核證據證明 deployed/source commit SHA 與此次待驗收的 `main` SHA 完全一致；若平台未提供 SHA，須有等價的明確部署對應證據。
2. ChatGPT Chat 中的私人 Site/plugin 可被選取，MCP 工具可見。
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
