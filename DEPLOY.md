# Deploy the Streamlit dashboard

Deploy to **Streamlit Community Cloud** (free) so the dashboard is available online.

## 1. Push your code to GitHub

Ensure your repo is on GitHub and up to date:

```bash
git add .
git commit -m "Prepare Streamlit deploy"
git push origin main
```

## 2. Deploy on Streamlit Community Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub.
2. Click **"New app"**.
3. **Repository:** `your-username/product-sentiment-engine`  
   **Branch:** `main`  
   **Main file path:** `src/app.py`
4. Click **"Advanced settings"** and set **Python version** to 3.9 or 3.11.  
   Because your main file is `src/app.py`, Streamlit Cloud will look for dependencies in `src/` first and use **`src/requirements.txt`** (dashboard-only, fast install). No need to change the requirements path.
5. Add **Secrets** (same page or in app **Settings → Secrets**):

   ```toml
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_KEY = "your-service-role-key"
   ```

   Use the **service_role** key (Project Settings → API in Supabase), not the anon key, so the dashboard can read all tables. If you prefer the anon key, run migration **`006_rls_read_policies.sql`** on your project so RLS allows public read on `targets`, `events`, and `sentiment`.

   The dashboard only reads from Supabase; **OPENAI_API_KEY** is not required for the app. (Scout, tracker, and report need it when you run them locally.)

6. Click **"Deploy"**. The first run may take a few minutes (install + start).

## 3. Supabase migrations

Ensure all migrations in `supabase/migrations/` have been applied to your Supabase project (Dashboard → SQL Editor, or `supabase db push`). In particular, **`006_rls_read_policies.sql`** adds read policies so the app can load targets and events; without it, the request may fail with an API error if RLS is enabled and no policies exist.

## 4. After deploy

- Your app will be at `https://your-app-name.streamlit.app`.
- To update: push to the same branch; Streamlit Cloud will redeploy.
- To change secrets or settings: open the app on share.streamlit.io → **Settings**.

## 5. If you see a redacted "APIError" on the app

- **Push the latest code and redeploy.** The app includes an error handler that shows the real Supabase message (code, message, details) instead of a redacted one. If the traceback points to `targets = fetch_targets()` around line 671 with no try/except, the deployed build is old — push, wait for redeploy, then reload the app to see the actual error.
- **Check Streamlit secrets format** (Settings → Secrets):
  - Use TOML: `SUPABASE_URL = "https://..."` and `SUPABASE_KEY = "eyJ..."` (quotes allowed).
  - Paste the **entire** service_role key with no leading/trailing spaces or newlines.
  - Ensure the key is from the same Supabase project as the URL.

## Note on dependencies

- **Streamlit Community Cloud** uses `src/requirements.txt` when the app path is `src/app.py` (dashboard-only deps → faster deploy).
- **Local runs** use the root `requirements.txt` (full pipeline: scout, tracker, report).
