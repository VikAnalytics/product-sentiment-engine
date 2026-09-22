'use client'

import { CSSProperties, ReactNode, useId } from 'react'
import { fmtScore, scoreTone, tagColor, tagLabel, toneColor } from '@/lib/utils'

/* ── Score figure ─────────────────────────────────────────────────────────── */

const SCORE_SIZE = { sm: 'text-[15px]', md: 'text-[20px]', lg: 'text-[28px]', xl: 'text-[44px]' } as const

export function Score({ value, size = 'md', className = '' }: { value: number | null | undefined; size?: keyof typeof SCORE_SIZE; className?: string }) {
  const tone = scoreTone(value)
  return (
    <span className={`figure font-semibold ${SCORE_SIZE[size]} ${className}`} style={{ color: toneColor(tone) }} aria-label={value == null ? 'no score' : `score ${fmtScore(value)}`}>
      {fmtScore(value)}
    </span>
  )
}

/* ── Implication tag ──────────────────────────────────────────────────────── */

export function TagChip({ tag, size = 'sm' }: { tag: string | null | undefined; size?: 'sm' | 'md' }) {
  const label = tagLabel(tag)
  if (!label) return null
  const { fg, bg } = tagColor(tag)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium leading-none whitespace-nowrap ${size === 'md' ? 'px-2.5 py-1.5 text-[12.5px]' : 'px-2 py-1 text-[11.5px]'}`}
      style={{ color: fg, background: bg }}
    >
      <span className="inline-block size-1.5 rounded-full" style={{ background: fg }} />
      {label}
    </span>
  )
}

/* ── Small neutral chip (sector, F500, ticker) ───────────────────────────── */

export function Chip({ children, tone = 'neutral', className = '' }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'macro'; className?: string }) {
  const style: CSSProperties =
    tone === 'accent' ? { color: 'var(--accent)', background: 'var(--accent-soft)' }
    : tone === 'macro' ? { color: 'var(--macro)', background: 'var(--macro-soft)' }
    : { color: 'var(--ink-2)', background: 'var(--raised)', boxShadow: 'inset 0 0 0 1px var(--line)' }
  return (
    <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11.5px] font-medium leading-none whitespace-nowrap ${className}`} style={style}>
      {children}
    </span>
  )
}

/* ── Section heading ─────────────────────────────────────────────────────── */

export function SectionHead({ title, meta, action, className = '' }: { title: string; meta?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={`flex items-baseline gap-3 pb-2 border-b border-line ${className}`}>
      <h2 className="headline text-[17px] font-semibold text-ink m-0">{title}</h2>
      {meta && <span className="text-[13px] text-ink-3">{meta}</span>}
      {action && <div className="ml-auto">{action}</div>}
    </div>
  )
}

/* ── Segmented control ───────────────────────────────────────────────────── */

