#!/bin/bash

# ClimateBench 2.0 Web Application Stop Script
# This script stops all running services

echo "🛑 Stopping ClimateBench 2.0 Web Application..."

# Function to stop service on a port
stop_service() {
    local port=$1
    local service_name=$2
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo "🔄 Stopping $service_name on port $port..."
        lsof -ti :$port | xargs kill -9
        echo "✅ $service_name stopped"
    else
        echo "ℹ️  $service_name on port $port is not running"
    fi
}

# Stop all services
stop_service 8000 "Main Backend"
stop_service 8001 "Probabilistic Scores Backend"
stop_service 3000 "Frontend"

echo ""
echo "🎉 All services stopped!"
echo ""
echo "💡 To start the application again, run: ./start.sh" 