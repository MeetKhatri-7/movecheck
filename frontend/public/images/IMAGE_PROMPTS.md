# Image prompts — full frontend shopping list

Generation prompts for every image slot across the site (Midjourney / DALL·E / SDXL / Firefly — any of them work with these). Matches the **current** live design system in `frontend/src/theme/tokens.ts`:

- Background: near-black `#0A0D10` (page) / `#12171D` (raised sections) / `#171D24` (placeholder panels)
- Accent: vermilion clay `#FF5A36` (brand colour — used as rim light, not literal paint)
- Secondary accents: cyan `#33C7FF`, violet `#A855F7`, sage green `#22D47A` (status = good), amber (warn), rust (bad) — reserve these for UI/data-viz, not photography
- Display type: Bebas Neue (bold condensed uppercase) — the visual tone is **editorial sports-science**, not gym-bro stock photography

> Note: `frontend/public/images/README.md` describes an older bone/cream palette that no longer matches the app — ignore it. `ImageSlot.tsx` exists but isn't wired into any page yet; these images are for when that gets connected.

---

## Master style block

Append this to the end of every prompt below (or keep it as a Midjourney `--style` reference image once you've generated one you like, for consistency across the set):

```
Editorial sports-science photography. Single athletic subject, fitted matte black or
charcoal training wear (no logos, no text, no brand marks). Minimal dark studio,
near-black backdrop. One hard directional key light plus a subtle warm vermilion
(#FF5A36) rim/kicker light tracing the muscle line. High contrast, low-key lighting,
fine film grain, shallow depth of field, 35mm lens look. Serious, focused, clinical-but-
human mood — no smiling, no gym clichés, no neon signage, no equipment branding.
Shot like a premium athletic-brand campaign, not stock photography.
```

**Negative prompt (SDXL/DALL·E-style tools):** `text, watermark, logo, brand name, gym signage, neon colors, smiling, stock photo look, cluttered background, multiple people, cartoon, 3d render`

---

## 1. Landing page

### 1a. Hero visual — replaces the placeholder "M" panel
`/images/landing/hero.jpg` · **4:5 portrait** · ≥1600×2000px

Currently a plain gradient card with a giant serif "M". This is the single highest-impact image on the site — first thing every visitor sees.

> Athlete captured mid-rep at the bottom of a back squat, strict side profile, three-quarter body in frame. Body position is technically perfect — neutral spine, knee tracking over toe. Near-black studio backdrop, single key light from camera-left, warm vermilion rim light along the spine and hamstring. Frozen, powerful moment — like a biomechanics ad campaign, not a gym photo. Fine grain, shallow depth of field, negative space in the upper third for a floating UI stat card.

### 1b. Marquee / texture background (optional)
`/images/landing/texture.jpg` · seamless tile · 1200×1200px

> Abstract close-up macro photograph of dark charcoal fabric weave under raking light, subtle vermilion color cast in the shadows. Almost black, very low contrast, barely-there texture — meant to sit behind UI, not compete with it. No recognizable subject.

### 1c. Social share / OG image
`/images/og-share.jpg` · **1.91:1 landscape** · 1200×630px

> Same athlete-mid-squat subject as the hero, cropped wide, positioned camera-left with large empty negative space on the right for a headline overlay. Near-black background, vermilion rim light, high contrast editorial sports photography.

---

## 2. Exercise Guide page (mobility / strength listing)

Each exercise card currently has a flat numbered gradient header (`00`–`10` in Bebas Neue) instead of a photo. Three category-level background images would let every card in a category share a subtle photographic backdrop behind the number.

`/images/category/lower-body.jpg`, `/images/category/upper-body.jpg`, `/images/category/core.jpg` · **16:9** · 1200×675px, will sit behind a dark scrim + the number, so keep it moody/dark

**Lower Body:**
> Extreme close-up of bare feet and ankles mid-movement — one heel pressing flat into a wooden floor, the other leg driving through a lunge. Near-black background, single raking light from the side, vermilion rim light on the ankle. Abstract, cropped tight, no face in frame.

**Upper Body:**
> Extreme close-up of a hand gripping a pull-up bar or foam roller under the upper back, shoulder blade visibly engaged. Dark studio, dramatic side lighting, vermilion kicker light along the deltoid. Abstract crop, no face.

**Core:**
> Extreme close-up of a torso in a plank position, obliques and rectus abdominis under tension, raking light emphasizing the muscle lines. Near-black backdrop, vermilion rim light along the waistline. Abstract crop, no face.

---

## 3. Instruction page — per-exercise reference image

Every exercise's "Reference library" already has an `IMAGE` slot (`Exercise Image` / `Reference` card) sitting next to the VIDEO/CAMERA/GUIDE cards — currently just an icon. These are demonstration photos of correct body position, one per exercise.

`/images/exercises/<slug>.jpg` · **16:9 landscape** · ≥1600×900px

### Mobility (10)

**`knee-to-wall-test.jpg`** — Ankle Dorsiflexion
> Side-profile photo of an athlete in a half-kneeling lunge, front knee driven forward touching a wall, heel flat on the floor, back knee down. Strict side view at hip height. Near-black studio, vermilion rim light along the shin.

**`seated-hip-rotation-test.jpg`** — Hip Internal/External Rotation
> Front-view photo of an athlete seated on the edge of a bench, knees bent at 90°, lower leg rotated outward, upper body upright and still. Shot from the front at knee height. Dark studio, vermilion kicker light on the shin.

**`thoracic-extension.jpg`** — Thoracic Spine Mobility
> Side-profile photo of an athlete lying back over a foam roller placed under the mid-back, arms crossed on chest, hips pinned to the floor, upper back arched into extension. Shot from the side at shoulder height. Low-key lighting, vermilion rim light along the ribcage.

**`quadruped-rotation.jpg`** — Thoracic Rotation ("Thread the Needle")
> Side-profile photo of an athlete on all fours, one arm threaded under the torso with the shoulder near the floor, head following the reaching hand. Shot from the side at hip height. Dark studio, vermilion rim light along the rotating shoulder.

**`shoulder-rotation-90-90.jpg`** — Shoulder Internal/External Rotation
> Photo shot from the foot of a bench looking down the length of the body, athlete supine, arm raised to 90° with elbow bent 90°, forearm rotated vertically. Axial framing. Near-black backdrop, vermilion rim light along the forearm.

**`single-leg-glute-bridge.jpg`** — Glute Strength & Hip Stability
> Side-profile photo of an athlete supine with one foot planted, hips driven up into full extension, opposite leg extended straight in the air. Shot from the side at hip height. Dark studio, vermilion rim light tracing the glute-to-hamstring line.

**`dead-bug.jpg`** — Core Stability & Motor Control
> Side-profile photo of an athlete supine, one arm extended overhead and the opposite leg extended straight, lower back pinned flat to the floor. Shot from the side at hip height. Low-key lighting, vermilion rim light along the extended limbs.

**`hollow-body-hold.jpg`** — Anterior Core Strength
> Side-profile photo of an athlete supine in a hollow-body position — shoulder blades and legs both lifted off the floor, arms extended overhead, lower back flush to the ground. Shot from the side at knee height. Dark studio, vermilion rim light along the torso curve.

**`plank-shoulder-tap.jpg`** — Core Stability & Anti-Rotation
> Front-side photo of an athlete in a high plank, one hand lifted mid-reach to tap the opposite shoulder, hips held level and square. Shot from a front-side angle at hip height. Near-black backdrop, vermilion rim light along the raised arm.

**`prone-y-t-w-raise.jpg`** — Scapular Control & Upper Back
> Overhead-angled photo of an athlete lying prone on a bench, arms raised into a "Y" shape (thumbs up, ~135° from body), shoulder blades visibly retracted. Shot from slightly above and behind. Dark studio, vermilion rim light across the upper back.

### Strength (5)

**`back-squat.jpg`** — Compound Knee + Hip Extension
> Strict side-profile photo of an athlete at the bottom of a barbell back squat, hip crease below the knee, neutral spine, barbell loaded with visible plates. Shot from the side at hip height, 90° to the lifter. Dark studio, vermilion rim light along the quad and spine.

**`deadlift.jpg`** — Hip-Dominant Pull Pattern
> Strict side-profile photo of an athlete at the setup position of a conventional deadlift — bar over mid-foot, shins near vertical, flat back, hips loaded. Shot from the strong side at hip height. Near-black backdrop, vermilion rim light along the hamstring and lat.

**`bench-press.jpg`** — Horizontal Push
> Side-profile photo of an athlete on a flat bench, bar lowered to the chest, elbows tucked, shoulder blades retracted into the bench. Shot perpendicular to the bench at bench-surface height. Dark studio, vermilion rim light along the forearm and chest.

**`pull-up.jpg`** — Vertical Pull Pattern
> Side-profile photo of an athlete mid-pull-up, chin just clearing an overhead bar, elbows driven down and back, body in a straight line. Shot from 90° to the bar at mid-bar height. Near-black backdrop, vermilion rim light along the lat and forearm.

**`overhead-press.jpg`** — Vertical Push
> Side-profile photo of an athlete standing, barbell locked out fully overhead, ribs down, glutes braced, head through the "window" of the arms. Shot from 90° to the lifter at sternum height. Dark studio, vermilion rim light along the triceps and delt.

---

## 4. Processing page

`/images/processing/ambient-bg.jpg` · **16:9** · 1920×1080px, will sit at very low opacity behind the pose-tracking animation

> Extreme macro close-up of a dark charcoal training surface with faint diagonal light streaks, near-black with barely visible warm vermilion glow in one corner. Almost abstract — very low detail, meant to be seen only as a subtle backdrop tint behind an animated skeleton overlay, not as a focal image.

---

## 5. Dashboard page

`/images/dashboard/banner.jpg` · **21:9 wide** · 2100×900px (optional — used only if a hero band is added above the score gauge)

> Wide, cropped photo of an athlete's torso and shoulders from behind, mid-breath after a lift, faint sheen of sweat catching a single side light. Near-black studio, vermilion rim light along the spine and shoulder blades. Lots of negative space on the left for a headline/score overlay.

---

## 6. Sessions page

`/images/sessions/banner.jpg` · **21:9 wide** · 2100×900px (optional — used only if a hero band is added above the session list)

> Wide, cropped photo of a stack of folded training mats and a phone on a small tripod, dark wood floor, single warm side light, vermilion accent glow on the tripod leg. Quiet, still-life composition — implies "the archive of past sessions," not action.

---

## What to avoid everywhere

- ❌ Neon / electric blue or cyan cast across the whole image (cyan is a *UI* accent only — reserve it for status pills, not photography)
- ❌ Smiling stock-photo energy, headphones, branded activewear, gym signage, visible logos
- ❌ Bright, high-key, white-background photography — everything here is low-key/dark
- ❌ Busy backgrounds — every shot should read as a single subject against near-black

## What works

- ✅ Near-black studio backdrops with one hard key light + a vermilion rim/kicker light
- ✅ Strict, technically-correct body positions matching each exercise's camera-setup spec
- ✅ Fine grain, shallow depth of field, 35mm editorial-campaign look
- ✅ Cropped/abstract close-ups for anything decorative (category headers, textures)
- ✅ Full-body strict-angle shots for anything instructional (the 15 exercise references)
