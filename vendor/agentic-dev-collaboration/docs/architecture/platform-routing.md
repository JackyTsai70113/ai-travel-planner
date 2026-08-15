# Platform Routing

## Required impact matrix

Every plan must classify each surface as `none`, `compatible`, `changed`, or
`unknown`:

| Surface | Questions |
| --- | --- |
| iOS | Swift/API changes, UI states, storage, permissions, signing, release |
| Android | Kotlin/API changes, UI states, storage, permissions, Gradle, release |
| Backend | API, events, persistence, jobs, infrastructure, rollout |
| Web | Browser behavior, API client, accessibility, bundling, deployment |
| Shared contracts | OpenAPI, GraphQL, protobuf, events, schemas, feature flags |
| Data | Migration, backfill, compatibility window, rollback |
| Observability | Logs, metrics, traces, alerts, privacy |
| Operations | CI, secrets, deployment, staged rollout, rollback |

An `unknown` impact is a planning blocker for production writes.

## Routing rules

### Single-platform change

Use the core team plus one platform engineer. Other platform agents do not need
to participate when shared contracts and behavior remain compatible.

### Shared contract change

1. Architect identifies compatibility and rollout constraints.
2. Contract Reviewer approves the proposed contract.
3. Backend and affected clients plan against the same contract version.
4. Consumer implementations may proceed in parallel only after step 2.
5. Integration Tester validates at least one end-to-end journey.
6. Verifier evaluates the integrated acceptance criteria.

### Cross-platform user journey

The Planner owns a single acceptance map with platform-specific evidence. Each
platform engineer owns only its implementation slice. Integration Tester owns
journey-level validation and must not repair platform defects.

## Mobile-specific concerns

Mobile clients cannot always update with the backend. Plans must define:

- Minimum supported app versions.
- Backward and forward compatibility windows.
- Feature flag and staged rollout behavior.
- Offline and degraded-network behavior.
- Store review or release lead time.
- Migration and rollback behavior.
- Privacy permission changes.

Backend changes must not assume immediate mobile adoption.

## Web-specific concerns

Plans should include browser support, accessibility, responsive behavior,
cache invalidation, client/server rendering boundaries, and observability.

## Backend-specific concerns

Plans should include API compatibility, idempotency, authorization, data
migration, failure recovery, rate limits, observability, and rollback.
