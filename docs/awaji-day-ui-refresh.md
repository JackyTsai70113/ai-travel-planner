# Awaji day UI refresh

Issue #89 的正式頁面改採 ai_kyushu 的資訊階層：深色 desktop sidebar、白色 top bar、sticky day selector、單一日摘要 hero，以及可在現場掃讀的垂直 itinerary timeline。視覺保留淡路島的海藍與青綠，而不是複製九州內容或假造旅行資料。

每一個停靠點都直接由 Canonical public bundle 的 date、place、notes、status 與 operational unknown 驅動。固定預約仍以 amber warning 顯示，未解析的地址、duration 與狀態不會被渲染成 confirmed。

仍未實作：完整五日的 prototype-specific hero 文案、地圖 API、reservation write workflow，及外部 photo media。這次變更只改善正式 TripApp 的可讀性與資訊層級，不改動 Canonical Trip 或 production data source。
