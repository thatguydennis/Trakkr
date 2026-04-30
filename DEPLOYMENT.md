# Trakkr — Deployment Guide

Step-by-step playbook for deploying Trakkr to production. Frontend goes to Vercel, backend goes to Render. Both are free-tier-friendly. The whole flow takes ~30 minutes the first time, and a few seconds for subsequent updates.

---

## 1. Prerequisites

- A **GitHub account** with this repo pushed.
- A **Vercel account** (sign in with GitHub).
- A **Render account** (sign in with GitHub).
- A **Mapbox public token** (`pk.…`) — already provisioned. The fallback in `api/app.py` will work if you don't set the env var, but for production *set the env var* and restrict the token's allowed referrers in the Mapbox dashboard.
- *(Optional)* A custom domain (e.g. `trakkr.app`).

---

## 2. Deploy the backend (Render)

1. Push the repo to GitHub.
2. Go to **Render.com → New → Blueprint**.
3. Select the GitHub repo. Render auto-detects `render.yaml` at the root.
4. On the env-var screen Render will prompt for the values that have `sync: false`:
   - `MAPBOX_TOKEN` — your `pk.…` token.
   - `CORS_ORIGINS` — leave **empty for now**. We'll fill it in after the frontend is deployed (otherwise the API won't know its caller's origin).
5. Click **Apply**. Render builds and starts the service.
6. Wait for the deploy to go green. Copy the public URL — it'll look like `https://trakkr-api.onrender.com`.
7. Sanity-check: `curl https://trakkr-api.onrender.com/health` should return JSON with `"forecast": {"ready": true, …}`. If `ready: false`, the forecast artifacts aren't bundled — see "Forecast artifacts on Render" below.

### 2.1 Forecast artifacts on Render

The pipeline writes forecasts to `data/artifacts/<run_id>/`. For the API to serve them in production, those CSVs **must travel with the deploy** (Render builds from the GitHub repo).

Two options:

- **(Easiest, current setup)** Commit the artifacts to git. They're a few MB of CSV — fine for a small project. Make sure `.gitignore` does *not* exclude `data/artifacts/`.
- **(Cleaner long-term)** Run the pipeline in CI on a schedule, push the artifacts to S3 / GCS, and have the API download them on boot. Out of scope for the hackathon launch.

---

## 3. Deploy the frontend (Vercel)

