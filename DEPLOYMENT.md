# Deployment Guide — MoveCheck

Written for someone who has never deployed anything. Every command is
copy-pasteable. This version picks up **exactly where you are now** and takes
you to a fully live site.

---

## Where you are right now

| Step | Status |
|---|---|
| Code committed and pushed to GitHub | ✅ **Done** |
| Hugging Face Space created, code pushed, image built | ✅ **Done** — but ⛔ **paused: free CPU quota exhausted** |
| Frontend deployed to Vercel | ⬜ **Next — do this first** |
| Live-analysis backend on Google Cloud Run | ⬜ After Vercel |
| Frontend ↔ backend connected | ⬜ Last |

**What happened with Hugging Face:** the push, LFS upload, and Docker build all
succeeded. Then HF paused the Space with *"You've reached your CPU Basic quota
limit"*, and the restart returns `403`. You have no other Spaces to pause, so
there is nothing to free up — the free compute allowance for the account is
simply used up. That's a billing-policy wall, not a bug in your project.

We're leaving that Space in place (it costs nothing and may come back when the
quota replenishes) and moving live analysis to **Google Cloud Run**, which has
real CPU, a genuinely usable free tier, and runs your existing `Dockerfile`
unchanged.

---

## Table of contents

1. [Part 1 — Deploy the frontend to Vercel (do this now)](#part-1--deploy-the-frontend-to-vercel-do-this-now)
2. [Part 2 — Deploy the backend to Google Cloud Run](#part-2--deploy-the-backend-to-google-cloud-run)
3. [Part 3 — Connect frontend and backend](#part-3--connect-frontend-and-backend)
4. [Part 4 — Verify everything](#part-4--verify-everything)
5. [Part 5 — Cost control (read this)](#part-5--cost-control-read-this)
6. [Troubleshooting](#troubleshooting)
7. [Updating the site later](#updating-the-site-later)
8. [How to demo this to clients](#how-to-demo-this-to-clients)
9. [Quick reference](#quick-reference)

---

# Part 1 — Deploy the frontend to Vercel (do this now)

**Do this before touching Google Cloud.** It takes ~5 minutes and gives you a
live, client-ready link *today* — because your site does not need the backend
to be impressive.

### Why it works without a backend

Demo mode reads the 12 pre-generated reports as static files from the same
origin. The code paths that talk to the API all fail soft: session bootstrap is
wrapped in `try/catch` and falls through, and the warm-up ping swallows its
error. With the backend completely dead, a visitor still gets the landing page,
all 12 real reports with annotated frames, coaching notes, the dashboard, and
the exercise guide. Only *uploading a new video* is unavailable.

### Steps

1. Go to **https://vercel.com/new**
2. Sign in with GitHub if you haven't
3. Find your **`movecheck`** repo → click **Import**
4. ⚠️ **The setting everyone misses** — expand **Root Directory** and set it to:

   ```
   frontend
   ```

   Your React app lives in the `frontend/` subfolder. Without this, Vercel looks
   for `package.json` at the repo root, doesn't find it, and the build fails.

5. **Framework Preset** should auto-detect as **Vite**. Leave the build settings
   alone — `frontend/vercel.json` already configures them.

6. Expand **Environment Variables** and add this one (you'll set the real value
   in Part 3 — a placeholder now is fine):

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://placeholder.invalid/api` |

7. Click **Deploy**. Takes ~2 minutes.

You'll get a URL like `https://movecheck-abc123.vercel.app`.

### Make the URL clean (optional, 30 seconds)

**Settings → Domains → Edit** → change it to `movecheck.vercel.app` if free.
A tidy URL matters on a portfolio.

### Verify

Open your Vercel URL:

- ✅ Landing page loads instantly
- ✅ Click **"See a real report — no upload, no wait"** → full Knee-to-Wall
  report: score **86 / GOOD**, metrics, bilateral comparison, coaching notes,
  and **6 annotated frames** with skeleton overlays and angle arcs
- ✅ Browse the exercise guide — all 12 samples open

**You now have a live portfolio link.** Everything below adds live upload.

---

# Part 2 — Deploy the backend to Google Cloud Run

**Time:** ~25 minutes, most of it waiting for the first build.

### What you're getting

| | Free tier allowance (per month) |
|---|---|
| CPU | 180,000 vCPU-seconds |
| Memory | 360,000 GiB-seconds |
| Requests | 2 million |

With the settings below (2 vCPU / 4 GiB), that's roughly **25 hours of active
instance time per month, free**. A portfolio demo won't come close. It also
scales to zero, so an idle site costs nothing.

> **Credit card required.** Google requires a card on file to enable billing,
> even to use the free tier. It will not auto-charge you when the free tier is
> exceeded unless you explicitly upgrade — but Part 5 has budget alerts, and
> you should set them.

---

### 2.1 — Create your Google Cloud account

1. Go to **https://console.cloud.google.com**
2. Sign in with a Google account
3. Accept the terms → you'll be offered **$300 in free credit for 90 days**.
   Accept it; it's a safety cushion on top of the always-free tier.
4. Add a credit/debit card when prompted

---

### 2.2 — Install the gcloud CLI

```bash
brew install --cask google-cloud-sdk
```

Then restart your terminal, or run:

```bash
source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
```

Verify:

```bash
gcloud --version
```

---

### 2.3 — Log in and create a project

```bash
gcloud auth login
```

A browser window opens — approve it.

Now create a project. The ID must be **globally unique**, so append a number:

```bash
gcloud projects create movecheck-app-4471 --name="MoveCheck"
gcloud config set project movecheck-app-4471
```

If that ID is taken, change the digits and rerun both lines.

---

### 2.4 — Link billing to the project

This must be done in the browser:

1. Go to **https://console.cloud.google.com/billing**
2. Select **MoveCheck** from the project dropdown at the top
3. Click **Link a billing account** → choose your account → **Set account**

Confirm it worked:

```bash
gcloud billing projects describe movecheck-app-4471
```

You want `billingEnabled: true`. If it's false, the next step fails.

---

### 2.5 — Enable the required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

Takes ~1 minute. These are Cloud Run itself, the build service that compiles
your Dockerfile, and the registry that stores the built image.

---

### 2.6 — Deploy

Run this from your project folder. It builds your `Dockerfile` in the cloud and
deploys the result.

```bash
cd "/Users/meet/Documents/Moblity 2"

gcloud run deploy movecheck \
  --source . \
  --region asia-south1 \
  --port 7860 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 900 \
  --concurrency 4 \
  --min-instances 0 \
  --max-instances 2 \
  --no-cpu-throttling \
  --allow-unauthenticated \
  --set-env-vars "^@^CORS_ORIGIN=*@MAX_UPLOAD_MB=200@SESSION_DIR=/tmp/sessions@UPLOAD_DIR=/tmp/uploads@HOT_RELOAD=0"
```

When prompted **"Allow unauthenticated invocations?"** → **`y`** (your API must
be publicly reachable from the browser).

**Region:** `asia-south1` is Mumbai. Pick whichever is nearest you —
`europe-west1`, `us-central1`, `asia-southeast1` are all fine. Use the same
region consistently.

#### What each flag does — and why it matters

| Flag | Why |
|---|---|
| `--source .` | Builds your `Dockerfile` in the cloud. No local Docker needed. |
| `--port 7860` | Matches the Dockerfile. Cloud Run injects `PORT`; your `start.sh` reads it. |
| `--memory 4Gi` | MediaPipe's heavy model plus video decoding. **Also:** Cloud Run's `/tmp` is *in-memory*, so uploads consume RAM too. |
| `--cpu 2` | Pose estimation is CPU-bound. This is the single biggest speed lever. |
| `--timeout 900` | 15 minutes. A long 4K clip can legitimately take minutes. |
| `--concurrency 4` | Default is 80. For CPU-heavy work that would thrash. |
| `--min-instances 0` | Scale to zero → **$0 when nobody is using it**. |
| `--max-instances 2` | **Cost ceiling.** Caps runaway spend if the URL gets traffic. |
| `--no-cpu-throttling` | ⚠️ **Essential — see below.** |
| `--allow-unauthenticated` | Public API, callable from the browser. |
| `--set-env-vars "^@^..."` | The `^@^` prefix makes `@` the separator, so the `*` and `/` in the values don't get mangled. |

> ### ⚠️ Why `--no-cpu-throttling` is not optional
>
> By default, Cloud Run only gives a container CPU **while it is handling a
> request**. Your architecture returns a `jobId` immediately and then does the
> analysis in the background while the browser polls for status.
>
> With default throttling, that background work would be frozen the instant the
> response is sent, and analysis would never finish. `--no-cpu-throttling` keeps
> CPU allocated for the instance's lifetime.
>
> The trade-off: you're billed for instance lifetime rather than request time.
> With `--min-instances 0` the instance still shuts down after ~15 minutes idle,
> so a demo stays comfortably inside the free tier.

The first deploy takes **10–20 minutes** (installing MediaPipe, OpenCV, SciPy,
downloading the 30 MB pose model, building React). Later deploys reuse cached
layers and take 2–4 minutes.

When it finishes you'll see:

```
Service URL: https://movecheck-xxxxxxxxxx-el.a.run.app
```

**Copy that URL — you need it in Part 3.**

---

### 2.7 — Test the backend

```bash
curl https://YOUR-SERVICE-URL/api/health
```

Expect JSON with `"status":"ok"`, `"reachable":true`, and all 15 exercises
listed. If you get that, your CV pipeline is live.

---

# Part 3 — Connect frontend and backend

Two values to line up.

### 3.1 — Point the frontend at Cloud Run

1. Vercel dashboard → your project → **Settings → Environment Variables**
2. Edit `VITE_API_BASE_URL` (replacing the placeholder):

   ```
   https://YOUR-SERVICE-URL/api
   ```

   ⚠️ Include the trailing **`/api`**. No trailing slash after it.

3. **Redeploy** — this is required. Go to **Deployments → ⋯ (top entry) →
   Redeploy**.

   > Vite bakes env vars in at **build** time. Changing the variable without
   > redeploying does nothing.

### 3.2 — Lock CORS to your domain

You deployed with `CORS_ORIGIN=*` so nothing was blocked while testing. Now
restrict it:

```bash
gcloud run services update movecheck \
  --region asia-south1 \
  --update-env-vars "CORS_ORIGIN=https://movecheck.vercel.app"
```

Use your real Vercel domain. Comma-separate multiple domains.

> Any `*.vercel.app` URL is already permitted by a built-in pattern in
> `backend/server.js`, so preview deployments keep working. Setting this
> explicitly matters once you add a custom domain.

---

# Part 4 — Verify everything

Open your Vercel URL and walk through these in order:

**1. Landing page loads instantly.** ✅

**2. "See a real report"** → full Knee-to-Wall report, 86/GOOD, 6 annotated
frames. (This never touches the backend.) ✅

**3. Backend health:**

```bash
curl https://YOUR-SERVICE-URL/api/health
```

`"status":"ok"` ✅

**4. Browser can reach the API.** Open your Vercel site, press **F12** →
**Console**, paste:

```js
fetch('https://YOUR-SERVICE-URL/api/health').then(r => r.json()).then(console.log)
```

If you get JSON back, CORS is correct. A red *"blocked by CORS policy"* means
`CORS_ORIGIN` doesn't match your domain.

**5. A real upload.** Start with a **short, small** clip — the 720p deadlift
samples in `Sample Videos for Strength Assessment/` are ideal. Expect 1–3
minutes. The first request after idle adds ~30s of cold start.

All five pass → **you are fully live.**

---

# Part 5 — Cost control (read this)

You have a card on file. Take five minutes to make surprise charges impossible.

### Set a budget alert

1. **https://console.cloud.google.com/billing** → **Budgets & alerts**
2. **Create budget**
3. Scope it to the **MoveCheck** project
4. Amount: **$5**
5. Alert thresholds: **50%, 90%, 100%**
6. ✅ Tick **Email alerts to billing admins**

You'll be emailed long before anything meaningful is spent.

### Guardrails already in place

- `--max-instances 2` caps how much can ever run at once
- `--min-instances 0` means an idle service costs **$0**
- `--concurrency 4` prevents one instance thrashing under load
- `.gcloudignore` keeps your 2.5 GB of sample video out of every build upload

### If you want to stop all spend immediately

```bash
gcloud run services delete movecheck --region asia-south1
```

Your Vercel site keeps working in demo mode. Redeploy whenever you like.

### Realistic expectation

A portfolio demo — a few dozen visitors, a handful of uploads — should sit at
**$0/month**, inside the always-free tier. The $300 credit is a further cushion.
Costs only become real with sustained heavy traffic.

---

# Troubleshooting

### Errors you already hit (and their fixes, for reference)

| Error | Cause | Fix |
|---|---|---|
| `Password authentication is no longer supported` | Used account password | Use an access token |
| Auth fails even with a correct token | macOS keychain cached the old bad credential | `security delete-internet-password -s huggingface.co` |
| `push was rejected because it contains binary files` | HF requires LFS for binaries | `git lfs install` + `git lfs migrate import --include="*.jpg,*.png"` |
| `"short_description" must be ≤ 60 characters` | Frontmatter too long | Shortened (fixed in `deploy/hf-space/README.md`) |
| `403 — cpu-basic quota limit` | HF free compute exhausted | Moved to Cloud Run |

### Cloud Run: build fails

```bash
gcloud builds list --limit 3
gcloud builds log $(gcloud builds list --limit 1 --format='value(id)')
```

Read the first red line.

- **`denied: Permission ... artifactregistry`** — APIs not enabled. Rerun 2.5.
- **`billing account not found`** — billing isn't linked. Rerun 2.4.
- **pip resolution errors** — transient; just rerun the deploy command.

### Cloud Run: deploys OK but `/api/health` times out

The container isn't listening on the right port. Check the logs:

```bash
gcloud run services logs read movecheck --region asia-south1 --limit 50
```

You should see `🚀 MobilityAI Backend listening on 0.0.0.0:7860`. If the port
differs, redeploy with `--port` matching it.

### Analysis starts but never finishes (stuck at "processing")

Almost certainly `--no-cpu-throttling` is missing. Confirm:

```bash
gcloud run services describe movecheck --region asia-south1 \
  --format="value(spec.template.metadata.annotations)"
```

Look for `run.googleapis.com/cpu-throttling: 'false'`. If absent:

```bash
gcloud run services update movecheck --region asia-south1 --no-cpu-throttling
```

### Analysis fails on large videos / instance restarts mid-job

Cloud Run's `/tmp` is in-memory, so a 150 MB upload eats 150 MB of your 4 GiB.
Either raise memory:

```bash
gcloud run services update movecheck --region asia-south1 --memory 8Gi
```

or lower the accepted upload size:

```bash
gcloud run services update movecheck --region asia-south1 \
  --update-env-vars "MAX_UPLOAD_MB=100"
```

### Browser shows "blocked by CORS policy"

`CORS_ORIGIN` doesn't exactly match your Vercel domain — check `https://`, no
trailing slash:

```bash
gcloud run services update movecheck --region asia-south1 \
  --update-env-vars "CORS_ORIGIN=https://your-exact-domain.vercel.app"
```

### Vercel build fails: "Could not read package.json"

Root Directory isn't `frontend`. **Settings → General → Root Directory** → set
it → redeploy.

### Frontend still calls the old URL

Vite bakes env vars at build time. Update the variable **and redeploy**.

### Uploaded results disappear after a while

Expected. Session JSON lives in `/tmp`, wiped when the instance scales to zero.
The browser keeps a `localStorage` copy so users still see their own results.
Persisting server-side would need Cloud Storage or a database.

---

# Updating the site later

```bash
cd "/Users/meet/Documents/Moblity 2"
git add -A
git commit -m "Describe your change"
git push                       # → Vercel redeploys automatically (~2 min)
```

**Frontend-only change?** That's all you need.

**Changed `backend/`, `processor/`, or `Dockerfile`?** Also redeploy Cloud Run:

```bash
gcloud run deploy movecheck --source . --region asia-south1
```

Settings from the first deploy are remembered — no need to repeat every flag.

### Regenerating demo reports

After changing an analyzer:

```bash
./processor/venv/bin/python scripts/generate_demo_reports.py
# or one exercise:
./processor/venv/bin/python scripts/generate_demo_reports.py knee-to-wall-test
```

Writes to `frontend/public/demo/`. Commit and push.

### Testing the container locally first

If you install Docker Desktop:

```bash
docker compose up --build     # → http://localhost:7860
```

Catches build errors in minutes instead of after a 20-minute cloud build.

---

# How to demo this to clients

Optimise for the 30 seconds of attention you get.

**Lead with the demo link, never the upload flow:**

```
https://movecheck.vercel.app
→ "See a real report — no upload, no wait"
```

**Point at these, in order:**

1. **The annotated frames.** Skeleton overlays, angle arcs, distance
   measurements, pass/fail colouring burned onto real video. Most impressive
   artifact, needs zero explanation.
2. **The scores aren't all perfect** — 62, 70, 71, 74, 81, 81, 86, 93, 93, 100,
   100, 100. Say this out loud. It proves the system *measures* rather than
   flatters. Anyone can build something that says "great job".
3. **The coaching notes** — especially knee-to-wall's arch-collapse check, which
   catches an athlete *cheating* the test by pronating instead of genuinely
   dorsiflexing. That's domain insight, not just code.
4. **The breadth** — 15 exercises, some with 4 simultaneous camera angles and
   30+ biomechanical metrics each.

**Have `ARCHITECTURE.md` open** for technical clients. It explains the
three-filter signal-processing rationale, DTW rep-outlier detection, and the
geometric-mean scoring that stops a good technique score from masking a bad
safety score — depth most freelancers can't show.

**Be upfront about limits.** *"The demo is instant. A live analysis takes a
couple of minutes because pose estimation is CPU-bound and this runs on a free
tier — on dedicated hardware it's much faster."* That reads as engineering
judgement, not excuse-making.

**Links for your profile:**
- Live app → your Vercel URL
- Source → your GitHub repo
- Technical deep-dive → `ARCHITECTURE.md`

---

# Quick reference

| Thing | Where |
|---|---|
| Live site | `https://movecheck.vercel.app` |
| API health | `https://YOUR-SERVICE-URL/api/health` |
| Cloud Run console | https://console.cloud.google.com/run |
| Cloud Run logs | `gcloud run services logs read movecheck --region asia-south1` |
| Budget alerts | https://console.cloud.google.com/billing → Budgets & alerts |
| Vercel env vars | Vercel → Settings → Environment Variables |
| Redeploy backend | `gcloud run deploy movecheck --source . --region asia-south1` |
| Redeploy frontend | `git push` (automatic) |
| Local dev | `./start.sh` → http://localhost:5173 |
| Local prod test | `docker compose up --build` → http://localhost:7860 |
| Stop all cloud spend | `gcloud run services delete movecheck --region asia-south1` |

### Environment variables

**Vercel (frontend)** — build-time; redeploy after changing:

| Name | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://YOUR-SERVICE-URL/api` |

**Cloud Run (backend)** — runtime; applied on update:

| Name | Value |
|---|---|
| `CORS_ORIGIN` | `https://movecheck.vercel.app` |
| `MAX_UPLOAD_MB` | `200` |
| `SESSION_DIR` | `/tmp/sessions` |
| `UPLOAD_DIR` | `/tmp/uploads` |
| `HOT_RELOAD` | `0` |
