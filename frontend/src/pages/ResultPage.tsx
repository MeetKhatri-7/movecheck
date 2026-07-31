import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Nav } from '@/components/shared';
import { PerRepAccordion } from '@/components/shared/PerRepAccordion';
import { MuscleBody } from '@/components/shared/MuscleBody';
import { MetricHistogram } from '@/components/shared/MetricHistogram';
import type {
  Exercise, Metric, BilateralComparison, AnnotatedFrame, MuscleActivationData,
  CompositeScore, GradeLetter,
} from '@/data/types';
import { listExercises, isValidAssessmentType } from '@/data/registry';
import {
  Button, Card, Pill, SectionLabel, Display, IconBadge,
} from '@/components/ui';
import { C, F, R, GUTTER, gridCols, overallStatusColor, statusColor } from '@/theme/tokens';
import { useKeyboard } from '@/hooks/useKeyboard';
import { useIsMobile, useIsNarrow } from '@/hooks/useMediaQuery';
import {
  ShieldAlert, Activity, Zap, TrendingUp, Trophy,
  AlertTriangle, AlertCircle, CheckCircle2, Users,
  ChevronDown, ChevronRight, Maximize2, X, BarChart3,
  Image as ImageIcon, ListChecks, MessageCircle,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────────────────
 * Helpers
 * ──────────────────────────────────────────────────────────────────── */

type Bucket = 'safety' | 'form' | 'performance';

function classifyMetric(name: string): Bucket {
  const n = name.toLowerCase();
  if (/lumbar|spine|spinal|valgus|hyperextens|wink|kip|flare|critical|asymmet|tuck/.test(n)) return 'safety';
  if (/velocity|\bmcv\b|tempo|1rm|epley|brzycki|eccentric|concentric|pause|rom/.test(n)) return 'performance';
  return 'form';
}

const BUCKETS: { key: Bucket; label: string; tone: 'rust'|'clay'|'indigo'; Icon: React.ComponentType<any>; description: string }[] = [
  { key: 'safety',      label: 'Safety',      tone: 'rust',   Icon: ShieldAlert, description: 'Injury-risk signals' },
  { key: 'form',        label: 'Form',        tone: 'clay',   Icon: Activity,    description: 'Technique & alignment' },
  { key: 'performance', label: 'Performance', tone: 'indigo', Icon: Zap,         description: 'Output & velocity' },
];

function synthesizeVerdict(metrics: Metric[]): { wins: string[]; fix: string | null } {
  const passed = metrics.filter(m => m.status === 'good');
  const failed = metrics.filter(m => m.status === 'bad' && m.confidence_tier !== 'low');
  const toPhrase = (m: Metric) =>
    m.name.replace(/\s*\([^)]*\)\s*/g, '').replace(/\s*[·:].*$/, '').trim();
  const winPriority = ['depth', 'bar', 'tempo', 'symmetry', 'lockout', 'spine', 'chin', 'rom'];
  const fixPriority = ['lumbar', 'flare', 'valgus', 'wink', 'kipping', 'heel', 'drift', 'stack'];
  const sortByMatch = (arr: Metric[], keys: string[]) =>
    [...arr].sort((a, b) => {
      const aIdx = keys.findIndex(k => a.name.toLowerCase().includes(k));
      const bIdx = keys.findIndex(k => b.name.toLowerCase().includes(k));
      return (aIdx < 0 ? 999 : aIdx) - (bIdx < 0 ? 999 : bIdx);
    });
  const wins = sortByMatch(passed, winPriority).slice(0, 2).map(toPhrase);
  const fix = failed.length ? sortByMatch(failed, fixPriority)[0] : null;
  return { wins, fix: fix ? toPhrase(fix).toLowerCase() : null };
}

function statusBand(score: number): { band: 'strong' | 'solid' | 'work'; label: string } {
  if (score >= 80) return { band: 'strong', label: 'Strong work' };
  if (score >= 55) return { band: 'solid',  label: 'Solid foundation' };
  return            { band: 'work',   label: 'Work to do' };
}

/* ─────────────────────────────────────────────────────────────────────
 * Inline components
 * ──────────────────────────────────────────────────────────────────── */

function ScoreBadge({ score, ready, status, size = 170 }: {
  score: number; ready: boolean; status: string; size?: number;
}) {
  const radius = 64;
  const circ = 2 * Math.PI * radius;
  const arc = circ * 0.75;
  const offset = arc - arc * (ready ? score / 100 : 0);
  const palette = overallStatusColor(status);
  return (
    <svg width={size} height={size} viewBox="0 0 170 170">
      <circle cx="85" cy="85" r={radius} fill="none"
        stroke={C.taupe} strokeWidth="9"
        strokeDasharray={`${arc} ${circ - arc}`}
        strokeDashoffset={circ * 0.125} strokeLinecap="round"
        transform="rotate(135 85 85)" />
      <circle cx="85" cy="85" r={radius} fill="none"
        stroke={palette.fg} strokeWidth="9"
        strokeDasharray={`${arc} ${circ - arc}`}
        strokeDashoffset={circ * 0.125 + offset} strokeLinecap="round"
        transform="rotate(135 85 85)"
        style={{ transition: 'stroke-dashoffset 1.1s cubic-bezier(.16,1,.3,1)' }} />
      <text x="85" y="86" textAnchor="middle"
        fontFamily={F.display} fontSize="56" fill={C.ink}
        dominantBaseline="middle">{ready ? score : 0}</text>
      <text x="85" y="116" textAnchor="middle"
        fontFamily={F.body} fontWeight="500" fontSize="9.5"
        fill={C.ink3} letterSpacing="2.5">OUT OF 100</text>
    </svg>
  );
}

