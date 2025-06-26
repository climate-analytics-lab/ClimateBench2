# ClimateBench 2.0 Web Application

A modern web application for ClimateBench 2.0 weather forecasting benchmark with a React frontend and FastAPI backend.

## Project Structure

```
web/
├── frontend/          # React application
├── backend/           # FastAPI backend
├── start.sh          # Startup script (starts all services)
├── stop.sh           # Stop script (stops all services)
├── package.json      # NPM scripts for easy management
└── README.md         # This file
```

## Prerequisites

Before running the application, make sure you have the following installed:

- **Node.js** (version 16 or higher)
- **npm** or **yarn**
- **Python** (version 3.8 or higher)
- **pip** (Python package manager)
- **Conda** (for environment management)

## Quick Start (Recommended)

### 🚀 One-Command Startup

The easiest way to run your application is with a single command:

```bash
# Navigate to the web directory
cd myscripts/web

# Start all services with one command
./start.sh
```

This will automatically:
- Start the main backend on port 8000
- Start the probabilistic scores backend on port 8001  
- Start the React frontend on port 3000
- Check if all services are running properly

### 🛑 Stop All Services

To stop all services:

```bash
./stop.sh
```

### 📦 Alternative: Using NPM Scripts

You can also use npm scripts:

```bash
# Install dependencies (first time only)
npm run setup

# Start all services
npm start

# Stop all services
npm run stop
```

## Manual Setup (Alternative)

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

## Running the Application

### Step-by-Step Instructions

1. **Start the Backend** (Terminal 1):
   ```bash
   cd /path/to/ClimateBench2/myscripts/web/backend
   conda activate example_env
   uvicorn index:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Start the Probabilistic Backend** (Terminal 2):
   ```bash
   cd /path/to/ClimateBench2/myscripts/web/backend
   conda activate example_env
   uvicorn probabilistic-scores:app --reload --host 127.0.0.1 --port 8001
   ```

3. **Start the Frontend** (Terminal 3):
   ```bash
   cd /path/to/ClimateBench2/myscripts/web/frontend
   npm install
   npm start
   ```

4. **Access the Application**:
   - Open your browser and go to `http://localhost:3000`
   - The application should now be running with both frontend and backend connected

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

1. **Backend not starting**:
   - Check if Python and required packages are installed
   - Verify the requirements.txt file is present
   - Check for port conflicts (8000, 8001)
   - Make sure conda environment is activated

2. **Frontend not connecting to backend**:
   - Ensure both backend servers are running
   - Check browser console for CORS errors
   - Verify API URLs in `frontend/src/services/api.js`

3. **"Failed to load data" error**:
   - Check if backend servers are running on correct ports
   - Verify API endpoints are accessible
   - Check browser network tab for failed requests

4. **Script permission errors**:
   - Run: `chmod +x start.sh stop.sh`

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