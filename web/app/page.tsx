'use client'

import { useEffect, useState } from 'react'
import { fetchTargets, fetchAllTargetScores, Target } from '@/lib/supabase'
import TopBar from '@/components/TopBar'
import Sidebar from '@/components/Sidebar'
import NewsFeed from '@/components/NewsFeed'
import Analysis from '@/components/Analysis'
import Simulator from '@/components/Simulator'

type View = 'feed' | 'analysis' | 'simulator'

export default function Home() {
  const [view, setView] = useState<View>('feed')
  const [targets, setTargets] = useState<Target[]>([])
  const [scores, setScores] = useState<Record<number, { avg: number; count: number }>>({})
  const [selectedId, setSelectedId] = useState<number | null>(null)

  useEffect(() => {
    Promise.all([fetchTargets(), fetchAllTargetScores()]).then(([t, s]) => {
      setTargets(t)
      setScores(s)
      // auto-select first company
      const first = t.find(x => x.target_type === 'COMPANY')
      if (first) setSelectedId(first.id)
    })
  }, [])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <TopBar />
      <div style={{ display: 'flex', height: '100%', paddingTop: '48px' }}>
        <Sidebar
          view={view}
          onViewChange={setView}
          targets={targets}
          scores={scores}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {view === 'feed' && <NewsFeed />}
          {view === 'analysis' && <Analysis targetId={selectedId} />}
          {view === 'simulator' && <Simulator />}
        </main>
      </div>
    </div>
  )
}
