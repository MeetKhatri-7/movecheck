/**
 * SVG path data for the interactive muscle anatomy diagram.
 *
 * Each muscle group is a separate path element with:
 *   - id: matches the backend slug (e.g. 'quadriceps', 'glutes')
 *   - view: 'front' | 'back' — which view the path belongs to
 *   - paths: SVG path "d" strings for the muscle shape
 *
 * The anatomy is drawn on a 200×420 viewBox (stylized fitness-app aesthetic).
 * Coordinates are manually crafted for a clean, modern look.
 */

export interface MusclePath {
  id: string;
  name: string;
  view: 'front' | 'back';
  paths: string[];
}

// ── FRONT VIEW (Anterior) ──────────────────────────────────────────────

export const FRONT_MUSCLES: MusclePath[] = [
  // ── HEAD / NECK ──
  {
    id: 'head',
    name: 'Head',
    view: 'front',
    paths: [
      'M 90,18 Q 100,2 110,18 Q 116,30 112,42 Q 100,50 88,42 Q 84,30 90,18 Z',
    ],
  },
  {
    id: 'neck',
    name: 'Neck',
    view: 'front',
    paths: [
      'M 94,42 L 106,42 L 108,58 L 92,58 Z',
    ],
  },

  // ── TRAPS (front view — upper trapezius visible portion) ──
  {
    id: 'traps',
    name: 'Trapezius',
    view: 'front',
    paths: [
      'M 92,58 L 75,68 L 72,62 L 92,52 Z',
      'M 108,58 L 125,68 L 128,62 L 108,52 Z',
    ],
  },

  // ── ANTERIOR DELTOIDS ──
  {
    id: 'anterior_deltoid',
    name: 'Anterior Deltoid',
    view: 'front',
    paths: [
      // Left shoulder
      'M 68,68 Q 60,72 58,82 Q 60,92 64,96 L 72,90 L 75,78 L 72,68 Z',
      // Right shoulder
      'M 132,68 Q 140,72 142,82 Q 140,92 136,96 L 128,90 L 125,78 L 128,68 Z',
    ],
  },

  // ── PECTORALS ──
  {
    id: 'pectorals',
    name: 'Pectoralis Major',
    view: 'front',
    paths: [
      // Left pec
      'M 75,68 L 100,72 L 100,100 Q 88,102 76,96 Q 68,90 68,82 L 72,68 Z',
      // Right pec
      'M 125,68 L 100,72 L 100,100 Q 112,102 124,96 Q 132,90 132,82 L 128,68 Z',
    ],
  },

  // ── BICEPS ──
  {
    id: 'biceps',
    name: 'Biceps Brachii',
    view: 'front',
    paths: [
      // Left bicep
      'M 60,96 Q 56,108 54,124 Q 56,134 62,136 Q 66,128 66,116 L 64,96 Z',
      // Right bicep
      'M 140,96 Q 144,108 146,124 Q 144,134 138,136 Q 134,128 134,116 L 136,96 Z',
    ],
  },

  // ── FOREARMS ──
  {
    id: 'forearms',
    name: 'Forearms',
    view: 'front',
    paths: [
      // Left forearm
      'M 54,136 Q 50,154 48,172 Q 46,182 48,186 L 54,184 Q 58,170 60,156 L 62,136 Z',
      // Right forearm
      'M 146,136 Q 150,154 152,172 Q 154,182 152,186 L 146,184 Q 142,170 140,156 L 138,136 Z',
    ],
  },

  // ── CORE / ABDOMINALS ──
  {
    id: 'core',
    name: 'Core / Abdominals',
    view: 'front',
    paths: [
      // Rectus abdominis — 3 rows of 2
      'M 90,102 L 100,100 L 110,102 L 112,118 L 100,120 L 88,118 Z',
      'M 88,120 L 100,122 L 112,120 L 114,138 L 100,140 L 86,138 Z',
      'M 86,140 L 100,142 L 114,140 L 116,158 L 100,160 L 84,158 Z',
    ],
  },

  // ── HIP FLEXORS (Iliopsoas — visible inner thigh/groin region) ──
  {
    id: 'hip_flexors',
    name: 'Hip Flexors',
    view: 'front',
    paths: [
      'M 84,160 L 94,162 L 96,178 L 88,180 Q 82,174 82,168 Z',
      'M 116,160 L 106,162 L 104,178 L 112,180 Q 118,174 118,168 Z',
    ],
  },

  // ── ADDUCTORS (inner thigh) ──
  {
    id: 'adductors',
    name: 'Adductors',
    view: 'front',
    paths: [
      // Left adductor
      'M 90,180 L 96,178 L 98,210 L 96,230 L 92,228 L 88,210 Z',
      // Right adductor
      'M 110,180 L 104,178 L 102,210 L 104,230 L 108,228 L 112,210 Z',
    ],
  },

  // ── QUADRICEPS ──
  {
    id: 'quadriceps',
    name: 'Quadriceps',
    view: 'front',
    paths: [
      // Left quad
      'M 78,170 Q 72,180 70,200 Q 68,220 70,240 Q 72,260 78,270 L 88,268 Q 92,250 92,230 L 90,200 L 88,180 Z',
      // Right quad
      'M 122,170 Q 128,180 130,200 Q 132,220 130,240 Q 128,260 122,270 L 112,268 Q 108,250 108,230 L 110,200 L 112,180 Z',
    ],
  },

  // ── CALVES (anterior tibialis portion visible from front) ──
  {
    id: 'calves',
    name: 'Calves',
    view: 'front',
    paths: [
      // Left shin/calf (front view shows tibialis anterior)
      'M 74,280 Q 72,300 72,320 Q 72,340 74,358 L 84,356 Q 86,340 86,320 Q 86,300 84,280 Z',
      // Right
      'M 126,280 Q 128,300 128,320 Q 128,340 126,358 L 116,356 Q 114,340 114,320 Q 114,300 116,280 Z',
    ],
  },

  // ── LATERAL DELTOIDS (front view — side of shoulder) ──
  {
    id: 'lateral_deltoid',
    name: 'Lateral Deltoid',
    view: 'front',
    paths: [
      'M 58,78 Q 54,84 54,92 L 58,96 L 62,88 L 60,78 Z',
      'M 142,78 Q 146,84 146,92 L 142,96 L 138,88 L 140,78 Z',
    ],
  },

  // ── TRICEPS (visible from front — outer arm) ──
  {
    id: 'triceps',
    name: 'Triceps Brachii',
    view: 'front',
    paths: [
      // Left — outer arm
      'M 56,96 Q 52,108 50,120 Q 48,130 50,136 L 54,134 Q 56,122 58,108 L 60,96 Z',
      // Right
      'M 144,96 Q 148,108 150,120 Q 152,130 150,136 L 146,134 Q 144,122 142,108 L 140,96 Z',
    ],
  },
];


