import { useEffect, useMemo, useState } from 'react';
import { Nav } from '@/components/shared';
import { useAppContext } from '@/context/AppContext';
import { fetchSessionDetails, resetSession, type SessionData } from '@/services/session';
import { getExercise, type AssessmentType } from '@/data/registry';
import type { AnnotatedFrame } from '@/data/types';
import {
  Button, Card, Pill, SectionLabel, Display, Stat, EmptyState, Skeleton, IconBadge,
} from '@/components/ui';
import { C, F, R, GUTTER, gridCols, statusColor } from '@/theme/tokens';
import { ArrowBadge } from '@/components/ui/Button';
import { useKeyboard } from '@/hooks/useKeyboard';
import { useIsMobile } from '@/hooks/useMediaQuery';
import {
  X, Download, RefreshCcw, FileText, Calendar, Clock, Hash,
  Activity, Dumbbell, ListChecks, Users, MessageCircle, ImageIcon,
} from 'lucide-react';

interface Props {
  onOpenReport: (type: AssessmentType, slug: string) => void;
  onGuide:      () => void;
  onLanding:    () => void;
  onBack:       () => void;
}

function gradeFromScore(score: number) {
  if (score >= 85) return { label: 'A', tone: 'good' as const, color: C.sage };
  if (score >= 70) return { label: 'B', tone: 'good' as const, color: C.sage };
  if (score >= 55) return { label: 'C', tone: 'warn' as const, color: C.amber };
  return            { label: 'D', tone: 'bad'  as const, color: C.rust };
}

function formatDate(iso: string) {
  try { return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); }
  catch { return iso; }
}

