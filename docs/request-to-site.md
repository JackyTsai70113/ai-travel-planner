# 從需求到行程網站

`python3 -m src.cli plan-site` 是完整的 production 入口。它只會在研究、規劃、最佳化、驗證都完成並產生 Canonical Trip 後，將該 Trip 投影成 React 網站可讀取的 public bundle，並更新 trip registry。

```sh
python3 -m src.cli plan-site \
  --request '2027/10/20 到 2027/10/22，台北出發名古屋，2 大 1 小，賞楓、自駕、不要太累，預算 8 萬日圓' \
  --trip-id nagoya-autumn-2027 \
  --site-slug nagoya-autumn-2027
```

完整起訖日期、可辨識目的地與成人數是開始 production planning 的必要條件。只有「10 月」或「12 月」不會被任意補成年份或日期；命令會回傳 `needs_details`，不會產生虛構行程。「兩個人」會正確辨識為 2 位成人。

命令需要 README 所列的 provider credentials，並沿用既有 production pipeline。成功後：

1. Canonical Trip 儲存在 `trips/<trip-id>/trip.json`。
2. React 相容 public bundle 儲存在 `web/public/trips/requested/<site-slug>/public-bundle.json`。
3. `web/public/trip-registry.json` 會新增或更新同 slug 的 entry。部署流程透過 `bundle_source_slug` 將其發布到 `/trips/<site-slug>/`。

輸出固定為 `preview`，因為來源、營業時間、票價與可訂狀態都可能隨時間改變。驗證包含 critical error 時 registry readiness 為 `blocked`，不能當成可出發的旅程。
