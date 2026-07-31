import type { ReactNode } from 'react';
import { C, R } from '../../theme/tokens';

type Tone = 'clay' | 'sage' | 'amber' | 'rust' | 'indigo' | 'neutral';
type Size = 'xs' | 'sm' | 'md' | 'lg';

/**
 * Icon "stamp" — a soft tinted square containing a single Lucide icon.
 * The editorial workhorse for visual rhythm across every page.
 *
 *   <IconBadge tone="clay" size="md"><Activity size={18} /></IconBadge>
 */
export function IconBadge({
  children,
  tone = 'clay',
  size = 'md',
  shape = 'square',
  style,
}: {
  children: ReactNode;
  tone?: Tone;
  size?: Size;
  shape?: 'square' | 'circle';
  style?: React.CSSProperties;
}) {
  const palette = {
    clay:    { bg: C.clayTint,   fg: C.clay,   border: C.borderClay },
    sage:    { bg: C.sageTint,   fg: C.sage,   border: C.borderSage },
    amber:   { bg: C.amberTint,  fg: C.amber,  border: 'rgba(255,201,74,0.30)' },
    rust:    { bg: C.rustTint,   fg: C.rust,   border: C.borderClay },
    indigo:  { bg: C.indigoTint, fg: C.indigo, border: 'rgba(51,199,255,0.30)' },
    neutral: { bg: C.taupe,      fg: C.ink2,   border: C.border },
  }[tone];

  const sizeMap = {
    xs: 22, sm: 28, md: 36, lg: 48,
  }[size];

  return (
    <span
      aria-hidden
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: sizeMap, height: sizeMap,
        background: palette.bg,
        color: palette.fg,
        border: `1px solid ${palette.border}`,
        borderRadius: shape === 'circle' ? sizeMap : R.md,
        flexShrink: 0,
        ...style,
      }}>
      {children}
    </span>
  );
}

export default IconBadge;
