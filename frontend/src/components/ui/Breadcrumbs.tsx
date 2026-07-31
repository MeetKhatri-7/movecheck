import { Fragment } from 'react';
import { C, F } from '../../theme/tokens';

export interface Crumb {
  label: string;
  to?: () => void;
}

/**
 * Top-of-page breadcrumb trail.
 * Last item is non-clickable (the current page).
 */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  if (!items.length) return null;
  return (
    <nav aria-label="Breadcrumb" style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: F.body,
      fontSize: 12.5,
      color: C.ink3,
      letterSpacing: '0.01em',
    }}>
      {items.map((c, i) => {
        const last = i === items.length - 1;
        return (
          <Fragment key={i}>
            {c.to && !last ? (
              <button
                onClick={c.to}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  color: C.ink2,
                  fontFamily: 'inherit',
                  fontSize: 'inherit',
                  cursor: 'pointer',
                  textDecoration: 'none',
                  borderBottom: '1px solid transparent',
                  transition: 'color 160ms, border-color 160ms',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = C.clay;
                  e.currentTarget.style.borderBottomColor = C.borderClay;
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = C.ink2;
                  e.currentTarget.style.borderBottomColor = 'transparent';
                }}>
                {c.label}
              </button>
            ) : (
              <span style={{ color: last ? C.ink : C.ink2, fontWeight: last ? 500 : 400 }}>
                {c.label}
              </span>
            )}
            {!last && <span style={{ color: C.ink4, fontSize: 11 }}>›</span>}
          </Fragment>
        );
      })}
    </nav>
  );
}

export default Breadcrumbs;
