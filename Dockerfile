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
#  Stage 3 — runtime: Node 20 (base) + Python 3.11 (from Debian)
#
#  Base is the Node image and Python comes from apt, rather than the
#  reverse. Debian Bookworm ships Python 3.11 — exactly the version
#  MediaPipe publishes wheels for — so both runtimes are native to the
#  image. Copying a Node binary into a Python image "works" until a
#  shared-library mismatch breaks it at runtime; this avoids that class
#  of failure entirely.
# ───────────────────────────────────────────────────────────────────
FROM node:20-slim AS runtime

# System packages.
#   python3 / venv  : Bookworm's Python 3.11
#   libglib2.0-0    : required by OpenCV, even the headless build
#   ffmpeg          : the decoder backend behind cv2.VideoCapture. Without it
#                     many phone-recorded .mp4/.mov files simply fail to open.
#   curl            : used by the HEALTHCHECK and by deploy/start.sh
#
#   libgles2 / libegl1 / libgl1 : REQUIRED BY MEDIAPIPE, not by OpenCV.
#     MediaPipe's Tasks API dlopen()s the OpenGL ES stack when it builds its
#     graph — on Linux this happens even for pure CPU inference. Without them
#     PoseLandmarker creation dies with:
#         OSError: libGLESv2.so.2: cannot open shared object file
#     and every video fails to process. `libgles2` is the Bookworm package
#     that provides libGLESv2.so.2.
#
#     Note this is unrelated to opencv-contrib-python-headless, which
#     genuinely needs no GL — the headless variant is still correct, it just
#     doesn't cover MediaPipe's own runtime dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        libglib2.0-0 \
        libgles2 \
        libegl1 \
        libgl1 \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Debian marks its system Python as externally managed (PEP 668), so pip
# cannot install into it. A venv is the supported path — and putting it on
# PATH means `python`/`pip`/`gunicorn` resolve to it with no activation.
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# ── Python dependencies ──────────────────────────────────────────
# Copied alone first so the slow (~1 GB) CV install layer stays cached and
# only reruns when requirements.txt actually changes.
COPY processor/requirements.txt /app/processor/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/processor/requirements.txt

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
# Uses curl rather than `ADD <url>` because ADD with --chmod on a remote URL
# needs BuildKit; this works on any builder.
RUN curl -fsSL -o /app/processor/pose_landmarker_heavy.task \
      https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task \
    && chmod 644 /app/processor/pose_landmarker_heavy.task \
    && test -s /app/processor/pose_landmarker_heavy.task

# ── Build-time smoke test ────────────────────────────────────────
# Actually construct a PoseLandmarker here, at build time. MediaPipe resolves
# its native dependencies (the GLES/EGL stack) lazily on first use, so a
# missing shared library would otherwise stay invisible until a user uploaded
# a video — surfacing as "every analysis fails" in production rather than as a
# failed build. This makes that class of bug impossible to ship.
RUN python -c "\
import cv2, mediapipe as mp;\
from mediapipe.tasks import python as mp_tasks;\
from mediapipe.tasks.python import vision;\
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions;\
opts = PoseLandmarkerOptions(\
    base_options=mp_tasks.BaseOptions(model_asset_path='/app/processor/pose_landmarker_heavy.task'),\
    running_mode=vision.RunningMode.VIDEO, num_poses=1);\
lm = PoseLandmarker.create_from_options(opts); lm.close();\
print('✓ smoke test: mediapipe', mp.__version__, '+ opencv', cv2.__version__, '- PoseLandmarker OK')"

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

# Run unprivileged. Hugging Face Spaces expects UID 1000; the node image
# already provides exactly that as the `node` user, so reuse it rather than
# creating a second account on the same UID (useradd would fail).
# HOME must be writable — MediaPipe and friends write caches there.
RUN mkdir -p /tmp/sessions /tmp/uploads \
    && chown -R node:node /app /tmp/sessions /tmp/uploads
USER node
ENV HOME=/home/node

EXPOSE 7860

# Give the CV stack a long grace period: the first boot loads the MediaPipe
# heavy model, which is slow on a shared vCPU.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["/app/start.sh"]
