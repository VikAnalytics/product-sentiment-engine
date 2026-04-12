'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchRecentHeadlines } from '@/lib/supabase'
import { fmtScore, relativeTime, scoreClass, tagClass, tagLabel } from '@/lib/utils'
import Logo from '@/components/Logo'

interface Props {
  sectorFilter?: string | null
}

export default function NewsFeed({ sectorFilter }: Props) {
  const [items, setItems] = useState<Awaited<ReturnType<typeof fetchRecentHeadlines>>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchRecentHeadlines(48)
      .then(setItems)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    if (!sectorFilter) return items
    return items.filter(i => i.target?.sector === sectorFilter)
  }, [items, sectorFilter])

  // group by date
  const grouped = useMemo(() => {
    const map: Record<string, typeof filtered> = {}
    for (const item of filtered) {
      const d = item.created_at.slice(0, 10)
      map[d] = map[d] ?? []
      map[d].push(item)
    }
    return Object.entries(map).sort(([a], [b]) => b.localeCompare(a))
  }, [filtered])

  const today = new Date().toISOString().slice(0, 10)

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.2em' }}>LOADING SIGNALS…</span>
    </div>
  )

  if (error) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--red)' }}>{error}</span>
    </div>
  )

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', flexDirection: 'column', animation: 'fadein 0.2s ease' }}>
      <div style={{ padding: '14px 24px 12px', borderBottom: '1px solid var(--br)', display: 'flex', alignItems: 'baseline', gap: 14, flexShrink: 0 }}>
        <span style={{ fontFamily: 'var(--ff-d)', fontSize: 30, fontWeight: 300, letterSpacing: '0.04em', lineHeight: 1 }}>
          Intelligence <em style={{ fontStyle: 'italic', color: 'var(--gold)' }}>Feed</em>
        </span>
        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--tm)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          <b style={{ color: 'var(--t2)', fontWeight: 400 }}>{filtered.length} signals</b>
        </span>
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {grouped.map(([date, cards], gi) => (
          <div key={date}>
            <div style={{
              padding: '8px 24px',
              fontFamily: 'var(--ff-m)',
              fontSize: 11,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: 'var(--tm)',
              borderBottom: '1px solid var(--br)',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}>
              {date === today ? 'Today' : date} &nbsp;·&nbsp; {new Date(date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
              <span style={{ flex: 1, height: 1, background: 'var(--br)', display: 'block' }} />
            </div>
            {cards.map((item, i) => {
              const sc = item.topScore
              const tag = item.topTag
              const isPos = sc != null && sc > 0
              const isNeg = sc != null && sc < 0
              return (
                <div
                  key={item.id}
                  style={{
                    display: 'flex',
                    borderBottom: '1px solid var(--br)',
                    cursor: 'pointer',
                    transition: 'background 0.1s',
                    animation: `cin 0.3s ${0.05 + i * 0.05}s ease both`,
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-h)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <div style={{
                    width: 4,
                    flexShrink: 0,
                    background: isPos ? 'var(--green)' : isNeg ? 'var(--red)' : 'var(--tm)',
                    opacity: 0.6,
                  }} />
                  <div style={{ flex: 1, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6, flexWrap: 'wrap' }}>
                      {item.target && (
                        <Logo logoUrl={item.target.logo_url} domain={item.target.domain} name={item.target.name} size={18} radius="sm" />
                      )}
                      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--t1)' }}>
                        {item.target?.name ?? '—'}
                      </span>
                      {item.target?.sector && (
                        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--tm)', background: 'var(--bg-r)', border: '1px solid var(--br)', padding: '2px 6px', borderRadius: 1 }}>
                          {item.target.sector}
                        </span>
                      )}
                      {item.target?.is_f500 && (
                        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--gold)', border: '1px solid var(--br-m)', padding: '2px 6px', borderRadius: 1 }}>F500</span>
                      )}
                      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--tm)', marginLeft: 'auto' }}>
                        {relativeTime(item.created_at)}
                      </span>
                    </div>
                    <div style={{ fontFamily: 'var(--ff-d)', fontSize: 20, fontWeight: 400, lineHeight: 1.3, marginBottom: 5, letterSpacing: '0.01em' }}>
                      {item.headline}
                    </div>
                    {item.target?.description && (
                      <div style={{ fontFamily: 'var(--ff-b)', fontSize: 13, color: 'var(--t2)', fontWeight: 300, fontStyle: 'italic', lineHeight: 1.5 }}>
                        {item.target.description.slice(0, 120)}{item.target.description.length > 120 ? '…' : ''}
                      </div>
                    )}
                  </div>
                  <div style={{ padding: '14px 16px 14px 0', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', justifyContent: 'space-between', minWidth: 84, gap: 8 }}>
                    <span className={scoreClass(sc)} style={{ fontFamily: 'var(--ff-m)', fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
                      {fmtScore(sc)}
                    </span>
                    {tag && (
                      <span className={tagClass(tag)} style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '3px 8px', borderRadius: 1, border: '1px solid' }}>
                        {tagLabel(tag)}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ))}
        {filtered.length === 0 && (
          <div style={{ padding: '60px 24px', textAlign: 'center' }}>
            <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.2em' }}>NO SIGNALS FOUND</span>
          </div>
        )}
      </div>
    </div>
  )
}
