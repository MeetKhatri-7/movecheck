import { useState } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { C, F, R } from '../../theme/tokens';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'sage';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Apply full rounded pill shape (matches the MoveCheck CTA). Default true. */
  pill?: boolean;
  /** Icon node placed AFTER the children (arrow → look). */
  iconRight?: ReactNode;
  /** Icon node placed BEFORE the children. */
  iconLeft?: ReactNode;
  /** Stretch to fill the container width. */
  block?: boolean;
}

/**
 * The single button primitive used across the app — MoveCheck athletic style.
 *
 * Hierarchy:
 *   primary    — strongest CTA, one per screen; solid vermilion on near-black,
 *                heavy weight. Pair with <ArrowBadge/> for the signature look.
 *   secondary  — glass outline alternative ("Re-record", "Dashboard").
 *   ghost      — tertiary nav / dismiss; no border.
 *   danger     — destructive; vermilion (reserved).
 *   sage       — affirmative-but-not-primary ("Mark complete").
 */
export function Button({
  variant = 'primary',
  size = 'md',
  pill = true,
  iconLeft, iconRight,
  block = false,
  children,
  style,
  disabled,
  ...rest
}: ButtonProps) {
  const [hover, setHover] = useState(false);
  const [pressed, setPressed] = useState(false);

  const sizeMap = {
    sm: { padY: 9,  padX: 18, font: 12.5, gap: 8,  },
    md: { padY: 12, padX: 24, font: 13.5, gap: 10, },
    lg: { padY: 15, padX: 30, font: 14.5, gap: 12, },
  }[size];

  // Variant palette
  let bg: string = C.clay, fg: string = C.bg, border: string = 'transparent';
  if (variant === 'primary') {
    bg = hover ? C.clayHover : C.clay;
    fg = C.bg;
    border = 'transparent';
  } else if (variant === 'secondary') {
    bg = hover ? 'rgba(255,255,255,0.10)' : 'rgba(255,255,255,0.05)';
    fg = C.ink;
    border = hover ? C.borderClay : C.borderStrong;
  } else if (variant === 'ghost') {
    bg = hover ? C.taupe : 'transparent';
    fg = hover ? C.ink : C.ink3;
    border = 'transparent';
  } else if (variant === 'danger') {
    bg = hover ? C.clayHover : C.clay;
    fg = C.bg;
    border = 'transparent';
  } else if (variant === 'sage') {
    bg = hover ? C.sageDark : C.sage;
    fg = C.bg;
    border = 'transparent';
  }

  return (
    <button
      {...rest}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPressed(false); }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: sizeMap.gap,
        background: bg,
        color: fg,
        border: border === 'transparent' ? '1px solid transparent' : `1px solid ${border}`,
        borderRadius: pill ? R.pill : R.md,
        padding: `${sizeMap.padY}px ${sizeMap.padX}px`,
        fontFamily: F.body,
        fontWeight: variant === 'primary' || variant === 'danger' || variant === 'sage' ? 800 : 700,
        fontSize: sizeMap.font,
        letterSpacing: '0.3px',
        transform: pressed ? 'scale(0.98)' : hover && !disabled ? 'scale(1.03)' : 'scale(1)',
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background 160ms ease, transform 120ms ease, border-color 160ms ease, color 160ms ease',
        width: block ? '100%' : 'auto',
        whiteSpace: 'nowrap',
        ...style,
      }}>
      {iconLeft}
      {children && <span>{children}</span>}
      {iconRight}
    </button>
  );
}

/**
 * The circular arrow badge that sits inside primary CTAs in the redesign —
 * a small inverted circle with the accent arrow. Pass as `iconRight`.
 */
export function ArrowBadge({
  glyph = '→',
  onDark = true,
  size = 34,
}: { glyph?: string; onDark?: boolean; size?: number }) {
  return (
    <span style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      width: size, height: size, borderRadius: '50%',
      background: onDark ? C.bg : 'rgba(255,255,255,0.10)',
      color: onDark ? C.clay : C.ink,
      fontSize: Math.round(size * 0.46), lineHeight: 1,
      flexShrink: 0,
    }}>{glyph}</span>
  );
}

export default Button;