/**
 * sessionStore — durable per-session JSON storage.
 *
 * One file per session at  <sessionDir>/<sessionId>.json
 * Writes are atomic (temp file + rename) and serialized per-session via an
 * in-memory mutex so rapid back-to-back appendResult() calls don't race.
 */

const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');

// Configurable so a container can point this at a writable / mounted volume.
// NOTE: on hosts with an ephemeral filesystem (Hugging Face Spaces, Cloud Run)
// this directory is wiped on restart/redeploy. That is acceptable here — the
// browser keeps its own localStorage cache of results and re-syncs on boot.
const SESSION_DIR = process.env.SESSION_DIR || path.join(__dirname, '..', 'sessions');
if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });

// Per-session promise chain — guarantees serial writes for the same session.
const locks = new Map();
function withLock(sessionId, fn) {
  const prev = locks.get(sessionId) || Promise.resolve();
  const next = prev.catch(() => {}).then(fn);
  // The stored promise must (a) be the same reference we compare against in
  // the cleanup — .finally() returns a NEW promise, so comparing against
  // `next` never matched and lock entries leaked forever — and (b) carry a
  // no-op rejection handler: the caller gets rejections via the returned
  // `next`, but an unhandled rejection on the *stored* copy crashes the
  // whole process on modern Node.
  const stored = next.finally(() => {
    if (locks.get(sessionId) === stored) locks.delete(sessionId);
  });
  stored.catch(() => {});
  locks.set(sessionId, stored);
  return next;
}

function pathFor(sessionId) {
  // Defensive: never let a bad id escape the sessions dir.
  if (!/^[a-zA-Z0-9_-]{4,128}$/.test(sessionId)) {
    throw new Error(`Invalid sessionId: ${sessionId}`);
  }
  return path.join(SESSION_DIR, `${sessionId}.json`);
}

function emptySession(sessionId) {
  const now = new Date().toISOString();
  return {
    sessionId,
    createdAt: now,
    updatedAt: now,
    assessments: {
      mobility: { reports: {}, completedAt: null },
      strength: { reports: {}, completedAt: null },
    },
  };
}

async function writeAtomic(filePath, json) {
  const tmp = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  await fsp.writeFile(tmp, JSON.stringify(json, null, 2), 'utf-8');
  await fsp.rename(tmp, filePath);
}

/* ── Public API ─────────────────────────────────────────────────── */

/** Create a new session and persist its empty file. Returns the session JSON. */
async function create() {
  const sessionId = crypto.randomUUID();
  const data = emptySession(sessionId);
  await writeAtomic(pathFor(sessionId), data);
  return data;
}

/** Read a session. Throws if not found. */
async function get(sessionId) {
  const filePath = pathFor(sessionId);
  try {
    const raw = await fsp.readFile(filePath, 'utf-8');
    return JSON.parse(raw);
  } catch (e) {
    if (e.code === 'ENOENT') {
      const err = new Error('Session not found');
      err.code = 'ENOENT';
      throw err;
    }
    throw e;
  }
}

/** True if a session file exists on disk. */
async function exists(sessionId) {
  try {
    await fsp.access(pathFor(sessionId));
    return true;
  } catch { return false; }
}

/**
 * Append (or replace) a single exercise result into a session.
 * Mutates assessments[type].reports[slug] = result, bumps updatedAt.
 *
 * Throws ENOENT if the session does not exist — a stale or mistyped id must
 * NOT silently resurrect as a new partial session file; callers decide how
 * to surface that (404 to the client, error log on the persist path).
 */
async function appendResult(sessionId, assessmentType, slug, result) {
  if (!['mobility', 'strength'].includes(assessmentType)) {
    throw new Error(`Unknown assessmentType: ${assessmentType}`);
  }
  return withLock(sessionId, async () => {
    const data = await get(sessionId); // throws ENOENT if missing
    data.assessments[assessmentType].reports[slug] = result;
    data.updatedAt = new Date().toISOString();
    await writeAtomic(pathFor(sessionId), data);
    return data;
  });
}

/**
 * Aggregate report for a session — flattens both assessment types into a
 * single object that's easy for the dashboard to consume.
 */
async function aggregate(sessionId) {
  const data = await get(sessionId);
  const all = [];
  for (const [type, bucket] of Object.entries(data.assessments)) {
    for (const [slug, result] of Object.entries(bucket.reports)) {
      all.push({ assessmentType: type, slug, result });
    }
  }
  return {
    sessionId: data.sessionId,
    createdAt: data.createdAt,
    updatedAt: data.updatedAt,
    totalCompleted: all.length,
    results: all,
    assessments: data.assessments,
  };
}

module.exports = { create, get, exists, appendResult, aggregate, SESSION_DIR };
