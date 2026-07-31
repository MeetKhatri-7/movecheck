# MobilityAI — Screen Documentation

## App brief

MobilityAI is a phone-only movement assessment web app that scores how well a user moves and how much force they produce. It runs two parallel assessment tracks:

- **Mobility** — 10 joint-by-joint range-of-motion tests (knee-to-wall, seated hip rotation, thoracic extension, quadruped rotation, shoulder rotation 90/90, single-leg glute bridge, dead bug, hollow-body hold, plank shoulder tap, prone Y/T/W raise).
- **Strength** — 5 compound lifts (back squat, deadlift, bench press, pull-up, overhead press).

The user films short clips of each exercise on a propped phone, uploads them through the browser, and the system returns a coach-grade report: a 0–100 score, status band (GOOD / NEEDS IMPROVEMENT / RESTRICTED), per-rep faults with timing, bilateral left-vs-right comparison, annotated skeleton frames, and plain-language coaching notes.

Under the hood the React frontend talks to a Node/Express backend (port 3001), which queues jobs and forwards videos to a Python/Flask processor (port 5001) running MediaPipe Pose + OpenCV. Sessions are dual-persisted: server-side JSON in `backend/sessions/` plus a localStorage cache, so reports survive page refreshes and can be re-opened later.

There are 7 screens in total. The flow is:

```
Landing → Exercise Guide → Instruction → Processing → Result
                                                        ↓
                                                    Dashboard
                                                        ↓
                                                    Sessions
```

---

## 1. Landing Page

**Route:** `/`
**File:** [frontend/src/pages/LandingPage.tsx](frontend/src/pages/LandingPage.tsx)

### What happens
The entry point. Introduces the app with a hero section, four feature highlights (phone-only setup, coach-grade AI, honest reports, progress tracking), and a "seven rules for clean footage" checklist that the user is expected to read before filming. The seven rules animate in one by one. Keyboard shortcuts are wired: Enter starts Mobility, **M** picks Mobility, **S** picks Strength.

### Buttons
- **My session** (top right, ghost) — jumps to the Sessions page if any session already exists.
- **Begin mobility** (hero, primary) — navigates to the Mobility exercise guide.
- **Begin strength** (hero, secondary) — navigates to the Strength exercise guide.
- **Begin mobility** (bottom of rules section, primary) — duplicate CTA after the user has read the rules.
- **Begin strength** (bottom of rules section, secondary) — duplicate CTA after the user has read the rules.

---

## 2. Exercise Guide

**Route:** `/assessments/:type` (where `type` is `mobility` or `strength`)
**File:** [frontend/src/pages/ExerciseGuide.tsx](frontend/src/pages/ExerciseGuide.tsx)

### What happens
Shows the full battery of exercises for the chosen track as a grid of cards. Each card has an image header, the exercise name, subtitle, description, and pills for category / difficulty / number of videos / duration. Completed exercises show a green checkmark badge in the top-right of the card. An "Overall progress" bar appears at the top once at least one exercise is completed. Stats in the header read out: total Exercises, total Videos, total Completed. If the user has already analysed at least one exercise, a "Dashboard" CTA appears in the nav and again at the bottom.

### Buttons
- **Back / Home** (nav left) — returns to Landing.
- **Session** (nav right, ghost) — opens the Sessions page.
- **Dashboard** (nav right, primary; only if any report exists) — opens the Dashboard for this track.
- **Exercise card** (one per exercise) — clicking the card opens that exercise's Instruction page.
- **Open dashboard** (bottom CTA, primary; only if any report exists) — opens the Dashboard.

---

## 3. Instruction Page

**Route:** `/assessments/:type/:slug`
**File:** [frontend/src/pages/InstructionPage.tsx](frontend/src/pages/InstructionPage.tsx)

### What happens
The "prepare to film" screen for a single exercise. Shows the exercise's title, category, difficulty, duration, and description, plus a step counter (e.g. "Step 3 / 10") and a horizontal progress bar. Sections from top to bottom:

1. **Reference library** — a horizontal scroll of reference cards (VIDEO / CAMERA / GUIDE / IMAGE types). Clicking a card opens a modal with the full reference content; GUIDE references render as a numbered step-by-step list.
2. **Submission checklist** — inline bullet list of things the user must verify before uploading.
3. **Lift details** (strength only) — a form for variant, weight max, reps max, target reps, plate size, etc. Fields vary per lift (back-squat has a side-vs-front reps split; pull-up has grip + athlete height; bench has incline angle).
4. **Calibration** (knee-to-wall test only) — a tibia-length input in cm used for pixel-to-cm conversion.
5. **Upload your videos** — one drop-zone per required clip (drag-drop or click to pick from disk). Filled count shows "X/Y uploaded" and the row of dots fills with each upload.
6. **Camera setup card** — the exact angle/distance the analyzer expects.

