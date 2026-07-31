/**
 * MuscleMap — Interactive muscle activation diagram with front/back card-flip.
 *
 * Features:
 *   - Hand-crafted SVG anatomy with per-muscle path highlighting
 *   - Heat-map gradient coloring (cool-blue → red)
 *   - 3D card-flip animation to toggle front ↔ back view
 *   - Hover tooltips with muscle name, %, and primary/stabilizer badge
 *   - Animated percentage labels with connecting lines
 *   - "Estimated from kinematics · Not EMG" disclaimer badge
 *   - Responsive sizing
 */
import { useState, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { MuscleActivationData, MuscleActivation } from '@/data/types';
import {
  FRONT_MUSCLES, BACK_MUSCLES, VIEWBOX,
  activationColor, activationGlow,
  type MusclePath,
} from './muscle-paths';

/* ── Styles ────────────────────────────────────────────────────────────── */

const containerStyle: React.CSSProperties = {
  position: 'relative',
  width: '100%',
  maxWidth: 520,
  margin: '0 auto',
};

const cardStyle: React.CSSProperties = {
  background: 'rgba(13, 23, 40, 0.92)',
  border: '1px solid rgba(68, 136, 255, 0.12)',
  borderRadius: 20,
  padding: '24px 16px 20px',
  backdropFilter: 'blur(16px)',
  boxShadow: '0 8px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 16,
  padding: '0 4px',
};

const titleStyle: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 700,
  color: '#e0eaff',
  letterSpacing: '0.02em',
  fontFamily: 'Space Grotesk, Inter, system-ui, sans-serif',
};

const dominanceBadgeStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  padding: '4px 10px',
  borderRadius: 20,
  background: 'rgba(68, 136, 255, 0.15)',
  color: '#6eaaff',
  letterSpacing: '0.04em',
  fontFamily: 'Space Grotesk, Inter, system-ui, sans-serif',
};

/* ── Tooltip ──────────────────────────────────────────────────────────── */

interface TooltipData {
  name: string;
  percentage: number;
  isPrimary: boolean;
  x: number;
  y: number;
}

function MuscleTooltip({ data }: { data: TooltipData | null }) {
  if (!data) return null;
  const color = activationColor(data.percentage);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.92 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.92 }}
      transition={{ duration: 0.15 }}
      style={{
        position: 'absolute',
        left: data.x,
        top: data.y,
        transform: 'translate(-50%, -120%)',
        background: 'rgba(10, 16, 28, 0.96)',
        border: `1px solid ${color}`,
        borderRadius: 12,
        padding: '10px 14px',
        zIndex: 100,
        pointerEvents: 'none',
        minWidth: 140,
        boxShadow: `0 4px 24px rgba(0,0,0,0.5), 0 0 16px ${activationGlow(data.percentage)}`,
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 700, color: '#e0eaff', marginBottom: 4, fontFamily: 'Space Grotesk, Inter, sans-serif' }}>
        {data.name}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          flex: 1, height: 6, borderRadius: 3,
          background: 'rgba(255,255,255,0.08)',
          overflow: 'hidden',
        }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${data.percentage}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            style={{ height: '100%', borderRadius: 3, background: color }}
          />
        </div>
        <span style={{ fontSize: 13, fontWeight: 700, color, fontFamily: 'Space Grotesk, Inter, sans-serif' }}>
          {data.percentage}%
        </span>
      </div>
      <div style={{
        fontSize: 10, marginTop: 4, color: data.isPrimary ? '#6eaaff' : '#667799',
        fontWeight: 500, fontFamily: 'Space Grotesk, Inter, sans-serif',
      }}>
        {data.isPrimary ? '● Primary Mover' : '○ Stabilizer'}
      </div>
    </motion.div>
  );
}

/* ── Activation Legend ─────────────────────────────────────────────────── */

function ActivationLegend() {
  const stops = [0, 20, 40, 60, 80, 100];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 4px 0' }}>
      <span style={{ fontSize: 10, color: '#556688', fontFamily: 'Space Grotesk, Inter, sans-serif' }}>0%</span>
      <div style={{
        flex: 1, height: 6, borderRadius: 3, overflow: 'hidden',
        background: `linear-gradient(to right, ${stops.map(s => activationColor(s)).join(', ')})`,
      }} />
      <span style={{ fontSize: 10, color: '#556688', fontFamily: 'Space Grotesk, Inter, sans-serif' }}>100%</span>
    </div>
  );
}

/* ── View Toggle ──────────────────────────────────────────────────────── */

