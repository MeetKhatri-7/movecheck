import { useState } from 'react';
import { Nav } from '@/components/shared';
import { assessmentLabel, type AssessmentType } from '@/data/registry';
import type { Exercise } from '@/data/types';
import {
  Button, Pill, SectionLabel, Display, Stat, EmptyState,
} from '@/components/ui';
import { ArrowBadge } from '@/components/ui/Button';
import { C, F, R } from '@/theme/tokens';
import {
  Check, ArrowRight, Move, Footprints, ChevronsUpDown, Activity,
} from 'lucide-react';

/** Per-category icon + accent colour — drives the card header rhythm. */
function categoryStyle(category: string): { Icon: React.ComponentType<any>; color: string } {
  const c = category.toLowerCase();
  if (c.includes('upper')) return { Icon: Move, color: C.indigo };
  if (c.includes('core'))  return { Icon: ChevronsUpDown, color: C.violet };
  if (c.includes('lower')) return { Icon: Footprints, color: C.clay };
  return { Icon: Activity, color: C.clay };
}

interface Props {
  assessmentType: AssessmentType;
  exercises: Exercise[];
  onSelect: (slug: string) => void;
  completed: Set<string>;
  reports?: Record<string, any>;
  onBack: () => void;
  onDashboard?: () => void;
  onSession?: () => void;
}

