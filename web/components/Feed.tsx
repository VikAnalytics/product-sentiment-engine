'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchRecentHeadlines } from '@/lib/supabase'
import { avg, fmtDayLong, fmtScore1, moodHeadline, moodVars, relativeTime, scoreTone, SECTORS, toneColor } from '@/lib/utils'
import { Chip, Empty, ErrorState, Icon, Loading, Score, TagChip } from '@/components/ui'
import { SelectBox } from '@/components/Select'
import Logo from '@/components/Logo'

type Item = Awaited<ReturnType<typeof fetchRecentHeadlines>>[number]

interface Group {
  key: string
  id: number
  name: string
  logo_url: string | null
  domain: string | null
  sector: string | null
  is_f500: boolean
  isMacro: boolean
  latestAt: string
  events: Item[]
}

function groupByDayAndCompany(items: Item[]): { date: string; groups: Group[] }[] {
  const days: Record<string, Record<string, Group>> = {}
  for (const it of items) {
    const date = it.published_at.slice(0, 10)
    const t = it.target
    const parent = t?.target_type === 'PRODUCT' ? t.parent_target : null
    const key = parent ? `p${parent.id}` : `t${t?.id}`
    const base = parent
      ? { id: parent.id, name: parent.name, logo_url: parent.logo_url, domain: parent.domain, sector: parent.sector ?? t?.sector ?? null, is_f500: parent.is_f500 ?? false, isMacro: false }
      : { id: t?.id ?? 0, name: t?.name ?? '—', logo_url: t?.logo_url ?? null, domain: t?.domain ?? null, sector: t?.sector ?? null, is_f500: t?.is_f500 ?? false, isMacro: t?.target_type === 'MACRO' }
    days[date] ??= {}
    days[date][key] ??= { key, ...base, latestAt: it.published_at, events: [] }
    days[date][key].events.push(it)
    if (it.published_at > days[date][key].latestAt) days[date][key].latestAt = it.published_at
  }
  return Object.entries(days)
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, g]) => ({
      date,
      groups: Object.values(g)
        .map(group => ({ ...group, events: dedupeByStory(group.events) }))
        .sort((a, b) => b.latestAt.localeCompare(a.latestAt)),
    }))
}

/**
 * One row per story. An article that names a company and its product is filed
 * against both, so without this a card shows the same headline twice. Rows with
 * no source_url predate migration 023 and cannot be matched, so they all stay.
 */
function dedupeByStory(events: Item[]): Item[] {
  const seen = new Map<string, Item>()
  const out: Item[] = []
  for (const ev of events) {
    if (!ev.source_url) { out.push(ev); continue }
    const kept = seen.get(ev.source_url)
    if (!kept) {
      seen.set(ev.source_url, ev)
      out.push(ev)
      continue
    }
    // Keep whichever copy carries a reading, so the score survives the merge.
    if (kept.topScore == null && ev.topScore != null) {
      out[out.indexOf(kept)] = ev
      seen.set(ev.source_url, ev)
    }
  }
  return out
}

