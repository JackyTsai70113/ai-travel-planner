# Trip Media Policy

## Approved sources

1. Repository-owned photographs with confirmed permission.
2. Wikimedia Commons assets whose individual file license is recorded.
3. Unsplash or Pexels assets only when the current terms permit the intended use and the source page is retained.
4. Official media kits that explicitly grant reuse rights.
5. Self-created SVG, gradients, geometry, route illustrations, and icons.

## Prohibited sources

Google Maps or business-profile photos, search-result image copies, unknown hotel/restaurant/blog images, and external original-file hotlinks as the only production copy are prohibited. A source URL is evidence, not a replacement for a checked-in or approved asset.

## Add an asset

1. Copy the approved source into the trip media directory.
2. Add a stable kebab-case ID, descriptive Traditional Chinese or English alt text, attribution ID, exact license, creator, visibility, and source page to `site-media.json`.
3. Run `python3 scripts/validate_media_attributions.py <manifest>`.
4. Run `python3 scripts/build_trip_media.py <manifest> --output <output-directory>` and commit only approved public derivatives and the generated manifest.

The builder hashes source bytes, records dimensions and aspect ratio, and stages output atomically. Private paths never enter a public manifest. Codec-specific WebP/AVIF encoders are an explicit build adapter; a build must not label a fallback file as WebP or AVIF unless that encoder produced it.
