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

## Getting Started

### Prerequisites

- Node.js (version 16 or higher)
- npm or yarn
- Backend API server running (see backend setup)

### Installation

1. Clone the repository and navigate to the React app directory:
```bash
cd climatebench-react
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
