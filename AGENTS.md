# AI Travel Planner 代理開發契約

## 真實來源

1. 每次實作都必須從最新的 `origin/main` 開始。
2. GitHub Issue 的驗收條件，或使用 MR-first 模式時的 MR 描述，加上本文件，都是權威依據。
3. Canonical Trip 仍是產品唯一真實來源。代理協作不得繞過既有的 Research、Planning、Optimization、Validation 與 Rendering 邊界。

## 平行開發邊界

1. 一個工作項目對應一個分支與一個外部 Git worktree。工作項目可以是開啟中的 GitHub Issue，也可以是 MR-first 請求。
2. Issue 分支：`agent/issue-<number>-<slug>`；MR-first 分支：`agent/mr-<slug>`。
3. 標準 worktree：`../.worktrees/ai-travel-planner/issue-<number>-<slug>` 或 `../.worktrees/ai-travel-planner/mr-<slug>`。
4. 只有在宣告的寫入路徑不重疊時，實作代理才能平行執行。
5. 每個可寫路徑只有一個 owner；其他代理對該路徑只能讀取。
6. Review 代理永遠是唯讀，不能修改或核准自己的發現。
7. 不得讓多個實作代理同時修改主要 checkout。
8. 一位整合 owner 透過 GitHub PR 處理跨工作項目依賴；代理不得在 worktree 之間複製尚未合併的變更。

在委派可寫入工作前，使用 repository guard：

```sh
python3 -m scripts.agent.collaboration prepare 28 \
  --slug request-constraints \
  --write-path 'src/intent/**' \
  --write-path 'tests/test_travel_intent.py'
```

MR-first 模式不需要遠端 Issue：

```sh
python3 -m scripts.agent.collaboration prepare \
  --mr-slug request-constraints \
  --write-path 'src/intent/**' \
  --write-path 'tests/test_travel_intent.py'
```

在 commit、push 或 handoff 前：

```sh
python3 -m scripts.agent.collaboration check 28
python3 -m scripts.agent.collaboration handoff 28 \
  --test-evidence 'python3 -m unittest tests.test_travel_intent=PASS'
```

MR-first 模式將 `28` 替換成 `mr:request-constraints`。

## 風險與角色路由

在委派前執行 `python3 -m scripts.agent.collaboration route <changed-path>...`。

1. 低風險：`core.executor`，之後由 `core.code-reviewer` 審查。
2. 中風險：`core.planner`、`core.executor`、`core.test-engineer`，之後由 `core.code-reviewer` 與路由出的 domain reviewer 審查。
3. 高風險：`core.explorer`、`core.architect`、`core.planner`、`core.executor`、`core.test-engineer`，之後由 `core.spec-reviewer`、`core.code-reviewer`、`core.verifier` 與路由出的 domain reviewer 審查。
4. 只要有一個路徑屬於較高風險，整個變更就採用較高風險等級。
5. Domain reviewer 定義於 `agent-collaboration/agents/`，並且是唯讀角色。

## 必要交付流程

除非使用者明確限定只做本地變更或分析：

1. 閱讀 Issue 並確認驗收條件；若使用 MR-first，則必須在開始前於 MR 描述寫清楚 scope、驗收條件、owner、風險、依賴與驗證計畫。
2. 從最新的 `origin/main` 建立專用 worktree。
3. 在啟動實作代理前宣告不重疊的寫入 ownership。
4. 實作最小但完整的變更。
5. 執行 repository validation 與相關測試。
6. 執行 collaboration ownership check。
7. commit 並 push 工作分支。
8. 使用 repository PR template 開啟 regular、非 Draft 的 PR 到 `main`。MR-first 模式必須提供 `--body-file`；MR 描述是權威來源，必須包含完整驗收條件與證據，不需要 Issue reference。
9. 檢查 CI；修正範圍內的 repository、實作、測試、build 或 workflow 失敗，直到綠燈或確認是外部阻塞。
10. 將精確 pushed head SHA、變更檔案、驗收條件與測試證據交給獨立 reviewer。
11. 每次重大修正後重新 review，因為舊 verdict 不涵蓋新 SHA。

如果 push、PR、CI 或 review 仍在範圍內，不得只完成本地實作就停止。除非使用者或 repository policy 明確授權，不得自動 merge。

## 證據要求

Handoff 必須包含：

1. 有 Issue 時提供 Issue 與 PR 編號；沒有 Issue 時提供 MR URL／編號與 MR-first 工作項目 slug。
2. Base 與 head SHA。
3. 宣告的寫入路徑與實際變更檔案。
4. 驗收條件覆蓋情況。
5. 精確的本地測試指令與結果。
6. CI check 結果。
7. 已知警告、尚未驗證的行為與阻塞事項。

「已實作」、「已測試」、「CI 通過」或「已 review」等聲明，都必須有綁定精確 head SHA 的最新證據。

## CI 失敗處理

