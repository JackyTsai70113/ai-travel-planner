# Railway 部署設定

`.railway/railway.ts` 是本專案 Railway production 環境的 IaC 定義，管理 GitHub repo 來源、服務副本數、`/data` volume、Dockerfile、健康檢查、重啟策略及既有服務變數。

## 檢查與套用

安裝 repo 根目錄的 JavaScript 開發相依套件後，先預覽遠端與本機定義的差異：

```sh
npm install
railway config plan
```

確認 plan 沒有移除服務變數、解除 GitHub repo 來源或卸載 `/data` volume，且 Dockerfile 與部署設定正確後，才執行：

```sh
railway config apply
```

變數以 `preserve()` 表示保留 Railway 現有值，不將 secret 明文寫進 repo。新增或移除服務變數時，應先檢視 `config plan` 的實際差異。

## 重要設定

- 來源：`JackyTsai70113/ai-travel-planner`
- 建置：repo 根目錄的 `/Dockerfile`
- 健康檢查：`/health`，逾時 120 秒
- 重啟：失敗時重試，最多 10 次（與 Railway 目前服務設定一致）
- 永續資料：volume 掛載於 `/data`，服務維持單一副本
