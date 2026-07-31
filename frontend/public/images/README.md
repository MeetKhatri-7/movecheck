# Image shopping list

Drop the files below into this folder. Filenames are exact — the UI will pick them up automatically and the editorial placeholders will vanish.

## 1. Landing hero — **highest impact**

`/public/images/hero-athlete.jpg` · **4:5 portrait** · ≥ 1200 × 1500 px

A single editorial photograph of an athlete mid-movement, side profile. Calm composition, room around the body. Lighting and tone should feel warm (window light, cream walls) — it must sit naturally next to the bone background `#F4EFE6`. Avoid neon, branded sportswear, or busy gym scenes.

Good prompts for stock / Midjourney / Unsplash:
- "Editorial photograph, female athlete mid-squat, side profile, natural light, beige studio background, fine grain"
- "Male lifter setting up for a deadlift, hip-height side view, warm window light"
- Unsplash search: `mobility`, `squat side profile`, `deadlift setup`, `studio fitness`

Optional **B&W or duotone** treatments work beautifully against the warm palette.

---

## 2. Exercise thumbnails — **biggest visual lift, used in 15 cards**

`/public/images/exercises/<slug>.jpg` · **16:9 landscape** · ≥ 800 × 450 px

One image per exercise. Same lighting + tone notes as the hero. Either:
- A photograph of someone doing the exercise (preferred), **or**
- A simple line illustration on a cream paper background

Filenames (exact slugs the codebase uses):

### Mobility (10)
- `knee-to-wall-test.jpg` — ankle dorsiflexion, foot flat against wall
- `seated-hip-rotation-test.jpg` — seated cross-leg hip rotation
- `thoracic-extension.jpg` — quadruped reach-up
- `quadruped-rotation.jpg` — bird-dog twist
- `shoulder-rotation-90-90.jpg` — 90/90 internal/external rotation
- `single-leg-glute-bridge.jpg` — single-leg bridge
- `dead-bug.jpg` — supine dead bug
- `hollow-body-hold.jpg` — hollow hold
- `plank-shoulder-tap.jpg` — plank with alternating taps
- `prone-y-t-w-raise.jpg` — prone YTW

### Strength (5)
- `back-squat.jpg` — back squat (side view)
- `deadlift.jpg` — conventional deadlift setup
- `bench-press.jpg` — flat bench press, side
- `pull-up.jpg` — pull-up bar, front view
- `overhead-press.jpg` — standing strict press

---

## 3. Camera setup diagrams (optional, very helpful)

`/public/images/setup/<slug>.png` · **transparent PNG** · ≥ 600 × 400 px

A clean top-down or 3/4-view line diagram showing where the phone should sit relative to the athlete. Think IKEA-instruction simplicity. Not in any slot yet — let me know if you want this wired in and I'll add a `CameraDiagram` slot to the Instruction page.

---

## What we're avoiding

- ❌ Stock-photo-istry: smiling models with white teeth, headphones in
- ❌ Logos, watermarks, harsh studio lighting
- ❌ Pastel-tinted Lightroom filters that fight the bone palette
- ❌ Neon / cyan / electric blue tones (clashes with terracotta)

## What works

- ✅ Natural light, window light, golden-hour
- ✅ Plain backdrops (beige, cream, off-white, oak floors)
- ✅ Fitted black/grey/cream clothing
- ✅ A little grain or film texture
- ✅ Cropped, abstract close-ups (a foot pressing the wall, a hand on the bar)
- ✅ B&W or warm duotone (`#2A2520` ↔ `#F4EFE6`)

## Image specs cheat-sheet

| Slot              | Aspect | Min size       | Format    |
|-------------------|:------:|:---------------|:----------|
| Hero              | 4:5    | 1200 × 1500    | JPG ≤ 400 KB |
| Exercise thumb    | 16:9   | 800 × 450      | JPG ≤ 150 KB |
| Camera diagram    | 3:2    | 600 × 400      | PNG (transparent) |

## Sources

- **Unsplash** (`unsplash.com`) — free, high quality, search the prompts above
- **Pexels** (`pexels.com`) — alternative free library
- **Midjourney / DALL·E** — great for the line illustrations
- **A friend with a phone** — best result, honestly. 30 minutes in a sunlit room with a friend doing each move gives you all 15 exercise thumbnails plus a usable hero.

Drop the files in and refresh — every placeholder swaps to a photo automatically.
