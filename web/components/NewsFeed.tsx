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
  isMacro: boolean
  latestAt: string
  events: HeadlineItem[]
}

interface DateGroup {
  date: string
  companies: CompanyGroup[]
}

function groupByDateThenCompany(items: HeadlineItem[]): DateGroup[] {
  const dateMap: Record<string, Record<string, CompanyGroup>> = {}

  for (const item of items) {
    const date = item.created_at.slice(0, 10)
    const isProduct = item.target?.target_type === 'PRODUCT'
    const isMacro = item.target?.target_type === 'MACRO'
    const parent = isProduct ? item.target?.parent_target : null

    const companyKey = parent ? `p${parent.id}` : `t${item.target?.id}`
    const companyInfo: Omit<CompanyGroup, 'latestAt' | 'events'> = parent
      ? { id: parent.id, name: parent.name, logo_url: parent.logo_url, domain: parent.domain, sector: parent.sector ?? item.target?.sector ?? null, is_f500: parent.is_f500 ?? item.target?.is_f500 ?? false, isMacro: false }
      : { id: item.target?.id ?? 0, name: item.target?.name ?? '—', logo_url: item.target?.logo_url ?? null, domain: item.target?.domain ?? null, sector: item.target?.sector ?? null, is_f500: item.target?.is_f500 ?? false, isMacro }

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

  const techItems = useMemo(
    () => filtered.filter(i => i.target?.target_type !== 'MACRO'),
    [filtered]
  )
  const macroItems = useMemo(
    () => filtered.filter(i => i.target?.target_type === 'MACRO'),
    [filtered]
  )

  const techGrouped = useMemo(() => groupByDateThenCompany(techItems), [techItems])
  const macroGrouped = useMemo(() => groupByDateThenCompany(macroItems), [macroItems])

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
          <b style={{ color: 'var(--t2)', fontWeight: 400 }}>{techItems.length}</b> tech
          &nbsp;·&nbsp;
          <b style={{ color: 'var(--t2)', fontWeight: 400 }}>{macroItems.length}</b> macro
        </span>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <div style={{ flex: '1 1 70%', minWidth: 0, overflowY: 'auto', borderRight: '1px solid var(--br)' }}>
          <FeedSection title="Tech & Companies" accent="var(--gold)" grouped={techGrouped} emptyLabel="NO TECH SIGNALS" />
        </div>
        <div style={{ flex: '0 0 360px', minWidth: 0, overflowY: 'auto' }}>
          <FeedSection title="Geopolitics & Macro" accent="#a78bfa" grouped={macroGrouped} emptyLabel="NO MACRO SIGNALS" />
        </div>
      </div>
    </div>
  )
}

function FeedSection({
  title,
  accent,
  grouped,
  emptyLabel,
}: {
  title: string
  accent: string
  grouped: DateGroup[]
  emptyLabel: string
}) {
  const today = new Date().toISOString().slice(0, 10)

  return (
    <section>
      <div style={{
        padding: '14px 24px 10px',
        fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.22em',
        textTransform: 'uppercase', color: accent,
        borderBottom: `1px solid ${accent}33`,
        background: `${accent}0a`,
        display: 'flex', alignItems: 'center', gap: 10,
        position: 'sticky', top: 0, zIndex: 5,
      }}>
        {title}
        <span style={{ flex: 1, height: 1, background: `${accent}22`, display: 'block' }} />
      </div>

      {grouped.length === 0 && (
        <div style={{ padding: '40px 24px', textAlign: 'center' }}>
          <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.2em' }}>{emptyLabel}</span>
        </div>
      )}

      {grouped.map(({ date, companies }) => (
        <div key={date}>
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

          {companies.map((co, ci) => {
            const allScores = co.events.map(e => e.topScore).filter((s): s is number => s != null)
            const avgScore = allScores.length ? allScores.reduce((a, b) => a + b, 0) / allScores.length : null
            const isPos = avgScore != null && avgScore > 0
            const isNeg = avgScore != null && avgScore < 0
            const borderColor = co.isMacro ? accent : (isPos ? 'var(--green)' : isNeg ? 'var(--red)' : 'var(--tm)')

            return (
              <div key={co.id} style={{ borderBottom: '1px solid var(--br)', animation: `cin 0.3s ${0.05 + ci * 0.04}s ease both` }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '10px 18px 8px 22px',
                  borderLeft: `3px solid ${borderColor}`,
                }}>
                  {co.isMacro ? (
                    <span style={{ fontSize: 14, lineHeight: 1, marginRight: 2 }}>🌐</span>
                  ) : (
                    <Logo logoUrl={co.logo_url} domain={co.domain} name={co.name} size={20} radius="sm" />
                  )}
                  <span style={{ fontFamily: 'var(--ff-m)', fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--t1)' }}>
                    {co.name}
                  </span>
                  {co.isMacro ? (
                    <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.07em', textTransform: 'uppercase', color: accent, background: `${accent}1a`, border: `1px solid ${accent}55`, padding: '2px 6px', borderRadius: 1 }}>
                      Macro Theme
                    </span>
                  ) : (
                    <>
                      {co.sector && (
                        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--tm)', background: 'var(--bg-r)', border: '1px solid var(--br)', padding: '2px 6px', borderRadius: 1 }}>
                          {co.sector}
                        </span>
                      )}
                      {co.is_f500 && (
                        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--gold)', border: '1px solid var(--br-m)', padding: '2px 6px', borderRadius: 1 }}>F500</span>
                      )}
                    </>
                  )}
                  <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--tm)', marginLeft: 'auto' }}>
                    {relativeTime(co.latestAt)}
                  </span>
                </div>

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
    </section>
  )
}
