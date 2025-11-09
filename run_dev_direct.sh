#!/bin/bash

# Document Intelligence Backend - Direct Python Development Server
# This script runs uvicorn directly without UV to avoid package reinstallation issues

echo "🚀 Starting Document Intelligence Backend (Direct Mode)"
echo "📁 Working Directory: $(pwd)"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "   Please copy .env.example to .env and configure your environment variables"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Error: Virtual environment not found!"
    echo "   Please run: uv sync"
    exit 1
fi

# Activate the virtual environment and run directly
echo "🔄 Starting server with optimized file watching (direct Python)..."
echo "📡 Server will be available at: http://127.0.0.1:8000"
echo "📚 API docs will be available at: http://127.0.0.1:8000/docs"
echo ""
echo "💡 Press Ctrl+C to stop the server"
echo ""

# Run uvicorn directly with the virtual environment's Python
.venv/bin/uvicorn app.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000 \
  --reload-dir app \
  --reload-exclude '.venv' \
  --reload-exclude '__pycache__' \
  --reload-exclude '*.pyc' \
  --reload-exclude '.git' \
  --reload-exclude 'logs' \
  --reload-exclude '*.log' \
  --reload-exclude '.pytest_cache' \
  --reload-exclude 'htmlcov' \
  --reload-exclude '.coverage'