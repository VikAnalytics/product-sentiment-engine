// Copies ../reports/*.md into public/reports/ and writes an index.json the Brief view reads.
// Runs on `predev` and `prebuild`. Vercel clones the whole repo, so ../reports exists at build time.
import { readdirSync, mkdirSync, copyFileSync, writeFileSync, existsSync, rmSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', '..', 'reports')
const dst = join(here, '..', 'public', 'reports')

if (existsSync(dst)) rmSync(dst, { recursive: true, force: true })
mkdirSync(dst, { recursive: true })

const weekly = []
const daily = []

if (existsSync(src)) {
  for (const f of readdirSync(src)) {
    if (!f.endsWith('.md')) continue
    copyFileSync(join(src, f), join(dst, f))
    if (f.startsWith('weekly_brief_')) {
      weekly.push({ file: f, label: f.replace('weekly_brief_', '').replace('.md', '') })
    } else if (f.startsWith('market_intelligence_')) {
      daily.push({ file: f, label: f.replace('market_intelligence_', '').replace('.md', '') })
    }
  }
}

weekly.sort((a, b) => b.label.localeCompare(a.label))
daily.sort((a, b) => b.label.localeCompare(a.label))

writeFileSync(join(dst, 'index.json'), JSON.stringify({ weekly, daily, generatedAt: new Date().toISOString() }, null, 2))
console.log(`reports synced: ${weekly.length} weekly, ${daily.length} daily`)
