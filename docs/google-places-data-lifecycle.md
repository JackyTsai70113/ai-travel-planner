# Google Places 資料生命週期盤點

最後核對：2026-10-08。這份文件記錄程式實際保存路徑與已查閱的 Google 官方文件，不作法律合規結論。

## 新版資料處理規則（PR #199）

- Google Places 搜尋結果只在單次規劃請求記憶體中供候選篩選、營業時間與路線排程使用；寫入 Canonical Trip 與靜態 HTML 前，會移除 Google Places 衍生欄位與 Google 回傳的 source URL。
- Canonical Trip 可保留 Google API 的原始 `id` 欄位（以 `google_place_id` 保存不含 `places/` 前綴的 ID），另保留使用者自己的行程安排、備註、選擇及其他非 Google 來源且有欄位級 provenance 的資料。查詢 Place Details 時才包成 `places/{place_id}` resource name。
- `get_place_details(place_id)` 每次呼叫均向 Places API 即時查詢，資料僅回傳當次 MCP 結果；不使用快取。工具失敗會回 `unavailable`、失敗類別及是否可重試，不回傳舊資料，也不把 Google 回應寫入日誌或行程。
- MCP 即時結果標示 `Google Maps`，並附上 API 回傳的第三方 attribution。靜態網頁若只有 Place ID，顯示 Google Maps 連結，不呈現 API 的名稱、地址、座標、營業時間、評分等詳細資料。
- 新版程式的 Places 詳細資料保存期限為 0 天；Places 座標不會持久保存。官方一般條款允許座標快取最多 30 個連續日，但本實作選擇不快取。Place ID 依政策例外可永久保存。
- 已存在於 Railway volume、已發布的 Pages bundle 與 Git 歷史中的舊資料均未刪除、改寫或回填。本變更只管束合併後新產生的 Canonical Trip、HTML 與公開 bundle。舊行程若仍含 Places 詳細欄位，發布器會繼續拒絕再次發布這些資料；現有歷史檔案和已公開頁面保持原樣。
- 不同來源重整後的欄位只有具備非 Google 欄位級 provenance 才能留存；沒有欄位級證據時，Places 標記候選只保留 Place ID、kind 與來源識別 metadata。

自動回歸測試涵蓋：原樣保存 Place ID、規劃與渲染投影移除 Places 詳細欄位、保留非 Google 欄位級 provenance、ID-only Google candidate 可投影為公開 bundle、舊 bundle 中仍含 Google 詳細欄位時發布受阻、即時查詢使用 GET 且不寫入資料、attribution 回傳，以及 API 錯誤不回退舊資料。

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
| `places.id` | `google_place_id`；穩定地點識別 | 可永久保存 | 新版 Canonical Trip、地點引用；公開 bundle 若發布 | 新版單獨保存原始 Place ID |
| `places.displayName.text` | `name`；行程顯示與排程 | 未找到快取例外 | 單次規劃請求記憶體 | 新版落盤前移除；顯示時重新查詢 |
| `places.formattedAddress` | `address`；辨識及導航 | 未找到快取例外 | 單次規劃請求記憶體 | 新版落盤前移除；顯示時重新查詢 |
| `places.location.latitude/longitude` | `coordinates`；路線計算與定位 | 最多 30 個連續日，之後必須刪除 | 單次規劃請求記憶體及路線輸入 | 新版請求結束即丟棄，持久化期限 0 天 |
| `places.googleMapsUri` | provenance `source_url` / 地圖連結 | 未找到 URI 快取例外；Place ID 可存 | 單次規劃請求記憶體 | 新版不保存回傳 URI；連結由原始 Place ID 即時組成 |
| `places.websiteUri` | 曾作為 `source_url` fallback | 未找到快取例外 | 若回傳可能進入 Canonical Trip / 公開來源 | 應由該官方網站獨立查核後另記來源 |
| `primaryType`, `types` | `primary_type`、餐廳 `cuisine`；分類與研究排序 | 未找到快取例外 | Canonical Trip、bundle 餐廳 facts | 不得視作永久保存欄位 |
| `regularOpeningHours`, `currentOpeningHours`, `timeZone` | `opening_hours`, `opening_hours_note`；排程及營業狀態 | 未找到 Places 快取例外 | Canonical Trip、HTML、bundle | 不得視作永久保存欄位 |
| `rating`, `userRatingCount` | rating、review count；餐廳排序 | 未找到快取例外 | Canonical Trip、HTML、bundle 餐廳 facts | 不得視作永久保存欄位 |
| `priceLevel`, `businessStatus` | 餐飲價格與營業狀態線索 | 未找到快取例外 | Canonical Trip、bundle 餐廳 facts | 不得視作永久保存欄位 |

