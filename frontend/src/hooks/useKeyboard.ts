import { useEffect } from 'react';

type KeyHandler = () => void;

interface Bindings {
  /** Enter / Return */
  onEnter?: KeyHandler;
  /** Escape */
  onEscape?: KeyHandler;
  /** Arrow Left */
  onLeft?: KeyHandler;
  /** Arrow Right */
  onRight?: KeyHandler;
  /** Arrow Up */
  onUp?: KeyHandler;
  /** Arrow Down */
  onDown?: KeyHandler;
  /** Custom key map: { 'g': () => …, '?': () => … } */
  map?: Record<string, KeyHandler>;
  /** When false, the listener is detached. */
  enabled?: boolean;
}

/**
 * Lightweight global keyboard binding.
 * Skips events when focus is inside form fields so typing isn't hijacked.
 */
export function useKeyboard({
  onEnter, onEscape, onLeft, onRight, onUp, onDown, map, enabled = true,
}: Bindings) {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = (target?.tagName || '').toLowerCase();
      const isEditable =
        tag === 'input' || tag === 'textarea' || tag === 'select' ||
        target?.isContentEditable === true;
      // Allow Escape inside form fields (lets user dismiss flows).
      if (isEditable && e.key !== 'Escape') return;

      const k = e.key;
      const callback =
        k === 'Enter'      ? onEnter  :
        k === 'Escape'     ? onEscape :
        k === 'ArrowLeft'  ? onLeft   :
        k === 'ArrowRight' ? onRight  :
        k === 'ArrowUp'    ? onUp     :
        k === 'ArrowDown'  ? onDown   :
        map?.[k];

      if (callback) {
        e.preventDefault();
        callback();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [enabled, onEnter, onEscape, onLeft, onRight, onUp, onDown, map]);
}

export default useKeyboard;
