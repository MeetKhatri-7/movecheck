import { useEffect, useRef, useState } from 'react';
import type { Exercise } from '@/data/types';
import type { AssessmentType } from '@/data/registry';
import { uploadAndAnalyse, getJobStatus, type AnalyseParams } from '@/services/api';
import { getStoredSessionId } from '@/services/session';
import { uploadKeyPrefix, uploadFieldFromKey } from '@/data/uploadKeys';
import { useAppContext } from '@/context/AppContext';
import { Logo } from '@/components/ui';
import { C, F } from '@/theme/tokens';
import { Film, Scan, Activity, Ruler, Users, FileBarChart } from 'lucide-react';

const stages = [
  { label: 'Extracting frames',         detail: 'Sampling video at 30 fps',                 Icon: Film },
  { label: 'Detecting body landmarks',  detail: 'Running pose estimation',                  Icon: Scan },
  { label: 'Tracking joint angles',     detail: 'Computing kinematics frame by frame',      Icon: Activity },
  { label: 'Range-of-motion analysis',  detail: 'Measuring peak & average angles',          Icon: Ruler },
  { label: 'Bilateral comparison',      detail: 'Left vs right symmetry',                   Icon: Users },
  { label: 'Generating report',         detail: 'Applying clinical thresholds',             Icon: FileBarChart },
];

function buildErrorResult(message: string) {
  return {
    status: 'RESTRICTED',
    score: 0,
    summary: `Analysis failed: ${message}`,
    stats: { validReps: '0/0', confidence: '0%', sides: 'error', cameraView: 'ERROR' },
    metrics: [], bilateral: [],
    coaching: [
      `Error: ${message}`,
      'Check that both videos uploaded successfully and the camera angles match the setup spec.',
      'Open the browser console and Python/Node server logs for the full stack trace.',
    ],
    annotated_frames: [], per_rep: [], _isError: true,
  };
}

interface ProcessingProps {
  exercise: Exercise;
  assessmentType: AssessmentType;
  uploads: Record<string, File>;
  onDone: (res?: any) => void;
}

