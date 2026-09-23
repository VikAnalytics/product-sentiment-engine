'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Target, TargetScore } from '@/lib/supabase'
import { SECTORS } from '@/lib/utils'
import { Chip } from '@/components/ui'
import TerminalDetail from '@/components/TerminalDetail'
import TerminalCompare from '@/components/TerminalCompare'

type Scores = Record<number, TargetScore>
type SortKey = 'sent' | 'chg' | 'rdg' | 'tkr' | 'name'

interface Props {
  targets: Target[]
  scores: Scores
  selectedId: number | null
  onSelect: (id: number) => void
}

/** Fixed columns. The grid is one CSS grid so every row aligns to the pixel. */
const COLUMNS = '3.5ch 7ch minmax(0,1fr) 7ch 7ch 5ch 15ch'

const SORTS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: 'tkr', label: 'TKR', numeric: false },
  { key: 'name', label: 'Name', numeric: false },
  { key: 'sent', label: 'Sent', numeric: true },
  { key: 'chg', label: '7D', numeric: true },
  { key: 'rdg', label: 'Rdg', numeric: true },
]

function signClass(n: number | null | undefined): string {
  if (n == null) return 'term-faint'
  if (n > 0.05) return 'term-pos'
  if (n < -0.05) return 'term-neg'
  return 'term-dim'
}

function fmtSigned(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  const s = n.toFixed(digits)
  return n > 0 ? `+${s}` : s.replace('-', '−')
}

