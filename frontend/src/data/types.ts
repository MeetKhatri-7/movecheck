export interface ExerciseRef {
  type: 'VIDEO' | 'CAMERA' | 'GUIDE' | 'IMAGE';
  title: string;
  sub: string;
  tag: string;
  guide: string | null;
}

export interface ExerciseUpload {
  id: string;
  label: string;
  angle: string;
  reps: string;
  shape?: string;
  optional?: boolean;
}

export interface FaultTiming {
  rep: number;
  start_phase_pct: number;
  message: string;
}

/** 5-tier per-metric status from the back-squat doc-driven rewrite.
 *  Older analyzers still emit 'good' | 'bad' — those remain valid members. */
export type MetricStatus =
  | 'very_good'
  | 'good'
  | 'yellow_flag'
  | 'bad'
  | 'very_bad';

export interface Metric {
  name: string;
  value: string;
  raw: number;
  target: string;
  max: number;
  status: MetricStatus;
  /** 0-100 linear sub-score (doc §7.1). Present on analyzers using the
   *  5-tier scoring system; absent on the older good/bad analyzers. */
  sub_score?: number;
  // Phase 1.4+ — confidence-aware metrics surfaced by the strength rewrite.
  confidence?: number;                  // 0..1
  confidence_tier?: 'high' | 'medium' | 'low';
  n_reps?: number;
  fault_timing?: FaultTiming | null;
}

export interface BilateralComparison {
  name: string;
  left: number;
  right: number;
  unit: string;
  max: number;
  asymmetry: number;
}

export interface AnnotatedFrame {
  label: string;
  image_base64: string;
  rep_num: number;
  side: string;
  is_best: boolean;
  metrics_shown: string[];
}

export interface PerRepMetric {
  rep: number;
  side: string;
  metrics: Record<string, number | string>;
}

export interface MuscleActivation {
  slug: string;          // e.g. 'quadriceps', 'glutes', 'hamstrings'
  name: string;          // Human-readable: 'Quadriceps'
  percentage: number;    // 0–100 activation intensity
  side: 'both' | 'left' | 'right';
  isPrimary: boolean;    // primary mover vs stabilizer
}

export interface MuscleActivationData {
  exercise: string;
  dominance: string;     // e.g. 'Quad-dominant', 'Hip-dominant', 'Balanced'
  muscles: MuscleActivation[];
}

export interface FatigueSeries {
  mean: number;
  std: number;
  decay_slope: number;
  n: number;
  values: number[];
}

/* ────────────────────────────────────────────────────────────────────
 * Spec-driven composite scoring (deadlift; reusable for future analyzers)
 * Mirrors the §7 / §8 / §11.4 structure of the AI-Metrics spec.
 * ──────────────────────────────────────────────────────────────────── */

export type GradeLetter = 'A' | 'B' | 'C' | 'D' | 'E';
export type GradeLabel  = 'Very Good' | 'Good' | 'Yellow Flag' | 'Bad' | 'Very Bad';

export interface CategoryScore {
  name: 'Safety' | 'Technique' | 'Performance';
  weight: number;        // 0..1 (Safety 0.50, Technique 0.35, Performance 0.15)
  score: number;         // 0..100 weighted average of metric sub-scores within the category
}

export interface SafetyOverride {
  condition: string;     // human-readable rule, e.g. "Lumbar flexion deviation >20° (Very Bad)"
  cap: number;           // composite cap when triggered (0..100)
  triggered: boolean;
  triggering_metric?: string;     // which metric tripped it
  triggering_value?: string;      // value that tripped it (formatted)
}

export interface CorrectiveCue {
  metric: string;
  sub_score: number;     // 0..100
  cue: string;           // plain-language correction
}

export interface SetAggregation {
  mean: number;          // headline composite
  worst: number;         // lowest single-rep composite
  last_three: number;    // mean composite of the final 3 reps (fatigue check)
  deteriorating_rep_nums: number[];   // reps >15 pts below the set mean
}

export interface CompositeScore {
  composite: number;             // 0..100 headline (matches `score` for back-compat)
  grade: GradeLetter;
  label: GradeLabel;
  composite_method: 'arithmetic' | 'geometric';
  categories: CategoryScore[];
  overrides: SafetyOverride[];   // all evaluated overrides; only `.triggered === true` capped
  active_cap?: number | null;    // lowest cap among triggered overrides (null if none)
  lowest_sub_scores: CorrectiveCue[];   // typically the 2 lowest, with corrective cues
  aggregation: SetAggregation;
  variant?: string;              // e.g. 'conventional' | 'romanian'
}

export interface ResultMeta {
  camera_view?: string;
  camera_view_confidence?: number;
  camera_view_warning?: string | null;
  camera_view_side?: string;
  camera_view_front?: string;
  camera_view_side_confidence?: number;
  camera_view_front_confidence?: number;
  camera_view_warnings?: string[];
  bar_track_quality_median?: number;
  bar_ref_source?: string;
  bar_ref_confidence?: number;
  analyzer_version?: string;
}

export interface ExerciseResult {
  status: 'GOOD' | 'ADEQUATE' | 'NEEDS IMPROVEMENT' | 'RESTRICTED' | 'PASS';
  score: number;
  summary: string;
  stats: Record<string, string>;
  metrics: Metric[];
  bilateral: BilateralComparison[];
  coaching: string[];
  annotated_frames?: AnnotatedFrame[];
  per_rep?: PerRepMetric[];
  muscle_activation?: MuscleActivationData;
  // Phase 4 — fatigue / form-decay sparklines per metric, keyed by metric slug.
  // For back-squat the shape is {side: {...}, front: {...}}.
  fatigue?: Record<string, FatigueSeries> | Record<string, Record<string, FatigueSeries>>;
  meta?: ResultMeta;
  // Spec-driven composite scoring (deadlift). Optional so existing analyzers
  // that emit only `score`/`status`/`metrics` continue to render unchanged.
  composite_score?: CompositeScore;
}

export interface Exercise {
  id: number;
  slug: string;
  name: string;
  subtitle: string;
  category: 'Lower Body' | 'Upper Body' | 'Core';
  duration: string;
  difficulty: string;
  color: string;
  description: string;
  cameraSetup: string;
  checklist: string[];
  refs: ExerciseRef[];
  uploads: ExerciseUpload[];
  result: ExerciseResult;
}
