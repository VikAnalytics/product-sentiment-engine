'use client'

import { useEffect, useState, useMemo } from 'react'
import { fetchSimData, fetchLatestPricesForTickers, SimPortfolio, SimHolding, SimTrade, SimPending, SimSnapshot } from '@/lib/supabase'
import { fmtUSD, fmtPct } from '@/lib/utils'

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
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{t.shares.toFixed(4)}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>${t.price.toFixed(2)}</td>
                  <td style={{ padding: '9px 10px', borderBottom: '1px solid var(--br)', color: 'var(--t2)' }}>{fmtUSD(t.usd_value)}</td>
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
