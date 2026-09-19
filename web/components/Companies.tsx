'use client'

import { useEffect, useMemo, useState } from 'react'
import { Target } from '@/lib/supabase'
import { SECTORS } from '@/lib/utils'
import { Chip, Icon, Score, Segmented } from '@/components/ui'
import { SelectBox } from '@/components/Select'
import Logo from '@/components/Logo'
import DeepDive from '@/components/DeepDive'
import Compare from '@/components/Compare'

type Scores = Record<number, { avg: number; count: number }>
type Sort = 'score' | 'activity' | 'name'

interface Props {
  targets: Target[]
  scores: Scores
  selectedId: number | null
  onSelect: (id: number) => void
}

export default function Companies({ targets, scores, selectedId, onSelect }: Props) {
  const [q, setQ] = useState('')
  const [sector, setSector] = useState('')
  const [f500, setF500] = useState(false)
  const [sort, setSort] = useState<Sort>('score')
  const [compareMode, setCompareMode] = useState(false)
  const [compareIds, setCompareIds] = useState<number[]>([])
  const [railOpen, setRailOpen] = useState(false)

  const companies = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return targets
      .filter(t => t.target_type === 'COMPANY')
      .filter(t => !needle || t.name.toLowerCase().includes(needle) || (t.ticker ?? '').toLowerCase() === needle)
      .filter(t => !sector || t.sector === sector)
      .filter(t => !f500 || t.is_f500)
      .sort((a, b) => {
        if (sort === 'name') return a.name.localeCompare(b.name)
        if (sort === 'activity') return (scores[b.id]?.count ?? 0) - (scores[a.id]?.count ?? 0)
        return (scores[b.id]?.avg ?? -99) - (scores[a.id]?.avg ?? -99) || (scores[b.id]?.count ?? 0) - (scores[a.id]?.count ?? 0)
      })
  }, [targets, scores, q, sector, f500, sort])

  const byId = useMemo(() => Object.fromEntries(targets.map(t => [t.id, t])), [targets])
  const selected = selectedId != null ? byId[selectedId] : null
  const selectedCompanyId = selected?.target_type === 'PRODUCT' ? selected.parent_target_id : selectedId

  // Close the mobile rail once a pick is made.
  useEffect(() => { setRailOpen(false) }, [selectedId])

  const toggleCompare = (id: number) => {
    setCompareIds(ids => ids.includes(id) ? ids.filter(x => x !== id) : ids.length >= 4 ? ids : [...ids, id])
  }

  const showCompare = compareMode && compareIds.length >= 2

  return (
    <div className="flex-1 min-h-0 flex">
      {/* Rail */}
      <aside
        className={`shrink-0 flex flex-col border-r border-line bg-bg lg:static fixed inset-y-0 left-0 z-30 transition-transform lg:translate-x-0 ${railOpen ? 'translate-x-0 shadow-pop' : '-translate-x-full'}`}
        style={{ width: 'var(--rail-w)', top: 'var(--topbar-h)' }}
        aria-label="Company list"
      >
        <div className="p-3 flex flex-col gap-2 border-b border-line">
          <label className="relative flex items-center">
            <Icon name="search" size={14} className="absolute left-2.5 text-ink-3" />
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Filter companies"
              className="w-full h-8 rounded-lg bg-surface border border-line hover:border-line-strong focus:border-accent pl-8 pr-2.5 text-[13px] outline-none transition-colors placeholder:text-ink-3"
            />
          </label>
          <div className="flex gap-1.5">
            <SelectBox value={sector} onChange={setSector} placeholder="All sectors" options={SECTORS.map(s => ({ value: s, label: s }))} className="flex-1 min-w-0" ariaLabel="Sector" />
            <button
              onClick={() => setF500(v => !v)}
              aria-pressed={f500}
              className={`h-8 rounded-lg px-2.5 text-[12.5px] font-medium border transition-colors ${f500 ? 'bg-accent-soft text-accent border-transparent' : 'bg-surface text-ink-2 border-line hover:border-line-strong'}`}
              title="Fortune 500 only"
            >F500</button>
          </div>
          <div className="flex items-center justify-between gap-2 pt-1">
            <Segmented value={sort} onChange={setSort} options={[{ value: 'score', label: 'Score' }, { value: 'activity', label: 'Activity' }, { value: 'name', label: 'A–Z' }]} />
            <button
              onClick={() => { setCompareMode(v => !v); if (compareMode) setCompareIds([]) }}
              aria-pressed={compareMode}
              className={`h-7 rounded-md px-2 text-[12.5px] font-medium transition-colors ${compareMode ? 'bg-accent text-accent-ink' : 'text-ink-2 hover:text-ink hover:bg-surface'}`}
            >
              {compareMode ? 'Done' : 'Compare'}
            </button>
          </div>
          {compareMode && (
            <p className="m-0 text-[12px] text-ink-2">Pick two to four companies. {compareIds.length} selected.</p>
          )}
        </div>

        <ol className="flex-1 min-h-0 overflow-y-auto m-0 p-1.5 list-none">
          {companies.length === 0 && <li className="text-[13px] text-ink-3 text-center py-10">No companies match.</li>}
          {companies.map((t, i) => {
            const sc = scores[t.id]
            const active = !compareMode && t.id === selectedCompanyId
            const checked = compareIds.includes(t.id)
            return (
              <li key={t.id}>
                <button
                  onClick={() => compareMode ? toggleCompare(t.id) : onSelect(t.id)}
                  aria-current={active ? 'true' : undefined}
                  className={`w-full flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors ${active || checked ? 'bg-accent-soft' : 'hover:bg-surface'}`}
                >
                  {compareMode ? (
                    <span className={`grid place-items-center size-4 rounded border transition-colors ${checked ? 'bg-accent border-accent text-accent-ink' : 'border-line-strong'}`}>{checked && <Icon name="check" size={11} />}</span>
                  ) : (
                    <span className="tnum w-5 text-right text-[11.5px] text-ink-3">{i + 1}</span>
                  )}
                  <Logo logoUrl={t.logo_url} domain={t.domain} name={t.name} size={24} />
                  <span className="flex-1 min-w-0">
                    <span className={`block text-[13.5px] truncate ${active ? 'text-ink font-medium' : 'text-ink'}`}>{t.name}</span>
                    <span className="block text-[11.5px] text-ink-3 truncate">{[t.ticker, t.sector].filter(Boolean).join('  ')}</span>
                  </span>
                  <span className="text-right shrink-0">
                    <Score value={sc?.avg ?? null} size="sm" />
                    {sc?.count != null && <span className="block tnum text-[10.5px] text-ink-3 leading-none mt-0.5">{sc.count}</span>}
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      </aside>

      {railOpen && <button className="fixed inset-0 z-20 bg-black/30 lg:hidden" style={{ top: 'var(--topbar-h)' }} aria-label="Close company list" onClick={() => setRailOpen(false)} />}

      {/* Main */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">
        <div className="lg:hidden flex items-center gap-2 px-4 py-2 border-b border-line">
          <button onClick={() => setRailOpen(true)} className="h-8 rounded-lg px-3 text-[13px] font-medium bg-surface border border-line">Companies</button>
          {selected && <span className="text-[13px] text-ink-2 truncate">{selected.name}</span>}
        </div>
        {showCompare
          ? <Compare targets={compareIds.map(id => byId[id]).filter(Boolean)} scores={scores} onOpen={id => { setCompareMode(false); onSelect(id) }} />
          : compareMode
            ? <div className="flex-1 flex items-center justify-center p-8 text-center"><div><div className="headline text-[18px] font-semibold">Pick companies to compare</div><p className="m-0 mt-1 text-[13.5px] text-ink-2">Choose two to four from the list.</p></div></div>
            : <DeepDive targetId={selectedId} targets={targets} onSelect={onSelect} />}
      </div>
    </div>
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
