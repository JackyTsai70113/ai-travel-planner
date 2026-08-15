# 可持續迭代的多 Agent 開發協作框架

本 repository 提供一套不綁定特定 AI 廠商的協作規格，可套用在 iOS、
Android、Backend 與 Web 專案。

## 核心原則

- 永久核心團隊保持精簡，平台專家依影響範圍載入。
- Architect、Reviewer 與 Verifier 預設唯讀。
- Developer 不得審查自己的實作。
- Tester 負責測試設計與測試程式，不替 Developer 偷改功能。
- Verifier 不相信「已完成」摘要，必須取得新的指令輸出與驗收證據。
- Agent 之間傳遞結構化摘要、風險、證據與判定，不交換隱藏推理過程。
- 規則若能以 Schema、程式、Git hook 或 CI 強制，就不只寫在 prompt。

## 跨平台調整

不建立四組永久團隊，而是分成兩層：

1. 共用核心角色：
   Orchestrator、Explorer、Architect、Planner、Executor、Test Engineer、
   Spec Reviewer、Code Reviewer、Verifier、Security Reviewer。
2. 按需平台角色：
   iOS Engineer、Android Engineer、Backend Engineer、Web Engineer、
   Contract Reviewer、Integration Tester。

每個需求先完成 platform impact matrix。只有受影響的平台 specialist
會收到任務。如果 API、事件格式、資料 schema 或驗證規則改變，必須先由
Contract Reviewer 檢查，再由所有受影響平台分別實作與驗證。

## AI 中立格式

- 專案說明：`AGENTS.md`
- Agent 定義：`*.agent.yaml`
- Skill：Agent Skills 相容的 `SKILL.md`
- 架構決策：MADR 風格 Markdown
- 任務、發現與判定：YAML，加上 JSON Schema
- 自動化閘門：可攜式腳本、Git hooks 與 CI
- 廠商差異：只放在非 canonical 的 `adapters/`

Canonical 文件不包含模型名稱、專有工具名稱或特定 CLI 指令。

## 建議導入順序

1. 先使用唯讀的 Explorer、Architect、Planner、Reviewer、Verifier。
2. 確認 schema 與 CI 能攔截錯誤後，再開放 Executor 寫入。
3. 先在一個中型功能上試行完整流程。
4. 量測返工率、真正缺陷、token／時間成本與人類介入點。
5. 只把經驗證有效的 lessons 納入下一版流程。
