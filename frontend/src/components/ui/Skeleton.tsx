import type { CSSProperties } from 'react';

/**
 * Single skeleton primitive. Combine to build skeleton compositions
 * (cards, list rows, gauges) that match the eventual layout.
 */
export function Skeleton({
  w = '100%',
  h = 16,
  radius = 6,
  style,
}: {
  w?: number | string;
  h?: number | string;
  radius?: number;
  style?: CSSProperties;
}) {
  return (
    <div
      className="skeleton"
      style={{
        width: typeof w === 'number' ? `${w}px` : w,
        height: typeof h === 'number' ? `${h}px` : h,
        borderRadius: radius,
        ...style,
      }}
    />
  );
}

/** Common skeleton: stacked text lines (title + subtitle + paragraph). */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          h={i === 0 ? 24 : 14}
          w={i === lines - 1 ? '60%' : i === 0 ? '40%' : '92%'}
        />
      ))}
    </div>
  );
}

export default Skeleton;
