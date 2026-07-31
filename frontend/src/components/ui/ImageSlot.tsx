import { useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { C, F, R } from '../../theme/tokens';

interface Props {
  /** Public image path, e.g. "/images/hero-athlete.jpg". When omitted or the
   *  file is missing, an editorial placeholder renders in its place. */
  src?: string;
  alt: string;
  /** Aspect ratio of the slot, e.g. '4/5' (portrait), '16/9' (landscape). */
  aspect?: string;
  /** Border-radius. Defaults to large card radius. */
  radius?: number;
  /** Big serif number/letter used as the placeholder's decorative anchor. */
  mark?: ReactNode;
  /** Tiny caption that sits below the mark — kept under the placeholder. */
  caption?: string;
  /** When true, treats the slot as decorative and hides it from screen readers. */
  decorative?: boolean;
  /** Stretch to fill the parent. */
  fill?: boolean;
  style?: CSSProperties;
  className?: string;
  /** Optional dark scrim overlay (helps text overlay readability). */
  scrim?: boolean;
}

/**
 * An image SLOT — renders a real photo when `src` resolves, and an elegant
 * editorial placeholder (big serif mark + soft surface) when it doesn't.
 *
 * Place these wherever a photo would live; the page reads "designed" either
 * way, so you can ship before the photoshoot.
 */
export function ImageSlot({
  src, alt, aspect = '4/5', radius = R.xl,
  mark, caption, decorative, fill = true,
  style, className, scrim,
}: Props) {
  const [errored, setErrored] = useState(false);
  const showPhoto = !!src && !errored;

  const wrapStyle: CSSProperties = {
    position: 'relative',
    width: fill ? '100%' : undefined,
    aspectRatio: aspect,
    background: showPhoto ? C.surfaceSolid : `linear-gradient(155deg, ${C.bg3} 0%, ${C.bg} 55%, ${C.bg2} 100%)`,
    borderRadius: radius,
    overflow: 'hidden',
    border: `1px solid ${C.border}`,
    ...style,
  };

  if (showPhoto) {
    return (
      <div className={className} style={wrapStyle}>
        <img
          src={src!} alt={decorative ? '' : alt}
          aria-hidden={decorative}
          onError={() => setErrored(true)}
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%', objectFit: 'cover',
            display: 'block',
          }}
        />
        {scrim && (
          <div aria-hidden style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(135deg, rgba(10,13,16,0.55) 0%, rgba(10,13,16,0.20) 50%, transparent 100%)',
          }} />
        )}
      </div>
    );
  }

  // ── Editorial placeholder ─────────────────────────────────────
  return (
    <div className={className} style={wrapStyle} aria-label={decorative ? undefined : alt}>
      {/* Decorative grid pattern */}
      <div aria-hidden style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'repeating-linear-gradient(115deg, rgba(255,90,54,0.06) 0px, rgba(255,90,54,0.06) 2px, transparent 2px, transparent 26px)',
      }} />

      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: 24, gap: 10, textAlign: 'center',
      }}>
        {mark && (
          <div style={{
            fontFamily: F.display,
            fontSize: 'clamp(64px, 12vw, 150px)',
            lineHeight: 0.9,
            color: 'rgba(255,90,54,0.9)',
            letterSpacing: '0.5px',
          }}>{mark}</div>
        )}
        {caption && (
          <div style={{
            fontFamily: F.body, fontSize: 10.5, fontWeight: 700,
            letterSpacing: '0.2em', textTransform: 'uppercase',
            color: C.ink4,
          }}>{caption}</div>
        )}
      </div>
    </div>
  );
}

export default ImageSlot;
