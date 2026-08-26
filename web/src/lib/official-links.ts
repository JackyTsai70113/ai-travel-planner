const VERIFIED_REPLACEMENTS: Record<string, string> = {
  'https://awaji-kanransya.com/': 'https://www.jb-highway.co.jp/sapa/awaji_down.html',
  'https://elb.nijigennomori.com/food/ichiraku/': 'https://nijigennomori.com/food/ichiraku/',
}

/** 將已失效或逾時的舊官方網址導向目前可開啟的官方直達頁。 */
export function usableOfficialHref(value: string | null | undefined): string | undefined {
  if (!value) return undefined
  return VERIFIED_REPLACEMENTS[value] || value
}
