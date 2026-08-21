import { Bundle, ChecklistState, DEFAULT_CHECKLIST, DEFAULT_CHECKLIST as CheckListFallback, safeParseJson } from '../contracts/trip'
import { useEffect, useMemo, useState } from 'react'

const STORAGE_KEYS = {
  checklist: 'golden_trip_checklist',
  notes: 'golden_trip_notes',
}

interface PackingPageProps {
  bundle: Bundle
}

export function PackingPage({ bundle }: PackingPageProps) {
  const [checklist, setChecklist] = useState<ChecklistState>(CheckListFallback)
  const [notes, setNotes] = useState('')

  useEffect(() => {
    setChecklist(safeParseJson(localStorage.getItem(STORAGE_KEYS.checklist), DEFAULT_CHECKLIST))
    setNotes(safeParseJson(localStorage.getItem(STORAGE_KEYS.notes), ''))
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.checklist, JSON.stringify(checklist))
  }, [checklist])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.notes, JSON.stringify(notes))
  }, [notes])

  const checklistProgress = useMemo(() => {
    const total = Object.keys(DEFAULT_CHECKLIST).length
    const done = Object.entries(checklist).filter((entry) => entry[1]).length
    return { total, done, rate: total === 0 ? 0 : Math.round((done / total) * 100) }
  }, [checklist])

  const labelMap: Record<string, string> = {
    passport: '護照/身分文件',
    twn_license: '台灣駕照與國際駕照文件',
    insurance: '汽車險與 rental 文件',
    itinerary_print: '行程頁列印檔',
    cash_change: '零用金與零錢',
    child_supplies: '嬰幼兒用品/奶瓶',
    elder_med: '長輩基本藥物與緊急連絡',
    heat_rain: '防曬與防暑／雨具',
    car_docs: '汽車文件與接送人聯絡方式',
    stroller: '小孩車與輔助用品',
    first_aid: '急救用品',
  }

  return (
    <section className="card" aria-label="行李與備忘">
      <h2>行李與備忘</h2>
      <p>行程：{bundle.title}</p>
      <p className="muted">完成率：{checklistProgress.done}/{checklistProgress.total}（{checklistProgress.rate}%）</p>
      <ul className="checklist">
        {Object.entries(checklist).map(([key, checked]) => (
          <li key={key}>
            <label>
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
              />
              {labelMap[key] || key}
            </label>
          </li>
        ))}
      </ul>
      <label className="budget-note" htmlFor="tripNotes">
        臨時備註
      </label>
      <textarea
        id="tripNotes"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="例如：8/28 前往鳴門前是否遇到塞車，或替代店家安排"
      />
    </section>
  )
}
