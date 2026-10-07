# 航班與住宿資料來源

## 航班

正式規劃不呼叫機票報價 API，也不擷取或自動操作 Google Flights。Canonical Trip 會提供 `flight_search_url`，連到 Google Flights 搜尋頁，並另列航線與日期摘要供旅客輸入。Google 沒有公開文件說明可預填航班條件的網址格式；自由文字查詢連結曾導向不支援的頁面，因此目前只開啟可用的搜尋頁，不宣稱已預填條件。Google Flights 顯示的票價由外部網站提供、可能變動，不會作為 repo 的候選資料或計入行程預算。

Google Flights Search 整合僅提供給合作夥伴。旅客可直接開啟公開的 Google Flights 網站，不需要本 repo 的 API key。

## 住宿

目前產品不自動搜尋住宿，不需要住宿供應商 API 或住宿憑證。住宿欄位可以留空，由旅客自行安排。`plan_trip` 目前不會把自由文字中的住宿名稱轉成 Canonical Trip 住宿候選；未提供住宿時，起點及每日返回住宿的路線保持未驗證，相關費用不計入預算總額，預算狀態會保留為未完成。

Amadeus Self-Service 與其他自動住宿搜尋目前不屬於產品需求；正式規劃流程不會呼叫這些服務。

## 其他正式環境憑證

景點研究需要 `GOOGLE_MAPS_API_KEY`；自駕／步行路線矩陣需要 `OPENROUTESERVICE_API_KEY`。`YOUTUBE_API_KEY` 為選用，可取得社群影片補充資料。YouTube 每次只送出一個請求，逾時為五秒且不重試。逾時、配額／認證錯誤、回應格式錯誤或缺少 key 會以研究警告回報，不會阻擋核心規劃，也不會令 Research 階段標記為未完成。YouTube 內容只能作為社群資料，不能證明營業等營運事實。供應商 key 應放在後端 secret 環境變數，並於供應商控制台設定限制。

### OpenRouteService 金鑰

1. Create or sign in to an account at [OpenRouteService / HeiGIT](https://openrouteservice.org/log-in/). The sign-in page links to the account used to access the developer dashboard.
2. In the developer dashboard, create a Standard API key. The Standard plan is listed at €0 and has request quotas; this project uses the Matrix endpoint, whose published Standard quota is 500 requests per day and 40 per minute. Review the current [plan limits](https://openrouteservice.org/plans/) and [endpoint restrictions](https://openrouteservice.org/restrictions/) before production use.
3. Copy the generated key and add it to the Railway production service as the secret variable `OPENROUTESERVICE_API_KEY`. Do not add it to GitHub Actions, the repository, source code, or an MCP tool argument. No payment details are needed for the free Standard plan; exceeding its quotas causes API errors and repeated excessive use can result in a temporary block.
4. The Matrix adapter uses the current endpoint `https://api.heigit.org/openrouteservice/v2/matrix`. Existing keys are valid on the new HeiGIT host. Do not use the deprecated `api.openrouteservice.org` host: its shutdown is scheduled for November 2–6, 2026.
5. After Railway deploys the new secret, use a small planning request or a direct Matrix API smoke check to confirm that the key is accepted. Avoid printing the key in shell history or logs.
