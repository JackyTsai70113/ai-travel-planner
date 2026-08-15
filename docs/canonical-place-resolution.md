# Canonical place resolution

Canonical Place 是 research observations 與 Trip、routing、renderer 之間的 provider-neutral 邊界。Resolver 不讀取 provider raw payload；adapter 必須先產出 `PlaceObservation`。

## Identity and matching

- `google_place_id`、canonicalized `official_url`、有 provider namespace 的 `provider_reference` 是 stable place identifiers。相同 type/value 形成 deterministic match。
- Resolver 以 observation provenance 的 provider 作為 `provider_reference` namespace；不同 provider 的相同裸 reference 不相等。
- reservation observation 可同時攜帶 `reservation_reference` 與真正的 place identifier，藉此連到既有 Canonical Place。reservation reference 只是 evidence linkage，不是 place identity key；相同 reservation reference 不得合併不同分店。
- 名稱、alias、地址與距離只能作為候選 evidence。name-only observation 的狀態是 `clarification_required`，不得自動合併。
- 連鎖店分店擁有不同 stable identifier，縱使名稱相同也維持不同 Canonical Place。
- 若 shared official URL 或 provider reference 形成的 component 同時包含多個 Google Place IDs，resolver 必須拆開分店並將相關 decision 標為 `clarification_required`；不得以 transitive match 輸出 confidence 1。

## Authority-aware merge

欄位選值依 `official > user_input > provider > derived > community`。所有曾提供該欄位的 provenance 都保存在 `field_provenance`，不因選值而遺失。若同一 identity 有不同 coordinates，最高 authority 的值是主座標，其他值逐筆列入 `coordinate_conflicts`，不得靜默覆寫。

## Navigation boundary

`navigation_points` 是場所下的獨立 routing targets，kind 包含 entrance、parking、station_exit 與 meeting_point。每個 target 至少提供 coordinates、Google Maps URL、phone 或 Mapcode 之一。它們不覆寫 Canonical Place 主座標。

`select_navigation_target(place, purpose)` 提供 routing-ready read model：driving 優先 parking 再 entrance；walking 優先 entrance 再 station exit；meeting 優先 meeting point；找不到適用 navigation point 才退回場所主座標或 navigation reference。Selector 不執行路由、不判定行程可行性。

## Rendering and clarification

Trip schema 的 place 欄位為 additive。Renderer 顯示地址、電話、Google Maps、Mapcode、navigation points，以及 `clarification_required` / `unresolved` 的人工確認訊息。Resolver 不得把 low-confidence match 呈現為 resolved。
