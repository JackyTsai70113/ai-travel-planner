---
spec_id: CHANGE-NNN
status: draft
created_at: YYYY-MM-DD
---

# Test Plan

## Risk model

List the highest-impact failures and why the selected tests address them.

## Test matrix

| Acceptance ID | Level | Platform/environment | Scenario | Expected result | Owner |
| --- | --- | --- | --- | --- | --- |
| AC-01 | unit/integration/e2e/manual | environment | scenario | result | role |

## Compatibility coverage

Include released mobile clients, supported browsers, API versions, data
migrations, and partial rollout where applicable.

## Negative and degraded paths

- Invalid input.
- Missing authorization.
- Network failure.
- Partial deployment.
- Retry or duplicate delivery.
- Offline or stale client.

## Environment and fixtures

Document required devices, simulators, services, data, clocks, and cleanup.

## Evidence locations

Define where fresh command output, screenshots, traces, and reports are stored.

## Known gaps

List unavailable environments or behavior that will remain unproven.