應用程式自行給定的 `kind`、`wait_risk`、時長估值與來源信心值不是上述原始 API 欄位；但如果它們是依 Google Places 結果選取或推導出的行程資料，不能僅靠改名或刪 provenance 規避來源限制。需以獨立來源重新建立並保存欄位證據。

## 已確認的儲存與公開路徑

以下清單記錄本次程式變更前的資料流快照；合併後的新寫入與查詢以後面的「新版資料處理規則」為準。歷史檔案本身不因程式升級自動重寫。

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

這 14 筆均被每日行程、路線或地點操作資料引用；尚未逐欄完成獨立來源核查，因此本盤點不將其中任何欄位重標為官方來源。依維護者要求，這些歷史公開資料不刪除、不改寫。

## 程式防線與歷史資料保留範圍

- PR #235 合併後，Canonical Trip 的新寫入、`get_trip` 回應、靜態 HTML 與 GitHub Pages publisher 都先套用 `durable_trip` 投影；Google Places 詳細欄位會被移除，Place ID 和自有行程／筆記保留。直接呼叫 `trip_to_public_bundle` 並傳入仍帶 Places 詳細欄位的未投影文件會拒絕，避免繞過 publisher 邊界。
- 公開行程的 Google Maps 連結使用 Google 官方 logo；已用瀏覽器驗收原始 98×18 尺寸及至少 10px 水平、5px 垂直留白。MCP 即時詳細資料回應附 `Google Maps` 與 API 提供的第三方 attribution。
- 歷史 Railway 檔案、歷史靜態 HTML、已發布 bundle 與 Git commit 均未刪除或改寫，並依維護者指示繼續保留。舊公開頁面仍可能包含合併前保存的 Places 詳細欄位；這是明確保留的歷史狀態，不宣稱舊內容已被移除。
- 新建立資料的 Places 詳細欄位保存期限為 0 天，沒有快取或排程刪除工作；要重新呈現 Google 詳細資料時，必須依原始 Place ID 即時查詢並附 attribution。座標不落盤，因此不需啟動 30 日座標清除流程。
- ChatGPT 規劃在需要 Places 名稱、地址或營業資料時，應以保存的原始 Place ID 呼叫 `get_place_details`，並附上回傳的 Google Maps 與第三方 attribution；查詢失敗時回報資料不可用，不讀取舊欄位或自行猜值。

自動回歸測試涵蓋新 Canonical Trip 的安全投影、原樣保存 Place ID、保留使用者自有行程與筆記、Places 詳細資料不進入新 HTML／公開 bundle、發布器拒絕帶有 Google Places 詳細資料的行程、即時查詢的署名與第三方 attribution，以及查詢失敗時不使用舊資料。Places 詳細資料 TTL 為 0 天，30 日座標期限不適用於本實作的永久儲存，因座標不落盤。

舊 Railway 檔案、現有公開 Pages 內容及 Git 歷史保持原樣。若未來要改變這項歷史保留狀態，需另行提出明確範圍與處置指示。

## 2026-10-08 OpenRouteService POI 替代來源唯讀試查

HeiGIT 官方 API 文件列有 OpenPOIService，路徑為 `https://api.heigit.org/openpoiservice/v0/pois`，資料由 OpenStreetMap 衍生；官方文件另列 POI 面積與搜尋半徑限制。既有 `OPENROUTESERVICE_API_KEY` 已以 production matrix 單次請求確認可用於 `api.heigit.org`，但這不代表 POI endpoint 已能提供所需資料。

使用 Railway production 注入的既有 key，對 OpenPOIService 執行四次唯讀試查：倉敷中心附近一次、HeiGIT 文件範例座標附近三次（含不同分類篩選、帶 bbox 與不帶 bbox）。四次均回 HTTP 200 `FeatureCollection`，但 `features` 都是空陣列；只記錄狀態與筆數，沒有輸出或保存地點內容，也沒有修改行程資料。這是有限的 endpoint/schema/coverage 試查，不足以證明整個服務無資料；目前不能把 OpenPOIService 宣稱為可用的 Google Places 替代來源。

官方參考：

- [HeiGIT OpenPOIService API 文件](https://giscience.github.io/openrouteservice/api-reference/endpoints/poi/)
- [OpenRouteService 網域遷移公告](https://ask.openrouteservice.org/t/deprecating-api-openrouteservice-org-in-favour-of-api-heigit-org/7912)
- [OpenRouteService 服務條款與資料來源／歸屬說明](https://ask.openrouteservice.org/tos)
- [OpenStreetMap 著作權與 ODbL 說明](https://www.openstreetmap.org/copyright)

若後續評估其他來源，仍須逐欄確認來源、署名、公開頁呈現及資料生命週期；本次實作維持 Google Places，不引入 OSM。#199 已由 PR #239 完成新資料生命週期防線並結案；歷史資料依維護者指示保留，不代表歷史資料已清理或重新核驗。
