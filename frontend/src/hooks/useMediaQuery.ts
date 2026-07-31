import { useEffect, useState } from 'react';
import { BP } from '@/theme/tokens';

/**
 * Subscribe to a CSS media query from JS.
 *
 * The whole UI is built from inline styles (see `theme/tokens.ts`), so CSS
 * media queries can't reach it. This hook is how layout decisions that
 * genuinely change *structure* — a two-column grid becoming one column, a
 * fixed sidebar becoming a stacked block — are made responsive.
 *
 * For anything that is only a *size* change (padding, font-size, gap), prefer
 * `clamp()` in the style itself: it costs no re-render and no JS.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    // Sync once on mount in case the query changed between render and effect.
    setMatches(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

/** True on phones (≤ 640px) — the "one column, full-width buttons" breakpoint. */
export function useIsMobile(): boolean {
  return useMediaQuery(`(max-width: ${BP.mobile}px)`);
}

/** True on phones + small tablets (≤ 900px) — where side-by-side panels stop fitting. */
export function useIsNarrow(): boolean {
  return useMediaQuery(`(max-width: ${BP.narrow}px)`);
}

/** True on tablets and below (≤ 1024px). */
export function useIsTablet(): boolean {
  return useMediaQuery(`(max-width: ${BP.tablet}px)`);
}

/**
 * True when the primary input is a coarse pointer (finger). Used to drop
 * keyboard-shortcut affordances and hover-only hints that mean nothing on a
 * touch device.
 */
export function useIsTouch(): boolean {
  return useMediaQuery('(hover: none) and (pointer: coarse)');
}