/** Annotated-frame tile in the gallery grid. */
function FrameTile({ frame, onOpen }: { frame: AnnotatedFrame; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      style={{
        position: 'relative', padding: 0, border: 'none', cursor: 'zoom-in',
        background: C.surface2, borderRadius: R.lg, overflow: 'hidden',
        aspectRatio: '1/1', width: '100%',
        transition: 'transform 220ms ease, box-shadow 220ms ease',
        outline: frame.is_best ? `2px solid ${C.clay}` : 'none',
        outlineOffset: frame.is_best ? -2 : 0,
      }}
      onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.boxShadow = '0 12px 28px rgba(0,0,0,0.4)'; }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)';     e.currentTarget.style.boxShadow = 'none'; }}>
      <img src={frame.image_base64} alt={frame.label}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
      <div style={{
        position: 'absolute', top: 8, left: 8,
        background: 'rgba(10,13,16,0.85)',
        backdropFilter: 'blur(6px)',
        border: `1px solid ${C.border}`,
        borderRadius: R.pill,
        padding: '3px 10px',
        fontFamily: F.body, fontSize: 10.5, fontWeight: 700, color: C.ink,
        letterSpacing: '0.04em',
      }}>{frame.label}</div>
      {frame.is_best && (
        <div style={{ position: 'absolute', top: 8, right: 8 }}>
          <Pill tone="clay" size="xs">★ Best</Pill>
        </div>
      )}
      <div style={{
        position: 'absolute', bottom: 8, right: 8,
        background: 'rgba(10,13,16,0.65)', backdropFilter: 'blur(6px)',
        color: C.ink, width: 24, height: 24, borderRadius: 12,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}><Maximize2 size={10} strokeWidth={2} /></div>
    </button>
  );
}

function FrameLightbox({ frame, onClose }: { frame: AnnotatedFrame; onClose: () => void }) {
  useKeyboard({ onEscape: onClose });
  const isMobile = useIsMobile();
  return (
    <div onClick={onClose} role="dialog" aria-modal="true" style={{
      position: 'fixed', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(10,13,16,0.85)', backdropFilter: 'blur(8px)',
      padding: isMobile ? 14 : 32, cursor: 'zoom-out',
      paddingTop: `max(${isMobile ? 14 : 32}px, env(safe-area-inset-top, 0px))`,
      paddingBottom: `max(${isMobile ? 14 : 32}px, env(safe-area-inset-bottom, 0px))`,
    }} className="animate-fade-in">
      <div onClick={e => e.stopPropagation()} style={{ position: 'relative', maxWidth: '100%', maxHeight: '100%' }}>
        <img src={frame.image_base64} alt={frame.label}
          style={{
            maxWidth: '100%', maxHeight: isMobile ? '76vh' : '85vh',
            borderRadius: R.lg, border: `1px solid ${C.border}`,
            boxShadow: '0 24px 60px rgba(0,0,0,0.3)',
            display: 'block',
          }} />
        <div style={{ textAlign: 'center', marginTop: 14 }}>
          <Pill tone="neutral" size="md">{frame.label}</Pill>
        </div>
        {/* Overhang the close button only where there's room for it — on a
            phone a -14px offset puts half the target off-screen. */}
        <button onClick={onClose} aria-label="Close" style={{
          position: 'absolute',
          top: isMobile ? 8 : -14, right: isMobile ? 8 : -14,
          width: 40, height: 40, borderRadius: 20,
          background: isMobile ? 'rgba(10,13,16,0.82)' : C.bg,
          backdropFilter: isMobile ? 'blur(6px)' : undefined,
          border: `1px solid ${C.border}`, color: C.ink, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}><X size={16} /></button>
      </div>
    </div>
  );
}

/** Metric.status now spans 5 tiers from the back-squat doc rewrite.
 *  This helper resolves the palette while still honouring low_conf dimming. */
function metricPalette(m: Metric) {
  if (m.confidence_tier === 'low') return statusColor('low_conf');
  return statusColor(m.status);
}

/** Lifts whether a metric counts as "passing" for the headline counters
 *  (very_good + good + legacy 'good'). yellow_flag and below are flags. */
function isPassingMetric(m: Metric): boolean {
  return m.status === 'good' || m.status === 'very_good';
}

function MetricGroupRow({ m }: { m: Metric }) {
  const palette = metricPalette(m);
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1fr) auto',
      gap: 12, alignItems: 'center',
      padding: '10px 0',
      borderBottom: `1px solid ${C.border}`,
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontFamily: F.body, fontSize: 13, color: C.ink, lineHeight: 1.3,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>{m.name}</div>
        <div style={{
          marginTop: 3, fontSize: 11, color: C.ink3,
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <span>{m.target}</span>
          {m.fault_timing && (
            <>· <span style={{ color: C.clay }}>rep {m.fault_timing.rep} · {Math.round(m.fault_timing.start_phase_pct)}%</span></>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          fontFamily: F.display, fontSize: 18, color: C.ink, letterSpacing: '-0.01em',
        }}>{m.value}</span>
        <span style={{
          display: 'inline-block', width: 8, height: 8, borderRadius: 4,
          background: palette.fg, boxShadow: `0 0 0 3px ${palette.bg}`,
        }} />
      </div>
    </div>
  );
}

function MetricGroup({
  title, description, Icon, tone, metrics,
}: {
  title: string; description: string;
  Icon: React.ComponentType<any>;
  tone: 'rust' | 'clay' | 'indigo';
  metrics: Metric[];
}) {
  const passed = metrics.filter(isPassingMetric).length;
  const accentColor = tone === 'rust' ? C.rust : tone === 'clay' ? C.clay : C.indigo;
  const total = metrics.length;
  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderTop: `3px solid ${accentColor}`,
      borderRadius: R.lg,
      padding: '20px 22px 4px',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <IconBadge tone={tone} size="xs"><Icon size={12} strokeWidth={1.8} /></IconBadge>
          <span style={{
            fontFamily: F.body, fontSize: 10.5, fontWeight: 600, letterSpacing: '0.18em',
            textTransform: 'uppercase', color: accentColor,
          }}>{title}</span>
          <span style={{
            marginLeft: 'auto',
            fontFamily: F.display, fontSize: 18, color: C.ink, letterSpacing: '-0.01em',
          }}>{passed}<span style={{ fontSize: 11, color: C.ink3 }}>/{total}</span></span>
        </div>
        <div style={{ fontSize: 11.5, color: C.ink3 }}>{description}</div>
      </div>
      {metrics.length === 0 ? (
        <div style={{ padding: '24px 0', fontSize: 12, color: C.ink3, textAlign: 'center' }}>
          No {title.toLowerCase()} metrics on this lift.
        </div>
      ) : (
        <div>{metrics.map((m, i) => <MetricGroupRow key={i} m={m} />)}</div>
      )}
    </div>
  );
}

