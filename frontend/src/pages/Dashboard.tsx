import { useEffect, useMemo, useState } from 'react';
import { Nav } from '@/components/shared';
import { assessmentLabel, type AssessmentType } from '@/data/registry';
import type { AnnotatedFrame, Exercise } from '@/data/types';
import {
  Button, Card, Pill, SectionLabel, Display, Stat, EmptyState, Skeleton, IconBadge,
} from '@/components/ui';
import { ArrowBadge } from '@/components/ui/Button';
import { C, F, R } from '@/theme/tokens';
import { useKeyboard } from '@/hooks/useKeyboard';
import { ListChecks, Trophy, AlertTriangle, Sparkles, Target, Flame } from 'lucide-react';

interface Props {
  assessmentType: AssessmentType;
  exercises: Exercise[];
  reports: Record<string, any>;
  onOpenReport: (slug: string) => void;
  onGuide: () => void;
  onLanding: () => void;
  onSession?: () => void;
}

function gradeFromScore(score: number): { label: string; tone: 'good' | 'warn' | 'bad'; status: string; color: string } {
  if (score >= 85) return { label: 'A', tone: 'good', status: 'EXCELLENT',   color: C.sage };
  if (score >= 70) return { label: 'B', tone: 'good', status: 'GOOD',        color: C.sage };
  if (score >= 55) return { label: 'C', tone: 'warn', status: 'NEEDS WORK',  color: C.amber };
  return            { label: 'D', tone: 'bad',  status: 'RESTRICTED',  color: C.rust };
}

/* ── Overall score gauge ───────────────────────────────────── */
function OverallGauge({ score, ready }: { score: number; ready: boolean }) {
  const radius = 84;
  const circ = 2 * Math.PI * radius;
  const arc = circ * 0.75;
  const offset = arc - arc * (ready ? score / 100 : 0);
  const g = gradeFromScore(score);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <svg width="208" height="208" viewBox="0 0 208 208">
        <circle cx="104" cy="104" r={radius} fill="none"
          stroke={C.taupe} strokeWidth="9"
          strokeDasharray={`${arc} ${circ - arc}`}
          strokeDashoffset={circ * 0.125} strokeLinecap="round"
          transform="rotate(135 104 104)" />
        <circle cx="104" cy="104" r={radius} fill="none"
          stroke={g.color} strokeWidth="9"
          strokeDasharray={`${arc} ${circ - arc}`}
          strokeDashoffset={circ * 0.125 + offset} strokeLinecap="round"
          transform="rotate(135 104 104)"
          style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(.16,1,.3,1)' }} />
        <text x="104" y="100" textAnchor="middle"
          fontFamily={F.display} fontSize="62" fill={C.ink}>
          {ready ? score : 0}
        </text>
        <text x="104" y="124" textAnchor="middle"
          fontFamily={F.body} fontSize="10" fill={C.ink3} letterSpacing="3">
          OUT OF 100
        </text>
      </svg>
      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          width: 44, height: 44, borderRadius: R.md,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: g.color, color: C.bg,
          fontFamily: F.display, fontSize: 22,
        }}>{g.label}</span>
        <span style={{ fontFamily: F.body, fontSize: 11.5, letterSpacing: '0.16em',
          textTransform: 'uppercase', color: C.ink3 }}>
          {g.status}
        </span>
      </div>
    </div>
  );
}

/* ── Skeleton frame thumb (clickable) ─────────────────────── */
function FrameThumb({ frame, onOpen }: { frame: AnnotatedFrame; onOpen: () => void }) {
  return (
    <button onClick={onOpen} style={{
      width: 200, padding: 0,
      background: C.surface2,
      border: frame.is_best ? `1.5px solid ${C.clay}` : `1px solid ${C.border}`,
      borderRadius: R.lg, overflow: 'hidden', cursor: 'pointer',
      transition: 'transform 220ms ease, box-shadow 220ms ease',
      textAlign: 'left',
    }}
      onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.boxShadow = '0 12px 28px rgba(0,0,0,0.4)'; }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)';  e.currentTarget.style.boxShadow = 'none'; }}>
      <img src={frame.image_base64} alt={frame.label}
        style={{ width: '100%', height: 130, objectFit: 'cover', display: 'block' }} />
      <div style={{ padding: '8px 12px', background: C.surface,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontFamily: F.body, fontSize: 12.5, fontWeight: 500, color: C.ink }}>
          {frame.label}
        </span>
        {frame.is_best && <Pill tone="clay" size="xs">Best</Pill>}
      </div>
    </button>
  );
}

