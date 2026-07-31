#!/bin/bash
# MobilityAI / MoveCheck — start all 3 servers for LOCAL DEVELOPMENT.
#
# For a production-parity run (single container, built frontend, same image
# that gets deployed):
#     docker compose up --build     → http://localhost:7860

export PATH="/opt/homebrew/bin:$PATH"
DIR="$(cd "$(dirname "$0")" && pwd)"

# HOT_RELOAD=1 makes the Python router re-import analyzers whose source
# changed, so threshold edits apply without restarting Flask. Off by default
# (and in the container) because it stats every loaded module per request.
export HOT_RELOAD=1

echo ""
echo "🚀 Starting MobilityAI (development)..."
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:3001"
echo "   Processor: http://localhost:5001"
echo ""

# Handle path with colon for Python and Node/Vite PATH issues
if [[ "$DIR" == *":"* ]]; then
    echo "⚠️  Detected colon in path. Setting up symlink at /tmp/mobility_project to bypass PATH issues..."
    ln -sfn "$DIR" /tmp/mobility_project
    RUN_DIR="/tmp/mobility_project"
else
    RUN_DIR="$DIR"
fi

# Start Python processor
echo "🔬 Starting Python processor..."
cd "$RUN_DIR/processor"
./venv/bin/python app.py &
PYTHON_PID=$!

# Start Node.js backend
echo "⚡ Starting Node.js backend..."
cd "$RUN_DIR/backend"
node server.js &
NODE_PID=$!

# Start React frontend
echo "🎨 Starting React frontend..."
cd "$RUN_DIR/frontend"
node node_modules/vite/bin/vite.js &
VITE_PID=$!

echo ""
echo "✅ All servers started!"
echo "   Open http://localhost:5173 in your browser"
echo ""
echo "Press Ctrl+C to stop all servers"

cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    kill $PYTHON_PID $NODE_PID $VITE_PID 2>/dev/null
    wait $PYTHON_PID $NODE_PID $VITE_PID 2>/dev/null
    echo "✅ All servers stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM
wait
