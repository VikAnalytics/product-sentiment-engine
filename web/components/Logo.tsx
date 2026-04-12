'use client'

import { useState } from 'react'

interface Props {
  logoUrl: string | null
  domain: string | null
  name: string
  size: number
  /** Border radius: 'sm' = 3px, 'md' = 6px, 'full' = 50% */
  radius?: 'sm' | 'md' | 'full'
  style?: React.CSSProperties
}

function faviconUrl(domain: string, size: number): string {
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=${size >= 48 ? 64 : 32}`
}

export default function Logo({ logoUrl, domain, name, size, radius = 'sm', style }: Props) {
  const [src, setSrc] = useState<string | null>(
    logoUrl ?? (domain ? faviconUrl(domain, size) : null)
  )
  const [failed, setFailed] = useState(false)

  const br = radius === 'full' ? '50%' : radius === 'md' ? 6 : 3

  // fallback: initials monogram
  if (!src || failed) {
    const initials = name
      .split(/[\s&,./]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(w => w[0].toUpperCase())
      .join('')
    return (
      <div style={{
        width: size,
        height: size,
        borderRadius: br,
        background: 'var(--bg-p)',
        border: '1px solid var(--br-m)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--ff-m)',
        fontSize: Math.max(size * 0.3, 8),
        fontWeight: 700,
        color: 'var(--tm)',
        flexShrink: 0,
        letterSpacing: '0.05em',
        ...style,
      }}>
        {initials}
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={name}
      width={size}
      height={size}
      onError={() => {
        // try favicon fallback before giving up
        if (src === logoUrl && domain) {
          setSrc(faviconUrl(domain, size))
        } else {
          setFailed(true)
        }
      }}
      style={{
        width: size,
        height: size,
        borderRadius: br,
        objectFit: 'contain',
        background: 'var(--bg-r)',
        flexShrink: 0,
        ...style,
      }}
    />
  )
}
