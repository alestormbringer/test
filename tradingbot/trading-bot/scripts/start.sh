#!/bin/bash
set -e

echo "Starting Crypto Trading Bot..."

# Create directories
mkdir -p logs data/reports

# Copy .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example - please configure before running live trading"
fi

# Start with docker-compose
if command -v docker-compose &> /dev/null; then
    docker-compose up -d postgres redis
    echo "Waiting for database..."
    sleep 5
    docker-compose up trading-bot
else
    echo "Running locally (no Docker)..."
    python main.py
fi
