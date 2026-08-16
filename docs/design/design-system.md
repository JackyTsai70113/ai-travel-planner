# Golden Trip Design System

## Scope (Issue 64)

這個 issue 建立可重用的前端基礎資產，目標是讓多個日本行程網站共享一組 design token、主題 contract 與 primitive。

## 目錄

1. Design tokens
2. Trip theme contract
3. Primitive components
4. Theme fixtures
5. 使用方式（未來接軌）

## 1. Design tokens

新增 `web/src/design-system/tokens.ts`，定義可被主題接管的語意欄位：

- color roles
- destination roles
- typography scale
- spacing / radius / elevation / focus
- status tones
- motion 與 print 行為

`StatusTone` 與 `DestinationRole` 目前先以 type-safe 的 union 管理，後續可直接映射到 tailwind tokens 或 css variables。

## 2. Trip theme contract

新增 `web/src/design-system/theme.ts`：

- `TripTheme`
  - id、displayName、description
  - brand palette + destination role
  - hero 視覺線索
  - map/route accent
  - tokens alias
- `validateTripThemeContract(value)`：最小 runtime 驗證
- `coerceTheme(source, fallback)`：在資料不齊全時回退安全主題
- `coerceStatusTone(value, aliases)`：將 legacy 狀態字串映射到 design status tone

## 3. Primitives

建立 `web/src/design-system/primitives/StatusBadge.tsx`，作為 status 語意最小實作，預留 `aria` 與 tone 映射。

後續 issue 可在此目錄擴充：

- Button, Card, Alert, Tab, SearchField 等

## 4. Theme fixtures

新增兩個可直接套用的主題檔：

- `web/src/themes/generic-japan.ts`
- `web/src/themes/setouchi-awaji.ts`

並保留 fallback

- `web/src/themes/fallback-japan.ts`

## 5. 接下來

建議下一步在 `web/src/App.tsx` 與 `web/src/styles.css` 逐步接軌這個 contract：

1. 從 `trips/*/public-bundle.json` 讀取 `meta.theme_id`
2. 把 theme metadata 注入 page class/inline tokens
3. 將原本散落的 class strings 轉換為 primitive + token class
