'use client'

import { useEffect, useState } from 'react'

export default function TopBar() {
  const [time, setTime] = useState('')

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(now.toLocaleTimeString('en-US', {
        timeZone: 'America/New_York',
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }) + ' EST')
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0,
      height: '48px',
      background: 'var(--bg)',
      borderBottom: '1px solid var(--br)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 16px',
      zIndex: 200,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{
          fontFamily: 'var(--ff-m)',
          fontSize: 13,
          fontWeight: 700,
          color: 'var(--gold)',
          letterSpacing: '0.25em',
        }}>M · I · E</span>
        <div style={{ width: 1, height: 16, background: 'var(--br-m)' }} />
        <span style={{
          fontFamily: 'var(--ff-m)',
          fontSize: 11,
          color: 'var(--tm)',
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
        }}>Market Intelligence Engine &nbsp;·&nbsp; Internal Use Only</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{
          fontFamily: 'var(--ff-m)',
          fontSize: 12,
          color: 'var(--t2)',
          letterSpacing: '0.04em',
        }}>{time}</span>
        <div style={{
          width: 6, height: 6,
          borderRadius: '50%',
          background: 'var(--green)',
          boxShadow: '0 0 6px var(--green)',
          animation: 'blink 2.2s ease-in-out infinite',
        }} />
      </div>
    </div>
  )
}
