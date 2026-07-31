import type { ReactNode } from 'react';
import { C, F } from '../../theme/tokens';

/**
 * Display-stat block: tiny uppercase label + serif numeral.
 * Composes well in 2-/3-/4-column grids on the dashboard and result page.
 */
export function Stat({
  label,
  value,
  hint,
  accent,
  align = 'left',
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: string;
  align?: 'left' | 'center' | 'right';
}) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      alignItems: align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start',
      textAlign: align,
    }}>
      <div style={{
        fontFamily: F.display,
        fontWeight: 400,
        fontSize: 32,
        letterSpacing: '0.4px',
        lineHeight: 1.0,
        color: accent || C.ink,
      }}>
        {value}
      </div>
      <div style={{
        fontFamily: F.body, fontWeight: 700, fontSize: 10,
        letterSpacing: '0.1em', textTransform: 'uppercase', color: C.ink4,
      }}>{label}</div>
      {hint && (
        <div style={{ fontSize: 12, color: C.ink3, marginTop: 2 }}>
          {hint}
        </div>
      )}
    </div>
  );
}

export default Stat;