export function Segmented<T extends string | number>({ options, value, onChange, size = 'sm' }: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  size?: 'sm' | 'md'
}) {
  return (
    <div className="inline-flex rounded-lg bg-sunken p-0.5" role="tablist">
      {options.map(o => {
        const active = o.value === value
        return (
          <button
            key={String(o.value)}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={`rounded-md font-medium transition-colors ${size === 'md' ? 'px-3 py-1.5 text-[13.5px]' : 'px-2.5 py-1 text-[12.5px]'} ${active ? 'bg-surface text-ink shadow-[0_1px_2px_rgba(0,0,0,0.08)]' : 'text-ink-2 hover:text-ink'}`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/* ── Sparkline ───────────────────────────────────────────────────────────── */

export function Sparkline({ points, color = 'var(--accent)', height = 48, width = 800, band, baseline, fill = true, strokeWidth = 2, className = '' }: {
  points: number[]
  color?: string
  height?: number
  width?: number
  /** Draw a faint band between these y-values (in data units), e.g. [-2, 2] for neutral sentiment. */
  band?: [number, number]
  /** Draw a dashed rule at this y-value. */
  baseline?: number
  fill?: boolean
  strokeWidth?: number
  className?: string
}) {
  const id = useId()
  if (points.length < 2) return null
  const min = Math.min(...points, band?.[0] ?? Infinity, baseline ?? Infinity)
  const max = Math.max(...points, band?.[1] ?? -Infinity, baseline ?? -Infinity)
  const pad = 4
  const span = max - min || 1
  const x = (i: number) => (i / (points.length - 1)) * width
  const y = (v: number) => pad + (height - pad * 2) * (1 - (v - min) / span)
  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(' ')
  const area = `${d} L${width},${height} L0,${height} Z`

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className={`block w-full ${className}`} style={{ height }} aria-hidden>
      <defs>
        <linearGradient id={`g${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {band && <rect x="0" y={y(band[1])} width={width} height={Math.max(1, y(band[0]) - y(band[1]))} fill="var(--ink-3)" opacity="0.10" />}
      {baseline != null && <line x1="0" x2={width} y1={y(baseline)} y2={y(baseline)} stroke="var(--ink-3)" strokeOpacity="0.5" strokeWidth="1" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />}
      {fill && <path d={area} fill={`url(#g${id})`} className="fade" />}
      {/* pathLength=1 normalizes dash units, so the draw-in works under preserveAspectRatio=none */}
      <path d={d} pathLength={1} fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" className="draw" style={{ ['--len' as string]: '1' }} />
    </svg>
  )
}

/* ── States ──────────────────────────────────────────────────────────────── */

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 rise">
      <div className="headline text-[18px] font-semibold text-ink">{title}</div>
      {hint && <p className="mt-1.5 max-w-[42ch] text-[13.5px] text-ink-2 m-0">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex-1 flex items-center justify-center py-20 text-[13px] text-ink-3" role="status" aria-live="polite">
      <span className="inline-block size-2 rounded-full bg-accent live-dot mr-2" />
      {label}
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  const paused = /failed to fetch|503|service unavailable/i.test(message)
  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="hero max-w-[46ch] p-5">
        <div className="headline text-[17px] font-semibold text-ink">Could not load data</div>
        <p className="mt-1.5 text-[13.5px] text-ink-2 m-0">
          {paused
            ? 'The database is not answering. If the Supabase project was paused for inactivity, restore it from the Supabase dashboard and reload.'
            : message}
        </p>
      </div>
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`rounded-md bg-raised animate-pulse ${className}`} />
}

/* ── Icon glyphs (inline SVG, 16px grid) ─────────────────────────────────── */

export function Icon({ name, size = 16, className = '' }: { name: 'sun' | 'moon' | 'search' | 'chevron' | 'close' | 'check' | 'arrow-up' | 'arrow-down' | 'globe' | 'external'; size?: number; className?: string }) {
  const common = { width: size, height: size, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, className, 'aria-hidden': true }
  switch (name) {
    case 'sun': return <svg {...common}><circle cx="8" cy="8" r="3" /><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" /></svg>
    case 'moon': return <svg {...common}><path d="M13.5 9.8A6 6 0 0 1 6.2 2.5a6 6 0 1 0 7.3 7.3z" /></svg>
    case 'search': return <svg {...common}><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" /></svg>
    case 'chevron': return <svg {...common}><path d="M4 6l4 4 4-4" /></svg>
    case 'close': return <svg {...common}><path d="M4 4l8 8M12 4l-8 8" /></svg>
    case 'check': return <svg {...common}><path d="M3 8.5l3 3 7-7" /></svg>
    case 'arrow-up': return <svg {...common}><path d="M8 13V3M4 7l4-4 4 4" /></svg>
    case 'arrow-down': return <svg {...common}><path d="M8 3v10M4 9l4 4 4-4" /></svg>
    case 'globe': return <svg {...common}><circle cx="8" cy="8" r="6" /><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12" /></svg>
    case 'external': return <svg {...common}><path d="M6.5 3H3v10h10V9.5M9 3h4v4M13 3 7 9" /></svg>
  }
}
