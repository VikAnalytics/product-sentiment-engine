export function scoreClass(score: number | null): string {
  if (score == null) return 'c-n'
  if (score >= 7) return 'c-ph'
  if (score >= 3) return 'c-pm'
  if (score >= -2) return 'c-n'
  if (score >= -6) return 'c-nm'
  return 'c-nh'
}

export function barClass(score: number | null): string {
  return scoreClass(score).replace('c-', 'b-')
}

export function tagClass(tag: string | null): string {
  if (tag === 'opportunity') return 't-op'
  if (tag === 'threat') return 't-th'
  if (tag === 'monitor') return 't-mo'
  return 't-na'
}

export function tagLabel(tag: string | null): string {
  if (tag === 'opportunity') return 'Opportunity'
  if (tag === 'threat') return 'Threat'
  if (tag === 'monitor') return 'Monitor'
  if (tag === 'no_action') return 'No Action'
  return '—'
}

export function tagEmoji(tag: string | null): string {
  if (tag === 'opportunity') return '🟢'
  if (tag === 'threat') return '🔴'
  if (tag === 'monitor') return '🟡'
  return '⚪'
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export function fmtScore(score: number | null): string {
  if (score == null) return '—'
  return score > 0 ? `+${score}` : `${score}`
}

export function fmtPct(val: number | null): string {
  if (val == null) return '—'
  const sign = val >= 0 ? '+' : ''
  return `${sign}${(val * 100).toFixed(2)}%`
}

export function fmtUSD(val: number | null): string {
  if (val == null) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val)
}

export function confidenceDot(conf: string | null): string {
  if (conf === 'high') return '●'
  if (conf === 'medium') return '◉'
  return '○'
}

/** Group an array by a key function */
export function groupBy<T>(arr: T[], key: (item: T) => string): Record<string, T[]> {
  return arr.reduce((acc, item) => {
    const k = key(item)
    acc[k] = acc[k] ?? []
    acc[k].push(item)
    return acc
  }, {} as Record<string, T[]>)
}
