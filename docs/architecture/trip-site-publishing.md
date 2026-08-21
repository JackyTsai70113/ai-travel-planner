# Trip Site Publishing Pipeline

Issue 72 establishes one offline publishing flow for Japan trip websites.

Canonical Trip is the only itinerary source of truth. The publisher performs no research, planning, routing, or repair. It validates the input, projects an allowlisted public bundle, and attaches site configuration, theme/media references, and build metadata.

Commands:

    python3 scripts/build_trip_site.py --trip trips/<trip-id>/trip.json --site-config site-configs/<trip>/site.json --output site
    python3 scripts/build_all_trip_sites.py --configs site-configs --output site
    python3 scripts/init_trip_site.py --trip-id hokkaido-2027 --slug hokkaido-2027 --theme snow-hokkaido

Each trip output contains index.html, public-bundle.json, site.json, site-media.json, and build-report.json. Build-all also emits registry.json and a root index artifact. The registry is generated from valid site configs; React does not hardcode trip entries.

Publication semantics are explicit. Preview builds can expose incomplete data with an incomplete readiness value. A published build with a critical validation error is blocked. Unknown source facts remain unknown; the publisher never fills them with guessed precision.

The bundle excludes provider payloads, credentials, private booking fields, and absolute source paths. Its schema version is trip-public-bundle-v1. Config, media, registry, and build reports have independent version markers.

Builds use recorded JSON only. No provider call is made by the publisher. Input, config, media, bundle, theme, and publisher versions are recorded in build-report.json for release gates and reproducibility checks.