/* ── Full-screen frame modal ───────────────────────────── */
function FrameModal({ frame, onClose }: { frame: AnnotatedFrame; onClose: () => void }) {
  useKeyboard({ onEscape: onClose });
  const isMobile = useIsMobile();
  return (
    <div onClick={onClose} role="dialog" aria-modal="true" style={{
      position: 'fixed', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(10,13,16,0.82)', backdropFilter: 'blur(8px)',
      cursor: 'zoom-out', padding: isMobile ? 14 : 32,
      paddingTop: `max(${isMobile ? 14 : 32}px, env(safe-area-inset-top, 0px))`,
      paddingBottom: `max(${isMobile ? 14 : 32}px, env(safe-area-inset-bottom, 0px))`,
    }} className="animate-fade-in">
      <div onClick={e => e.stopPropagation()} style={{ maxWidth: '100%', maxHeight: '100%', position: 'relative' }}>
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

/* ── Per-report block ─────────────────────────────────── */
function ReportBlock({ type, slug, report, onOpen, onFrame, isMobile }: {
  type: AssessmentType; slug: string; report: any;
  onOpen: () => void; onFrame: (f: AnnotatedFrame) => void; isMobile?: boolean;
}) {
  const ex = getExercise(type, slug);
  const g = gradeFromScore(report.score || 0);
  const frames: AnnotatedFrame[] = report.annotated_frames || [];
  const goodCount = (report.metrics || []).filter((m: any) => m.status === 'good').length;
  const totalMetrics = (report.metrics || []).length;
  const padX = isMobile ? 18 : 28;

  return (
    <Card pad={0} accent={g.tone === 'good' ? 'sage' : g.tone === 'warn' ? 'amber' : 'rust'}>
      {/* Header */}
      <div style={{
        padding: `22px ${padX}px`,
        display: 'flex', alignItems: 'flex-start', gap: isMobile ? 12 : 18,
        borderBottom: `1px solid ${C.border}`,
      }}>
        <span style={{
          width: isMobile ? 36 : 44, height: isMobile ? 36 : 44, borderRadius: R.md,
          background: C.surface2, color: C.clay,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: F.display, fontSize: isMobile ? 17 : 20, flexShrink: 0,
        }}>{ex?.id ?? '·'}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: F.display, fontSize: isMobile ? 19 : 22, color: C.ink, letterSpacing: '-0.01em', lineHeight: 1.15 }}>
              {ex?.name ?? slug}
            </span>
            <Pill tone={g.tone} size="xs">{report.status}</Pill>
          </div>
          <SectionLabel style={{ marginTop: 4 }}>{type} · {ex?.subtitle ?? ''}</SectionLabel>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontFamily: F.display, fontSize: isMobile ? 28 : 36, color: g.color, lineHeight: 1 }}>{report.score ?? 0}</div>
          <SectionLabel style={{ marginTop: 4 }}>Grade · {g.label}</SectionLabel>
        </div>
      </div>

      {/* Summary */}
      {report.summary && (
        <div style={{ padding: `16px ${padX}px`, borderBottom: `1px solid ${C.border}` }}>
          <p style={{ margin: 0, fontSize: 13.5, color: C.ink2, lineHeight: 1.7 }}>{report.summary}</p>
        </div>
      )}

      {/* Stats strip */}
      {report.stats && (
        <div style={{
          padding: `12px ${padX}px`, borderBottom: `1px solid ${C.border}`,
          display: 'flex', gap: 10, flexWrap: 'wrap',
        }}>
          {Object.entries(report.stats).map(([k, v]) => (
            <span key={k} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              fontFamily: F.body, fontSize: 11.5, color: C.ink2,
            }}>
              <span style={{ color: C.ink3, letterSpacing: '0.10em', textTransform: 'uppercase', fontSize: 10 }}>
                {k.replace(/([A-Z])/g, ' $1').trim()}
              </span>
              <strong style={{ color: C.ink, fontWeight: 500 }}>{String(v)}</strong>
            </span>
          ))}
        </div>
      )}

      {/* Metrics */}
      {report.metrics && report.metrics.length > 0 && (
        <div style={{ padding: `18px ${padX}px` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <IconBadge tone="indigo" size="xs"><ListChecks size={12} strokeWidth={1.8} /></IconBadge>
            <SectionLabel>All metrics · {goodCount}/{totalMetrics} passed</SectionLabel>
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: gridCols(260),
            gap: 6,
          }}>
            {report.metrics.map((m: any, i: number) => {
              const palette = statusColor(m.status);
              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                  padding: '8px 12px', borderRadius: R.sm,
                  background: C.surface2,
                  border: `1px solid ${palette.border}`,
                }}>
                  <span style={{ fontSize: 12, color: C.ink, lineHeight: 1.3, flex: 1, minWidth: 0 }}>{m.name}</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: F.display, fontSize: 13, color: palette.fg }}>{m.value}</span>
                    <span style={{ fontSize: 10, color: C.ink3 }}>→ {m.target}</span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Bilateral */}
      {report.bilateral && report.bilateral.length > 0 && (
        <div style={{ padding: `0 ${padX}px 14px` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <IconBadge tone="indigo" size="xs"><Users size={12} strokeWidth={1.8} /></IconBadge>
            <SectionLabel>Bilateral</SectionLabel>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {report.bilateral.map((b: any, i: number) => (
              <span key={i} style={{
                padding: '6px 12px', borderRadius: R.sm,
                background: C.surface2, border: `1px solid ${C.border}`,
                fontFamily: F.body, fontSize: 12, color: C.ink,
              }}>
                {b.name}: <strong style={{ fontWeight: 500 }}>L {b.left}{b.unit}</strong>
                {' · '}<strong style={{ fontWeight: 500 }}>R {b.right}{b.unit}</strong>
                {' · '}<span style={{ color: b.asymmetry > 5 ? C.rust : C.sage }}>Δ {b.asymmetry}{b.unit}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Frames */}
      {frames.length > 0 && (
        <div style={{ padding: `0 ${padX}px 14px` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <IconBadge tone="clay" size="xs"><ImageIcon size={12} strokeWidth={1.8} /></IconBadge>
            <SectionLabel>Skeleton frames ({frames.length})</SectionLabel>
          </div>
          <div className="mc-hscroll" style={{ display: 'flex', gap: 12, paddingBottom: 4 }}>
            {frames.map((f, i) => (
              <button key={i} onClick={() => onFrame(f)} style={{
                width: 200, flexShrink: 0, padding: 0, textAlign: 'left', cursor: 'pointer',
                background: C.surface, border: f.is_best ? `1.5px solid ${C.clay}` : `1px solid ${C.border}`,
                borderRadius: R.lg, overflow: 'hidden',
                transition: 'transform 220ms ease',
              }}
                onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
                onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                <img src={f.image_base64} alt={f.label}
                  style={{ width: '100%', height: 140, objectFit: 'cover', display: 'block' }} />
                <div style={{
                  padding: '8px 12px',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                }}>
                  <span style={{ fontSize: 12, color: C.ink, fontWeight: 500 }}>{f.label}</span>
                  {f.is_best && <Pill tone="clay" size="xs">★ Best</Pill>}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Coaching */}
      {report.coaching && report.coaching.length > 0 && (
        <div style={{ padding: `0 ${padX}px 14px` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <IconBadge tone="amber" size="xs"><MessageCircle size={12} strokeWidth={1.8} /></IconBadge>
            <SectionLabel>Coaching</SectionLabel>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {report.coaching.map((c: string, i: number) => (
              <p key={i} style={{
                margin: 0, fontSize: 13, color: C.ink2, lineHeight: 1.6,
                paddingLeft: 12, borderLeft: `2px solid ${C.clay}`,
              }}>{c}</p>
            ))}
          </div>
        </div>
      )}

      {/* Per-rep raw */}
      {report.per_rep && report.per_rep.length > 0 && (
        <details style={{ padding: `0 ${padX}px 14px` }}>
          <summary style={{
            fontFamily: F.body, fontWeight: 500, fontSize: 11, letterSpacing: '0.18em',
            color: C.ink3, textTransform: 'uppercase', cursor: 'pointer',
          }}>
            Per-rep raw data ({report.per_rep.length} reps)
          </summary>
          <pre style={{
            marginTop: 10, padding: 12, borderRadius: R.sm,
            background: C.surface2, border: `1px solid ${C.border}`,
            fontSize: 11, color: C.ink2, overflowX: 'auto', maxHeight: 240,
            fontFamily: F.mono,
          }}>
{JSON.stringify(report.per_rep, null, 2)}
          </pre>
        </details>
      )}

      {/* Open */}
      <div style={{ padding: `14px ${padX}px 22px` }}>
        <Button variant="secondary" size="md" block onClick={onOpen}
          iconRight={<span style={{ fontSize: 16 }}>→</span>}>
          Open full report
        </Button>
      </div>
    </Card>
  );
}

/* ═══════════════════════════════════════════════════════════ */
export function SessionsPage({ onOpenReport, onGuide, onLanding, onBack }: Props) {
  const { sessionId, sessionLoading, reports } = useAppContext();
  const isMobile = useIsMobile();
  const [serverSession, setServerSession] = useState<SessionData | null>(null);
  const [openFrame, setOpenFrame] = useState<AnnotatedFrame | null>(null);
  const [loadingServer, setLoadingServer] = useState(true);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!sessionId) return;
      setLoadingServer(true);
      try {
        const data = await fetchSessionDetails(sessionId);
        if (!cancelled) setServerSession(data);
      } catch (e) { console.error('Session fetch failed', e); }
      finally { if (!cancelled) setLoadingServer(false); }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  const view: SessionData | null = useMemo(() => {
    if (serverSession) return serverSession;
    if (!sessionId) return null;
    return {
      sessionId,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      assessments: {
        mobility: { reports: reports.mobility, completedAt: null },
        strength: { reports: reports.strength, completedAt: null },
      },
    };
  }, [serverSession, sessionId, reports]);

  const totalReports = view
    ? Object.keys(view.assessments.mobility.reports).length +
      Object.keys(view.assessments.strength.reports).length
    : 0;

  const exportJson = async () => {
    if (!view) return;
    setExporting(true);
    try {
      const blob = new Blob([JSON.stringify(view, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `session-${view.sessionId}.json`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally { setTimeout(() => setExporting(false), 500); }
  };

  const clearSession = () => {
    if (!confirm('Clear this session? A new sessionId will be created on next page load. Server JSON is kept.')) return;
    resetSession();
    location.reload();
  };

  // Keyboard: Escape → back home; Enter → continue assessing
  useKeyboard({ onEscape: onLanding, onEnter: onGuide });

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.ink, paddingBottom: 96 }}>
      <Nav
        onBack={onBack} backLabel="Back"
        crumbs={[
          { label: 'Home', to: onLanding },
          { label: 'Session details' },
        ]}
      />

      {/* ── Banner ──────────────────────────────────────────── */}
      <div style={{
        position: 'relative', height: 'clamp(120px, 26vw, 200px)', overflow: 'hidden',
        backgroundImage: `linear-gradient(180deg, rgba(10,13,16,0.35) 0%, ${C.bg} 94%), url(/images/sessions/banner.jpg)`,
        backgroundSize: 'cover', backgroundPosition: 'center 35%',
        borderBottom: `1px solid ${C.border}`,
      }}>
        <div style={{ maxWidth: 1180, margin: '0 auto', height: '100%', display: 'flex', alignItems: 'flex-end', padding: `0 ${GUTTER} 22px` }}>
          <span style={{ fontFamily: F.body, fontSize: isMobile ? 10 : 11.5, letterSpacing: isMobile ? '1.6px' : '2.5px', color: C.ink3, fontWeight: 700, textTransform: 'uppercase' }}>
            The archive · every session, kept
          </span>
        </div>
      </div>

      <div style={{ maxWidth: 1180, margin: '0 auto', padding: `clamp(32px,6vw,56px) ${GUTTER} 0` }}>
        {/* Header */}
        <div className="animate-fade-up" style={{ marginBottom: 36 }}>
          <SectionLabel style={{ marginBottom: 14 }}>Persisted session</SectionLabel>
          <Display size="h1">
            Everything you've<br/>
            run, <em>kept safe.</em>
          </Display>
          <p style={{ marginTop: 14, color: C.ink2, fontSize: 15, maxWidth: 640, lineHeight: 1.7 }}>
            Every analysis is saved here — locally in your browser and as a JSON file on the
            backend. Open any report to dive in, or export the whole session as JSON.
          </p>
        </div>

        {sessionLoading || loadingServer ? (
          <Card pad={isMobile ? 22 : 40} className="animate-fade-up-1" style={{ marginBottom: 32 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <Skeleton h={20} w="32%" />
              <Skeleton h={14} w="60%" />
              <div style={{ display: 'grid', gap: 14, gridTemplateColumns: gridCols(110) }}>
                <Skeleton h={56} /><Skeleton h={56} /><Skeleton h={56} /><Skeleton h={56} />
              </div>
            </div>
          </Card>
        ) : view ? (
          <>
            {/* Session meta */}
            <Card pad={isMobile ? 20 : 28} className="animate-fade-up-1" style={{ marginBottom: 28 }} accent="clay">
              <div style={{
                display: 'grid', gap: 18, marginBottom: 22,
                gridTemplateColumns: gridCols(180),
              }}>
                {[
                  { Icon: Hash,     tone: 'neutral' as const, label: 'Session ID',     value: view.sessionId.slice(0, 8) + '…',          accent: undefined },
                  { Icon: Calendar, tone: 'neutral' as const, label: 'Created',        value: <span style={{ fontSize: 14 }}>{formatDate(view.createdAt)}</span>, accent: undefined },
                  { Icon: Clock,    tone: 'neutral' as const, label: 'Updated',        value: <span style={{ fontSize: 14 }}>{formatDate(view.updatedAt)}</span>, accent: undefined },
                  { Icon: FileText, tone: 'clay'    as const, label: 'Total reports',  value: totalReports,                              accent: C.clay },
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
                display: 'flex', gap: 10, flexWrap: 'wrap',
                flexDirection: isMobile ? 'column' : 'row',
              }}>
                <Button variant="primary" size="md" disabled={exporting} block={isMobile}
                  iconLeft={<Download size={14} />} onClick={exportJson}>
                  {exporting ? 'Exporting…' : 'Export session JSON'}
                </Button>
                <Button variant="secondary" size="md" block={isMobile}
                  iconLeft={<RefreshCcw size={14} />} onClick={() => location.reload()}>
                  Refresh from server
                </Button>
                <Button variant="ghost" size="md" onClick={clearSession} block={isMobile}
                  style={{ color: C.rust }}>
                  Clear &amp; start new
                </Button>
              </div>
              <p style={{ marginTop: 16, fontSize: 11.5, color: C.ink3, lineHeight: 1.7 }}>
                Server JSON: <code style={{
                  background: C.surface2, padding: '2px 6px', borderRadius: 4,
                  fontFamily: F.mono, fontSize: 11, color: C.ink2,
                  wordBreak: 'break-all',
                }}>backend/sessions/{view.sessionId}.json</code>
                {' · '}Local cache key: <code style={{
                  background: C.surface2, padding: '2px 6px', borderRadius: 4,
                  fontFamily: F.mono, fontSize: 11, color: C.ink2,
                  wordBreak: 'break-all',
                }}>mobilityai_reports_v2</code>
              </p>
            </Card>

            {totalReports === 0 ? (
              <EmptyState
                kicker="No reports yet"
                title={<>Nothing saved here <em>yet.</em></>}
                body="Run an analysis and it'll appear here automatically — both locally and on the backend."
                ctaLabel="Start an assessment"
                onCta={onGuide}
              />
            ) : (
              <>
                {Object.keys(view.assessments.mobility.reports).length > 0 && (
                  <div className="animate-fade-up-2" style={{ marginBottom: 36 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                      <IconBadge tone="clay" size="sm"><Activity size={14} strokeWidth={1.8} /></IconBadge>
                      <SectionLabel>
                        Mobility · {Object.keys(view.assessments.mobility.reports).length} report{Object.keys(view.assessments.mobility.reports).length !== 1 ? 's' : ''}
                      </SectionLabel>
                    </div>
                    <div style={{
                      display: 'grid', gap: 18,
                      gridTemplateColumns: gridCols(460),
                    }}>
                      {Object.entries(view.assessments.mobility.reports).map(([slug, report]) => (
                        <ReportBlock key={slug} type="mobility" slug={slug} report={report}
                          isMobile={isMobile}
                          onOpen={() => onOpenReport('mobility', slug)}
                          onFrame={f => setOpenFrame(f)} />
                      ))}
                    </div>
                  </div>
                )}

                {Object.keys(view.assessments.strength.reports).length > 0 && (
                  <div className="animate-fade-up-3" style={{ marginBottom: 36 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                      <IconBadge tone="sage" size="sm"><Dumbbell size={14} strokeWidth={1.8} /></IconBadge>
                      <SectionLabel>
                        Strength · {Object.keys(view.assessments.strength.reports).length} report{Object.keys(view.assessments.strength.reports).length !== 1 ? 's' : ''}
                      </SectionLabel>
                    </div>
                    <div style={{
                      display: 'grid', gap: 18,
                      gridTemplateColumns: gridCols(460),
                    }}>
                      {Object.entries(view.assessments.strength.reports).map(([slug, report]) => (
                        <ReportBlock key={slug} type="strength" slug={slug} report={report}
                          isMobile={isMobile}
                          onOpen={() => onOpenReport('strength', slug)}
                          onFrame={f => setOpenFrame(f)} />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        ) : (
          <EmptyState
            kicker="No session"
            title={<>No session detected <em>yet.</em></>}
            body="Start an exercise to bootstrap a new session — your reports will live here once analysis runs."
            ctaLabel="Start an exercise"
            onCta={onGuide}
          />
        )}

        {/* Bottom nav */}
        <div style={{
          paddingTop: 28, marginTop: 8,
          borderTop: `1px solid ${C.border}`,
          display: 'flex',
          flexDirection: isMobile ? 'column-reverse' : 'row',
          justifyContent: 'space-between',
          alignItems: isMobile ? 'stretch' : 'center',
          flexWrap: 'wrap', gap: 12,
        }}>
          <Button variant="ghost" size="md" onClick={onLanding} block={isMobile}
            iconLeft={<span style={{ fontSize: 16 }}>←</span>}>Home</Button>
          <Button variant="primary" size="md" onClick={onGuide} block={isMobile}
            iconRight={<ArrowBadge size={30} />}
            style={isMobile ? { paddingRight: 6, justifyContent: 'space-between' } : { paddingRight: 6 }}>
            Continue assessing
          </Button>
        </div>
      </div>

      {openFrame && <FrameModal frame={openFrame} onClose={() => setOpenFrame(null)} />}
    </div>
  );
}
