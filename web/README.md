# Carbon Plan Demo

A comprehensive climate data visualization and analysis platform with interactive maps, probabilistic scores, and overview dashboards.

## 🏗️ Project Structure

```
carbon_plan_demo/
├── frontend/          # Next.js frontend application
│   ├── pages/         # Next.js pages
│   ├── components/    # React components
│   ├── styles/        # CSS stylesheets
│   ├── services/      # API services
│   ├── public/        # Static assets
│   └── package.json   # Frontend dependencies
├── backend/           # Python backend services
│   ├── map_server.py  # Zarr data server for climate maps
│   ├── api_server.py  # FastAPI server for RMSE and variable data
│   └── requirements.txt # Python dependencies
└── start.sh          # Script to start all services
```

## 🚀 Quick Start

### Starting All Services

```bash
# navigate to frontend directory and run
npm install

# Make the start script executable (first time only)
# Make sure you are in root directory (web)
chmod +x start.sh

# Start all services
./start.sh
```

This will start:
- **Frontend**: http://localhost:3000 (Next.js development server)
- **Map Backend**: http://localhost:8000 (Zarr data server)
- **API Backend**: http://localhost:8001 (FastAPI server)

## 🔑 Environment Setup

### Google Cloud Authentication
The API backend requires access to Google Cloud Storage for climate data:

```bash
# Install Google Cloud CLI
gcloud auth application-default login
```

### Conda Environment
```bash
# Activate the environment
conda activate cp_demo_env

# Or create if it doesn't exist
conda env create -f env.yml
```
