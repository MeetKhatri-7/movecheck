import type { ReactNode } from 'react';
import { C, F } from '../../theme/tokens';
import { Button, ArrowBadge } from './Button';
import { SectionLabel } from './SectionLabel';

interface Props {
  /** small label above title (e.g. "NOTHING HERE YET"). */
  kicker?: string;
  /** main message in serif. */
  title: ReactNode;
  /** supporting copy. */
  body?: ReactNode;
  /** primary CTA. */
  ctaLabel?: string;
  onCta?: () => void;
  /** optional illustration/icon node on the left (kept simple — no clip art). */
  illustration?: ReactNode;
}

/**
 * Empty states are first impressions. Show one clear next step.
 * Used for: empty dashboard, no sessions, no reports yet, no annotated frames.
 */
export function EmptyState({ kicker, title, body, ctaLabel, onCta, illustration }: Props) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: illustration ? 'auto 1fr' : '1fr',
      gap: 'clamp(20px, 4vw, 32px)',
      alignItems: 'center',
      padding: 'clamp(32px, 6vw, 56px) clamp(20px, 5vw, 40px)',
      background: C.surface,
      backdropFilter: C.glassBlur,
      WebkitBackdropFilter: C.glassBlur,
      border: `1px solid ${C.border}`,
      borderRadius: 20,
    }}>
      {illustration && (
        <div style={{
          width: 88, height: 88,
          background: C.clayTint,
          borderRadius: 24,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: C.clay,
        }}>
          {illustration}
        </div>
      )}
      <div>
        {kicker && <SectionLabel style={{ marginBottom: 8 }}>{kicker}</SectionLabel>}
        <div style={{
          fontFamily: F.display,
          fontWeight: 400,
          fontSize: 'clamp(26px, 6vw, 38px)',
          letterSpacing: '0.4px',
          lineHeight: 1.05,
          color: C.ink,
          marginBottom: body ? 12 : 0,
        }}>
          {title}
        </div>
        {body && (
          <p style={{
            fontFamily: F.body,
            fontSize: 14,
            lineHeight: 1.7,
            color: C.ink2,
            margin: 0,
            maxWidth: 480,
          }}>
            {body}
          </p>
        )}
        {ctaLabel && onCta && (
          <div style={{ marginTop: 24 }}>
            <Button variant="primary" size="md" iconRight={<ArrowBadge />} onClick={onCta}
              style={{ paddingRight: 6 }}>
              {ctaLabel}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default EmptyState;
