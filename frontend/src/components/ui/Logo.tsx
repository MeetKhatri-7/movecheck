import { C, F } from '../../theme/tokens';

/**
 * MoveCheck wordmark — `MOVE//CHECK` set in Bebas Neue with the signature
 * vermilion `//` slash motif. This is the brand's memorable element; it
 * appears in every nav, the processing screen, and the footer.
 */
export function Logo({
  size = 22,
  onClick,
  showSlashOnly = false,
}: {
  size?: number;
  onClick?: () => void;
  /** Render only the compact `//` mark (for tight spaces / favicujn echoes). */
  showSlashOnly?: boolean;
}) {
  if (showSlashOnly) {
    return (
      <span
        onClick={onClick}
        style={{
          fontFamily: F.display, fontSize: size, letterSpacing: '0.5px',
          color: C.clay, cursor: onClick ? 'pointer' : 'default', lineHeight: 1,
        }}>
        //
      </span>
    );
  }
  return (
    <span
      onClick={onClick}
      style={{
        fontFamily: F.display,
        fontSize: size,
        letterSpacing: '0.5px',
        color: C.ink,
        cursor: onClick ? 'pointer' : 'default',
        lineHeight: 1,
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}>
      MOVE<span style={{ color: C.clay }}>//</span>CHECK
    </span>
  );
}

export default Logo;