# Deploying the Dashboard

Deploy to **Streamlit Community Cloud** (free tier) so the dashboard is accessible online.

---

## 1. Push Code to GitHub

Ensure your repo is on GitHub and up to date:

```bash
git push origin main
```

---

## 2. Deploy on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **New app**.
3. Set the following:
   - **Repository:** `VikAnalytics/product-sentiment-engine`
   - **Branch:** `main`
   - **Main file path:** `src/app.py`
4. Click **Advanced settings** and set **Python version** to `3.11`.
5. Add secrets (same page, or later via app **Settings → Secrets**):

   ```toml
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_KEY = "your-service-role-key"
   ```

   Use the **service_role** key. The dashboard is read-only — it never writes to Supabase — so service_role is safe and avoids RLS issues. If you prefer the anon key, apply migration `006_rls_read_policies.sql` first.

   `OPENAI_API_KEY` is **not** required for the dashboard.

6. Click **Deploy**. First boot takes a few minutes (install + model download).

---

## 3. Apply Supabase Migrations

Before the dashboard loads correctly, all migrations in `supabase/migrations/` (`000` through `014`) must be applied to your Supabase project. See [supabase/README.md](../supabase/README.md).

Migration `006_rls_read_policies.sql` is required if you are using the anon key.

---

## 4. After Deployment

- Your app will be at `https://your-app-name.streamlit.app`.
- To update: push to `main` — Streamlit Cloud redeploys automatically.
- To change secrets or settings: open the app on share.streamlit.io → **Settings**.

---

## 5. Troubleshooting

### White-on-white dropdowns or wrong colors

The app uses a dark theme. Ensure `.streamlit/config.toml` contains `base = "dark"`. If it reverts to `base = "light"`, native Streamlit components (dropdowns, selectboxes) will render with white text on a white background.

### API error on first load

- Verify the `SUPABASE_URL` and `SUPABASE_KEY` secrets are set correctly in Streamlit Cloud (Settings → Secrets).
- Paste the full service_role key with no leading/trailing whitespace.
- Confirm the key belongs to the same Supabase project as the URL.

### Stale build after a code push

Streamlit Cloud may serve a cached build. Force a redeploy from the app dashboard (three-dot menu → **Reboot app**).

---

## Note on Dependencies

Streamlit Community Cloud resolves dependencies from `src/requirements.txt` when the main file path is `src/app.py`. This is a lighter set (dashboard-only) compared to the root `requirements.txt` (full pipeline including spaCy, sentence-transformers, yfinance). This keeps dashboard deploys fast.
