import { useState } from 'react';
import type { PerRepMetric } from '@/data/types';
import { C, F } from '@/theme/tokens';

interface Props { reps: PerRepMetric[]; bestRep?: number; }

export function PerRepAccordion({ reps, bestRep }: Props) {
  const [open, setOpen] = useState<number | null>(null);
  if (!reps || reps.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {reps.map((rep, i) => {
        const isBest = bestRep !== undefined ? rep.rep === bestRep : i === 0;
        const isOpen = open === i;
        const entries = Object.entries(rep.metrics).filter(([k]) => !['peak_frame', 'side'].includes(k));

        return (
          <div key={i} style={{
            borderRadius: 12, overflow: 'hidden',
            border: `1px solid ${isBest ? C.borderClay : C.border}`,
            background: C.surface2,
          }}>
            <button onClick={() => setOpen(isOpen ? null : i)}
              style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'none', border: 'none', cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: isBest ? C.clayTint : C.taupe, border: `1px solid ${isBest ? C.borderClay : C.border}`,
                  fontFamily: F.display, fontWeight: 400, fontSize: 14, color: isBest ? C.clay : C.ink3,
                }}>
                  {rep.rep}
                </div>
                <span style={{ fontFamily: F.body, fontWeight: 700, fontSize: 13, color: C.ink }}>Rep {rep.rep}</span>
                {rep.side && <span style={{ fontSize: 10, color: C.ink4, fontFamily: F.body, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700 }}>{rep.side}</span>}
                {isBest && <span style={{ background: C.clayTint, border: `1px solid ${C.borderClay}`, borderRadius: 6, padding: '2px 8px', fontFamily: F.body, fontWeight: 700, fontSize: 9, letterSpacing: '0.1em', color: C.clay }}>★ BEST</span>}
              </div>
              <span style={{ fontSize: 12, color: C.ink4, transition: 'transform 0.2s', transform: isOpen ? 'rotate(180deg)' : 'rotate(0)' }}>▼</span>
            </button>
            {isOpen && (
              <div style={{ padding: '0 16px 14px', borderTop: `1px solid ${C.border}` }}>
                <div style={{ display: 'grid', gap: 8, paddingTop: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
                  {entries.map(([key, val]) => (
                    <div key={key} style={{ background: C.taupe, borderRadius: 8, padding: '8px 12px' }}>
                      <div style={{ fontSize: 9, color: C.ink4, fontFamily: F.body, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 2, fontWeight: 700 }}>
                        {key.replace(/_/g, ' ')}
                      </div>
                      <div style={{ fontFamily: F.display, fontWeight: 400, fontSize: 16, color: C.ink }}>
                        {typeof val === 'number' ? val.toFixed?.(1) ?? val : val}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}