---
title: MoveCheck — AI Movement Assessment
emoji: 🏋️
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Coach-grade AI movement assessment from phone video
---

# MoveCheck — AI Movement Assessment API

Computer-vision movement assessment. Upload phone video of a mobility screen or
a barbell lift; get back a scored biomechanics report — per-metric breakdowns,
left/right asymmetry, coaching notes, and annotated frames with angle overlays.

**This Space runs the full stack in one container:**

- **Python / Flask** — MediaPipe pose estimation + OpenCV biomechanics analysis
  (15 exercise analyzers). Bound to loopback; never exposed publicly.
- **Node / Express** — job queue, session persistence, upload proxy. This is the
  public API on port 7860.
- **React SPA** — the full UI, served statically from the same origin.

So this Space URL is a complete, working application on its own, *and* it serves
as the API backend for the Vercel-hosted frontend.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | Service + processor status (used for warm-up) |
| `POST` | `/api/sessions` | Create an anonymous session |
| `POST` | `/api/assessments/:type/:slug/analyse` | Upload videos → returns `jobId` |
| `GET`  | `/api/jobs/:jobId` | Poll job status / fetch result |

## Notes

- **Cold starts:** free Spaces sleep after inactivity. The first request after a
  sleep takes ~30–60 s to wake the container.
- **Processing time:** pose estimation is CPU-bound. A 15 s 4K clip takes roughly
  1–3 minutes on this hardware; a 5 s 720p clip is much faster.
- **Storage is ephemeral.** Session JSON is written to `/tmp` and is wiped on
  restart. The browser keeps its own `localStorage` cache and re-syncs.

See the source repository for architecture documentation.