/* ── Per-exercise card ────────────────────────────────────── */
function ExerciseCard({ ex, report, onOpen, onFrame }: {
  ex: Exercise; report: any; onOpen: () => void; onFrame: (f: AnnotatedFrame) => void;
}) {
  const g = gradeFromScore(report.score);
  const frames: AnnotatedFrame[] = report.annotated_frames || [];
  const bySide: Record<string, AnnotatedFrame> = {};
  for (const f of frames) {
    const k = f.side || 'center';
    if (!bySide[k] || (f.is_best && !bySide[k].is_best)) bySide[k] = f;
  }
  const bestFrames = Object.values(bySide);

  return (
    <Card pad={0} accent={g.tone === 'good' ? 'sage' : g.tone === 'warn' ? 'amber' : 'rust'}>
      {/* Header */}
      <div style={{
        padding: '24px 28px 18px',
        display: 'flex', alignItems: 'flex-start', gap: 18,
        borderBottom: `1px solid ${C.border}`,
      }}>
        <div style={{
          width: 48, height: 48, borderRadius: R.md,
          background: C.surface2, color: C.clay,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: F.display, fontSize: 22, flexShrink: 0,
        }}>{ex.id}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: F.display, fontSize: 22, color: C.ink,
            letterSpacing: '-0.01em', lineHeight: 1.15 }}>
            {ex.name}
          </div>
          <SectionLabel style={{ marginTop: 4 }}>{ex.subtitle}</SectionLabel>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontFamily: F.display, fontSize: 38, color: g.color, lineHeight: 1 }}>
            {report.score}
          </div>
          <SectionLabel style={{ marginTop: 4 }}>Score · {g.label}</SectionLabel>
        </div>
      </div>

      {/* Status + meta */}
      <div style={{
        padding: '14px 28px', display: 'flex', flexWrap: 'wrap', gap: 12,
        alignItems: 'center', justifyContent: 'space-between',
        borderBottom: `1px solid ${C.border}`,
      }}>
        <Pill tone={g.tone} size="sm">{report.status}</Pill>
        <span style={{ fontFamily: F.body, fontSize: 12, color: C.ink3 }}>
          {report.stats?.validReps && <>{report.stats.validReps} reps</>}
          {report.stats?.confidence && <> · {report.stats.confidence} confidence</>}
        </span>
      </div>

      {/* Frames */}
      {bestFrames.length > 0 && (
        <div style={{ padding: '20px 28px 12px' }}>
          <SectionLabel style={{ marginBottom: 10 }}>
            {bestFrames.length > 1 ? 'Best rep · each side' : 'Best rep'}
          </SectionLabel>
          <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 4 }}>
            {bestFrames.map((f, i) => (
              <FrameThumb key={i} frame={f} onOpen={() => onFrame(f)} />
            ))}
          </div>
        </div>
      )}

      {/* Coaching */}
      {report.coaching && report.coaching.length > 0 && (
        <div style={{ padding: '14px 28px 8px' }}>
          <SectionLabel style={{ marginBottom: 10 }}>Coaching · top notes</SectionLabel>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {report.coaching.slice(0, 3).map((note: string, i: number) => (
              <li key={i} style={{
                display: 'flex', gap: 12, alignItems: 'flex-start',
                padding: 12, borderRadius: R.md,
                background: C.surface2,
              }}>
                <span style={{
                  flexShrink: 0, width: 6, height: 6, borderRadius: '50%',
                  background: i === 0 ? C.clay : C.sage, marginTop: 7,
                }} />
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: C.ink2 }}>{note}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Open */}
      <div style={{ padding: '14px 28px 24px' }}>
        <Button variant="secondary" size="md" block onClick={onOpen}
          iconRight={<span style={{ fontSize: 16 }}>→</span>}>
          Open full report
        </Button>
      </div>
    </Card>
  );
}

