#!/bin/bash

# Document Intelligence Backend - Development Server
# This script starts the FastAPI development server with optimized file watching

echo "🚀 Starting Document Intelligence Backend (Development Mode)"
echo "📁 Working Directory: $(pwd)"
echo "🐍 Using UV for dependency management"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "   Please copy .env.example to .env and configure your environment variables"
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv is not installed!"
    echo "   Please install uv: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Start the development server with file watcher optimization
echo "🔄 Starting server with optimized file watching..."
echo "📡 Server will be available at: http://127.0.0.1:8000"
echo "📚 API docs will be available at: http://127.0.0.1:8000/docs"
echo ""
echo "💡 Press Ctrl+C to stop the server"
echo ""

# Using exec to avoid UV reinstalling packages on every run
exec uv run uvicorn app.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000 \
  --reload-dir app \
  --reload-exclude '.venv/*' \
  --reload-exclude '*.pyc' \
  --reload-exclude '__pycache__' \
  --reload-exclude '.git' \
  --reload-exclude 'node_modules' \
  --reload-exclude '.pytest_cache' \
  --reload-exclude '*.egg-info' \
  --reload-exclude 'build' \
  --reload-exclude 'dist' \
  --reload-exclude '*.log'