export default function Feed({ onSelectTarget, onOpenMacro }: { onSelectTarget: (id: number) => void; onOpenMacro: () => void }) {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sector, setSector] = useState('')

  useEffect(() => {
    fetchRecentHeadlines(48).then(setItems).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => sector ? items.filter(i => (i.target?.parent_target?.sector ?? i.target?.sector) === sector || i.target?.target_type === 'MACRO') : items, [items, sector])
  const company = useMemo(() => filtered.filter(i => i.target?.target_type !== 'MACRO'), [filtered])
  const macro = useMemo(() => filtered.filter(i => i.target?.target_type === 'MACRO'), [filtered])
  const companyDays = useMemo(() => groupByDayAndCompany(company), [company])
  const macroDays = useMemo(() => groupByDayAndCompany(macro), [macro])

  // Mood = the latest day with company signals.
  const mood = useMemo(() => {
    const latestDate = companyDays[0]?.date
    const day = latestDate ? company.filter(i => i.published_at.slice(0, 10) === latestDate) : []
    const scored = day.map(i => i.topScore).filter((s): s is number => s != null)
    const a = avg(scored)
    return {
      date: latestDate,
      avg: a,
      count: day.length,
      threats: day.filter(i => i.topTag === 'threat').length,
      opportunities: day.filter(i => i.topTag === 'opportunity').length,
      macroCount: latestDate ? macro.filter(i => i.published_at.slice(0, 10) === latestDate).length : 0,
    }
  }, [companyDays, company, macro])

  if (loading) return <Loading label="Loading signals" />
  if (error) return <ErrorState message={error} />

  const today = new Date().toISOString().slice(0, 10)
  const dayLabel = mood.date ? (mood.date === today ? 'Today' : fmtDayLong(mood.date)) : 'Recent'

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-[1320px] mx-auto px-4 md:px-6 py-5 md:py-6">

        {/* Mood panel: the page's ambient color is today's sentiment. */}
        <section className="mood rise p-5 md:p-7" style={moodVars(mood.avg) as React.CSSProperties} aria-label="Today at a glance">
          <div className="flex flex-col md:flex-row md:items-end gap-5 md:gap-8">
            <div className="flex-1 min-w-0">
              <div className="text-[13px] text-ink-2">{dayLabel}{mood.date && mood.date !== today ? ' (latest signals)' : ''}</div>
              <h1 className="display text-[34px] md:text-[44px] font-semibold text-ink m-0 mt-1">{moodHeadline(mood.avg, mood.count)}</h1>
              <p className="m-0 mt-2 text-[14.5px] text-ink-2 max-w-[60ch]">
                {mood.count === 0
                  ? 'No company headlines were tracked in the last 48 hours. The pipeline runs daily after market close.'
                  : <>{mood.count} company signal{mood.count === 1 ? '' : 's'} and {mood.macroCount} macro signal{mood.macroCount === 1 ? '' : 's'}. {mood.opportunities > 0 && <>{mood.opportunities} flagged as opportunities</>}{mood.opportunities > 0 && mood.threats > 0 && ', '}{mood.threats > 0 && <>{mood.threats} as threats</>}{(mood.opportunities > 0 || mood.threats > 0) && '.'}</>}
              </p>
            </div>
            {mood.avg != null && (
              <div className="flex items-end gap-6 md:gap-8">
                <Stat label="Average signal" value={fmtScore1(mood.avg)} color={toneColor(scoreTone(mood.avg))} big />
                <Stat label="Opportunities" value={String(mood.opportunities)} color="var(--pos)" />
                <Stat label="Threats" value={String(mood.threats)} color="var(--neg)" />
              </div>
            )}
          </div>
        </section>

        {/* Filter row */}
        <div className="flex items-center gap-3 mt-6 mb-3">
          <SelectBox value={sector} onChange={setSector} placeholder="All sectors" options={SECTORS.map(s => ({ value: s, label: s }))} ariaLabel="Filter by sector" />
          <span className="text-[13px] text-ink-3">{company.length} company, {macro.length} macro, last 48 hours</span>
        </div>

        {items.length === 0 ? (
          <Empty title="Nothing tracked yet" hint="Headlines appear here after the daily pipeline runs. Come back after 5pm Eastern." />
        ) : (
          <div className="grid gap-6 lg:gap-8 lg:grid-cols-[minmax(0,1fr)_380px] items-start">
            <Column title="Companies and products" days={companyDays} accent="var(--accent)" empty="No company signals for this sector." onOpen={onSelectTarget} />
            <Column title="Geopolitics and macro" days={macroDays} accent="var(--macro)" empty="No macro signals in the last 48 hours." onOpen={() => onOpenMacro()} macro />
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, color, big = false }: { label: string; value: string; color: string; big?: boolean }) {
  return (
    <div className="text-right">
      <div className={`figure font-semibold ${big ? 'text-[48px] md:text-[60px]' : 'text-[26px] md:text-[30px]'}`} style={{ color }}>{value}</div>
      <div className="text-[12.5px] text-ink-2 mt-1">{label}</div>
    </div>
  )
}

function Column({ title, days, accent, empty, onOpen, macro = false }: {
  title: string
  days: { date: string; groups: Group[] }[]
  accent: string
  empty: string
  onOpen: (id: number) => void
  macro?: boolean
}) {
  const today = new Date().toISOString().slice(0, 10)
  return (
    <section className="min-w-0">
      <div className="flex items-baseline gap-3 pb-2 border-b border-line">
        <h2 className="headline text-[17px] font-semibold m-0">{title}</h2>
      </div>
      {days.length === 0 && <p className="text-[13.5px] text-ink-3 py-8 text-center m-0">{empty}</p>}
      {days.map(({ date, groups }) => (
        <div key={date}>
          <div className="sticky top-0 z-10 py-2 text-[12.5px] text-ink-2 bg-bg/90 backdrop-blur-sm">
            {date === today ? 'Today' : fmtDayLong(date)}
          </div>
          <div className="stagger">
            {groups.map(g => {
              const scored = g.events.map(e => e.topScore).filter((s): s is number => s != null)
              const gAvg = avg(scored)
              const rule = macro ? accent : toneColor(scoreTone(gAvg == null ? null : Math.round(gAvg)))
              return (
                <article key={g.key} className="hero mb-2.5 overflow-hidden">
                  <header className="flex items-center gap-2.5 px-4 pt-3 pb-2">
                    <span className="w-[3px] self-stretch rounded-full -ml-1" style={{ background: rule }} aria-hidden />
                    {g.isMacro
                      ? <span className="text-macro shrink-0" title="Macro theme"><Icon name="globe" size={18} /></span>
                      : <Logo logoUrl={g.logo_url} domain={g.domain} name={g.name} size={22} />}
                    {/* Macro names are long and the column is narrow, so let them wrap instead of truncating. */}
                    <button onClick={() => onOpen(g.id)} className={`headline text-[15px] font-semibold text-ink hover:text-accent transition-colors text-left ${g.isMacro ? 'min-w-0' : 'truncate'}`}>{g.name}</button>
                    {!g.isMacro && g.sector && <Chip>{g.sector}</Chip>}
                    {!g.isMacro && g.is_f500 && <Chip tone="accent">F500</Chip>}
                    <span className="ml-auto self-start pt-0.5 text-[12px] text-ink-3 whitespace-nowrap">{relativeTime(g.latestAt)}</span>
                  </header>
                  <ul className="m-0 p-0 list-none">
                    {g.events.map(ev => {
                      const product = ev.target?.target_type === 'PRODUCT' ? ev.target.name : null
                      return (
                        <li key={ev.id} className="border-t border-line relative">
                          <button onClick={() => onOpen(product ? ev.target.id : g.id)} className="w-full flex items-start gap-4 px-4 py-3 text-left row-hover">
                            <span className="flex-1 min-w-0">
                              {product && <span className="block text-[12px] font-medium text-accent mb-0.5">{product}</span>}
                              <span className="headline block text-[16px] text-ink">{ev.headline}</span>
                              {/* The model's read of the story, under the publication's headline. */}
                              {ev.summary && ev.summary !== ev.headline && (
                                <span className="block text-[13px] text-ink-2 mt-1 leading-snug">{ev.summary}</span>
                              )}
                            </span>
                            <span className="flex flex-col items-end gap-1.5 shrink-0 pt-0.5">
                              <Score value={ev.topScore} size="md" />
                              <TagChip tag={ev.topTag} />
                              {/* Reserve the corner so the link never lands on the badges. */}
                              {ev.source_url && <span className="h-[18px]" aria-hidden />}
                            </span>
                          </button>
                          {ev.source_url && (
                            <a
                              href={ev.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              className="absolute bottom-2.5 right-3 text-ink-3 hover:text-accent transition-colors"
                              title="Read the original"
                              aria-label={`Read the original: ${ev.headline}`}
                            >
                              <Icon name="external" size={14} />
                            </a>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </article>
              )
            })}
          </div>
        </div>
      ))}
    </section>
  )
}
