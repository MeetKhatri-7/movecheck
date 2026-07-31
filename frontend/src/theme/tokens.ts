/**
 * MoveCheck — Athletic Dark design tokens.
 *
 * Single source of truth for the visual system. Inline-style call sites
 * import `T` (or `C, F, R, S`) and reference tokens directly, so every
 * surface stays in sync. Rewriting this file re-skins the whole app.
 *
 * Identity: near-black stage (#0A0D10), vermilion primary (#FF5A36), cyan
 * counterpoint (#33C7FF), Bebas Neue display + Inter body, glassmorphic
 * cards. Status ladder: green (pass) → yellow (improve) → orange (restricted).
 *
 * Legacy key names are preserved (bg / surface / ink / clay / sage / amber /
 * rust / indigo …) so existing components keep working — only their values
 * changed from the old "Editorial Bone" light theme to this dark system.
 */

export const C = {
  // ── surfaces ──────────────────────────────────────────────
  bg:        '#0A0D10', // near-black — page background (the "stage")
  bg2:       '#12171D', // raised dark section band
  bg3:       '#171D24', // image / video placeholder gradients
  surface:   'rgba(255,255,255,0.045)', // glass card fill
  surface2:  'rgba(255,255,255,0.03)',  // subtler glass / sunken
  surfaceSolid: '#141A20', // when a real opaque fill is needed
  taupe:     'rgba(255,255,255,0.06)',   // chip fill / low-key panels
  taupeDeep: 'rgba(255,255,255,0.10)',   // stronger chip / hairline-as-fill

  // ── ink (text) — light on dark ────────────────────────────
  ink:       '#F5F6F1', // primary headings / body
  ink2:      '#C7CCD2', // secondary body
  ink3:      '#8D95A0', // labels / muted body
  ink4:      '#5C636C', // captions / disabled / placeholder
  ink5:      '#3A4048', // faintest decorative

  // ── accents ───────────────────────────────────────────────
  clay:      '#FF5A36', // primary accent — vermilion (the brand colour)
  clayHover: '#FF8A6B',
  clayDark:  '#E04A2A',
  clayTint:  'rgba(255,90,54,0.12)', // soft fill behind clay accents

  // cyan counterpoint (kept under the legacy `indigo` key)
  indigo:    '#33C7FF', // secondary accent — cyan
  indigoTint:'rgba(51,199,255,0.12)',

  // violet — used for Core-category exercises
  violet:    '#A855F7',
  violetTint:'rgba(168,85,247,0.12)',

  // ── status ────────────────────────────────────────────────
  sage:      '#22D47A', // GOOD / pass — green
  sageTint:  'rgba(34,212,122,0.12)',
  sageDark:  '#1BB768',
  sageDeep:  '#22D47A', // VERY_GOOD — strongest positive

  amber:     '#FFC94A', // WARN / needs improvement (yellow_flag tier)
  amberTint: 'rgba(255,201,74,0.12)',

  rust:      '#FF5A36', // BAD / restricted — orange-red (same hue as brand)
  rustTint:  'rgba(255,90,54,0.12)',
  rustDeep:  '#FF7A4A', // VERY_BAD — strongest negative

  // ── borders ───────────────────────────────────────────────
  border:        'rgba(255,255,255,0.10)',
  borderStrong:  'rgba(255,255,255,0.18)',
  borderClay:    'rgba(255,90,54,0.35)',
  borderSage:    'rgba(34,212,122,0.30)',

  // ── glass + shadows ───────────────────────────────────────
  glassBlur: 'blur(18px)',
  shadow1: '0 1px 2px rgba(0,0,0,0.30)',
  shadow2: '0 8px 24px rgba(0,0,0,0.35)',
  shadow3: '0 16px 40px rgba(0,0,0,0.45)',
  shadowGlow: '0 12px 28px rgba(255,90,54,0.20)',
} as const;

export const F = {
  display: '"Bebas Neue", "Inter", system-ui, sans-serif',
  body:    '"Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
  mono:    '"JetBrains Mono", ui-monospace, SFMono-Regular, monospace',
} as const;

export const R = {
  xs:   6,
  sm:   8,
  md:   12,
  lg:   14,
  xl:   18,
  xxl:  22,
  pill: 999,
} as const;

export const S = {
  // spacing scale (px). Reach for these instead of magic numbers.
  '0': 0, '1': 4, '2': 8, '3': 12, '4': 16, '5': 20, '6': 24,
  '7': 32, '8': 40, '9': 48, '10': 56, '11': 64, '12': 80, '13': 96, '14': 128,
} as const;