// ── BACK VIEW (Posterior) ───────────────────────────────────────────────

export const BACK_MUSCLES: MusclePath[] = [
  // ── HEAD / NECK (back view) ──
  {
    id: 'head',
    name: 'Head',
    view: 'back',
    paths: [
      'M 90,18 Q 100,2 110,18 Q 116,30 112,42 Q 100,50 88,42 Q 84,30 90,18 Z',
    ],
  },
  {
    id: 'neck',
    name: 'Neck',
    view: 'back',
    paths: [
      'M 94,42 L 106,42 L 108,58 L 92,58 Z',
    ],
  },

  // ── TRAPS (back view — full diamond shape) ──
  {
    id: 'traps',
    name: 'Trapezius',
    view: 'back',
    paths: [
      // Upper traps
      'M 92,52 L 70,64 L 75,72 L 100,80 L 125,72 L 130,64 L 108,52 Z',
    ],
  },

  // ── POSTERIOR DELTOIDS ──
  {
    id: 'posterior_deltoid',
    name: 'Posterior Deltoid',
    view: 'back',
    paths: [
      // Left
      'M 68,68 Q 58,76 56,86 Q 58,94 62,96 L 68,88 L 70,74 Z',
      // Right
      'M 132,68 Q 142,76 144,86 Q 142,94 138,96 L 132,88 L 130,74 Z',
    ],
  },

  // ── RHOMBOIDS ──
  {
    id: 'rhomboids',
    name: 'Rhomboids',
    view: 'back',
    paths: [
      // Between spine and scapulae
      'M 88,72 L 100,76 L 112,72 L 114,100 L 100,104 L 86,100 Z',
    ],
  },

  // ── LATS ──
  {
    id: 'lats',
    name: 'Latissimus Dorsi',
    view: 'back',
    paths: [
      // Left lat — wide V shape
      'M 72,78 L 86,100 L 84,130 Q 80,148 78,155 L 70,150 Q 64,130 62,110 Q 60,96 66,82 Z',
      // Right lat
      'M 128,78 L 114,100 L 116,130 Q 120,148 122,155 L 130,150 Q 136,130 138,110 Q 140,96 134,82 Z',
    ],
  },

  // ── ERECTOR SPINAE ──
  {
    id: 'erector_spinae',
    name: 'Erector Spinae',
    view: 'back',
    paths: [
      // Two columns along the spine
      'M 94,100 L 100,98 L 106,100 L 108,155 L 100,158 L 92,155 Z',
    ],
  },

  // ── TRICEPS (visible from back) ──
  {
    id: 'triceps',
    name: 'Triceps Brachii',
    view: 'back',
    paths: [
      // Left
      'M 58,96 Q 52,110 50,128 Q 52,136 56,138 Q 60,128 62,114 L 64,96 Z',
      // Right
      'M 142,96 Q 148,110 150,128 Q 148,136 144,138 Q 140,128 138,114 L 136,96 Z',
    ],
  },

  // ── FOREARMS (back) ──
  {
    id: 'forearms',
    name: 'Forearms',
    view: 'back',
    paths: [
      'M 52,138 Q 48,156 46,174 Q 44,184 46,188 L 52,186 Q 56,172 58,158 L 56,138 Z',
      'M 148,138 Q 152,156 154,174 Q 156,184 154,188 L 148,186 Q 144,172 142,158 L 144,138 Z',
    ],
  },

  // ── GLUTES ──
  {
    id: 'glutes',
    name: 'Gluteus Maximus',
    view: 'back',
    paths: [
      // Left glute
      'M 78,155 L 100,160 L 100,190 Q 94,196 86,196 Q 76,192 72,182 Q 70,170 74,160 Z',
      // Right glute
      'M 122,155 L 100,160 L 100,190 Q 106,196 114,196 Q 124,192 128,182 Q 130,170 126,160 Z',
    ],
  },

  // ── HAMSTRINGS ──
  {
    id: 'hamstrings',
    name: 'Hamstrings',
    view: 'back',
    paths: [
      // Left hamstring
      'M 74,196 Q 70,210 68,230 Q 68,250 72,270 L 86,268 Q 88,250 88,230 L 86,196 Z',
      // Right hamstring
      'M 126,196 Q 130,210 132,230 Q 132,250 128,270 L 114,268 Q 112,250 112,230 L 114,196 Z',
    ],
  },

  // ── CALVES (posterior — gastrocnemius) ──
  {
    id: 'calves',
    name: 'Calves (Gastrocnemius)',
    view: 'back',
    paths: [
      // Left calf — diamond shape
      'M 74,274 Q 70,290 68,310 Q 68,330 70,340 L 76,350 L 84,348 Q 88,330 88,310 Q 88,290 86,274 Z',
      // Right calf
      'M 126,274 Q 130,290 132,310 Q 132,330 130,340 L 124,350 L 116,348 Q 112,330 112,310 Q 112,290 114,274 Z',
    ],
  },

  // ── ADDUCTORS (inner thigh — back view) ──
  {
    id: 'adductors',
    name: 'Adductors',
    view: 'back',
    paths: [
      'M 88,196 L 96,194 L 98,220 L 94,240 L 88,238 Z',
      'M 112,196 L 104,194 L 102,220 L 106,240 L 112,238 Z',
    ],
  },

  // ── BICEPS (back view — inner arm) ──
  {
    id: 'biceps',
    name: 'Biceps Brachii',
    view: 'back',
    paths: [
      'M 62,96 Q 64,110 66,128 Q 64,136 60,138 L 58,134 Q 56,118 56,106 L 58,96 Z',
      'M 138,96 Q 136,110 134,128 Q 136,136 140,138 L 142,134 Q 144,118 144,106 L 142,96 Z',
    ],
  },
];


