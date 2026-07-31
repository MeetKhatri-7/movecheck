import { useEffect, useRef, useState } from 'react';
import {
  Sun, Smartphone, Shirt, Crosshair, RotateCw, SplitSquareHorizontal, Scissors,
  Camera, Brain, FileBarChart, Sparkles, PlayCircle,
} from 'lucide-react';
import { Button, ArrowBadge } from '@/components/ui/Button';
import { Logo } from '@/components/ui/Logo';
import { ImageSlot } from '@/components/ui/ImageSlot';
import { C, F, R } from '@/theme/tokens';
import { useKeyboard } from '@/hooks/useKeyboard';

const rules: { n: string; t: string; b: string; Icon: React.ComponentType<any> }[] = [
  { n: '01', t: 'Well-lit space',         b: 'Plain background where possible.',                            Icon: Sun },
  { n: '02', t: 'Propped phone',          b: 'Use a tripod or a stable surface — never hand-held.',         Icon: Smartphone },
  { n: '03', t: 'Fitted clothing',        b: 'Joints must be visible. Avoid baggy shorts or tops.',         Icon: Shirt },
  { n: '04', t: 'Exact camera angle',     b: 'The angle listed for each exercise is the angle we score.',   Icon: Crosshair },
  { n: '05', t: 'Slow, controlled reps',  b: 'Three good reps beat ten messy ones.',                        Icon: RotateCw },
  { n: '06', t: 'Both sides, separately', b: 'For unilateral exercises, film left and right separately.',    Icon: SplitSquareHorizontal },
  { n: '07', t: 'One take per clip',      b: 'Trim before uploading; the analyzer expects a single attempt.', Icon: Scissors },
];

const features = [
  { Icon: Camera,       t: 'Phone-only setup', b: 'Record on the phone you already have. No wearables, no gym membership.' },
  { Icon: Brain,        t: 'Coach-grade AI',   b: 'MediaPipe Pose + custom biomechanics — the same metrics a strength coach reads.' },
  { Icon: FileBarChart, t: 'Honest reports',   b: 'Per-rep faults with timing, confidence pills, side-by-side bilateral comparison.' },
  { Icon: Sparkles,     t: 'Track progress',   b: 'Every session saved. Re-test the same lift weekly to see real change.' },
];

const MARQUEE = ['10 MOBILITY TESTS', '5 STRENGTH LIFTS', 'PHONE-ONLY CAPTURE', 'COACH-GRADE AI', 'ZERO GUESSWORK'];

interface LandingProps {
  onStartMobility: () => void;
  onStartStrength: () => void;
  onSession?: () => void;
  /** Open a pre-computed sample report instantly (demo mode). */
  onViewSample?: () => void;
  /** True while the sample report JSON is being fetched. */
  sampleLoading?: boolean;
}

/** Scroll-reveal hook — fades a block up the first time it enters view. */
function useReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { setShown(true); obs.disconnect(); } });
    }, { threshold: 0.12 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, shown };
}

