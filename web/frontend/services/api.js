import axios from 'axios';

const OVERVIEW_API_BASE_URL = 'http://127.0.0.1:8001';  // RMSE data for overview
const PROBABILISTIC_API_BASE_URL = 'http://127.0.0.1:8002';  // Probabilistic data

// Create axios instances with default config
const overviewApiClient = axios.create({
  baseURL: OVERVIEW_API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

const probabilisticApiClient = axios.create({
  baseURL: PROBABILISTIC_API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// RMSE data endpoint (for overview page)
export const fetchRMSEData = async (metric = 'rmse') => {
  try {
    console.log(`Fetching RMSE data for metric: ${metric}`);
    const response = await overviewApiClient.get(`/rmse-zonal-mean?metric=${metric}`);
    
    if (response.status !== 200) {
      throw new Error(`HTTP error ${response.status}`);
    }
    
    return response.data.zonal_mean_rmse;
  } catch (error) {
    console.error('Failed to load RMSE data:', error);
    throw error;
  }
};

// Probabilistic data endpoint (for probabilistic scores page)
export const fetchProbabilisticData = async (variable, metric, level, region, year, resolution) => {
  try {
    console.log(`Fetching probabilistic data for: ${variable} (${metric})`);
    const response = await probabilisticApiClient.get('/variable', {
      params: {
        variable
      }
    });
    
    if (response.status !== 200) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.data;
  } catch (error) {
    console.error('Failed to fetch probabilistic data:', error);
    throw error;
  }
};



// Legacy function for backward compatibility (remove this later)
export const fetchVariableData = async (variable) => {
  console.warn('fetchVariableData is deprecated. Use fetchProbabilisticData instead.');
  return fetchProbabilisticData(variable, 'crps', 'surface', 'global', '2020', 'low');
};

export { overviewApiClient, probabilisticApiClient }; 