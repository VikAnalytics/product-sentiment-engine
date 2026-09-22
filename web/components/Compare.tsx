'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchRecentSentiment, fetchScoreSeriesBatch, SentimentRow, Target } from '@/lib/supabase'
import { avg, dedupeLines, fmtScore1, scoreLabel, scoreTone, signColor, toLines, toneColor } from '@/lib/utils'
import { Icon, Loading, Score, Sparkline, TagChip } from '@/components/ui'
import Logo from '@/components/Logo'

const TAG_PRIORITY: Record<string, number> = { threat: 4, opportunity: 3, monitor: 2, no_action: 1 }

export default function Compare({ targets, scores, onOpen }: { targets: Target[]; scores: Record<number, { avg: number; count: number }>; onOpen: (id: number) => void }) {
  const [series, setSeries] = useState<Record<number, { date: string; score: number }[]>>({})
  const [rows, setRows] = useState<Record<number, SentimentRow[]>>({})
  const [loading, setLoading] = useState(true)
  const ids = useMemo(() => targets.map(t => t.id), [targets])

  useEffect(() => {
    let alive = true
    setLoading(true)
    Promise.all([fetchScoreSeriesBatch(ids, 30), ...ids.map(id => fetchRecentSentiment(id, 12))])
      .then(([s, ...r]) => { if (!alive) return; setSeries(s); setRows(Object.fromEntries(ids.map((id, i) => [id, r[i] as SentimentRow[]]))) })
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [ids])

  if (loading) return <Loading label="Comparing" />

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-[1320px] mx-auto px-4 md:px-6 py-5 md:py-6">
        <h1 className="display text-[30px] font-semibold m-0 mb-4">Side by side</h1>
        <div className="grid gap-4 stagger" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(240px, 1fr))` }}>
          {targets.map(t => {
            const s = series[t.id] ?? []
            const rs = rows[t.id] ?? []
            const now = Date.now()
            const recent = avg(s.filter(x => new Date(x.date).getTime() >= now - 7 * 864e5).map(x => x.score))
            const prior = avg(s.filter(x => { const ts = new Date(x.date).getTime(); return ts >= now - 14 * 864e5 && ts < now - 7 * 864e5 }).map(x => x.score))
            const momentum = recent != null && prior != null ? recent - prior : null
            const score = scores[t.id]?.avg ?? null
            const tag = rs.map(r => r.implication_tag).filter(Boolean).sort((a, b) => (TAG_PRIORITY[b!] ?? 0) - (TAG_PRIORITY[a!] ?? 0))[0] ?? null
            const pros = dedupeLines(rs.flatMap(r => toLines(r.pros))).slice(0, 3)
            const cons = dedupeLines(rs.flatMap(r => toLines(r.cons))).slice(0, 3)
            return (
              <article key={t.id} className="hero p-5 flex flex-col">
                <header className="flex items-center gap-3">
                  <Logo logoUrl={t.logo_url} domain={t.domain} name={t.name} size={36} />
                  <div className="min-w-0">
                    <button onClick={() => onOpen(t.id)} className="headline text-[17px] font-semibold text-ink hover:text-accent transition-colors truncate block">{t.name}</button>
                    <div className="text-[12px] text-ink-3 truncate">{[t.ticker, t.sector].filter(Boolean).join('  ')}</div>
                  </div>
                </header>
                <div className="mt-5 flex items-end justify-between gap-3">
                  <div>
                    <Score value={score} size="xl" />
                    <div className="text-[12.5px] text-ink-2 mt-1">{scoreLabel(score)}</div>
                  </div>
                  <div className="text-right">
                    {momentum != null && (
                      <div className="figure text-[18px] font-semibold inline-flex items-center gap-1" style={{ color: signColor(momentum) }}>
                        <Icon name={momentum >= 0 ? 'arrow-up' : 'arrow-down'} size={14} />{fmtScore1(momentum)}
                      </div>
                    )}
                    <div className="mt-1"><TagChip tag={tag} /></div>
                  </div>
                </div>
                <div className="mt-4">
                  {s.length > 1 ? <Sparkline points={s.map(x => x.score)} color={toneColor(scoreTone(score))} band={[-2, 2]} baseline={0} height={56} /> : <div className="h-14 grid place-items-center text-[12px] text-ink-3">No 30-day trend</div>}
                </div>
                <Mini title="Pros" items={pros} tone="var(--pos)" />
                <Mini title="Cons" items={cons} tone="var(--neg)" />
              </article>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function Mini({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div className="mt-4">
      <h3 className="text-[12.5px] font-semibold text-ink-2 m-0 mb-1.5">{title}</h3>
      {items.length === 0 ? <p className="m-0 text-[13px] text-ink-3">None recorded.</p> : (
        <ul className="m-0 p-0 list-none">
          {items.map((it, i) => <li key={i} className="flex gap-2 text-[13px] text-ink leading-snug py-1"><span className="mt-[7px] size-1.5 rounded-full shrink-0" style={{ background: tone }} />{it}</li>)}
        </ul>
      )}
    </div>
  )
}