/* ── Frame modal ─────────────────────────────────────────── */
function FrameModal({ frame, onClose }: { frame: AnnotatedFrame; onClose: () => void }) {
  useKeyboard({ onEscape: onClose });
  return (
    <div onClick={onClose} role="dialog" aria-modal="true" style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(10,13,16,0.82)',
      backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      cursor: 'zoom-out',
      padding: 32,
    }} className="animate-fade-in">
      <div style={{ maxWidth: '92vw', maxHeight: '92vh', position: 'relative' }}>
        <img src={frame.image_base64} alt={frame.label}
          style={{
            maxWidth: '100%', maxHeight: '85vh',
            borderRadius: R.lg, border: `1px solid ${C.border}`,
            boxShadow: '0 24px 60px rgba(0,0,0,0.3)',
          }} />
        <div style={{ textAlign: 'center', marginTop: 14 }}>
          <Pill tone="neutral" size="md">{frame.label}</Pill>
        </div>
        <button onClick={(e) => { e.stopPropagation(); onClose(); }} aria-label="Close"
          style={{
            position: 'absolute', top: -14, right: -14, width: 36, height: 36, borderRadius: 18,
            background: C.bg, border: `1px solid ${C.border}`, color: C.ink,
            fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
          }}>✕</button>
      </div>
    </div>
  );
}

