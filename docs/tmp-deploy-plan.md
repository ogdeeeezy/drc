# Deploy agentic-drc to VPS

## Context
User wants to share the DRC tool with others for feedback. Has a VPS (ExtraVM, Ubuntu 24.04, 8GB RAM, Docker installed) at `104.156.154.153` with Caddy already running on 80/443. DuckDNS domain `sky130drc.duckdns.org` already resolves to the VPS IP. Caddy already serves another app (`gantamade.duckdns.org`).

## What needs to happen

### 1. Fix frontend static serving in backend
**File:** `backend/main.py`
- Add `StaticFiles` mount to serve `frontend/dist` at `/` for production
- Use `pathlib.Path` to check if dist exists (dev mode won't have it)
- Add catch-all HTML response for SPA routing

### 2. Fix CORS for production domain
**File:** `backend/main.py`
- Add `https://sky130drc.duckdns.org` to `allow_origins`
- Keep localhost entries for dev

### 3. Add .dockerignore
**File:** `.dockerignore` (new)
- Exclude `.venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `tests/`, `data/`, `.git`

### 4. Add "Give Feedback" button linking to GitHub Issues
**File:** `frontend/src/App.tsx`
- Add a small fixed-position link/button in the corner: "Give Feedback" → `https://github.com/ogdeeeezy/drc/issues/new`

### 5. Deploy to VPS
**On VPS via SSH:**
- Clone the repo to `/opt/drc`
- Run `docker compose up -d --build`
- Add Caddy reverse proxy entry for `sky130drc.duckdns.org → localhost:8000`
- Reload Caddy (auto-provisions Let's Encrypt SSL)

### Files to modify
| File | Change |
|------|--------|
| `backend/main.py` | Static file serving + CORS |
| `.dockerignore` | New file |
| `frontend/src/App.tsx` | Feedback button |

### Verification
1. `docker compose up --build` locally — confirm frontend loads at `localhost:8000`
2. SSH to VPS, clone, build, verify `curl localhost:8000/health`
3. Add Caddy entry, reload — verify `https://sky130drc.duckdns.org` loads
4. Test full flow: upload GDS → DRC → fix → LVS through the browser
5. Click "Give Feedback" → opens GitHub issue form
