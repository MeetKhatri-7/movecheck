import { useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { useParams } from 'react-router-dom';
import { Nav, ExerciseProgressBar } from '@/components/shared';
import type { Exercise, ExerciseRef, ExerciseUpload } from '@/data/types';
import { listExercises, isValidAssessmentType } from '@/data/registry';
import { uploadKey } from '@/data/uploadKeys';
import { useAppContext } from '@/context/AppContext';
import {
  Button, Card, Pill, SectionLabel, Display,
} from '@/components/ui';
import { ArrowBadge } from '@/components/ui/Button';
import { C, F, R, GUTTER, gridCols } from '@/theme/tokens';
import { useKeyboard } from '@/hooks/useKeyboard';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { CheckCircle2, Upload as UploadIcon, X, Video, Camera, BookOpen, Image as ImageIcon } from 'lucide-react';

interface Props {
  exercise: Exercise;
  completed: Set<string>;
  uploads: Record<string, File>;
  setUpload: (key: string, file: File) => void;
  onAnalyse: () => void;
  onBack: () => void;
}

/* ── Strength input config (UNCHANGED — same data shape as before) ── */
type StrengthField = {
  key: string; label: string; type: 'select' | 'number';
  options?: { value: string; label: string }[];
  unit?: string; min?: number; max?: number; step?: number;
  placeholder?: string; defaultValue?: string | number;
};

const STRENGTH_INPUT_CONFIG: Record<string, StrengthField[]> = {
  'back-squat': [
    { key: 'variant', label: 'Variant', type: 'select', defaultValue: 'high-bar',
      options: [
        { value: 'high-bar', label: 'High bar squat' },
        { value: 'low-bar',  label: 'Low bar squat' },
      ] },
    { key: 'weightMax',       label: 'Weight max (RM)',  type: 'number', unit: 'kg',   min: 0, max: 500, step: 0.5, placeholder: '100' },
    { key: 'repsMax',         label: 'Reps max (RM)',    type: 'number', unit: 'reps', min: 1, max: 30,  step: 1,   placeholder: '1', defaultValue: 1 },
    { key: 'targetRepsSide',  label: 'Reps in side video',  type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'targetRepsFront', label: 'Reps in front video', type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'plateSizeKg', label: 'Plate size', type: 'select', defaultValue: 20,
      options: [
        { value: '25', label: '25 kg (450 mm)' }, { value: '20', label: '20 kg (450 mm)' },
        { value: '15', label: '15 kg (400 mm)' }, { value: '10', label: '10 kg (320 mm)' },
        { value: '5',  label: '5 kg (230 mm)' },
      ] },
  ],
  'deadlift': [
    { key: 'variant', label: 'Variant', type: 'select', defaultValue: 'conventional',
      options: [
        { value: 'conventional', label: 'Conventional' },
        { value: 'romanian',     label: 'Romanian' },
      ] },
    { key: 'weightMax',  label: 'Weight max (RM)',     type: 'number', unit: 'kg',   min: 0, max: 500, step: 0.5, placeholder: '140' },
    { key: 'repsMax',    label: 'Reps max (RM)',       type: 'number', unit: 'reps', min: 1, max: 30,  step: 1,   placeholder: '1', defaultValue: 1 },
    // ONE shared rep count — all four camera clips capture the SAME set, so the
    // rep count is identical across them. The analyzer detects reps on the
    // sagittal clip and fuses the other three views into those same reps.
    { key: 'targetReps', label: 'Reps in the set (same in all 4 clips)', type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'plateSizeKg', label: 'Plate size', type: 'select', defaultValue: 20,
      options: [
        { value: '25', label: '25 kg (450 mm)' }, { value: '20', label: '20 kg (450 mm)' },
        { value: '15', label: '15 kg (400 mm)' }, { value: '10', label: '10 kg (320 mm)' },
      ] },
  ],
  'bench-press': [
    { key: 'variant', label: 'Variant', type: 'select', defaultValue: 'flat',
      options: [
        { value: 'flat',    label: 'Flat' },
        { value: 'incline', label: 'Incline' },
      ] },
    { key: 'style', label: 'Style (Flat only)', type: 'select', defaultValue: 'powerlifting',
      options: [
        { value: 'powerlifting', label: 'Powerlifting (low touch, tucked, arch, wide grip ≤81 cm)' },
        { value: 'bodybuilding', label: 'Bodybuilding (mid-chest touch, ~60–75° flare, minimal arch)' },
      ] },
    { key: 'inclineDeg', label: 'Incline angle (Incline only)', type: 'number', unit: '°', min: 15, max: 60, step: 5, placeholder: '30', defaultValue: 30 },
    { key: 'paused',     label: 'Paused vs touch-and-go',       type: 'select', defaultValue: 'paused',
      options: [
        { value: 'paused', label: 'Paused (≥0.5 s motionless on chest)' },
        { value: 'tng',    label: 'Touch-and-go' },
      ] },
    { key: 'weightMax',  label: 'Weight max',    type: 'number', unit: 'kg',   min: 0, max: 300, step: 0.5, placeholder: '80' },
    { key: 'repsMax',    label: 'Reps max (RM)', type: 'number', unit: 'reps', min: 1, max: 30,  step: 1,   placeholder: '1', defaultValue: 1 },
    // Per-camera rep counts — the analyzer trusts these inputs verbatim
    // (touch-frame detector picks exactly N extreme positions per video).
    { key: 'targetRepsSagittal', label: 'Reps · sagittal video',  type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'targetRepsOverhead', label: 'Reps · overhead video',  type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'targetRepsHeadEnd',  label: 'Reps · head-end video',  type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'targetRepsOblique',  label: 'Reps · oblique video',   type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'plateSizeKg', label: 'Plate size', type: 'select', defaultValue: 20,
      options: [
        { value: '25', label: '25 kg (450 mm)' }, { value: '20', label: '20 kg (450 mm)' },
        { value: '15', label: '15 kg (400 mm)' }, { value: '10', label: '10 kg (320 mm)' },
      ] },
  ],
  'pull-up': [
    { key: 'grip', label: 'Grip', type: 'select', defaultValue: 'pronated',
      options: [
        { value: 'pronated',  label: 'Pronated (overhand, palms away — the standard)' },
        { value: 'supinated', label: 'Supinated (chin-up, palms toward face)' },
        { value: 'neutral',   label: 'Neutral (palms facing each other / parallel bars)' },
        { value: 'wide',      label: 'Wide (≥1.5× biacromial, pronated)' },
      ] },
    { key: 'style', label: 'Style', type: 'select', defaultValue: 'strict',
      options: [
        { value: 'strict',    label: 'Strict (dead-hang each rep, no swing)' },
        { value: 'kipping',   label: 'Kipping (CrossFit hollow-arch transitions)' },
        { value: 'butterfly', label: 'Butterfly (continuous circular kip)' },
        { value: 'sternum',   label: 'Sternum chin-up (Gironda, pronounced layback)' },
        { value: 'c2b',       label: 'Chest-to-bar (chin clears + sternum contact)' },
        { value: 'tactical',  label: 'Tactical (StrongFirst, thumbless, motionless dead hang)' },
      ] },
    { key: 'weightMax',        label: 'Added load (RM)',  type: 'number', unit: 'kg',   min: 0, max: 100, step: 0.5, placeholder: '0' },
    { key: 'repsMax',          label: 'Reps max (RM)',    type: 'number', unit: 'reps', min: 1, max: 50,  step: 1,   placeholder: '1', defaultValue: 1 },
    // Per-camera rep counts — the analyzer trusts these inputs verbatim
    // (touch-frame detector picks exactly N extreme positions per video).
    { key: 'targetRepsSagittal',  label: 'Reps · sagittal video',  type: 'number', unit: 'reps', min: 1, max: 50, step: 1, placeholder: '10', defaultValue: 10 },
    { key: 'targetRepsFrontal',   label: 'Reps · frontal video',   type: 'number', unit: 'reps', min: 1, max: 50, step: 1, placeholder: '10', defaultValue: 10 },
    { key: 'targetRepsPosterior', label: 'Reps · posterior video', type: 'number', unit: 'reps', min: 1, max: 50, step: 1, placeholder: '10', defaultValue: 10 },
    { key: 'targetRepsOblique',   label: 'Reps · oblique video',   type: 'number', unit: 'reps', min: 1, max: 50, step: 1, placeholder: '10', defaultValue: 10 },
    { key: 'athleteHeightCm',  label: 'Athlete height',   type: 'number', unit: 'cm',   min: 140, max: 220, step: 1, placeholder: '170' },
  ],
  'overhead-press': [
    { key: 'variant', label: 'Variant', type: 'select', defaultValue: 'military',
      options: [
        { value: 'military',  label: 'Military Press (standing barbell, strict)' },
        { value: 'seated-db', label: 'Seated Dumbbell Shoulder Press' },
      ] },
    { key: 'backrestDeg', label: 'Backrest angle (Seated DB only)', type: 'select', defaultValue: '85',
      options: [
        { value: '90', label: '90° (vertical) — maximum anterior-delt isolation' },
        { value: '85', label: '85° — most-tutorials default' },
        { value: '80', label: '80° — common gym setting' },
        { value: '75', label: '75° — research-anchor setting (more upper-pec)' },
      ] },
    { key: 'stance', label: 'Stance (Military only)', type: 'select', defaultValue: 'strict',
      options: [
        { value: 'military_true', label: 'True Military (heels together)' },
        { value: 'strict',        label: 'Strict press (shoulder-width)' },
      ] },
    { key: 'weightMax',  label: 'Weight max (RM)', type: 'number', unit: 'kg',   min: 0, max: 200, step: 0.5, placeholder: '50' },
    { key: 'repsMax',    label: 'Reps max (RM)',   type: 'number', unit: 'reps', min: 1, max: 30,  step: 1,   placeholder: '1', defaultValue: 1 },
    // Per-camera rep counts — the analyzer trusts these inputs verbatim
    // (extreme-frame detector picks exactly N sets of {setup, sticking, lockout} per video).
    { key: 'targetRepsSagittal',  label: 'Reps · sagittal video',  type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'targetRepsFrontal',   label: 'Reps · frontal video',   type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'targetRepsPosterior', label: 'Reps · posterior video', type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'targetRepsOblique',   label: 'Reps · oblique video',   type: 'number', unit: 'reps', min: 1, max: 30, step: 1, placeholder: '3', defaultValue: 3 },
    { key: 'plateSizeKg', label: 'Plate size', type: 'select', defaultValue: 20,
      options: [
        { value: '25', label: '25 kg (450 mm)' }, { value: '20', label: '20 kg (450 mm)' },
        { value: '15', label: '15 kg (400 mm)' }, { value: '10', label: '10 kg (320 mm)' },
      ] },
    { key: 'athleteHeightCm',  label: 'Athlete height',   type: 'number', unit: 'cm',   min: 140, max: 220, step: 1, placeholder: '170' },
  ],
};

const refIcon: Record<string, ReactElement> = {
  VIDEO:  <Video size={14} strokeWidth={2} />,
  CAMERA: <Camera size={14} strokeWidth={2} />,
  GUIDE:  <BookOpen size={14} strokeWidth={2} />,
  IMAGE:  <ImageIcon size={14} strokeWidth={2} />,
};

const refTone: Record<string, 'clay'|'good'|'neutral'> = {
  VIDEO: 'clay', CAMERA: 'neutral', GUIDE: 'good', IMAGE: 'neutral',
};

/* ── Reference card ─────────────────────────────────────────── */
function RefCard({ r, onClick, imgSrc, compact }: {
  r: ExerciseRef; onClick: () => void; imgSrc?: string; compact?: boolean;
}) {
  const [hov, setHov] = useState(false);
  const showImg = r.type === 'IMAGE' && !!imgSrc;
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        // Narrower on phones so the next card peeks in and the rail reads
        // as scrollable rather than as a single cropped card.
        width: compact ? 244 : 320, flexShrink: 0,
        background: C.surface,
        border: `1px solid ${hov ? C.borderClay : C.border}`,
        borderRadius: R.lg,
        padding: 0, textAlign: 'left',
        cursor: 'pointer',
        transition: 'transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease',
        transform: hov ? 'translateY(-4px)' : 'none',
        boxShadow: hov ? '0 16px 36px rgba(0,0,0,0.35)' : 'none',
        overflow: 'hidden',
        backdropFilter: C.glassBlur, WebkitBackdropFilter: C.glassBlur,
      }}>
      {/* Thumbnail strip */}
      <div style={{
        aspectRatio: '16/9',
        backgroundImage: showImg
          ? `linear-gradient(180deg, rgba(10,13,16,0.05) 60%, rgba(10,13,16,0.55) 100%), url(${imgSrc})`
          : `linear-gradient(155deg, ${C.bg3}, ${C.bg})`,
        backgroundSize: 'cover', backgroundPosition: 'center',
        borderBottom: `1px solid ${C.border}`,
        position: 'relative',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {!showImg && (
          <div style={{
            color: r.type === 'GUIDE' ? C.sage : r.type === 'IMAGE' ? C.indigo : C.clay,
            opacity: 0.9,
            fontSize: 56,
          }}>{refIcon[r.type]}</div>
        )}
        <span style={{
          position: 'absolute', top: 12, left: 12,
        }}>
          <Pill tone={refTone[r.type]} size="xs">{r.type}</Pill>
        </span>
      </div>
      <div style={{ padding: compact ? '14px 16px 16px' : '16px 20px 18px' }}>
        <div style={{ fontFamily: F.display, fontSize: 17, lineHeight: 1.2, color: C.ink, marginBottom: 4, letterSpacing: '-0.01em' }}>
          {r.title}
        </div>
        <div style={{ fontSize: 12.5, color: C.ink2, lineHeight: 1.5 }}>
          {r.sub}
        </div>
        <div style={{ marginTop: 10 }}>
          <Pill tone="neutral" size="xs" uppercase={false}>{r.tag}</Pill>
        </div>
      </div>
    </button>
  );
}

