/**
 * MuscleBody — anatomical front + back silhouettes with heat-mapped muscle
 * activation in the bone + clay palette.
 *
 * The user sees their own body lit up by which muscles did the work — every
 * muscle group is a real SVG region (head, traps, pecs, lats, glutes, quads,
 * hams, calves, …). Activation intensity drives the fill colour from cool
 * taupe → amber → clay → deep rust.
 *
 * Backend muscle slugs (quadriceps, glutes, lats, …) map directly to the
 * `id` of each path defined in `muscle-paths.ts`.
 */
import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import type { MuscleActivationData } from '@/data/types';
import { FRONT_MUSCLES, BACK_MUSCLES, VIEWBOX, type MusclePath } from './muscle-paths';
import { C, F, R } from '@/theme/tokens';

/* ── Bone+clay heat scale ──────────────────────────────────────────────
 *  0–10%   → taupe (idle muscle, basically off)
 *  10–35%  → soft taupe-clay mix
 *  35–60%  → amber
 *  60–80%  → clay
 *  80–100% → deep rust (the engine of the lift)
 */
function heatFill(percentage: number): { fill: string; stroke: string } {
  const p = Math.max(0, Math.min(100, percentage));
  if (p < 10)  return { fill: 'rgba(255,255,255,0.06)', stroke: 'rgba(255,255,255,0.12)' };
  if (p < 35)  return { fill: 'rgba(255,201,74,0.30)',  stroke: 'rgba(255,201,74,0.40)' };
  if (p < 60)  return { fill: C.amber,                  stroke: 'rgba(255,201,74,0.55)' };
  if (p < 80)  return { fill: C.clay,                   stroke: 'rgba(255,90,54,0.55)' };
  return         { fill: '#FF7A4A',                     stroke: 'rgba(255,122,74,0.70)' };
}

/* Body skeleton outline — drawn behind the muscles to anchor anatomy. */
const FRONT_SILHOUETTE = `
  M 100,4
  Q 116,4 122,18
  Q 126,30 122,42
  Q 134,48 142,60
  Q 152,68 158,82
  Q 162,100 160,112
  L 160,118
  Q 156,124 152,128
  Q 158,160 156,200
  Q 156,224 152,254
  Q 150,278 148,302
  Q 152,330 150,360
  Q 148,386 144,410
  L 130,412
  Q 124,388 124,362
  Q 122,330 120,302
  L 118,272
  Q 112,272 100,272
  Q 88,272 82,272
  L 80,302
  Q 78,330 76,362
  Q 76,388 70,412
  L 56,410
  Q 52,386 50,360
  Q 48,330 52,302
  Q 50,278 48,254
  Q 44,224 44,200
  Q 42,160 48,128
  Q 44,124 40,118
  L 40,112
  Q 38,100 42,82
  Q 48,68 58,60
  Q 66,48 78,42
  Q 74,30 78,18
  Q 84,4 100,4 Z
`.replace(/\s+/g, ' ').trim();

interface MuscleBodyProps {
  data: MuscleActivationData;
  /** Compact = no caption strip, smaller padding. */
  compact?: boolean;
}

