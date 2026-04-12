import { createClient } from '@supabase/supabase-js'

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(url, key)

// ── Types ────────────────────────────────────────────────────────────────────

export interface Target {
  id: number
  name: string
  target_type: 'COMPANY' | 'PRODUCT'
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
  shares: number
  price: number
  usd_value: number
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

export async function fetchRecentHeadlines(lookbackHours = 48): Promise<(Event & { target: Target; topScore: number | null; topTag: string | null })[]> {
  const since = new Date(Date.now() - lookbackHours * 3600 * 1000).toISOString()
  const { data: events, error } = await supabase
    .from('events')
    .select('*, targets!inner(*)')
    .gte('created_at', since)
    .order('created_at', { ascending: false })
    .limit(200)
  if (error) throw error

  const eventIds = (events ?? []).map((e: any) => e.id)
  if (eventIds.length === 0) return []

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
    return { ...e, target: e.targets, topScore: topScore ? Math.round(topScore) : null, topTag }
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
  const all: StockPrice[] = []
  let offset = 0
  while (true) {
    const { data, error } = await supabase
      .from('stock_prices')
      .select('*')
      .eq('target_id', targetId)
      .order('ts', { ascending: true })
      .range(offset, offset + 999)
    if (error || !data || data.length === 0) break
    all.push(...data)
    if (data.length < 1000) break
    offset += 1000
  }
  return all
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
  const result: Record<string, number> = {}
  for (const ticker of tickers) {
    const { data: targetRow } = await supabase
      .from('targets')
      .select('id')
      .eq('ticker', ticker)
      .single()
    if (!targetRow) continue
    const { data } = await supabase
      .from('stock_prices')
      .select('close')
      .eq('target_id', targetRow.id)
      .order('ts', { ascending: false })
      .limit(1)
      .single()
    if (data) result[ticker] = data.close
  }
  return result
}