1. **Vercel → Add New → Project**, pick the same GitHub repo.
2. **Root Directory**: set to `frontend` (Vercel needs to know that's where the static site lives).
3. **Framework preset**: "Other" (it's plain HTML).
4. **Build Command**: leave blank.
5. **Output Directory**: leave blank (Vercel serves from root when no build step).
6. Click **Deploy**.
7. Vercel issues a URL like `https://trakkr.vercel.app`. Open it — the homepage should load with all the rotating-word animation, header, footer, and Feedback pill intact.

### 3.1 Wire the frontend's API base URL

`dashboard.html` reads its API base from a `<meta name="trakkr-api">` tag. In dev it falls back to `http://localhost:8001`. For production, add the meta tag in the `<head>` of `dashboard.html`:

```html
<meta name="trakkr-api" content="https://trakkr-api.onrender.com"/>
```

Or, if you've already wired a custom domain (e.g. `api.trakkr.app`):

```html
<meta name="trakkr-api" content="https://api.trakkr.app"/>
```

The override precedence is: `window.TRAKKR_API` (set in inline JS, useful for previews) → `<meta name="trakkr-api">` (the recommended way) → an automatic `https://api.${current_hostname}` fallback if the page is served from a non-localhost domain.

Commit the change, push — Vercel auto-redeploys.

---

## 4. Lock CORS to your live frontend

Now that you have both URLs, complete the loop:

1. Go to **Render → trakkr-api → Environment** and set:

   ```
   CORS_ORIGINS=https://trakkr.vercel.app,https://www.trakkr.app
   ```

   List every domain the dashboard might be served from (Vercel preview URL, custom domain, www / apex variants).
2. Render will redeploy automatically.
3. Reload the dashboard — the network tab should show successful API calls. If you see `CORS error`, your `CORS_ORIGINS` value doesn't match the browser's origin exactly (check protocol + host + port).

---

## 5. Custom domain (optional)

### 5.1 Vercel (frontend)

1. **Vercel → Project → Settings → Domains → Add**.
2. Enter `www.trakkr.app` (or whatever you own).
3. Vercel shows DNS records — add them at your registrar.
4. Within minutes, your site is live on the custom domain.

### 5.2 Render (backend)

1. **Render → trakkr-api → Settings → Custom Domain**.
2. Enter `api.trakkr.app`.
3. Add the CNAME at your registrar.
4. Update `dashboard.html`'s API base URL to `https://api.trakkr.app`.
5. Update `CORS_ORIGINS` on Render to include `https://www.trakkr.app` and any apex.

---

## 6. Make OG, canonical, sitemap, and robots.txt absolute

The frontend ships with **relative** `og:url`, `og:image`, `twitter:image`, `<link rel="canonical">`, and `Sitemap:` references. Search engines and social-card scrapers (Twitter, Facebook, LinkedIn, iMessage) require absolute URLs — relative refs are silently ignored, breaking link previews and SEO.

Run this once after you know the production domain (replace `https://www.trakkr.app` below if yours differs):

```bash
# from repo root
DOMAIN="https://www.trakkr.app"

# 1. Fix sitemap.xml — already absolute, just swap the placeholder if your domain differs
sed -i '' "s|https://www.trakkr.app|$DOMAIN|g" frontend/sitemap.xml

# 2. Fix robots.txt — replace the relative Sitemap: directive with absolute
sed -i '' "s|^Sitemap: /sitemap.xml|Sitemap: $DOMAIN/sitemap.xml|" frontend/robots.txt

# 3. Make OG/canonical/Twitter URLs absolute on every page
python3 - <<PY
import os, re
DOMAIN = "$DOMAIN"
for f in os.listdir('frontend'):
    if not f.endswith('.html'): continue
    p = os.path.join('frontend', f)
    src = open(p).read()
    # Make canonical absolute
    src = re.sub(
      r'<link rel="canonical" href="([^"]+\.html)"/>',
      lambda m: f'<link rel="canonical" href="{DOMAIN}/{m.group(1) if m.group(1)!="index.html" else ""}"/>',
      src)
    # Make og:url, og:image, twitter:image absolute when they're page-relative
    src = re.sub(
      r'(<meta property="og:url" content=")([^"]+\.html)("/>)',
      lambda m: f'{m.group(1)}{DOMAIN}/{m.group(2) if m.group(2)!="index.html" else ""}{m.group(3)}',
      src)
    src = re.sub(
      r'(<meta (?:property|name)="(?:og|twitter):image" content=")(favicon\.svg)("/>)',
      lambda m: f'{m.group(1)}{DOMAIN}/social-card.png{m.group(3)}',
      src)
    open(p,'w').write(src)
    print('updated', f)
PY
```

**Social card image.** Both `frontend/social-card.svg` and `frontend/social-card.png` ship with the repo. The PNG is the default OG image after the substitution above; every social platform (Twitter, Facebook, LinkedIn, iMessage, Slack, Discord) renders it. Replace either file with branded artwork later if you want, but it's deploy-ready as-is.

Submit the sitemap to Google Search Console once the domain is live.

---

## 7. Smoke test the deployed site

Run this checklist before announcing:

- [ ] `https://YOUR-DOMAIN/` loads and shows the rotating headline animation.
- [ ] `https://YOUR-DOMAIN/dashboard.html` loads, the map renders Mapbox tiles (not a blank gray box).
- [ ] Type a real NYC address (e.g. `Times Square`) → station report renders, Trakkr verdict shown, equipment list populated, MTA live panels show data.
- [ ] Click the floating **Feedback** pill → land on `feedback.html` → submit a test message → confirm it arrives in `worksbydennis@gmail.com`.
- [ ] Footer Privacy / Legal / Accessibility links all open the right page.
- [ ] `https://api.YOUR-DOMAIN/health` returns `{"status":"ok","forecast":{"ready":true, …}}`.
- [ ] `https://api.YOUR-DOMAIN/v1/lookup?address=Grand+Central` returns a JSON report.
- [ ] No CORS errors in browser console.
- [ ] Mobile test: open the homepage on a phone, check the rotating word animation and search form.

---

## 8. Updates after first deploy

| Change | What to do |
|---|---|
| Edit a frontend page (HTML/CSS/JS) | Push to `main` → Vercel auto-redeploys (~30 sec) |
| Edit a backend route | Push to `main` → Render auto-redeploys (~2 min build + restart) |
| New monthly forecast | Run `ops/run_mvp_pipeline.sh`, commit `data/artifacts/<new_run>/` and the updated `data/artifacts/latest/forecast.json`, push → Render redeploys with the new pointer |
| Rotate Mapbox token | Update `MAPBOX_TOKEN` in Render env vars, save → service auto-restarts |
| Adjust CORS allowlist | Update `CORS_ORIGINS` env var in Render |

---

## 9. Rollback

### 9.1 Frontend (Vercel)

Vercel keeps every deployment. **Project → Deployments → ⋯ → Promote to Production** rolls back instantly.

### 9.2 Backend (Render)

Render keeps deploys for 7 days. **Service → Deploys → previous deploy → Redeploy** to revert.

### 9.3 Forecast snapshot

If a bad forecast publishes:

```bash
python3 ops/rollback_latest.py --to <previous_run_id>
git add data/artifacts/latest/forecast.json
git commit -m "rollback forecast to <run_id>"
git push
```

Render redeploys with the older pointer.

---

## 10. Pre-launch hardening checklist

Stuff worth doing before you point the press at it:

- [x] ~~Add rate limiting on `/v1/lookup`~~ — done (slowapi @ 30 req/min/IP)
- [ ] **Finish locking the Mapbox token's allowed URLs.** The dev-localhost entries are already on the token (`http://localhost:8765/*` and `http://localhost:5173/*`). After deploy, return to **https://account.mapbox.com/access-tokens/** → click the public token → add to "URL restrictions":
   ```
   https://*.vercel.app/*       ← while testing on Vercel preview URLs
   https://www.trakkr.app/*     ← live custom domain (replace with yours)
   https://trakkr.app/*         ← apex
   ```
   Save. The map and geocoding will continue to work because Mapbox URL restrictions enforce against the browser `Referer` header — backend server-side calls bypass them. Note: Mapbox does **not** accept raw IP addresses (e.g. `127.0.0.1`) in this list; use hostnames only.
- [ ] **Compile Tailwind** instead of loading the CDN. Drops ~3 MB per page load. Use Tailwind CLI's `--minify` to produce per-page CSS at build time.
- [ ] **Enable Vercel Web Analytics** (free, no cookies) for traffic insights.
- [ ] **Set up Render's HTTP health-check alerts** so you get an email if `/health` flips to non-200.
- [ ] **Submit the production sitemap** to Google Search Console.

---

*Maintainer: Dennis Comandante. Last reviewed: 2026-04-30.*
