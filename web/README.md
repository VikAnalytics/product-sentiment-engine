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
│   ├── layout.tsx          Root layout — fonts, globals, dynamic export
│   ├── page.tsx            Entry point — view state, sidebar + main area
│   └── globals.css         CSS variables, grain texture, keyframes, utilities
├── components/
│   ├── TopBar.tsx          48px header — clock, title, live indicator
│   ├── Sidebar.tsx         Nav (News Feed / Analysis / Simulator), sector filter, company list
│   ├── NewsFeed.tsx        Chronological headline feed with score + tag badges
│   ├── Analysis.tsx        Deep Dive / Compare / Rankings tabs
│   ├── Simulator.tsx       Portfolio summary, positions, trade log, growth chart
│   └── Logo.tsx            Company logo with fallback: logo_url → favicon → initials
├── lib/
│   ├── supabase.ts         Supabase client + all DB query helpers + TypeScript types
│   └── utils.ts            Score color classes, tag labels, formatters (USD, %, relative time)
└── public/                 Static assets
```

---

## Design System

Dark theme. CSS variables defined in `globals.css`:

| Variable | Use |
|----------|-----|
| `--bg` | Page background (`#0a0a08`) |
| `--gold` | Primary accent (headlines, icons) |
| `--green` / `--red` / `--amber` | Sentiment colors |
| `--ff-d` | Display font (Cormorant Garamond) |
| `--ff-m` | Monospace font (Space Mono) |
| `--ff-b` | Body font (Crimson Pro) |

Score color bands:

| Score | Color |
|-------|-------|
| ≥ 7 | Green |
| 3 – 6 | Lime |
| −2 – +2 | Gray (neutral) |
| −6 – −3 | Amber |
| ≤ −7 | Red |

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
