/**
 * Deployment configuration, resolved at build time from Vite env vars.
 *
 * Local dev  → VITE_API_BASE_URL is unset, so this stays `/api` and Vite's
 *              dev-server proxy (vite.config.ts) forwards to localhost:3001.
 * Production → VITE_API_BASE_URL is set in the Vercel dashboard to the public
 *              API origin, e.g. https://<user>-movecheck.hf.space/api
 *
 * Why a full cross-origin URL instead of proxying through Vercel: video
 * uploads are 80–150 MB, and routing those through Vercel's edge proxy runs
 * into request-body limits. Talking to the API host directly keeps large
 * uploads off Vercel entirely — the backend's CORS allowlist permits it.
 */

const rawBase = import.meta.env.VITE_API_BASE_URL as string | undefined;

/** Base URL every API call is made against. No trailing slash. */
export const API_BASE_URL = (rawBase?.trim() || '/api').replace(/\/+$/, '');

/** True when the API lives on a different origin (production split deploy). */
export const IS_REMOTE_API = /^https?:\/\//i.test(API_BASE_URL);

/**
 * Origin of the API host, without the /api path — used for warm-up pings.
 * Empty string when the API is same-origin.
 */
export const API_ORIGIN = IS_REMOTE_API ? new URL(API_BASE_URL).origin : '';

/**
 * Free-tier CV containers sleep when idle and need ~30-60s to wake. We fire a
 * cheap health request as soon as the app loads so the container is already
 * warming while the user reads the instructions — by the time they upload,
 * it's usually ready. Failures are ignored on purpose; this is best-effort.
 */
export function warmUpApi(): void {
  const url = `${API_BASE_URL}/health`;
  fetch(url, { method: 'GET', mode: 'cors', cache: 'no-store' }).catch(() => {
    /* container is asleep or unreachable — the real request will surface it */
  });
}
