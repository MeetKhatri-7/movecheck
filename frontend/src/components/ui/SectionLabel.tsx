import type { ReactNode, ElementType } from 'react';
import { C, F } from '../../theme/tokens';

/**
 * "Kicker" label — small uppercase tracked text used above section titles.
 * Anchors the rhythm; pair with <Display> headline below. Defaults to the
 * cyan eyebrow colour the MoveCheck redesign uses over section headings.
 */
export function SectionLabel({
  children,
  color = C.indigo,
  style,
}: {
  children: ReactNode;
  color?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{
      fontFamily: F.body,
      fontWeight: 700,
      fontSize: 11,
      letterSpacing: '0.18em',
      textTransform: 'uppercase',
      color,
      ...style,
    }}>
      {children}
    </div>
  );
}

/**
 * Display heading — Bebas Neue, condensed all-caps (the MoveCheck voice).
 * Wrap an `<em>` inside for the vermilion accent (styled in index.css).
 */
export function Display({
  children,
  size = 'h2',
  style,
  as: As = 'h2',
}: {
  children: ReactNode;
  size?: 'hero' | 'h1' | 'h2' | 'h3' | 'h4';
  style?: React.CSSProperties;
  as?: ElementType;
}) {
  const sizeMap = {
    hero: { fz: 'clamp(60px, 9vw, 108px)', lh: 0.92 },
    h1:   { fz: 'clamp(40px, 5.5vw, 64px)', lh: 0.98 },
    h2:   { fz: 'clamp(32px, 3.4vw, 52px)', lh: 1.0  },
    h3:   { fz: 24, lh: 1.05 },
    h4:   { fz: 20, lh: 1.1 },
  }[size];

  return (
    <As className="display" style={{
      fontFamily: F.display,
      fontWeight: 400,
      letterSpacing: '0.5px',
      lineHeight: sizeMap.lh,
      fontSize: sizeMap.fz,
      color: C.ink,
      margin: 0,
      ...style,
    } as React.CSSProperties}>
      {children}
    </As>
  );
}

export default SectionLabel;