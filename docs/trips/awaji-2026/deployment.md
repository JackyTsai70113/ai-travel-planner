# Deployment 目錄（awaji-2026）

- 本地驗證輸出：`python3 scripts/build_awaji_public_bundle.py --trip-path trips/awaji-naruto-tokushima-kobe-2026/trip.json --output trips/awaji-naruto-tokushima-kobe-2026/public-bundle.json`
- 後續若建置 React PWA，預期輸出可直接對應為 offline 首屏基礎資料。
- 上線前需完成 contamination 掃描：`python3 scripts/check-awaji-contamination.py`。
- PWA 在既有 gh-pages 路徑下輸出：`/trips/awaji-2026/`
