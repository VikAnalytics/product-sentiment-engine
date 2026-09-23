'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Event, PriceReaction, StockPrice, Target,
  fetchPriceSeries, fetchScoreSeries, fetchTargetWithEvents,
} from '@/lib/supabase'

type Ev = Event & { reaction: PriceReaction | null; avgScore: number | null; topTag: string | null }

function fmtSigned(n: number | null | undefined, digits = 1, suffix = ''): string {
  if (n == null) return '—'
  const s = Math.abs(n).toFixed(digits)
  return `${n > 0 ? '+' : n < 0 ? '−' : ' '}${s}${suffix}`
}

function signClass(n: number | null | undefined): string {
  if (n == null) return 'term-faint'
  if (n > 0.05) return 'term-pos'
  if (n < -0.05) return 'term-neg'
  return 'term-dim'
}

/** MM/DD, the terminal's date column. */
function fmtDay(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
}

/**
 * Sentiment drawn as a column chart in text-height rows.
 * Bars, not a smoothed line: each day is a discrete reading, and a line would
 * imply readings between them that do not exist.
 */
function Histogram({ series }: { series: { date: string; score: number }[] }) {
  if (series.length < 2) return <p className="term-faint m-0">Not enough readings to plot.</p>
  const w = 100, h = 34, mid = h / 2
  const step = w / series.length
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-[54px]" role="img"
         aria-label={`Daily sentiment over ${series.length} days`}>
      <line x1="0" x2={w} y1={mid} y2={mid} stroke="var(--t-faint)" strokeWidth="0.3" />
      {series.map((d, i) => {
        const height = Math.max(0.6, (Math.abs(d.score) / 10) * mid)
        return (
          <rect
            key={d.date}
            x={i * step + step * 0.18}
            width={step * 0.64}
            y={d.score >= 0 ? mid - height : mid}
            height={height}
            fill={d.score > 0 ? 'var(--t-pos)' : d.score < 0 ? 'var(--t-neg)' : 'var(--t-dim)'}
          />
        )
      })}
    </svg>
  )
}

function PriceLine({ bars }: { bars: StockPrice[] }) {
  const path = useMemo(() => {
    if (bars.length < 2) return null
    const closes = bars.map(b => Number(b.close))
    const lo = Math.min(...closes), hi = Math.max(...closes)
    const span = hi - lo || 1
    return {
      d: closes.map((c, i) => `${i ? 'L' : 'M'}${(i / (closes.length - 1)) * 100} ${28 - ((c - lo) / span) * 26}`).join(' '),
      lo, hi, last: closes[closes.length - 1], first: closes[0],
    }
  }, [bars])
  if (!path) return null
  const change = ((path.last - path.first) / path.first) * 100
  return (
    <div>
      <Row label="Last" value={`$${path.last.toFixed(2)}`} valueClass="term-white" />
      <Row label="Window" value={fmtSigned(change, 2, '%')} valueClass={signClass(change)} />
      <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="w-full h-[46px] mt-1" role="img" aria-label="Recent price">
        <path d={path.d} fill="none" stroke="var(--t-cyan)" strokeWidth="0.7" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

function Row({ label, value, valueClass = '' }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="term-head w-[13ch] shrink-0">{label}</span>
      <span className={`tabular-nums ${valueClass}`}>{value}</span>
    </div>
  )
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t px-3 py-2" style={{ borderColor: 'var(--t-rule)' }}>
      <h3 className="term-head m-0 mb-1.5">{title}</h3>
      {children}
    </section>
  )
}

