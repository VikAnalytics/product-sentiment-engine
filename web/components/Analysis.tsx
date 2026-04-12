'use client'

import { useEffect, useState, useMemo } from 'react'
import {
  fetchTargetWithEvents,
  fetchScoreSeries,
  fetchPriceSeries,
  Target,
  StockPrice,
} from '@/lib/supabase'
import { fmtScore, fmtPct, scoreClass, tagClass, tagLabel, relativeTime, confidenceDot } from '@/lib/utils'
import Logo from '@/components/Logo'

/** Returns RGBA color string keyed to score intensity */
function sentimentColor(score: number | null): string {
  if (score == null) return 'rgba(72,70,63,0)'   // neutral/invisible
  if (score >= 7)  return 'rgba(91,140,68,'       // deep green
  if (score >= 3)  return 'rgba(122,184,72,'      // lime green
  if (score >= -2) return 'rgba(138,135,120,'     // neutral gray
  if (score >= -6) return 'rgba(176,120,32,'      // amber
  return 'rgba(193,64,64,'                        // red
}

/** Hero background gradient based on sentiment */
function heroBg(score: number | null): string {
  const base = sentimentColor(score)
  if (score == null) return 'transparent'
  const intensity = Math.min(Math.abs(score) / 10, 1)
  const opacity = (0.04 + intensity * 0.08).toFixed(3)
  return `linear-gradient(135deg, ${base}${opacity}) 0%, var(--bg) 65%)`
}

/** Left accent bar color based on score */
function accentColor(score: number | null): string {
  if (score == null) return 'var(--tm)'
  if (score >= 7)  return 'var(--green)'
  if (score >= 3)  return '#7AB848'
  if (score >= -2) return 'var(--t2)'
  if (score >= -6) return 'var(--amber)'
  return 'var(--red)'
}

/** Sparkline stroke color based on score */
function sparkColor(score: number | null): string {
  if (score == null) return 'var(--gold)'
  if (score >= 3)  return 'var(--green)'
  if (score >= -2) return 'var(--t2)'
  return 'var(--red)'
}

interface Props {
  targetId: number | null
}

type EventWithMeta = {
  id: number
  headline: string
  created_at: string
  cached_analysis: string | null
  avgScore: number | null
  topTag: string | null
  reaction: {
    window_return_pct: number | null
    reaction_1d: number | null
    reaction_3d: number | null
    reaction_7d: number | null
    confidence: string | null
    market_session: string | null
  } | null
}

