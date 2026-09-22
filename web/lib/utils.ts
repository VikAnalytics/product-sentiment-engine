export type Tone = 'pos' | 'posMild' | 'neutral' | 'warn' | 'neg' | 'none'

/** Score bands: ≥7 strong positive, 3–6 positive, −2–+2 neutral, −6–−3 negative, ≤−7 strong negative. */
export function scoreTone(score: number | null | undefined): Tone {
  if (score == null) return 'none'
  if (score >= 7) return 'pos'
  if (score >= 3) return 'posMild'
  if (score >= -2) return 'neutral'
  if (score >= -6) return 'warn'
  return 'neg'
}

export function toneColor(tone: Tone): string {
  switch (tone) {
    case 'pos': return 'var(--pos)'
    case 'posMild': return 'var(--pos-mild)'
    case 'warn': return 'var(--warn)'
    case 'neg': return 'var(--neg)'
    case 'neutral': return 'var(--ink-2)'
    default: return 'var(--ink-3)'
  }
}

export function toneSoft(tone: Tone): string {
  switch (tone) {
    case 'pos': case 'posMild': return 'var(--pos-soft)'
    case 'warn': return 'var(--warn-soft)'
    case 'neg': return 'var(--neg-soft)'
    default: return 'var(--raised)'
  }
}

export function scoreLabel(score: number | null | undefined): string {
  switch (scoreTone(score)) {
    case 'pos': return 'Very positive'
    case 'posMild': return 'Positive'
    case 'neutral': return 'Neutral'
    case 'warn': return 'Negative'
    case 'neg': return 'Very negative'
    default: return 'No reading yet'
  }
}

/** Direction color for a signed change (returns, P&L, momentum). */
export function signColor(v: number | null | undefined): string {
  if (v == null) return 'var(--ink-3)'
  if (v > 0) return 'var(--pos)'
  if (v < 0) return 'var(--neg)'
  return 'var(--ink-2)'
}

export type Tag = 'threat' | 'opportunity' | 'monitor' | 'no_action'

export function tagLabel(tag: string | null | undefined): string {
  if (tag === 'opportunity') return 'Opportunity'
  if (tag === 'threat') return 'Threat'
  if (tag === 'monitor') return 'Monitor'
  if (tag === 'no_action') return 'No action'
  return ''
}

export function tagColor(tag: string | null | undefined): { fg: string; bg: string } {
  if (tag === 'opportunity') return { fg: 'var(--pos)', bg: 'var(--pos-soft)' }
  if (tag === 'threat') return { fg: 'var(--neg)', bg: 'var(--neg-soft)' }
  if (tag === 'monitor') return { fg: 'var(--warn)', bg: 'var(--warn-soft)' }
  return { fg: 'var(--ink-2)', bg: 'var(--raised)' }
}

/** Ambient gradient for the mood panel. −10 → red, 0 → neutral gray-violet, +10 → green. */
export function moodVars(avg: number | null | undefined): Record<string, string> {
  if (avg == null) return { '--mood-a': 'hsla(250, 60%, 62%, 0.26)', '--mood-b': 'hsla(272, 50%, 64%, 0.18)' }
  const t = Math.max(-10, Math.min(10, avg)) / 10          // −1..1
  // hue: 6 (red) → 250 (violet, neutral) → 150 (green)
  const hue = t < 0 ? 6 + (250 - 6) * (1 + t) : 250 + (150 - 250) * t
  const sat = 55 + Math.abs(t) * 30
  const strength = 0.26 + Math.abs(t) * 0.22
  return {
    '--mood-a': `hsla(${hue.toFixed(0)}, ${sat.toFixed(0)}%, 58%, ${strength.toFixed(2)})`,
    '--mood-b': `hsla(${(hue + 22).toFixed(0)}, ${(sat - 10).toFixed(0)}%, 62%, ${(strength * 0.7).toFixed(2)})`,
  }
}

