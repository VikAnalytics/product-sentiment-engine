'use client'

import { useCallback, useEffect, useState } from 'react'
import { credentialsMissing, fetchTargets, fetchAllTargetScores, Target, TargetScore } from '@/lib/supabase'
import TopBar, { View, VIEWS } from '@/components/TopBar'
import Feed from '@/components/Feed'
import Companies from '@/components/Companies'
import Macro from '@/components/Macro'
import Simulator from '@/components/Simulator'
import Brief from '@/components/Brief'
import { ErrorState } from '@/components/ui'

export type Scores = Record<number, TargetScore>

function parseHash(): { view: View; id: number | null } {
  if (typeof window === 'undefined') return { view: 'feed', id: null }
  const [v, id] = window.location.hash.replace(/^#\/?/, '').split('/')
  const view = (VIEWS.find(x => x.key === v)?.key ?? 'feed') as View
  return { view, id: id && /^\d+$/.test(id) ? Number(id) : null }
}

export default function Home() {
  const [view, setViewState] = useState<View>('feed')
  const [targets, setTargets] = useState<Target[]>([])
  const [scores, setScores] = useState<Scores>({})
  const [selectedId, setSelectedIdState] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  // URL hash keeps view + selection shareable and survives reloads.
  useEffect(() => {
    const apply = () => { const h = parseHash(); setViewState(h.view); if (h.id != null) setSelectedIdState(h.id) }
    apply()
    window.addEventListener('hashchange', apply)
    return () => window.removeEventListener('hashchange', apply)
  }, [])

  const setView = useCallback((v: View) => {
    setViewState(v)
    const id = v === 'companies' && selectedId != null ? `/${selectedId}` : ''
    history.replaceState(null, '', `#${v}${id}`)
  }, [selectedId])

  const selectTarget = useCallback((id: number) => {
    setSelectedIdState(id)
    setViewState('companies')
    history.replaceState(null, '', `#companies/${id}`)
  }, [])

  useEffect(() => {
    // Without credentials every request goes to a placeholder host and hangs,
    // leaving the page on "Loading signals" forever. Say so instead of waiting.
    if (credentialsMissing) {
      setError('This build has no Supabase credentials.')
      return
    }
    Promise.all([fetchTargets(), fetchAllTargetScores()])
      .then(([t, s]) => {
        setTargets(t)
        setScores(s)
        setSelectedIdState(cur => {
          if (cur != null) return cur
          const ranked = t.filter(x => x.target_type === 'COMPANY').sort((a, b) => (s[b.id]?.avg ?? -99) - (s[a.id]?.avg ?? -99))
          return ranked[0]?.id ?? null
        })
      })
      .catch(e => setError(e?.message ?? String(e)))
  }, [])

  return (
    <div className="h-full flex flex-col">
      <TopBar view={view} onViewChange={setView} targets={targets} scores={scores} onSelectTarget={selectTarget} />
      <main className="flex-1 min-h-0 flex flex-col" style={{ paddingTop: 'var(--topbar-h)' }}>
        {error ? <ErrorState message={error} /> : (
          <>
            {view === 'feed' && <Feed onSelectTarget={selectTarget} onOpenMacro={() => setView('macro')} />}
            {view === 'companies' && <Companies targets={targets} scores={scores} selectedId={selectedId} onSelect={selectTarget} />}
            {view === 'macro' && <Macro />}
            {view === 'simulator' && <Simulator />}
            {view === 'brief' && <Brief />}
          </>
        )}
      </main>
    </div>
  )
}