function ViewToggle({ view, onToggle }: { view: 'front' | 'back'; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 14px',
        borderRadius: 20,
        border: '1px solid rgba(68, 136, 255, 0.2)',
        background: 'rgba(68, 136, 255, 0.08)',
        color: '#6eaaff',
        fontSize: 12,
        fontWeight: 600,
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        fontFamily: 'Space Grotesk, Inter, sans-serif',
      }}
      onMouseEnter={e => {
        (e.target as HTMLButtonElement).style.background = 'rgba(68, 136, 255, 0.18)';
      }}
      onMouseLeave={e => {
        (e.target as HTMLButtonElement).style.background = 'rgba(68, 136, 255, 0.08)';
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M7 16l-4-4 4-4M17 8l4 4-4 4M14 4l-4 16" />
      </svg>
      {view === 'front' ? 'Show Back' : 'Show Front'}
    </button>
  );
}

/* ── Muscle SVG Layer ─────────────────────────────────────────────────── */

interface MuscleSVGProps {
  musclePaths: MusclePath[];
  activationMap: Map<string, MuscleActivation>;
  onHover: (slug: string | null, e?: React.MouseEvent) => void;
  hoveredSlug: string | null;
}

function MuscleSVG({ musclePaths, activationMap, onHover, hoveredSlug }: MuscleSVGProps) {
  return (
    <svg
      viewBox={VIEWBOX}
      style={{ width: '100%', height: 'auto', maxHeight: 380 }}
    >
      {/* Body outline silhouette (very faint) */}
      <defs>
        <filter id="muscle-glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="muscle-glow-strong">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Render each muscle group */}
      {musclePaths.map(muscle => {
        const activation = activationMap.get(muscle.id);
        const pct = activation?.percentage ?? 0;
        const isActive = pct > 0;
        const isHovered = hoveredSlug === muscle.id;
        const fillColor = isActive ? activationColor(pct) : 'rgba(30, 45, 65, 0.4)';
        const strokeColor = isActive ? activationColor(pct) : 'rgba(60, 80, 110, 0.3)';
        const opacity = isActive ? (0.5 + pct / 200) : 0.3;

        return (
          <g
            key={muscle.id}
            onMouseEnter={(e) => onHover(muscle.id, e)}
            onMouseLeave={() => onHover(null)}
            style={{ cursor: isActive ? 'pointer' : 'default', transition: 'all 0.3s ease' }}
          >
            {muscle.paths.map((d, i) => (
              <path
                key={`${muscle.id}-${i}`}
                d={d}
                fill={fillColor}
                fillOpacity={isHovered && isActive ? Math.min(opacity + 0.2, 1) : opacity}
                stroke={isHovered && isActive ? '#fff' : strokeColor}
                strokeWidth={isHovered && isActive ? 1.5 : 0.8}
                strokeOpacity={isActive ? 0.8 : 0.4}
                filter={isActive && pct > 50 ? 'url(#muscle-glow)' : undefined}
                style={{
                  transition: 'all 0.3s ease',
                  transform: isHovered && isActive ? 'scale(1.02)' : 'scale(1)',
                  transformOrigin: 'center',
                }}
              />
            ))}

            {/* Percentage label for active muscles */}
            {isActive && pct > 15 && (
              (() => {
                // Calculate approximate center of the muscle paths
                const allPaths = muscle.paths.join(' ');
                const coords = allPaths.match(/[\d.]+/g)?.map(Number) || [];
                let cx = 100, cy = 200;
                if (coords.length >= 4) {
                  const xs = coords.filter((_, i) => i % 2 === 0);
                  const ys = coords.filter((_, i) => i % 2 === 1);
                  cx = xs.reduce((a, b) => a + b, 0) / xs.length;
                  cy = ys.reduce((a, b) => a + b, 0) / ys.length;
                }
                return (
                  <text
                    x={cx}
                    y={cy + 2}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill="#fff"
                    fontSize={pct > 60 ? 9 : 7.5}
                    fontWeight={pct > 60 ? 700 : 600}
                    fontFamily="Space Grotesk, Inter, sans-serif"
                    style={{
                      pointerEvents: 'none',
                      textShadow: `0 1px 4px rgba(0,0,0,0.8)`,
                      opacity: isHovered ? 1 : 0.85,
                    }}
                  >
                    {pct}%
                  </text>
                );
              })()
            )}
          </g>
        );
      })}
    </svg>
  );
}

/* ── Active Muscles List ──────────────────────────────────────────────── */

