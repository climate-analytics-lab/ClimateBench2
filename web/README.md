# Climate Bench Web App

A comprehensive climate data visualization and analysis platform with interactive maps, probabilistic scores, and overview dashboards.

## 🏗️ Project Structure

```
web/
├── frontend/          # Next.js frontend application
│   ├── pages/         # Next.js pages
│   ├── components/    # React components
│   ├── styles/        # CSS stylesheets
│   └── package.json   # Frontend dependencies
├── backend/           # Python backend services
│   ├── data_server.py # Data server for metric table and climate maps
└── minimal_start.sh   # Script to start all services
```

## 🚀 Quick Start

### Starting All Services
You will need to have the google cloud cli installed and set up.

```bash
# navigate to frontend directory and run
cd frontend
npm install
cd ..

# Make the start script executable (first time only)
chmod +x minimal_start.sh

# Start all services
./minimal_start.sh
```

This will start:
- **Frontend**: http://localhost:3000 (Next.js development server)
- **Backend**: http://localhost:8000 (Data server)

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