export default function Analysis({ targetId }: Props) {
  const [target, setTarget] = useState<Target | null>(null)
  const [events, setEvents] = useState<EventWithMeta[]>([])
  const [scoreSeries, setScoreSeries] = useState<{ date: string; score: number }[]>([])
  const [prices, setPrices] = useState<StockPrice[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [chartRange, setChartRange] = useState<30 | 90 | 365>(30)

  useEffect(() => {
    if (targetId == null) return
    setLoading(true)
    setExpandedId(null)
    Promise.all([
      fetchTargetWithEvents(targetId),
      fetchScoreSeries(targetId, 90),
      fetchPriceSeries(targetId),
    ]).then(([{ target, events }, series, px]) => {
      setTarget(target)
      setEvents(events as EventWithMeta[])
      setScoreSeries(series)
      setPrices(px)
    }).finally(() => setLoading(false))
  }, [targetId])

  const avgScore = useMemo(() => {
    const scored = events.filter(e => e.avgScore != null).map(e => e.avgScore!)
    if (!scored.length) return null
    return Math.round(scored.reduce((a, b) => a + b, 0) / scored.length)
  }, [events])

  // momentum: avg(last 7 days score) - avg(prior 7 days score)
  const momentum = useMemo(() => {
    const now = Date.now()
    const d7 = now - 7 * 86400000
    const d14 = now - 14 * 86400000
    const recent = scoreSeries.filter(s => new Date(s.date).getTime() >= d7).map(s => s.score)
    const prior = scoreSeries.filter(s => new Date(s.date).getTime() >= d14 && new Date(s.date).getTime() < d7).map(s => s.score)
    if (!recent.length || !prior.length) return null
    return (
      recent.reduce((a, b) => a + b, 0) / recent.length -
      prior.reduce((a, b) => a + b, 0) / prior.length
    )
  }, [scoreSeries])

  const filteredSeries = useMemo(() => {
    const since = Date.now() - chartRange * 86400000
    return scoreSeries.filter(s => new Date(s.date).getTime() >= since)
  }, [scoreSeries, chartRange])

  // build sparkline path
  const sparkPath = useMemo(() => {
    if (filteredSeries.length < 2) return ''
    const W = 800, H = 60
    const scores = filteredSeries.map(s => s.score)
    const min = Math.min(-10, ...scores)
    const max = Math.max(10, ...scores)
    const xScale = (i: number) => (i / (filteredSeries.length - 1)) * W
    const yScale = (v: number) => H - ((v - min) / (max - min)) * H
    return filteredSeries.map((s, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(s.score)}`).join(' ')
  }, [filteredSeries])

  // price chart path (daily close, last N bars)
  const priceChartData = useMemo(() => {
    if (prices.length === 0) return null
    // aggregate to daily close (last bar of each day)
    const daily: Record<string, number> = {}
    for (const p of prices) {
      const d = p.ts.slice(0, 10)
      daily[d] = p.close
    }
    const entries = Object.entries(daily).sort(([a], [b]) => a.localeCompare(b)).slice(-60)
    if (entries.length < 2) return null
    const closes = entries.map(([, c]) => c)
    const minC = Math.min(...closes)
    const maxC = Math.max(...closes)
    const W = 800, H = 80
    const xScale = (i: number) => (i / (entries.length - 1)) * W
    const yScale = (v: number) => maxC === minC ? H / 2 : H - ((v - minC) / (maxC - minC)) * H
    const path = entries.map(([, c], i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(c)}`).join(' ')
    const current = closes[closes.length - 1]
    const prev = closes[closes.length - 2]
    const changePct = (current - prev) / prev
    return { path, current, changePct, entries }
  }, [prices])

  if (targetId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.2em' }}>
          SELECT A TARGET FROM SIDEBAR
        </span>
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.2em' }}>LOADING…</span>
      </div>
    )
  }

  if (!target) return null

  const accent = accentColor(avgScore)
  const spark = sparkColor(avgScore)

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', flexDirection: 'column', animation: 'fadein 0.2s ease' }}>
      {/* view header — left accent bar colored by sentiment */}
      <div style={{
        padding: '14px 24px 12px',
        borderBottom: '1px solid var(--br)',
        display: 'flex',
        alignItems: 'baseline',
        gap: 14,
        flexShrink: 0,
        borderLeft: `3px solid ${accent}`,
        transition: 'border-color 0.4s ease',
      }}>
        <span style={{ fontFamily: 'var(--ff-d)', fontSize: 30, fontWeight: 300, letterSpacing: '0.04em', lineHeight: 1 }}>
          Deep <em style={{ fontStyle: 'italic', color: 'var(--gold)' }}>Dive</em>
        </span>
        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 12, color: 'var(--tm)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          <b style={{ color: 'var(--t2)', fontWeight: 400 }}>{events.length} events</b>
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* hero — gradient background keyed to sentiment */}
        <div style={{
          padding: '22px 24px 18px',
          borderBottom: '1px solid var(--br)',
          display: 'flex',
          gap: 28,
          alignItems: 'flex-start',
          background: heroBg(avgScore),
          transition: 'background 0.5s ease',
          position: 'relative',
        }}>
          <div style={{ flex: 1 }}>
            {/* logo + ticker row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <Logo
                logoUrl={target.logo_url}
                domain={target.domain}
                name={target.name}
                size={48}
                radius="md"
                style={{ border: '1px solid var(--br-m)', padding: 4, background: 'var(--bg-r)' }}
              />
              {target.ticker && (
                <div>
                  <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--tm)', letterSpacing: '0.2em' }}>
                    {target.ticker}
                  </div>
                  <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.12em' }}>
                    {target.sector ?? '—'}
                  </div>
                </div>
              )}
              {!target.ticker && target.sector && (
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.12em' }}>
                  {target.sector}
                </div>
              )}
            </div>
            <div style={{ fontFamily: 'var(--ff-d)', fontSize: 46, fontWeight: 300, lineHeight: 1, letterSpacing: '0.02em', marginBottom: 8 }}>
              {target.name}
            </div>
            {target.description && (
              <div style={{ fontFamily: 'var(--ff-b)', fontSize: 13.5, color: 'var(--t2)', fontWeight: 300, fontStyle: 'italic', maxWidth: 480, lineHeight: 1.65 }}>
                {target.description}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 22, flexShrink: 0 }}>
            {avgScore != null && (
              <div style={{ textAlign: 'right' }}>
                <div className={scoreClass(avgScore)} style={{ fontFamily: 'var(--ff-m)', fontSize: 34, fontWeight: 700, lineHeight: 1 }}>
                  {fmtScore(avgScore)}
                </div>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--tm)', marginTop: 5 }}>Avg Score</div>
              </div>
            )}
            {momentum != null && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 34, fontWeight: 700, lineHeight: 1, color: momentum >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {momentum >= 0 ? '↑' : '↓'}
                </div>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--tm)', marginTop: 5 }}>7d Trend</div>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--t2)', marginTop: 3 }}>
                  {momentum >= 0 ? '+' : ''}{momentum.toFixed(1)} pts
                </div>
              </div>
            )}
            {priceChartData && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 34, fontWeight: 700, lineHeight: 1, color: priceChartData.changePct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  ${priceChartData.current.toFixed(2)}
                </div>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--tm)', marginTop: 5 }}>Price</div>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: priceChartData.changePct >= 0 ? 'var(--green)' : 'var(--red)', marginTop: 3 }}>
                  {fmtPct(priceChartData.changePct)} 1d
                </div>
              </div>
            )}
          </div>
        </div>

        {/* sentiment sparkline */}
        {filteredSeries.length > 1 && (
          <div style={{ padding: '0 24px', borderBottom: '1px solid var(--br)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0 8px' }}>
              <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--tm)', flex: 1 }}>
                Sentiment Trend
              </span>
              {([30, 90, 365] as const).map(r => (
                <button
                  key={r}
                  onClick={() => setChartRange(r)}
                  style={{
                    fontFamily: 'var(--ff-m)',
                    fontSize: 11,
                    letterSpacing: '0.1em',
                    padding: '2px 8px',
                    border: `1px solid ${chartRange === r ? 'var(--gold)' : 'var(--br)'}`,
                    background: chartRange === r ? 'var(--gold-d)' : 'transparent',
                    color: chartRange === r ? 'var(--gold)' : 'var(--tm)',
                    cursor: 'pointer',
                    borderRadius: 1,
                  }}
                >{r}D</button>
              ))}
            </div>
            <svg viewBox="0 0 800 60" style={{ width: '100%', height: 60, display: 'block', overflow: 'visible', marginBottom: 12 }}>
              {/* zero line */}
              <line x1="0" y1="30" x2="800" y2="30" stroke="rgba(200,168,75,0.15)" strokeWidth="1" strokeDasharray="4 4" />
              {/* neutral band */}
              <rect x="0" y="25" width="800" height="10" fill="rgba(138,135,120,0.06)" />
              {/* score line */}
              <path d={sparkPath} fill="none" stroke={spark} strokeWidth="2" opacity="0.85" />
            </svg>
          </div>
        )}

        {/* price chart */}
        {priceChartData && (
          <div style={{ padding: '0 24px', borderBottom: '1px solid var(--br)' }}>
            <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--tm)', padding: '12px 0 8px' }}>
              Price Chart — {target.ticker}
            </div>
            <svg viewBox="0 0 800 80" style={{ width: '100%', height: 80, display: 'block', overflow: 'visible', marginBottom: 12 }}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.15" />
                  <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d={priceChartData.path + ' V 80 L 0 80 Z'} fill="url(#priceGrad)" />
              <path d={priceChartData.path} fill="none" stroke="var(--gold)" strokeWidth="1.5" />
            </svg>
          </div>
        )}

        {/* events */}
        <div style={{ padding: '0 24px' }}>
          <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--tm)', padding: '14px 0 8px', borderBottom: '1px solid var(--br)' }}>
            Events Timeline
          </div>
          {events.map(ev => {
            const evAccent = accentColor(ev.avgScore)
            return (
            <div key={ev.id} style={{ borderBottom: '1px solid var(--br)' }}>
              <div
                style={{ display: 'grid', gridTemplateColumns: '80px 1fr 90px', gap: 16, padding: '14px 0', alignItems: 'start', cursor: 'pointer', borderLeft: `2px solid ${evAccent}`, paddingLeft: 12, transition: 'border-color 0.2s' }}
                onClick={() => setExpandedId(expandedId === ev.id ? null : ev.id)}
              >
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 12, color: 'var(--tm)', paddingTop: 3 }}>
                  {new Date(ev.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  <br />
                  <span style={{ fontSize: 11, letterSpacing: '0.1em' }}>{relativeTime(ev.created_at)}</span>
                </div>
                <div style={{ fontFamily: 'var(--ff-d)', fontSize: 18, fontWeight: 400, lineHeight: 1.35 }}>
                  {ev.headline}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                  {ev.avgScore != null && (
                    <span className={scoreClass(ev.avgScore)} style={{ fontFamily: 'var(--ff-m)', fontSize: 17, fontWeight: 700 }}>
                      {fmtScore(ev.avgScore)}
                    </span>
                  )}
                  {ev.topTag && (
                    <span className={tagClass(ev.topTag)} style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', padding: '2px 6px', border: '1px solid', borderRadius: 1 }}>
                      {tagLabel(ev.topTag)}
                    </span>
                  )}
                  {ev.reaction?.window_return_pct != null && (
                    <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: ev.reaction.window_return_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      {fmtPct(ev.reaction.window_return_pct / 100)} {confidenceDot(ev.reaction.confidence)}
                    </span>
                  )}
                </div>
              </div>
              {expandedId === ev.id && ev.cached_analysis && (
                <div style={{ padding: '0 0 16px 96px' }}>
                  <div style={{ background: 'var(--bg-r)', border: '1px solid var(--br)', padding: '14px 16px', borderRadius: 2 }}>
                    <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--gold)', marginBottom: 10 }}>
                      AI Analysis
                    </div>
                    <div style={{ fontFamily: 'var(--ff-b)', fontSize: 13.5, color: 'var(--t2)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                      {ev.cached_analysis}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )})}
        </div>
      </div>
    </div>
  )
}
