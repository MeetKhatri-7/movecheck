/**
 * MetricHistogram — vertical bar chart of metrics vs target threshold.
 *
 * Built from scratch in SVG (no chart library) to match the bone+clay
 * palette and stay tiny in the bundle. Bars are colour-coded by status,
 * value labels float above each bar, and a dashed horizontal line marks
 * the 100% target threshold. Hover reveals a tooltip.
 */
import { useMemo, useState } from 'react';
import type { Metric } from '@/data/types';
import { C, F } from '@/theme/tokens';

/** Normalise a metric to a 0..100% bar height that respects target direction. */
function metricToPct(m: Metric): number {
  const target = (m.target || '').toString();
  const higherIsBetter = /[≥>]/.test(target) || /at\s*(or\s*)?(below|above)\s*parallel/i.test(target);
  const lowerIsBetter  = /[≤<]/.test(target);
  const base = m.max && m.max > 0 ? (Math.abs(m.raw) / m.max) * 100 : 50;
  let pct = base;
  if (lowerIsBetter && !higherIsBetter) pct = 100 - base;
  return Math.max(0, Math.min(120, pct)); // allow bars to exceed 100% when overshooting target
}

/** Short label for x-axis (removes parens, truncates to `max` chars). */
function shortLabel(m: Metric, max = 14): string {
  let s = m.name.replace(/\s*\([^)]*\)\s*/g, '').trim();
  if (s.length > max) s = s.slice(0, max - 1) + '…';
  return s;
}

/**
 * Performance-graded colour ramp keyed to how far a bar clears the 100%
 * target. This is a diverging status scale (not categorical) — greens above
 * target, warming through amber → orange → red the further under it falls.
 * `top`/`base` drive a vertical gradient so every bar also carries a shade.
 */
type PerfTier = { key: string; label: string; top: string; base: string };
function perfTier(pct: number, lowConf: boolean): PerfTier {
  if (lowConf) return { key: 'low_conf', label: 'Low confidence', top: '#AEB6C0', base: '#5C636C' };
  if (pct >= 112) return { key: 'elite', label: 'Well clear',    top: '#6CF0AE', base: '#0FB25C' };
  if (pct >= 100) return { key: 'pass',  label: 'On target',     top: '#3FE88C', base: '#1BB768' };
  if (pct >= 85)  return { key: 'near',  label: 'Just under',    top: '#FFE07A', base: '#E3A61F' };
  if (pct >= 65)  return { key: 'under', label: 'Under target',  top: '#FFB877', base: '#F5883C' };
  if (pct >= 40)  return { key: 'well',  label: 'Well under',    top: '#FF9A7A', base: '#FF5A36' };
  return                 { key: 'crit',  label: 'Far under',     top: '#FF7A66', base: '#D8371C' };
}

interface Props {
  metrics: Metric[];
  /** Max number of bars (extras truncated). */
  maxBars?: number;
  /** Total chart height in px. */
  height?: number;
  /**
   * Intrinsic viewBox width. The SVG always renders at 100% of its container,
   * so this is really a *text-scale* control: a narrower viewBox means the
   * 10px axis labels are scaled down less on a small screen. Pass ~380 on
   * phones, leave at 720 on desktop.
   */
  width?: number;
}

