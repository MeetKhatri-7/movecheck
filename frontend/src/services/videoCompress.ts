/**
 * Browser-side video downscaling, run before upload.
 *
 * WHY THIS EXISTS
 * ---------------
 * Two independent constraints meet here:
 *
 *  1. Managed hosts cap request bodies (Cloud Run: 32 MiB). A 4K phone clip
 *     is 80–150 MB, so it is rejected at the edge before our API ever sees
 *     it — surfacing as an opaque 413 with no CORS header.
 *
 *  2. The analyser already discards anything above 1920px:
 *     `MAX_INFERENCE_DIM = 1920` in processor/utils/landmarks.py downscales
 *     every frame before pose estimation.
 *
 * Together those mean shrinking to 1080p costs **nothing in accuracy** — we
 * are only dropping pixels the server was going to throw away anyway — while
 * cutting upload size roughly 10×.
 *
 * WHAT IS PRESERVED
 * -----------------
 * Timing is sacred here: hold durations, rep tempo and bar velocity are all
 * derived from frame rate. So the re-encode runs at 1× real time (never
 * sped up) and targets a constant 30 fps, which is what the analyser assumes
 * when a container reports no usable rate. Output duration therefore matches
 * the input, and every time-based metric stays valid.
 *
 * Anything unsupported degrades to returning the original file untouched.
 */

/** Longest edge to keep. Matches MAX_INFERENCE_DIM on the Python side. */
const MAX_DIM = 1920;

/** Target frame rate. The analyser's fallback assumption is 30 fps. */
const TARGET_FPS = 30;

/** Bits per pixel-second. ~4 Mbps at 1080p30 — visually clean for pose work. */
const BITS_PER_PIXEL_SECOND = 0.065;

/** Files at or below this are uploaded untouched — re-encoding would be waste. */
const SKIP_BELOW_BYTES = 12 * 1024 * 1024;

/** Container/codec preference. MP4 first: cleanest metadata for OpenCV. */
const MIME_CANDIDATES = [
  'video/mp4;codecs=avc1.42E01E',
  'video/mp4',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
  'video/webm',
];

export interface CompressProgress {
  /** 0..1 through this file. */
  ratio: number;
  stage: 'probing' | 'encoding' | 'done' | 'skipped';
}

function pickMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  for (const m of MIME_CANDIDATES) {
    try {
      if (MediaRecorder.isTypeSupported(m)) return m;
    } catch { /* older browsers throw instead of returning false */ }
  }
  return null;
}

function extensionFor(mime: string): string {
  return mime.includes('mp4') ? 'mp4' : 'webm';
}

/** Browser can actually do this? */
export function canCompress(): boolean {
  return (
    typeof document !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    typeof HTMLCanvasElement !== 'undefined' &&
    typeof HTMLCanvasElement.prototype.captureStream === 'function' &&
    pickMimeType() !== null
  );
}

function loadVideo(file: File): Promise<{ el: HTMLVideoElement; url: string }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const el = document.createElement('video');
    el.preload = 'auto';
    el.muted = true;
    // iOS refuses to play inline without this and will not render to canvas.
    el.playsInline = true;
    el.src = url;

    const fail = (msg: string) => { URL.revokeObjectURL(url); reject(new Error(msg)); };
    el.onerror = () => fail(`Could not read video (${file.name}) — unsupported codec?`);
    el.onloadedmetadata = () => {
      if (!el.videoWidth || !el.videoHeight) return fail('Video has no visual track');
      resolve({ el, url });
    };
  });
}

/**
 * Downscale `file` so its longest edge is at most 1920px.
 *
 * Returns the ORIGINAL file when compression is unnecessary or impossible —
 * this never throws for capability reasons, so callers can always upload
 * whatever comes back.
 */
