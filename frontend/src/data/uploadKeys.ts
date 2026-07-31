import type { AssessmentType } from '@/data/registry';

/**
 * Upload-slot keys for the global `uploads` map in AppContext.
 *
 * Keys are namespaced by assessment type AND slug — never by the numeric
 * exercise id. Mobility and strength ids overlap (both tracks start at 1),
 * so id-based keys made knee-to-wall's `1-front` and back-squat's `1-front`
 * the same slot: a video uploaded for one exercise silently satisfied (and
 * was analysed for) a different exercise in the other track.
 *
 * The `::` separator cannot appear in slugs or upload ids (both are
 * kebab-case), so splitting is unambiguous.
 */
const SEP = '::';

export function uploadKey(type: AssessmentType, slug: string, uploadId: string): string {
  return `${type}${SEP}${slug}${SEP}${uploadId}`;
}

export function uploadKeyPrefix(type: AssessmentType, slug: string): string {
  return `${type}${SEP}${slug}${SEP}`;
}

/** Extract the analyzer-facing field name (e.g. 'side', 'front') from a key. */
export function uploadFieldFromKey(key: string): string {
  const parts = key.split(SEP);
  return parts.length === 3 ? parts[2] : key;
}
