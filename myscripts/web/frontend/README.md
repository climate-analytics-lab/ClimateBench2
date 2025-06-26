# ClimateBench 2.0 React Application

A modern React-based frontend for the ClimateBench 2.0 weather forecasting benchmark application.

## Features

- **Overview Page**: Displays project information and deterministic scores with interactive metric selection
- **Probabilistic Scores Page**: Interactive charts and widgets for analyzing probabilistic forecast metrics
- **Responsive Design**: Mobile-friendly interface that works on all device sizes
- **Real-time Data**: Live updates and interactive visualizations using Plotly.js
- **Modern UI**: Clean, professional interface with Google Material Design principles

## Technology Stack

- **React 18**: Modern React with hooks and functional components
- **React Router**: Client-side routing for navigation
- **Plotly.js**: Interactive charts and visualizations
- **Axios**: HTTP client for API communication
- **CSS3**: Modern styling with responsive design

## 🚀 Quick Start (Recommended)

### Using the Parent Directory Scripts

The easiest way to run the entire application (frontend + backend) is from the parent directory:

```bash
# Navigate to the web directory
cd myscripts/web

# Make scripts executable (first time only)
chmod +x start.sh stop.sh

# Start all services (frontend + both backends)
./start.sh

# Stop all services
./stop.sh
```

This will automatically start:
- ✅ React frontend on port 3000
- ✅ Main backend on port 8000
- ✅ Probabilistic scores backend on port 8001

### Frontend Only Development

If you want to run just the frontend for development:

```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies (first time only)
npm install

# Start the development server
npm start
```

The application will open at `http://localhost:3000`

## Getting Started

### Prerequisites

- Node.js (version 16 or higher)
- npm or yarn
- Backend API server running (see backend setup or use `./start.sh` from parent directory)

### Installation

1. Clone the repository and navigate to the React app directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm start
```

The application will open at `http://localhost:3000`

### Backend Setup

Make sure the FastAPI backend is running on `http://127.0.0.1:8000` before using the React app.

**Option 1: Use the parent directory script (Recommended)**
```bash
cd myscripts/web
./start.sh
```

**Option 2: Manual backend setup**
```bash
cd backend
conda activate example_env
uvicorn index:app --reload --host 127.0.0.1 --port 8000
```

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── Header.js       # Application header
│   ├── Navigation.js   # Navigation bar
│   └── Footer.js       # Application footer
├── pages/              # Page components
│   ├── Overview.js     # Main overview page
│   └── ProbabilisticScores.js  # Probabilistic scores page
├── services/           # API services
│   └── api.js         # HTTP client and API functions
├── App.js             # Main application component
└── index.js           # Application entry point
```

## Available Scripts

- `npm start`: Runs the app in development mode
- `npm test`: Launches the test runner
- `npm run build`: Builds the app for production
- `npm run eject`: Ejects from Create React App (not recommended)

## API Endpoints

The React app communicates with the following backend endpoints:

- `GET /rmse-zonal-mean?metric={metric}`: Fetch RMSE data for different metrics
- `GET /variable?variable={variable}`: Fetch variable data for charts

## Troubleshooting

### Common Issues

1. **"Failed to load data" error**:
   - Ensure backend servers are running (use `./start.sh` from parent directory)
   - Check browser console for CORS errors
   - Verify API URLs in `src/services/api.js`

2. **Port 3000 already in use**:
   ```bash
   # Stop all services
   cd .. && ./stop.sh
   
   # Start again
   ./start.sh
   ```

3. **Frontend not connecting to backend**:
   - Check if backend servers are running on ports 8000 and 8001
   - Verify API endpoints are accessible
   - Check browser network tab for failed requests

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is part of the ClimateBench 2.0 initiative for weather forecasting benchmarks.

## Support

For questions and support, please visit our documentation or file a GitHub issue.
