export interface JapanesePhrase {
  id: string
  category: string
  japanese: string
  kana?: string
  romaji?: string
  traditionalChinese: string
  usageNote?: string
  sourceType: 'curated' | 'trip_specific'
}

export const JAPANESE_PHRASES: JapanesePhrase[] = [
  { id: 'seats', category: '餐廳', japanese: '大人六名と子供一名です。', kana: 'おとな ろくめい と こども いちめい です。', romaji: 'Otona roku-mei to kodomo ichi-mei desu.', traditionalChinese: '六位大人、一位幼兒。', usageNote: '訂位或候位時使用', sourceType: 'curated' },
  { id: 'child-seat', category: '餐廳', japanese: '子供用の椅子と食器はありますか？', kana: 'こどもよう の いす と しょっき は ありますか？', romaji: 'Kodomo-yō no isu to shokki wa arimasu ka?', traditionalChinese: '有兒童椅和兒童餐具嗎？', sourceType: 'curated' },
  { id: 'reservation', category: '住宿餐廳', japanese: '予約を確認していただけますか？', kana: 'よやく を かくにん して いただけますか？', romaji: 'Yoyaku o kakunin shite itadakemasu ka?', traditionalChinese: '可以幫忙確認預約嗎？', sourceType: 'curated' },
  { id: 'allergy', category: '餐廳', japanese: 'この食材が食べられません。', kana: 'この しょくざい が たべられません。', romaji: 'Kono shokuzai ga taberaremasen.', traditionalChinese: '不能吃這種食材。', usageNote: '請再向店家確認可提供的餐點', sourceType: 'curated' },
  { id: 'parking', category: '自駕', japanese: '駐車場の入口はどこですか？', kana: 'ちゅうしゃじょう の いりぐち は どこですか？', romaji: 'Chūshajō no iriguchi wa doko desu ka?', traditionalChinese: '停車場入口在哪裡？', sourceType: 'curated' },
  { id: 'hotel', category: '住宿', japanese: '荷物を預けてもいいですか？', kana: 'にもつ を あずけても いいですか？', romaji: 'Nimotsu o azuketemo ii desu ka?', traditionalChinese: '可以寄放行李嗎？', sourceType: 'curated' },
  { id: 'fuel', category: '自駕', japanese: '満タンでお願いします。', kana: 'まんたん で おねがいします。', romaji: 'Mantan de onegai shimasu.', traditionalChinese: '請加滿油。', sourceType: 'curated' },
  { id: 'cancelled', category: '船班', japanese: '船は欠航ですか？', kana: 'ふね は けっこう ですか？', romaji: 'Fune wa kekkō desu ka?', traditionalChinese: '船班停航了嗎？', sourceType: 'curated' },
  { id: 'hospital', category: '緊急', japanese: '病院に行きたいです。救急車を呼んでください。', kana: 'びょういん に いきたい です。きゅうきゅうしゃ を よんで ください。', romaji: 'Byōin ni ikitai desu. Kyūkyūsha o yonde kudasai.', traditionalChinese: '我需要去醫院，請叫救護車。', usageNote: '嚴重或緊急狀況請撥 119', sourceType: 'curated' },
]
