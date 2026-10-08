# Google Places 資料生命週期盤點

最後核對：2026-10-08。這份文件記錄程式實際保存路徑與已查閱的 Google 官方文件，不作法律合規結論。

## 官方規則摘要

本服務 GCP 計費地址尚未從帳務設定確認是否屬於 EEA。Places API 文件說明非 EEA 帳務地址使用一般 Maps Platform 條款；EEA 有另一套 Service Specific Terms，部署前仍須確認適用版本。

已查閱：

- [Places API 政策與 attribution](https://developers.google.com/maps/documentation/places/web-service/policies)：Places 內容除明文例外外不得預取、快取或保存；Place ID 不受快取限制，可永久保存。顯示非地圖內容時須提供 Google Maps attribution，Places 內容不得放在非 Google 地圖上。
- 同一份 Places API 政策的最新歸屬標示說明要求盡可能使用 Google Maps 官方 logo；介面空間不足時才可使用未翻譯、大小寫不變的 `Google Maps` 文字。repo 將官方提供的深灰色 logo 原樣加入地圖連結，保留 98×18 比例及規定留白。此標示只標明 Google Maps 連結；不代表行程內每個地點欄位都已完成來源辨識。
- [Maps Platform Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms) 第 14 節：Places API (Legacy and New) 明確允許緯度、經度快取最多 30 個連續日，期滿必須刪除。
- [Maps Platform Terms](https://cloud.google.com/maps-platform/terms) 第 3.2.3 節：禁止在服務外匯出、擷取、保存、轉載或重新託管 Google Maps Content；條文明列複製保存商家名稱與地址。禁止快取未經 Service Specific Terms 明確允許的內容，也禁止以 Google Maps Content 建立內容。Attribution 本身不會授予保存或重新託管權。

## Google Places API (New) 欄位清冊

| API 欄位 | 正規化欄位／用途 | Google 例外與期限 | 現行 Canonical Trip / Pages 路徑 | 狀態 |
| --- | --- | --- | --- | --- |
| `places.id` | 候選 `id` 中的 Google Place ID；穩定地點識別 | 可永久保存 | `candidate_sets`、地點引用；公開 bundle 若發布 | Place ID 單獨保存有明文例外 |
| `places.displayName.text` | `name`；行程顯示與排程 | 未找到快取例外 | Canonical Trip、`/data/site/<id>/index.html`、公開 bundle | 不得當作可永久保存欄位 |
| `places.formattedAddress` | `address`；辨識及導航 | 未找到快取例外 | Canonical Trip、網站 HTML、公開 bundle | 不得當作可永久保存欄位 |
| `places.location.latitude/longitude` | `coordinates`；路線計算與定位 | 最多 30 個連續日，之後必須刪除 | Canonical Trip、路線輸入、網站 HTML、公開 bundle | 目前沒有可證明執行期限刪除的全生命週期清理器 |
| `places.googleMapsUri` | provenance `source_url` / 地圖連結 | 未找到 URI 快取例外；Place ID 可存 | Canonical Trip、網站 HTML、bundle | 改由 Place ID 組成連結，避免持久化 API 回傳 URI |
| `places.websiteUri` | 曾作為 `source_url` fallback | 未找到快取例外 | 若回傳可能進入 Canonical Trip / 公開來源 | 應由該官方網站獨立查核後另記來源 |
| `primaryType`, `types` | `primary_type`、餐廳 `cuisine`；分類與研究排序 | 未找到快取例外 | Canonical Trip、bundle 餐廳 facts | 不得視作永久保存欄位 |
| `regularOpeningHours`, `currentOpeningHours`, `timeZone` | `opening_hours`, `opening_hours_note`；排程及營業狀態 | 未找到 Places 快取例外 | Canonical Trip、HTML、bundle | 不得視作永久保存欄位 |
| `rating`, `userRatingCount` | rating、review count；餐廳排序 | 未找到快取例外 | Canonical Trip、HTML、bundle 餐廳 facts | 不得視作永久保存欄位 |
| `priceLevel`, `businessStatus` | 餐飲價格與營業狀態線索 | 未找到快取例外 | Canonical Trip、bundle 餐廳 facts | 不得視作永久保存欄位 |

應用程式自行給定的 `kind`、`wait_risk`、時長估值與來源信心值不是上述原始 API 欄位；但如果它們是依 Google Places 結果選取或推導出的行程資料，不能僅靠改名或刪 provenance 規避來源限制。需以獨立來源重新建立並保存欄位證據。

## 已確認的儲存與公開路徑

- Production composition 將 Provider candidates 放入 Canonical Trip。
- Orchestrator 將完整 Canonical Trip 寫到設定的 `TRAVEL_PLANNER_TRIPS_DIR/<trip_id>/trip.json`；Railway 掛載為 `/data`。
- Renderer 將 Canonical Trip 內容寫入 `/data/site/<trip_id>/index.html`。
- GitHub Pages publisher 從 Canonical Trip 投影 bundle 和 registry；靜態 bundle 會永久進入 Git repository 歷史，即使之後從目前 branch 移除。
- MCP `get_trip` 會讀取已保存 Canonical Trip 並返回摘要。

因此只加 30 日座標 TTL 仍不夠：其他 Google Places 欄位沒有在目前 storage / renderer / MCP / Pages 全路徑內排除或刪除。

## 既有資料盤點

盤點時間 2026-10-08：

- Git tracked public bundle：`awaji-2026` 有 51 個 place records，其中 14 個 record 的 provenance provider 明確寫 `Google Maps`；其 `name`、`address` 等欄位缺少逐欄位 provenance。source ledger 另有 14 個 `Google Maps` authority 記錄。該標籤不足以證明這批是 Places API 回應，也不足以證明欄位另有獨立來源。
- `wanhua-2026`：19 個 place records，沒有 provider 欄位明確標為 `Google Maps`。
- `kansai-preview-2025`：public bundle 沒有 places 清單。
- Railway volume 不在本機掛載中；MCP 唯讀工具只按明確 `trip_id` 讀摘要，不能列出全部 Canonical Trip。2026-10-08 透過已登入 Railway CLI 的 SSH 在遠端執行唯讀 JSON metadata 盤點，沒有輸出地點名稱、地址、座標或任何憑證值。該盤點目前只確認遠端檔案數與欄位存在數，尚未檢查每個欄位的逐筆來源或保存期限。
- 此次 Railway production inventory：`/data/trips/` 有 1 份 `trip.json`，`/data/site/` 有 1 個 `index.html`；唯一 trip ID 是 `kurashiki-2026-11`。該 Canonical Trip 有 40 個 `places`、20 個 `restaurants`、0 個 `hotels` 候選；60 個候選均標示 `Google Places API (New)` provenance，且均有 `name`、`address`、`coordinates`。其中 20 筆有 `opening_hours`、`rating`、`ratings` 與 `field_provenance`。五天 `days[].items[]` 仍有 0 個 `meal` 項目。此為一次 SSH 時點盤點，不代表已清除、更新或套用保存期限。
- 過往 Git commit 可能仍含目前 bundle 已移除的資料；單純改寫目前 branch 不會清除所有既有 clone、fork、GitHub cache 或歷史物件。

### `awaji-2026` 的 14 筆 Google Maps 標示地點

逐筆比對 `trips/awaji-naruto-tokushima-kobe-2026/trip.json` 的 `candidate_sets.places` 與部署用 `web/public/trips/awaji-2026/public-bundle.json`。以下每筆均有 place-level provenance `provider=Google Maps`，每筆皆沒有 `field_provenance`；所列官方網站欄位只代表有保存該連結，不代表地點名稱、地址、座標或其他欄位已由該網站逐欄重新查證。

| Canonical ID | 顯示名稱 | provider reference | 保存的官方網站連結 | 欄位來源狀態 |
| --- | --- | --- | --- | --- |
| `map-import-pokara-naruto-store` | ポカラ 鳴門店 | `maps-list:entry-01` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-ocean-terrace` | Ocean Terrace | `maps-list:entry-02` | `https://ocean-terrace-awaji.jp/menu/`（圖片來源） | 名稱、地址、座標等無欄位級來源 |
| `map-import-sbrick-warehouse` | S BRICK 旧:鐘紡工場跡 赤レンガ倉庫 | `maps-list:entry-03` | `https://sumoto-brick.jp/about/`（圖片來源） | 名稱、地址、座標等無欄位級來源 |
| `map-import-uzuno-oka` | 絶景レストラン うずの丘 | `maps-list:entry-05` | `https://rest.uzunokuni.com/shop/`（圖片來源） | 名稱、地址、座標等無欄位級來源 |
| `map-import-yumebutai` | 夢舞台 | `maps-list:entry-06` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-naruto-bridge-memorial` | 漩渦之丘 大鳴門橋紀念館 | `maps-list:entry-07` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-poplar-ramen` | 淡路島ラーメン ポプラ | `maps-list:entry-08` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-ohama-park` | Ohama Park | `maps-list:entry-09` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-garb-costa-orange` | Garb Costa Orange | `maps-list:entry-10` | `https://garbcostaorange.jp/`（圖片來源） | 名稱、地址、座標等無欄位級來源 |
| `map-import-taidrobou` | 浮世離れの鯛ドロボー | `maps-list:entry-11` | `https://www.shichicafe.com/taidoroboo/`（圖片來源） | 名稱、地址、座標等無欄位級來源 |
| `map-import-o-awaji` | O AWAJI | `maps-list:entry-12` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-picnic-garden` | Picnic Garden | `maps-list:entry-14` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-keino-beach` | 慶野松原海水浴場 | `maps-list:entry-15` | 無 | 名稱、地址、座標等無欄位級來源 |
| `map-import-awaji-hanasajiki` | Hyogo Prefecture Awaji Hanasajiki | `maps-list:entry-16` | `https://awajihanasajiki.jp/flowering/`（圖片來源） | 名稱、地址、座標等無欄位級來源 |

這 14 筆均被每日行程、路線或地點操作資料引用；尚未逐欄完成獨立來源核查，因此本盤點不將其中任何欄位重標為官方來源，也未刪除或改寫公開資料。逐筆來源重建或移除仍是 #199 的必要處置。

## 本次程式防線與未完成項目

- `trip_to_public_bundle` 現在拒絕 Canonical Trip candidates 或 field-level provenance 中明確含 `Google Places API (New)` 的資料，GitHub Pages publisher 因此不會把這些 provider fields 再寫入新的公開 bundle。
- 本次變更後，地點地圖連結使用 Google 官方提供的 Maps logo；瀏覽器驗收會核對原始 98×18 尺寸及至少 10px 水平、5px 垂直留白。這只改善歸屬標示外觀，並未解決 Canonical Trip 持久化、既有 public bundle 或欄位級來源辨識問題。
- 這個防線不清理已發布的靜態 bundle，也不解決 Railway Canonical Trip 和 renderer HTML 的持久化。因此 #199 仍未完成，不可宣稱 Places 資料生命週期已符合政策。
- 已發布的 Awaji 資料須逐欄位重建獨立來源或移除；不能僅依據 place-level provenance 將資料轉標成官方來源。
- 私有 Railway 行程需先有可列舉、可安全盤點的唯讀稽核方式，才可逐欄位決定保留、重新查證或刪除；不要輸出或記錄任何 credential。
- 若繼續使用 Places API，還需要重新界定規劃流程，使禁止保存／再託管的欄位不進入持久化 Canonical Trip、靜態 HTML、Git Pages、日誌及長期 ChatGPT 摘要，並確保介面仍能合法實現規劃目標。現有 Google Places adapter 是 production 唯一景點發現來源，不能用「加 attribution」宣稱此設計已解決。

自動測試目前只保證 GitHub Pages 動態 publisher 會拒絕新的 Google Places provider provenance；尚未建立 Railway historical-data migration、座標期限刪除或靜態舊 bundle 處置驗證。Issue #199 在這些範圍完備前保持開啟。