export default function TerminalDetail({ targetId, onBack }: { targetId: number | null; onBack: () => void }) {
  const [data, setData] = useState<{ target: Target; events: Ev[] } | null>(null)
  const [series, setSeries] = useState<{ date: string; score: number }[]>([])
  const [bars, setBars] = useState<StockPrice[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (targetId == null) return
    let live = true
    setLoading(true)
    setError(null)
    fetchTargetWithEvents(targetId)
      .then(d => { if (live) { setData(d); setLoading(false) } })
      .catch(e => { if (live) { setError(e?.message ?? String(e)); setLoading(false) } })
    fetchScoreSeries(targetId, 30).then(s => { if (live) setSeries(s) }).catch(() => setSeries([]))
    setBars([])
    return () => { live = false }
  }, [targetId])

  // Price is a second trip and only for listed companies, so it loads after.
  useEffect(() => {
    if (!data?.target?.ticker || targetId == null) return
    let live = true
    fetchPriceSeries(targetId).then(b => { if (live) setBars(b) }).catch(() => setBars([]))
    return () => { live = false }
  }, [data?.target?.ticker, targetId])

  if (targetId == null) return <p className="term-dim m-0 p-4">Move the cursor to load a company.</p>
  if (error) return <p className="term-neg m-0 p-4">{error}</p>
  if (!data && loading) return <p className="term-dim m-0 p-4">Loading…</p>
  if (!data) return null

  const { target, events } = data
  const scored = events.map(e => e.avgScore).filter((s): s is number => s != null)
  const avg = scored.length ? scored.reduce((a, b) => a + b, 0) / scored.length : null
  const reactions = events.map(e => e.reaction?.window_return_pct).filter((r): r is number => r != null)
  const hitRate = reactions.length
    ? reactions.filter((r, i) => {
        const s = events.filter(e => e.reaction?.window_return_pct != null)[i]?.avgScore
        return s != null && ((s > 0 && r > 0) || (s < 0 && r < 0))
      }).length / reactions.length
    : null

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      {/* Security header */}
      <header className="px-3 py-2 flex items-baseline gap-3 flex-wrap">
        <button onClick={onBack} className="term-head lg:hidden hover:underline">← SCREEN</button>
        <span className="term-white text-[17px] font-semibold">{target.ticker ?? target.name}</span>
        {target.ticker && <span className="text-[14px]">{target.name}</span>}
        <span className="term-dim">{target.sector ?? 'Unclassified'}</span>
        {target.is_f500 && <span className="term-dim">F500</span>}
        {!target.ticker && <span className="term-faint">PRIVATE</span>}
        <span className={`ml-auto text-[17px] tabular-nums ${signClass(avg)}`}>{fmtSigned(avg)}</span>
      </header>

      <Panel title="Sentiment · 30 days">
        <Histogram series={series} />
        <div className="mt-1.5 grid grid-cols-2 gap-x-6">
          <Row label="Readings" value={String(scored.length)} valueClass="term-dim" />
          <Row label="Events" value={String(events.length)} valueClass="term-dim" />
        </div>
      </Panel>

      {target.ticker && (
        <Panel title={`Price · ${target.ticker}`}>
          {bars.length ? <PriceLine bars={bars} /> : <p className="term-faint m-0">No bars stored for this ticker.</p>}
          {hitRate != null && (
            <div className="mt-1.5">
              <Row
                label="Hit rate"
                value={`${Math.round(hitRate * 100)}% of ${reactions.length}`}
                valueClass={hitRate >= 0.5 ? 'term-pos' : 'term-neg'}
              />
            </div>
          )}
        </Panel>
      )}

      <Panel title={`Events · newest first`}>
        {events.length === 0 && <p className="term-faint m-0">Nothing tracked yet.</p>}
        <ol className="m-0 p-0 list-none">
          {events.map(ev => {
            const move = ev.reaction?.window_return_pct
            return (
              <li key={ev.id} className="grid gap-x-2 py-[3px] items-baseline" style={{ gridTemplateColumns: '5.5ch 6ch minmax(0,1fr) 7ch' }}>
                <span className="term-faint tabular-nums">{fmtDay(ev.published_at)}</span>
                <span className={`tabular-nums text-right ${signClass(ev.avgScore)}`}>{fmtSigned(ev.avgScore)}</span>
                <span className="min-w-0">
                  {ev.source_url ? (
                    <a href={ev.source_url} target="_blank" rel="noopener noreferrer" className="hover:underline">{ev.headline}</a>
                  ) : ev.headline}
                  {ev.summary && ev.summary !== ev.headline && (
                    <span className="term-dim block text-[11.5px] leading-snug">{ev.summary}</span>
                  )}
                </span>
                <span className={`tabular-nums text-right ${signClass(move)}`}>
                  {move == null ? <span className="term-faint">—</span> : fmtSigned(move, 2, '%')}
                </span>
              </li>
            )
          })}
        </ol>
      </Panel>
    </div>
  )
}
