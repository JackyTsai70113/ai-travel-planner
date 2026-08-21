# Design gallery workflow

此目錄是 Issue 73 的 design governance contract。Gallery 是 public-safe、deterministic 的獨立 preview；production 元件由 web app 的既有 design system 提供，待各頁面 owner 增加對應 story/scenario 時，使用同一份 fixture 與 baseline manifest。

## 本地驗證

```sh
node web/design-preview/build-gallery.mjs
python3 -m json.tool web/visual-fixtures/gallery-scenarios.json >/dev/null
python3 -m json.tool web/visual-baselines/manifest.json >/dev/null
```

開啟 `web/design-preview/design-gallery-dist/index.html`，依 baseline manifest 檢視 390×844、430×932、768×1024、1440×900；切換三種 theme 並檢查 state matrix。截圖產生器由 Issue 62 的 release tooling 呼叫，不能用此 gallery build 取代 screenshot artifact 或人工 review。

## Baseline 更新規則

1. fixture 固定 clock、random seed、API mode；不要使用 live API、private data、隨機內容或未固定時間。
2. 只在 intentional design change 時更新 golden manifest 或 screenshot；PR 必須說明 visual diff、affected viewport/theme/state。
3. unexplained large diff 必須停在 review，並由 reviewer 記錄 finding、fix commit 或 accepted limitation。
4. review record 必須綁 exact SHA，material fix 後重新由獨立 reviewer 檢視。
