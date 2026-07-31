import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowLeft, Menu, X } from 'lucide-react';
import { C, F, R } from '../../theme/tokens';
import { Breadcrumbs, type Crumb } from '../ui/Breadcrumbs';
import { Logo } from '../ui/Logo';

interface NavProps {
  /** Optional middle-of-nav title (overridden by breadcrumbs when present). */
  exerciseName?: string;
  /** Optional step indicator. Renders as a small pill on the right side. */
  step?: number;
  totalSteps?: number;
  /** Back arrow handler. Renders nothing if absent. */
  onBack?: () => void;
  backLabel?: string;
  /** Optional breadcrumb trail (replaces the centered exercise name). */
  crumbs?: Crumb[];
  /** Optional right-aligned action slot (e.g. "Skip", "Save"). */
  rightSlot?: ReactNode;
  /** Click handler for the wordmark — usually go to landing. */
  onLogo?: () => void;
}

/**
 * Sticky top navigation with three slots: brand (left), breadcrumbs / title
 * (centre), action (right). Always-visible — calms the user, makes the app
 * feel like an environment rather than a series of disconnected pages.
 */
export function Nav({
  exerciseName, step, totalSteps,
  onBack, backLabel,
  crumbs,
  rightSlot,
  onLogo,
}: NavProps) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <nav style={{
      position: 'sticky',
      top: 0, left: 0, right: 0,
      zIndex: 80,
      background: scrolled ? 'rgba(10,13,16,0.92)' : 'rgba(10,13,16,0.80)',
      backdropFilter: 'blur(12px) saturate(140%)',
      WebkitBackdropFilter: 'blur(12px) saturate(140%)',
      borderBottom: `1px solid ${C.border}`,
      transition: 'background 240ms ease, border-color 240ms ease',
    }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(180px,1fr) auto minmax(180px,1fr)',
        alignItems: 'center',
        gap: 24,
        height: 64,
        padding: '0 32px',
        maxWidth: 1400,
        margin: '0 auto',
      }}>
        {/* ── Left: brand + optional back */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {onBack && (
            <button
              onClick={onBack}
              aria-label={backLabel || 'Back'}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: 'transparent',
                border: `1px solid ${C.border}`,
                borderRadius: R.pill,
                padding: '6px 12px 6px 10px',
                color: C.ink2,
                fontFamily: F.body,
                fontSize: 12.5,
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'background 180ms, color 180ms, border-color 180ms',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = C.taupe;
                e.currentTarget.style.color = C.ink;
                e.currentTarget.style.borderColor = C.borderStrong;
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = C.ink3;
                e.currentTarget.style.borderColor = C.border;
              }}>
              <ArrowLeft size={14} strokeWidth={2} />
              <span>{backLabel || 'Back'}</span>
            </button>
          )}
          <Logo size={22} onClick={onLogo} />
        </div>

        {/* ── Centre: breadcrumbs or exercise name */}
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, minWidth: 0 }}>
          {crumbs ? (
            <Breadcrumbs items={crumbs} />
          ) : exerciseName ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{
                fontFamily: F.body, fontSize: 13, fontWeight: 500,
                color: C.ink, letterSpacing: '0.02em',
              }}>{exerciseName}</span>
              {step && totalSteps && (
                <span style={{
                  background: C.clayTint,
                  color: C.clay,
                  border: `1px solid ${C.borderClay}`,
                  padding: '2px 10px',
                  borderRadius: R.pill,
                  fontFamily: F.body, fontSize: 10.5, fontWeight: 600,
                  letterSpacing: '0.12em',
                }}>STEP {step} / {totalSteps}</span>
              )}
            </div>
          ) : null}
        </div>

        {/* ── Right: optional action slot */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10 }}>
          {rightSlot}
        </div>
      </div>
    </nav>
  );
}

/**
 * Step progress bar — horizontal segments for multi-exercise flows.
 * Visually subtle so the user can focus on the active step.
 */
export function ExerciseProgressBar({
  current, total, completed,
}: { current: number; total: number; completed: Set<number> }) {
  return (
    <div style={{
      display: 'flex', gap: 6, padding: '14px 32px',
      background: C.surface2,
      borderBottom: `1px solid ${C.border}`,
    }}>
      {Array.from({ length: total }, (_, i) => {
        const num = i + 1;
        const done = completed.has(num);
        const active = num === current;
        return (
          <div key={i} style={{
            flex: 1,
            height: 3,
            borderRadius: 2,
            background: done ? C.clay : active ? C.clay : C.taupe,
            opacity: done ? 0.85 : active ? 1 : 0.55,
            transition: 'background 280ms, opacity 280ms',
          }} />
        );
      })}
    </div>
  );
}

/**
 * Decorative line-drawing of a stick figure. Used in empty states and
 * loading screens — restrained and editorial.
 */
export function SkeletonViz({ size = 220, color = C.clay }: { size?: number; color?: string }) {
  const nodes = [[50,8],[50,20],[50,30],[35,28],[20,38],[8,48],[65,28],[80,38],[92,48],[44,42],[56,42],[42,58],[40,74],[38,88],[58,58],[60,74],[62,88]];
  const bones = [[0,1],[1,2],[2,3],[3,4],[4,5],[2,6],[6,7],[7,8],[2,9],[2,10],[9,10],[9,11],[11,12],[12,13],[10,14],[14,15],[15,16]];
  return (
    <svg viewBox="0 0 100 96" width={size} height={size * 96/100} style={{ overflow:'visible' }}>
      <ellipse cx="50" cy="92" rx="22" ry="3" fill={color} opacity={0.10} />
      {bones.map(([a,b], i) => (
        <line key={i} x1={nodes[a][0]} y1={nodes[a][1]} x2={nodes[b][0]} y2={nodes[b][1]}
          stroke={color} strokeOpacity={0.35} strokeWidth="1.2" strokeLinecap="round" />
      ))}
      {nodes.map(([x,y], i) => (
        <g key={i}>
          <circle cx={x} cy={y} r={i===0?3:1.8} fill="none" stroke={color} strokeWidth="1.2" />
          <circle cx={x} cy={y} r={i===0?1.2:0.6} fill={color} />
        </g>
      ))}
    </svg>
  );
}

/**
 * Floating menu toggle — used on Landing when no other nav action makes sense.
 * Tiny editorial overflow icon.
 */
export function MenuToggle({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-label="Menu" style={{
      background: 'transparent', border: `1px solid ${C.border}`,
      borderRadius: R.pill, padding: 8, color: C.ink, cursor: 'pointer',
    }}>
      {open ? <X size={16} /> : <Menu size={16} />}
    </button>
  );
}