export function MetricHistogram({ metrics, maxBars = 9, height = 280, width = 720 }: Props) {
  const [hovered, setHovered] = useState<number | null>(null);

  // Build chart data, sorted: best tier first → worst tier last.
  const bars = useMemo(() => {
    const tierRank: Record<string, number> = {
      very_good: 0, good: 1, yellow_flag: 2, bad: 3, very_bad: 4,
    };
    // Narrow charts get shorter labels — the per-bar slot shrinks with the
    // viewBox, so 14 chars would run into the neighbouring bar.
    const labelMax = width < 500 ? 10 : 14;
    const enriched = metrics
      .filter(m => m.max && m.max > 0)
      .map(m => ({
        m,
        pct: metricToPct(m),
        label: shortLabel(m, labelMax),
      }));
    enriched.sort((a, b) => {
      const ar = tierRank[a.m.status] ?? 1;  // legacy 'good'/'bad' fall into rank 1/3
      const br = tierRank[b.m.status] ?? 1;
      if (ar !== br) return ar - br;
      return b.pct - a.pct;
    });
    return enriched.slice(0, maxBars);
  }, [metrics, maxBars, width]);

  const isPassing = (status: string) => status === 'good' || status === 'very_good';

  if (bars.length === 0) return null;

  // ── chart geometry ───────────────────────────────────────────────
  const padL = 44, padR = 16, padT = 28, padB = 56;
  const W = width;  // intrinsic; SVG scales responsively
  const H = height;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const barW = Math.min(48, plotW / bars.length * 0.6);
  const gap = (plotW - barW * bars.length) / Math.max(1, bars.length - 1);
  const yScale = (pct: number) => padT + plotH - (Math.min(pct, 120) / 120) * plotH;
  const targetY = yScale(100);

  return (
    <div style={{ width: '100%', position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: 'block', overflow: 'visible' }}>
        {/* ── Per-bar vertical gradients (bright cap → deep base) ────── */}
        <defs>
          {bars.map((b, i) => {
            const tier = perfTier(b.pct, b.m.confidence_tier === 'low');
            return (
              <linearGradient key={i} id={`mh-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={tier.top} />
                <stop offset="100%" stopColor={tier.base} />
              </linearGradient>
            );
          })}
        </defs>

        {/* ── Y-axis gridlines + ticks (0 / 50 / 100 / 120%) ─────────── */}
        {[0, 50, 100, 120].map(t => {
          const y = yScale(t);
          const isTarget = t === 100;
          return (
            <g key={t}>
              <line
                x1={padL} y1={y} x2={W - padR} y2={y}
                stroke={isTarget ? C.clay : C.borderStrong}
                strokeWidth={isTarget ? 1.2 : 0.6}
                strokeDasharray={isTarget ? '6 4' : t === 0 ? undefined : '2 4'}
                opacity={isTarget ? 0.8 : t === 0 ? 0.5 : 0.4}
              />
              <text
                x={padL - 8} y={y + 3}
                textAnchor="end"
                fontFamily={F.body} fontSize="10"
                fill={isTarget ? C.clay : C.ink3}
                fontWeight={isTarget ? 600 : 400}
                letterSpacing="0.06em">
                {t}%
              </text>
            </g>
          );
        })}

        {/* "TARGET" label on the dashed line */}
        <text
          x={W - padR - 4} y={targetY - 6}
          textAnchor="end"
          fontFamily={F.body} fontSize="9"
          fill={C.clay} fontWeight="700"
          letterSpacing="0.14em">
          TARGET
        </text>

        {/* ── Bars ─────────────────────────────────────────────────── */}
        {bars.map((b, i) => {
          const x = padL + i * (barW + gap);
          const y = yScale(b.pct);
          const h = padT + plotH - y;
          const lowConf = b.m.confidence_tier === 'low';
          const passing = isPassing(b.m.status);
          const tier = perfTier(b.pct, lowConf);
          const isHover = hovered === i;
          const barColor = tier.base;

          return (
            <g key={i}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: 'pointer' }}>
              {/* Coloured footer track (tier base, faint) */}
              <rect
                x={x} y={padT + plotH - 4}
                width={barW} height={4}
                fill={barColor} opacity={0.28} rx={2}
              />
              {/* Bar */}
              <rect
                x={x} y={y}
                width={barW} height={Math.max(2, h)}
                fill={`url(#mh-grad-${i})`}
                rx={3}
                style={{
                  transition: 'opacity 200ms ease, filter 200ms ease',
                  opacity: isHover ? 1 : 0.94,
                  filter: isHover ? `drop-shadow(0 4px 14px ${barColor}66)` : 'none',
                }}
              >
                <animate attributeName="height"
                  from="0" to={Math.max(2, h)}
                  dur="0.9s" fill="freeze"
                  calcMode="spline" keySplines="0.16 1 0.3 1" />
                <animate attributeName="y"
                  from={padT + plotH} to={y}
                  dur="0.9s" fill="freeze"
                  calcMode="spline" keySplines="0.16 1 0.3 1" />
              </rect>
              {/* Bright cap highlight — extra shade at the very top of the bar */}
              {h > 6 && (
                <rect
                  x={x} y={y}
                  width={barW} height={Math.min(6, h)}
                  fill={tier.top} opacity={0.9} rx={3}
                  pointerEvents="none"
                >
                  <animate attributeName="y"
                    from={padT + plotH} to={y}
                    dur="0.9s" fill="freeze"
                    calcMode="spline" keySplines="0.16 1 0.3 1" />
                </rect>
              )}

              {/* Value label above bar */}
              <text
                x={x + barW / 2} y={Math.max(padT + 10, y - 8)}
                textAnchor="middle"
                fontFamily={F.display} fontSize="13"
                fill={passing ? C.ink : tier.top}
                fontWeight={passing ? '600' : '700'}>
                {Math.round(b.pct)}%
              </text>

              {/* X-axis label */}
              <text
                x={x + barW / 2} y={padT + plotH + 18}
                textAnchor="middle"
                fontFamily={F.body} fontSize="10"
                fill={C.ink2}
                fontWeight="500">
                {b.label}
              </text>
              <text
                x={x + barW / 2} y={padT + plotH + 30}
                textAnchor="middle"
                fontFamily={F.display} fontSize="10"
                fill={C.ink3}>
                {b.m.value}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Tooltip (overlay) */}
      {hovered != null && bars[hovered] && (
        <div style={{
          position: 'absolute', top: 6, right: 12,
          background: C.surfaceSolid, border: `1px solid ${C.borderStrong}`,
          borderRadius: 10, padding: '10px 14px',
          boxShadow: '0 12px 28px rgba(0,0,0,0.45)',
          maxWidth: 260, pointerEvents: 'none',
        }}>
          <div style={{
            fontFamily: F.body, fontSize: 9.5, fontWeight: 600,
            letterSpacing: '0.18em', textTransform: 'uppercase',
            color: perfTier(bars[hovered].pct, bars[hovered].m.confidence_tier === 'low').top,
            marginBottom: 2,
          }}>{perfTier(bars[hovered].pct, bars[hovered].m.confidence_tier === 'low').label}</div>
          <div style={{
            fontFamily: F.display, fontSize: 18, color: C.ink,
            letterSpacing: '-0.01em', marginBottom: 4,
          }}>{bars[hovered].m.name}</div>
          <div style={{ fontSize: 12, color: C.ink2 }}>
            Value: <strong>{bars[hovered].m.value}</strong>{' · '}
            Target: <span style={{ color: C.ink3 }}>{bars[hovered].m.target}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default MetricHistogram;
