'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchSimData, fetchLatestPricesForTickers, SimHolding, SimPending, SimPortfolio, SimSnapshot, SimTrade } from '@/lib/supabase'
import { fmtDate, fmtPct, fmtSignedUSD, fmtUSD, signColor } from '@/lib/utils'
import { Empty, ErrorState, Icon, Loading, SectionHead, Sparkline } from '@/components/ui'

const SIM_START = 1000

export default function Simulator() {
  const [portfolio, setPortfolio] = useState<SimPortfolio | null>(null)
  const [holdings, setHoldings] = useState<SimHolding[]>([])
  const [pending, setPending] = useState<SimPending[]>([])
  const [trades, setTrades] = useState<SimTrade[]>([])
  const [snapshots, setSnapshots] = useState<SimSnapshot[]>([])
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [strategyOpen, setStrategyOpen] = useState(false)

  useEffect(() => {
    fetchSimData()
      .then(async d => {
        setPortfolio(d.portfolio); setHoldings(d.holdings); setPending(d.pending); setTrades(d.trades); setSnapshots(d.snapshots)
        if (d.holdings.length) setPrices(await fetchLatestPricesForTickers(d.holdings.map(h => h.ticker)))
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const holdingsValue = useMemo(() => holdings.reduce((s, h) => s + (prices[h.ticker] ?? h.avg_buy_price) * h.shares, 0), [holdings, prices])
  const cash = portfolio?.cash_usd ?? 0
  const total = cash + holdingsValue
  const pnl = total - SIM_START
  const pnlPct = pnl / SIM_START
  const drawdown = portfolio?.peak_value ? (total - portfolio.peak_value) / portfolio.peak_value : null

  if (loading) return <Loading label="Loading portfolio" />
  if (error) return <ErrorState message={error} />
  if (!portfolio) return <Empty title="Simulator not initialized" hint="Apply migration 015 in Supabase, then run the analyze step once." />

  const curve = [...snapshots.map(s => s.total_value), total]

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-[1080px] mx-auto px-4 md:px-6 py-5 md:py-6">

        {/* Hero */}
        <section className="hero p-5 md:p-7 rise">
          <div className="flex flex-col md:flex-row md:items-end gap-6">
            <div className="flex-1 min-w-0">
              <div className="text-[13px] text-ink-2">Virtual portfolio, started with {fmtUSD(SIM_START, 0)}</div>
              <div className="display text-[48px] md:text-[64px] font-semibold text-ink mt-1 tnum">{fmtUSD(total)}</div>
              <div className="figure text-[20px] font-semibold mt-1" style={{ color: signColor(pnl) }}>
                {fmtSignedUSD(pnl)} <span className="text-[15px] font-medium">({fmtPct(pnlPct)})</span>
                <span className="text-[13px] font-normal text-ink-2 ml-2">since inception</span>
              </div>
            </div>
            <dl className="grid grid-cols-3 gap-6 md:gap-8 m-0">
              <Stat label="Cash" value={fmtUSD(cash)} />
              <Stat label="Invested" value={fmtUSD(holdingsValue)} sub={`${holdings.length} position${holdings.length === 1 ? '' : 's'}`} />
              <Stat label="From peak" value={drawdown == null ? '–' : fmtPct(drawdown, 1)} color={drawdown != null && drawdown < 0 ? 'var(--neg)' : 'var(--ink)'} sub="liquidates at −15%" />
            </dl>
          </div>
          {curve.length > 1 && (
            <div className="mt-6">
              <Sparkline points={curve} color={signColor(pnl)} baseline={SIM_START} height={110} />
              <div className="flex justify-between text-[11.5px] text-ink-3 mt-1.5 tnum">
                <span>{snapshots[0] ? fmtDate(snapshots[0].snapshot_date, { month: 'short', day: 'numeric', year: 'numeric' }) : ''}</span>
                <span>Fortnightly snapshots, dashed line is starting capital</span>
                <span>Now</span>
              </div>
            </div>
          )}
        </section>

        {/* Queue */}
        <section className="mt-6">
          <SectionHead title="Queued for next open" meta={pending.length === 0 ? 'nothing queued' : `${pending.length} order${pending.length === 1 ? '' : 's'}`} />
          {pending.length === 0 ? (
            <p className="text-[13.5px] text-ink-3 py-4 m-0">The analyze step queues orders after 5pm Eastern when signals clear every gate. Quiet days are by design.</p>
          ) : (
            <ul className="m-0 p-0 list-none stagger">
              {pending.map(p => (
                <li key={p.id} className="flex items-start gap-4 py-3 border-b border-line">
                  <span className={`shrink-0 w-12 rounded-md px-2 py-1 text-center text-[12px] font-semibold ${p.action === 'BUY' ? 'bg-pos-soft text-pos' : 'bg-neg-soft text-neg'}`}>{p.action}</span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-[15px] font-medium text-ink">{p.ticker} <span className="text-ink-2 font-normal">{p.action === 'BUY' ? fmtUSD(p.usd_amount) : p.sell_all ? 'entire position' : ''}</span></span>
                    {p.ai_rationale && <span className="block text-[13px] text-ink-2 mt-0.5">{p.ai_rationale}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Holdings */}
        <section className="mt-8">
          <SectionHead title="Open positions" meta={holdings.length === 0 ? 'all cash' : undefined} />
          {holdings.length === 0 ? <p className="text-[13.5px] text-ink-3 py-4 m-0">No positions. The next queued buy opens one.</p> : (
            <Table
              head={['Ticker', 'Shares', 'Avg cost', 'Last', 'Value', 'P&L', 'P&L %']}
              align={['l', 'r', 'r', 'r', 'r', 'r', 'r']}
              rows={holdings.map(h => {
                const last = prices[h.ticker] ?? null
                const val = last != null ? last * h.shares : null
                const p = val != null ? val - h.total_cost : null
                const pp = p != null && h.total_cost ? p / h.total_cost : null
                return [
                  <span key="t" className="font-medium text-ink">{h.ticker}</span>,
                  h.shares.toFixed(4),
                  fmtUSD(h.avg_buy_price),
                  last != null ? fmtUSD(last) : '–',
                  val != null ? fmtUSD(val) : '–',
                  <span key="p" style={{ color: signColor(p) }}>{fmtSignedUSD(p)}</span>,
                  <span key="pp" style={{ color: signColor(pp) }}>{fmtPct(pp)}</span>,
                ]
              })}
            />
          )}
        </section>

        {/* Trades */}
        <section className="mt-8">
          <SectionHead title="Trade log" meta={trades.length ? `last ${trades.length}` : undefined} />
          {trades.length === 0 ? <p className="text-[13.5px] text-ink-3 py-4 m-0">No trades yet.</p> : (
            <Table
              head={['Date', 'Action', 'Ticker', 'Shares', 'Price', 'Value', 'P&L', 'Status']}
              align={['l', 'l', 'l', 'r', 'r', 'r', 'r', 'l']}
              rows={trades.map(t => [
                <span key="d" className="text-ink">{fmtDate(t.trade_date, { month: 'short', day: 'numeric', year: '2-digit' })}</span>,
                <span key="a" className="font-medium" style={{ color: t.action === 'BUY' ? 'var(--pos)' : 'var(--neg)' }}>{t.action}</span>,
                <span key="t" className="font-medium text-ink">{t.ticker}</span>,
                t.shares != null ? t.shares.toFixed(4) : '–',
                t.price != null ? fmtUSD(t.price) : '–',
                t.usd_value != null ? fmtUSD(t.usd_value) : '–',
                <span key="p" style={{ color: signColor(t.pnl_usd) }}>{t.pnl_usd != null ? fmtSignedUSD(t.pnl_usd) : '–'}</span>,
                <span key="s" title={t.skip_reason ?? undefined} className={t.status === 'executed' ? 'text-ink-2' : 'text-warn'}>{t.status === 'executed' ? 'Filled' : `Skipped${t.skip_reason ? ', ' + t.skip_reason : ''}`}</span>,
              ])}
            />
          )}
        </section>

        {/* Strategy */}
        <section className="mt-8 mb-6">
          <button onClick={() => setStrategyOpen(v => !v)} aria-expanded={strategyOpen} className="w-full flex items-center gap-3 py-2 border-b border-line text-left">
            <h2 className="headline text-[17px] font-semibold text-ink m-0">How the simulator decides</h2>
            <span className="text-[13px] text-ink-3">six factors, four gates, math-sized positions</span>
            <span className="ml-auto text-ink-3 transition-transform duration-300" style={{ transform: strategyOpen ? 'rotate(180deg)' : 'none' }}><Icon name="chevron" size={16} /></span>
          </button>
          {strategyOpen && <Strategy />}
        </section>
      </div>
    </div>
  )
}

function Stat({ label, value, sub, color = 'var(--ink)' }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="text-right">
      <dt className="text-[12.5px] text-ink-2 order-2">{label}</dt>
      <dd className="figure text-[24px] md:text-[28px] font-semibold m-0" style={{ color }}>{value}</dd>
      {sub && <dd className="text-[11.5px] text-ink-3 m-0 mt-0.5">{sub}</dd>}
    </div>
  )
}

function Table({ head, align, rows }: { head: string[]; align: ('l' | 'r')[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full border-collapse text-[13.5px] tnum">
        <thead>
          <tr>{head.map((h, i) => <th key={h} className={`py-2 px-2.5 font-medium text-[12.5px] text-ink-2 border-b border-line whitespace-nowrap ${align[i] === 'r' ? 'text-right' : 'text-left'}`}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="row-hover">
              {r.map((c, ci) => <td key={ci} className={`py-2.5 px-2.5 border-b border-line text-ink-2 whitespace-nowrap ${align[ci] === 'r' ? 'text-right' : 'text-left'}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Strategy explainer: mirrors src/sim_trader.py v2 (six-factor) ───────── */

const FACTORS = [
  { name: 'Sentiment momentum', weight: 25, desc: 'Average score this week against the prior week' },
  { name: 'Price momentum', weight: 20, desc: 'Five-day return from stored price bars' },
  { name: 'Inverse volatility', weight: 15, desc: 'Calmer names score higher' },
  { name: 'Signal consistency', weight: 15, desc: 'Share of positive readings in the window' },
  { name: 'Historical accuracy', weight: 10, desc: 'Past win rate from price reactions' },
  { name: 'Macro exposure', weight: 15, desc: 'Sector-weighted sentiment of active macro themes' },
]

const GATES = [
  { name: 'Top cohort', rule: 'Top third of the scored universe, at least four names' },
  { name: 'Expected value', rule: 'Win rate above 55% and expected return above 1.5% from at least five past reactions. A score of +7 or better tagged as opportunity may pass at half size.' },
  { name: 'Consensus', rule: 'At least three of six factors point the same way' },
  { name: 'Regime', rule: 'At least 40% of the universe, or three names, must have rising sentiment. Otherwise only the top name is bought, capped at 25% of cash.' },
]

const RISK = [
  ['−8% from average cost', 'Stop loss, sell'],
  ['−6% from the post-entry peak, once up 2%', 'Trailing stop, sell'],
  ['+25% from average cost', 'Take profit, sell'],
  ['Threat tag or day score below −3', 'Sentiment stop, sell'],
  ['Held name scores negative while a buy queues', 'Rotate out, at most two a day'],
  ['−15% from portfolio peak', 'Liquidate everything and clear the queue'],
]

function Strategy() {
  return (
    <div className="grid md:grid-cols-2 gap-6 pt-5 rise">
      <div>
        <h3 className="text-[13px] font-semibold text-ink-2 m-0 mb-2">Ranking, six weighted factors</h3>
        <ul className="m-0 p-0 list-none">
          {FACTORS.map(f => (
            <li key={f.name} className="grid grid-cols-[minmax(0,1fr)_88px_36px] items-center gap-3 py-2 border-b border-line">
              <span><span className="block text-[13.5px] text-ink">{f.name}</span><span className="block text-[12px] text-ink-3">{f.desc}</span></span>
              <span className="h-1.5 rounded-full bg-sunken overflow-hidden"><span className="block h-full rounded-full bg-accent" style={{ width: `${f.weight * 3}%` }} /></span>
              <span className="tnum text-right text-[12.5px] text-ink-2">{f.weight}%</span>
            </li>
          ))}
        </ul>
        <p className="m-0 mt-3 text-[12.5px] text-ink-3">Held positions are scored in the same pass as new candidates, so a weak holding can be rotated out for a stronger pick.</p>
      </div>
      <div>
        <h3 className="text-[13px] font-semibold text-ink-2 m-0 mb-2">Gates, in order</h3>
        <ol className="m-0 p-0 list-none">
          {GATES.map((g, i) => (
            <li key={g.name} className="flex gap-3 py-2 border-b border-line">
              <span className="tnum text-[12.5px] text-ink-3 w-4 shrink-0 pt-0.5">{i + 1}</span>
              <span><span className="block text-[13.5px] text-ink">{g.name}</span><span className="block text-[12.5px] text-ink-2">{g.rule}</span></span>
            </li>
          ))}
        </ol>
        <p className="m-0 mt-3 text-[12.5px] text-ink-3">Sizing: max-Sharpe weights with Ledoit-Wolf shrinkage, capped by Kelly at 25% per position, at most 90% of cash deployed.</p>

        <h3 className="text-[13px] font-semibold text-ink-2 m-0 mt-6 mb-2">Exits, checked before any buy</h3>
        <ul className="m-0 p-0 list-none">
          {RISK.map(([trigger, action]) => (
            <li key={trigger} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 py-2 border-b border-line text-[13px]">
              <span className="text-ink-2">{trigger}</span><span className="text-ink">{action}</span>
            </li>
          ))}
        </ul>
        <p className="m-0 mt-3 text-[12.5px] text-ink-3">Orders queue after 5pm Eastern and fill at the next 9:30am open price already stored in the database, so there is no look-ahead.</p>
      </div>
    </div>
  )
}
