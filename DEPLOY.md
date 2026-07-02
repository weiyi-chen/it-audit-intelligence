# Deployment Guide

## Option 1 — ngrok (quick share, < 5 min)

Share your local server with anyone via a public URL without any cloud setup.

```bash
# 1. Start the backend
uvicorn api.main:app --reload --port 8000

# 2. In a second terminal, expose it
ngrok http 8000

# 3. Copy the https://xxxx.ngrok-free.app URL
#    Share that URL — the frontend is served at /frontend/pbc.html
#    e.g. https://xxxx.ngrok-free.app/frontend/pbc.html
```

ngrok URLs are temporary (reset on restart). Use Railway for a permanent link.

---

## Option 2 — Railway (permanent, free tier available)

Railway gives a permanent HTTPS URL and auto-deploys on git push.

### One-time setup

1. **Push to GitHub**
   ```bash
   cd it-audit-intelligence
   git init
   git add .
   git commit -m "initial commit"
   # Create a repo at github.com, then:
   git remote add origin https://github.com/YOUR_USER/it-audit-intelligence.git
   git push -u origin main
   ```

2. **Create a Railway project**
   - Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
   - Select `it-audit-intelligence`

3. **Set environment variables** in Railway dashboard → Variables:
   ```
   ANTHROPIC_API_KEY = sk-ant-...
   RESEND_API_KEY    = re_...       (optional, for email)
   SENDER_FROM       = audit@yourdomain.com  (optional)
   ```

4. **Railway auto-detects** `railway.toml` and `Procfile`. It will:
   - Install `requirements.txt`
   - Run `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
   - Assign a URL like `https://it-audit-intelligence-production.up.railway.app`

5. **Access the app**
   ```
   https://your-app.up.railway.app/              → index.html
   https://your-app.up.railway.app/pbc.html      → Module A
   https://your-app.up.railway.app/frontend/pbc.html  → also works
   ```

   The frontend auto-discovers the API base URL via `/config.js` — no manual changes needed.

### Subsequent deploys

```bash
git add .
git commit -m "update"
git push
# Railway redeploys automatically
```

---

## Architecture in production

```
Browser
  │
  ├── GET  /                  → FastAPI serves frontend/index.html
  ├── GET  /pbc.html          → FastAPI serves frontend/pbc.html
  ├── GET  /config.js         → FastAPI returns: window.API_BASE = "https://..."
  │
  ├── POST /api/pbc/generate  → runs pipeline, saves to SQLite, returns xlsx b64
  ├── GET  /api/pbc/history   → lists past runs from SQLite
  ├── GET  /api/pbc/runs/{id} → re-downloads a past xlsx
  └── POST /api/send-email    → dispatches via Resend
```

Everything — API + frontend + SQLite history — lives in one Railway service.
The SQLite file (`audit_history.db`) lives on the Railway volume (persists across deploys).

---

## Adding a persistent volume (Railway)

By default, Railway's filesystem resets on redeploy. To keep `audit_history.db`:

1. Railway dashboard → your service → Settings → Volumes → Add Volume
2. Mount path: `/data`
3. Set env var: `AUDIT_DB=/data/audit_history.db`

The `api/database.py` reads `AUDIT_DB` env var and defaults to the project root otherwise.

---

## Local dev commands (reminder)

```bash
# Backend
uvicorn api.main:app --reload --port 8000

# Frontend (open directly — no server needed for local dev)
open frontend/pbc.html

# Or serve everything through FastAPI (mirrors production)
uvicorn api.main:app --reload --port 8000
# then open http://localhost:8000/pbc.html

# Tests
pytest tests/ -v
```