export function ProcessingPage({ exercise, assessmentType, uploads, onDone }: ProcessingProps) {
  const { profile, exerciseInputs } = useAppContext();
  const [stageIdx, setStageIdx] = useState(0);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null);
  const doneRef = useRef(false);

  useEffect(() => {
    let jobId = '';
    let pollInt: ReturnType<typeof setInterval>;

    const startProcessing = async () => {
      try {
        // Keys are namespaced by (type, slug) so another exercise's videos —
        // including one from the other assessment track — can never leak in.
        const prefix = uploadKeyPrefix(assessmentType, exercise.slug);
        const exUploads: Record<string, File> = {};
        Object.entries(uploads).forEach(([k, v]) => {
          if (k.startsWith(prefix)) {
            exUploads[uploadFieldFromKey(k)] = v;
          }
        });

        const sessionId = getStoredSessionId() ?? undefined;
        const params: AnalyseParams = {};
        if (profile.tibiaLengthCm) params.tibiaLengthCm = profile.tibiaLengthCm;

        // Forward every field the Node API whitelists — this list must stay
        // in sync with `passthroughFields` in backend/server.js. Previously
        // the per-view rep counts and style fields collected by the strength
        // forms were silently dropped here and analyzers ran on defaults.
        const slugInputs = exerciseInputs[exercise.slug] || {};
        const numericKeys: (keyof AnalyseParams)[] = [
          'loadKg', 'plateSizeKg', 'inclineDeg', 'backrestDeg', 'athleteHeightCm',
          'weightMax', 'repsMax',
          'targetReps', 'targetRepsSide', 'targetRepsFront',
          'targetRepsSagittal', 'targetRepsOverhead', 'targetRepsHeadEnd',
          'targetRepsFrontal', 'targetRepsPosterior', 'targetRepsOblique',
        ];
        for (const k of numericKeys) {
          const v = slugInputs[k as string];
          if (typeof v === 'number' && !isNaN(v)) (params as any)[k] = v;
          else if (typeof v === 'string' && v !== '') {
            const n = parseFloat(v);
            if (!isNaN(n)) (params as any)[k] = n;
          }
        }
        const stringKeys: (keyof AnalyseParams)[] = [
          'variant', 'grip', 'stance', 'style', 'paused',
        ];
        for (const k of stringKeys) {
          const v = slugInputs[k as string];
          if (typeof v === 'string' && v !== '') (params as any)[k] = v;
        }

        const res = await uploadAndAnalyse(assessmentType, exercise.slug, exUploads, sessionId, params);
        jobId = res.jobId;

        // Polling must always terminate. A 404 means the backend restarted
        // and lost the in-memory job — retrying can never succeed, so fail
        // immediately. Other errors (transient network) get a bounded number
        // of consecutive retries before giving up.
        const MAX_CONSECUTIVE_POLL_FAILURES = 15;
        let consecutiveFailures = 0;
        const failTerminal = (msg: string) => {
          clearInterval(pollInt);
          doneRef.current = true;
          setDone(true);
          setProgress(100);
          setTimeout(() => onDone(buildErrorResult(msg)), 900);
        };
        pollInt = setInterval(async () => {
          try {
            const status = await getJobStatus(jobId);
            consecutiveFailures = 0;
            if (status.status === 'complete') {
              clearInterval(pollInt);
              doneRef.current = true;
              setDone(true);
              setProgress(100);
              setStageIdx(stages.length - 1);
              setTimeout(() => onDone(status.result), 900);
            } else if (status.status === 'error') {
              failTerminal(status.error || 'Analysis failed for an unknown reason.');
            }
          } catch (e: any) {
            if (e?.response?.status === 404) {
              failTerminal('The analysis job was lost — the server likely restarted mid-processing. Please try again.');
              return;
            }
            consecutiveFailures += 1;
            console.error(`Polling error (${consecutiveFailures}/${MAX_CONSECUTIVE_POLL_FAILURES})`, e);
            if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
              failTerminal('Lost contact with the server while waiting for results — check that the backend is running and try again.');
            }
          }
        }, 1000);
      } catch (error: any) {
        doneRef.current = true;
        setDone(true);
        setProgress(100);
        const errMsg = error?.message || 'Upload failed — check your network and try again.';
        setTimeout(() => onDone(buildErrorResult(errMsg)), 900);
      }
    };

    startProcessing();

    let s = 0;
    const next = () => {
      if (doneRef.current) return;
      setStageIdx(s);
      timerRef.current = setTimeout(() => {
        if (s < stages.length - 1 && !doneRef.current) { s++; next(); }
      }, 1100);
    };
    next();

    let elapsed = 0;
    const totalApprox = 1100 * stages.length;
    const progInt = setInterval(() => {
      elapsed += 50;
      setProgress(() => {
        if (doneRef.current) return 100;
        return Math.min((elapsed / totalApprox) * 100, 95);
      });
    }, 50);

    return () => {
      clearInterval(progInt);
      if (pollInt) clearInterval(pollInt);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const RING_C = 402.1; // 2πr, r=64
  const ringOffset = RING_C - (RING_C * progress) / 100;

  return (
    <div style={{
      position: 'relative', minHeight: '100vh', background: C.bg, color: C.ink,
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: 'clamp(32px,7vw,60px) clamp(16px,4.5vw,24px) clamp(56px,10vw,100px)',
      overflow: 'hidden',
    }}>
      <div aria-hidden style={{
        position: 'fixed', inset: 0, zIndex: 0,
        backgroundImage: `linear-gradient(180deg, ${C.bg}f2 0%, ${C.bg}fa 60%, ${C.bg} 100%), url(/images/processing/ambient-bg.jpg)`,
        backgroundSize: 'cover', backgroundPosition: 'center',
      }} />
      <div style={{ position: 'relative', zIndex: 1, marginBottom: 'clamp(24px,5vw,40px)' }}><Logo size={24} /></div>

      {/* Main card with gradient progress ring */}
      <div style={{
        position: 'relative', zIndex: 1,
        width: '100%', maxWidth: 640, background: C.surface,
        backdropFilter: C.glassBlur, WebkitBackdropFilter: C.glassBlur,
        border: `1px solid ${C.border}`, borderRadius: 22, padding: 'clamp(28px,5vw,44px)',
        textAlign: 'center', animation: 'fadeUp .6s ease both',
      }}>
        <div style={{ position: 'relative', width: 'min(150px, 42vw)', aspectRatio: '1/1', margin: '0 auto 28px' }}>
          <svg viewBox="0 0 150 150" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', animation: 'ringGlow 2.4s ease-in-out infinite' }}>
            <defs>
              <linearGradient id="mcRingGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor={C.clay} />
                <stop offset="100%" stopColor={C.indigo} />
              </linearGradient>
            </defs>
            <circle cx="75" cy="75" r="64" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="9" />
            <circle cx="75" cy="75" r="64" fill="none" stroke="url(#mcRingGrad)" strokeWidth="9"
              strokeLinecap="round" strokeDasharray={RING_C} strokeDashoffset={ringOffset}
              transform="rotate(-90 75 75)" style={{ transition: 'stroke-dashoffset .6s ease' }} />
          </svg>
          <div style={{ position: 'absolute', inset: 6, borderRadius: '50%', border: '1px dashed rgba(255,255,255,0.12)', animation: 'ringRotate 12s linear infinite' }} />
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontFamily: F.display, fontSize: 'clamp(28px,9vw,38px)', letterSpacing: '0.5px' }}>{Math.round(progress)}<span style={{ fontSize: 18, color: C.ink3 }}>%</span></span>
            <span style={{ fontSize: 9, letterSpacing: '1.5px', color: C.ink4, fontWeight: 700 }}>ANALYSING</span>
          </div>
        </div>

        <div style={{ fontFamily: F.display, fontSize: 'clamp(22px,5.5vw,28px)', letterSpacing: '0.4px', marginBottom: 10, textTransform: 'uppercase' }}>
          {done ? 'Compiling Your Report' : 'Analysing Your Movement'}
        </div>
        <div style={{ fontSize: 14, color: C.ink3, marginBottom: 'clamp(22px,5vw,32px)' }}>
          {done ? "You'll see your report in a moment." : 'Hang tight — this usually takes under a minute.'}
        </div>

        <div style={{ height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 4, overflow: 'hidden', marginBottom: 'clamp(24px,5vw,36px)' }}>
          <div style={{ height: '100%', background: `linear-gradient(90deg, ${C.clay}, ${C.clayHover})`, borderRadius: 4, width: `${progress}%`, transition: 'width .5s ease' }} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, textAlign: 'left' }}>
          {stages.map(({ label }, i) => {
            const isCurrent = i === stageIdx && !done;
            const isDone = i < stageIdx || done;
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 14,
                padding: 'clamp(10px,2.5vw,12px) clamp(10px,3vw,16px)', borderRadius: 12,
                background: isCurrent ? C.clayTint : 'transparent', transition: 'background .3s',
              }}>
                <div style={{
                  width: 30, height: 30, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: isDone ? C.sageTint : isCurrent ? C.clayTint : 'rgba(255,255,255,0.06)',
                  color: isDone ? C.sage : isCurrent ? C.clay : C.ink4, flexShrink: 0,
                  fontSize: 13, transition: 'all .3s',
                }}>{isDone ? '✓' : isCurrent ? '●' : '○'}</div>
                <span style={{ fontSize: 'clamp(13px,3.4vw,14px)', fontWeight: 600, color: isDone || isCurrent ? C.ink : C.ink4 }}>{label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Skeleton preview */}
      <div style={{
        position: 'relative', zIndex: 1,
        width: '100%', maxWidth: 640, marginTop: 24, background: C.surface2,
        border: `1px solid ${C.border}`, borderRadius: 22,
        padding: 'clamp(20px,5vw,32px)', animation: 'fadeUp .6s ease .1s both',
      }}>
        <div style={{ fontSize: 11, letterSpacing: '1.5px', color: C.ink4, fontWeight: 700, marginBottom: 18, textTransform: 'uppercase' }}>Your report will look like this</div>
        <div style={{ display: 'flex', gap: 20, marginBottom: 20 }}>
          <div className="skeleton" style={{ width: 70, height: 70, borderRadius: '50%' }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, justifyContent: 'center' }}>
            <div className="skeleton" style={{ height: 12, width: '60%' }} />
            <div className="skeleton" style={{ height: 10, width: '40%' }} />
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
          {[0, 1, 2].map(i => <div key={i} className="skeleton" style={{ height: 64, borderRadius: 12 }} />)}
        </div>
      </div>
    </div>
  );
}