export function LandingPage({
  onStartMobility, onStartStrength, onSession, onViewSample, sampleLoading,
}: LandingProps) {
  const [score, setScore] = useState(0);
  const features_ = useReveal<HTMLDivElement>();
  const rules_ = useReveal<HTMLDivElement>();
  const cta_ = useReveal<HTMLDivElement>();

  // Animated hero score counter → 87.
  useEffect(() => {
    const target = 87, duration = 1200, start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      setScore(Math.round(p * target));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  useKeyboard({ onEnter: onStartMobility, map: { m: onStartMobility, s: onStartStrength } });

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.ink, overflowX: 'hidden' }}>
      {/* ── NAV ─────────────────────────────────────────── */}
      <nav style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '22px clamp(20px,4vw,48px)', borderBottom: `1px solid ${C.border}`,
        position: 'sticky', top: 0, background: 'rgba(10,13,16,0.85)',
        backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)', zIndex: 50,
      }}>
        <Logo size={30} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
          <span style={{
            fontSize: 11, letterSpacing: '1.5px', color: C.ink4, fontWeight: 600,
            textTransform: 'uppercase', display: 'none',
          }} className="mc-nav-tag">Movement Assessment · By Film</span>
          {onSession && (
            <button onClick={onSession} style={{
              background: 'rgba(255,255,255,0.05)', backdropFilter: 'blur(10px)',
              border: `1px solid ${C.borderStrong}`, color: C.ink,
              padding: '10px 20px', borderRadius: R.pill, fontSize: 13, fontWeight: 600,
              letterSpacing: '0.3px', cursor: 'pointer', fontFamily: F.body,
              transition: 'border-color .2s, color .2s',
            }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = C.borderClay; e.currentTarget.style.color = C.clay; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = C.borderStrong; e.currentTarget.style.color = C.ink; }}>
              My Session
            </button>
          )}
        </div>
      </nav>

      {/* ── MARQUEE ─────────────────────────────────────── */}
      <div style={{
        background: C.clay, overflow: 'hidden', padding: '9px 0',
        borderBottom: `2px solid ${C.bg}`, transform: 'skewY(-0.6deg)', marginTop: -1,
      }}>
        <div style={{ display: 'flex', width: 'max-content', animation: 'marquee 22s linear infinite' }}>
          {[0, 1].map(dup => (
            <span key={dup} aria-hidden={dup === 1} style={{
              display: 'flex', gap: 36, paddingRight: 36, fontFamily: F.display,
              fontSize: 16, letterSpacing: '2px', color: C.bg, whiteSpace: 'nowrap',
            }}>
              {MARQUEE.map((m, i) => (
                <span key={i} style={{ display: 'flex', gap: 36 }}><span>{m}</span><span>◆</span></span>
              ))}
            </span>
          ))}
        </div>
      </div>

      {/* ── HERO ─────────────────────────────────────────── */}
      <section style={{
        padding: 'clamp(56px,8vw,96px) clamp(20px,4vw,48px) 80px',
        display: 'grid', gridTemplateColumns: 'minmax(0,1.05fr) minmax(0,0.95fr)',
        gap: 'clamp(32px,5vw,64px)', alignItems: 'center', maxWidth: 1560, margin: '0 auto',
      }} className="mc-hero">
        <div className="animate-fade-up">
          <div style={{ fontSize: 12, letterSpacing: '2px', color: C.clay, fontWeight: 700, marginBottom: 22, textTransform: 'uppercase' }}>
            10 Mobility Tests · 5 Strength Lifts
          </div>
          <h1 style={{ fontFamily: F.display, fontSize: 'clamp(60px,9vw,108px)', lineHeight: 0.92, letterSpacing: '0.5px', margin: '0 0 28px', color: C.ink }}>
            KNOW HOW<br />YOUR BODY<br /><span style={{ color: C.clay }}>MOVES.</span>
          </h1>
          <p style={{ fontSize: 17, lineHeight: 1.7, color: C.ink3, maxWidth: 480, margin: '0 0 40px' }}>
            Two tracks, one honest profile. Mobility tests how your joints move; Strength tests how
            much force you produce. Record a few clips, get a coach-grade report back — no guesswork,
            no gym jargon.
          </p>
          <div style={{ display: 'flex', gap: 14, marginBottom: 22, flexWrap: 'wrap' }}>
            <Button variant="primary" size="lg" onClick={onStartMobility}
              iconRight={<ArrowBadge />} style={{ paddingLeft: 26, paddingRight: 8, animation: 'ctaGlow 3s ease-in-out infinite' }}>
              BEGIN MOBILITY
            </Button>
            <Button variant="secondary" size="lg" onClick={onStartStrength}
              iconRight={<ArrowBadge onDark={false} />} style={{ paddingLeft: 26, paddingRight: 8 }}>
              BEGIN STRENGTH
            </Button>
          </div>

          {/* Zero-friction entry point. Recording and analysing a clip takes
              minutes; this shows a real, fully-rendered report immediately. */}
          {onViewSample && (
            <div style={{ marginBottom: 22 }}>
              <button
                onClick={onViewSample}
                disabled={sampleLoading}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 10,
                  background: 'none', border: 'none', padding: '6px 0',
                  cursor: sampleLoading ? 'wait' : 'pointer',
                  color: C.ink2, fontSize: 14, fontWeight: 600,
                  fontFamily: 'inherit',
                  borderBottom: `1px solid ${C.border}`,
                  opacity: sampleLoading ? 0.6 : 1,
                }}
              >
                <PlayCircle size={18} />
                {sampleLoading ? 'Loading sample report…' : 'See a real report — no upload, no wait'}
              </button>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11, letterSpacing: '1px', color: C.ink4, fontWeight: 600, textTransform: 'uppercase', flexWrap: 'wrap' }}>
            <span>Shortcuts</span>
            <Kbd>↵</Kbd><span>start mobility</span>
            <Kbd>M</Kbd><Kbd>S</Kbd><span>pick a track</span>
          </div>
        </div>

        {/* Hero visual */}
        <div style={{ position: 'relative', animation: 'fadeUp 0.9s ease 0.15s both, float 5s ease-in-out 1s infinite' }} className="mc-hero-visual">
          <ImageSlot
            src="/images/landing/hero.jpg"
            alt="Athlete captured mid-squat, coach-grade form analysis"
            aspect="4/5" radius={28} mark="M" caption="Movement, measured" scrim
            style={{ border: `1px solid ${C.border}` }}
          />
          <div style={{
              position: 'absolute', top: 24, right: 24, background: 'rgba(10,13,16,0.6)',
              backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
              border: `1px solid ${C.borderClay}`, padding: '14px 18px', borderRadius: 14,
            }}>
              <div style={{ fontSize: 10, letterSpacing: '1.5px', color: C.ink4, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase' }}>Squat Depth</div>
              <div style={{ fontFamily: F.display, fontSize: 34, color: C.clay }}>{score}<span style={{ fontSize: 16, color: C.ink4 }}>/100</span></div>
            </div>
            <div style={{
              position: 'absolute', bottom: 24, left: 24, display: 'flex', alignItems: 'center', gap: 8,
              background: 'rgba(10,13,16,0.5)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
              border: `1px solid ${C.border}`, padding: '9px 14px', borderRadius: 20,
            }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.indigo, animation: 'pulseDot 1.4s ease-in-out infinite' }} />
              <span style={{ fontSize: 11, letterSpacing: '1px', color: C.ink2, fontWeight: 600 }}>33 KEYPOINTS · LIVE</span>
            </div>
        </div>
      </section>

      {/* ── FEATURES ─────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,48px) 100px', maxWidth: 1560, margin: '0 auto' }}>
        <div ref={features_.ref} style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 18,
          opacity: features_.shown ? 1 : 0, transform: features_.shown ? 'translateY(0)' : 'translateY(28px)',
          transition: 'opacity .7s ease, transform .7s ease',
        }}>
          {features.map(({ Icon, t, b }, i) => (
            <div key={i} className="mc-card-hover" style={{
              background: C.surface, backdropFilter: C.glassBlur, WebkitBackdropFilter: C.glassBlur,
              border: `1px solid ${C.border}`, borderRadius: 18, padding: '34px 28px',
              transition: 'transform .3s, border-color .3s, box-shadow .3s',
            }}>
              <div style={{ width: 38, height: 38, borderRadius: 10, background: C.clayTint, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
                <Icon size={18} strokeWidth={1.8} color={C.clay} />
              </div>
              <div style={{ fontFamily: F.display, fontSize: 22, letterSpacing: '0.4px', marginBottom: 10, textTransform: 'uppercase' }}>{t}</div>
              <div style={{ fontSize: 14, lineHeight: 1.6, color: C.ink3 }}>{b}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── RULES ─────────────────────────────────────────── */}
      <section style={{
        position: 'relative', background: C.bg2, padding: 'clamp(80px,10vw,120px) clamp(20px,4vw,48px) 100px',
        clipPath: 'polygon(0 3.5%, 100% 0, 100% 100%, 0 100%)',
      }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', textAlign: 'center' }}>
          <div style={{ fontSize: 12, letterSpacing: '2.5px', color: C.indigo, fontWeight: 700, marginBottom: 20, textTransform: 'uppercase' }}>Required Reading Before You Film</div>
          <h2 style={{ fontFamily: F.display, fontSize: 'clamp(40px,6vw,64px)', letterSpacing: '0.5px', margin: '0 0 24px', lineHeight: 1.02 }}>
            SEVEN RULES FOR <span style={{ color: C.clay }}>CLEAN FOOTAGE.</span>
          </h2>
          <p style={{ fontSize: 16, lineHeight: 1.7, color: C.ink3, maxWidth: 620, margin: '0 auto 64px' }}>
            The analyzer is opinionated — small camera-angle mistakes shave 10+ accuracy points off
            your report. Treat these like a checklist, not suggestions.
          </p>
        </div>

        <div ref={rules_.ref} style={{
          maxWidth: 1080, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 16,
          opacity: rules_.shown ? 1 : 0, transform: rules_.shown ? 'translateY(0)' : 'translateY(28px)',
          transition: 'opacity .7s ease, transform .7s ease',
        }}>
          {rules.map(({ n, t, b, Icon }, i) => {
            const isLast = i === rules.length - 1;
            return (
              <div key={i} className="mc-card-hover" style={{
                gridColumn: isLast ? '1 / -1' : undefined,
                display: 'flex', gap: 18,
                background: isLast ? 'linear-gradient(135deg, rgba(255,90,54,0.08), rgba(51,199,255,0.05))' : C.surface,
                backdropFilter: C.glassBlur, WebkitBackdropFilter: C.glassBlur,
                border: `1px solid ${isLast ? C.borderClay : C.border}`, borderRadius: 16, padding: 24,
                transition: 'transform .3s, border-color .3s, box-shadow .3s',
              }}>
                <div style={{ flexShrink: 0, width: 48, height: 48, borderRadius: 12, background: C.clayTint, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon size={22} strokeWidth={1.8} color={C.clay} />
                </div>
                <div>
                  <div style={{ fontFamily: F.display, fontSize: 12, letterSpacing: '2px', color: C.clay, marginBottom: 4 }}>RULE {n}</div>
                  <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6 }}>{t}</div>
                  <div style={{ fontSize: 13, color: C.ink3, lineHeight: 1.6 }}>{b}</div>
                </div>
              </div>
            );
          })}
        </div>

        <div ref={cta_.ref} style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, marginTop: 72,
          opacity: cta_.shown ? 1 : 0, transform: cta_.shown ? 'translateY(0)' : 'translateY(20px)',
          transition: 'opacity .7s ease, transform .7s ease',
        }}>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', justifyContent: 'center' }}>
            <Button variant="primary" size="lg" onClick={onStartMobility} iconRight={<ArrowBadge />} style={{ paddingLeft: 26, paddingRight: 8 }}>BEGIN MOBILITY</Button>
            <Button variant="secondary" size="lg" onClick={onStartStrength} iconRight={<ArrowBadge onDark={false} />} style={{ paddingLeft: 26, paddingRight: 8 }}>BEGIN STRENGTH</Button>
          </div>
          <div style={{ fontSize: 11, letterSpacing: '1.5px', color: C.ink4, fontWeight: 700, textTransform: 'uppercase' }}>Choose a track · do both for your full profile</div>
        </div>
      </section>

      {/* ── FOOTER ─────────────────────────────────────────── */}
      <footer style={{ padding: '26px clamp(20px,4vw,48px)', borderTop: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <span style={{ fontSize: 11, letterSpacing: '1.5px', color: C.ink4, fontWeight: 700, textTransform: 'uppercase' }}>MoveCheck · V2 · Athletic Release</span>
        <Logo size={18} />
      </footer>
    </div>
  );
}

/** Tiny keyboard-shortcut indicator. */
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: 22, height: 22, background: 'rgba(255,255,255,0.05)',
      border: `1px solid ${C.border}`, borderRadius: 4,
      fontFamily: F.mono, fontSize: 11, fontWeight: 500, color: C.ink3, padding: '0 6px',
    }}>
      {children}
    </span>
  );
}