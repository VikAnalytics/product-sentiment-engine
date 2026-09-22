'use client'

import { useEffect, useState } from 'react'
import { fetchMacroThemes, MacroTheme } from '@/lib/supabase'
import { fmtScore1, relativeTime, scoreLabel, scoreTone, toneColor } from '@/lib/utils'
import { Empty, ErrorState, Icon, Loading } from '@/components/ui'

export default function Macro() {
  const [themes, setThemes] = useState<MacroTheme[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMacroThemes().then(setThemes).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Loading label="Loading macro themes" />
  if (error) return <ErrorState message={error} />

  const sorted = [...themes].sort((a, b) => (a.avg7d ?? 0) - (b.avg7d ?? 0))
  const withData = sorted.filter(t => t.avg7d != null)
  const headwinds = withData.filter(t => (t.avg7d ?? 0) <= -2).length
  const tailwinds = withData.filter(t => (t.avg7d ?? 0) >= 2).length

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-[1320px] mx-auto px-4 md:px-6 py-5 md:py-6">
        <div className="rise">
          <h1 className="display text-[34px] md:text-[40px] font-semibold m-0">Macro themes</h1>
          <p className="m-0 mt-2 text-[14.5px] text-ink-2 max-w-[70ch]">
            Geopolitics and policy that move whole sectors. Each theme carries its own 7-day sentiment, weighted into the simulator for the sectors it touches.
            {withData.length > 0 && <> Right now: {headwinds} headwind{headwinds === 1 ? '' : 's'}, {tailwinds} tailwind{tailwinds === 1 ? '' : 's'}.</>}
          </p>
        </div>

        {themes.length === 0 ? (
          <Empty title="No macro themes seeded" hint="Apply migration 017 and run scripts/seed_macro_targets.py to create the eight themes." />
        ) : (
          <div className="grid gap-4 mt-6 md:grid-cols-2 stagger">
            {sorted.map(t => {
              const tone = scoreTone(t.avg7d == null ? null : Math.round(t.avg7d))
              const color = t.avg7d == null ? 'var(--ink-3)' : toneColor(tone)
              return (
                <article key={t.id} className="hero p-5 flex flex-col">
                  <header className="flex items-start gap-3">
                    <span className="mt-1 text-macro"><Icon name="globe" size={20} /></span>
                    <div className="flex-1 min-w-0">
                      <h2 className="headline text-[19px] font-semibold text-ink m-0">{t.name}</h2>
                      <div className="text-[12.5px] text-ink-3 mt-0.5 tnum">{t.readings7d} reading{t.readings7d === 1 ? '' : 's'} this week, {t.eventCount} event{t.eventCount === 1 ? '' : 's'} total</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="figure text-[32px] font-semibold" style={{ color }}>{fmtScore1(t.avg7d)}</div>
                      <div className="text-[11.5px] text-ink-2">{t.avg7d == null ? 'No reading yet' : scoreLabel(Math.round(t.avg7d))}</div>
                    </div>
                  </header>

                  {t.description && <p className="m-0 mt-3 text-[13.5px] text-ink-2 leading-relaxed">{t.description}</p>}

                  {t.series.length > 1 && (
                    <div className="mt-4">
                      <MiniLine points={t.series.map(s => s.score)} color={color} />
                    </div>
                  )}

                  {t.exposures.length > 0 && (
                    <div className="mt-4">
                      <h3 className="text-[12.5px] font-semibold text-ink-2 m-0 mb-2">Sector exposure</h3>
                      <ul className="m-0 p-0 list-none flex flex-col gap-1.5">
                        {t.exposures.map(e => (
                          <li key={e.sector} className="grid grid-cols-[minmax(0,1fr)_120px_36px] items-center gap-3 text-[13px]">
                            <span className="truncate text-ink">{e.sector}</span>
                            <span className="h-1.5 rounded-full bg-sunken overflow-hidden"><span className="block h-full rounded-full bg-macro" style={{ width: `${Math.round(e.weight * 100)}%` }} /></span>
                            <span className="tnum text-right text-ink-3">{e.weight.toFixed(2)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {t.latest.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-line">
                      <h3 className="text-[12.5px] font-semibold text-ink-2 m-0 mb-1.5">Latest</h3>
                      <ul className="m-0 p-0 list-none">
                        {t.latest.map(ev => (
                          <li key={ev.id} className="flex gap-3 py-1.5 text-[13.5px]">
                            <span className="text-ink-3 shrink-0 w-12 tnum">{relativeTime(ev.created_at)}</span>
                            <span className="headline text-ink">{ev.headline}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function MiniLine({ points, color }: { points: number[]; color: string }) {
  const W = 400, H = 40
  const min = Math.min(-10, ...points), max = Math.max(10, ...points)
  const x = (i: number) => (i / (points.length - 1)) * W
  const y = (v: number) => H - ((v - min) / (max - min)) * H
  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="block w-full" style={{ height: H }} aria-hidden>
      <line x1="0" x2={W} y1={y(0)} y2={y(0)} stroke="var(--ink-3)" strokeOpacity="0.4" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />
      <path d={d} pathLength={1} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" className="draw" style={{ ['--len' as string]: '1' }} />
    </svg>
  )
}
