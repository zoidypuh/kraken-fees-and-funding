const CACHE_PREFIX = 'kraken_dashboard_';
const POSITIONS_CACHE_KEY = `${CACHE_PREFIX}positions`;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

export const positionsCache = {
  set: (data) => {
    try {
      const cacheData = {
        data,
        timestamp: Date.now(),
      };
      localStorage.setItem(POSITIONS_CACHE_KEY, JSON.stringify(cacheData));
    } catch (error) {
      console.error('Error saving positions to cache:', error);
    }
  },

  get: () => {
    try {
      const cached = localStorage.getItem(POSITIONS_CACHE_KEY);
      if (!cached) return null;

      const { data, timestamp } = JSON.parse(cached);
      
      // Check if cache is still valid (within TTL)
      const age = Date.now() - timestamp;
      if (age > CACHE_TTL) {
        // Cache is stale but still return it (will be used while loading fresh data)
        return { data, isStale: true, age };
      }

      return { data, isStale: false, age };
    } catch (error) {
      console.error('Error reading positions from cache:', error);
      return null;
    }
  },

  clear: () => {
    try {
      localStorage.removeItem(POSITIONS_CACHE_KEY);
    } catch (error) {
      console.error('Error clearing positions cache:', error);
    }
  },
};

// Format cache age for display
export const formatCacheAge = (ageMs) => {
  const seconds = Math.floor(ageMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ago`;
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s ago`;
  } else {
    return `${seconds}s ago`;
  }
}; 