export function ExerciseGuide({
  assessmentType, exercises, onSelect, completed, reports, onBack, onDashboard, onSession,
}: Props) {
  const [hov, setHov] = useState<string | null>(null);
  const totalVideos = exercises.reduce((s, e) => s + e.uploads.length, 0);
  const hasReports = reports && Object.keys(reports).length > 0;
  const heading = assessmentLabel(assessmentType);
  const progress = exercises.length ? (completed.size / exercises.length) * 100 : 0;

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.ink, paddingBottom: 96 }}>
      <Nav
        onBack={onBack} backLabel="Home"
        crumbs={[{ label: 'Home', to: onBack }, { label: heading }]}
        rightSlot={(
          <>
            {onSession && <Button variant="ghost" size="sm" onClick={onSession}>Session</Button>}
            {hasReports && onDashboard && (
              <Button variant="primary" size="sm" onClick={onDashboard} iconRight={<ArrowBadge size={26} />} style={{ paddingRight: 5 }}>
                Dashboard
              </Button>
            )}
          </>
        )}
      />

      {/* ── Header ─────────────────────────────────── */}
      <div style={{ maxWidth: 1280, margin: '0 auto', padding: '48px clamp(20px,4vw,40px) 24px' }}>
        <div className="animate-fade-up" style={{
          display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) auto',
          gap: 40, alignItems: 'flex-end',
        }} >
          <div>
            <SectionLabel style={{ marginBottom: 14 }}>
              {heading} assessment · protocol
            </SectionLabel>
            <Display size="h1" style={{ textTransform: 'uppercase' }}>
              {exercises.length} exercise{exercises.length !== 1 ? 's' : ''}, <em>one honest report.</em>
            </Display>
            <p style={{ marginTop: 12, color: C.ink3, fontSize: 15, maxWidth: 560 }}>
              {exercises.length === 0
                ? `No ${heading.toLowerCase()} exercises configured yet — check back soon.`
                : `Select any exercise to begin. Complete all ${exercises.length} for your full ${heading.toLowerCase()} profile.`}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
            <Stat label="Exercises" value={exercises.length} align="center" />
            <Stat label="Videos" value={totalVideos} align="center" />
            <Stat label="Completed" value={completed.size} accent={C.clay} align="center" />
          </div>
        </div>

        {/* Progress bar */}
        {exercises.length > 0 && (
          <div className="animate-fade-up-1" style={{ marginTop: 36 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <SectionLabel style={{ color: C.ink4 }}>Overall progress</SectionLabel>
              <span style={{ fontFamily: F.body, fontSize: 11, fontWeight: 700, color: C.clay, letterSpacing: '0.05em' }}>
                {Math.round(progress)}%
              </span>
            </div>
            <div style={{ height: 6, background: C.taupe, borderRadius: 4, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 4,
                background: `linear-gradient(90deg, ${C.clay}, ${C.clayHover})`,
                width: `${progress}%`,
                transition: 'width 700ms cubic-bezier(.16,1,.3,1)',
              }} />
            </div>
          </div>
        )}
      </div>

      {/* ── Exercise grid ─────────────────────────────── */}
      <div style={{ maxWidth: 1280, margin: '0 auto', padding: '20px clamp(20px,4vw,40px) 32px' }}>
        {exercises.length === 0 ? (
          <EmptyState
            kicker="Coming soon"
            title={<>The {heading.toLowerCase()} battery is being built.</>}
            body="The plumbing is ready — exercises will appear here once they're configured."
          />
        ) : (
          <div className="animate-fade-up-2" style={{
            display: 'grid', gap: 20,
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          }}>
            {exercises.map(ex => {
              const isDone = completed.has(ex.slug);
              const isHov = hov === ex.slug;
              const { Icon, color } = categoryStyle(ex.category);
              return (
                <button
                  key={ex.id}
                  onClick={() => onSelect(ex.slug)}
                  onMouseEnter={() => setHov(ex.slug)}
                  onMouseLeave={() => setHov(null)}
                  style={{
                    textAlign: 'left', background: C.surface,
                    backdropFilter: C.glassBlur, WebkitBackdropFilter: C.glassBlur,
                    border: `1px solid ${isHov ? C.borderClay : C.border}`,
                    borderRadius: R.xl, padding: 0, overflow: 'hidden', cursor: 'pointer',
                    transition: 'transform 260ms ease, box-shadow 260ms ease, border-color 260ms ease',
                    transform: isHov ? 'translateY(-6px)' : 'translateY(0)',
                    boxShadow: isHov ? '0 16px 40px rgba(0,0,0,0.35)' : 'none',
                    position: 'relative',
                    display: 'flex', flexDirection: 'column', height: '100%',
                  }}>
                  {/* Exercise photo header */}
                  <div style={{
                    position: 'relative', aspectRatio: '16/9', flexShrink: 0,
                    borderBottom: `1px solid ${C.border}`,
                    overflow: 'hidden',
                  }}>
                    <img
                      src={`/images/exercises/${ex.slug}.jpg`} alt={ex.name}
                      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                    />
                    {isDone && (
                      <span style={{
                        position: 'absolute', top: 12, right: 12, width: 26, height: 26, borderRadius: 13,
                        background: C.sage, color: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        zIndex: 1,
                      }} aria-label="Completed"><Check size={14} strokeWidth={3} /></span>
                    )}
                  </div>

                  <div style={{ padding: 20, flex: 1, display: 'flex', flexDirection: 'column' }}>
                    {/* Title row — reserves 2 lines so every subtitle lands on the same baseline */}
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8, minHeight: 40 }}>
                      <Icon size={16} strokeWidth={1.8} color={color} style={{ flexShrink: 0, marginTop: 2 }} />
                      <span style={{
                        fontWeight: 700, fontSize: 15, color: C.ink, minWidth: 0, flex: 1, lineHeight: 1.3,
                        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                      }}>{ex.name}</span>
                      <ArrowRight size={18} strokeWidth={1.6} style={{
                        color: C.clay, opacity: isHov ? 1 : 0.35, flexShrink: 0, marginTop: 1,
                        transform: isHov ? 'translateX(2px)' : 'translateX(0)',
                        transition: 'transform 220ms ease, opacity 220ms ease',
                      }} />
                    </div>
                    <div style={{ fontSize: 12, color: C.ink4, marginBottom: 10, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}>{ex.subtitle}</div>
                    {/* Description — clamped to 3 lines for a uniform block height */}
                    <p style={{
                      margin: '0 0 14px', fontSize: 13, color: C.ink3, lineHeight: 1.6, minHeight: 62,
                      display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                    }}>{ex.description}</p>
                    {/* Pills pinned to the card floor — aligned across the whole grid */}
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 'auto' }}>
                      <Pill tone="neutral" size="xs" uppercase={false}>{ex.difficulty}</Pill>
                      <Pill tone="neutral" size="xs" uppercase={false}>{ex.uploads.length} video{ex.uploads.length !== 1 ? 's' : ''}</Pill>
                      <Pill tone="neutral" size="xs" uppercase={false}>{ex.duration}</Pill>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Bottom dashboard CTA ───────────────────────── */}
      {hasReports && onDashboard && (
        <div className="animate-fade-up-3" style={{
          maxWidth: 1280, margin: '32px auto 0', padding: '44px clamp(20px,4vw,40px) 0',
          borderTop: `1px solid ${C.border}`, textAlign: 'center',
        }}>
          <SectionLabel style={{ marginBottom: 14, color: C.ink4 }}>Already analysed</SectionLabel>
          <p style={{ margin: '0 auto 24px', maxWidth: 480, color: C.ink3, fontSize: 16, lineHeight: 1.7 }}>
            You've finished {completed.size} of {exercises.length} exercises. View your aggregated report any time.
          </p>
          <Button variant="primary" size="lg" onClick={onDashboard} iconRight={<ArrowBadge />} style={{ paddingRight: 8 }}>
            OPEN DASHBOARD
          </Button>
        </div>
      )}
    </div>
  );
}