1. 修改程式前先檢查失敗的 job、step 與 log。
2. 修正範圍內的實作、測試、build、workflow 或 repository 失敗。
3. 沒有證據時，不得把重跑後變綠稱為 flaky test 修正。
4. 只有在確認是權限、憑證、服務或產品決策阻塞時才升級處理。
5. 必要 CI 全部通過後，才能回報工作完成。

## 專案正確性閘門

變更下列區域時，必須由對應的唯讀 reviewer 審查：

1. `src/schemas/**`、`fixtures/trips/**` 或 canonical contract 文件：`domain.trip-schema-reviewer`。
2. `src/planner/**`、`src/optimizer/**`、`src/validator/**`、routing 或 production orchestration：`domain.itinerary-invariant-reviewer`。
3. `src/sources/**`、provider adapter、餐廳證據或 provenance 文件：`domain.source-provenance-auditor`。

不得在 planner logic 使用 provider-specific raw payload，不得把 unknown routing 當成零，不得把未知營業時間視為營業中，不得暴露憑證，也不得把 invalid trip 呈現為成功。

## 旅遊網站可用性閘門

1. 元件存在不等於功能可用。外部網址、官方網站與 Google Maps 路線必須在瀏覽器實際點擊，並確認新頁開啟正確目標；不得只檢查 `href` 存在。
   連結異動後另執行 `cd web && npm run test:links`，直接請求所有公開頁外連；攔截網路的 popup 測試只能驗證開啟行為，不得作為網站可用證據。
2. 電腦版至少驗證 1200、1366、1440 與 1920 畫面像素；手機版至少驗證 375、390 與 430 畫面像素。手機主內容左右至少保留 `16px`，主要卡片內容左右至少保留 `16px`，相鄰主要卡片至少保留 `14px`；同一張主要卡片內的摘要儀表板可使用 `12px` 內距與 `8px` 間距，避免把每個短欄位做成厚重全寬卡。標題、摘要、路線卡、照片與側欄控制不得互相遮蔽、溢出、貼邊或留下版面拉伸造成的空白。
3. 同一資訊在相鄰區塊只顯示一次。住宿摘要與住宿照片、交通目的地停車資訊與下一張景點停車資訊、官方網站文字按鈕與名稱連結不得重複。
4. 景點、餐廳與住宿名稱若有可驗證的直接官方頁面，名稱本身連到官方頁面並保留滑鼠懸停與鍵盤焦點樣式；名稱旁的小型地圖定位圖示只能連到該景點、餐廳或住宿本身，不得改連停車場。沒有直接官方頁面時，名稱保持純文字。
5. 具名停車場的 Google 地圖連結放在「停車」資訊本身；停車文字可點擊，但不得再增加第二個停車按鈕，也不得讓交通卡與下一張目的地卡重複同一停車資訊。
6. Google 地圖路線優先使用資料中已驗證的查詢詞或設施名稱，不得以尚未證明可解析的郵遞地址產生路線。每個分段路線都要實際確認不會顯示「找不到地點」。
7. 「官方未公布」、「未提供」、「未知」、「依當日公告」、「以現場為準」、「只供閱讀」、「不要求填寫」等沒有旅程決策價值或只解釋介面不做什麼的文字不得顯示。已知事實後接未知尾句時，只保留已知事實；整個欄位沒有有用內容時省略欄位。
8. 同列照片卡必須使用相同圖片比例與卡片高度；長標題最多兩行且不得把單字或日期拆成難讀斷行。不得把裝飾框、空白素材或無法辨識景點的圖片當代表照，提交前必須實際檢視圖片內容與桌機、手機截圖。
9. 日期頁籤使用不含前導零的短日期，例如 `D1 8/27`，並保持同一行；不得顯示 `D1 08-27` 或讓天數與日期分行。
10. 收合式導覽的控制位置不得在展開與收合後跳動。瀏覽器測試需比較操作前後座標，不得只檢查 class 是否切換。
11. 淡路島行程的詳細呈現規則以 `trips/awaji-naruto-tokushima-kobe-2026/PRESENTATION_GUIDELINES.md` 為準；修改相關 UI 時同步更新具體瀏覽器驗收。
12. 行動版共用規則集中在 `web/src/responsive.css`；不得在既有樣式檔尾端反覆追加互相覆蓋的媒體查詢規則。修改手機版時，需取得瀏覽器實際計算樣式，並逐頁檢查旅行總覽、五天每日行程、預約時間、餐飲與補給、攜帶物品與實用日文。
13. 本網站假設旅途中可連網，不提供離線快取、離線頁或要求旅客刷新的提示。若舊版 Service Worker 曾註冊，必須靜默解除註冊並刪除舊快取，不得繼續控制新版頁面。

## Framework 完整性

1. `vendor/agentic-dev-collaboration/` 是 pinned upstream snapshot，不得直接修改。
2. 交付前必須驗證 `vendor/agentic-dev-collaboration.lock.json`。
3. 專案覆寫放在 `agent-collaboration/`。
4. collaboration policy 變更後執行 `python3 scripts/validate_agent_collaboration.py`。