/** 09:41:22 ET, ticking. The clock is the one thing on screen that moves. */
function useMarketClock(): string {
  const [now, setNow] = useState<string>('')
  useEffect(() => {
    const tick = () => setNow(new Date().toLocaleTimeString('en-US', {
      hour12: false, timeZone: 'America/New_York',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    }))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

export default function Companies({ targets, scores, selectedId, onSelect }: Props) {
  const [q, setQ] = useState('')
  const [sectorIdx, setSectorIdx] = useState(0) // 0 = all
  const [f500, setF500] = useState(false)
  // The pipeline stopped between 2026-06-10 and 2026-09-19, so most companies
  // carry no reading inside the 30-day window. Default to the ones that do:
  // a screen full of dashes says nothing, and a stale score says something false.
  const [scoredOnly, setScoredOnly] = useState(true)
  const [sort, setSort] = useState<SortKey>('sent')
  const [desc, setDesc] = useState(true)
  const [compareMode, setCompareMode] = useState(false)
  const [compareIds, setCompareIds] = useState<number[]>([])
  const [cursor, setCursor] = useState(0)
  const [mobileDetail, setMobileDetail] = useState(false)
  const [typing, setTyping] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const clock = useMarketClock()
  const sector = sectorIdx === 0 ? '' : SECTORS[sectorIdx - 1]

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const list = targets
      .filter(t => t.target_type === 'COMPANY')
      .filter(t => !needle || t.name.toLowerCase().includes(needle) || (t.ticker ?? '').toLowerCase().includes(needle))
      .filter(t => !sector || t.sector === sector)
      .filter(t => !f500 || t.is_f500)
      .filter(t => !scoredOnly || (scores[t.id]?.count ?? 0) > 0)
    // Numbers read high-to-low when descending; text reads A-Z when ascending.
    const sign = desc ? 1 : -1
    const num = (v: number | null | undefined) => (v == null ? -Infinity : v)
    return list.sort((a, b) => {
      const sa = scores[a.id], sb = scores[b.id]
      switch (sort) {
        case 'tkr': return -sign * (a.ticker ?? 'zzz').localeCompare(b.ticker ?? 'zzz')
        case 'name': return -sign * a.name.localeCompare(b.name)
        case 'chg': return sign * (num(sb?.chg) - num(sa?.chg))
        case 'rdg': return sign * (num(sb?.count) - num(sa?.count))
        default: return sign * (num(sb?.avg1) - num(sa?.avg1))
      }
    })
  }, [targets, scores, q, sector, f500, scoredOnly, sort, desc])

  // The cursor addresses a position in the list, so reset it when the list changes.
  useEffect(() => { setCursor(0) }, [q, sector, f500, scoredOnly, sort, desc])

  const companyCount = useMemo(() => targets.filter(t => t.target_type === 'COMPANY').length, [targets])
  const scoredCount = useMemo(
    () => targets.filter(t => t.target_type === 'COMPANY' && (scores[t.id]?.count ?? 0) > 0).length,
    [targets, scores],
  )

  const active = rows[cursor] ?? null

  // Moving the cursor drives the panel, but a held-down key would fire a fetch
  // per row, so the panel follows a beat behind.
  const [panelId, setPanelId] = useState<number | null>(selectedId)
  useEffect(() => {
    if (!active) return
    const id = setTimeout(() => { setPanelId(active.id); onSelect(active.id) }, 170)
    return () => clearTimeout(id)
  }, [active, onSelect])

  // Follow the cursor with the scroll container.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-row='${cursor}']`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  const toggleCompare = useCallback((id: number) => {
    setCompareIds(ids => ids.includes(id) ? ids.filter(x => x !== id) : ids.length >= 4 ? ids : [...ids, id])
  }, [])

  const setSortKey = (key: SortKey) => {
    if (key === sort) { setDesc(d => !d); return }
    setSort(key)
    setDesc(key !== 'tkr' && key !== 'name')
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    const k = e.key
    if (k === 'ArrowDown' || (k === 'j' && e.ctrlKey)) { e.preventDefault(); setCursor(c => Math.min(c + 1, rows.length - 1)) }
    else if (k === 'ArrowUp' || (k === 'k' && e.ctrlKey)) { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
    else if (k === 'PageDown') { e.preventDefault(); setCursor(c => Math.min(c + 12, rows.length - 1)) }
    else if (k === 'PageUp') { e.preventDefault(); setCursor(c => Math.max(c - 12, 0)) }
    else if (k === 'Home') { e.preventDefault(); setCursor(0) }
    else if (k === 'End') { e.preventDefault(); setCursor(rows.length - 1) }
    else if (k === 'Enter') { e.preventDefault(); if (active) { compareMode ? toggleCompare(active.id) : setMobileDetail(true) } }
    else if (k === 'Escape') { e.preventDefault(); setQ('') }
    else if (k === 'F2') { e.preventDefault(); setCompareMode(v => { if (v) setCompareIds([]); return !v }) }
    else if (k === 'F3') { e.preventDefault(); setF500(v => !v) }
    else if (k === 'F4') { e.preventDefault(); setSectorIdx(i => (i + 1) % (SECTORS.length + 1)) }
    else if (k === 'F5') { e.preventDefault(); setScoredOnly(v => !v) }
  }

  const showCompare = compareMode && compareIds.length >= 2

  return (
    <div className="term flex-1 min-h-0 flex flex-col" onKeyDown={onKeyDown}>
      {/* Command line */}
      <div className="flex items-center gap-3 px-3 h-9 border-b" style={{ borderColor: 'var(--t-rule-lit)' }}>
        <span className="term-amber shrink-0">&gt;</span>
        <label className="flex-1 min-w-0 flex items-center">
          <span className="sr-only">Filter companies by name or ticker</span>
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            onFocus={() => setTyping(true)}
            onBlur={() => setTyping(false)}
            placeholder="TICKER OR NAME"
            // Sized to its contents so the idle caret can sit right after the text.
            style={{ width: `${Math.max(q.length, 14)}ch` }}
            className="min-w-0"
            autoComplete="off"
            spellCheck={false}
          />
          {!typing && <span className="term-caret pointer-events-none" aria-hidden />}
        </label>
        <span className="term-dim shrink-0 hidden sm:inline">
          {rows.length.toLocaleString()} OF {companyCount.toLocaleString()}
        </span>
        <span className="term-faint shrink-0 hidden lg:inline">{scoredCount} SCORED 30D</span>
        {sector && <span className="term-white shrink-0 hidden md:inline">{sector.toUpperCase()}</span>}
        {f500 && <span className="term-white shrink-0">F500</span>}
        <span className="term-dim shrink-0 tabular-nums">{clock} ET</span>
      </div>

      <div className="flex-1 min-h-0 flex">
        {/* Screen */}
        <section
          className={`min-w-0 flex flex-col lg:w-[52%] lg:border-r w-full ${mobileDetail ? 'hidden lg:flex' : 'flex'}`}
          style={{ borderColor: 'var(--t-rule)' }}
          aria-label="Company screen"
        >
          <div
            className="grid gap-x-2 px-3 py-1 border-b term-head shrink-0"
            style={{ gridTemplateColumns: COLUMNS, borderColor: 'var(--t-rule)' }}
          >
            <span aria-hidden>#</span>
            {SORTS.map(col => (
              <button
                key={col.key}
                onClick={() => setSortKey(col.key)}
                className={`term-head text-left hover:underline ${col.numeric ? 'text-right' : ''}`}
                aria-label={`Sort by ${col.label}`}
                aria-sort={sort === col.key ? (desc ? 'descending' : 'ascending') : 'none'}
              >
                {col.label}{sort === col.key ? (desc ? '▼' : '▲') : ''}
              </button>
            ))}
            <span>Sector</span>
          </div>

          <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto" role="listbox" aria-label="Companies" tabIndex={-1}>
            {rows.length === 0 && (
              <p className="term-dim px-3 py-6 m-0">
                {scoredOnly && scoredCount === 0
                  ? 'No company has a reading in the last 30 days. F5 lists every tracked company.'
                  : 'No company matches that filter. ESC clears it.'}
              </p>
            )}
            {rows.map((t, i) => {
              const sc = scores[t.id]
              const picked = compareIds.includes(t.id)
              return (
                <button
                  key={t.id}
                  data-row={i}
                  role="option"
                  aria-selected={i === cursor}
                  onClick={() => { setCursor(i); if (compareMode) toggleCompare(t.id); else setMobileDetail(true) }}
                  className="term-row w-full grid gap-x-2 px-3 py-[3px] text-left"
                  style={{ gridTemplateColumns: COLUMNS }}
                >
                  <span className="term-faint tabular-nums text-right">{compareMode ? (picked ? '▣' : '▢') : i + 1}</span>
                  <span className="term-white truncate">{t.ticker ?? <span className="term-faint">—</span>}</span>
                  <span className="truncate">{t.name}</span>
                  <span className={`${signClass(sc?.avg1)} tabular-nums text-right`}>{fmtSigned(sc?.avg1)}</span>
                  <span className={`${signClass(sc?.chg)} tabular-nums text-right`}>
                    {sc?.chg == null ? <span className="term-faint">—</span> : `${sc.chg > 0 ? '▲' : sc.chg < 0 ? '▼' : ' '}${Math.abs(sc.chg).toFixed(1)}`}
                  </span>
                  <span className="term-dim tabular-nums text-right">{sc?.count ?? 0}</span>
                  <span className="term-dim truncate">{t.sector ?? ''}</span>
                </button>
              )
            })}
          </div>
        </section>

        {/* Detail */}
        <section
          className={`flex-1 min-w-0 min-h-0 ${mobileDetail ? 'flex' : 'hidden lg:flex'} flex-col`}
          aria-label="Company detail"
        >
          {showCompare
            ? <TerminalCompare targets={compareIds.map(id => targets.find(t => t.id === id)).filter((t): t is Target => !!t)} scores={scores} />
            : compareMode
              ? <p className="term-dim m-0 p-4">Pick two to four companies with ENTER. {compareIds.length} picked.</p>
              : <TerminalDetail targetId={panelId} onBack={() => setMobileDetail(false)} />}
        </section>
      </div>

      {/* Function bar */}
      <div
        className="shrink-0 flex flex-wrap items-center gap-x-4 gap-y-0.5 px-3 h-7 border-t overflow-hidden"
        style={{ borderColor: 'var(--t-rule-lit)' }}
      >
        <FnKey k="F2" label={compareMode ? 'Exit compare' : 'Compare'} on={compareMode} onClick={() => setCompareMode(v => { if (v) setCompareIds([]); return !v })} />
        <FnKey k="F3" label="F500" on={f500} onClick={() => setF500(v => !v)} />
        <FnKey k="F4" label={sector || 'All sectors'} on={!!sector} onClick={() => setSectorIdx(i => (i + 1) % (SECTORS.length + 1))} />
        <FnKey k="F5" label={scoredOnly ? 'Scored only' : 'All companies'} on={scoredOnly} onClick={() => setScoredOnly(v => !v)} />
        <FnKey k="/" label="Filter" onClick={() => inputRef.current?.focus()} />
        <span className="term-faint hidden md:inline">↑↓ MOVE</span>
        <span className="term-faint hidden md:inline">ESC CLEAR</span>
      </div>
    </div>
  )
}

function FnKey({ k, label, on = false, onClick }: { k: string; label: string; on?: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex items-center gap-1.5 term-head hover:underline" aria-pressed={on}>
      <span className="term-white">{k}</span>
      <span style={{ color: on ? 'var(--t-amber)' : undefined }}>{label.toUpperCase()}</span>
    </button>
  )
}

export function TargetChips({ target, products, onSelect }: { target: Target; products: Target[]; onSelect: (id: number) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {target.ticker && <Chip tone="accent">{target.ticker}</Chip>}
      {target.sector && <Chip>{target.sector}</Chip>}
      {target.is_f500 && <Chip>Fortune 500</Chip>}
      {target.target_type === 'PRODUCT' && <Chip>Product</Chip>}
      {products.map(p => (
        <button key={p.id} onClick={() => onSelect(p.id)} className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[11.5px] font-medium text-ink-2 hover:text-accent bg-raised transition-colors" style={{ boxShadow: 'inset 0 0 0 1px var(--line)' }}>
          {p.name}
        </button>
      ))}
    </div>
  )
}
