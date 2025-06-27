# ClimateBench 2.0 Web Application

A modern web application for ClimateBench 2.0 weather forecasting benchmark with a React frontend and FastAPI backend.

## Project Structure

```
web/
├── frontend/          # React application
├── backend/           # FastAPI backend
│   ├── index.py              # Main backend server (port 8000)
│   ├── probabilistic-scores.py  # Probabilistic scores backend (port 8001)
│   ├── requirements.txt      # Python dependencies
│   └── README.md            # Backend-specific documentation
├── start.sh          # Startup script (starts all services)
├── stop.sh           # Stop script (stops all services)
├── package.json      # NPM scripts for easy management
└── README.md         # This file
```

## Backend Architecture

The backend consists of two separate FastAPI applications:

### 🖥️ Main Backend (`index.py` - Port 8000)
**Purpose**: Serves RMSE (Root Mean Square Error) data for the Overview page

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

### 🔧 Backend Dependencies
```
fastapi              # Web framework
uvicorn             # ASGI server
pandas              # Data manipulation
xarray              # Multi-dimensional arrays
google-cloud-storage # Google Cloud Storage access
```

### 🚀 Backend Features
- **Automatic Data Preloading**: Both backends preload data at startup
- **CORS Support**: Configured for cross-origin requests from frontend
- **Error Handling**: Comprehensive error handling and logging
- **Health Monitoring**: Health check endpoints for service monitoring
- **Thread Safety**: Safe concurrent access to shared data structures

## Prerequisites

Before running the application, make sure you have the following installed:

- **Node.js** (version 16 or higher)
- **npm** or **yarn**
- **Python** (version 3.8 or higher)
- **pip** (Python package manager)
- **Conda** (for environment management)

## 🚀 Quick Start (Recommended)

### One-Command Startup

The easiest way to run your application is with a single command:

```bash
# Navigate to the web directory
cd myscripts/web

# Make scripts executable (first time only)
chmod +x start.sh stop.sh

# Start all services with one command
./start.sh
```

This will automatically:
- ✅ Start the main backend on port 8000
- ✅ Start the probabilistic scores backend on port 8001  
- ✅ Start the React frontend on port 3000
- ✅ Check if all services are running properly
- ✅ Display access URLs

### 🛑 Stop All Services

To stop all services:

```bash
./stop.sh
```

### 📱 Access the Application

After running `./start.sh`, access your application at:
- **Frontend**: http://localhost:3000
- **Main API**: http://127.0.0.1:8000
- **Probabilistic API**: http://127.0.0.1:8001

## 📦 Alternative: Using NPM Scripts

You can also use npm scripts:

```bash
# Install dependencies (first time only)
npm run setup

# Start all services
npm start

# Stop all services
npm run stop
```

## Manual Setup (Advanced Users)

If you prefer to run services manually or need more control:

### 1. Backend Setup

First, set up and start the FastAPI backend:

```bash
# Navigate to the backend directory
cd backend

# Activate conda environment (if using conda)
conda activate example_env

# Install Python dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn index:app --reload --host 127.0.0.1 --port 8000
```

The backend will be available at:
- Main API: `http://127.0.0.1:8000`
- Probabilistic Scores API: `http://127.0.0.1:8001`

### 2. Frontend Setup

In a new terminal window, set up and start the React frontend:

```bash
# Navigate to the frontend directory
cd frontend

# Install Node.js dependencies
npm install

# Start the development server
npm start
```

The frontend will be available at `http://localhost:3000`

## Application Features

### Overview Page
- Displays project information and deterministic scores
- Interactive metric selection (RMSE, RMSE bias-adjusted, RMSE anomaly)
- Real-time data visualization

### Probabilistic Scores Page
- Interactive charts for analyzing probabilistic forecast metrics
- Variable selection (e.g., precipitation, temperature)
- Time series visualization with Plotly.js

## API Endpoints

### Main Backend (Port 8000)
- `GET /rmse-zonal-mean?metric={metric}` - Fetch RMSE data for different metrics

### Probabilistic Scores Backend (Port 8001)
- `GET /variable?variable={variable}` - Fetch variable data for charts

## Troubleshooting

### Common Issues

1. **Script permission errors**:
   ```bash
   chmod +x start.sh stop.sh
   ```

2. **Backend not starting**:
   - Check if Python and required packages are installed
   - Verify the requirements.txt file is present
   - Check for port conflicts (8000, 8001)
   - Make sure conda environment is activated

3. **Frontend not connecting to backend**:
   - Ensure both backend servers are running
   - Check browser console for CORS errors
   - Verify API URLs in `frontend/src/services/api.js`

4. **"Failed to load data" error**:
   - Check if backend servers are running on correct ports
   - Verify API endpoints are accessible
   - Check browser network tab for failed requests

5. **Port already in use**:
   ```bash
   # Stop all services first
   ./stop.sh
   
   # Then start again
   ./start.sh
   ```

### Port Configuration

If you need to change the default ports:

- **Backend**: Modify the port in `backend/index.py`
- **Frontend**: Update API URLs in `frontend/src/services/api.js`

## Development

### Frontend Development
```bash
cd frontend
npm start          # Start development server
npm test           # Run tests
npm run build      # Build for production
```

### Backend Development
```bash
cd backend
conda activate example_env
uvicorn index:app --reload --host 127.0.0.1 --port 8000
```

## Dependencies

### Frontend Dependencies
- React 19.1.0
- React Router DOM 7.6.2
- Plotly.js 3.0.1
- Axios 1.10.0

### Backend Dependencies
- FastAPI
- Google Cloud Storage
- Pandas
- Xarray
- Uvicorn

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test both frontend and backend
5. Submit a pull request

## Support

For issues and questions:
- Check the troubleshooting section above
- Review the individual README files in `frontend/` and `backend/` directories
- File a GitHub issue with detailed error information

## License

This project is part of the ClimateBench 2.0 initiative for weather forecasting benchmarks. 