// ── VIEWBOX for both views ──────────────────────────────────────────────

export const VIEWBOX = '0 0 200 420';
export const SVG_WIDTH = 200;
export const SVG_HEIGHT = 420;


// ── Color scale (cool-blue → red heat-map) ─────────────────────────────

/**
 * Returns an HSL color string for a given activation percentage (0–100).
 * 0% = cool blue (hsl 210, 80%, 50%)
 * 20% = cyan (hsl 190, 90%, 50%)
 * 40% = teal-green (hsl 160, 85%, 45%)
 * 60% = amber (hsl 40, 90%, 50%)
 * 80% = orange (hsl 20, 90%, 50%)
 * 100% = red (hsl 0, 85%, 55%)
 */
export function activationColor(percentage: number): string {
  const p = Math.max(0, Math.min(100, percentage));
  // Hue ranges from 210 (blue) down to 0 (red)
  const hue = 210 - (p / 100) * 210;
  // Saturation ramps up
  const sat = 65 + (p / 100) * 25;
  // Lightness sweet spot
  const light = 48 + Math.sin((p / 100) * Math.PI) * 12;
  return `hsl(${Math.round(hue)}, ${Math.round(sat)}%, ${Math.round(light)}%)`;
}

/**
 * Returns a glow-shadow color for the muscle at given intensity.
 */
export function activationGlow(percentage: number): string {
  const color = activationColor(percentage);
  const alpha = 0.3 + (percentage / 100) * 0.5;
  return color.replace('hsl', 'hsla').replace(')', `, ${alpha})`);
}
