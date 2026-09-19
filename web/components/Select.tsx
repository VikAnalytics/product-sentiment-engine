'use client'

import { Icon } from '@/components/ui'

export function SelectBox({ value, onChange, options, placeholder, className = '', ariaLabel }: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
  className?: string
  ariaLabel?: string
}) {
  return (
    <label className={`relative inline-flex items-center ${className}`}>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        aria-label={ariaLabel ?? placeholder}
        className={`appearance-none w-full rounded-lg bg-surface border border-line hover:border-line-strong pl-3 pr-8 py-1.5 text-[13px] leading-5 transition-colors ${value ? 'text-ink' : 'text-ink-2'}`}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <Icon name="chevron" size={14} className="pointer-events-none absolute right-2.5 text-ink-3" />
    </label>
  )
}
