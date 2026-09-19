'use client'

import { useState } from 'react'

interface Props {
  logoUrl: string | null
  domain: string | null
  name: string
  size: number
  radius?: 'sm' | 'md' | 'full'
  className?: string
}

function faviconUrl(domain: string, size: number): string {
  // Google returns blank tiles above 64px for many domains, so cap the request size.
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=${size >= 32 ? 64 : 32}`
}

/** Company mark with fallback chain: logo_url → favicon → initials. */
export default function Logo({ logoUrl, domain, name, size, radius = 'md', className = '' }: Props) {
  const [src, setSrc] = useState<string | null>(logoUrl ?? (domain ? faviconUrl(domain, size) : null))
  const [failed, setFailed] = useState(false)
  const r = radius === 'full' ? '9999px' : radius === 'md' ? Math.max(6, Math.round(size * 0.22)) : 4

  if (!src || failed) {
    const initials = name.split(/[\s&,./]+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('')
    return (
      <div
        className={`shrink-0 flex items-center justify-center headline font-semibold text-ink-2 bg-raised ${className}`}
        style={{ width: size, height: size, borderRadius: r, fontSize: Math.max(size * 0.36, 9), boxShadow: 'inset 0 0 0 1px var(--line)' }}
        aria-hidden
      >
        {initials}
      </div>
    )
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => { if (src === logoUrl && domain) setSrc(faviconUrl(domain, size)); else setFailed(true) }}
      className={`shrink-0 object-contain bg-white ${className}`}
      style={{ width: size, height: size, borderRadius: r, boxShadow: 'inset 0 0 0 1px var(--line)', padding: Math.round(size * 0.08) }}
    />
  )
}
