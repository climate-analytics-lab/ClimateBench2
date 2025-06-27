#!/bin/bash

# ClimateBench 2.0 Web Application Startup Script
# This script starts both backend servers and the frontend

echo "🚀 Starting ClimateBench 2.0 Web Application..."

# Function to check if a port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null ; then
        echo "❌ Port $1 is already in use. Please stop the service using port $1 first."
        exit 1
    fi
}

# Check if ports are available
echo "🔍 Checking if ports are available..."
check_port 8000
check_port 8001
check_port 3000

# Function to start a service
start_service() {
    local name=$1
    local command=$2
    local port=$3
    
    echo "🔄 Starting $name on port $port..."
    eval "$command" &
    echo "✅ $name started in background (PID: $!)"
}

# Navigate to the web directory
cd "$(dirname "$0")"

# Start backend servers
echo ""
echo "🔧 Starting Backend Servers..."

# Check if conda is available and get its path
if command -v conda &> /dev/null; then
    echo "📦 Using conda environment..."
    CONDA_BASE=$(conda info --base)
    CONDA_ACTIVATE="$CONDA_BASE/etc/profile.d/conda.sh"
    
    # Start main backend (port 8000) with conda environment
    start_service "Main Backend" "source $CONDA_ACTIVATE && conda activate example_env && cd backend && uvicorn index:app --reload --host 127.0.0.1 --port 8000" 8000

    # Start probabilistic scores backend (port 8001) with conda environment
    start_service "Probabilistic Scores Backend" "source $CONDA_ACTIVATE && conda activate example_env && cd backend && uvicorn probabilistic-scores:app --reload --host 127.0.0.1 --port 8001" 8001
else
    echo "⚠️  Conda not found, trying without conda environment..."
    # Start main backend (port 8000) without conda
    start_service "Main Backend" "cd backend && uvicorn index:app --reload --host 127.0.0.1 --port 8000" 8000

    # Start probabilistic scores backend (port 8001) without conda
    start_service "Probabilistic Scores Backend" "cd backend && uvicorn probabilistic-scores:app --reload --host 127.0.0.1 --port 8001" 8001
fi

# Wait a moment for backends to start
sleep 5

# Start frontend
echo ""
echo "🎨 Starting Frontend..."
cd frontend
start_service "Frontend" "npm start" 3000

# Wait for all services to start
echo ""
echo "⏳ Waiting for all services to start..."
sleep 8

# Check if services are running
echo ""
echo "🔍 Checking service status..."

if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "✅ Main Backend (port 8000): Running"
else
    echo "❌ Main Backend (port 8000): Not running"
    echo "💡 Try running manually: cd backend && conda activate example_env && uvicorn index:app --reload --host 127.0.0.1 --port 8000"
fi

if lsof -Pi :8001 -sTCP:LISTEN -t >/dev/null ; then
    echo "✅ Probabilistic Scores Backend (port 8001): Running"
else
    echo "❌ Probabilistic Scores Backend (port 8001): Not running"
    echo "💡 Try running manually: cd backend && conda activate example_env && uvicorn probabilistic-scores:app --reload --host 127.0.0.1 --port 8001"
fi

if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null ; then
    echo "✅ Frontend (port 3000): Running"
else
    echo "❌ Frontend (port 3000): Not running"
fi

echo ""
echo "🎉 ClimateBench 2.0 Web Application is starting!"
echo ""
echo "📱 Access your application at:"
echo "   Frontend: http://localhost:3000"
echo "   Main API: http://127.0.0.1:8000"
echo "   Probabilistic API: http://127.0.0.1:8001"
echo ""
echo "🛑 To stop all services, run: ./stop.sh"
echo ""

# Keep the script running to maintain the background processes
wait 