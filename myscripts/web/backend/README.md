# ClimateBench 2.0 Backend

This directory contains two FastAPI applications:
- `index.py` for RMSE/Overview endpoints (port 8000)
- `probabilistic-scores.py` for Probabilistic Scores endpoints (port 8001)

## 📁 Backend Structure

```
backend/
├── index.py                    # Main backend server (port 8000)
├── probabilistic-scores.py     # Probabilistic scores backend (port 8001)
├── requirements.txt            # Python dependencies
└── README.md                  # This file
```

## 🏗️ Backend Architecture

### 🖥️ Main Backend (`index.py` - Port 8000)

**Purpose**: Serves RMSE (Root Mean Square Error) data for the Overview page

**Core Components**:
- **FastAPI Application**: Main web server with CORS middleware
- **Data Cache**: Thread-safe in-memory cache for RMSE data
- **Google Cloud Storage Client**: Fetches data from GCS bucket "climatebench"
- **Background Preloader**: Preloads all data at startup for fast response times

**Key Features**:
- **Data Caching**: Preloads all RMSE data at startup for fast response times
- **Google Cloud Storage Integration**: Fetches data from GCS bucket "climatebench"
- **Multiple Metrics**: Supports RMSE, RMSE bias-adjusted, and RMSE anomaly
- **Thread-Safe Operations**: Uses locks for concurrent data access

**API Endpoints**:
- `GET /rmse-zonal-mean?metric={metric}` - Fetch RMSE data for different metrics
- `GET /health` - Health check endpoint
- `GET /cache-status` - Cache information and status

**Data Sources**:
- CSV files from GCS: `results/RMSE/pr/zonal_mean_rmse_-90_90_results.csv`
- Zarr datasets for variable data

### 📊 Probabilistic Scores Backend (`probabilistic-scores.py` - Port 8001)

**Purpose**: Serves probabilistic forecast data for interactive charts

**Core Components**:
- **FastAPI Application**: Web server with CORS middleware
- **Dataset Cache**: Comprehensive cache for observed and predicted datasets
- **ThreadPoolExecutor**: Parallel data loading for efficiency
- **Background Preloader**: Preloads all datasets at startup

**Key Features**:
- **Parallel Data Loading**: Uses ThreadPoolExecutor for efficient dataset loading
- **Comprehensive Caching**: Caches both observed and predicted datasets
- **Variable Support**: Handles multiple climate variables (precipitation, temperature, etc.)
- **Real-time Data Access**: Fast access to preloaded datasets

**API Endpoints**:
- `GET /variable?variable={variable}` - Fetch variable data for charts
- `GET /health` - Health check endpoint
- `GET /cache-status` - Cache information and status

**Data Sources**:
- Observed data: `gs://climatebench/observations/preprocessed/`
- Predicted data: `gs://climatebench/results/RMSE/`

### 🔧 Dependencies

```
fastapi              # Web framework for building APIs
uvicorn             # ASGI server for running FastAPI
pandas              # Data manipulation and analysis
xarray              # Multi-dimensional arrays for scientific data
google-cloud-storage # Google Cloud Storage access
```

### 🚀 Backend Features

- **Automatic Data Preloading**: Both backends preload data at startup
- **CORS Support**: Configured for cross-origin requests from frontend
- **Error Handling**: Comprehensive error handling and logging
- **Health Monitoring**: Health check endpoints for service monitoring
- **Thread Safety**: Safe concurrent access to shared data structures
- **Performance Optimization**: Caching and parallel loading for fast response times

## 🚀 Quick Start (Recommended)

### Using the Parent Directory Scripts

The easiest way to run the entire application (backend + frontend) is from the parent directory:

```bash
# Navigate to the web directory
cd myscripts/web

# Make scripts executable (first time only)
chmod +x start.sh stop.sh

# Start all services (both backends + frontend)
./start.sh

# Stop all services
./stop.sh
```

This will automatically start:
- ✅ Main backend on port 8000
- ✅ Probabilistic scores backend on port 8001
- ✅ React frontend on port 3000

## Manual Setup (Advanced Users)

If you prefer to run services manually or need more control:

### 1. Environment Setup

```bash
# Create and activate your environment
conda create -n climatebench python=3.10
conda activate climatebench

# Or use the existing environment
conda activate example_env
```

### 2. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt
```

### 3. Set up Google Cloud Credentials

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```

### 4. Start the Servers

**Option 1: Start both servers in separate terminals**

Terminal 1 (Main Backend):
```bash
uvicorn index:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 (Probabilistic Scores Backend):
```bash
uvicorn probabilistic-scores:app --reload --host 127.0.0.1 --port 8001
```

**Option 2: Start both servers in background**
```bash
# Start main backend in background
uvicorn index:app --reload --host 127.0.0.1 --port 8000 &

# Start probabilistic scores backend in background
uvicorn probabilistic-scores:app --reload --host 127.0.0.1 --port 8001 &
```

## API Documentation

Once the servers are running, you can access the interactive API documentation:

- **Main Backend API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Probabilistic Scores API Docs**: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

## Troubleshooting

### Common Issues

1. **Port already in use**:
   ```bash
   # Stop all services first
   cd .. && ./stop.sh
   
   # Then start again
   ./start.sh
   ```

2. **Conda environment not found**:
   ```bash
   # List available environments
   conda env list
   
   # Create new environment if needed
   conda create -n example_env python=3.10
   conda activate example_env
   ```

3. **Dependencies not installed**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Google Cloud credentials missing**:
   - Set up your service account key
   - Export the credentials path
   - Or use the parent directory script which handles this automatically

## API Endpoints

### Main Backend (Port 8000)
- `GET /rmse-zonal-mean?metric={metric}` - Fetch RMSE data for different metrics

### Probabilistic Scores Backend (Port 8001)
- `GET /variable?variable={variable}` - Fetch variable data for charts 