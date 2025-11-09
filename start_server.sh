#!/bin/bash

# Document Intelligence Backend - Production-ready startup script
# This script ensures clean server startup without package reinstallation loops

echo "🚀 Starting Document Intelligence Backend"
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

# Option 1: Development with auto-reload (DEFAULT)
if [ "$1" == "--reload" ] || [ -z "$1" ]; then
    echo "🔄 Starting in DEVELOPMENT mode with auto-reload"
    echo "📡 Server: http://127.0.0.1:8000"
    echo "📚 API docs: http://127.0.0.1:8000/docs"
    echo ""
    echo "💡 Press Ctrl+C to stop the server"
    echo ""

    # Run with minimal file watching to avoid .venv changes
    exec .venv/bin/uvicorn app.main:app \
        --reload \
        --host 127.0.0.1 \
        --port 8000 \
        --reload-dir app \
        --reload-dir . \
        --reload-include '*.py' \
        --reload-include '*.json' \
        --reload-include '*.yaml' \
        --reload-include '*.yml' \
        --reload-exclude '.venv' \
        --reload-exclude '__pycache__' \
        --reload-exclude '*.pyc' \
        --reload-exclude '.git' \
        --reload-exclude 'logs' \
        --reload-exclude '*.log'

# Option 2: Production without reload
elif [ "$1" == "--production" ]; then
    echo "🏭 Starting in PRODUCTION mode (no auto-reload)"
    echo "📡 Server: http://0.0.0.0:8000"
    echo ""
    echo "💡 Press Ctrl+C to stop the server"
    echo ""

    exec .venv/bin/uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 2 \
        --loop uvloop \
        --access-log

# Option 3: Help
else
    echo "Usage: ./start_server.sh [option]"
    echo ""
    echo "Options:"
    echo "  --reload      Start in development mode with auto-reload (default)"
    echo "  --production  Start in production mode without auto-reload"
    echo ""
    exit 0
fi