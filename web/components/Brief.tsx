'use client'

import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Empty, Loading, Segmented } from '@/components/ui'
import { SelectBox } from '@/components/Select'

type Kind = 'weekly' | 'daily'
interface Index { weekly: { file: string; label: string }[]; daily: { file: string; label: string }[]; generatedAt: string }

export default function Brief() {
  const [index, setIndex] = useState<Index | null>(null)
  const [kind, setKind] = useState<Kind>('weekly')
  const [file, setFile] = useState<string>('')
  const [md, setMd] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/reports/index.json').then(r => r.ok ? r.json() : { weekly: [], daily: [], generatedAt: '' }).then((ix: Index) => {
      setIndex(ix)
      const k: Kind = ix.weekly.length ? 'weekly' : 'daily'
      setKind(k)
      setFile(ix[k][0]?.file ?? '')
    }).catch(() => setIndex({ weekly: [], daily: [], generatedAt: '' })).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!file) { setMd(''); return }
    fetch(`/reports/${file}`).then(r => r.ok ? r.text() : '').then(setMd).catch(() => setMd(''))
  }, [file])

  if (loading || !index) return <Loading label="Loading briefs" />

  const list = index[kind]
  const hasAny = index.weekly.length + index.daily.length > 0

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-[1080px] mx-auto px-4 md:px-6 py-5 md:py-6">
        <div className="flex flex-col md:flex-row md:items-end gap-4 rise">
          <div className="flex-1">
            <h1 className="display text-[34px] md:text-[40px] font-semibold m-0">Executive brief</h1>
            <p className="m-0 mt-2 text-[14.5px] text-ink-2 max-w-[64ch]">Written by the pipeline from the week's signals: what moved, the top opportunities and risks, and what to do about it.</p>
          </div>
          {hasAny && (
            <div className="flex items-center gap-2">
              <Segmented value={kind} onChange={k => { setKind(k); setFile(index[k][0]?.file ?? '') }} size="md" options={[{ value: 'weekly', label: 'Weekly' }, { value: 'daily', label: 'Daily' }]} />
              <SelectBox value={file} onChange={setFile} options={list.map(x => ({ value: x.file, label: kind === 'weekly' ? `Week ${x.label.replace('-W', ' ')}` : x.label }))} ariaLabel="Which brief" />
            </div>
          )}
        </div>

        {!hasAny ? (
          <Empty title="No briefs published yet" hint="Weekly briefs are generated on Mondays and daily reports after each pipeline run. They show up here on the next deploy." />
        ) : !md ? (
          <Empty title="Nothing for this selection" hint="Pick another week or day." />
        ) : (
          <article className="hero mt-6 p-6 md:p-10 fade">
            <div className="prose-brief">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a> }}>
                {md}
              </ReactMarkdown>
            </div>
          </article>
        )}
      </div>
    </div>
  )
}
