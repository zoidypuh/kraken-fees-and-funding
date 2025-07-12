import axios from 'axios';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Add auth headers to all requests
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('apiKey');
  const apiSecret = localStorage.getItem('apiSecret');
  
  if (apiKey && apiSecret) {
    config.headers['X-API-Key'] = apiKey;
    config.headers['X-API-Secret'] = apiSecret;
  }
  
  return config;
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

export const getPositionsDetailed = (forceRefresh = false) => 
  api.get('/positions/detailed', { 
    params: forceRefresh ? { force_refresh: true } : {} 
  });

export const getClosedPositions = (days = 30) => 
  api.get('/positions/closed', { params: { days } });

// Market data endpoints
export const getTicker = (symbol) => api.get(`/market/ticker/${symbol}`);

export const getMultipleTickers = (symbols) =>
  api.post('/market/tickers', { symbols });

export const getMarkPrice = (symbol) => api.get(`/market/price/${symbol}`);

export const getFeeInfo = () => api.get('/market/fees');

export const getTradingVolumes = (days = 30, forceRefresh = false) => {
  const params = { days };
  if (forceRefresh) {
    params.force_refresh = true;
  }
  return api.get('/volumes', { params });
};

// Analytics endpoints
export const getChartData = (days = 7, forceRefresh = false) =>
  api.get(`/analytics/chart-data?days=${days}${forceRefresh ? '&force_refresh=true' : ''}`);

export const getFeesData = (days = 7) =>
  api.get(`/analytics/fees?days=${days}`);

export const getFundingData = (days = 7) =>
  api.get(`/analytics/funding?days=${days}`);

export const getSummary = (days = 7) =>
  api.get(`/analytics/summary?days=${days}`);

// Funding endpoints
export const getFundingHistory = (symbol) =>
  api.get(`/funding/history/${symbol}`);

export const getPredictedFunding = (symbol, days) =>
  api.get(`/funding/predict/${symbol}`, { params: { days } });

export default api; 