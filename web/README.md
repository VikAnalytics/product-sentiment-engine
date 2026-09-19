# Market Intelligence Engine — Web Dashboard

Next.js 16 (App Router) dashboard for the Market Intelligence Engine. Deployed on Vercel.

**Live:** https://market-intelligence-engine-five.vercel.app

---

## Local Development

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Environment Variables

Create `web/.env.local`:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

Use the **anon** key (not service_role). Get both from Supabase → Project Settings → API.

---

## Structure

```
web/
├── app/
│   ├── layout.tsx          Root layout — next/font (Bricolage Grotesque, DM Sans), theme init script
│   ├── page.tsx            Shell — view state synced to URL hash (#companies/123), loads targets + scores
│   └── globals.css         Tailwind v4 tokens (@theme inline), light/dark palettes, motion, brief prose styles
├── components/
│   ├── TopBar.tsx          Brand, primary nav, ⌘K search palette, theme toggle, live dot
│   ├── Feed.tsx            Mood panel (ambient gradient = today's sentiment) + company / macro columns
│   ├── Companies.tsx       Ranked rail (search, sector, F500, sort, compare picker) + main pane
│   ├── DeepDive.tsx        Company hero, sentiment + price sparklines, expandable event rows
│   ├── Compare.tsx         Up to four companies side by side
│   ├── Macro.tsx           Macro themes with 7-day score, sector exposure bars, latest headlines
│   ├── Simulator.tsx       Portfolio hero + growth chart vs SPY/QQQ, queue, holdings, trade log, strategy
│   ├── Brief.tsx           Weekly and daily reports rendered from public/reports (react-markdown)
│   ├── ui.tsx              Score, TagChip, Chip, SectionHead, Segmented, Sparkline, states, icons
│   ├── Select.tsx          Styled native select
│   └── Logo.tsx            Company mark with fallback: logo_url → favicon → initials
├── lib/
│   ├── supabase.ts         Supabase client + query helpers + TypeScript types
│   ├── utils.ts            Score bands, tone colors, mood gradient, formatters
│   └── theme.ts            useTheme(): reads/writes <html data-theme>, persists to localStorage
├── scripts/
│   └── sync-reports.mjs    predev/prebuild: copies ../reports/*.md → public/reports + index.json
└── public/                 Static assets (public/reports is generated, git-ignored)
```

---

## Design System

Light and dark, toggled in the top bar (persisted per browser, follows system by default). Tokens live in `globals.css` and are exposed to Tailwind through `@theme inline`, so `bg-surface`, `text-ink-2`, `border-line` etc. resolve per theme.

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--bg` | `#EEEFF1` | `#141519` | Page ground |
| `--surface` | `#FFFFFF` | `#1D1E24` | Hero panels, cards |
| `--ink` / `--ink-2` / `--ink-3` | `#17181C` / `#5B5E6B` / `#8E919D` | `#EEEFF3` / `#A3A6B3` / `#6E717E` | Text hierarchy |
| `--accent` | `#5646E6` | `#8F84FF` | Nav, selection, links |
| `--pos` / `--neg` / `--warn` | `#178A4E` / `#CF3A31` / `#C77A14` | `#3FD48A` / `#FF6A5F` / `#FFB347` | Sentiment and P&L |
| `--macro` | `#0E8288` | `#3EC3C9` | Macro themes |

Type: **Bricolage Grotesque** for display and headlines (`.display`, `.headline`, `.figure`), **DM Sans** for everything else, with tabular numerals (`.tnum`) on data.

Score bands: ≥7 very positive, 3–6 positive, −2–+2 neutral, −6–−3 negative, ≤−7 very negative (`scoreTone()` in `lib/utils.ts`).

Motion: one load choreography per view (`.rise`, `.stagger`, mood bloom + drift, sparkline draw). `prefers-reduced-motion` disables it.

---

## Key Query Helpers (`lib/supabase.ts`)

| Function | Returns |
|----------|---------|
| `fetchTargets()` | All tracked targets with sector, ticker, logo |
| `fetchAllTargetScores()` | Avg sentiment score per target (last 30 days) |
| `fetchRecentHeadlines(hours)` | News feed — events joined with scores + tags |
| `fetchTargetWithEvents(id)` | Single target with full event + price reaction data |
| `fetchSimData()` | All 5 simulator tables in parallel |
| `fetchLatestPricesForTickers(tickers)` | Latest close price per ticker |

---

## Deployment

Auto-deploys from `main` via Vercel. See [docs/DEPLOY.md](../docs/DEPLOY.md) for full setup instructions.
