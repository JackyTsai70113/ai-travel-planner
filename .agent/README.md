# Codex 開發入口

本目錄是本儲存庫可提交、可審查的 Codex 輔助開發入口。

## 使用順序

1. 先讀根目錄 `AGENTS.md`，它是本儲存庫的最高優先專案規範。
2. 再讀 `vendor/agentic-dev-collaboration/AGENTS.md` 與 `agent-collaboration/` 下的專案代理設定。
3. 依任務需要讀取 `.agent/skills/` 下的技能說明。
4. 交付前執行 `scripts/validate_agent_collaboration.py` 與任務指定的測試。

## 本次納入的內容

本機頂層設定盤點後，只有可移植的方法文件納入本儲存庫：

- `context-recovery`：中斷或交接後，依持久證據恢復工作狀態。
- `continuous-collaboration`：選擇最小且足夠的實作者、審查者與驗證流程。
- `investigation`：以工具證據回答目前狀態、使用者與呼叫關係問題。
- `planning`：把已核准任務整理成可執行、可驗證的計畫。
- `platform-impact-analysis`：先分類 Web、契約、資料與營運影響，再決定路由。

## 刻意不納入的內容

- 個人 Codex 身分、帳號、認證、工作階段、資料庫與全域狀態。
- 本機執行期快照與工作階段紀錄。
- 依賴個人絕對路徑的全域攔截器或技能同步設定。
- 儲存庫已經以固定版本快照管理的代理定義與技能副本。

這些內容不是產品原始碼，也不應隨儲存庫複製或公開。
