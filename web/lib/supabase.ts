import { createClient } from '@supabase/supabase-js'

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? ''
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? ''

// createClient throws if url is empty — guard for build-time SSR prerender
export const supabase = url && key ? createClient(url, key) : createClient('https://placeholder.supabase.co', 'placeholder')

// ── Types ────────────────────────────────────────────────────────────────────

export interface Target {
  id: number
  name: string
  target_type: 'COMPANY' | 'PRODUCT' | 'MACRO'
  description: string | null
  status: string
  logo_url: string | null
  domain: string | null
  parent_target_id: number | null
  ticker: string | null
  sector: string | null
  is_f500: boolean
}

export interface Event {
  id: number
  target_id: number
  headline: string
  cached_analysis: string | null
  created_at: string
}

export interface SentimentRow {
  id: number
  target_id: number
  event_id: number | null
  pros: string | null
  cons: string | null
  verbatim_quotes: string | null
  source_url: string | null
  sentiment_score: number | null
  implication_tag: 'threat' | 'opportunity' | 'monitor' | 'no_action' | null
  source_type: string | null
  created_at: string
}

export interface StockPrice {
  id: number
  target_id: number
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface PriceReaction {
  event_id: number
  target_id: number
  ticker: string
  price_at_event: number | null
  window_return_pct: number | null
  reaction_1d: number | null
  reaction_3d: number | null
  reaction_7d: number | null
  market_session: string | null
  confidence: string | null
  confidence_reason: string | null
  computed_at: string
}

export interface SimPortfolio {
  id: number
  cash_usd: number
  peak_value: number
  initialized_at: string
  updated_at: string
}

export interface SimHolding {
  id: number
  target_id: number
  ticker: string
  shares: number
  avg_buy_price: number
  total_cost: number
  created_at: string
  updated_at: string
}

export interface SimTrade {
  id: number
  trade_date: string
  target_id: number | null
  ticker: string
  action: 'BUY' | 'SELL'
  shares: number | null
  price: number | null
  usd_value: number | null
  pnl_usd: number | null
  status: 'executed' | 'skipped'
  skip_reason: string | null
  ai_rationale: string | null
  created_at: string
}

export interface SimPending {
  id: number
  queued_at: string
  target_id: number | null
  ticker: string
  action: 'BUY' | 'SELL'
  usd_amount: number | null
  sell_all: boolean
  ai_rationale: string | null
}

export interface SimSnapshot {
  id: number
  snapshot_date: string
  cash_usd: number
  holdings_value: number
  total_value: number
  pnl_usd: number
  pnl_pct: number
  summary_text: string | null
  created_at: string
  /** What the starting capital would be worth in this index from inception. Null before migration 021. */
  spy_value: number | null
  qqq_value: number | null
}

// ── Query helpers ────────────────────────────────────────────────────────────

export async function fetchTargets(): Promise<Target[]> {
  const { data, error } = await supabase
    .from('targets')
    .select('*')
    .eq('status', 'tracking')
    .order('name')
  if (error) throw error
  return data ?? []
}

export async function fetchRecentHeadlines(lookbackHours = 48): Promise<(Event & { target: Target & { parent_target: Pick<Target, 'id' | 'name' | 'logo_url' | 'domain' | 'sector' | 'is_f500'> | null }; topScore: number | null; topTag: string | null })[]> {
  const since = new Date(Date.now() - lookbackHours * 3600 * 1000).toISOString()
  const { data: events, error } = await supabase
    .from('events')
    .select('*, targets!inner(*)')
    .gte('created_at', since)
    .neq('headline', '(general)')
    .order('created_at', { ascending: false })
    .limit(200)
  if (error) throw error

  const eventIds = (events ?? []).map((e: any) => e.id)
  if (eventIds.length === 0) return []

  // Fetch parent companies for product targets
  const parentIds = [...new Set(
    (events ?? []).map((e: any) => e.targets?.parent_target_id).filter(Boolean)
  )] as number[]
  const parentMap: Record<number, Pick<Target, 'id' | 'name' | 'logo_url' | 'domain' | 'sector' | 'is_f500'>> = {}
  if (parentIds.length > 0) {
    const { data: parents } = await supabase
      .from('targets')
      .select('id, name, logo_url, domain, sector, is_f500')
      .in('id', parentIds)
    for (const p of parents ?? []) parentMap[p.id] = p
  }

  const { data: sentRows } = await supabase
    .from('sentiment')
    .select('event_id, sentiment_score, implication_tag')
    .in('event_id', eventIds)

  const scoreMap: Record<number, number[]> = {}
  const tagMap: Record<number, string[]> = {}
  for (const row of sentRows ?? []) {
    if (row.event_id == null) continue
    if (row.sentiment_score != null) {
      scoreMap[row.event_id] = scoreMap[row.event_id] ?? []
      scoreMap[row.event_id].push(row.sentiment_score)
    }
    if (row.implication_tag) {
      tagMap[row.event_id] = tagMap[row.event_id] ?? []
      tagMap[row.event_id].push(row.implication_tag)
    }
  }

  const TAG_PRIORITY: Record<string, number> = { threat: 4, opportunity: 3, monitor: 2, no_action: 1 }
  return (events ?? []).map((e: any) => {
    const scores = scoreMap[e.id] ?? []
    const tags = tagMap[e.id] ?? []
    const topScore = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null
    const topTag = tags.length ? tags.sort((a, b) => (TAG_PRIORITY[b] ?? 0) - (TAG_PRIORITY[a] ?? 0))[0] : null
    const target = e.targets
    const parent_target = target?.parent_target_id ? (parentMap[target.parent_target_id] ?? null) : null
    return { ...e, target: { ...target, parent_target }, topScore: topScore ? Math.round(topScore) : null, topTag }
  })
}

export async function fetchTargetWithEvents(targetId: number): Promise<{ target: Target; events: (Event & { reaction: PriceReaction | null; avgScore: number | null; topTag: string | null })[] }> {
  const [{ data: targetData }, { data: eventsData }] = await Promise.all([
    supabase.from('targets').select('*').eq('id', targetId).single(),
    supabase.from('events').select('*').eq('target_id', targetId).order('created_at', { ascending: false }).limit(50),
  ])

  if (!targetData) throw new Error('Target not found')
  const events = eventsData ?? []
  const eventIds = events.map((e: any) => e.id)

  const [{ data: reactions }, { data: sentRows }] = await Promise.all([
    eventIds.length ? supabase.from('price_reactions').select('*').in('event_id', eventIds) : Promise.resolve({ data: [] }),
    eventIds.length ? supabase.from('sentiment').select('event_id, sentiment_score, implication_tag').in('event_id', eventIds) : Promise.resolve({ data: [] }),
  ])

  const reactionMap: Record<number, PriceReaction> = {}
  for (const r of reactions ?? []) reactionMap[r.event_id] = r

  const scoreMap: Record<number, number[]> = {}
  const tagMap: Record<number, string[]> = {}
  for (const row of sentRows ?? []) {
    if (row.event_id == null) continue
    if (row.sentiment_score != null) {
      scoreMap[row.event_id] = scoreMap[row.event_id] ?? []
      scoreMap[row.event_id].push(row.sentiment_score)
    }
    if (row.implication_tag) {
      tagMap[row.event_id] = tagMap[row.event_id] ?? []
      tagMap[row.event_id].push(row.implication_tag)
    }
  }

  const TAG_PRIORITY: Record<string, number> = { threat: 4, opportunity: 3, monitor: 2, no_action: 1 }
  return {
    target: targetData,
    events: events.map((e: any) => {
      const scores = scoreMap[e.id] ?? []
      const tags = tagMap[e.id] ?? []
      const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null
      const topTag = tags.length ? tags.sort((a, b) => (TAG_PRIORITY[b] ?? 0) - (TAG_PRIORITY[a] ?? 0))[0] : null
      return { ...e, reaction: reactionMap[e.id] ?? null, avgScore, topTag }
    }),
  }
}

export async function fetchScoreSeries(targetId: number, days = 30): Promise<{ date: string; score: number }[]> {
  const since = new Date(Date.now() - days * 86400 * 1000).toISOString()
  const { data } = await supabase
    .from('sentiment')
    .select('created_at, sentiment_score')
    .eq('target_id', targetId)
    .gte('created_at', since)
    .not('sentiment_score', 'is', null)
    .order('created_at')
  if (!data) return []
  const grouped: Record<string, number[]> = {}
  for (const row of data) {
    const d = row.created_at.slice(0, 10)
    grouped[d] = grouped[d] ?? []
    grouped[d].push(row.sentiment_score)
  }
  return Object.entries(grouped).map(([date, scores]) => ({
    date,
    score: Math.round(scores.reduce((a, b) => a + b, 0) / scores.length),
  }))
}

export async function fetchPriceSeries(targetId: number): Promise<StockPrice[]> {
  // Newest bars first, no date filter: if the pipeline has paused, the chart still shows the last known window.
  // 5-min bars run ~78 per trading day, so 6 pages of 1000 cover roughly 75 trading days.
  const PAGES = 6
  const results = await Promise.all(
    Array.from({ length: PAGES }, (_, i) =>
      supabase.from('stock_prices').select('ts, close').eq('target_id', targetId)
        .order('ts', { ascending: false }).range(i * 1000, i * 1000 + 999)
    )
  )
  const all: StockPrice[] = []
  for (const { data } of results) if (data?.length) all.push(...(data as StockPrice[]))
  return all.reverse()
}

export async function fetchAllTargetScores(): Promise<Record<number, { avg: number; count: number }>> {
  const { data } = await supabase
    .from('sentiment')
    .select('target_id, sentiment_score')
    .not('sentiment_score', 'is', null)
  if (!data) return {}
  const map: Record<number, number[]> = {}
  for (const row of data) {
    map[row.target_id] = map[row.target_id] ?? []
    map[row.target_id].push(row.sentiment_score)
  }
  return Object.fromEntries(
    Object.entries(map).map(([id, scores]) => [
      id,
      { avg: Math.round(scores.reduce((a, b) => a + b, 0) / scores.length), count: scores.length },
    ])
  )
}

export async function fetchSimData(): Promise<{
  portfolio: SimPortfolio | null
  holdings: SimHolding[]
  pending: SimPending[]
  trades: SimTrade[]
  snapshots: SimSnapshot[]
}> {
  const [
    { data: portfolio },
    { data: holdings },
    { data: pending },
    { data: trades },
    { data: snapshots },
  ] = await Promise.all([
    supabase.from('sim_portfolio').select('*').single(),
    supabase.from('sim_holdings').select('*').order('ticker'),
    supabase.from('sim_pending_trades').select('*').order('queued_at', { ascending: false }),
    supabase.from('sim_trades').select('*').order('created_at', { ascending: false }).limit(50),
    supabase.from('sim_snapshots').select('*').order('snapshot_date'),
  ])
  return {
    portfolio: portfolio ?? null,
    holdings: holdings ?? [],
    pending: pending ?? [],
    trades: trades ?? [],
    snapshots: snapshots ?? [],
  }
}

export async function fetchLatestPricesForTickers(tickers: string[]): Promise<Record<string, number>> {
  if (tickers.length === 0) return {}
  const { data: targetRows } = await supabase.from('targets').select('id, ticker').in('ticker', tickers)
  const byTicker: Record<string, number> = {}
  for (const t of targetRows ?? []) if (t.ticker && byTicker[t.ticker] == null) byTicker[t.ticker] = t.id
  const result: Record<string, number> = {}
  await Promise.all(Object.entries(byTicker).map(async ([ticker, targetId]) => {
    const { data } = await supabase.from('stock_prices').select('close').eq('target_id', targetId).order('ts', { ascending: false }).limit(1)
    const close = data?.[0]?.close
    if (close != null) result[ticker] = close
  }))
  return result
}

// ── Added for the redesigned dashboard ───────────────────────────────────────

export interface MacroTheme extends Target {
  avg7d: number | null
  readings7d: number
  eventCount: number
  exposures: { sector: string; weight: number }[]
  latest: { id: number; headline: string; created_at: string }[]
  series: { date: string; score: number }[]
}

/** Macro themes with 7-day sentiment, sector exposures, and latest headlines. */
export async function fetchMacroThemes(): Promise<MacroTheme[]> {
  const { data: macros, error } = await supabase.from('targets').select('*').eq('target_type', 'MACRO').eq('status', 'tracking').order('name')
  if (error) throw error
  const ids = (macros ?? []).map(m => m.id)
  if (ids.length === 0) return []

  const since7 = new Date(Date.now() - 7 * 86400e3).toISOString()
  const since30 = new Date(Date.now() - 30 * 86400e3).toISOString()
  const [{ data: exp }, { data: sent }, { data: evts }] = await Promise.all([
    supabase.from('macro_sector_exposure').select('macro_target_id, sector, exposure_weight').in('macro_target_id', ids),
    supabase.from('sentiment').select('target_id, sentiment_score, created_at').in('target_id', ids).gte('created_at', since30).not('sentiment_score', 'is', null).order('created_at'),
    supabase.from('events').select('id, target_id, headline, created_at').in('target_id', ids).neq('headline', '(general)').order('created_at', { ascending: false }).limit(400),
  ])

  const expMap: Record<number, { sector: string; weight: number }[]> = {}
  for (const r of exp ?? []) (expMap[r.macro_target_id] ??= []).push({ sector: r.sector, weight: Number(r.exposure_weight) })

  const s7: Record<number, number[]> = {}
  const daily: Record<number, Record<string, number[]>> = {}
  for (const r of sent ?? []) {
    if (r.created_at >= since7) (s7[r.target_id] ??= []).push(r.sentiment_score)
    const d = r.created_at.slice(0, 10)
    ;((daily[r.target_id] ??= {})[d] ??= []).push(r.sentiment_score)
  }

  const evMap: Record<number, { id: number; headline: string; created_at: string }[]> = {}
  for (const e of evts ?? []) (evMap[e.target_id] ??= []).push({ id: e.id, headline: e.headline, created_at: e.created_at })

  return (macros ?? []).map(m => {
    const arr = s7[m.id] ?? []
    const series = Object.entries(daily[m.id] ?? {}).sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({ date, score: v.reduce((a, b) => a + b, 0) / v.length }))
    return {
      ...m,
      avg7d: arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null,
      readings7d: arr.length,
      eventCount: (evMap[m.id] ?? []).length,
      exposures: (expMap[m.id] ?? []).sort((a, b) => b.weight - a.weight),
      latest: (evMap[m.id] ?? []).slice(0, 3),
      series,
    }
  })
}

