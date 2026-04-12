'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchRecentHeadlines } from '@/lib/supabase'
import { fmtScore, relativeTime, scoreClass, tagClass, tagLabel } from '@/lib/utils'
import Logo from '@/components/Logo'

interface Props {
  sectorFilter?: string | null
}

type HeadlineItem = Awaited<ReturnType<typeof fetchRecentHeadlines>>[number]

interface CompanyGroup {
  id: number
  name: string
  logo_url: string | null
  domain: string | null
  sector: string | null
  is_f500: boolean
  latestAt: string
  events: HeadlineItem[]
}

interface DateGroup {
  date: string
  companies: CompanyGroup[]
}

export default function NewsFeed({ sectorFilter }: Props) {
  const [items, setItems] = useState<HeadlineItem[]>([])
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
    return items.filter(i => {
      const sector = i.target?.parent_target?.sector ?? i.target?.sector
      return sector === sectorFilter
    })
  }, [items, sectorFilter])

  // Group by date → company
  const grouped = useMemo((): DateGroup[] => {
    const dateMap: Record<string, Record<string, CompanyGroup>> = {}

    for (const item of filtered) {
      const date = item.created_at.slice(0, 10)
      const isProduct = item.target?.target_type === 'PRODUCT'
      const parent = isProduct ? item.target?.parent_target : null

      // Root company identity
      const companyKey = parent ? `p${parent.id}` : `t${item.target?.id}`
      const companyInfo: Omit<CompanyGroup, 'latestAt' | 'events'> = parent
        ? { id: parent.id, name: parent.name, logo_url: parent.logo_url, domain: parent.domain, sector: parent.sector ?? item.target?.sector ?? null, is_f500: parent.is_f500 ?? item.target?.is_f500 ?? false }
        : { id: item.target?.id ?? 0, name: item.target?.name ?? '—', logo_url: item.target?.logo_url ?? null, domain: item.target?.domain ?? null, sector: item.target?.sector ?? null, is_f500: item.target?.is_f500 ?? false }

      dateMap[date] = dateMap[date] ?? {}
      if (!dateMap[date][companyKey]) {
        dateMap[date][companyKey] = { ...companyInfo, latestAt: item.created_at, events: [] }
      }
      dateMap[date][companyKey].events.push(item)
      if (item.created_at > dateMap[date][companyKey].latestAt) {
        dateMap[date][companyKey].latestAt = item.created_at
      }
    }

    return Object.entries(dateMap)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([date, companies]) => ({
        date,
        companies: Object.values(companies).sort((a, b) => b.latestAt.localeCompare(a.latestAt)),
      }))
  }, [filtered])

  const today = new Date().toISOString().slice(0, 10)
  const totalSignals = filtered.length

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
          <b style={{ color: 'var(--t2)', fontWeight: 400 }}>{totalSignals} signals</b>
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {grouped.map(({ date, companies }) => (
          <div key={date}>
            {/* Date header */}
            <div style={{
              padding: '8px 24px',
              fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.14em',
              textTransform: 'uppercase', color: 'var(--tm)',
              borderBottom: '1px solid var(--br)',
              display: 'flex', alignItems: 'center', gap: 10,
            }}>
              {date === today ? 'Today' : date}&nbsp;·&nbsp;
              {new Date(date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
              <span style={{ flex: 1, height: 1, background: 'var(--br)', display: 'block' }} />
            </div>

            {/* Company blocks */}
            {companies.map((co, ci) => {
              const allScores = co.events.map(e => e.topScore).filter((s): s is number => s != null)
              const avgScore = allScores.length ? allScores.reduce((a, b) => a + b, 0) / allScores.length : null
              const isPos = avgScore != null && avgScore > 0
              const isNeg = avgScore != null && avgScore < 0

              return (
                <div key={co.id} style={{ borderBottom: '1px solid var(--br)', animation: `cin 0.3s ${0.05 + ci * 0.04}s ease both` }}>
                  {/* Company header */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '10px 18px 8px 22px',
                    borderLeft: `3px solid ${isPos ? 'var(--green)' : isNeg ? 'var(--red)' : 'var(--tm)'}`,
                  }}>
                    <Logo logoUrl={co.logo_url} domain={co.domain} name={co.name} size={20} radius="sm" />
                    <span style={{ fontFamily: 'var(--ff-m)', fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--t1)' }}>
                      {co.name}
                    </span>
                    {co.sector && (
                      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--tm)', background: 'var(--bg-r)', border: '1px solid var(--br)', padding: '2px 6px', borderRadius: 1 }}>
                        {co.sector}
                      </span>
                    )}
                    {co.is_f500 && (
                      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--gold)', border: '1px solid var(--br-m)', padding: '2px 6px', borderRadius: 1 }}>F500</span>
                    )}
                    <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--tm)', marginLeft: 'auto' }}>
                      {relativeTime(co.latestAt)}
                    </span>
                  </div>

                  {/* Event rows */}
                  {co.events.map((item) => {
                    const sc = item.topScore
                    const tag = item.topTag
                    const isProduct = item.target?.target_type === 'PRODUCT'
                    const productName = isProduct ? item.target?.name : null

                    return (
                      <div
                        key={item.id}
                        style={{ display: 'flex', borderTop: '1px solid var(--br)', cursor: 'pointer', transition: 'background 0.1s' }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-h)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                      >
                        <div style={{ width: 3, flexShrink: 0, marginLeft: 22, background: 'var(--br)' }} />
                        <div style={{ flex: 1, padding: '10px 14px' }}>
                          {productName && (
                            <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--gold)', marginBottom: 3, display: 'block' }}>
                              {productName}
                            </span>
                          )}
                          <div style={{ fontFamily: 'var(--ff-d)', fontSize: 18, fontWeight: 400, lineHeight: 1.3, letterSpacing: '0.01em' }}>
                            {item.headline}
                          </div>
                        </div>
                        <div style={{ padding: '10px 16px 10px 0', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', justifyContent: 'center', minWidth: 80, gap: 6 }}>
                          <span className={scoreClass(sc)} style={{ fontFamily: 'var(--ff-m)', fontSize: 20, fontWeight: 700, lineHeight: 1 }}>
                            {fmtScore(sc)}
                          </span>
                          {tag && (
                            <span className={tagClass(tag)} style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '2px 7px', borderRadius: 1, border: '1px solid' }}>
                              {tagLabel(tag)}
                            </span>
                          )}
                        </div>
                      </div>
                    )
                  })}
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
