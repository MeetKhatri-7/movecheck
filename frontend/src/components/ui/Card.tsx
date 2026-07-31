import type { CSSProperties, HTMLAttributes, ReactNode } from 'react';
import { C, R } from '../../theme/tokens';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** raised = glass w/ blur; flat = subtler glass; sunken = faint inset panel */
  variant?: 'raised' | 'flat' | 'sunken';
  /** Internal padding token (default 24px). */
  pad?: number | string;
  /** Optional accent stripe on the left edge (clay/sage/amber/cyan). */
  accent?: 'clay' | 'sage' | 'amber' | 'rust' | 'cyan' | 'none';
  interactive?: boolean;
  children?: ReactNode;
}

export function Card({
  variant = 'raised',
  pad = 28,
  accent = 'none',
  interactive = false,
  style,
  children,
  ...rest
}: CardProps) {
  let bg: string = C.surface;
  let border: string = C.border;
  let shadow: string = 'none';

  if (variant === 'flat') {
    bg = C.surface2;
    shadow = 'none';
  } else if (variant === 'sunken') {
    bg = C.surface2;
    shadow = 'inset 0 1px 0 rgba(255,255,255,0.04)';
    border = C.border;
  }

  const accentColor =
    accent === 'clay'  ? C.clay :
    accent === 'sage'  ? C.sage :
    accent === 'amber' ? C.amber :
    accent === 'rust'  ? C.rust :
    accent === 'cyan'  ? C.indigo :
    null;

  const merged: CSSProperties = {
    background: bg,
    backdropFilter: C.glassBlur,
    WebkitBackdropFilter: C.glassBlur,
    border: `1px solid ${border}`,
    // A left accent reads best as a thicker edge stripe in this system.
    borderLeft: accentColor ? `3px solid ${accentColor}` : `1px solid ${border}`,
    borderRadius: R.xl,
    padding: typeof pad === 'number' ? `${pad}px` : pad,
    boxShadow: shadow,
    position: 'relative',
    transition: interactive ? 'transform 240ms ease, border-color 240ms ease, box-shadow 240ms ease' : undefined,
    ...style,
  };

  return (
    <div {...rest} style={merged}>
      {children}
    </div>
  );
}

export default Card;
