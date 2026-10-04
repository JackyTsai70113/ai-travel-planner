# 設計展示流程

此目錄是 Issue 73 的設計治理契約。Gallery 是公開安全、可重現的獨立預覽；正式元件由 web app 既有的設計系統提供。各頁面負責人新增對應的 story/scenario 後，使用同一份 fixture 與 baseline manifest。

## 本機驗證

```sh
node web/design-preview/build-gallery.mjs
python3 -m json.tool web/visual-fixtures/gallery-scenarios.json >/dev/null
python3 -m json.tool web/visual-baselines/manifest.json >/dev/null
```

開啟 `web/design-preview/design-gallery-dist/index.html`，依 baseline manifest 檢視 390×844、430×932、768×1024、1440×900；切換三種主題並檢查狀態矩陣。截圖產生器由 Issue 62 的發布工具呼叫，不能以此 gallery build 取代 screenshot artifact 或人工審查。

## 基準更新規則

1. fixture 固定 clock、random seed、API mode；不要使用 live API、private data、隨機內容或未固定時間。
2. 只在刻意進行設計變更時更新 golden manifest 或 screenshot；PR 必須說明視覺差異、影響的 viewport/theme/state。
3. 無法解釋的大幅差異必須停在 review，並由 reviewer 記錄 finding、修正 commit 或接受的限制。
4. review record 必須綁定 exact SHA；重大修正後由獨立 reviewer 重新檢視。
