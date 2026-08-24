## 變更摘要

### 一句話摘要


### Issue / MR-first task 與 acceptance criteria

- Issue：`#`（沒有 Issue 時填 `MR-first`）
- [ ] 已在本 MR 寫清楚背景、scope、acceptance criteria、write ownership、風險、依賴與 validation
- [ ] 已逐項驗證 Issue acceptance criteria，或 MR-first acceptance criteria

### Agent workspace

- Branch：`agent/issue-<number>-<slug>` 或 `agent/mr-<slug>`
- Worktree：對應的 `../.worktrees/ai-travel-planner/` worktree
- Declared write ownership：
- [ ] `python3 -m scripts.agent.collaboration check <issue-or-mr:slug>` 通過
- [ ] Actual changed files 全部位於 declared write ownership

### 風險與角色

- Risk：`low` / `medium` / `high`
- Implementation roles：
- Independent review roles：
- Domain reviewers：

### Exact evidence

- Base SHA：
- Exact head SHA：
- Local test commands and results：
- [ ] Handoff evidence 綁定目前 pushed exact head SHA
- [ ] PR 是 regular non-Draft 狀態
- [ ] 沒有未解決的 blocking finding

### Project correctness gates

- [ ] Canonical Trip 仍是唯一 source of truth
- [ ] Provider raw payload 未進入 planner/canonical model
- [ ] Unknown route 未視為 0 分鐘
- [ ] Unknown opening hours 未視為營業
- [ ] Deterministic validator 仍是 final correctness gate
- [ ] API credential 未出現在 log、Trip JSON 或 rendered HTML

### CI

- [ ] `framework`
- [ ] `python`
- [ ] `website`

### Merge boundary

- [ ] 本 PR 不使用自動 merge；由使用者或已授權流程決定合併
