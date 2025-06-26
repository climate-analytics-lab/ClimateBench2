import axios from 'axios';

const MAIN_API_BASE_URL = 'http://127.0.0.1:8000';
const PROBABILISTIC_API_BASE_URL = 'http://127.0.0.1:8001';

// Create axios instances with default config
const mainApiClient = axios.create({
  baseURL: MAIN_API_BASE_URL,
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

// RMSE data endpoint (from main backend)
export const fetchRMSEData = async (metric = 'rmse') => {
  try {
    console.log(`Fetching data for metric: ${metric}`);
    const response = await mainApiClient.get(`/rmse-zonal-mean?metric=${metric}`);
    
    if (response.status !== 200) {
      throw new Error(`HTTP error ${response.status}`);
    }
    
    return response.data.zonal_mean_rmse;
  } catch (error) {
    console.error('Failed to load RMSE data:', error);
    throw error;
  }
};

// Variable data endpoint (from probabilistic scores backend)
export const fetchVariableData = async (variable) => {
  try {
    const response = await probabilisticApiClient.get(`/variable?variable=${variable}`);
    
    if (response.status !== 200) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.data;
  } catch (error) {
    console.error('Failed to fetch variable data:', error);
    throw error;
  }
};

export { mainApiClient, probabilisticApiClient }; 