A sticky footer at the bottom holds the analyse CTA, which stays disabled until every required video is uploaded. Keyboard: Enter triggers Analyse when ready, Escape goes back.

### Buttons
- **Back / All exercises** (nav left) — returns to the Exercise Guide.
- **Reference card** (multiple) — opens a modal with the full reference detail.
- **Modal close (X)** — dismisses the reference modal.
- **Upload zone** (one per required video) — click to open the file picker; drag-and-drop also works.
- **Analyse** (sticky footer, primary; disabled until all videos uploaded) — kicks off the upload + analysis job and navigates to the Processing page.

---

## 4. Processing Page

**Route:** `/assessments/:type/:slug/processing`
**File:** [frontend/src/pages/ProcessingPage.tsx](frontend/src/pages/ProcessingPage.tsx)

### What happens
Pure progress screen — no user input. On mount it builds the upload payload (videos + tibia length + strength inputs like variant, weight, plate size), POSTs to the backend, receives a `jobId`, then polls `GET /api/jobs/:jobId` every second. Visually it cycles through six labelled stages with icons (Extracting frames → Detecting body landmarks → Tracking joint angles → Range-of-motion analysis → Bilateral comparison → Generating report), accompanied by a linear progress bar that creeps up to ~95% and snaps to 100% on completion. Below the progress card a skeleton placeholder previews the shape of the report so the user knows what to expect.

When the job returns `complete` it auto-navigates to the Result page with the result data; on `error` it builds an error result and navigates anyway so the user sees the failure inline.

### Buttons
- None. This screen is fully automated; the only "exit" is the back navigation that the browser provides.

---

## 5. Result Page

**Route:** `/assessments/:type/:slug/result`
**File:** [frontend/src/pages/ResultPage.tsx](frontend/src/pages/ResultPage.tsx)

### What happens
The detailed per-exercise report. Layout from top to bottom:

1. **Header** — exercise name, category, and a "strong work / solid foundation / work to do" status band.
2. **Banners** — a camera-view warning (if any), an "Analysis failed" banner with a retry CTA (if the run errored), or a "Sample preview" banner if the user is looking at placeholder data.
3. **Hero card** — a circular score badge (0–100), status pill, and two mini stats (passed metrics, pass rate %). Right side has a verdict line synthesised from the metrics (e.g. "depth · bar path · one fix: lumbar") plus stat pills.
4. **Evidence row** — a gallery of every annotated skeleton frame from the analysis (clicking any frame opens a full-screen lightbox), paired with a Muscle Body diagram when activation data is present.
5. **Top actions** — up to 3 coaching cards prioritised as Critical / Important / Maintain.
6. **Technical** — three grouped metric cards (Safety / Form / Performance), each with metric rows showing name, target, value, and a coloured status dot. Below them: a histogram of metrics expressed as "% of target" with a 100% threshold line, and a Left-vs-right bilateral comparison card with bars per side and an asymmetry delta pill.
7. **Per-rep raw data** — a collapsible accordion of every detected rep's underlying numbers.
8. **Bottom nav row** — redo, all exercises, dashboard, next/full-report.

Keyboard: Enter advances (next exercise, or Dashboard if last), Left arrow redoes, Right arrow advances, Escape goes back to the Guide.

