/**
 * Exercise registry — looks up exercises by (assessmentType, slug).
 *
 * This is the single source of truth pages should read from. Direct
 * imports of `assessments/mobility/exercises.ts` from page code should
 * be avoided so adding a new assessment type doesn't ripple through.
 */
import type { Exercise } from './types';
import { EXERCISES as MOBILITY_EXERCISES, catColors as MOBILITY_CAT_COLORS } from '@/assessments/mobility/exercises';
import { EXERCISES as STRENGTH_EXERCISES } from '@/assessments/strength/exercises';

export type AssessmentType = 'mobility' | 'strength';

export const ASSESSMENT_TYPES: AssessmentType[] = ['mobility', 'strength'];

const REGISTRY: Record<AssessmentType, Exercise[]> = {
  mobility: MOBILITY_EXERCISES,
  strength: STRENGTH_EXERCISES,
};

const TYPE_LABELS: Record<AssessmentType, string> = {
  mobility: 'Mobility',
  strength: 'Strength',
};

/** Re-exported so existing pages don't need to know which assessment owns it. */
export const catColors = MOBILITY_CAT_COLORS;

export function listExercises(type: AssessmentType): Exercise[] {
  return REGISTRY[type] || [];
}

export function getExercise(type: AssessmentType, slug: string): Exercise | undefined {
  return (REGISTRY[type] || []).find(e => e.slug === slug);
}

export function getExerciseById(type: AssessmentType, id: number): Exercise | undefined {
  return (REGISTRY[type] || []).find(e => e.id === id);
}

export function assessmentLabel(type: AssessmentType): string {
  return TYPE_LABELS[type];
}

export function isValidAssessmentType(value: string | undefined): value is AssessmentType {
  return value === 'mobility' || value === 'strength';
}