/** Daily average score per target for several targets at once (for compare cards + rail sparklines). */
export async function fetchScoreSeriesBatch(targetIds: number[], days = 30): Promise<Record<number, { date: string; score: number }[]>> {
  if (targetIds.length === 0) return {}
  const since = new Date(Date.now() - days * 86400e3).toISOString()
  const rows: { target_id: number; created_at: string; sentiment_score: number }[] = []
  let offset = 0
  while (true) {
    const { data, error } = await supabase
      .from('sentiment').select('target_id, created_at, sentiment_score')
      .in('target_id', targetIds).gte('created_at', since).not('sentiment_score', 'is', null)
      .order('created_at').range(offset, offset + 999)
    if (error || !data || data.length === 0) break
    rows.push(...data)
    if (data.length < 1000) break
    offset += 1000
  }
  const grouped: Record<number, Record<string, number[]>> = {}
  for (const r of rows) ((grouped[r.target_id] ??= {})[r.created_at.slice(0, 10)] ??= []).push(r.sentiment_score)
  const out: Record<number, { date: string; score: number }[]> = {}
  for (const [tid, days] of Object.entries(grouped)) {
    out[Number(tid)] = Object.entries(days).sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({ date, score: Math.round(v.reduce((a, b) => a + b, 0) / v.length) }))
  }
  return out
}

/** Recent sentiment rows for a target: pros, cons, quotes, tags. Used by compare cards and deep-dive summaries. */
export async function fetchRecentSentiment(targetId: number, limit = 12): Promise<SentimentRow[]> {
  const { data } = await supabase
    .from('sentiment').select('*').eq('target_id', targetId)
    .order('created_at', { ascending: false }).limit(limit)
  return data ?? []
}

/** Sentiment rows attached to one event (for the expanded event card). */
export async function fetchEventSentiment(eventId: number): Promise<SentimentRow[]> {
  const { data } = await supabase
    .from('sentiment').select('*').eq('event_id', eventId)
    .order('created_at', { ascending: false }).limit(20)
  return data ?? []
}
