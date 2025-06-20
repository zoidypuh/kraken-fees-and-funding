/**
 * Kraken Dashboard API Client
 * Provides a clean interface to all backend API endpoints
 */

class KrakenAPI {
    constructor() {
        this.baseUrl = '';  // Use relative URLs
    }

    // Helper method for API calls
    async _fetch(url, options = {}) {
        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API Error (${url}):`, error);
            throw error;
        }
    }

    // Authentication endpoints
    async checkAuthStatus() {
        return this._fetch('/api/auth/status');
    }

    async setCredentials(apiKey, apiSecret) {
        return this._fetch('/api/auth/credentials', {
            method: 'POST',
            body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret })
        });
    }

    async clearCredentials() {
        return this._fetch('/api/auth/credentials', {
            method: 'DELETE'
        });
    }

    // Position endpoints
    async getPositions() {
        return this._fetch('/api/positions/');
    }

    async getPositionsDetailed() {
        return this._fetch('/api/positions/detailed');
    }

    async getPositionsDetailedAsync() {
        return this._fetch('/api/positions/detailed-async');
    }

    async getPositionHistory(symbol) {
        return this._fetch(`/api/positions/${symbol}/history`);
    }

    // Market data endpoints
    async getTicker(symbol) {
        return this._fetch(`/api/market/ticker/${symbol}`);
    }

    async getMultipleTickers(symbols) {
        return this._fetch('/api/market/tickers', {
            method: 'POST',
            body: JSON.stringify({ symbols })
        });
    }

    async getMarkPrice(symbol) {
        return this._fetch(`/api/market/price/${symbol}`);
    }

    // Analytics endpoints
    async getChartData(days = 7) {
        return this._fetch(`/api/analytics/chart-data?days=${days}`);
    }

    async getChartDataAsync(days = 7) {
        return this._fetch(`/api/analytics/chart-data-async?days=${days}`);
    }

    async getFeesData(days = 7) {
        return this._fetch(`/api/analytics/fees?days=${days}`);
    }

    async getFundingData(days = 7) {
        return this._fetch(`/api/analytics/funding?days=${days}`);
    }

    async getSummary(days = 7) {
        return this._fetch(`/api/analytics/summary?days=${days}`);
    }



    // Utility methods
    async checkAsyncSupport() {
        try {
            // Try to use an async endpoint
            await this.getChartDataAsync(1);
            return true;
        } catch (error) {
            if (error.message.includes('501')) {
                return false;
            }
            // If it's a different error, async might be available
            return true;
        }
    }

    async refreshPositionPrices(positions) {
        if (!positions || positions.length === 0) return positions;
        
        const symbols = positions.map(p => p.symbol);
        const tickers = await this.getMultipleTickers(symbols);
        
        return positions.map(pos => ({
            ...pos,
            currentPrice: tickers[pos.symbol]?.markPrice || pos.currentPrice
        }));
    }
}

// Create global API instance
window.krakenAPI = new KrakenAPI(); 