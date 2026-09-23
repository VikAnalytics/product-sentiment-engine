'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchEventSentiment, fetchPriceSeries, fetchScoreSeries, fetchTargetWithEvents, PriceReaction, SentimentRow, StockPrice, Target } from '@/lib/supabase'
import { avg, confidenceLabel, dedupeLines, fmtDate, fmtPct, fmtScore1, fmtUSD, relativeTime, scoreLabel, scoreTone, signColor, toLines, toneColor } from '@/lib/utils'
import { Empty, Icon, Loading, Score, SectionHead, Segmented, Sparkline, TagChip } from '@/components/ui'
import { TargetChips } from '@/components/Companies'
import Logo from '@/components/Logo'

type Ev = { id: number; headline: string; summary: string | null; source_url: string | null; published_at: string; created_at: string; cached_analysis: string | null; avgScore: number | null; topTag: string | null; reaction: PriceReaction | null }

export default function DeepDive({ targetId, targets, onSelect }: { targetId: number | null; targets: Target[]; onSelect: (id: number) => void }) {
  const [target, setTarget] = useState<Target | null>(null)
  const [events, setEvents] = useState<Ev[]>([])
  const [series, setSeries] = useState<{ date: string; score: number }[]>([])
  const [prices, setPrices] = useState<StockPrice[]>([])
  const [loading, setLoading] = useState(false)
  const [range, setRange] = useState<30 | 90>(30)
  const [openId, setOpenId] = useState<number | null>(null)

  useEffect(() => {
    if (targetId == null) return
    let alive = true
    setLoading(true); setOpenId(null)
    Promise.all([fetchTargetWithEvents(targetId), fetchScoreSeries(targetId, 90), fetchPriceSeries(targetId)])
      .then(([{ target, events }, s, p]) => { if (!alive) return; setTarget(target); setEvents(events as Ev[]); setSeries(s); setPrices(p) })
      .catch(() => { if (alive) setTarget(null) })
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [targetId])

  const products = useMemo(() => targets.filter(t => t.target_type === 'PRODUCT' && t.parent_target_id === targetId), [targets, targetId])
  const parent = useMemo(() => target?.parent_target_id ? targets.find(t => t.id === target.parent_target_id) ?? null : null, [targets, target])

  const avgScore = useMemo(() => { const a = avg(events.map(e => e.avgScore).filter((s): s is number => s != null)); return a == null ? null : Math.round(a) }, [events])

  const momentum = useMemo(() => {
    const now = Date.now(), d7 = now - 7 * 864e5, d14 = now - 14 * 864e5
    const t = (d: string) => new Date(d).getTime()
    const recent = avg(series.filter(s => t(s.date) >= d7).map(s => s.score))
    const prior = avg(series.filter(s => t(s.date) >= d14 && t(s.date) < d7).map(s => s.score))
    return recent == null || prior == null ? null : recent - prior
  }, [series])

  const visibleSeries = useMemo(() => { const since = Date.now() - range * 864e5; return series.filter(s => new Date(s.date).getTime() >= since) }, [series, range])

  const daily = useMemo(() => {
    const m: Record<string, number> = {}
    for (const p of prices) m[p.ts.slice(0, 10)] = p.close
    const entries = Object.entries(m).sort(([a], [b]) => a.localeCompare(b)).slice(-60)
    if (entries.length < 2) return null
    const closes = entries.map(([, c]) => c)
    const last = closes[closes.length - 1], prev = closes[closes.length - 2], first = closes[0]
    return { closes, last, change1d: (last - prev) / prev, changeWindow: (last - first) / first, from: entries[0][0], to: entries[entries.length - 1][0] }
  }, [prices])

  if (targetId == null) return <Empty title="Pick a company" hint="Choose one from the list, or press ⌘K to search." />
  // While loading, render the hero from the already-loaded target list so the switch feels instant.
  const listTarget = targets.find(t => t.id === targetId) ?? null
  if (loading && listTarget) return <HeroOnly target={listTarget} parent={parent ?? (listTarget.parent_target_id ? targets.find(t => t.id === listTarget.parent_target_id) ?? null : null)} products={products} onSelect={onSelect} />
  if (loading) return <Loading label="Loading company" />
  if (!target) return <Empty title="Company not found" hint="It may have been removed from tracking." />

  const spark = toneColor(scoreTone(avgScore))

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-[1080px] mx-auto px-4 md:px-6 py-5 md:py-6 fade">

        {/* Hero */}
        <section className="hero p-5 md:p-7">
          <div className="flex flex-col md:flex-row gap-6 md:gap-10">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-3">
                <Logo logoUrl={target.logo_url ?? parent?.logo_url ?? null} domain={target.domain ?? parent?.domain ?? null} name={target.name} size={48} />
                {parent && <button onClick={() => onSelect(parent.id)} className="text-[13px] text-ink-2 hover:text-accent transition-colors">Part of {parent.name}</button>}
              </div>
              <h1 className="display text-[36px] md:text-[44px] font-semibold text-ink m-0">{target.name}</h1>
              <div className="mt-3"><TargetChips target={target} products={products} onSelect={onSelect} /></div>
              {target.description && <p className="m-0 mt-4 text-[14.5px] text-ink-2 max-w-[62ch]">{target.description}</p>}
            </div>
            <div className="flex md:flex-col md:items-end gap-6 md:gap-4 shrink-0">
              <div className="text-right">
                <Score value={avgScore} size="xl" />
                <div className="text-[12.5px] text-ink-2 mt-1">{scoreLabel(avgScore)}, {events.length} event{events.length === 1 ? '' : 's'}</div>
              </div>
              {momentum != null && (
                <div className="text-right">
                  <div className="figure text-[22px] font-semibold inline-flex items-center gap-1" style={{ color: signColor(momentum) }}>
                    <Icon name={momentum >= 0 ? 'arrow-up' : 'arrow-down'} size={16} />{fmtScore1(momentum)}
                  </div>
                  <div className="text-[12.5px] text-ink-2 mt-0.5">vs prior 7 days</div>
                </div>
              )}
              {daily && (
                <div className="text-right">
                  <div className="figure text-[22px] font-semibold text-ink">{fmtUSD(daily.last)}</div>
                  <div className="text-[12.5px] mt-0.5" style={{ color: signColor(daily.change1d) }}>{fmtPct(daily.change1d)} today</div>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Charts */}
        <div className="grid md:grid-cols-2 gap-4 mt-4">
          <section className="hero p-4 md:p-5">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="headline text-[15px] font-semibold m-0">Sentiment trend</h2>
              <Segmented value={range} onChange={setRange} options={[{ value: 30, label: '30d' }, { value: 90, label: '90d' }]} />
            </div>
            {visibleSeries.length > 1
              ? <Sparkline points={visibleSeries.map(s => s.score)} color={spark} band={[-2, 2]} baseline={0} height={96} />
              : <p className="m-0 py-8 text-center text-[13px] text-ink-3">Not enough readings for a trend.</p>}
            <div className="flex justify-between text-[11.5px] text-ink-3 mt-1.5 tnum">
              <span>{visibleSeries[0] ? fmtDate(visibleSeries[0].date) : ''}</span>
              <span>Daily average, −10 to +10</span>
              <span>{visibleSeries.at(-1) ? fmtDate(visibleSeries.at(-1)!.date) : ''}</span>
            </div>
          </section>
          <section className="hero p-4 md:p-5">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="headline text-[15px] font-semibold m-0">{target.ticker ? `${target.ticker} close` : 'Price'}</h2>
              {daily && <span className="tnum text-[12.5px] font-medium" style={{ color: signColor(daily.changeWindow) }}>{fmtPct(daily.changeWindow)} over window</span>}
            </div>
            {daily
              ? <Sparkline points={daily.closes} color={signColor(daily.changeWindow)} height={96} />
              : <p className="m-0 py-8 text-center text-[13px] text-ink-3">{target.ticker ? 'No price bars yet.' : 'Private company, no listed price.'}</p>}
            {daily && <div className="flex justify-between text-[11.5px] text-ink-3 mt-1.5 tnum"><span>{fmtDate(daily.from)}</span><span>Daily close</span><span>{fmtDate(daily.to)}</span></div>}
          </section>
        </div>

        {/* Events */}
        <section className="mt-6">
          <SectionHead title="Events" meta={`${events.length} tracked, newest first`} />
          {events.length === 0 && <Empty title="No events yet" hint="Events appear when the scout links a headline to this company." />}
          <ol className="m-0 p-0 list-none stagger">
            {events.map(ev => (
              <EventRow key={ev.id} ev={ev} open={openId === ev.id} onToggle={() => setOpenId(openId === ev.id ? null : ev.id)} />
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}

function HeroOnly({ target, parent, products, onSelect }: { target: Target; parent: Target | null; products: Target[]; onSelect: (id: number) => void }) {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-[1080px] mx-auto px-4 md:px-6 py-5 md:py-6">
        <section className="hero p-5 md:p-7">
          <div className="flex items-center gap-3 mb-3">
            <Logo logoUrl={target.logo_url ?? parent?.logo_url ?? null} domain={target.domain ?? parent?.domain ?? null} name={target.name} size={48} />
            {parent && <button onClick={() => onSelect(parent.id)} className="text-[13px] text-ink-2 hover:text-accent transition-colors">Part of {parent.name}</button>}
          </div>
          <h1 className="display text-[36px] md:text-[44px] font-semibold text-ink m-0">{target.name}</h1>
          <div className="mt-3"><TargetChips target={target} products={products} onSelect={onSelect} /></div>
          {target.description && <p className="m-0 mt-4 text-[14.5px] text-ink-2 max-w-[62ch]">{target.description}</p>}
        </section>
        <Loading label="Loading events and prices" />
      </div>
    </div>
  )
}

function EventRow({ ev, open, onToggle }: { ev: Ev; open: boolean; onToggle: () => void }) {
  const [rows, setRows] = useState<SentimentRow[] | null>(null)
  useEffect(() => { if (open && rows == null) fetchEventSentiment(ev.id).then(setRows).catch(() => setRows([])) }, [open, rows, ev.id])

  const r = ev.reaction
  const windowPct = r?.window_return_pct != null ? r.window_return_pct / 100 : null
  const rule = toneColor(scoreTone(ev.avgScore))

  const pros = useMemo(() => dedupeLines((rows ?? []).flatMap(x => toLines(x.pros))).slice(0, 6), [rows])
  const cons = useMemo(() => dedupeLines((rows ?? []).flatMap(x => toLines(x.cons))).slice(0, 6), [rows])
  const quotes = useMemo(() => dedupeLines((rows ?? []).flatMap(x => toLines(x.verbatim_quotes).map(q => q.replace(/^["“”']+|["“”']+$/g, '')))).slice(0, 4), [rows])
  const sources = useMemo(() => [...new Set((rows ?? []).map(x => x.source_url).filter((u): u is string => !!u && u.startsWith('http')))].slice(0, 8), [rows])

  return (
    <li className="border-b border-line">
      <button onClick={onToggle} aria-expanded={open} className="w-full grid grid-cols-[72px_minmax(0,1fr)_auto] gap-4 py-3.5 pl-1 pr-1 text-left row-hover rounded-lg items-start">
        <span className="pt-0.5 border-l-2 pl-3" style={{ borderColor: rule }}>
          <span className="block text-[13px] text-ink tnum">{fmtDate(ev.published_at)}</span>
          <span className="block text-[11.5px] text-ink-3">{relativeTime(ev.published_at)}</span>
        </span>
        <span className="min-w-0">
          <span className="headline block text-[16.5px] text-ink">{ev.headline}</span>
          {ev.summary && ev.summary !== ev.headline && (
            <span className="block text-[13px] text-ink-2 mt-1 leading-snug">{ev.summary}</span>
          )}
        </span>
        <span className="flex flex-col items-end gap-1.5 shrink-0">
          <Score value={ev.avgScore} size="md" />
          <TagChip tag={ev.topTag} />
          {windowPct != null && <span className="tnum text-[12px] font-medium" style={{ color: signColor(windowPct) }}>{fmtPct(windowPct)} move</span>}
        </span>
      </button>

      {open && (
        <div className="pl-[88px] pr-2 pb-5 rise">
          {ev.source_url && (
            <a href={ev.source_url} target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-1.5 mb-3 text-[13px] text-accent hover:underline">
              Read the original <Icon name="external" size={13} />
            </a>
          )}
          {r && r.price_at_event != null && (
            <div className="flex flex-wrap items-end gap-x-7 gap-y-2 mb-4 p-4 rounded-lg bg-raised">
              <Cell label={`${r.ticker} at event`} value={fmtUSD(r.price_at_event)} />
              <Cell label="Until next event" value={fmtPct(windowPct)} color={signColor(windowPct)} strong />
              <Cell label="1 day" value={fmtPct(r.reaction_1d != null ? r.reaction_1d / 100 : null)} color={signColor(r.reaction_1d)} />
              <Cell label="3 days" value={fmtPct(r.reaction_3d != null ? r.reaction_3d / 100 : null)} color={signColor(r.reaction_3d)} />
              <Cell label="7 days" value={fmtPct(r.reaction_7d != null ? r.reaction_7d / 100 : null)} color={signColor(r.reaction_7d)} />
              <span className="ml-auto text-[12px] text-ink-2 max-w-[38ch]">
                {confidenceLabel(r.confidence)}{r.market_session ? `, ${r.market_session.replace('_', ' ')} session` : ''}{r.confidence_reason ? `. ${r.confidence_reason}` : ''}
              </span>
            </div>
          )}

          {rows == null ? <p className="m-0 text-[13px] text-ink-3">Loading details</p> : rows.length === 0 && !ev.cached_analysis ? (
            <p className="m-0 text-[13px] text-ink-3">No community chatter recorded for this event.</p>
          ) : (
            <div className="grid md:grid-cols-3 gap-5">
              <List title="Pros" items={pros} tone="var(--pos)" />
              <List title="Cons" items={cons} tone="var(--neg)" />
              <div>
                <h3 className="text-[13px] font-semibold text-ink-2 m-0 mb-2">What people said</h3>
                {quotes.length === 0 && <p className="m-0 text-[13px] text-ink-3">No quotes recorded.</p>}
                {quotes.map((q, i) => <blockquote key={i} className="m-0 mb-2 pl-3 border-l-2 border-accent text-[13.5px] text-ink-2 leading-relaxed">{q}</blockquote>)}
                {sources.length > 0 && (
                  <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
                    {sources.map(u => <a key={u} href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">{hostOf(u)}<Icon name="external" size={11} /></a>)}
                  </div>
                )}
              </div>
            </div>
          )}

          {ev.cached_analysis && (
            <div className="mt-4 p-4 rounded-lg bg-accent-soft">
              <h3 className="text-[13px] font-semibold text-accent m-0 mb-1.5">Strategic read</h3>
              <p className="m-0 text-[14px] text-ink leading-relaxed whitespace-pre-wrap">{ev.cached_analysis}</p>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function Cell({ label, value, color = 'var(--ink)', strong = false }: { label: string; value: string; color?: string; strong?: boolean }) {
  return (
    <span>
      <span className={`figure block ${strong ? 'text-[22px]' : 'text-[17px]'} font-semibold`} style={{ color }}>{value}</span>
      <span className="block text-[11.5px] text-ink-3 mt-0.5">{label}</span>
    </span>
  )
}

function List({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div>
      <h3 className="text-[13px] font-semibold text-ink-2 m-0 mb-2">{title}</h3>
      {items.length === 0 && <p className="m-0 text-[13px] text-ink-3">None recorded.</p>}
      <ul className="m-0 p-0 list-none">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-[13.5px] text-ink leading-relaxed py-1 border-b border-line last:border-0">
            <span className="mt-[9px] size-1.5 rounded-full shrink-0" style={{ background: tone }} />{it}
          </li>
        ))}
      </ul>
    </div>
  )
}

function hostOf(u: string): string {
  try { return new URL(u).hostname.replace(/^www\./, '') } catch { return 'source' }
}
