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

### Prerequisites

1. **Python Environment**: Ensure you have the `cp_demo_env` conda environment activated
2. **Google Cloud Authentication**: Run `gcloud auth application-default login` for data access
3. **Node.js**: Version 16+ for the frontend

### Starting All Services

```bash
# Make the start script executable (first time only)
chmod +x start.sh

# Start all services
./start.sh
```

This will start:
- **Frontend**: http://localhost:3000 (Next.js development server)
- **Map Backend**: http://localhost:8000 (Zarr data server)
- **API Backend**: http://localhost:8001 (FastAPI server)

### Manual Start (Alternative)

If you prefer to start services individually:

```bash
# Start map backend
cd backend
python map_server.py

# Start API backend (in another terminal)
cd backend
uvicorn api_server:app --host 0.0.0.0 --port 8001

# Start frontend (in another terminal)
cd frontend
npm run dev
```

## 📊 Features

### 1. Climate Map (`/map`)
- Interactive climate data visualization
- Uses CarbonPlan Maps components
- Displays temperature data from Zarr files

### 2. Overview (`/overview`)
- High-level climate metrics and statistics
- RMSE analysis across different models
- Historical vs. future projections

### 3. Probabilistic Scores (`/probabilistic-scores`)
- Detailed probabilistic analysis
- Interactive charts and visualizations
- Model comparison and uncertainty quantification

## 🔧 Development

### Frontend Development
```bash
cd frontend
npm install          # Install dependencies
npm run dev         # Start development server
npm run build       # Build for production
```

### Backend Development
```bash
cd backend
pip install -r requirements.txt  # Install Python dependencies
python map_server.py            # Test map server
uvicorn api_server:app --reload # Test API server with auto-reload
```

## 🌐 API Endpoints

### Map Backend (Port 8000)
- Serves Zarr data for climate maps
- Static file serving for map data

### API Backend (Port 8001)
- `GET /health` - Health check
- `GET /rmse-zonal-mean?metric={metric}` - RMSE data
- `GET /variable?variable={variable}` - Variable data
- `GET /cache-status` - Cache information

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

## 🐛 Troubleshooting

### Common Issues

1. **"Failed to load RMSE data"**
   - Ensure Google Cloud authentication is set up
   - Check if API backend is running on port 8001

2. **"ReferenceError: self is not defined"**
   - This is a known Plotly.js issue with SSR
   - The error is handled with dynamic imports

3. **Port conflicts**
   - Ensure ports 3000, 8000, and 8001 are available
   - Stop any existing services on these ports

4. **Node.js OpenSSL errors**
   - The start script includes the `--openssl-legacy-provider` flag
   - This handles Node.js v17+ compatibility issues

### Health Checks
```bash
# Check API backend health
curl http://localhost:8001/health

# Check map backend
curl http://localhost:8000

# Check frontend
curl http://localhost:3000
```

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.