function Collapsible({ title, defaultOpen = false, children }: {
  title: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: R.lg, overflow: 'hidden', marginBottom: 14,
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', padding: '14px 20px',
          background: 'transparent', border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
        {title}
        {open
          ? <ChevronDown size={16} strokeWidth={2} color={C.ink2} />
          : <ChevronRight size={16} strokeWidth={2} color={C.ink2} />}
      </button>
      {open && (
        <div style={{ padding: '0 20px 20px', borderTop: `1px solid ${C.border}` }}>
          {children}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
 * CompositeBreakdown — spec-driven scoring block (deadlift §7/§8/§11.4)
 * Renders only when ExerciseResult.composite_score is present.
 * ──────────────────────────────────────────────────────────────────── */

const GRADE_TONE: Record<GradeLetter, 'good'|'warn'|'bad'> = {
  A: 'good', B: 'good', C: 'warn', D: 'bad', E: 'bad',
};
const GRADE_COLOR: Record<GradeLetter, string> = {
  A: C.sage, B: C.sage, C: C.amber, D: C.rust, E: C.rust,
};

function CategoryBar({
  name, weight, score, Icon,
}: { name: string; weight: number; score: number; Icon: React.ComponentType<any> }) {
  const pct = Math.max(0, Math.min(100, score));
  const tone: 'sage'|'amber'|'rust' = score >= 75 ? 'sage' : score >= 60 ? 'amber' : 'rust';
  const accent = tone === 'sage' ? C.sage : tone === 'amber' ? C.amber : C.rust;
  return (
    <div style={{
      background: C.surface2, border: `1px solid ${C.border}`,
      borderRadius: R.md, padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <IconBadge tone={tone} size="xs"><Icon size={11} strokeWidth={1.8} /></IconBadge>
        <span style={{
          fontFamily: F.body, fontSize: 10.5, fontWeight: 600,
          letterSpacing: '0.16em', textTransform: 'uppercase', color: accent,
        }}>{name}</span>
        <span style={{ marginLeft: 'auto', fontSize: 10.5, color: C.ink3 }}>
          ×{(weight * 100).toFixed(0)}%
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 8 }}>
        <span style={{
          fontFamily: F.display, fontSize: 28, color: C.ink, letterSpacing: '-0.02em',
        }}>{Math.round(score)}</span>
        <span style={{ fontFamily: F.body, fontSize: 11, color: C.ink3 }}>/100</span>
      </div>
      <div style={{
        position: 'relative', height: 6, background: C.taupe,
        borderRadius: 3, overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', inset: 0, width: `${pct}%`,
          background: accent, transition: 'width 800ms cubic-bezier(.16,1,.3,1)',
        }} />
      </div>
    </div>
  );
}

function CompositeBreakdown({ cs }: { cs: CompositeScore }) {
  const triggered = cs.overrides.filter(o => o.triggered);
  const gradeColor = GRADE_COLOR[cs.grade];
  const gradeTone = GRADE_TONE[cs.grade];
  const detRepCount = cs.aggregation.deteriorating_rep_nums.length;
  const isMobile = useIsMobile();

  return (
    <div className="animate-fade-up-1" style={{ marginBottom: 20 }}>
      <Card pad={0} variant="raised" style={{ overflow: 'hidden' }}>
        {/* Header strip: grade letter + composite + variant + method */}
        <div style={{
          display: 'grid',
          // Grade tile · headline · label pill needs ~440px before the
          // headline starts wrapping one word per line. Stack on phones.
          gridTemplateColumns: isMobile ? 'auto minmax(0, 1fr)' : 'auto minmax(0, 1fr) auto',
          gap: isMobile ? 14 : 18, alignItems: 'center',
          padding: `clamp(16px,4vw,22px) clamp(18px,4.5vw,26px)`,
          borderBottom: `1px solid ${C.border}`,
          background: C.surface,
        }}>
          <div style={{
            width: isMobile ? 60 : 84, height: isMobile ? 60 : 84, borderRadius: R.lg,
            background: gradeColor, color: C.bg,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: F.display, fontSize: isMobile ? 40 : 56, lineHeight: 1, letterSpacing: '-0.04em',
            boxShadow: `0 6px 18px ${gradeColor}55`, flexShrink: 0,
          }}>{cs.grade}</div>
          <div style={{ minWidth: 0 }}>
            <SectionLabel style={{ marginBottom: 4 }}>
              Composite · {cs.composite_method} mean
              {cs.variant ? <> · {cs.variant}</> : null}
            </SectionLabel>
            <div style={{
              fontFamily: F.display, fontSize: 'clamp(21px,5vw,28px)', color: C.ink,
              letterSpacing: '-0.015em', lineHeight: 1.15,
            }}>
              {cs.label}, <em style={{ color: gradeColor }}>{Math.round(cs.composite)}/100</em>.
            </div>
            {cs.active_cap != null && (
              <div style={{ fontSize: 11.5, color: C.rust, marginTop: 4 }}>
                Capped at {cs.active_cap} by a safety override.
              </div>
            )}
          </div>
          {/* On phones the verdict pill moves under the pair, spanning both
              columns, rather than being squeezed into a third track. */}
          <div style={{ gridColumn: isMobile ? '1 / -1' : undefined }}>
            <Pill tone={gradeTone} size="md">{cs.label}</Pill>
          </div>
        </div>

        {/* Override banner — only if any hard-fail triggered */}
        {triggered.length > 0 && (
          <div style={{
            background: '#fbeae3', borderBottom: `1px solid ${C.border}`,
            padding: `14px clamp(18px,4.5vw,26px)`,
            display: 'flex', gap: 12, alignItems: 'flex-start',
          }}>
            <IconBadge tone="rust" size="sm"><ShieldAlert size={14} strokeWidth={1.9} /></IconBadge>
            <div style={{ flex: 1, minWidth: 0 }}>
              <SectionLabel style={{ color: C.rust, marginBottom: 4 }}>
                Safety override{triggered.length > 1 ? 's' : ''} triggered · composite capped
              </SectionLabel>
              <ul style={{ margin: 0, paddingLeft: 16, listStyle: 'disc' }}>
                {triggered.map((o, i) => (
                  <li key={i} style={{ fontSize: 13, color: C.ink, lineHeight: 1.55 }}>
                    <strong>{o.condition}</strong>
                    {o.triggering_metric && (
                      <> — {o.triggering_metric}
                        {o.triggering_value ? ` (${o.triggering_value})` : ''}</>
                    )}
                    {' · cap '}<span style={{ color: C.rust, fontWeight: 600 }}>{o.cap}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Category bars: Safety / Technique / Performance */}
        <div style={{ padding: `20px clamp(18px,4.5vw,26px)` }}>
          <div style={{
            display: 'grid', gap: 12,
            // A hard `repeat(3, 1fr)` gives each bar ~100px on a phone, which
            // clips the category name. Let them wrap instead.
            gridTemplateColumns: isMobile ? gridCols(150) : `repeat(${cs.categories.length}, minmax(0, 1fr))`,
            marginBottom: 16,
          }}>
            {cs.categories.map(cat => {
              const Icon = cat.name === 'Safety' ? ShieldAlert
                : cat.name === 'Technique' ? Activity : Zap;
              return (
                <CategoryBar key={cat.name}
                  name={cat.name} weight={cat.weight} score={cat.score} Icon={Icon} />
              );
            })}
          </div>

          {/* Aggregation pills: mean / worst / last-3 + deteriorating reps */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14,
          }}>
            <Pill tone="neutral" size="sm">
              Mean {Math.round(cs.aggregation.mean)}
            </Pill>
            <Pill tone={cs.aggregation.worst >= 60 ? 'warn' : 'bad'} size="sm">
              Worst rep {Math.round(cs.aggregation.worst)}
            </Pill>
            <Pill tone="neutral" size="sm">
              Last 3 {Math.round(cs.aggregation.last_three)}
            </Pill>
            {detRepCount > 0 && (
              <Pill tone="bad" size="sm">
                {detRepCount} deteriorating rep{detRepCount !== 1 ? 's' : ''} (&gt;15 pts below mean)
              </Pill>
            )}
          </div>

          {/* Lowest sub-scores with corrective cues (spec §11.4) */}
          {cs.lowest_sub_scores.length > 0 && (
            <div>
              <SectionLabel style={{ marginBottom: 10 }}>
                Two lowest sub-scores · fix these first
              </SectionLabel>
              <div style={{
                display: 'grid', gap: 10,
                gridTemplateColumns: isMobile
                  ? '1fr'
                  : `repeat(${Math.min(cs.lowest_sub_scores.length, 2)}, minmax(0, 1fr))`,
              }}>
                {cs.lowest_sub_scores.slice(0, 2).map((cue, i) => {
                  const sev: 'rust'|'amber' = cue.sub_score < 60 ? 'rust' : 'amber';
                  return (
                    <Card key={i} pad={16} accent={sev}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
                        <span style={{
                          fontFamily: F.display, fontSize: 22, color: C.ink,
                          letterSpacing: '-0.015em',
                        }}>{Math.round(cue.sub_score)}</span>
                        <span style={{ fontSize: 10, color: C.ink3 }}>/100</span>
                        <span style={{
                          marginLeft: 6, fontFamily: F.body, fontSize: 11.5,
                          fontWeight: 600, color: C.ink, lineHeight: 1.3,
                        }}>{cue.metric}</span>
                      </div>
                      <div style={{ fontSize: 12.5, color: C.ink2, lineHeight: 1.55 }}>{cue.cue}</div>
                    </Card>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
 * Main ResultPage
 * ──────────────────────────────────────────────────────────────────── */

interface Props {
  exercise: Exercise;
  apiResult?: any;
  completed: Set<string>;
  onNext: () => void;
  onRedo: () => void;
  onGuide: () => void;
  onDashboard?: () => void;
  onSession?: () => void;
}

export function ResultPage({
  exercise, apiResult, completed: _completed, onNext, onRedo, onGuide, onDashboard, onSession,
}: Props) {
  void _completed;
  const [gaugeReady, setGaugeReady] = useState(false);
  const [openFrame, setOpenFrame] = useState<AnnotatedFrame | null>(null);
  const isMobile = useIsMobile();
  const isNarrow = useIsNarrow();

  const { type } = useParams();
  const assessmentType = isValidAssessmentType(type) ? type : 'mobility';
  const exercises = listExercises(assessmentType);
  const exIdx = exercises.findIndex(e => e.slug === exercise.slug);
  const hasNext = exIdx < exercises.length - 1;
  const r = apiResult || exercise.result;

  const isSample = !apiResult;
  const isError = !!(apiResult && (apiResult as any)._isError);

  useEffect(() => { setGaugeReady(false); }, [exercise.id]);
  useEffect(() => {
    const t = setTimeout(() => setGaugeReady(true), 240);
    return () => clearTimeout(t);
  }, [exercise.id]);

  const goodCount = r.metrics.filter((m: Metric) => isPassingMetric(m)).length;
  const totalMetrics = r.metrics.length;
  const passRate = totalMetrics > 0 ? goodCount / totalMetrics : 0;

  const grouped = useMemo(() => {
    const out: Record<Bucket, Metric[]> = { safety: [], form: [], performance: [] };
    for (const m of r.metrics as Metric[]) out[classifyMetric(m.name)].push(m);
    return out;
  }, [r.metrics]);

  const verdict = useMemo(() => synthesizeVerdict(r.metrics), [r.metrics]);
  const allFrames: AnnotatedFrame[] = r.annotated_frames ?? [];
  const band = statusBand(r.score);
  const palette = overallStatusColor(r.status);
  const muscle: MuscleActivationData | undefined = r.muscle_activation;
  const hasMuscle = !!(muscle && muscle.muscles && muscle.muscles.length);

  // Histogram source: prefer "performance" metrics (velocity, tempo, ROM, etc.)
  // — they have meaningful numeric ranges. Fall back to all metrics if none.
  const histogramMetrics = useMemo(() => {
    const performanceish = (r.metrics as Metric[]).filter(m => m.max && m.max > 0);
    return performanceish.length >= 3 ? performanceish : (r.metrics as Metric[]).filter(m => m.max);
  }, [r.metrics]);

  useKeyboard({
    onEnter: () => hasNext ? onNext() : (onDashboard ? onDashboard() : onGuide()),
    onEscape: onGuide,
    onLeft: onRedo,
    onRight: hasNext ? onNext : undefined,
  });

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.ink, paddingBottom: 96 }}>
      <Nav
        onBack={onGuide} backLabel="All exercises"
        crumbs={[
          { label: 'Home' },
          { label: 'Exercises', to: onGuide },
          { label: exercise.name },
        ]}
        rightSlot={(
          <>
            {onSession && (
              <Button variant="ghost" size="sm" onClick={onSession}>Session</Button>
            )}
            <Pill tone="clay" size="sm">Rep {exIdx + 1} / {exercises.length}</Pill>
          </>
        )}
      />

      <div style={{ maxWidth: 1280, margin: '0 auto', padding: `clamp(26px,5vw,40px) ${GUTTER} 0` }}>
        {/* ── Kicker + Headline ─────────────────────── */}
        <div className="animate-fade-up" style={{ marginBottom: 22 }}>
          <SectionLabel style={{ marginBottom: 10 }}>
            Report · {exercise.category} · {exercise.subtitle}
          </SectionLabel>
          <Display size="h1" style={{ marginBottom: 4 }}>
            {exercise.name}, <em>{band.label.toLowerCase()}.</em>
          </Display>
        </div>

        {/* ── Banners ───────────────────────────────── */}
        {r.meta?.camera_view_warning && (
          <Card pad={16} accent="amber" style={{ marginBottom: 14 }}>
            <SectionLabel style={{ color: C.amber, marginBottom: 4 }}>📷 Camera view</SectionLabel>
            <div style={{ fontSize: 13.5, color: C.ink, lineHeight: 1.55 }}>{r.meta.camera_view_warning}</div>
          </Card>
        )}
        {isError && (
          <Card pad={18} accent="rust" style={{ marginBottom: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 240 }}>
                <SectionLabel style={{ color: C.rust, marginBottom: 4 }}>Analysis failed</SectionLabel>
                <div style={{ fontSize: 13.5, color: C.ink, lineHeight: 1.5 }}>{r.summary}</div>
              </div>
              <Button variant="danger" size="md" onClick={onRedo} iconRight={<span style={{ fontSize: 16 }}>→</span>}>Try again</Button>
            </div>
          </Card>
        )}
        {isSample && !isError && (
          <Card pad={18} accent="amber" style={{ marginBottom: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 240 }}>
                <SectionLabel style={{ color: C.amber, marginBottom: 4 }}>Sample preview</SectionLabel>
                <div style={{ fontSize: 13.5, color: C.ink, lineHeight: 1.55 }}>
                  Placeholder numbers — upload a video to see your actual report.
                </div>
              </div>
              <Button variant="primary" size="md" onClick={onRedo} iconRight={<span style={{ fontSize: 16 }}>→</span>}>Upload & analyse</Button>
            </div>
          </Card>
        )}

        {/* ═══════════════════════════════════════════════════════════════
            HERO  —  Score + Verdict (compact, single row)
            ═══════════════════════════════════════════════════════════════ */}
        <Card pad={0} className="animate-fade-up-1" style={{ marginBottom: 20, overflow: 'hidden' }}>
          <div style={{
            display: 'grid',
            // The 220px score rail leaves under 100px for the verdict on a
            // phone — stack the two so each gets the full width.
            gridTemplateColumns: isMobile ? '1fr' : 'minmax(220px, 260px) minmax(0, 1fr)',
            alignItems: 'stretch',
          }}>
            <div style={{
              padding: `clamp(22px,4.5vw,28px) clamp(18px,4vw,24px)`,
              borderRight: isMobile ? 'none' : `1px solid ${C.border}`,
              borderBottom: isMobile ? `1px solid ${C.border}` : 'none',
              background: C.surface,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              gap: 14, textAlign: 'center',
            }}>
              <ScoreBadge score={r.score} ready={gaugeReady} status={r.status} size={isMobile ? 148 : 170} />
              <Pill tone={band.band === 'strong' ? 'good' : band.band === 'solid' ? 'warn' : 'bad'} size="md">
                {band.label}
              </Pill>
              <div style={{ display: 'flex', gap: 18 }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: F.display, fontSize: 18, color: C.ink, letterSpacing: '-0.01em' }}>
                    {goodCount}<span style={{ fontSize: 10, color: C.ink3 }}>/{totalMetrics}</span>
                  </div>
                  <SectionLabel style={{ marginTop: 2, fontSize: 9 }}>Pass</SectionLabel>
                </div>
                <div style={{ width: 1, background: C.border }} />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: F.display, fontSize: 18, color: C.ink, letterSpacing: '-0.01em' }}>
                    {Math.round(passRate * 100)}<span style={{ fontSize: 10, color: C.ink3 }}>%</span>
                  </div>
                  <SectionLabel style={{ marginTop: 2, fontSize: 9 }}>Rate</SectionLabel>
                </div>
              </div>
            </div>
            <div style={{ padding: `clamp(22px,4.5vw,28px) clamp(18px,5vw,32px)`, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <IconBadge tone={band.band === 'strong' ? 'sage' : band.band === 'solid' ? 'amber' : 'rust'} size="sm">
                  {band.band === 'strong' ? <Trophy size={14} strokeWidth={1.8} />
                    : band.band === 'solid' ? <TrendingUp size={14} strokeWidth={1.8} />
                    : <AlertTriangle size={14} strokeWidth={1.8} />}
                </IconBadge>
                <SectionLabel style={{ color: palette.fg }}>Verdict</SectionLabel>
              </div>
              <div style={{
                fontFamily: F.display, fontSize: 'clamp(20px, 2.2vw, 26px)', lineHeight: 1.3,
                color: C.ink, letterSpacing: '-0.015em',
              }}>
                {verdict.wins.length > 0
                  ? <>
                      {verdict.wins.map(w => w.toLowerCase()).join(' · ')}
                      {verdict.fix && <> · one fix: <em style={{ color: C.clay }}>{verdict.fix}</em>.</>}
                      {!verdict.fix && '.'}
                    </>
                  : verdict.fix
                    ? <>focus: <em style={{ color: C.clay }}>{verdict.fix}</em>.</>
                    : <>{r.summary || 'No major faults detected.'}</>}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {Object.entries(r.stats).slice(0, 5).map(([k, v]) => (
                  <span key={k} style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '3px 10px', borderRadius: R.pill,
                    background: C.surface2, border: `1px solid ${C.border}`,
                  }}>
                    <span style={{
                      fontFamily: F.body, fontSize: 9.5, color: C.ink3,
                      letterSpacing: '0.14em', textTransform: 'uppercase',
                    }}>{k.replace(/([A-Z])/g, ' $1').trim()}</span>
                    <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 11.5, color: C.ink }}>{String(v)}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </Card>

        {/* ═══════════════════════════════════════════════════════════════
            COMPOSITE BREAKDOWN  —  spec-driven (Safety / Technique / Performance)
            Only renders when analyzer emits composite_score (deadlift).
            ═══════════════════════════════════════════════════════════════ */}
        {r.composite_score && <CompositeBreakdown cs={r.composite_score as CompositeScore} />}

        {/* ═══════════════════════════════════════════════════════════════
            EVIDENCE ROW  —  All frames (gallery) + Muscle Body (paired)
            The two main visual sources: "what you did" + "what worked"
            ═══════════════════════════════════════════════════════════════ */}
        <div className="animate-fade-up-2" style={{
          display: 'grid', gap: 16, marginBottom: 28,
          // The muscle diagram needs 360px to stay legible; below ~900px total
          // there isn't room for it *and* the frame gallery side by side, so
          // the two stack rather than overflowing the viewport.
          gridTemplateColumns: hasMuscle && !isNarrow
            ? 'minmax(0, 1.6fr) minmax(360px, 1fr)'
            : '1fr',
        }}>
          {/* Frames gallery — ALL frames visible at once */}
          <Card pad={isMobile ? 16 : 22} variant="raised">
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              gap: 12, marginBottom: 16, flexWrap: 'wrap',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <IconBadge tone="clay" size="sm"><ImageIcon size={14} strokeWidth={1.8} /></IconBadge>
                <div>
                  <SectionLabel>Every rep · annotated</SectionLabel>
                  <div style={{ fontFamily: F.display, fontSize: 20, color: C.ink, letterSpacing: '-0.015em', marginTop: 2 }}>
                    Watch what <em>actually happened.</em>
                  </div>
                </div>
              </div>
              {allFrames.length > 0 && (
                <Pill tone="neutral" size="xs">{allFrames.length} frame{allFrames.length !== 1 ? 's' : ''} · tap to enlarge</Pill>
              )}
            </div>
            {allFrames.length > 0 ? (
              <div style={{
                display: 'grid',
                // 120px min keeps two tiles per row on a 375px phone instead
                // of dropping to one giant tile per row.
                gridTemplateColumns: gridCols(isMobile ? 120 : 150, 'fill'),
                gap: isMobile ? 8 : 12,
              }}>
                {allFrames.map((f, i) => (
                  <FrameTile key={i} frame={f} onOpen={() => setOpenFrame(f)} />
                ))}
              </div>
            ) : (
              <div style={{
                padding: 32, textAlign: 'center',
                background: C.surface2, borderRadius: R.lg,
              }}>
                <div style={{ fontFamily: F.display, fontSize: 18, color: C.ink, marginBottom: 6 }}>
                  No frames <em>yet.</em>
                </div>
                <div style={{ fontSize: 12.5, color: C.ink2 }}>
                  {isError ? 'Analyser errored before frames were rendered.' : 'Upload a video to see annotated frames.'}
                </div>
              </div>
            )}
          </Card>

          {/* Muscle activation BODY DIAGRAM */}
          {hasMuscle && <MuscleBody data={muscle!} />}
        </div>

        {/* ═══════════════════════════════════════════════════════════════
            TOP ACTIONS  —  ≤ 3 coaching cards
            ═══════════════════════════════════════════════════════════════ */}
        {r.coaching && r.coaching.length > 0 && (
          <div className="animate-fade-up-2" style={{ marginBottom: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <IconBadge tone="clay" size="sm"><MessageCircle size={14} strokeWidth={1.8} /></IconBadge>
              <SectionLabel>Top actions · do these next</SectionLabel>
            </div>
            <div style={{
              display: 'grid', gap: 12,
              // Three fixed columns turn each coaching note into a ~100px
              // ribbon on a phone. Let them wrap by content width instead.
              gridTemplateColumns: isNarrow
                ? gridCols(240)
                : `repeat(${Math.min(r.coaching.length, 3)}, minmax(0, 1fr))`,
            }}>
              {r.coaching.slice(0, 3).map((note: string, i: number) => {
                const isWarning = note.includes('⚠️') || note.includes('🚩');
                const tone: 'good' | 'warn' | 'bad' = isWarning ? 'bad' : i === 0 ? 'warn' : 'good';
                const Icon = tone === 'bad' ? AlertTriangle : tone === 'warn' ? AlertCircle : CheckCircle2;
                const priority = isWarning ? 'Critical' : i === 0 ? 'Important' : 'Maintain';
                const accent = tone === 'bad' ? 'rust' : tone === 'warn' ? 'amber' : 'sage';
                const palette2 = statusColor(tone);
                const cleaned = note.replace(/^(⚠️|🚩|🟡|🔴|🟢|📷)\s*/g, '');
                return (
                  <Card key={i} pad={20} accent={accent} style={{ paddingLeft: 26 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <IconBadge tone={accent} size="xs">
                          <Icon size={12} strokeWidth={1.8} />
                        </IconBadge>
                        <span style={{
                          fontFamily: F.body, fontSize: 10, fontWeight: 600,
                          letterSpacing: '0.18em', textTransform: 'uppercase',
                          color: palette2.fg,
                        }}>{priority}</span>
                      </div>
                      <p style={{ margin: 0, fontSize: 13.5, color: C.ink, lineHeight: 1.6 }}>{cleaned}</p>
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════
            TECHNICAL  —  Grouped metric cards + Histogram + Bilateral
            ═══════════════════════════════════════════════════════════════ */}
        <div className="animate-fade-up-3" style={{ marginBottom: 16 }}>
          <div style={{
            display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
            flexWrap: 'wrap', gap: 12,
            paddingBottom: 14, marginBottom: 18,
            borderBottom: `1px solid ${C.border}`,
          }}>
            <div>
              <SectionLabel style={{ marginBottom: 4 }}>Technical · for coaches</SectionLabel>
              <div style={{ fontFamily: F.display, fontSize: 'clamp(20px,4.5vw,24px)', color: C.ink, letterSpacing: '-0.015em' }}>
                The <em>numbers behind the score.</em>
              </div>
            </div>
            <div style={{ fontSize: 12.5, color: C.ink3, maxWidth: 360, lineHeight: 1.55 }}>
              Everything the analyser measured, grouped so a coach can scan it in 30 seconds.
            </div>
          </div>

          {/* Grouped metric cards */}
          <div style={{
            display: 'grid', gap: 14, marginBottom: 18,
            gridTemplateColumns: gridCols(280),
          }}>
            {BUCKETS.map(b => (
              <MetricGroup
                key={b.key}
                title={b.label}
                description={b.description}
                Icon={b.Icon}
                tone={b.tone}
                metrics={grouped[b.key]}
              />
            ))}
          </div>

          {/* HISTOGRAM — real SVG bar chart with target line */}
          {histogramMetrics.length > 0 && (
            <Card pad={isMobile ? 16 : 24} variant="raised" style={{ marginBottom: 16 }}>
              <div style={{
                display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
                marginBottom: 16, flexWrap: 'wrap', gap: 10,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <IconBadge tone="clay" size="sm"><BarChart3 size={14} strokeWidth={1.8} /></IconBadge>
                  <div>
                    <SectionLabel>Metric histogram · % of target</SectionLabel>
                    <div style={{ fontFamily: F.display, fontSize: 18, color: C.ink, letterSpacing: '-0.015em', marginTop: 2 }}>
                      How far you cleared the bar — <em>literally.</em>
                    </div>
                  </div>
                </div>
                <span style={{ fontFamily: F.body, fontSize: 11, color: C.clay, fontStyle: 'italic' }}>
                  -- target threshold at 100%
                </span>
              </div>
              {/* Fewer, wider bars on a phone — nine bars scaled into 340px
                  renders the axis labels at ~5px. */}
              <MetricHistogram
                metrics={histogramMetrics}
                maxBars={isMobile ? 5 : 9}
                height={isMobile ? 260 : 300}
                width={isMobile ? 380 : 720}
              />
            </Card>
          )}

          {/* Bilateral L vs R */}
          {r.bilateral && r.bilateral.length > 0 && (
            <Card variant="raised" pad={isMobile ? 16 : 22} style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <IconBadge tone="indigo" size="sm"><Users size={14} strokeWidth={1.8} /></IconBadge>
                <SectionLabel>Left vs right</SectionLabel>
              </div>
              <div style={{
                display: 'grid', gap: 18,
                gridTemplateColumns: gridCols(260),
              }}>
                {r.bilateral.map((b: BilateralComparison, i: number) => {
                  const lPct = Math.min(100, (b.left  / Math.max(b.max, 0.01)) * 100);
                  const rPct = Math.min(100, (b.right / Math.max(b.max, 0.01)) * 100);
                  const asymTone: 'good' | 'warn' | 'bad' =
                    b.asymmetry < 5 ? 'good' : b.asymmetry < 15 ? 'warn' : 'bad';
                  return (
                    <div key={i}>
                      <div style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                        marginBottom: 8, flexWrap: 'wrap', gap: 6,
                      }}>
                        <span style={{ fontFamily: F.body, fontSize: 13, color: C.ink, fontWeight: 500 }}>{b.name}</span>
                        <Pill tone={asymTone} size="xs">{b.asymmetry}% Δ</Pill>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {[
                          { side: 'L', val: b.left,  pct: lPct, color: C.indigo },
                          { side: 'R', val: b.right, pct: rPct, color: C.clay },
                        ].map(row => (
                          <div key={row.side} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{
                              width: 14, fontFamily: F.body, fontWeight: 600, fontSize: 10,
                              color: C.ink3, letterSpacing: '0.06em',
                            }}>{row.side}</span>
                            <div style={{ flex: 1, height: 5, borderRadius: 2.5, background: C.taupe, overflow: 'hidden' }}>
                              <div style={{
                                height: '100%', background: row.color,
                                width: `${row.pct}%`,
                                transition: 'width 1s cubic-bezier(.16,1,.3,1)',
                              }} />
                            </div>
                            <span style={{
                              minWidth: 44, textAlign: 'right',
                              fontFamily: F.display, fontSize: 14, color: C.ink,
                            }}>{row.val}{b.unit}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>

        {/* ═══════════════════════════════════════════════════════════════
            COLLAPSIBLES  —  per-rep raw data
            ═══════════════════════════════════════════════════════════════ */}
        {r.per_rep && r.per_rep.length > 0 && (
          <Collapsible
            defaultOpen={false}
            title={(
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                <IconBadge tone="amber" size="xs"><ListChecks size={12} strokeWidth={1.8} /></IconBadge>
                <SectionLabel>Per-rep raw data ({r.per_rep.length} reps)</SectionLabel>
              </span>
            )}>
            <div style={{ paddingTop: 14 }}>
              <PerRepAccordion reps={r.per_rep} />
            </div>
          </Collapsible>
        )}

        {/* ── Bottom nav ────────────────────────────── */}
        <div style={{
          paddingTop: 28, marginTop: 24,
          borderTop: `1px solid ${C.border}`,
          display: 'flex',
          flexDirection: isMobile ? 'column-reverse' : 'row',
          justifyContent: 'space-between',
          alignItems: isMobile ? 'stretch' : 'center',
          flexWrap: 'wrap', gap: 12,
        }}>
          <Button variant="ghost" size="md" onClick={onRedo} block={isMobile}
            iconLeft={<span style={{ fontSize: 16 }}>←</span>}>
            Redo this exercise
          </Button>
          <div style={{
            display: isMobile ? 'grid' : 'flex',
            gridTemplateColumns: isMobile ? '1fr 1fr' : undefined,
            gap: 10, flexWrap: 'wrap',
          }}>
            <Button variant="secondary" size="md" onClick={onGuide} block={isMobile}>All exercises</Button>
            {onDashboard && (
              <Button variant="secondary" size="md" onClick={onDashboard} block={isMobile}>Dashboard</Button>
            )}
            {hasNext ? (
              <Button variant="primary" size="md" onClick={onNext} block={isMobile}
                style={isMobile ? { gridColumn: '1 / -1' } : undefined}
                iconRight={<span style={{ fontSize: 16 }}>→</span>}>
                Next exercise
              </Button>
            ) : (
              <Button variant="primary" size="md" onClick={onDashboard || onGuide} block={isMobile}
                style={isMobile ? { gridColumn: '1 / -1' } : undefined}
                iconRight={<span style={{ fontSize: 16 }}>→</span>}>
                Full report
              </Button>
            )}
          </div>
        </div>
      </div>

      {openFrame && <FrameLightbox frame={openFrame} onClose={() => setOpenFrame(null)} />}
    </div>
  );
}
