# Deployment Guide — Getting MoveCheck Online for Free

Written for someone who has never deployed anything. Follow it top to bottom;
every command is copy-pasteable. Budget **45–60 minutes** for the first run.

**End result:** a public URL like `https://movecheck.vercel.app` that anyone can
open, explore, and try — costing you nothing, with no credit card.

---

## Table of contents

1. [What you're building](#1-what-youre-building)
2. [Why this architecture](#2-why-this-architecture)
3. [Accounts you need](#3-accounts-you-need)
4. [Step 1 — Push the code to GitHub](#step-1--push-the-code-to-github)
5. [Step 2 — Deploy the CV backend to Hugging Face](#step-2--deploy-the-cv-backend-to-hugging-face)
6. [Step 3 — Deploy the frontend to Vercel](#step-3--deploy-the-frontend-to-vercel)
7. [Step 4 — Connect the two](#step-4--connect-the-two)
8. [Step 5 — Verify everything works](#step-5--verify-everything-works)
9. [Troubleshooting](#9-troubleshooting)
10. [Updating the site later](#10-updating-the-site-later)
11. [Limits, costs, and honest caveats](#11-limits-costs-and-honest-caveats)
12. [How to demo this to clients](#12-how-to-demo-this-to-clients)

---

## 1. What you're building

Your app has three parts. They get deployed to two different free hosts:

```
        ┌──────────────────────────────────────────────┐
        │  VERCEL  (free, always on, global CDN)        │
        │  ─────────────────────────────────────────    │
        │  • The React app (what people see)            │
        │  • The 12 pre-computed demo reports           │
        │                                               │
        │  https://movecheck.vercel.app                 │
        └───────────────────┬──────────────────────────┘
                            │
              only when someone actually
              uploads a video for analysis
                            │
                            ▼
        ┌──────────────────────────────────────────────┐
        │  HUGGING FACE SPACE  (free, 2 vCPU / 16 GB)   │
        │  ─────────────────────────────────────────    │
        │  • Node API (job queue, sessions)             │
        │  • Python + MediaPipe + OpenCV (the CV work)  │
        │                                               │
        │  https://<you>-movecheck.hf.space             │
        └──────────────────────────────────────────────┘
```

**The single most important design decision:** the landing page and all demo
reports live on Vercel, which is *always instantly available*. The heavy CV
container is only touched when someone uploads a real video. So a prospective
client clicking your link **never waits**, even if the CV container is asleep.

---

## 2. Why this architecture

You asked for free hosting. Here's the honest reasoning, because it explains
several things you'll see later:

**Your app is unusually heavy for a free tier.** Pose estimation is CPU-bound.
Measured on your M4 Mac with GPU acceleration, it runs at ~21 frames/sec. On a
free shared cloud CPU it's roughly 3–7 fps. Your 4K mobility clips are 430
frames each, and knee-to-wall needs two of them — so **one real analysis is
3–5 minutes of pure compute**.

That rules out the "obvious" choices:

| Platform | Free tier | Verdict |
|---|---|---|
| Render | 512 MB RAM, **0.1 CPU** | ❌ MediaPipe's heavy model will OOM; 0.1 CPU means 30+ min per video |
| Railway | $5 trial credit, then paid | ❌ Not actually free ongoing |
| Fly.io | Limited free allowance | ⚠️ Tight on RAM for MediaPipe |
| **Hugging Face Spaces** | **2 vCPU, 16 GB RAM, free forever, no card** | ✅ **Purpose-built for exactly this** |
| Google Cloud Run | 2 vCPU / 2 GB, generous | ⚠️ Requires a credit card |

Hugging Face Spaces is the outlier: it's designed for ML demos, gives you real
CPU and a huge amount of RAM, needs no credit card, and being on HF is a
*positive signal* for a CV project — it's where ML practitioners publish work.

**Why not put everything on Hugging Face then?** Free Spaces sleep after
inactivity and take 30–60s to wake. If that's your landing page, a client
clicking your portfolio link stares at a loading screen. Vercel serves the
marketing surface instantly and never sleeps.

---

## 3. Accounts you need

All free, no credit card:

1. **GitHub** — https://github.com/signup (stores your code)
2. **Hugging Face** — https://huggingface.co/join (runs the CV backend)
3. **Vercel** — https://vercel.com/signup → **"Continue with GitHub"** (hosts the frontend)

Also make sure `git` works. You already have it (v2.50.1):

```bash
git --version
```

---

## Step 1 — Push the code to GitHub

Your repo is already initialized and committed locally. I verified what gets
committed: **189 files, 47 MB** — no videos, no `node_modules`, no virtualenv.

> **Why 47 MB and not 3.4 GB?** Your sample videos are 2.5 GB and the Python
> virtualenv is 487 MB. Both are excluded by `.gitignore`. GitHub would reject
> the repo otherwise. The demo reports (12 MB) *are* committed on purpose —
> that's what makes the instant demo work.

### 1a. Create an empty repo on GitHub

Go to https://github.com/new and:

- **Repository name:** `movecheck`
- **Visibility:** **Public** (required for free Vercel + it's your portfolio)
- **Do NOT** check "Add a README", "Add .gitignore", or "Choose a license" —
  the repo must be empty or the next step conflicts.

Click **Create repository**.

### 1b. Push

Copy your repo URL from the page (looks like
`https://github.com/YOURNAME/movecheck.git`), then run — replacing `YOURNAME`:

```bash
cd "/Users/meet/Documents/Moblity 2"

git remote add origin https://github.com/YOURNAME/movecheck.git
git branch -M main
git push -u origin main
```

If prompted for a password, GitHub no longer accepts your account password.
Either:
- Install the GitHub CLI and authenticate: `brew install gh && gh auth login`, or
- Create a Personal Access Token at https://github.com/settings/tokens
  (classic, scope `repo`) and paste it as the password.

**Verify:** refresh your GitHub repo page — you should see your files.

---

## Step 2 — Deploy the CV backend to Hugging Face

### 2a. Create the Space

Go to https://huggingface.co/new-space and set:

| Field | Value |
|---|---|
| **Space name** | `movecheck` |
| **License** | `mit` |
| **Space SDK** | **Docker** → **Blank** |
| **Space hardware** | `CPU basic · 2 vCPU · 16 GB` (the free default) |
| **Visibility** | **Public** |

Click **Create Space**.

### 2b. Push your code to the Space

A Space *is* a git repo. Clone it somewhere separate from your project:

```bash
cd ~
git clone https://huggingface.co/spaces/YOURNAME/movecheck hf-movecheck
cd hf-movecheck
```

If it asks for a password, use a Hugging Face **access token** (create one at
https://huggingface.co/settings/tokens with **Write** permission) as the password.

Now copy your project in. This uses `git archive` so it copies exactly the
files git tracks — no videos, no `node_modules`:

```bash
# From your project, export tracked files into the Space clone
cd "/Users/meet/Documents/Moblity 2"
git archive main | tar -x -C ~/hf-movecheck

# The Space needs its own README (it carries the Docker config in its
# frontmatter — sdk, app_port). Overwrite the project README with it.
cp ~/hf-movecheck/deploy/hf-space/README.md ~/hf-movecheck/README.md

cd ~/hf-movecheck
git add -A
git commit -m "Deploy MoveCheck"
git push
```

> **Why swap the README?** Hugging Face reads Docker settings (`sdk: docker`,
> `app_port: 7860`) from YAML frontmatter at the top of `README.md`. Your
> project README doesn't have that. `deploy/hf-space/README.md` does.

### 2c. Watch it build

Open `https://huggingface.co/spaces/YOURNAME/movecheck` and click the
**Logs** tab.

**The first build takes 10–20 minutes.** It's installing MediaPipe, OpenCV,
SciPy and friends (~1 GB of wheels), plus building your React app. This is
normal and only slow the first time — later pushes reuse cached layers.

You'll know it worked when the Space badge turns **Running** and the logs show:

```
✓ CV processor ready after Ns
🚀 MobilityAI Backend listening on 0.0.0.0:7860
```

### 2d. Note your API URL

Your Space's direct app URL is **not** the `huggingface.co/spaces/...` page.
It's the `.hf.space` subdomain:

```
https://YOURNAME-movecheck.hf.space
```

(lowercase, `/` replaced with `-`). Test it:

```bash
curl https://YOURNAME-movecheck.hf.space/api/health
```

You should get JSON with `"status":"ok"` and a list of all 15 exercises. **Save
this URL — you need it in Step 4.**

---

## Step 3 — Deploy the frontend to Vercel

1. Go to https://vercel.com/new
2. Click **Import** next to your `movecheck` GitHub repo
3. **Critical setting** — expand **Root Directory** and set it to **`frontend`**

   Your React app lives in the `frontend/` subfolder. If you skip this, Vercel
   looks for `package.json` at the repo root, doesn't find it, and the build fails.

4. Framework Preset should auto-detect as **Vite**. Leave build settings alone —
   `frontend/vercel.json` already configures them.
5. Expand **Environment Variables** and add:

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://YOURNAME-movecheck.hf.space/api` |

   ⚠️ Include the trailing **`/api`**. Use *your* Space URL from Step 2d.

6. Click **Deploy**.

The build takes ~2 minutes. You'll get a URL like
`https://movecheck-abc123.vercel.app`.

> **Forgot the env var?** Add it under **Settings → Environment Variables**, then
> go to **Deployments → ⋯ → Redeploy**. Vite bakes env vars in at *build* time,
> so adding one without redeploying changes nothing.

---

## Step 4 — Connect the two

The browser now loads your app from Vercel but calls the API on Hugging Face —
a different origin. Browsers block that unless the API explicitly allows it
(CORS). Your backend reads an allowlist from an environment variable.

1. Go to `https://huggingface.co/spaces/YOURNAME/movecheck/settings`
2. Scroll to **Variables and secrets** → **New variable** (a *variable*, not a secret)
3. Add:

   | Name | Value |
   |---|---|
   | `CORS_ORIGIN` | `https://movecheck.vercel.app` |

   Use your real Vercel domain. For multiple domains, comma-separate them.

4. The Space restarts automatically (~1 min).

> Any `*.vercel.app` URL is already allowed by a built-in pattern, so preview
> deployments work without extra config. Setting `CORS_ORIGIN` explicitly is
> still worth doing so a custom domain keeps working later.

---

## Step 5 — Verify everything works

Open your Vercel URL and check, in order:

**1. The landing page loads instantly.** No spinner, no wait. ✅

**2. Click "See a real report — no upload, no wait".**
You should land on a full Knee-to-Wall report: score **86 / GOOD**, metrics
table, bilateral comparison, coaching notes, and **6 annotated frames** with
skeleton overlays and angle arcs. This is real analyzer output, served from the
CDN — the backend isn't even involved. ✅

**3. Browse the other samples.** From the report, go to the exercise guide —
all 12 sample exercises are viewable, each loading its report on demand. ✅

**4. Check the API is alive:**

```bash
curl https://YOURNAME-movecheck.hf.space/api/health
```

Expect `"status":"ok"` and `"reachable":true`. ✅

**5. (Optional) Try a real upload.** Pick a *short, small* clip — the 720p
deadlift samples work well. Expect 1–3 minutes, longer if the Space was asleep.

If all five pass, **you're live.**

---

## 9. Troubleshooting

### Vercel build fails: "Could not read package.json"
Root Directory isn't set to `frontend`. Fix in **Settings → General → Root
Directory**, then redeploy.

### The site loads but analysis fails with a network/CORS error
Open the browser console (F12). If you see *"blocked by CORS policy"*:
- `CORS_ORIGIN` on the Space doesn't match your Vercel domain exactly
  (check `https://`, no trailing slash)
- Confirm it's set as a **variable**, not a **secret**

If you see *404* or *Failed to fetch*: `VITE_API_BASE_URL` is wrong or missing
the `/api` suffix. Fix it in Vercel and **redeploy** (env vars are build-time).

### Hugging Face build fails
Open the **Logs** tab and read the first red error.

- *"failed to solve: failed to compute cache key"* — a file the Dockerfile
  expects is missing. Confirm `git archive` copied everything: `ls ~/hf-movecheck`
  should show `Dockerfile`, `backend/`, `processor/`, `frontend/`, `deploy/`.
- *pip resolution errors* — usually a stale cache. Push an empty commit to
  rebuild: `git commit --allow-empty -m "rebuild" && git push`

### "Space is sleeping" / first request takes ~60s
Expected on the free tier after ~48h idle. Your demo mode is unaffected. The app
also fires a warm-up ping on load, so the container starts waking as soon as
someone opens the site.

### Analysis times out or the container restarts mid-job
The clip is too big. Free-tier CPU realistically handles ~15s of 1080p. Advise
users to keep clips short, or lower `MAX_UPLOAD_MB` on the Space to reject
oversized files early.

### Uploaded results vanish after a while
Expected. Session JSON is written to `/tmp`, which is wiped when the container
restarts. The browser keeps a `localStorage` copy so users still see their own
results. Persistent storage on HF is a paid add-on.

---

## 10. Updating the site later

You now have two remotes. Vercel auto-deploys from GitHub; Hugging Face needs
an explicit push.

```bash
cd "/Users/meet/Documents/Moblity 2"

# 1. Commit your change
git add -A
git commit -m "Describe your change"

# 2. Push to GitHub → Vercel redeploys the frontend automatically (~2 min)
git push

# 3. Push to Hugging Face → rebuilds the backend (only if you changed
#    backend/, processor/, or the Dockerfile)
git archive main | tar -x -C ~/hf-movecheck
cp ~/hf-movecheck/deploy/hf-space/README.md ~/hf-movecheck/README.md
cd ~/hf-movecheck && git add -A && git commit -m "Update" && git push
```

**Frontend-only change?** Step 2 is enough.

### Regenerating demo reports

If you change an analyzer and want the samples to reflect it:

```bash
cd "/Users/meet/Documents/Moblity 2"
./processor/venv/bin/python scripts/generate_demo_reports.py

# or just one exercise
./processor/venv/bin/python scripts/generate_demo_reports.py knee-to-wall-test
```

Output goes to `frontend/public/demo/`. Commit and push.

### Testing the container locally before pushing

If you install Docker Desktop (https://docker.com/products/docker-desktop —
you don't currently have it), you can run the exact production image:

```bash
docker compose up --build       # → http://localhost:7860
```

Optional, but it catches build errors in 5 minutes instead of a 20-minute
Hugging Face build.

---

## 11. Limits, costs, and honest caveats

**Cost: $0/month.** No credit card anywhere. Nothing can bill you by surprise.

Know these before you show it to a client:

| Reality | Impact | Mitigation in place |
|---|---|---|
| Free Space sleeps after ~48h idle | First analysis waits 30–60s | Demo mode needs no backend; app pings warm-up on load |
| Pose estimation is CPU-bound | 1–3 min per real analysis | Demo mode is instant |
| `/tmp` storage is ephemeral | Uploaded results lost on restart | Browser `localStorage` keeps the user's own copy |
| API is public and unauthenticated | Anyone could upload | Demo is the default path; low-traffic risk. Add auth if it ever matters |
| Vercel free = non-commercial | Fine for a portfolio | Upgrade if it becomes a paid product |

**Security note:** the Python CV service binds to `127.0.0.1` inside the
container — it's never reachable from the internet. Only the Node API is
exposed. Uploads are written with generated names (never user-supplied
filenames), and session IDs are regex-validated before touching the filesystem.

---

## 12. How to demo this to clients

You're using this to win freelance work, so optimise for the 30 seconds of
attention you get.

**Lead with the demo link, not the upload flow.** Send them straight to a
report — one click, zero wait, and it immediately shows depth:

```
https://movecheck.vercel.app
→ "See a real report — no upload, no wait"
```

**What to point at, in order:**

1. **The annotated frames.** Skeleton overlays, angle arcs, distance
   measurements, pass/fail colouring burned onto real video frames. This is the
   most immediately impressive artifact and needs no explanation.
2. **The scores aren't all perfect** — 62, 70, 71, 74, 81, 86, 93, 100. Point
   this out explicitly. It proves the system measures rather than flatters.
   Anyone can build something that says "great job".
3. **The coaching notes.** Especially knee-to-wall's arch-collapse check, which
   catches an athlete *cheating* the test by pronating instead of truly
   dorsiflexing. That's domain insight, not just code.
4. **The breadth.** 15 exercises, 10 mobility + 5 strength, some with 4
   simultaneous camera angles and 30+ biomechanical metrics each.

**Have `ARCHITECTURE.md` ready.** When a technical client asks "how does it
work", that document answers at a depth most freelancers can't produce — the
three-filter signal-processing rationale, DTW rep-outlier detection, the
geometric-mean scoring that stops a good technique score from masking a bad
safety score.

**Be upfront about the free-tier limits.** Saying *"the demo is instant; a live
analysis takes a couple of minutes because pose estimation is CPU-bound, and
this is running on free hardware — on a paid instance it's much faster"* reads
as engineering judgement, not as an excuse. Clients trust people who know their
system's limits.

**Add these links to your portfolio/Upwork profile:**
- Live app → your Vercel URL
- Source → your GitHub repo
- Technical deep-dive → `ARCHITECTURE.md` in the repo

---

## Quick reference

| Thing | Where |
|---|---|
| Live site | `https://movecheck.vercel.app` |
| API health | `https://YOURNAME-movecheck.hf.space/api/health` |
| Space logs | `https://huggingface.co/spaces/YOURNAME/movecheck` → Logs |
| Vercel logs | Vercel dashboard → your project → Deployments |
| Frontend env var | Vercel → Settings → Environment Variables |
| Backend env var | HF Space → Settings → Variables and secrets |
| Local dev | `./start.sh` → http://localhost:5173 |
| Local prod test | `docker compose up --build` → http://localhost:7860 |
