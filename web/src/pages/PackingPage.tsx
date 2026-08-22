import { useMemo, useState } from 'react'
import { Bundle, BundlePretripChecklistItem, DEFAULT_CHECKLIST } from '../contracts/trip'
import { useTripStorage } from '../hooks/useTripStorage'

interface Note {
  id: string
  title: string
  content: string
  updatedAt: string
}

const EMPTY_KEYS: string[] = []
const EMPTY_NOTES: Note[] = []
const LEGACY_NOTE_KEYS = ['golden_trip_notes']

const fallbackLabels: Record<string, string> = {
  passport: '護照／身分文件',
  twn_license: '台灣駕照與國際駕照',
  insurance: '保險與租車文件',
  itinerary_print: '行程離線檔',
  cash_change: '零用金與零錢',
  child_supplies: '幼兒用品',
  elder_med: '長輩常用藥',
  heat_rain: '防曬、防暑與雨具',
  car_docs: '汽車文件',
  stroller: '推車',
  first_aid: '急救用品',
}

const validChecklist = (value: unknown): value is Record<string, boolean> =>
  typeof value === 'object' &&
  value !== null &&
  !Array.isArray(value) &&
  Object.values(value).every((item) => typeof item === 'boolean')

const validNotes = (value: unknown): value is Note[] =>
  Array.isArray(value) &&
  value.every((item) => item && typeof item.id === 'string' && typeof item.title === 'string' && typeof item.content === 'string')

function parseLegacyNotes(raw: string): Note[] | null {
  try {
    const value = JSON.parse(raw)
    return typeof value === 'string' ? [{ id: `${Date.now()}`, title: '舊版備忘', content: value, updatedAt: new Date().toISOString() }] : null
  } catch {
    return null
  }
}

function genericChecklist(): BundlePretripChecklistItem[] {
  return Object.keys(DEFAULT_CHECKLIST).map((id) => ({
    id,
    timing: '通用行李',
    item: fallbackLabels[id] || id,
  }))
}

function isUrl(value: string) {
  return /^https?:\/\//i.test(value)
}