export function moodHeadline(avg: number | null | undefined, count: number): string {
  if (count === 0) return 'Quiet so far'
  if (avg == null) return 'Signals in, scores pending'
  if (avg >= 5) return 'Markets lean strongly positive'
  if (avg >= 2) return 'Markets lean positive'
  if (avg > -2) return 'Mixed signals today'
  if (avg > -5) return 'Markets lean negative'
  return 'Markets lean strongly negative'
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export function fmtScore(score: number | null | undefined): string {
  if (score == null) return '–'
  const r = Math.round(score)
  return r > 0 ? `+${r}` : `${r}`
}

export function fmtScore1(score: number | null | undefined): string {
  if (score == null) return '–'
  return score > 0 ? `+${score.toFixed(1)}` : score.toFixed(1)
}

/** val is a fraction: 0.0123 → "+1.23%" */
export function fmtPct(val: number | null | undefined, digits = 2): string {
  if (val == null) return '–'
  const sign = val > 0 ? '+' : ''
  return `${sign}${(val * 100).toFixed(digits)}%`
}

export function fmtUSD(val: number | null | undefined, digits = 2): string {
  if (val == null) return '–'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(val)
}

export function fmtSignedUSD(val: number | null | undefined): string {
  if (val == null) return '–'
  return `${val > 0 ? '+' : val < 0 ? '−' : ''}${fmtUSD(Math.abs(val))}`
}

export function fmtDate(iso: string, opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }): string {
  // A bare YYYY-MM-DD parses as UTC midnight, which renders as the previous day
  // anywhere west of Greenwich: a trade dated the 19th showed as the 18th.
  // Calendar dates carry no time, so anchor them at local midday.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00`) : new Date(iso)
  return d.toLocaleDateString('en-US', opts)
}

export function fmtDayLong(yyyymmdd: string): string {
  return new Date(yyyymmdd + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
}

export function confidenceLabel(conf: string | null | undefined): string {
  if (conf === 'high') return 'High confidence'
  if (conf === 'medium') return 'Medium confidence'
  if (conf === 'low') return 'Low confidence'
  return ''
}

export function avg(nums: number[]): number | null {
  if (!nums.length) return null
  return nums.reduce((a, b) => a + b, 0) / nums.length
}

/** Split stored pros/cons text into clean bullet lines. Drops placeholder strings. */
export function toLines(text: string | null | undefined): string[] {
  if (!text) return []
  const PLACEHOLDER = /^(none|n\/a|no (pros|cons|quotes|verbatims?)( mentioned| identified| recorded)?\.?|none identified\.?|not applicable\.?)$/i
  return text
    .split(/\r?\n|(?<=\.)\s+(?=[A-Z•\-–*])|\s*[•]\s*/)
    .map(s => s.replace(/^[\s\-–*•\d.)]+/, '').trim())
    .filter(s => s.length > 3 && !PLACEHOLDER.test(s))
}

/** Drop near-duplicate lines: exact matches after normalization, or ≥55% word overlap with an earlier line. */
export function dedupeLines(lines: string[], overlap = 0.55): string[] {
  const STOP = new Set(['the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'is', 'are', 'was', 'has', 'have', 'with', 'that', 'this', 'its', 'as', 'by', 'be'])
  const kept: { raw: string; norm: string; words: Set<string> }[] = []
  for (const raw of lines) {
    const norm = raw.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim()
    if (!norm) continue
    const words = new Set(norm.split(' ').filter(w => w.length > 2 && !STOP.has(w)))
    const dup = kept.some(k => {
      if (k.norm === norm) return true
      if (words.size === 0 || k.words.size === 0) return false
      let shared = 0
      for (const w of words) if (k.words.has(w)) shared++
      return shared / Math.min(words.size, k.words.size) >= overlap
    })
    if (!dup) kept.push({ raw, norm, words })
  }
  return kept.map(k => k.raw)
}

export function groupBy<T>(arr: T[], key: (item: T) => string): Record<string, T[]> {
  return arr.reduce((acc, item) => {
    const k = key(item)
    acc[k] = acc[k] ?? []
    acc[k].push(item)
    return acc
  }, {} as Record<string, T[]>)
}

export const SECTORS = [
  'Technology', 'Gaming', 'Consumer Electronics', 'Automotive & EV',
  'Media & Entertainment', 'Finance & Fintech', 'Retail',
  'Defense & Aerospace', 'Social Media', 'Industrials', 'Mobility',
  'Sports & Events', 'Education', 'Luxury', 'Transport',
]
