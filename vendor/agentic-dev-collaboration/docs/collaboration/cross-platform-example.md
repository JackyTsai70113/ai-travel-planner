# Cross-platform Example: Evolving a Session Contract

This example illustrates the ordering for a backend contract consumed by iOS,
Android, and web clients.

## Impact

```yaml
ios: changed
android: changed
backend: changed
web: changed
shared_contracts: changed
data: none
observability: changed
operations: compatible
```

## Safe execution order

1. Explorer inventories released clients and existing contract usage.
2. Architect defines the compatibility window and rollout strategy.
3. Planner creates one acceptance map and separate path-owned platform tasks.
4. Contract Reviewer approves optionality, defaults, deprecation, and versioning.
5. Backend Engineer implements backward-compatible producer behavior.
6. Platform engineers implement clients in isolated worktrees.
7. Test Engineer adds producer, consumer, and negative-path tests.
8. Integration Tester validates old and new clients against the compatible
   backend and runs one end-to-end journey.
9. Spec Reviewer checks every platform and compatibility requirement.
10. Code and Security Reviewers evaluate the integrated change.
11. Verifier maps fresh evidence to all acceptance criteria.

## Parallelism

iOS, Android, and web implementation may run in parallel only after the shared
contract is approved. Backend work may overlap if the compatibility behavior is
fixed and contract tests are available.

## Release separation

Implementation completion does not imply release. Store submission, production
deployment, feature enablement, and deprecation remain separate,
human-authorized operations.