### Buttons
- **Back / All exercises** (nav left) — returns to the Exercise Guide.
- **Session** (nav right, ghost; if available) — opens Sessions page.
- **Try again** (rust button inside error banner; only on error) — re-runs the exercise.
- **Upload & analyse** (primary inside sample banner; only when viewing placeholder) — jumps back to Instruction.
- **Frame tile** (one per annotated frame) — opens a full-screen lightbox of that frame.
- **Lightbox close (X)** — dismisses the lightbox.
- **Collapsible header — Per-rep raw data** — expands/collapses the per-rep accordion.
- **Redo this exercise** (bottom left, ghost) — returns to the Instruction page for this same exercise.
- **All exercises** (bottom, secondary) — returns to the Exercise Guide.
- **Dashboard** (bottom, secondary; if available) — opens the Dashboard.
- **Next exercise** (bottom right, primary; if there's a next exercise) — navigates to the next exercise's Instruction page.
- **Full report** (bottom right, primary; if last exercise) — opens the Dashboard.

---

## 6. Dashboard

**Route:** `/assessments/:type/dashboard`
**File:** [frontend/src/pages/Dashboard.tsx](frontend/src/pages/Dashboard.tsx)

### What happens
The aggregated report across all completed exercises in one track. Top sections:

1. **Overall card** — a large circular gauge with the average score, grade letter (A/B/C/D), status label (EXCELLENT / GOOD / NEEDS WORK / RESTRICTED), and four stat tiles: Analysed, Passed, To improve, Strengths. A short paragraph summarises the state of the user's profile based on the overall score.
2. **To work on** — up to 3 exercises with scores under 70 (lowest first). Each is a clickable row that opens that exercise's report.
3. **Your strengths** — up to 3 exercises with scores ≥ 80 (highest first). Same row-button format.
4. **All [type] reports** — one card per analysed exercise, showing exercise number + name, the score and grade letter, a status pill, valid-reps and confidence summary, the best annotated frame per side (clickable, opens a modal), the top 3 coaching notes, and an "Open full report" button.
5. **Not yet analysed** — if any exercises are missing, a dashed-border card lists their names and offers a CTA to continue.

If no reports exist, an EmptyState invites the user to start their first exercise. Keyboard: Escape goes back home, Enter opens the Guide.

### Buttons
- **Back / All exercises** (nav left) — returns to the Exercise Guide.
- **Session** (nav right, ghost; if available) — opens the Sessions page.
- **Start first exercise** (empty-state CTA; only when no reports) — opens the Exercise Guide.
- **To work on — exercise row** (one per listed exercise) — opens that exercise's Result page.
- **Your strengths — exercise row** (one per listed exercise) — opens that exercise's Result page.
- **Frame thumbnail** (one per best frame on each card) — opens the frame modal.
- **Frame modal close (✕)** — dismisses the modal.
- **Open full report** (one per exercise card, secondary) — opens that exercise's Result page.
- **Continue assessment** (inside "Not yet analysed" card, primary) — returns to the Exercise Guide.
- **Home** (bottom left, ghost) — returns to Landing.
- **Session details** (bottom, secondary; if available) — opens the Sessions page.
- **All exercises** (bottom right, primary) — returns to the Exercise Guide.

---

## 7. Sessions Page

**Route:** `/session` (and `/sessions`)
**File:** [frontend/src/pages/SessionsPage.tsx](frontend/src/pages/SessionsPage.tsx)

### What happens
A persistence-focused view of everything tied to the current session ID. On mount it fetches `backend/sessions/<sessionId>.json` from the server and falls back to the local in-memory reports if the server call fails. Top section shows session metadata: session ID (truncated), created timestamp, last-updated timestamp, total report count. Below that, reports are grouped into two collapsed lists — Mobility and Strength — with one detailed report block per saved analysis.

Each report block contains: exercise number + name + status pill, score and grade letter, summary line, stats strip, every metric grouped into a 2-column grid with value-vs-target, bilateral L/R comparison chips, a horizontal strip of all annotated skeleton frames (clickable → frame modal), all coaching notes, and a collapsible `<details>` with the raw per-rep JSON.

Footer paths show where data lives on disk and in localStorage. Keyboard: Escape goes home, Enter continues assessing.

### Buttons
- **Back** (nav left) — returns to the previous screen (browser history).
- **Export session JSON** (primary) — downloads the full session as `session-<id>.json`.
- **Refresh from server** (secondary) — reloads the page to re-fetch from the backend.
- **Clear & start new** (ghost, rust text) — confirms then resets the local session ID and reloads (server JSON is kept).
- **Start an assessment / Start an exercise** (empty-state CTA; only when no reports) — opens the Mobility Exercise Guide.
- **Frame thumbnail** (one per saved frame, on every report block) — opens the frame modal.
- **Frame modal close (X)** — dismisses the modal.
- **Per-rep raw data — `<summary>` toggle** (one per report) — expands/collapses the raw JSON dump.
- **Open full report** (one per report block, secondary) — navigates to that exercise's Result page.
- **Home** (bottom left, ghost) — returns to Landing.
- **Continue assessing** (bottom right, primary) — returns to the Mobility Exercise Guide.