export function PackingPage({ bundle }: { bundle: Bundle }) {
  const items = useMemo(() => {
    const bundleItems = bundle.operations?.pretrip_checklist?.filter((item) => item.id && item.item) || []
    return bundleItems.length ? bundleItems : genericChecklist()
  }, [bundle.operations?.pretrip_checklist])
  const usesBundleChecklist = (bundle.operations?.pretrip_checklist?.length || 0) > 0
  const initialState = useMemo<Record<string, boolean>>(
    () => Object.fromEntries(items.map((item) => [item.id, false])),
    [items],
  )
  const checklist = useTripStorage({
    tripId: bundle.trip_id,
    module: 'checklist',
    schemaVersion: 2,
    fallback: initialState,
    validate: validChecklist,
    legacyKeys: EMPTY_KEYS,
  })
  const notes = useTripStorage({
    tripId: bundle.trip_id,
    module: 'notes',
    schemaVersion: 1,
    fallback: EMPTY_NOTES,
    validate: validNotes,
    legacyKeys: LEGACY_NOTE_KEYS,
    legacyParser: parseLegacyNotes,
  })
  const [draft, setDraft] = useState<Note>({ id: '', title: '', content: '', updatedAt: '' })

  const grouped = useMemo(() => {
    const groups = new Map<string, BundlePretripChecklistItem[]>()
    items.forEach((item) => {
      const phase = item.timing || '出發前'
      groups.set(phase, [...(groups.get(phase) || []), item])
    })
    return [...groups.entries()]
  }, [items])

  const completedCount = items.filter((item) => checklist.value[item.id]).length
  const percentage = items.length ? Math.round(completedCount / items.length * 100) : 0

  const saveNote = () => {
    if (!draft.title.trim() && !draft.content.trim()) return
    const item = {
      ...draft,
      id: draft.id || `${Date.now()}`,
      title: draft.title.trim() || '未命名備忘',
      content: draft.content.trim(),
      updatedAt: new Date().toISOString(),
    }
    notes.setValue(draft.id ? notes.value.map((note) => note.id === draft.id ? item : note) : [item, ...notes.value])
    setDraft({ id: '', title: '', content: '', updatedAt: '' })
  }

  return (
    <section className="packing-workspace" aria-label="出發前清單與備忘">
      <header className="page-intro">
        <div><p className="eyebrow">PRE-TRIP CHECK</p><h1>出發前確認清單</h1><p>{usesBundleChecklist ? '依 Canonical Trip 內的試算表清單逐項確認，勾選結果只保存在此瀏覽器。' : 'Canonical Trip 尚無專屬清單，目前顯示通用備品。勾選結果只保存在此瀏覽器。'}</p></div>
        <div className="checklist-progress" aria-label={`清單完成 ${percentage}%`}><strong>{percentage}%</strong><span>{completedCount} / {items.length} 完成</span></div>
      </header>

      <div className="progress-track" aria-hidden="true"><span style={{ width: `${percentage}%` }} /></div>

      <div className="packing-toolbar">
        <span className={usesBundleChecklist ? 'source-chip canonical' : 'source-chip fallback'}>{usesBundleChecklist ? '試算表清單已載入' : '通用 fallback'}</span>
        <button type="button" className="secondary-button" onClick={() => checklist.reset(initialState)}>全部重設</button>
        {checklist.warning || checklist.saveError || notes.warning || notes.saveError ? <span role="status" className="warning-text">{checklist.warning || checklist.saveError || notes.warning || notes.saveError}</span> : null}
      </div>

      <div className="checklist-groups">
        {grouped.map(([phase, phaseItems]) => (
          <section className="checklist-group" key={phase}>
            <header><span>{phase}</span><small>{phaseItems.filter((item) => checklist.value[item.id]).length}/{phaseItems.length}</small></header>
            <ul>
              {phaseItems.map((item) => {
                const checked = checklist.value[item.id] || false
                return (
                  <li className={checked ? 'is-checked' : ''} key={item.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => checklist.setValue({ ...checklist.value, [item.id]: event.target.checked })}
                      />
                      <span className="custom-checkbox" aria-hidden="true">✓</span>
                      <span className="checklist-copy"><strong>{item.item}</strong>{item.action ? <p><b>要做：</b>{item.action}</p> : null}{item.fallback ? <p className="fallback-note"><b>未完成時：</b>{item.fallback}</p> : null}</span>
                    </label>
                    {item.contact ? isUrl(item.contact) ? <a href={item.contact} target="_blank" rel="noreferrer">參考連結</a> : <span className="reference-note">聯絡／參考：{item.contact}</span> : null}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>

      <section className="notes-workspace">
        <div className="section-heading"><div><p className="eyebrow">LOCAL NOTES</p><h2>旅途中備忘</h2></div><span>僅此裝置</span></div>
        <div className="note-editor">
          <input aria-label="備忘標題" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="標題，例如：住宿晚到通知" />
          <textarea aria-label="備忘內容" value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} placeholder="寫下現場才需要知道的資訊" />
          <div className="action-row"><button type="button" onClick={saveNote}>{draft.id ? '更新備忘' : '新增備忘'}</button>{draft.id ? <button type="button" className="secondary-button" onClick={() => setDraft({ id: '', title: '', content: '', updatedAt: '' })}>取消</button> : null}</div>
        </div>
        <div className="note-list">
          {notes.value.map((note) => <article className="note-card" key={note.id}><div><h3>{note.title}</h3><small>{note.updatedAt.slice(0, 16).replace('T', ' ')}</small></div><p>{note.content}</p><div className="action-row"><button type="button" className="secondary-button" onClick={() => setDraft(note)}>編輯</button><button type="button" className="danger-button" onClick={() => notes.setValue(notes.value.filter((item) => item.id !== note.id))}>刪除</button></div></article>)}
          {notes.value.length === 0 ? <p className="honest-inline">尚無本機備忘。</p> : null}
        </div>
      </section>
    </section>
  )
}
