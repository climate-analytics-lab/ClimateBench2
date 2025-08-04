#!/bin/bash

# Function to check if conda env is active
is_conda_env_active() {
  [[ "$CONDA_DEFAULT_ENV" == "cp_demo_env" ]]
}

# Function to check if a port is in use
check_port() {
  lsof -i :$1 >/dev/null 2>&1
}

# Start the map backend server (data_server.py in backend/)
echo "Starting map backend server on port 8000..."
cd backend
if is_conda_env_active; then
  echo "cp_demo_env already active."
  python data_server.py &
else
  echo "Activating cp_demo_env..."
  source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null
  conda activate cp_demo_env
  python data_server.py &
fi
BACKEND_PID=$!
cd ..

# Wait a moment for map backend to start
sleep 90 # give time for data to download from cloud
if check_port 8000; then
  echo "✅ Map backend is running on http://localhost:8000"
else
  echo "❌ Map backend failed to start on port 8000"
fi

# Start the frontend server (in frontend/)
echo "Starting frontend server on port 3000..."
cd frontend
NODE_OPTIONS=--openssl-legacy-provider npm run dev &
FRONTEND_PID=$!
cd ..

# Wait a moment for frontend to start
sleep 3
if check_port 3000; then
  echo "✅ Frontend is running on http://localhost:3000"
else
  echo "❌ Frontend failed to start on port 3000"
fi

echo ""
echo "🎉 All services started!"
echo "   Frontend: http://localhost:3000"
echo "   Map Backend: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for all four to exit
wait $BACKEND_PID $FRONTEND_PID 