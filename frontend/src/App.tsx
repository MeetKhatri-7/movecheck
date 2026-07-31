import { useState, useEffect } from 'react';
import { Routes, Route, useNavigate, useParams, Navigate } from 'react-router-dom';
import {
  getExercise, listExercises, isValidAssessmentType,
  type AssessmentType,
} from '@/data/registry';
import { useAppContext } from '@/context/AppContext';
import { FLAGSHIP_DEMO } from '@/services/demo';

import { LandingPage } from '@/pages/LandingPage';
import { ExerciseGuide } from '@/pages/ExerciseGuide';
import { InstructionPage } from '@/pages/InstructionPage';
import { ProcessingPage } from '@/pages/ProcessingPage';
import { ResultPage } from '@/pages/ResultPage';
import { Dashboard } from '@/pages/Dashboard';
import { SessionsPage } from '@/pages/SessionsPage';

function basePathFor(type: AssessmentType) {
  return `/assessments/${type}`;
}

/* ── Route-aware page wrappers ─────────────────────────────────── */

function LandingRoute() {
  const nav = useNavigate();
  const { enterDemoMode } = useAppContext();
  const [sampleLoading, setSampleLoading] = useState(false);

  const viewSample = async () => {
    setSampleLoading(true);
    try {
      await enterDemoMode();
      nav(`/assessments/${FLAGSHIP_DEMO.type}/${FLAGSHIP_DEMO.slug}/result`);
    } finally {
      setSampleLoading(false);
    }
  };

  return (
    <LandingPage
      onStartMobility={() => nav('/assessments/mobility')}
      onStartStrength={() => nav('/assessments/strength')}
      onSession={() => nav('/session')}
      onViewSample={viewSample}
      sampleLoading={sampleLoading}
    />
  );
}

function GuideRoute() {
  // Hooks must run unconditionally, before any early return — a conditional
  // hook call changes the hook count between renders and crashes React.
  const nav = useNavigate();
  const { type } = useParams();
  const { completed, reports, demoMode, demoAvailable } = useAppContext();
  if (!isValidAssessmentType(type)) return <Navigate to="/" replace />;
  const exercises = listExercises(type);

  // In demo mode every exercise with a pre-computed sample counts as
  // "available to view", even before its (lazy-loaded) JSON has arrived.
  const shown = demoMode
    ? new Set([...completed[type], ...demoAvailable[type]])
    : completed[type];

  return (
    <ExerciseGuide
      assessmentType={type}
      exercises={exercises}
      // In demo mode, jump straight to the report rather than the upload page.
      onSelect={(slug) => nav(
        demoMode && demoAvailable[type].has(slug)
          ? `${basePathFor(type)}/${slug}/result`
          : `${basePathFor(type)}/${slug}`,
      )}
      completed={shown}
      reports={reports[type]}
      onBack={() => nav('/')}
      onDashboard={() => nav(`${basePathFor(type)}/dashboard`)}
      onSession={() => nav('/session')}
    />
  );
}

function InstructionRoute() {
  const nav = useNavigate();
  const { type, slug } = useParams();
  const { uploads, setUpload, completed } = useAppContext();
  if (!isValidAssessmentType(type)) return <Navigate to="/" replace />;
  const ex = getExercise(type, slug || '');
  if (!ex) return <Navigate to={basePathFor(type)} replace />;
  return (
    <InstructionPage
      exercise={ex}
      completed={completed[type]}
      uploads={uploads}
      setUpload={setUpload}
      onAnalyse={() => nav(`${basePathFor(type)}/${ex.slug}/processing`)}
      onBack={() => nav(basePathFor(type))}
    />
  );
}

function ProcessingRoute() {
  const nav = useNavigate();
  const { type, slug } = useParams();
  const { uploads, setApiResult, saveReport } = useAppContext();
  if (!isValidAssessmentType(type)) return <Navigate to="/" replace />;
  const ex = getExercise(type, slug || '');
  if (!ex) return <Navigate to={basePathFor(type)} replace />;
  return (
    <ProcessingPage
      exercise={ex}
      assessmentType={type}
      uploads={uploads}
      onDone={async (result?: any) => {
        if (result) {
          setApiResult({ type, slug: ex.slug, result });
          // Don't persist error results — keep any previously-saved real
          // analysis intact so the user doesn't lose good data after a retry fails.
          if (!result._isError) {
            await saveReport(type, ex.slug, result);
          }
        }
        nav(`${basePathFor(type)}/${ex.slug}/result`);
      }}
    />
  );
}