export async function compressVideo(
  file: File,
  onProgress?: (p: CompressProgress) => void,
): Promise<File> {
  // Small files: nothing to gain, and re-encoding would only cost quality.
  if (file.size <= SKIP_BELOW_BYTES) {
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }
  if (!canCompress()) {
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }

  onProgress?.({ ratio: 0, stage: 'probing' });

  let el: HTMLVideoElement;
  let url: string;
  try {
    ({ el, url } = await loadVideo(file));
  } catch {
    // Unreadable here doesn't mean unreadable server-side (ffmpeg is far more
    // permissive than a browser). Let the upload proceed and let the API judge.
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }

  const srcW = el.videoWidth;
  const srcH = el.videoHeight;
  const longest = Math.max(srcW, srcH);

  // Already within budget and merely a big file? Still worth re-encoding,
  // because bitrate — not resolution — is what makes phone clips huge.
  const scale = longest > MAX_DIM ? MAX_DIM / longest : 1;
  // Codecs require even dimensions.
  const dstW = Math.max(2, Math.round((srcW * scale) / 2) * 2);
  const dstH = Math.max(2, Math.round((srcH * scale) / 2) * 2);

  const mimeType = pickMimeType()!;
  const canvas = document.createElement('canvas');
  canvas.width = dstW;
  canvas.height = dstH;
  const ctx = canvas.getContext('2d', { alpha: false });
  if (!ctx) {
    URL.revokeObjectURL(url);
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }

  const stream = canvas.captureStream(TARGET_FPS);
  const bitrate = Math.min(
    8_000_000,
    Math.max(1_200_000, Math.round(dstW * dstH * TARGET_FPS * BITS_PER_PIXEL_SECOND)),
  );

  let recorder: MediaRecorder;
  try {
    recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: bitrate });
  } catch {
    URL.revokeObjectURL(url);
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }

  const chunks: BlobPart[] = [];
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };

  const finished = new Promise<Blob>((resolve, reject) => {
    recorder.onstop = () => resolve(new Blob(chunks, { type: mimeType }));
    recorder.onerror = () => reject(new Error('Recorder failed'));
  });

  const duration = Number.isFinite(el.duration) && el.duration > 0 ? el.duration : 0;
  let stopped = false;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    try { recorder.stop(); } catch { /* already stopping */ }
    stream.getTracks().forEach(t => t.stop());
  };

  // Draw every source frame we're given. requestVideoFrameCallback fires once
  // per decoded frame, which keeps the copy faithful; rAF is the fallback.
  const anyEl = el as any;
  const useRVFC = typeof anyEl.requestVideoFrameCallback === 'function';
  const draw = () => {
    if (stopped) return;
    ctx.drawImage(el, 0, 0, dstW, dstH);
    if (duration) onProgress?.({ ratio: Math.min(1, el.currentTime / duration), stage: 'encoding' });
    if (el.ended || el.paused) { stop(); return; }
    if (useRVFC) anyEl.requestVideoFrameCallback(draw);
    else requestAnimationFrame(draw);
  };

  el.onended = stop;

  recorder.start(1000);
  try {
    await el.play();
  } catch {
    // Autoplay blocked — cannot drive the canvas, so ship the original.
    stop();
    URL.revokeObjectURL(url);
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }
  draw();

  // Safety net: never hang if 'ended' is missed. Real time + 50% + 10s.
  const timeoutMs = duration ? duration * 1500 + 10_000 : 120_000;
  const timer = setTimeout(stop, timeoutMs);

  let blob: Blob;
  try {
    blob = await finished;
  } catch {
    clearTimeout(timer);
    URL.revokeObjectURL(url);
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }
  clearTimeout(timer);
  URL.revokeObjectURL(url);

  // A "compressed" file that grew, or came back suspiciously tiny (a dropped
  // or truncated recording), is not trustworthy — keep the original.
  if (blob.size === 0 || blob.size >= file.size) {
    onProgress?.({ ratio: 1, stage: 'skipped' });
    return file;
  }

  const base = file.name.replace(/\.[^.]+$/, '');
  const out = new File([blob], `${base}-1080p.${extensionFor(mimeType)}`, { type: mimeType });
  onProgress?.({ ratio: 1, stage: 'done' });
  return out;
}
