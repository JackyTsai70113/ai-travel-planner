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

## Framework 完整性

1. `vendor/agentic-dev-collaboration/` 是 pinned upstream snapshot，不得直接修改。
2. 交付前必須驗證 `vendor/agentic-dev-collaboration.lock.json`。
3. 專案覆寫放在 `agent-collaboration/`。
4. collaboration policy 變更後執行 `python3 scripts/validate_agent_collaboration.py`。
