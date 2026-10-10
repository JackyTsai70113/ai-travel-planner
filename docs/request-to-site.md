# 從需求到行程網站

`python3 -m src.cli plan-site` 是 repository checkout 中的 production 入口。它只會在研究、規劃、最佳化、驗證都完成並產生 Canonical Trip 後，將該 Trip 投影成 React 網站可讀取的 public bundle，並更新本機 trip registry。ChatGPT MCP 則使用獨立的 `publish_trip_site` tool 寫入 GitHub Pages repository；兩者都沿用同一個 public bundle allowlist。

```sh
python3 -m src.cli plan-site \
  --request '2027/10/20 到 2027/10/22，台北出發名古屋，2 大 1 小，賞楓、自駕、不要太累，預算 8 萬日圓' \
  --trip-id nagoya-autumn-2027 \
  --site-slug nagoya-autumn-2027
```

完整起訖日期、可辨識目的地與成人數是開始 production planning 的必要條件。只有「10 月」或「12 月」不會被任意補成年份或日期；命令會回傳 `needs_details`，不會產生虛構行程。「兩個人」會正確辨識為 2 位成人。

命令需要 README 所列的 provider credentials，並沿用既有 production pipeline。成功後：

1. Canonical Trip 儲存在 `trips/<trip-id>/trip.json`。
2. React 相容 public bundle 儲存在 `web/public/trips/requested/<site-slug>/public-bundle.json`。
3. `web/public/trip-registry.json` 會新增或更新同 slug 的 entry。部署流程透過 `bundle_source_slug` 將其發布到 `/trips/<site-slug>/`。

輸出固定為 `preview`，因為來源、營業時間、票價與可訂狀態都可能隨時間改變。驗證包含 critical error 時 registry readiness 為 `blocked`，不能當成可出發的旅程。

## 從 ChatGPT MCP 發布

本機 `build_trip_site` 不會公開行程。使用者若明確要求 MCP 規劃後公開網站並回傳網址，這項要求就是公開授權；MCP 應在規劃前的摘要確認中說明公開範圍，待使用者確認後，以 `confirm_write=true` 和 `confirm_public_publish=true` 呼叫 `plan_trip`。規劃成功後，工具會自動呼叫發布流程，並在同一個 `plan_trip` 回應中帶回發布結果與實際 URL。這會把旅程日期、同行人數與行程內容提交至 GitHub repository。若使用者沒有明確要求公開，規劃時須傳入 `confirm_public_publish=false`，規劃完成後再另外詢問公開授權。

有錯誤級驗證或硬性缺項的 trip 會拒絕發布。只有已揭露的警告（例如未安排全部餐段、費用估算不完整、住宿未選或未排入候選地點）時，仍可在明確公開確認後發布為 preview；registry readiness 保留 `incomplete`，網站 bundle 保留警告，不會標成完整。公開 slug 已被其他 trip 使用時不覆寫；更新同一 trip 的現有網站還需使用者另行確認 `confirm_overwrite=true`。

Railway 必須設定 `GITHUB_TOKEN` secret，token 僅需對指定 repository 有 `Contents: Read and write` 權限。發布以單一 Git commit 原子更新 bundle 和 registry，觸發既有 GitHub Pages Actions。MCP 回傳 `publish_accepted` 和正式網址時，部署狀態仍是 `pending`；Actions 完成後網站才會顯示新版內容。其他 repository/branch/Pages host 設定請看 [MCP server deployment](mcp-server.md#已查證的-railway-production-endpoint2026-10-05)。