function ActiveMusclesList({ muscles }: { muscles: MuscleActivation[] }) {
  const sorted = [...muscles].sort((a, b) => b.percentage - a.percentage);
  return (
    <div style={{ marginTop: 12, padding: '0 4px' }}>
      {sorted.map(m => {
        const color = activationColor(m.percentage);
        return (
          <div key={m.slug} style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: color,
              boxShadow: `0 0 6px ${activationGlow(m.percentage)}`,
              flexShrink: 0,
            }} />
            <span style={{
              fontSize: 11.5, color: '#c0d0e8', flex: 1,
              fontFamily: 'Space Grotesk, Inter, sans-serif',
              fontWeight: 500,
            }}>
              {m.name}
              {!m.isPrimary && (
                <span style={{ color: '#556688', fontSize: 10, marginLeft: 4 }}>(stabilizer)</span>
              )}
            </span>
            <div style={{
              width: 60, height: 5, borderRadius: 3,
              background: 'rgba(255,255,255,0.06)', overflow: 'hidden',
            }}>
              <div style={{
                width: `${m.percentage}%`, height: '100%',
                borderRadius: 3, background: color,
                transition: 'width 0.6s ease',
              }} />
            </div>
            <span style={{
              fontSize: 12, fontWeight: 700, color,
              width: 34, textAlign: 'right',
              fontFamily: 'Space Grotesk, Inter, sans-serif',
            }}>
              {m.percentage}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ── Main MuscleMap Component ─────────────────────────────────────────── */

interface MuscleMapProps {
  data: MuscleActivationData;
}

export function MuscleMap({ data }: MuscleMapProps) {
  const [view, setView] = useState<'front' | 'back'>('front');
  const [hoveredSlug, setHoveredSlug] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  const activationMap = useMemo(() => {
    const map = new Map<string, MuscleActivation>();
    data.muscles.forEach(m => map.set(m.slug, m));
    return map;
  }, [data.muscles]);

  const handleHover = useCallback((slug: string | null, e?: React.MouseEvent) => {
    setHoveredSlug(slug);
    if (slug && e) {
      const activation = activationMap.get(slug);
      if (activation && activation.percentage > 0) {
        const rect = (e.currentTarget as Element).closest('div')?.getBoundingClientRect();
        const svgRect = (e.currentTarget as Element).closest('svg')?.getBoundingClientRect();
        if (rect && svgRect) {
          setTooltip({
            name: activation.name,
            percentage: activation.percentage,
            isPrimary: activation.isPrimary,
            x: e.clientX - rect.left,
            y: svgRect.top - rect.top + 10,
          });
        }
      }
    } else {
      setTooltip(null);
    }
  }, [activationMap]);

  const toggleView = useCallback(() => {
    setView(v => v === 'front' ? 'back' : 'front');
    setTooltip(null);
    setHoveredSlug(null);
  }, []);

  const currentPaths = view === 'front' ? FRONT_MUSCLES : BACK_MUSCLES;

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <div>
            <div style={titleStyle}>Muscle Activation Map</div>
            <div style={{ fontSize: 10, color: '#556688', marginTop: 2, fontFamily: 'Space Grotesk, Inter, sans-serif' }}>
              Estimated from kinematics · Not EMG
            </div>
          </div>
          <ViewToggle view={view} onToggle={toggleView} />
        </div>

        {/* Dominance badge */}
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
          <div style={dominanceBadgeStyle}>
            {data.dominance}
          </div>
        </div>

        {/* Card-flip animation container */}
        <div style={{
          position: 'relative',
          perspective: 1000,
          minHeight: 340,
        }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={view}
              initial={{ rotateY: view === 'front' ? -90 : 90, opacity: 0 }}
              animate={{ rotateY: 0, opacity: 1 }}
              exit={{ rotateY: view === 'front' ? 90 : -90, opacity: 0 }}
              transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
              style={{
                transformStyle: 'preserve-3d',
                backfaceVisibility: 'hidden',
              }}
            >
              {/* View label */}
              <div style={{
                textAlign: 'center', fontSize: 10, fontWeight: 700,
                color: '#4488ff', letterSpacing: '0.12em',
                textTransform: 'uppercase', marginBottom: 4,
                fontFamily: 'Space Grotesk, Inter, sans-serif',
              }}>
                {view === 'front' ? '◇ Anterior View' : '◆ Posterior View'}
              </div>

              <MuscleSVG
                musclePaths={currentPaths}
                activationMap={activationMap}
                onHover={handleHover}
                hoveredSlug={hoveredSlug}
              />
            </motion.div>
          </AnimatePresence>

          {/* Tooltip overlay */}
          <AnimatePresence>
            {tooltip && <MuscleTooltip data={tooltip} />}
          </AnimatePresence>
        </div>

        {/* Legend gradient */}
        <ActivationLegend />

        {/* Active muscles list */}
        <ActiveMusclesList muscles={data.muscles} />
      </div>
    </div>
  );
}

export default MuscleMap;