function ResultRoute() {
  const nav = useNavigate();
  const { type, slug } = useParams();
  const {
    apiResult, reports, completed, setApiResult,
    demoMode, demoAvailable, loadDemo,
  } = useAppContext();

  const validType = isValidAssessmentType(type) ? type : null;
  const ex = validType ? getExercise(validType, slug || '') : null;
  const haveReport = !!(validType && ex && reports[validType][ex.slug]);

  // In demo mode, pull this exercise's sample report on demand so every
  // exercise is browsable without loading all 12 MB of samples up front.
  // Hooks must run unconditionally — the early returns come after.
  useEffect(() => {
    if (!demoMode || !validType || !ex || haveReport) return;
    if (!demoAvailable[validType]?.has(ex.slug)) return;
    void loadDemo(validType, ex.slug);
  }, [demoMode, validType, ex?.slug, haveReport, demoAvailable, loadDemo]);

  if (!validType) return <Navigate to="/" replace />;
  if (!ex) return <Navigate to={basePathFor(validType)} replace />;
  const type_ = validType;

  // Use the live result only when it belongs to THIS exercise — a stale
  // global result must not render on another exercise's page (reachable
  // via browser back/forward). Otherwise fall back to the saved report.
  const live = apiResult && apiResult.type === type_ && apiResult.slug === ex.slug
    ? apiResult.result
    : null;
  const result = live ?? reports[type_][ex.slug];
  const exercises = listExercises(type_);

  const goNext = () => {
    setApiResult(null);
    const idx = exercises.findIndex(e => e.id === ex.id);
    if (idx >= 0 && idx < exercises.length - 1) {
      nav(`${basePathFor(type_)}/${exercises[idx + 1].slug}`);
    } else {
      nav(`${basePathFor(type_)}/dashboard`);
    }
  };

  return (
    <ResultPage
      exercise={ex}
      apiResult={result}
      completed={completed[type_]}
      onNext={goNext}
      onRedo={() => { setApiResult(null); nav(`${basePathFor(type_)}/${ex.slug}`); }}
      onGuide={() => { setApiResult(null); nav(basePathFor(type_)); }}
      onDashboard={() => { setApiResult(null); nav(`${basePathFor(type_)}/dashboard`); }}
      onSession={() => { setApiResult(null); nav('/session'); }}
    />
  );
}

function DashboardRoute() {
  const nav = useNavigate();
  const { type } = useParams();
  const { reports, setApiResult } = useAppContext();
  if (!isValidAssessmentType(type)) return <Navigate to="/" replace />;
  const exercises = listExercises(type);
  return (
    <Dashboard
      assessmentType={type}
      exercises={exercises}
      reports={reports[type]}
      onOpenReport={(slug) => {
        const ex = getExercise(type, slug);
        if (!ex) return;
        // ResultRoute falls back to the saved report — no need to smuggle
        // it through the live-result slot (which caused stale cross-exercise
        // renders); just clear any leftover live result.
        setApiResult(null);
        nav(`${basePathFor(type)}/${ex.slug}/result`);
      }}
      onGuide={() => nav(basePathFor(type))}
      onLanding={() => nav('/')}
      onSession={() => nav('/session')}
    />
  );
}

function SessionsRoute() {
  const nav = useNavigate();
  const { setApiResult } = useAppContext();
  return (
    <SessionsPage
      onOpenReport={(type, slug) => {
        const ex = getExercise(type, slug);
        if (!ex) return;
        setApiResult(null);
        nav(`${basePathFor(type)}/${ex.slug}/result`);
      }}
      onGuide={() => nav('/assessments/mobility')}
      onLanding={() => nav('/')}
      onBack={() => nav(-1 as any)}
    />
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingRoute />} />
      <Route path="/session"  element={<SessionsRoute />} />
      <Route path="/sessions" element={<SessionsRoute />} />
      <Route path="/assessments/:type" element={<GuideRoute />} />
      <Route path="/assessments/:type/dashboard" element={<DashboardRoute />} />
      <Route path="/assessments/:type/:slug" element={<InstructionRoute />} />
      <Route path="/assessments/:type/:slug/processing" element={<ProcessingRoute />} />
      <Route path="/assessments/:type/:slug/result" element={<ResultRoute />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
