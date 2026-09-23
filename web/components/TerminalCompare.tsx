'use client'

import { useEffect, useState } from 'react'
import { Target, TargetScore, fetchScoreSeriesBatch } from '@/lib/supabase'

function fmtSigned(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  const s = Math.abs(n).toFixed(digits)
  return `${n > 0 ? '+' : n < 0 ? '−' : ' '}${s}`
}

function signClass(n: number | null | undefined): string {
  if (n == null) return 'term-faint'
  if (n > 0.05) return 'term-pos'
  if (n < -0.05) return 'term-neg'
  return 'term-dim'
}

/** One row of the comparison: label on the left, a cell per company. */
function Line({ label, cells }: { label: string; cells: { key: number; text: string; cls?: string }[] }) {
  return (
    <div className="grid gap-x-3 py-[3px]" style={{ gridTemplateColumns: `13ch repeat(${cells.length}, minmax(0,1fr))` }}>
      <span className="term-head">{label}</span>
      {cells.map(c => <span key={c.key} className={`tabular-nums ${c.cls ?? ''}`}>{c.text}</span>)}
    </div>
  )
}

export default function TerminalCompare({ targets, scores }: { targets: Target[]; scores: Record<number, TargetScore> }) {
  const [series, setSeries] = useState<Record<number, { date: string; score: number }[]>>({})

  useEffect(() => {
    let live = true
    fetchScoreSeriesBatch(targets.map(t => t.id), 30)
      .then(s => { if (live) setSeries(s) })
      .catch(() => setSeries({}))
    return () => { live = false }
  }, [targets])

  const best = targets.reduce<{ id: number; avg: number } | null>((acc, t) => {
    const a = scores[t.id]?.avg1
    return a != null && (!acc || a > acc.avg) ? { id: t.id, avg: a } : acc
  }, null)

  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2">
      <div className="grid gap-x-3 pb-1.5 border-b" style={{ gridTemplateColumns: `13ch repeat(${targets.length}, minmax(0,1fr))`, borderColor: 'var(--t-rule)' }}>
        <span className="term-head">Compare</span>
        {targets.map(t => (
          <span key={t.id} className="term-white truncate">{t.ticker ?? t.name}</span>
        ))}
      </div>

      <div className="mt-1.5">
        <Line label="Name" cells={targets.map(t => ({ key: t.id, text: t.name, cls: 'truncate' }))} />
        <Line label="Sector" cells={targets.map(t => ({ key: t.id, text: t.sector ?? '—', cls: 'term-dim truncate' }))} />
        <Line label="Sentiment" cells={targets.map(t => ({ key: t.id, text: fmtSigned(scores[t.id]?.avg1), cls: signClass(scores[t.id]?.avg1) }))} />
        <Line label="7d change" cells={targets.map(t => ({ key: t.id, text: fmtSigned(scores[t.id]?.chg), cls: signClass(scores[t.id]?.chg) }))} />
        <Line label="Readings" cells={targets.map(t => ({ key: t.id, text: String(scores[t.id]?.count ?? 0), cls: 'term-dim' }))} />
        <Line label="Listed" cells={targets.map(t => ({ key: t.id, text: t.ticker ?? 'private', cls: t.ticker ? 'term-white' : 'term-faint' }))} />
      </div>

      <div className="grid gap-x-3 mt-3" style={{ gridTemplateColumns: `13ch repeat(${targets.length}, minmax(0,1fr))` }}>
        <span className="term-head">30d</span>
        {targets.map(t => {
          const s = series[t.id] ?? []
          if (s.length < 2) return <span key={t.id} className="term-faint">not enough readings</span>
          const step = 100 / s.length
          return (
            <svg key={t.id} viewBox="0 0 100 26" preserveAspectRatio="none" className="w-full h-[40px]" role="img" aria-label={`${t.name} sentiment`}>
              <line x1="0" x2="100" y1="13" y2="13" stroke="var(--t-faint)" strokeWidth="0.3" />
              {s.map((d, i) => {
                const height = Math.max(0.5, (Math.abs(d.score) / 10) * 13)
                return <rect key={d.date} x={i * step + step * 0.2} width={step * 0.6}
                             y={d.score >= 0 ? 13 - height : 13} height={height}
                             fill={d.score > 0 ? 'var(--t-pos)' : d.score < 0 ? 'var(--t-neg)' : 'var(--t-dim)'} />
              })}
            </svg>
          )
        })}
      </div>

      {best && (
        <p className="term-dim m-0 mt-3">
          Strongest reading: <span className="term-white">{targets.find(t => t.id === best.id)?.name}</span> at {fmtSigned(best.avg)}.
        </p>
      )}
    </div>
  )
}
