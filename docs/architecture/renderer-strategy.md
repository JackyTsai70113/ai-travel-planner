# Renderer strategy

The reusable React trip app is the product renderer and consumes the versioned public bundle. The Python golden_trip_renderer remains a diagnostic and print/fallback renderer for legacy fixtures; it is not a second production publishing flow.

Issue 72 owns the publisher contract and artifact topology. The existing app shell and Pages/PWA workflows retain their ownership boundaries and consume the generated root registry and trips/<slug>/ artifacts during integration.

Per-trip URLs are isolated by slug. A trip's PWA scope and browser storage namespace are derived from trip identity, so one trip cannot overwrite another trip's local state. Shared static assets may be deduplicated by the web build, while bundle and media manifests remain per-trip artifacts.
