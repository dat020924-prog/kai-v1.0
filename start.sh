#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "======================================"
echo "  TradingView Lite - Starting..."
echo "======================================"

# Check venv
if [ ! -d "$ROOT_DIR/.venv" ]; then
  echo "[1/4] Creating Python virtual environment..."
  python3 -m venv "$ROOT_DIR/.venv"
fi

# Install backend deps
echo "[2/4] Installing backend dependencies..."
source "$ROOT_DIR/.venv/bin/activate"
pip install -r "$BACKEND_DIR/requirements.txt" --quiet

# Start backend in background
echo "[3/4] Starting backend on http://localhost:8000 ..."
(
  cd "$BACKEND_DIR"
  python app.py
) &
BACKEND_PID=$!

sleep 2

# Install frontend deps
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[4/4] Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install --silent)
fi

# Start frontend in background
echo "Starting frontend on http://localhost:5173 ..."
(
  cd "$FRONTEND_DIR"
  npm run dev
) &
FRONTEND_PID=$!

echo ""
echo "======================================"
echo "  ✅ App is running!"
echo "======================================"
echo "  Frontend : http://localhost:5173"
echo "  Backend  : http://localhost:8000"
echo "  API Docs : http://localhost:8000/docs"
echo "======================================"
echo "  Press Ctrl+C to stop"
echo "======================================"

# Wait for both
wait $BACKEND_PID $FRONTEND_PID
