# Frontend runtime architecture

## Scope

The `web/` package has one browser composition root. `src/main.tsx` bootstraps
`TripApp`, and `TripApp` owns the route registry, bundle loading state, shell,
and pages. `src/App.tsx` is intentionally absent; no compatibility root or
feature flag may reintroduce a second production application.

## Runtime layers

1. `main.tsx`: browser bootstrap, stylesheet, and best-effort PWA registration.
2. `app/TripApp.tsx`: route selection, bundle/status state, and page composition.
3. `layouts/`: responsive shell and navigation only.
4. `pages/`: presentation and user-local actions; pages never research,
   reorder, estimate, or mutate Canonical Trip content.
5. `contracts/` and `hooks/`: runtime bundle validation, URL resolution,
   navigation, and trip-scoped local storage.

## Bundle and registry ownership

The registry is the deployment configuration. The loader reads the registry,
selects its canonical entry, and fetches exactly one
`<canonical_url>/public-bundle.json`. It does not probe legacy or guessed
fallback paths. `parseBundle` validates required fields before any page receives
the data; malformed, wrong-shape, or unavailable data remains an explicit shell
state.

## Storage ownership

All user-created data is namespaced as `trip:<trip_id>:<module>:v<schema>` and
stored in a versioned envelope. Legacy keys are migration inputs only and are
validated before migration. Corrupt values are preserved under a `:corrupt`
key and replaced with a safe default. No local value is written back into the
Canonical Trip bundle.

## Route and PWA ownership

Hash routes are parsed and built by `app/route-registry.ts`; deep links and
browser history use the same parser. `main.tsx` owns service-worker
registration, while the worker remains a static deployment asset. The Vite
artifact is built from the minimal `index.html` root and `/src/main.tsx`, so
source architecture and deployed runtime are the same path.

## Migration inventory

| Legacy responsibility | Canonical owner | State |
| --- | --- | --- |
| Bundle loading and recovery | `useBundleLoader` + `parseBundle` | migrated |
| Loading, invalid, critical, offline states | `TripShell` + `TripApp` | migrated |
| Section/day navigation | `route-registry` + `useTripNavigation` | migrated |
| Overview and itinerary | `OverviewPage` + `ItineraryPage` | migrated |
| Maps and copy actions | `MapPage`, itinerary action utilities | migrated |
| Reservations and unresolved status | `ReservationsPage` | migrated |
| Budget, checklist, notes | `BudgetPage`, `PackingPage`, `useTripStorage` | migrated |
| Theme and responsive shell | design-system/theme modules + `TripShell` | migrated |
| Validation and source freshness | `TripShell`, `OverviewPage`, `SourcesPage` | migrated |
| Rich operational hubs | dedicated pages with safe unavailable states | deferred to #69 |
| Screenshot and Lighthouse baselines | release-quality harness | deferred to #73 |
| Generic multi-trip publisher | publishing layer | deferred to #72 |

## Quality gates

The reproducible local gate is:

```sh
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npm --prefix web run test:e2e
```

Unit tests cover bundle rejection, route round trips, URL resolution, and
architecture regressions. E2E starts the production preview artifact and
opens overview, sources, and day routes at a mobile viewport.
