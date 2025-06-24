import axios from 'axios';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Helper method for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized
      window.dispatchEvent(new CustomEvent('unauthorized'));
    }
    console.error(`API Error:`, error);
    throw error;
  }
);

// Authentication endpoints
export const checkAuthStatus = () => api.get('/auth/status');

export const setCredentials = (apiKey, apiSecret) =>
  api.post('/auth/credentials', { api_key: apiKey, api_secret: apiSecret });

export const clearCredentials = () => api.delete('/auth/credentials');

// Position endpoints
export const getPositions = () => api.get('/positions/');

export const getPositionsDetailed = () => api.get('/positions/detailed');

// Market data endpoints
export const getTicker = (symbol) => api.get(`/market/ticker/${symbol}`);

export const getMultipleTickers = (symbols) =>
  api.post('/market/tickers', { symbols });

export const getMarkPrice = (symbol) => api.get(`/market/price/${symbol}`);

export const getFeeInfo = () => api.get('/market/fees');

export const getTradingVolumes = (days = 30) => {
  return api.get('/volumes', { params: { days } });
};

// Analytics endpoints
export const getChartData = (days = 7) =>
  api.get(`/analytics/chart-data?days=${days}`);

export const getFeesData = (days = 7) =>
  api.get(`/analytics/fees?days=${days}`);

export const getFundingData = (days = 7) =>
  api.get(`/analytics/funding?days=${days}`);

export const getSummary = (days = 7) =>
  api.get(`/analytics/summary?days=${days}`);

export default api; 