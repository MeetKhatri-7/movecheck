# ═══════════════════════════════════════════════════════════════════
#  MobilityAI / MoveCheck — single-container production image
#
#  Runs all three tiers in one container:
#    • Python/Flask CV processor  → 127.0.0.1:5001  (internal only)
#    • Node/Express API           → 0.0.0.0:$PORT   (public)
#    • Built React SPA            → served statically by Node
#
#  One container is deliberate: free hosts (Hugging Face Spaces, Cloud Run)
#  expose exactly ONE port, and keeping Node→Python on loopback means the
#  CV service is never reachable from the internet.
#
#  Build:  docker build -t movecheck .
#  Run:    docker run -p 7860:7860 movecheck
# ═══════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────
#  Stage 1 — build the React frontend
# ───────────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Install deps first so this layer caches unless the lockfile changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# The bundled copy talks to the API on its OWN origin, so the container is a
# complete, self-contained app. (The Vercel copy is built separately with
# VITE_API_BASE_URL pointing at this container's public URL.)
ENV VITE_API_BASE_URL=/api
RUN npm run build


# ───────────────────────────────────────────────────────────────────
#  Stage 2 — install Node backend dependencies
# ───────────────────────────────────────────────────────────────────
FROM node:20-slim AS backend-deps

WORKDIR /build
COPY backend/package.json backend/package-lock.json ./
RUN npm ci --omit=dev


# ───────────────────────────────────────────────────────────────────
#  Stage 3 — runtime: Python 3.11 + Node 20 + the app
# ───────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# System libraries.
#   libglib2.0-0 : required by opencv (even the headless build)
#   ffmpeg       : video demuxing/decoding backend for cv2.VideoCapture.
#                  Without it, many phone-recorded .mp4/.mov files fail to open.
#   curl         : used by the container HEALTHCHECK
# opencv-contrib-python-headless needs NO libgl1/X11 — that is why the
# headless variant is pinned in requirements.txt.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node 20 runtime, copied from the official image rather than installed via
# apt (Debian's nodejs package is far older than what the backend needs).
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

WORKDIR /app

# ── Python dependencies ──────────────────────────────────────────
# Copied alone first so the (slow, ~1 GB) CV install layer is cached and only
# reruns when requirements.txt actually changes.
COPY processor/requirements.txt /app/processor/requirements.txt
RUN pip install --no-cache-dir -r /app/processor/requirements.txt

# ── Application code ─────────────────────────────────────────────
COPY processor/ /app/processor/
COPY backend/   /app/backend/
COPY --from=backend-deps    /build/node_modules /app/backend/node_modules
COPY --from=frontend-builder /build/dist        /app/frontend/dist

# ── MediaPipe pose model ─────────────────────────────────────────
# Fetched at BUILD time rather than committed to git. The file is 29 MB, which
# would force Git LFS on Hugging Face (required above 10 MB) and bloat the
# repo. Baking it in also avoids a 29 MB download on every cold start —
# utils/landmarks.py would otherwise fetch it at runtime on first use.
# Placed AFTER the code COPY so it is never overwritten by a stale local copy.
ADD --chmod=644 \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task \
    /app/processor/pose_landmarker_heavy.task

# (Demo reports live in frontend/public/demo and are already inside the
#  built dist copied above — no separate COPY needed.)

COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# ── Runtime configuration ────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    PORT=7860 \
    PROCESSOR_HOST=127.0.0.1 \
    PROCESSOR_PORT=5001 \
    PYTHON_URL=http://127.0.0.1:5001 \
    SERVE_STATIC_DIR=/app/frontend/dist \
    SESSION_DIR=/tmp/sessions \
    UPLOAD_DIR=/tmp/uploads \
    HOT_RELOAD=0 \
    MAX_UPLOAD_MB=512 \
    PROCESS_TIMEOUT_MS=900000 \
    CORS_ORIGIN=*

# Hosted platforms (Hugging Face Spaces) run containers as a non-root user
# with UID 1000. Writable runtime dirs must exist and be owned by it, and
# HOME must be writable because MediaPipe/matplotlib write caches there.
RUN useradd -m -u 1000 appuser \
    && mkdir -p /tmp/sessions /tmp/uploads \
    && chown -R appuser:appuser /app /tmp/sessions /tmp/uploads
USER appuser
ENV HOME=/home/appuser

EXPOSE 7860

# Give the CV stack a long grace period: the first boot loads the MediaPipe
# heavy model, which is slow on a shared vCPU.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["/app/start.sh"]
