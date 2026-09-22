'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Target } from '@/lib/supabase'
import { useTheme } from '@/lib/theme'
import { Icon, Score } from '@/components/ui'
import Logo from '@/components/Logo'

export type View = 'feed' | 'companies' | 'macro' | 'simulator' | 'brief'
export const VIEWS: { key: View; label: string }[] = [
  { key: 'feed', label: 'Feed' },
  { key: 'companies', label: 'Companies' },
  { key: 'macro', label: 'Macro' },
  { key: 'simulator', label: 'Simulator' },
  { key: 'brief', label: 'Brief' },
]

interface Props {
  view: View
  onViewChange: (v: View) => void
  targets: Target[]
  scores: Record<number, { avg: number; count: number }>
  onSelectTarget: (id: number) => void
}

export default function TopBar({ view, onViewChange, targets, scores, onSelectTarget }: Props) {
  const [theme, toggleTheme] = useTheme()
  const [searchOpen, setSearchOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearchOpen(v => !v) }
      if (e.key === '/' && !searchOpen && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement)) { e.preventDefault(); setSearchOpen(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [searchOpen])

  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-40 flex items-center gap-4 px-4 md:px-6 bg-bg/85 backdrop-blur-md border-b border-line"
        style={{ height: 'var(--topbar-h)' }}
      >
        <button onClick={() => onViewChange('feed')} className="flex items-center gap-2.5 shrink-0" aria-label="Market Intelligence, go to feed">
          <Mark />
          <span className="headline text-[16px] font-semibold text-ink hidden sm:inline">Market Intelligence</span>
        </button>

        <nav className="flex-1 flex justify-center min-w-0" aria-label="Primary">
          <ul className="flex items-stretch gap-1 md:gap-2 m-0 p-0 list-none overflow-x-auto" style={{ height: 'var(--topbar-h)' }}>
            {VIEWS.map(v => {
              const active = v.key === view
              return (
                <li key={v.key} className="relative flex">
                  <button
                    onClick={() => onViewChange(v.key)}
                    aria-current={active ? 'page' : undefined}
                    className={`px-3.5 md:px-4 text-[14px] font-medium transition-colors whitespace-nowrap ${active ? 'text-ink' : 'text-ink-2 hover:text-ink'}`}
                  >
                    {v.label}
                  </button>
                  <span
                    className="absolute left-3.5 right-3.5 bottom-0 h-[2px] rounded-full bg-accent transition-transform duration-300 origin-center"
                    style={{ transform: active ? 'scaleX(1)' : 'scaleX(0)', transitionTimingFunction: 'cubic-bezier(0.22,1,0.36,1)' }}
                  />
                </li>
              )
            })}
          </ul>
        </nav>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={() => setSearchOpen(true)}
            className="flex items-center gap-2 h-8 rounded-lg px-2.5 text-[13px] text-ink-2 hover:text-ink bg-surface border border-line hover:border-line-strong transition-colors"
            aria-label="Search companies"
          >
            <Icon name="search" size={15} />
            <span className="hidden md:inline">Search</span>
            <kbd className="hidden md:inline text-[11px] text-ink-3 font-sans">⌘K</kbd>
          </button>
          <button
            onClick={toggleTheme}
            className="relative size-8 rounded-lg text-ink-2 hover:text-ink hover:bg-surface transition-colors grid place-items-center overflow-hidden"
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
          >
            <span className="absolute transition-all duration-300" style={{ transform: theme === 'dark' ? 'translateY(0) rotate(0)' : 'translateY(120%) rotate(-40deg)', opacity: theme === 'dark' ? 1 : 0 }}><Icon name="sun" size={16} /></span>
            <span className="absolute transition-all duration-300" style={{ transform: theme === 'dark' ? 'translateY(-120%) rotate(40deg)' : 'translateY(0) rotate(0)', opacity: theme === 'dark' ? 0 : 1 }}><Icon name="moon" size={16} /></span>
          </button>
          <div className="hidden sm:flex items-center gap-1.5 pl-2 text-[12.5px] text-ink-2" title="Data refreshes daily after market close">
            <span className="size-1.5 rounded-full bg-pos live-dot" />
            Live
          </div>
        </div>
      </header>

      {searchOpen && (
        <SearchPalette targets={targets} scores={scores} onClose={() => setSearchOpen(false)} onPick={id => { setSearchOpen(false); onSelectTarget(id) }} />
      )}
    </>
  )
}

function Mark() {
  // Three rising bars, the last one crossing the baseline: sentiment and price on one glyph.
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden>
      <rect x="2" y="12" width="4" height="8" rx="1.2" fill="var(--ink-3)" />
      <rect x="9" y="7" width="4" height="13" rx="1.2" fill="var(--ink-2)" />
      <rect x="16" y="2" width="4" height="18" rx="1.2" fill="var(--accent)" />
    </svg>
  )
}

function SearchPalette({ targets, scores, onClose, onPick }: {
  targets: Target[]
  scores: Record<number, { avg: number; count: number }>
  onClose: () => void
  onPick: (id: number) => void
}) {
  const [q, setQ] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const pool = targets.filter(t => t.target_type !== 'MACRO')
    const hits = needle
      ? pool.filter(t => t.name.toLowerCase().includes(needle) || (t.ticker ?? '').toLowerCase() === needle)
      : pool.filter(t => t.target_type === 'COMPANY')
    return hits
      .sort((a, b) => {
        const an = a.name.toLowerCase().startsWith(needle) ? 0 : 1
        const bn = b.name.toLowerCase().startsWith(needle) ? 0 : 1
        if (an !== bn) return an - bn
        return (scores[b.id]?.count ?? 0) - (scores[a.id]?.count ?? 0)
      })
      .slice(0, 10)
  }, [q, targets, scores])

  useEffect(() => setCursor(0), [q])

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(results.length - 1, c + 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(0, c - 1)) }
    if (e.key === 'Enter' && results[cursor]) onPick(results[cursor].id)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4 bg-black/30 backdrop-blur-[2px] fade" onMouseDown={onClose} role="dialog" aria-modal aria-label="Search companies">
      <div className="w-full max-w-[560px] rounded-2xl bg-surface shadow-pop border border-line overflow-hidden rise" onMouseDown={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 px-4 border-b border-line">
          <Icon name="search" size={16} className="text-ink-3" />
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={onKey}
            placeholder="Company or ticker"
            className="flex-1 h-12 bg-transparent outline-none text-[15px] placeholder:text-ink-3"
          />
          <button onClick={onClose} className="text-ink-3 hover:text-ink" aria-label="Close search"><Icon name="close" size={16} /></button>
        </div>
        <ul className="m-0 p-1.5 list-none max-h-[52vh] overflow-y-auto">
          {results.length === 0 && <li className="px-3 py-6 text-center text-[13px] text-ink-3">No company matches “{q}”.</li>}
          {results.map((t, i) => (
            <li key={t.id}>
              <button
                onMouseEnter={() => setCursor(i)}
                onClick={() => onPick(t.id)}
                className={`w-full flex items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors ${i === cursor ? 'bg-raised' : ''}`}
              >
                <Logo logoUrl={t.logo_url} domain={t.domain} name={t.name} size={26} />
                <span className="flex-1 min-w-0">
                  <span className="block text-[14px] text-ink truncate">{t.name}</span>
                  <span className="block text-[12px] text-ink-3 truncate">{[t.ticker, t.sector, t.target_type === 'PRODUCT' ? 'Product' : null].filter(Boolean).join('  ')}</span>
                </span>
                <Score value={scores[t.id]?.avg ?? null} size="sm" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