/* ── Upload drop zone ───────────────────────────────────────── */
function UploadZone({ up, file, onFile, isMobile }: {
  up: ExerciseUpload; file?: File; onFile: (f: File) => void; isMobile?: boolean;
}) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const handle = (f?: File) => { if (f && f.type.startsWith('video/')) onFile(f); };

  return (
    // `minWidth: 280` plus the page gutter overflows a 375px viewport, so on
    // phones each zone takes the full row instead of trying to share one.
    <div style={{ flex: isMobile ? '1 1 100%' : 1, minWidth: isMobile ? 0 : 280, width: isMobile ? '100%' : undefined }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        {up.shape && (
          <span style={{
            width: 28, height: 28, borderRadius: R.sm,
            background: C.surface2, color: C.clay,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: F.display, fontSize: 14,
          }}>{up.shape}</span>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: F.body, fontWeight: 500, fontSize: 14, color: C.ink }}>{up.label}</div>
          <div style={{ fontSize: 12, color: C.ink3, marginTop: 2 }}>{up.angle} · {up.reps}</div>
        </div>
        {file && <Pill tone="good" size="xs">✓ Uploaded</Pill>}
      </div>

      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files[0]); }}
        style={{
          cursor: 'pointer',
          textAlign: 'center',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 10,
          padding: '28px 20px', minHeight: 132,
          background: file ? C.sageTint : drag ? C.clayTint : C.surface,
          border: `2px dashed ${file ? C.borderSage : drag ? C.clay : C.borderStrong}`,
          borderRadius: R.lg,
          transition: 'background 180ms ease, border-color 180ms ease',
        }}>
        <input ref={inputRef} type="file" accept="video/*" hidden
          onChange={e => handle(e.target.files?.[0])} />
        {file ? (
          <>
            <CheckCircle2 size={32} strokeWidth={1.6} color={C.sage} />
            <div style={{
              fontFamily: F.body, fontWeight: 500, fontSize: 13.5, color: C.ink,
              maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {file.name.length > 28 ? file.name.slice(0, 28) + '…' : file.name}
            </div>
            <div style={{ fontSize: 11.5, color: C.ink3 }}>
              {(file.size / 1024 / 1024).toFixed(1)} MB · tap to replace
            </div>
          </>
        ) : (
          <>
            <UploadIcon size={28} strokeWidth={1.6} color={drag ? C.clay : C.ink3} />
            <div style={{ fontFamily: F.body, fontWeight: 500, fontSize: 13.5, color: drag ? C.clay : C.ink2 }}>
              {drag ? 'Release to upload' : isMobile ? 'Tap to choose a video' : 'Drop video or click to choose'}
            </div>
            <div style={{ fontSize: 11.5, color: C.ink3 }}>
              MP4 · MOV · AVI · up to 2 GB
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Modal for reference detail ──────────────────────────────── */
function Modal({ r, onClose, exercise }: { r: ExerciseRef; onClose: () => void; exercise: Exercise }) {
  useKeyboard({ onEscape: onClose });
  return (
    <div onClick={onClose} role="dialog" aria-modal="true" style={{
      position: 'fixed', inset: 0, zIndex: 500,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(10,13,16,0.72)',
      backdropFilter: 'blur(10px)',
      // 32px of inset on a 375px screen leaves the sheet 311px wide. Give the
      // dialog the screen on phones, and clear the notch / home indicator.
      padding: 'clamp(12px, 4vw, 32px)',
      paddingTop: `max(clamp(12px, 4vw, 32px), env(safe-area-inset-top, 0px))`,
      paddingBottom: `max(clamp(12px, 4vw, 32px), env(safe-area-inset-bottom, 0px))`,
    }} className="animate-fade-in">
      <Card onClick={(e: React.MouseEvent) => e.stopPropagation()} pad={0} variant="raised"
        style={{
          maxWidth: 720, width: '100%', maxHeight: '100%',
          overflow: 'auto', boxShadow: '0 24px 60px rgba(0,0,0,0.20)',
          WebkitOverflowScrolling: 'touch',
        }}>
        <div style={{
          padding: 'clamp(16px,3.5vw,20px) clamp(18px,4vw,28px)',
          borderBottom: `1px solid ${C.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
          position: 'sticky', top: 0, zIndex: 1,
          background: C.surfaceSolid,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <Pill tone={refTone[r.type]} size="sm">{r.type}</Pill>
            <div style={{
              fontFamily: F.display, fontSize: 'clamp(18px,4vw,22px)', color: C.ink,
              letterSpacing: '-0.01em', minWidth: 0,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {r.title}
            </div>
          </div>
          <button onClick={onClose} aria-label="Close" style={{
            background: 'transparent', border: `1px solid ${C.border}`, borderRadius: R.pill,
            width: 36, height: 36, color: C.ink2, cursor: 'pointer', flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}><X size={16} /></button>
        </div>
        <div style={{ padding: 'clamp(18px,4vw,28px)' }}>
          {r.type === 'GUIDE' && r.guide ? (
            <div>
              <SectionLabel style={{ marginBottom: 16 }}>Step-by-step</SectionLabel>
              {r.guide.split('\n').map((line, i) => {
                const numMatch = line.match(/^(\d+)\.\s*(.*)$/);
                return (
                  <div key={i} style={{
                    display: 'flex', gap: 14, alignItems: 'flex-start',
                    padding: '12px 0',
                    borderBottom: i < r.guide!.split('\n').length - 1 ? `1px solid ${C.border}` : 'none',
                  }}>
                    {numMatch ? (
                      <>
                        <span style={{
                          width: 24, height: 24, borderRadius: R.sm,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          background: C.clayTint, color: C.clay,
                          fontFamily: F.display, fontSize: 14, flexShrink: 0,
                        }}>{numMatch[1]}</span>
                        <p style={{ margin: 0, fontSize: 14, color: C.ink, lineHeight: 1.65, paddingTop: 2 }}>
                          {numMatch[2]}
                        </p>
                      </>
                    ) : (
                      <p style={{ margin: 0, fontSize: 14, color: C.ink2, lineHeight: 1.65, paddingLeft: 38 }}>
                        {line}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div>
              {r.type === 'IMAGE' && (
                <img src={`/images/exercises/${exercise.slug}.jpg`} alt={r.title}
                  style={{ width: '100%', borderRadius: R.lg, border: `1px solid ${C.border}`, marginBottom: 20, display: 'block' }} />
              )}
              <p style={{ margin: 0, fontSize: 14.5, color: C.ink, lineHeight: 1.75 }}>{r.sub}</p>
              {r.type === 'CAMERA' && (
                <Card variant="sunken" pad={16} style={{ marginTop: 20 }}>
                  <SectionLabel style={{ marginBottom: 6 }}>Camera position</SectionLabel>
                  <p style={{ margin: 0, fontSize: 13.5, color: C.ink2 }}>{exercise.cameraSetup}</p>
                </Card>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

export function InstructionPage({ exercise, completed, uploads, setUpload, onAnalyse, onBack }: Props) {
  const [modal, setModal] = useState<ExerciseRef | null>(null);
  const isMobile = useIsMobile();
  const { type } = useParams();
  const assessmentType = isValidAssessmentType(type) ? type : 'mobility';
  const exercises = listExercises(assessmentType);
  const exIdx = exercises.findIndex(e => e.slug === exercise.slug);
  const completedSteps = new Set<number>(
    Array.from(completed)
      .map(s => exercises.findIndex(e => e.slug === s) + 1)
      .filter(n => n > 0)
  );

  const allKeys = exercise.uploads.map(u => uploadKey(assessmentType, exercise.slug, u.id));
  const requiredKeys = exercise.uploads.filter(u => !u.optional).map(u => uploadKey(assessmentType, exercise.slug, u.id));
  const ready = requiredKeys.every(k => uploads[k]);
  const filled = allKeys.filter(k => uploads[k]).length;

  const { profile, updateProfile, exerciseInputs, setExerciseInput } = useAppContext();
  const needsTibia = exercise.slug === 'knee-to-wall-test';
  const strengthConfig = STRENGTH_INPUT_CONFIG[exercise.slug];
  const isStrength = !!strengthConfig;
  const currentInputs = exerciseInputs[exercise.slug] || {};

  // Keyboard: Enter → analyse when ready; Escape → back
  useKeyboard({
    enabled: !modal,
    onEnter: () => ready && onAnalyse(),
    onEscape: onBack,
  });

  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.ink }}>
      <Nav
        onBack={onBack} backLabel="All exercises"
        crumbs={[
          { label: 'Home', to: onBack },
          { label: exercise.name },
        ]}
        rightSlot={<Pill tone="clay" size="sm">Step {exIdx + 1} / {exercises.length}</Pill>}
      />
      <ExerciseProgressBar current={exIdx + 1} total={exercises.length} completed={completedSteps} />

      {/* ── Exercise title ─────────────────────────── */}
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: `clamp(28px,5vw,48px) ${GUTTER} clamp(20px,3.5vw,28px)` }}>
        <SectionLabel style={{ marginBottom: 12 }}>
          {exercise.category} · {exercise.difficulty} · {exercise.duration}
        </SectionLabel>
        <div className="animate-fade-up">
          <Display size="h1" style={{ textTransform: 'uppercase' }}>
            {exercise.name}
          </Display>
        </div>
        <p style={{
          marginTop: 14, color: C.ink2, fontSize: 15, lineHeight: 1.7, maxWidth: 720,
        }} className="animate-fade-up-1">
          {exercise.description}
        </p>
      </div>

      {/* ── Reference library ─────────────────────── */}
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: `0 ${GUTTER}` }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <SectionLabel>Reference library</SectionLabel>
            <Pill tone="neutral" size="xs">{exercise.refs.length} items</Pill>
          </div>
          <span style={{ fontSize: 12, color: C.ink3, whiteSpace: 'nowrap' }}>Swipe →</span>
        </div>
        <div className="mc-hscroll" style={{ display: 'flex', gap: 14, paddingBottom: 12 }}>
          {exercise.refs.map((r, i) => (
            <RefCard key={i} r={r} onClick={() => setModal(r)} compact={isMobile}
              imgSrc={r.type === 'IMAGE' ? `/images/exercises/${exercise.slug}.jpg` : undefined} />
          ))}
        </div>
      </div>

      {/* ── Checklist ─────────────────────────────── */}
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: `20px ${GUTTER} 0` }}>
        <Card variant="sunken" pad={isMobile ? 16 : 20}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
            <SectionLabel style={{ color: C.clay, marginRight: 4 }}>Submission checklist</SectionLabel>
            {exercise.checklist.map((c, i) => (
              <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: C.ink }}>
                <span style={{ width: 6, height: 6, borderRadius: 3, background: C.clay, opacity: 0.6 }} />
                {c}
              </span>
            ))}
          </div>
        </Card>
      </div>

      {/* ── Strength inputs ────────────────────────── */}
      {isStrength && (
        <div style={{ maxWidth: 1180, margin: '0 auto', padding: `14px ${GUTTER} 0` }}>
          <Card variant="raised" accent="clay" pad={isMobile ? 18 : 28}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
              <SectionLabel>Lift details</SectionLabel>
              <span style={{ fontSize: 12, color: C.ink3 }}>
                Used for analysis bands · 1RM estimation · bar-plate calibration
              </span>
            </div>
            <div style={{
              display: 'grid', gap: 14,
              gridTemplateColumns: gridCols(220),
            }}>
              {strengthConfig.map(fld => {
                const stored = currentInputs[fld.key];
                const value = stored !== undefined ? stored : (fld.defaultValue ?? '');
                const onChange = (v: string) => {
                  if (fld.type === 'number') {
                    const n = parseFloat(v);
                    setExerciseInput(exercise.slug, fld.key, isNaN(n) ? '' : n);
                  } else {
                    setExerciseInput(exercise.slug, fld.key, v);
                  }
                };
                return (
                  <label key={fld.key} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <SectionLabel>{fld.label}</SectionLabel>
                    {fld.type === 'select' ? (
                      <select
                        value={String(value)}
                        onChange={e => onChange(e.target.value)}
                        style={{
                          background: C.surface, color: C.ink,
                          border: `1px solid ${C.borderStrong}`, borderRadius: R.md,
                          padding: '11px 12px', fontFamily: F.body, fontSize: 13.5,
                          outline: 'none', cursor: 'pointer',
                          // Long option labels ("Powerlifting (low touch, tucked…)")
                          // otherwise stretch the select past its grid track.
                          width: '100%', maxWidth: '100%', minWidth: 0,
                        }}>
                        {fld.options!.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="number" inputMode="decimal"
                          step={fld.step ?? 1}
                          min={fld.min} max={fld.max}
                          placeholder={fld.placeholder}
                          value={value === '' || value === undefined ? '' : String(value)}
                          onChange={e => onChange(e.target.value)}
                          style={{
                            background: C.surface, color: C.ink,
                            border: `1px solid ${C.borderStrong}`, borderRadius: R.md,
                            padding: '11px 12px', fontFamily: F.body, fontSize: 13.5,
                            outline: 'none', minWidth: 0, flex: 1, width: '100%',
                          }}
                        />
                        {fld.unit && <span style={{ fontSize: 12.5, color: C.ink3, minWidth: 28 }}>{fld.unit}</span>}
                      </div>
                    )}
                  </label>
                );
              })}
            </div>
          </Card>
        </div>
      )}

      {/* ── Tibia calibration ──────────────────────── */}
      {needsTibia && (
        <div style={{ maxWidth: 1180, margin: '0 auto', padding: `14px ${GUTTER} 0` }}>
          <Card variant="raised" accent="sage" pad={isMobile ? 18 : 28}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
              <SectionLabel style={{ color: C.sage }}>Calibration</SectionLabel>
              <span style={{ fontSize: 13, color: C.ink2, flex: 1, minWidth: 200 }}>
                Tibia length powers zero-setup pixel-to-cm conversion. Measure knee-cap centre to ankle bone.
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="number" inputMode="decimal" step="0.1" min="25" max="60"
                  placeholder="40.0"
                  defaultValue={profile.tibiaLengthCm ?? ''}
                  onChange={e => {
                    const v = parseFloat(e.target.value);
                    updateProfile({ tibiaLengthCm: isNaN(v) ? undefined : v });
                  }}
                  style={{
                    background: C.surface, color: C.ink,
                    border: `1px solid ${C.borderStrong}`, borderRadius: R.md,
                    padding: '10px 12px', fontFamily: F.body, fontSize: 13.5,
                    outline: 'none', width: 96, textAlign: 'right',
                  }}/>
                <span style={{ fontSize: 12.5, color: C.ink3 }}>cm</span>
                {profile.tibiaLengthCm
                  ? <Pill tone="good" size="xs">✓ Saved</Pill>
                  : <Pill tone="warn" size="xs">Fallback</Pill>}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* ── Upload zone ────────────────────────────── */}
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: `28px ${GUTTER} 24px` }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 18, flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <SectionLabel>Upload your videos</SectionLabel>
            <Pill tone={ready ? 'good' : 'neutral'} size="xs">
              {filled}/{exercise.uploads.length} uploaded
            </Pill>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {exercise.uploads.map(u => {
              const k = uploadKey(assessmentType, exercise.slug, u.id);
              return (
                <span key={u.id} style={{
                  width: 8, height: 8, borderRadius: 4,
                  background: uploads[k] ? C.clay : C.taupe,
                  transition: 'background 240ms',
                }} />
              );
            })}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {exercise.uploads.map(u => (
            <UploadZone
              key={u.id}
              up={u}
              isMobile={isMobile}
              file={uploads[uploadKey(assessmentType, exercise.slug, u.id)]}
              onFile={f => setUpload(uploadKey(assessmentType, exercise.slug, u.id), f)}
            />
          ))}
        </div>

        {/* Camera note */}
        <Card variant="sunken" pad={16} style={{ marginTop: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{
              width: 32, height: 32, borderRadius: R.sm,
              background: C.clayTint, color: C.clay,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}><Camera size={16} strokeWidth={2} /></span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <SectionLabel style={{ color: C.clay, marginBottom: 4 }}>Camera setup</SectionLabel>
              <p style={{ margin: 0, fontSize: 13.5, color: C.ink, lineHeight: 1.55 }}>
                {exercise.cameraSetup}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* ── Sticky analyse footer ─────────────────── */}
      <div style={{
        position: 'sticky', bottom: 0, zIndex: 100,
        background: 'rgba(10,13,16,0.95)',
        backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
        borderTop: `1px solid ${ready ? C.borderClay : C.border}`,
        padding: `${isMobile ? 12 : 16}px ${GUTTER}`,
        // Clear the iPhone home indicator — without this the CTA sits under it.
        paddingBottom: `calc(${isMobile ? 12 : 16}px + env(safe-area-inset-bottom, 0px))`,
      }}>
        <div style={{
          maxWidth: 1180, margin: '0 auto',
          display: 'flex',
          alignItems: isMobile ? 'stretch' : 'center',
          flexDirection: isMobile ? 'column' : 'row',
          justifyContent: 'space-between',
          gap: isMobile ? 10 : 16, flexWrap: 'wrap',
        }}>
          <div style={{ fontSize: isMobile ? 13 : 14, color: C.ink3, textAlign: isMobile ? 'center' : 'left' }}>
            {ready
              ? <span style={{ color: C.sage, fontWeight: 600 }}>All videos uploaded — ready to analyse</span>
              : <>Upload <strong style={{ color: C.ink }}>{exercise.uploads.length - filled}</strong> more video{exercise.uploads.length - filled !== 1 ? 's' : ''} to continue</>
            }
          </div>
          <Button
            variant="primary"
            size="lg"
            disabled={!ready}
            onClick={ready ? onAnalyse : undefined}
            iconRight={<ArrowBadge />}
            block={isMobile}
            style={isMobile
              ? { paddingLeft: 22, paddingRight: 6, justifyContent: 'space-between' }
              : { paddingRight: 8 }}>
            ANALYSE
          </Button>
        </div>
      </div>

      {modal && <Modal r={modal} onClose={() => setModal(null)} exercise={exercise} />}
    </div>
  );
}
