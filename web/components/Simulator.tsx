'use client'

import { useEffect, useState, useMemo, useRef } from 'react'
import { fetchSimData, fetchLatestPricesForTickers, SimPortfolio, SimHolding, SimTrade, SimPending, SimSnapshot } from '@/lib/supabase'
import { fmtUSD, fmtPct } from '@/lib/utils'

const SIM_START = 1000

export default function Simulator() {
  const [strategyOpen, setStrategyOpen] = useState(false)
  const [portfolio, setPortfolio] = useState<SimPortfolio | null>(null)
  const [holdings, setHoldings] = useState<SimHolding[]>([])
  const [pending, setPending] = useState<SimPending[]>([])
  const [trades, setTrades] = useState<SimTrade[]>([])
  const [snapshots, setSnapshots] = useState<SimSnapshot[]>([])
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSimData()
      .then(async (d) => {
        setPortfolio(d.portfolio)
        setHoldings(d.holdings)
        setPending(d.pending)
        setTrades(d.trades)
        setSnapshots(d.snapshots)
        if (d.holdings.length > 0) {
          const px = await fetchLatestPricesForTickers(d.holdings.map(h => h.ticker))
          setPrices(px)
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const holdingsValue = useMemo(() =>
    holdings.reduce((sum, h) => sum + (prices[h.ticker] ?? h.avg_buy_price) * h.shares, 0),
    [holdings, prices]
  )

  const totalValue = (portfolio?.cash_usd ?? 0) + holdingsValue
  const pnlUsd = totalValue - SIM_START
  const pnlPct = pnlUsd / SIM_START

  // portfolio growth chart path
  const chartPath = useMemo(() => {
    if (snapshots.length < 2) return ''
    const W = 800, H = 100
    const values = snapshots.map(s => s.total_value)
    const min = Math.min(SIM_START * 0.8, ...values)
    const max = Math.max(SIM_START * 1.2, ...values)
    const xScale = (i: number) => (i / (snapshots.length - 1)) * W
    const yScale = (v: number) => H - ((v - min) / (max - min)) * H
    const startY = yScale(SIM_START)
    return {
      line: snapshots.map((s, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(s.total_value)}`).join(' '),
      startLine: startY,
      fill: snapshots.map((s, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(s.total_value)}`).join(' ') + ` L ${W} ${H} L 0 ${H} Z`,
    }
  }, [snapshots])

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.2em' }}>LOADING PORTFOLIO…</span>
    </div>
  )

  if (error) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--red)' }}>{error}</span>
    </div>
  )

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', flexDirection: 'column', animation: 'fadein 0.2s ease' }}>
      {/* header */}
      <div style={{ padding: '14px 24px 12px', borderBottom: '1px solid var(--br)', display: 'flex', alignItems: 'baseline', gap: 14, flexShrink: 0 }}>
        <span style={{ fontFamily: 'var(--ff-d)', fontSize: 30, fontWeight: 300, letterSpacing: '0.04em', lineHeight: 1 }}>
          AI <em style={{ fontStyle: 'italic', color: 'var(--gold)' }}>Simulator</em>
        </span>
        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 12, color: 'var(--tm)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          $1,000 starting capital &nbsp;·&nbsp; five-layer quant strategy
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '18px 24px' }}>
        {/* portfolio summary cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 22 }}>
          {[
            { label: 'Cash Available', value: fmtUSD(portfolio?.cash_usd ?? null), sub: null },
            { label: 'Holdings Value', value: fmtUSD(holdingsValue), sub: `${holdings.length} position${holdings.length !== 1 ? 's' : ''}` },
            {
              label: 'Total Value',
              value: fmtUSD(totalValue),
              sub: `${pnlUsd >= 0 ? '+' : ''}${fmtUSD(pnlUsd)} (${(pnlPct * 100).toFixed(2)}%)`,
              subColor: pnlUsd >= 0 ? 'var(--green)' : 'var(--red)',
            },
          ].map((card, i) => (
            <div key={i} style={{
              background: 'var(--bg-r)',
              border: '1px solid var(--br)',
              padding: '14px 16px',
              position: 'relative',
              overflow: 'hidden',
            }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 1, background: 'linear-gradient(90deg, transparent, var(--gold), transparent)', opacity: 0.4 }} />
              <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--tm)', marginBottom: 7 }}>{card.label}</div>
              <div style={{ fontFamily: 'var(--ff-m)', fontSize: 27, fontWeight: 700, lineHeight: 1, color: 'var(--t1)' }}>{card.value}</div>
              {card.sub && (
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10.5, color: card.subColor ?? 'var(--t2)', marginTop: 4 }}>{card.sub}</div>
              )}
            </div>
          ))}
        </div>

        {/* ── strategy overview ── */}
        <StrategyOverview open={strategyOpen} onToggle={() => setStrategyOpen(v => !v)} />

        {/* open positions */}
        <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--tm)', marginBottom: 10, paddingBottom: 7, borderBottom: '1px solid var(--br)' }}>
          Open Positions
        </div>
        {holdings.length === 0 ? (
          <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.1em', marginBottom: 22, padding: '12px 0' }}>No open positions</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 22, fontFamily: 'var(--ff-m)', fontSize: 11 }}>
            <thead>
              <tr>
                {['Ticker', 'Shares', 'Avg Cost', 'Current', 'Unreal. P&L', 'P&L %'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '5px 10px', fontWeight: 400, letterSpacing: '0.1em', textTransform: 'uppercase', fontSize: 11, color: 'var(--tm)', borderBottom: '1px solid var(--br)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {holdings.map(h => {
                const cur = prices[h.ticker] ?? null
                const mktVal = cur != null ? cur * h.shares : null
                const pnl = mktVal != null ? mktVal - h.total_cost : null
                const pnlP = pnl != null ? pnl / h.total_cost : null
                const color = pnl == null ? 'var(--t2)' : pnl >= 0 ? 'var(--green)' : 'var(--red)'
                return (
                  <tr key={h.id} onMouseEnter={e => { Array.from(e.currentTarget.cells).forEach(td => (td.style.background = 'var(--bg-h)')) }}
                    onMouseLeave={e => { Array.from(e.currentTarget.cells).forEach(td => (td.style.background = '')) }}>
                    <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t1)', fontWeight: 700 }}>{h.ticker}</td>
                    <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{h.shares.toFixed(4)}</td>
                    <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>${h.avg_buy_price.toFixed(2)}</td>
                    <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{cur != null ? `$${cur.toFixed(2)}` : '—'}</td>
                    <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color }}>{pnl != null ? `${pnl >= 0 ? '+' : ''}${fmtUSD(pnl)}` : '—'}</td>
                    <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color }}>{pnlP != null ? `${pnlP >= 0 ? '+' : ''}${(pnlP * 100).toFixed(2)}%` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {/* queued for tomorrow */}
        {pending.length > 0 && (
          <>
            <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--tm)', marginBottom: 10, paddingBottom: 7, borderBottom: '1px solid var(--br)' }}>
              Queued for Tomorrow
            </div>
            <div style={{ marginBottom: 22 }}>
              {pending.map(p => (
                <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 0', borderBottom: '1px solid var(--br)', fontFamily: 'var(--ff-m)', fontSize: 11 }}>
                  <span style={{ color: p.action === 'BUY' ? 'var(--green)' : 'var(--red)', fontWeight: 700, fontSize: 12, letterSpacing: '0.1em' }}>{p.action}</span>
                  <span style={{ color: 'var(--t1)', fontWeight: 700 }}>{p.ticker}</span>
                  <span style={{ color: 'var(--gold)', marginLeft: 'auto' }}>
                    {p.action === 'BUY' ? fmtUSD(p.usd_amount) : p.sell_all ? 'ALL' : '—'}
                  </span>
                  {p.ai_rationale && (
                    <span style={{ color: 'var(--tm)', fontSize: 12, fontFamily: 'var(--ff-b)', fontStyle: 'italic', maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.ai_rationale}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        {/* performance chart */}
        {snapshots.length >= 2 && chartPath && (
          <>
            <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--tm)', marginBottom: 10, paddingBottom: 7, borderBottom: '1px solid var(--br)' }}>
              Portfolio Growth
            </div>
            <div style={{ background: 'var(--bg-r)', border: '1px solid var(--br)', padding: '16px 16px 10px', marginBottom: 22 }}>
              <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--tm)', marginBottom: 12 }}>
                Fortnightly Snapshots — vs $1,000 baseline
              </div>
              <svg viewBox="0 0 800 100" style={{ width: '100%', height: 100, display: 'block', overflow: 'visible' }}>
                <defs>
                  <linearGradient id="simGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={pnlUsd >= 0 ? 'var(--green)' : 'var(--red)'} stopOpacity="0.25" />
                    <stop offset="100%" stopColor={pnlUsd >= 0 ? 'var(--green)' : 'var(--red)'} stopOpacity="0" />
                  </linearGradient>
                </defs>
                {/* baseline $1000 */}
                <line x1="0" y1={chartPath.startLine} x2="800" y2={chartPath.startLine} stroke="var(--gold)" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />
                <path d={chartPath.fill} fill="url(#simGrad)" />
                <path d={chartPath.line} fill="none" stroke={pnlUsd >= 0 ? 'var(--green)' : 'var(--red)'} strokeWidth="2" />
              </svg>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
                <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--tm)' }}>{snapshots[0]?.snapshot_date}</span>
                <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--tm)' }}>{snapshots[snapshots.length - 1]?.snapshot_date}</span>
              </div>
            </div>
          </>
        )}

        {/* trade log */}
        <div style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--tm)', marginBottom: 10, paddingBottom: 7, borderBottom: '1px solid var(--br)' }}>
          Recent Trades
        </div>
        {trades.length === 0 ? (
          <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--tm)', letterSpacing: '0.1em', padding: '12px 0' }}>No trades yet</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--ff-m)', fontSize: 11 }}>
            <thead>
              <tr>
                {['Date', 'Action', 'Ticker', 'Shares', 'Price', 'Value', 'P&L', 'Status'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '5px 10px', fontWeight: 400, letterSpacing: '0.1em', textTransform: 'uppercase', fontSize: 11, color: 'var(--tm)', borderBottom: '1px solid var(--br)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map(t => (
                <tr key={t.id} onMouseEnter={e => Array.from(e.currentTarget.cells).forEach(td => (td.style.background = 'var(--bg-h)'))}
                  onMouseLeave={e => Array.from(e.currentTarget.cells).forEach(td => (td.style.background = ''))}>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t1)', fontWeight: 700 }}>{t.trade_date}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: t.action === 'BUY' ? 'var(--green)' : 'var(--red)' }}>{t.action}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{t.ticker}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{t.shares != null ? t.shares.toFixed(4) : '—'}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{t.price != null ? `$${t.price.toFixed(2)}` : '—'}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{t.usd_value != null ? fmtUSD(t.usd_value) : '—'}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: t.pnl_usd == null ? 'var(--tm)' : t.pnl_usd >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {t.pnl_usd != null ? `${t.pnl_usd >= 0 ? '+' : ''}${fmtUSD(t.pnl_usd)}` : '—'}
                  </td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: t.status === 'executed' ? 'var(--t2)' : 'var(--amber)' }}>{t.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── Strategy Overview ─────────────────────────────────────────────────────────

const LAYERS = [
  {
    num: '01',
    name: 'Multi-Factor Ranking',
    gate: 'Top 20% of universe only',
    color: 'var(--blue)',
    colorD: 'var(--blue-d)',
    factors: [
      { label: 'Sentiment Momentum', weight: '30%', desc: 'Avg score this week vs. prior week' },
      { label: 'Price Momentum',     weight: '25%', desc: '5-day return from stock_prices' },
      { label: 'Inv. Volatility',    weight: '15%', desc: 'Lower vol = higher score' },
      { label: 'Signal Consistency', weight: '15%', desc: 'Fraction of positive-score sentiment rows' },
      { label: 'Historical Accuracy',weight: '15%', desc: 'Past win rate from price_reactions' },
    ],
    note: 'All 5 factors are Z-scored and weighted. Only the top quintile advances.',
  },
  {
    num: '02',
    name: 'Expected Value Gate',
    gate: 'p_win > 55% AND EV > 3%',
    color: 'var(--gold)',
    colorD: 'var(--gold-d)',
    factors: [
      { label: 'p_win',       weight: '>55%', desc: 'Historical win rate from price_reactions (min 5 samples)' },
      { label: 'Avg Gain',    weight: '',     desc: 'Mean positive return when sentiment was bullish' },
      { label: 'Avg Loss',    weight: '',     desc: 'Mean negative return when sentiment was bearish' },
      { label: 'EV',          weight: '>3%',  desc: 'p_win × avg_gain + (1−p_win) × avg_loss' },
    ],
    note: 'No historical data (<5 samples) = automatic disqualification. Cash is preserved over uncertainty.',
  },
  {
    num: '03',
    name: 'Signal Consensus',
    gate: '4 of 5 factors must be positive',
    color: '#7AB848',
    colorD: 'rgba(122,184,72,0.10)',
    factors: [
      { label: 'Sentiment Momentum', weight: '', desc: 'Positive = bullish signal' },
      { label: 'Price Momentum',     weight: '', desc: 'Positive = uptrend' },
      { label: 'Inv. Volatility',    weight: '', desc: 'Above median = low-risk signal' },
      { label: 'Signal Consistency', weight: '', desc: '>50% positive rows this week' },
      { label: 'Historical Accuracy',weight: '', desc: 'Win rate above universe median' },
    ],
    note: 'Mixed signals = no trade. Requires 4/5 directional agreement before capital is committed.',
  },
  {
    num: '04',
    name: 'Regime Filter',
    gate: '≥50% of universe has positive sentiment momentum',
    color: 'var(--amber)',
    colorD: 'var(--amber-d)',
    factors: [
      { label: 'Universe Sentiment', weight: '', desc: 'Count targets with positive 7-day momentum' },
      { label: 'Risk-On Threshold',  weight: '≥50%', desc: 'If market is broadly negative, hold cash' },
    ],
    note: 'Macro risk-off override. When the majority of tracked companies are deteriorating, no new positions are opened regardless of individual signals.',
  },
  {
    num: '05',
    name: 'Markowitz + Kelly Sizing',
    gate: 'Max 5 positions · Max 25% per position · Max 80% cash deployed',
    color: 'var(--green)',
    colorD: 'var(--green-d)',
    factors: [
      { label: 'Max-Sharpe Weights', weight: '', desc: 'scipy SLSQP optimizer, Ledoit-Wolf covariance shrinkage' },
      { label: 'Kelly Criterion',    weight: '≤25%', desc: 'f* = (p×b − (1−p)) / b, capped at 25% per position' },
      { label: 'Final Weight',       weight: '', desc: 'min(Markowitz, Kelly, 30%) per position' },
      { label: 'Deploy Cap',         weight: '80%', desc: 'At most 80% of cash is ever deployed in one cycle' },
    ],
    note: 'Position sizes come from math, not AI opinion. AI only writes the rationale text after the quant decision is made.',
  },
]

const RISK_RULES = [
  { trigger: '−8% from avg cost',         action: 'Stop-loss → forced SELL' },
  { trigger: '+25% from avg cost',         action: 'Take-profit → forced SELL' },
  { trigger: 'implication_tag = threat',   action: 'Sentiment stop → forced SELL' },
  { trigger: 'Avg score < −3 today',       action: 'Sentiment stop → forced SELL' },
  { trigger: '−15% from portfolio peak',   action: 'Max drawdown → liquidate ALL + clear queue' },
]

function StrategyOverview({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <div style={{ marginBottom: 22, border: '1px solid var(--br)', borderRadius: 2, overflow: 'hidden' }}>
      {/* toggle header */}
      <button
        onClick={onToggle}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          background: open ? 'var(--bg-p)' : 'var(--bg-r)',
          border: 'none',
          cursor: 'pointer',
          transition: 'background 0.15s',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--gold)' }}>
            Strategy Overview
          </span>
          <span style={{ fontFamily: 'var(--ff-b)', fontSize: 13, color: 'var(--tm)', fontStyle: 'italic' }}>
            Five-layer quant pipeline — how stocks are selected daily
          </span>
        </div>
        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 13, color: 'var(--tm)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▾</span>
      </button>

      {open && (
        <div style={{ padding: '0 16px 20px', background: 'var(--bg-p)' }}>

          {/* pipeline flow */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 0, margin: '18px 0 20px', overflowX: 'auto', paddingBottom: 4 }}>
            {LAYERS.map((l, i) => (
              <div key={l.num} style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                <div style={{
                  background: 'var(--bg-h)',
                  border: `1px solid ${l.color}`,
                  borderRadius: 2,
                  padding: '6px 12px',
                  textAlign: 'center',
                  minWidth: 110,
                }}>
                  <div style={{ fontFamily: 'var(--ff-m)', fontSize: 9, color: l.color, letterSpacing: '0.15em', marginBottom: 3 }}>{l.num}</div>
                  <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--t1)', letterSpacing: '0.06em', lineHeight: 1.3 }}>{l.name}</div>
                </div>
                {i < LAYERS.length - 1 && (
                  <div style={{ padding: '0 6px', fontFamily: 'var(--ff-m)', fontSize: 14, color: 'var(--tm)' }}>→</div>
                )}
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
              <div style={{ padding: '0 6px', fontFamily: 'var(--ff-m)', fontSize: 14, color: 'var(--tm)' }}>→</div>
              <div style={{ background: 'var(--bg-h)', border: '1px solid var(--green)', borderRadius: 2, padding: '6px 12px', textAlign: 'center' }}>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 9, color: 'var(--green)', letterSpacing: '0.15em', marginBottom: 3 }}>EXECUTE</div>
                <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--t1)', letterSpacing: '0.06em' }}>Next Open</div>
              </div>
            </div>
          </div>

          {/* layer detail cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {LAYERS.map(l => (
              <div key={l.num} style={{ background: 'var(--bg-h)', border: `1px solid var(--br)`, borderLeft: `3px solid ${l.color}`, borderRadius: 2, padding: '12px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
                  <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: l.color, letterSpacing: '0.15em' }}>LAYER {l.num}</span>
                  <span style={{ fontFamily: 'var(--ff-d)', fontSize: 18, fontWeight: 400, color: 'var(--t1)' }}>{l.name}</span>
                  <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: l.color, background: l.colorD, border: `1px solid ${l.color}`, padding: '2px 8px', borderRadius: 1, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                    {l.gate}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 6, marginBottom: 10 }}>
                  {l.factors.map(f => (
                    <div key={f.label} style={{ background: 'var(--bg-r)', border: '1px solid var(--br)', borderRadius: 2, padding: '7px 10px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                        <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--t1)', fontWeight: 700 }}>{f.label}</span>
                        {f.weight && <span style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: l.color }}>{f.weight}</span>}
                      </div>
                      <span style={{ fontFamily: 'var(--ff-b)', fontSize: 12, color: 'var(--t2)', fontStyle: 'italic' }}>{f.desc}</span>
                    </div>
                  ))}
                </div>
                <div style={{ fontFamily: 'var(--ff-b)', fontSize: 12.5, color: 'var(--tm)', fontStyle: 'italic', lineHeight: 1.6, borderTop: '1px solid var(--br)', paddingTop: 8 }}>
                  {l.note}
                </div>
              </div>
            ))}
          </div>

          {/* risk management */}
          <div style={{ marginTop: 16, background: 'var(--bg-h)', border: '1px solid var(--br)', borderLeft: '3px solid var(--red)', borderRadius: 2, padding: '12px 14px' }}>
            <div style={{ fontFamily: 'var(--ff-m)', fontSize: 10, color: 'var(--red)', letterSpacing: '0.15em', marginBottom: 10 }}>RISK MANAGEMENT · Execute step</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {RISK_RULES.map(r => (
                <div key={r.trigger} style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                  <span style={{ fontFamily: 'var(--ff-m)', fontSize: 11, color: 'var(--t2)', minWidth: 220, flexShrink: 0 }}>{r.trigger}</span>
                  <span style={{ fontFamily: 'var(--ff-m)', fontSize: 9, color: 'var(--tm)', letterSpacing: '0.06em' }}>→</span>
                  <span style={{ fontFamily: 'var(--ff-b)', fontSize: 12.5, color: 'var(--red)', fontStyle: 'italic' }}>{r.action}</span>
                </div>
              ))}
            </div>
            <div style={{ fontFamily: 'var(--ff-b)', fontSize: 12.5, color: 'var(--tm)', fontStyle: 'italic', lineHeight: 1.6, borderTop: '1px solid var(--br)', paddingTop: 8, marginTop: 10 }}>
              Risk checks run before any new trades execute. Drawdown liquidation clears the pending queue so no further capital is deployed that day.
            </div>
          </div>

          {/* timing note */}
          <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--bg-h)', border: '1px solid var(--br)', borderRadius: 2, display: 'flex', gap: 16, alignItems: 'flex-start' }}>
            <span style={{ fontFamily: 'var(--ff-m)', fontSize: 9, color: 'var(--gold)', letterSpacing: '0.15em', flexShrink: 0, paddingTop: 2 }}>TIMING</span>
            <span style={{ fontFamily: 'var(--ff-b)', fontSize: 13, color: 'var(--t2)', lineHeight: 1.65 }}>
              Pipeline runs at <b style={{ color: 'var(--t1)' }}>5 pm EST</b> daily.
              The <b style={{ color: 'var(--t1)' }}>analyze</b> step reads today's sentiment and queues trades.
              The <b style={{ color: 'var(--t1)' }}>execute</b> step next morning buys at the <b style={{ color: 'var(--t1)' }}>9:30 am open price</b> already stored in stock_prices — correctly simulating next-day-open execution with no look-ahead bias.
            </span>
          </div>

        </div>
      )}
    </div>
  )
}
