'use client'

import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

const KEY = 'mi-theme'

function readDom(): Theme {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}

/** Theme is owned by <html data-theme>. The init script in layout.tsx sets it before paint. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    setTheme(readDom())
    // Follow the system only while the person has not chosen explicitly.
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      try {
        if (localStorage.getItem(KEY)) return
      } catch { /* storage unavailable */ }
      const next: Theme = mq.matches ? 'dark' : 'light'
      document.documentElement.setAttribute('data-theme', next)
      setTheme(next)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const toggle = useCallback(() => {
    const next: Theme = readDom() === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    try { localStorage.setItem(KEY, next) } catch { /* ignore */ }
    setTheme(next)
  }, [])

  return [theme, toggle]
}
