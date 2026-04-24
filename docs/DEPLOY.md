# Deploying the Web Dashboard

The dashboard is a Next.js app in `web/` deployed to **Vercel**. It auto-deploys on every push to `main`.

---

## Live URL

**Production:** https://market-intelligence-engine-five.vercel.app

---

## Prerequisites

- The GitHub repo is connected to the Vercel project (already configured).
- Two environment variables set in Vercel → Project → Settings → Environment Variables:
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

Use the **anon** (public) key — not the service_role key. RLS policies in migrations `006` and `016` grant read access to the anon key. New tables from migrations 017 (`macro_sector_exposure`) and 018 (`pipeline_runs`) need their own RLS policies if the dashboard needs to read them with the anon key — currently they are read via the service_role key on the pipeline side and the new Macro tab in Streamlit, which uses the service key.

---

## Deploying

Every push to `main` triggers an automatic Vercel build. No manual steps needed.

To deploy manually from the CLI:

```bash
cd web
vercel --prod
```

---

## First-Time Setup (if starting from scratch)

### 1. Install Vercel CLI

```bash
npm install -g vercel
```

### 2. Link the project

```bash
cd web
vercel link
```

### 3. Set environment variables

```bash
vercel env add NEXT_PUBLIC_SUPABASE_URL
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY
```

Select **All** environments (Production, Preview, Development) when prompted.

### 4. Connect GitHub for auto-deploy

Vercel Dashboard → Project → Settings → Git → Connect Git Repository → select `VikAnalytics/product-sentiment-engine`.

Set **Root Directory** to `web` in Vercel Dashboard → Project → Settings → General.

### 5. Apply Supabase migrations

Before the dashboard loads correctly, all migrations in `supabase/migrations/` (`000` through `018`) must be applied. See [supabase/README.md](../supabase/README.md). After `017_macro_targets.sql`, run `PYTHONPATH=src python scripts/seed_macro_targets.py` to seed the 8 MACRO themes used by the Macro tab and the simulator's `macro_exposure` factor.

---

## Environment Variables

| Variable | Value | Notes |
|----------|-------|-------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` | Supabase → Project Settings → API |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJ...` | Supabase → Project Settings → API → anon key |

`NEXT_PUBLIC_` prefix means these values are embedded at build time and visible in the browser bundle. The anon key is safe to expose — it is rate-limited and restricted by RLS policies.

---

## Troubleshooting

### Build error: "Couldn't find any pages or app directory"

Vercel is building from the repo root instead of `web/`. Fix: Vercel Dashboard → Project → Settings → General → Root Directory → set to `web`.

### Build error: "supabaseUrl is required"

Environment variables are not set. Run `vercel env ls` to verify. If missing, add them with `vercel env add`.

### Data not loading

- Verify `NEXT_PUBLIC_SUPABASE_ANON_KEY` is the anon key (not service_role).
- Confirm migrations `006_rls_read_policies.sql` and `016_rls_remaining_tables.sql` are applied — these grant read access to the anon key.
- Open browser DevTools → Network tab — look for failed Supabase requests and check the error message.

### Stale build after a code push

Vercel builds automatically on every push. If it hasn't triggered, check the Vercel dashboard → Deployments for build status and errors.
