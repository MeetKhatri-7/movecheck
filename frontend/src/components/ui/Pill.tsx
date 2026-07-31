import type { ReactNode } from 'react';
import { C, F, R, statusColor } from '../../theme/tokens';

type Tone = 'good' | 'bad' | 'warn' | 'critical' | 'low_conf' | 'neutral' | 'clay'
  | 'very_good' | 'yellow_flag' | 'very_bad';

export function Pill({
  tone = 'neutral',
  size = 'sm',
  children,
  uppercase = true,
}: {
  tone?: Tone;
  size?: 'xs' | 'sm' | 'md';
  children: ReactNode;
  uppercase?: boolean;
}) {
  let palette = tone === 'clay'
    ? { fg: C.clay, bg: C.clayTint, border: C.borderClay }
    : statusColor(tone);

  const sizeMap = {
    xs: { padY: 2, padX: 8,  font: 10 },
    sm: { padY: 3, padX: 10, font: 10.5 },
    md: { padY: 5, padX: 14, font: 12 },
  }[size];

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      background: palette.bg,
      color: palette.fg,
      border: `1px solid ${palette.border}`,
      borderRadius: R.pill,
      padding: `${sizeMap.padY}px ${sizeMap.padX}px`,
      fontFamily: F.body,
      fontWeight: 600,
      fontSize: sizeMap.font,
      letterSpacing: uppercase ? '0.10em' : 0,
      textTransform: uppercase ? 'uppercase' : 'none',
      lineHeight: 1.2,
      whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

export default Pill;
