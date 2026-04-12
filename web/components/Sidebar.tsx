'use client'

import { useMemo, useState } from 'react'
import { Target } from '@/lib/supabase'
import { barClass, fmtScore, scoreClass } from '@/lib/utils'
import Logo from '@/components/Logo'

type View = 'feed' | 'analysis' | 'simulator'

interface Props {
  view: View
  onViewChange: (v: View) => void
  targets: Target[]
  scores: Record<number, { avg: number; count: number }>
  selectedId: number | null
  onSelect: (id: number) => void
}

const SECTORS = [
  'Technology', 'Gaming', 'Consumer Electronics', 'Automotive & EV',
  'Media & Entertainment', 'Finance & Fintech', 'Retail',
  'Defense & Aerospace', 'Social Media', 'Industrials', 'Mobility',
  'Sports & Events', 'Education', 'Luxury', 'Transport',
]

const SECTOR_ABBR: Record<string, string> = {
  'Technology': 'TECH',
  'Gaming': 'GAME',
  'Consumer Electronics': 'CE',
  'Automotive & EV': 'AUTO',
  'Media & Entertainment': 'MED',
  'Finance & Fintech': 'FIN',
  'Retail': 'RTIL',
  'Defense & Aerospace': 'DEF',
  'Social Media': 'SOC',
  'Industrials': 'IND',
  'Mobility': 'MOB',
  'Sports & Events': 'SPRT',
  'Education': 'EDU',
  'Luxury': 'LUX',
  'Transport': 'TRNP',
}

const NAV: { key: View; label: string }[] = [
  { key: 'feed',      label: 'News Feed' },
  { key: 'analysis',  label: 'Analysis' },
  { key: 'simulator', label: 'Simulator' },
]