/* ── Main Dashboard ──────────────────────────────────────── */
export function Dashboard({
  assessmentType, exercises, reports, onOpenReport, onGuide, onLanding, onSession,
}: Props) {
  const [ready, setReady] = useState(false);
  const [openFrame, setOpenFrame] = useState<AnnotatedFrame | null>(null);
  const heading = assessmentLabel(assessmentType);

  useEffect(() => { const t = setTimeout(() => setReady(true), 240); return () => clearTimeout(t); }, []);

  // Esc to go back, Enter to continue
  useKeyboard({ onEscape: onLanding, onEnter: onGuide });

  const reportEntries = useMemo(
    () => exercises.filter(ex => reports[ex.slug])
      .map(ex => ({ slug: ex.slug, exercise: ex, report: reports[ex.slug] })),
    [exercises, reports]
  );

  const overallScore = useMemo(() => {
    if (!reportEntries.length) return 0;
    const sum = reportEntries.reduce((s, e) => s + (e.report.score || 0), 0);
    return Math.round(sum / reportEntries.length);
  }, [reportEntries]);

  const overall = gradeFromScore(overallScore);
  const passedCount = reportEntries.filter(e => e.report.status === 'GOOD' || e.report.status === 'PASS').length;

  const toImprove = useMemo(() => [...reportEntries]
    .filter(e => e.report.score < 70)
    .sort((a, b) => a.report.score - b.report.score)
    .slice(0, 3), [reportEntries]);
  const strengths = useMemo(() => [...reportEntries]
    .filter(e => e.report.score >= 80)
    .sort((a, b) => b.report.score - a.report.score)
    .slice(0, 3), [reportEntries]);

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.ink, paddingBottom: 96 }}>
      <Nav
        onBack={onGuide} backLabel="All exercises"
        crumbs={[
          { label: 'Home', to: onLanding },
          { label: heading, to: onGuide },
          { label: 'Dashboard' },
        ]}
        rightSlot={onSession ? (
          <Button variant="ghost" size="sm" onClick={onSession}>Session</Button>
        ) : null}
      />

      {/* ── Banner ──────────────────────────────────────────── */}
      <div style={{
        position: 'relative', height: 200, overflow: 'hidden',
        backgroundImage: `linear-gradient(180deg, rgba(10,13,16,0.35) 0%, ${C.bg} 94%), url(/images/dashboard/banner.jpg)`,
        backgroundSize: 'cover', backgroundPosition: 'center 28%',
        borderBottom: `1px solid ${C.border}`,
      }}>
        <div style={{ maxWidth: 1180, margin: '0 auto', height: '100%', display: 'flex', alignItems: 'flex-end', padding: '0 32px 22px' }}>
          <span style={{ fontFamily: F.body, fontSize: 11.5, letterSpacing: '2.5px', color: C.ink3, fontWeight: 700, textTransform: 'uppercase' }}>
            Coach-grade review · every rep, scored
          </span>
        </div>
      </div>

      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '56px 32px 0' }}>
        {/* ── Header ────────────────────────────────────────── */}
        <div className="animate-fade-up" style={{ marginBottom: 48 }}>
          <SectionLabel style={{ marginBottom: 14 }}>
            {heading} assessment · dashboard
          </SectionLabel>
          <Display size="h1">
            Your full report,<br/>
            in <em>one place.</em>
          </Display>
          <p style={{ marginTop: 14, color: C.ink2, fontSize: 15 }}>
            {reportEntries.length} of {exercises.length} exercises analysed
            {passedCount > 0 && <> · {passedCount} passed</>}.
          </p>
        </div>

        {reportEntries.length === 0 ? (
          <EmptyState
            kicker="Nothing here yet"
            title={<>Record your first exercise to start <em>building your profile.</em></>}
            body="Each exercise takes about 90 seconds to record. The first analyzer run will populate this dashboard automatically."
            ctaLabel="Start first exercise"
            onCta={onGuide}
          />
        ) : (
          <>
            {/* ── Overall card ─────────────────────────────── */}
            <Card pad={0} variant="raised" style={{ marginBottom: 32 }} className="animate-fade-up-1">
              <div style={{
                display: 'grid', gridTemplateColumns: '300px 1fr', gap: 0,
                alignItems: 'stretch',
              }}>
                <div style={{
                  padding: '36px 28px',
                  borderRight: `1px solid ${C.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: C.surface,
                }}>
                  {ready ? <OverallGauge score={overallScore} ready={ready} />
                         : <Skeleton w={208} h={208} radius={208} />}
                </div>
                <div style={{ padding: '36px 36px' }}>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(4, 1fr)',
                    gap: 18,
                    marginBottom: 28,
                  }}>
                    {[
                      { Icon: ListChecks,    tone: 'neutral' as const, label: 'Analysed',   value: `${reportEntries.length} / ${exercises.length}`, accent: undefined },
                      { Icon: Trophy,        tone: 'sage'    as const, label: 'Passed',     value: passedCount,        accent: C.sage },
                      { Icon: AlertTriangle, tone: 'amber'   as const, label: 'To improve', value: toImprove.length,   accent: C.amber },
                      { Icon: Sparkles,      tone: 'clay'    as const, label: 'Strengths',  value: strengths.length,   accent: C.clay },
                    ].map(({ Icon, tone, label, value, accent }) => (
                      <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        <IconBadge tone={tone} size="sm">
                          <Icon size={14} strokeWidth={1.8} />
                        </IconBadge>
                        <Stat label={label} value={value} accent={accent} />
                      </div>
                    ))}
                  </div>
                  <div style={{
                    borderLeft: `2px solid ${overall.color}`,
                    paddingLeft: 18,
                    fontFamily: F.body, fontSize: 14.5, lineHeight: 1.7, color: C.ink2,
                  }}>
                    Your overall {heading.toLowerCase()} score is{' '}
                    <strong style={{ color: overall.color }}>{overallScore} / 100</strong>.{' '}
                    {overallScore >= 80 && `Strong baseline ${heading.toLowerCase()} — focus on maintaining your routine and refining any minor asymmetries.`}
                    {overallScore >= 55 && overallScore < 80 && 'Foundation is in place but several areas need attention. Prioritise the exercises listed below.'}
                    {overallScore < 55 && `Significant gaps detected. Build a daily ${heading.toLowerCase()} routine starting with the lowest-scoring exercises.`}
                  </div>
                </div>
              </div>
            </Card>

            {/* ── To improve / Strengths ─────────────────── */}
            {(toImprove.length > 0 || strengths.length > 0) && (
              <div className="animate-fade-up-2"
                style={{
                  display: 'grid', gap: 18, marginBottom: 32,
                  gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
                }}>
                {toImprove.length > 0 && (
                  <Card variant="raised" accent="rust">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
                      <IconBadge tone="rust" size="sm"><Target size={14} strokeWidth={1.8} /></IconBadge>
                      <SectionLabel>To work on</SectionLabel>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {toImprove.map(e => (
                        <button key={e.slug} onClick={() => onOpenReport(e.slug)}
                          style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            padding: '12px 14px', borderRadius: R.md,
                            background: C.surface2, border: 'none',
                            cursor: 'pointer', textAlign: 'left',
                            transition: 'transform 180ms, background 180ms',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.background = C.rustTint; e.currentTarget.style.transform = 'translateX(2px)'; }}
                          onMouseLeave={e => { e.currentTarget.style.background = C.surface2; e.currentTarget.style.transform = 'translateX(0)'; }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <span style={{ fontFamily: F.display, fontSize: 16, color: C.rust }}>#{e.exercise.id}</span>
                            <span style={{ fontSize: 13.5, color: C.ink }}>{e.exercise.name}</span>
                          </div>
                          <span style={{ fontFamily: F.display, fontSize: 18, color: C.rust }}>{e.report.score}</span>
                        </button>
                      ))}
                    </div>
                  </Card>
                )}
                {strengths.length > 0 && (
                  <Card variant="raised" accent="sage">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
                      <IconBadge tone="sage" size="sm"><Flame size={14} strokeWidth={1.8} /></IconBadge>
                      <SectionLabel>Your strengths</SectionLabel>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {strengths.map(e => (
                        <button key={e.slug} onClick={() => onOpenReport(e.slug)}
                          style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            padding: '12px 14px', borderRadius: R.md,
                            background: C.surface2, border: 'none',
                            cursor: 'pointer', textAlign: 'left',
                            transition: 'transform 180ms, background 180ms',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.background = C.sageTint; e.currentTarget.style.transform = 'translateX(2px)'; }}
                          onMouseLeave={e => { e.currentTarget.style.background = C.surface2; e.currentTarget.style.transform = 'translateX(0)'; }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <span style={{ fontFamily: F.display, fontSize: 16, color: C.sage }}>#{e.exercise.id}</span>
                            <span style={{ fontSize: 13.5, color: C.ink }}>{e.exercise.name}</span>
                          </div>
                          <span style={{ fontFamily: F.display, fontSize: 18, color: C.sage }}>{e.report.score}</span>
                        </button>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            )}

            {/* ── Per-exercise cards ─────────────────────── */}
            <div className="animate-fade-up-3" style={{ marginBottom: 16 }}>
              <SectionLabel>All {heading.toLowerCase()} reports · {reportEntries.length}</SectionLabel>
            </div>
            <div className="animate-fade-up-3"
              style={{ display: 'grid', gap: 20,
                gridTemplateColumns: 'repeat(auto-fit, minmax(440px, 1fr))' }}>
              {reportEntries.map(e => (
                <ExerciseCard key={e.slug} ex={e.exercise} report={e.report}
                  onOpen={() => onOpenReport(e.slug)}
                  onFrame={f => setOpenFrame(f)} />
              ))}
            </div>

            {/* Missing */}
            {reportEntries.length < exercises.length && (
              <Card variant="flat" style={{
                marginTop: 32,
                border: `1px dashed ${C.borderStrong}`,
                background: 'transparent',
              }}>
                <SectionLabel style={{ marginBottom: 14 }}>Not yet analysed</SectionLabel>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 18 }}>
                  {exercises.filter(ex => !reports[ex.slug]).map(ex => (
                    <span key={ex.slug} style={{
                      padding: '4px 12px', borderRadius: R.pill,
                      background: C.surface, border: `1px solid ${C.border}`,
                      fontFamily: F.body, fontSize: 12, color: C.ink2,
                    }}>#{ex.id} · {ex.name}</span>
                  ))}
                </div>
                <Button variant="primary" size="md" onClick={onGuide}
                  iconRight={<ArrowBadge size={30} />} style={{ paddingRight: 6 }}>
                  Continue assessment
                </Button>
              </Card>
            )}
          </>
        )}

        {/* ── Bottom nav ────────────────────────────────── */}
        <div style={{
          marginTop: 56, paddingTop: 28,
          borderTop: `1px solid ${C.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          gap: 12, flexWrap: 'wrap',
        }}>
          <Button variant="ghost" size="md" onClick={onLanding}
            iconLeft={<span style={{ fontSize: 16 }}>←</span>}>
            Home
          </Button>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {onSession && (
              <Button variant="secondary" size="md" onClick={onSession}>
                Session details
              </Button>
            )}
            <Button variant="primary" size="md" onClick={onGuide}
              iconRight={<ArrowBadge size={30} />} style={{ paddingRight: 6 }}>
              All exercises
            </Button>
          </div>
        </div>
      </div>

      {openFrame && <FrameModal frame={openFrame} onClose={() => setOpenFrame(null)} />}
    </div>
  );
}