export function MuscleBody({ data, compact = false }: MuscleBodyProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  /** Build a {slug → percentage} lookup so we can fill muscle paths quickly. */
  const activationMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const m of data.muscles ?? []) {
      // Aggregate L/R into a single value (max across sides).
      map[m.slug] = Math.max(map[m.slug] ?? 0, m.percentage ?? 0);
    }
    return map;
  }, [data.muscles]);

  /** Top muscles ranked by activation — used for the side legend. */
  const topMuscles = useMemo(() => {
    return [...(data.muscles ?? [])]
      .filter(m => m.percentage > 5)
      .sort((a, b) => b.percentage - a.percentage)
      .slice(0, 6);
  }, [data.muscles]);

  const renderView = (paths: MusclePath[], label: string) => (
    <div style={{ position: 'relative', flex: 1, display: 'flex', justifyContent: 'center' }}>
      <div style={{
        position: 'absolute', top: 0, left: 0,
        fontFamily: F.body, fontSize: 10, fontWeight: 600,
        letterSpacing: '0.20em', textTransform: 'uppercase',
        color: C.ink3,
      }}>{label}</div>

      <svg viewBox={VIEWBOX} width="100%" style={{
        maxWidth: 220, height: 'auto', display: 'block',
        filter: 'drop-shadow(0 6px 18px rgba(0,0,0,0.4))',
      }}>
        {/* Body silhouette (background) */}
        <path d={FRONT_SILHOUETTE}
          fill={C.surfaceSolid}
          stroke={C.borderStrong}
          strokeWidth="1.2"
          strokeLinejoin="round"
        />

        {/* Inactive muscle outlines — faint hint of structure */}
        {paths.map((m, idx) =>
          m.id === 'head' || m.id === 'neck' ? null :
          m.paths.map((d, j) => (
            <path key={`${idx}-${j}-outline`} d={d}
              fill="transparent"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="0.5"
            />
          ))
        )}

        {/* Active muscles — heat-mapped fills, layered above the outlines */}
        {paths.map((m, idx) => {
          if (m.id === 'head' || m.id === 'neck') return null;
          const pct = activationMap[m.id] ?? 0;
          if (pct < 5) return null;
          const { fill, stroke } = heatFill(pct);
          const isHover = hovered === m.id;
          return m.paths.map((d, j) => (
            <motion.path
              key={`${idx}-${j}-fill`} d={d}
              fill={fill}
              stroke={stroke}
              strokeWidth={isHover ? 1.6 : 0.9}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.1 + idx * 0.04, ease: 'easeOut' }}
              onMouseEnter={() => setHovered(m.id)}
              onMouseLeave={() => setHovered(null)}
              style={{
                cursor: 'pointer',
                filter: isHover ? `drop-shadow(0 0 4px ${stroke})` : 'none',
                transition: 'stroke-width 200ms ease, filter 200ms ease',
              }}
            />
          ));
        })}

        {/* Top-muscle % labels — drawn for muscles ≥ 50% activation */}
        {paths.map((m, idx) => {
          if (m.id === 'head' || m.id === 'neck') return null;
          const pct = activationMap[m.id] ?? 0;
          if (pct < 50) return null;
          // Use the first sub-path's rough centroid for label placement.
          const dStr = m.paths[0];
          const nums = dStr.match(/-?\d+(?:\.\d+)?/g)?.map(Number) ?? [];
          if (nums.length < 4) return null;
          let cx = 0, cy = 0, count = 0;
          for (let k = 0; k + 1 < nums.length; k += 2) {
            cx += nums[k]; cy += nums[k + 1]; count++;
          }
          if (!count) return null;
          cx /= count; cy /= count;
          return (
            <g key={`${idx}-lbl`} pointerEvents="none">
              <rect
                x={cx - 13} y={cy - 6}
                width={26} height={12} rx={6}
                fill="rgba(10,13,16,0.85)"
                stroke="rgba(255,255,255,0.20)"
                strokeWidth="0.5"
              />
              <text x={cx} y={cy + 3.5}
                textAnchor="middle"
                fontFamily={F.display}
                fontSize="9"
                fill={C.ink}
                fontWeight="600">
                {Math.round(pct)}%
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );

  /** Hovered muscle detail strip (or default summary). */
  const hoveredData = data.muscles?.find(m => m.slug === hovered);

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: R.xl,
      padding: compact ? 20 : 28,
      display: 'flex', flexDirection: 'column', gap: compact ? 14 : 20,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{
            fontFamily: F.body, fontSize: 10.5, fontWeight: 600,
            letterSpacing: '0.20em', textTransform: 'uppercase',
            color: C.ink3, marginBottom: 4,
          }}>Muscle activation</div>
          <div style={{
            fontFamily: F.display, fontSize: 22, color: C.ink,
            letterSpacing: '-0.015em', lineHeight: 1.15,
          }}>{data.dominance}</div>
        </div>
        <span style={{
          fontFamily: F.body, fontSize: 11, color: C.ink3, fontStyle: 'italic',
        }}>Estimated · not EMG</span>
      </div>

      {/* Body diagrams */}
      <div style={{
        display: 'grid', gap: 12,
        gridTemplateColumns: '1fr 1fr',
        background: `linear-gradient(180deg, ${C.bg3} 0%, ${C.bg} 100%)`,
        borderRadius: R.lg,
        padding: '16px 8px 8px',
        position: 'relative',
        minHeight: 280,
      }}>
        {renderView(FRONT_MUSCLES, 'Front')}
        {renderView(BACK_MUSCLES,  'Back')}
      </div>

      {/* Heat-scale legend */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 12,
      }}>
        <div style={{
          fontFamily: F.body, fontSize: 9.5, fontWeight: 600,
          letterSpacing: '0.18em', textTransform: 'uppercase', color: C.ink3,
        }}>Low</div>
        <div style={{ display: 'flex', gap: 0, flex: 1, maxWidth: 280, height: 8, borderRadius: 4, overflow: 'hidden' }}>
          {[10, 30, 50, 70, 90].map(p => (
            <div key={p} style={{ flex: 1, background: heatFill(p).fill }} />
          ))}
        </div>
        <div style={{
          fontFamily: F.body, fontSize: 9.5, fontWeight: 600,
          letterSpacing: '0.18em', textTransform: 'uppercase', color: C.ink3,
        }}>High</div>
      </div>

      {/* Hovered detail OR top muscles list */}
      {hoveredData ? (
        <div style={{
          padding: '12px 14px', background: C.surface2, borderRadius: R.md,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        }}>
          <div>
            <div style={{ fontFamily: F.body, fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', color: C.ink3 }}>
              {hoveredData.isPrimary ? 'Primary mover' : 'Stabiliser'}
            </div>
            <div style={{ fontFamily: F.display, fontSize: 18, color: C.ink, marginTop: 2 }}>
              {hoveredData.name}
            </div>
          </div>
          <div style={{ fontFamily: F.display, fontSize: 26, color: heatFill(hoveredData.percentage).fill, letterSpacing: '-0.02em' }}>
            {Math.round(hoveredData.percentage)}<span style={{ fontSize: 12, color: C.ink3 }}>%</span>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{
            fontFamily: F.body, fontSize: 10, fontWeight: 600,
            letterSpacing: '0.18em', textTransform: 'uppercase', color: C.ink3,
            marginBottom: 4,
          }}>Top muscles</div>
          {topMuscles.map(m => (
            <div key={m.slug + (m.side ?? '')} style={{
              display: 'grid', gridTemplateColumns: '12px 1fr 56px 40px',
              alignItems: 'center', gap: 10,
              padding: '4px 0',
            }}
              onMouseEnter={() => setHovered(m.slug)}
              onMouseLeave={() => setHovered(null)}>
              <span style={{
                width: 8, height: 8, borderRadius: 4,
                background: heatFill(m.percentage).fill,
              }} />
              <span style={{
                fontFamily: F.body, fontSize: 12.5, color: C.ink,
                fontWeight: m.isPrimary ? 600 : 400,
              }}>{m.name}</span>
              <div style={{ height: 4, borderRadius: 2, background: C.taupe, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 2,
                  background: heatFill(m.percentage).fill,
                  width: `${Math.min(100, m.percentage)}%`,
                  transition: 'width 800ms cubic-bezier(.16,1,.3,1)',
                }} />
              </div>
              <span style={{
                fontFamily: F.display, fontSize: 14, color: C.ink,
                textAlign: 'right', letterSpacing: '-0.01em',
              }}>{Math.round(m.percentage)}<span style={{ fontSize: 9, color: C.ink3 }}>%</span></span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default MuscleBody;
