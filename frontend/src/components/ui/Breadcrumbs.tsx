import { Fragment } from 'react';
import { C, F } from '../../theme/tokens';

export interface Crumb {
  label: string;
  to?: () => void;
}

/**
 * Top-of-page breadcrumb trail.
 * Last item is non-clickable (the current page).
 *
 * `collapse` (phones) keeps only the immediate parent and the current page —
 * a three-deep trail plus exercise name can't fit a 375px line, and the
 * middle links are the least useful ones to keep.
 */
export function Breadcrumbs({ items, collapse = false }: { items: Crumb[]; collapse?: boolean }) {
  if (!items.length) return null;
  const shown = collapse ? items.slice(-2) : items;
  return (
    <nav aria-label="Breadcrumb" style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: F.body,
      fontSize: 12.5,
      color: C.ink3,
      letterSpacing: '0.01em',
      minWidth: 0,
    }}>
      {collapse && shown.length < items.length && (
        <>
          <span style={{ color: C.ink4, flexShrink: 0 }} aria-hidden>…</span>
          <span style={{ color: C.ink4, fontSize: 11, flexShrink: 0 }}>›</span>
        </>
      )}
      {shown.map((c, i) => {
        const last = i === shown.length - 1;
        return (
          <Fragment key={i}>
            {c.to && !last ? (
              <button
                onClick={c.to}
                // .mc-crumb widens the tap area to 44px with a pseudo-element
                // on touch devices — growing the button itself would push the
                // nav row taller on every screen.
                className="mc-crumb"
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
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
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
              <span style={{
                color: last ? C.ink : C.ink2,
                fontWeight: last ? 500 : 400,
                // The current page is the one allowed to truncate — everything
                // before it is a short, fixed nav label.
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {c.label}
              </span>
            )}
            {!last && <span style={{ color: C.ink4, fontSize: 11, flexShrink: 0 }}>›</span>}
          </Fragment>
        );
      })}
    </nav>
  );
}

export default Breadcrumbs;
