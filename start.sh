#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── Check .env ────────────────────────────────────────────────────────────────
if [ ! -f backend/.env ]; then
  echo "⚠️  backend/.env not found."
  echo "   Copy the example and add your Anthropic API key:"
  echo "   cp backend/.env.example backend/.env"
  echo "   Then edit backend/.env and set ANTHROPIC_API_KEY=sk-ant-..."
  exit 1
fi

# ── Install Python deps if needed ─────────────────────────────────────────────
if ! python3 -c "import fastapi, uvicorn, anthropic" 2>/dev/null; then
  echo "📦 Installing Python dependencies..."
  pip install -r backend/requirements.txt
fi

# ── Load data if DB doesn't exist ─────────────────────────────────────────────
if [ ! -f backend/o2c.db ]; then
  echo "📊 Loading SAP O2C data into SQLite..."
  python3 backend/load_data.py
fi

# ── Start server ──────────────────────────────────────────────────────────────
echo ""
echo "🚀 Starting Order-to-Cash Graph Explorer"
echo "   Open: http://localhost:8000"
echo ""

uvicorn backend.main:app --host 0.0.0.0 --port 8000