export default function Sidebar({ view, onViewChange, targets, scores, selectedId, onSelect }: Props) {
  const [search, setSearch] = useState('')
  const [sectorFilter, setSectorFilter] = useState('')
  const [f500Only, setF500Only] = useState(false)

  const sorted = useMemo(() => {
    return targets
      .filter(t => t.target_type === 'COMPANY')
      .filter(t => !search || t.name.toLowerCase().includes(search.toLowerCase()))
      .filter(t => !sectorFilter || t.sector === sectorFilter)
      .filter(t => !f500Only || t.is_f500)
      .sort((a, b) => {
        const sa = scores[a.id]?.avg ?? -999
        const sb = scores[b.id]?.avg ?? -999
        return sb - sa
      })
  }, [targets, scores, search, sectorFilter, f500Only])

  return (
    <aside style={{
      width: '280px',
      minWidth: '280px',
      height: '100%',
      borderRight: '1px solid var(--br)',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      background: 'var(--bg)',
    }}>

      {/* ── nav ── */}
      <nav style={{ padding: '8px', borderBottom: '1px solid var(--br)', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV.map(n => {
          const active = view === n.key
          return (
            <button
              key={n.key}
              onClick={() => onViewChange(n.key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '10px 12px',
                border: 'none',
                borderLeft: active ? '2px solid var(--gold)' : '2px solid transparent',
                background: active ? 'var(--gold-d)' : 'transparent',
                color: active ? 'var(--gold)' : 'var(--t2)',
                fontFamily: 'var(--ff-m)',
                fontSize: 12,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                cursor: 'pointer',
                transition: 'all 0.13s',
                textAlign: 'left',
                width: '100%',
                borderRadius: '0 2px 2px 0',
              }}
              onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--bg-h)'; e.currentTarget.style.color = 'var(--t1)' } }}
              onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--t2)' } }}
            >
              {n.label}
            </button>
          )
        })}
      </nav>

      {/* ── filters ── */}
      <div style={{ padding: '12px', borderBottom: '1px solid var(--br)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <input
          style={{
            width: '100%',
            background: 'var(--bg-r)',
            border: '1px solid var(--br)',
            color: 'var(--t1)',
            fontFamily: 'var(--ff-m)',
            fontSize: 12,
            padding: '7px 10px',
            borderRadius: 2,
            outline: 'none',
            transition: 'border-color 0.13s',
          }}
          placeholder="Search companies…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onFocus={e => (e.target.style.borderColor = 'var(--br-a)')}
          onBlur={e => (e.target.style.borderColor = 'var(--br)')}
        />
        <div style={{ display: 'flex', gap: 6 }}>
          <select
            value={sectorFilter}
            onChange={e => setSectorFilter(e.target.value)}
            style={{
              flex: 1,
              background: 'var(--bg-r)',
              border: '1px solid var(--br)',
              color: sectorFilter ? 'var(--gold)' : 'var(--t2)',
              fontFamily: 'var(--ff-m)',
              fontSize: 11,
              padding: '6px 8px',
              borderRadius: 2,
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="">All Sectors</option>
            {SECTORS.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button
            onClick={() => setF500Only(v => !v)}
            title="Fortune 500 only"
            style={{
              fontFamily: 'var(--ff-m)',
              fontSize: 11,
              padding: '6px 10px',
              border: `1px solid ${f500Only ? 'var(--gold)' : 'var(--br)'}`,
              borderRadius: 2,
              cursor: 'pointer',
              color: f500Only ? 'var(--gold)' : 'var(--t2)',
              background: f500Only ? 'var(--gold-d)' : 'var(--bg-r)',
              letterSpacing: '0.06em',
              whiteSpace: 'nowrap',
              transition: 'all 0.13s',
            }}
          >F500</button>
        </div>
        {(search || sectorFilter || f500Only) && (
          <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.1em', marginTop: 2 }}>
            {sorted.length} result{sorted.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      {/* ── ranked company list — only when filtering/searching ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {!search && !sectorFilter && !f500Only ? (
          <div style={{ padding: '28px 16px', textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.12em', lineHeight: 1.8 }}>
              Search or select<br />a sector to browse
            </div>
          </div>
        ) : sorted.length === 0 ? (
          <div style={{ padding: '24px 16px', textAlign: 'center', fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.1em' }}>
            No results
          </div>
        ) : null}
        {(search || sectorFilter || f500Only) && sorted.map((t, rank) => {
          const sc = scores[t.id]
          const avg = sc?.avg ?? null
          const sel = t.id === selectedId
          const abbr = SECTOR_ABBR[t.sector ?? ''] ?? t.sector?.slice(0, 4).toUpperCase() ?? '—'
          return (
            <div
              key={t.id}
              onClick={() => { onSelect(t.id); if (view !== 'analysis') onViewChange('analysis') }}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '8px 12px',
                cursor: 'pointer',
                gap: 10,
                transition: 'background 0.1s',
                borderLeft: sel ? '2px solid var(--gold)' : '2px solid transparent',
                background: sel ? 'var(--gold-d)' : 'transparent',
              }}
              onMouseEnter={e => { if (!sel) e.currentTarget.style.background = 'var(--bg-h)' }}
              onMouseLeave={e => { if (!sel) e.currentTarget.style.background = 'transparent' }}
            >
              {/* rank */}
              <span style={{ fontFamily: 'var(--ff-m)', fontSize: 9, color: 'var(--tm)', minWidth: 16, textAlign: 'right' }}>
                {rank + 1}
              </span>

              {/* logo */}
              <Logo logoUrl={t.logo_url} domain={t.domain} name={t.name} size={22} radius="sm" />

              {/* name */}
              <span style={{
                flex: 1,
                fontFamily: 'var(--ff-b)',
                fontSize: 14,
                color: sel ? 'var(--t1)' : 'var(--t1)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                lineHeight: 1.2,
              }}>{t.name}</span>

              {/* sector abbr */}
              <span style={{
                fontFamily: 'var(--ff-m)',
                fontSize: 8,
                color: 'var(--tm)',
                letterSpacing: '0.06em',
                flexShrink: 0,
              }}>{abbr}</span>

              {/* score */}
              <span className={scoreClass(avg)} style={{
                fontFamily: 'var(--ff-m)',
                fontSize: 12,
                fontWeight: 700,
                minWidth: 28,
                textAlign: 'right',
                flexShrink: 0,
              }}>{fmtScore(avg)}</span>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