export const Z = {
  base: 1,
  nav: 80,
  modal: 200,
  toast: 300,
} as const;

/**
 * Breakpoints (px). These are the *only* widths the app branches on — keep
 * them in sync with `hooks/useMediaQuery.ts`, which reads them directly.
 */
export const BP = {
  mobile: 640,  // phones — one column, full-width CTAs
  narrow: 900,  // large phones / small tablets — side-by-side panels stop fitting
  tablet: 1024,
} as const;

/**
 * Page gutter. Every full-width page section should use this for its
 * horizontal padding instead of a hard-coded 32px — 32px of padding either
 * side eats 17% of a 375px phone viewport.
 */
export const GUTTER = 'clamp(16px, 4.5vw, 32px)';

/** Slightly tighter gutter for content nested inside a card. */
export const GUTTER_TIGHT = 'clamp(14px, 3.5vw, 24px)';

/**
 * Responsive auto-fit grid columns.
 *
 * `minmax(320px, 1fr)` overflows any viewport narrower than 320px + padding,
 * which is exactly what phones are. Wrapping the minimum in `min(…, 100%)`
 * lets the track collapse to the container width instead, so the same grid
 * works from 320px to 4K with no JS and no media query.
 *
 *   gridCols(440)          → 'repeat(auto-fit, minmax(min(440px, 100%), 1fr))'
 *   gridCols(320, 'fill')  → uses auto-fill (keeps empty tracks)
 */
export const gridCols = (min: number, mode: 'fit' | 'fill' = 'fit') =>
  `repeat(auto-${mode}, minmax(min(${min}px, 100%), 1fr))`;

/** Reusable glass-card style block (spread into an inline style object). */
export const glass = {
  background: C.surface,
  backdropFilter: C.glassBlur,
  WebkitBackdropFilter: C.glassBlur,
  border: `1px solid ${C.border}`,
} as const;

/** Status → palette mapping used across pills, gauges, and metric chips.
 *
 * Accepts both the legacy 3-state tokens (good / warn / bad / critical /
 * low_conf / neutral) and the 5-tier doc-driven Metric.status tokens
 * (very_good / good / yellow_flag / bad / very_bad). Each tier renders its
 * own bright fg over a matched translucent fill so tiers stay distinct on
 * the dark stage. */
export const statusColor = (
  status:
    | 'good' | 'bad' | 'warn' | 'critical' | 'low_conf' | 'neutral'
    | 'very_good' | 'yellow_flag' | 'very_bad' | 'clay'
): { fg: string; bg: string; border: string } => {
  switch (status) {
    case 'very_good': return { fg: C.sageDeep, bg: C.sageTint,  border: C.borderSage };
    case 'good':      return { fg: C.sage,     bg: C.sageTint,  border: C.borderSage };
    case 'warn':
    case 'yellow_flag': return { fg: C.amber,  bg: C.amberTint, border: 'rgba(255,201,74,0.32)' };
    case 'bad':
    case 'critical': return { fg: C.rust,     bg: C.rustTint,   border: C.borderClay };
    case 'very_bad': return { fg: C.rustDeep, bg: C.rustTint,   border: C.borderClay };
    case 'low_conf': return { fg: C.ink3,     bg: C.taupe,      border: C.border };
    case 'clay':     return { fg: C.clay,     bg: C.clayTint,   border: C.borderClay };
    default:         return { fg: C.ink2,     bg: C.taupe,      border: C.border };
  }
};

/** Convenience: convert overall result status string → palette. */
export const overallStatusColor = (s?: string) => {
  switch (s) {
    case 'GOOD':              return statusColor('good');
    case 'PASS':              return statusColor('good');
    case 'ADEQUATE':          return statusColor('warn');
    case 'NEEDS IMPROVEMENT': return statusColor('warn');
    case 'RESTRICTED':        return statusColor('bad');
    default:                  return statusColor('neutral');
  }
};

/** Numeric score (0–100) → colour, matching the redesign's ring colours. */
export const scoreColor = (score: number): string => {
  if (score >= 75) return C.sage;
  if (score >= 55) return C.amber;
  return C.clay;
};

/** Single export object for ergonomic destructure: `const { C, F, R, S } = T`. */
export const T = {
  C, F, R, S, Z, BP, GUTTER, GUTTER_TIGHT, gridCols,
  glass, statusColor, overallStatusColor, scoreColor,
};
export default T;