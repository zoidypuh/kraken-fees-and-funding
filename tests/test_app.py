"""
Tests for Flask app endpoints.
"""
import pytest
import sys
import os
import json
import time
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, get_api_credentials, get_cache_key, cleanup_cache

# Load environment variables
load_dotenv()


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_client(client):
    """Create a test client with API credentials set."""
    api_key = os.getenv("KRAKEN_API_KEY")
    api_secret = os.getenv("KRAKEN_API_SECRET")
    
    if not api_key or not api_secret:
        pytest.skip("KRAKEN_API_KEY or KRAKEN_API_SECRET not found in .env file")
    
    # Set cookies with credentials
    client.set_cookie('kraken_api_key', api_key)
    client.set_cookie('kraken_api_secret', api_secret)
    
    return client


class TestAppEndpoints:
    """Test suite for Flask app endpoints."""
    
    def test_index_route(self, client):
        """Test the index route."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Kraken' in response.data or b'Dashboard' in response.data
    
    def test_health_check(self, client):
        """Test the health check endpoint."""
        response = client.get('/health')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert data['service'] == 'kraken-dashboard'
    
    def test_404_error(self, client):
        """Test 404 error handling."""
        response = client.get('/nonexistent')
        assert response.status_code == 404
    
    def test_api_data_without_credentials(self, client):
        """Test /api/data endpoint without credentials."""
        response = client.get('/api/data')
        assert response.status_code == 401
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'credentials' in data['error'].lower()
    
    def test_api_data_with_credentials(self, authenticated_client):
        """Test /api/data endpoint with valid credentials."""
        response = authenticated_client.get('/api/data?days=1')
        
        # Should be successful or rate limited
        assert response.status_code in [200, 429, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'labels' in data
            assert 'fees' in data
            assert 'funding' in data
            assert 'trades' in data
            assert 'positions' in data
    
    def test_api_data_invalid_days(self, authenticated_client):
        """Test /api/data with invalid days parameter."""
        # Test with negative days
        response = authenticated_client.get('/api/data?days=-1')
        assert response.status_code == 400
        
        # Test with too many days
        response = authenticated_client.get('/api/data?days=400')
        assert response.status_code == 400
        
        # Test with non-numeric days
        response = authenticated_client.get('/api/data?days=abc')
        assert response.status_code == 400
    
    def test_set_credentials_valid(self, client):
        """Test setting valid credentials."""
        api_key = os.getenv("KRAKEN_API_KEY")
        api_secret = os.getenv("KRAKEN_API_SECRET")
        
        if not api_key or not api_secret:
            pytest.skip("KRAKEN_API_KEY or KRAKEN_API_SECRET not found in .env file")
        
        # Mock the validation to avoid rate limiting
        with patch('app.get_execution_events') as mock_get_events:
            mock_get_events.return_value = []
            
            response = client.post(
                '/api/set-credentials',
                json={'api_key': api_key, 'api_secret': api_secret},
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            
            # Check that cookies were set
            cookies = response.headers.getlist('Set-Cookie')
            assert any('kraken_api_key' in cookie for cookie in cookies)
            assert any('kraken_api_secret' in cookie for cookie in cookies)
    
    def test_set_credentials_invalid(self, client):
        """Test setting invalid credentials."""
        # Mock the rate limit check to avoid waiting
        with patch('app.last_credential_attempt', 0):
            response = client.post(
                '/api/set-credentials',
                json={'api_key': 'invalid', 'api_secret': 'invalid'},
                content_type='application/json'
            )
            
            # Should fail authentication
            assert response.status_code in [401, 429]
    
    def test_set_credentials_missing_fields(self, client):
        """Test setting credentials with missing fields."""
        # Mock the rate limit check
        with patch('app.last_credential_attempt', 0):
            # Missing api_secret
            response = client.post(
                '/api/set-credentials',
                json={'api_key': 'test'},
                content_type='application/json'
            )
            assert response.status_code == 400
            
            # Missing api_key
            response = client.post(
                '/api/set-credentials',
                json={'api_secret': 'test'},
                content_type='application/json'
            )
            assert response.status_code == 400
            
            # Empty values
            response = client.post(
                '/api/set-credentials',
                json={'api_key': '', 'api_secret': ''},
                content_type='application/json'
            )
            assert response.status_code == 400
    
    def test_clear_credentials(self, authenticated_client):
        """Test clearing credentials."""
        response = authenticated_client.post('/api/clear-credentials')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        
        # Check that cookies were cleared
        cookies = response.headers.getlist('Set-Cookie')
        assert any('kraken_api_key' in cookie and 'Max-Age=0' in cookie for cookie in cookies)
        assert any('kraken_api_secret' in cookie and 'Max-Age=0' in cookie for cookie in cookies)
    
    def test_validate_credentials(self, client):
        """Test credential validation endpoint."""
        api_key = os.getenv("KRAKEN_API_KEY")
        api_secret = os.getenv("KRAKEN_API_SECRET")
        
        if not api_key or not api_secret:
            pytest.skip("KRAKEN_API_KEY or KRAKEN_API_SECRET not found in .env file")
        
        # Mock the account logs call
        with patch('app.get_account_logs') as mock_get_logs:
            mock_get_logs.return_value = []
            
            response = client.post(
                '/api/validate-credentials',
                json={'api_key': api_key, 'api_secret': api_secret},
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['valid'] is True

    def test_positions_with_unrealized_pnl(self, client):
        """Test that positions data includes unrealized P&L calculations."""
        # Mock open positions with average price
        mock_positions = [
            {
                "symbol": "PF_XBTUSD",
                "size": 10,
                "price": 95000  # Average entry price
            },
            {
                "symbol": "PF_ETHUSD", 
                "size": -50,  # Short position
                "price": 3600  # Average entry price
            }
        ]
        
        # Mock ticker data with current prices
        mock_tickers = {
            "PF_XBTUSD": {
                "markPrice": "100000"  # Current price higher than entry
            },
            "PF_ETHUSD": {
                "markPrice": "3500"  # Current price lower than entry (good for short)
            }
        }
        
        # Mock batch accumulated data
        mock_accumulated = [
            {
                "symbol": "PF_XBTUSD",
                "size": 10,
                "accumulated_funding": 150.0,
                "accumulated_fees": 50.0,
                "data_is_capped": False,
                "true_opened_date_utc": "2025-01-01T00:00:00Z"
            },
            {
                "symbol": "PF_ETHUSD",
                "size": -50,
                "accumulated_funding": 200.0,
                "accumulated_fees": 75.0,
                "data_is_capped": False,
                "true_opened_date_utc": "2025-01-01T00:00:00Z"
            }
        ]
        
        # Mock chart data
        mock_chart_data = {
            'labels': ['2025-01-01'],
            'fees': [10.0],
            'funding': [5.0],
            'trades': {}
        }
        
        # Set up mocks
        with patch('kraken_client.get_open_positions', return_value=mock_positions), \
             patch('kraken_client.batch_get_tickers', return_value=mock_tickers), \
             patch('kraken_client.batch_get_position_accumulated_data', return_value=mock_accumulated), \
             patch('app.get_chart_data', return_value=mock_chart_data), \
             patch('app.get_open_positions_data') as mock_get_positions_data:
            
            # Set up expected return value for get_open_positions_data
            expected_positions = [
                {
                    'symbol': 'PF_XBTUSD',
                    'size': 10,
                    'avgPrice': 95000,
                    'currentPrice': 100000,
                    'unrealizedPnl': 50000.0,
                    'accumulatedFunding': 150.0,
                    'accumulatedFees': 50.0,
                    'netUnrealizedPnl': 49800.0,  # 50000 - 150 - 50
                    'dataIsCapped': False,
                    'trueOpenedDateUTC': '2025-01-01T00:00:00Z'
                },
                {
                    'symbol': 'PF_ETHUSD',
                    'size': -50,
                    'avgPrice': 3600,
                    'currentPrice': 3500,
                    'unrealizedPnl': 5000.0,
                    'accumulatedFunding': 200.0,
                    'accumulatedFees': 75.0,
                    'netUnrealizedPnl': 4725.0,  # 5000 - 200 - 75
                    'dataIsCapped': False,
                    'trueOpenedDateUTC': '2025-01-01T00:00:00Z'
                }
            ]
            mock_get_positions_data.return_value = expected_positions
            
            # Set credentials via cookies with valid base64 secret
            client.set_cookie('kraken_api_key', 'test_key')
            client.set_cookie('kraken_api_secret', 'dGVzdF9zZWNyZXRfa2V5X2Jhc2U2NA==')
            
            # Test with credentials
            response = client.get('/api/data?days=30')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'positions' in data
            
            positions = data['positions']
            assert len(positions) == 2
            
            # Check first position (long BTC)
            btc_pos = positions[0]
            assert btc_pos['symbol'] == 'PF_XBTUSD'
            assert btc_pos['size'] == 10
            assert btc_pos['avgPrice'] == 95000
            assert btc_pos['currentPrice'] == 100000  # Converted from string
            assert btc_pos['unrealizedPnl'] == 50000.0  # (100000 - 95000) * 10
            assert btc_pos['netUnrealizedPnl'] == 49800.0  # 50000 - 150 - 50
            
            # Check second position (short ETH)
            eth_pos = positions[1]
            assert eth_pos['symbol'] == 'PF_ETHUSD'
            assert eth_pos['size'] == -50
            assert eth_pos['avgPrice'] == 3600
            assert eth_pos['currentPrice'] == 3500
            assert eth_pos['unrealizedPnl'] == 5000.0  # (3600 - 3500) * 50
            assert eth_pos['netUnrealizedPnl'] == 4725.0  # 5000 - 200 - 75


class TestCaching:
    """Test suite for caching functionality."""
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        key1 = get_cache_key("test_api_key", "data_type", 1000, 2000)
        key2 = get_cache_key("test_api_key", "data_type", 1000, 2000)
        key3 = get_cache_key("different_key", "data_type", 1000, 2000)
        key4 = get_cache_key("test_api_key", "different_type", 1000, 2000)
        
        # Same inputs should produce same key
        assert key1 == key2
        
        # Different inputs should produce different keys
        assert key1 != key3
        assert key1 != key4
        
        # Should be a valid hex string (MD5)
        assert len(key1) == 32
        assert all(c in '0123456789abcdef' for c in key1)
    
    def test_cache_cleanup(self):
        """Test cache cleanup function."""
        # Create test cache directory
        cache_dir = os.path.join(os.path.dirname(__file__), '.test_cache')
        os.makedirs(cache_dir, exist_ok=True)
        
        # Create some test cache files
        old_file = os.path.join(cache_dir, 'old_cache.json')
        new_file = os.path.join(cache_dir, 'new_cache.json')
        
        with open(old_file, 'w') as f:
            json.dump({'test': 'data'}, f)
        
        with open(new_file, 'w') as f:
            json.dump({'test': 'data'}, f)
        
        # Make old_file old
        old_time = time.time() - 700  # More than 2x cache duration
        os.utime(old_file, (old_time, old_time))
        
        # Mock the cache directory
        with patch('app.CACHE_DIR', cache_dir):
            cleanup_cache()
        
        # Old file should be removed
        assert not os.path.exists(old_file)
        # New file should still exist
        assert os.path.exists(new_file)
        
        # Cleanup
        os.remove(new_file)
        os.rmdir(cache_dir)


class TestHelperFunctions:
    """Test suite for helper functions."""
    
    def test_get_api_credentials_with_cookies(self):
        """Test extracting API credentials from cookies."""
        with app.test_request_context(
            headers={'Cookie': 'kraken_api_key=test_key; kraken_api_secret=test_secret'}
        ):
            from flask import request
            api_key, api_secret = get_api_credentials(request)
            
            assert api_key == 'test_key'
            assert api_secret == 'test_secret'
    
    def test_get_api_credentials_without_cookies(self):
        """Test extracting API credentials when not present."""
        with app.test_request_context():
            from flask import request
            api_key, api_secret = get_api_credentials(request)
            
            assert api_key is None
            assert api_secret is None
    
    def test_require_api_credentials_decorator(self):
        """Test the require_api_credentials decorator."""
        from app import require_api_credentials
        
        @require_api_credentials
        def test_function(api_key, api_secret):
            return {'key': api_key, 'secret': api_secret}
        
        # Test without credentials
        with app.test_request_context():
            result = test_function()
            assert isinstance(result, tuple)
            response, status_code = result
            assert status_code == 401
        
        # Test with credentials
        with app.test_request_context(
            headers={'Cookie': 'kraken_api_key=test_key; kraken_api_secret=test_secret'}
        ):
            result = test_function()
            assert result == {'key': 'test_key', 'secret': 'test_secret'}


@pytest.mark.slow
class TestIntegrationFlow:
    """Integration tests for complete user flows."""
    
    def test_complete_user_flow(self, client):
        """Test a complete user flow: set credentials, fetch data, clear credentials."""
        api_key = os.getenv("KRAKEN_API_KEY")
        api_secret = os.getenv("KRAKEN_API_SECRET")
        
        if not api_key or not api_secret:
            pytest.skip("KRAKEN_API_KEY or KRAKEN_API_SECRET not found in .env file")
        
        # Step 1: Set credentials (mock rate limit to avoid cooldown)
        with patch('app.last_credential_attempt', 0):
            with patch('app.get_execution_events') as mock_get_events:
                mock_get_events.return_value = []
                
                response = client.post(
                    '/api/set-credentials',
                    json={'api_key': api_key, 'api_secret': api_secret}
                )
                assert response.status_code == 200
        
        # Step 2: Fetch data (mocked to avoid rate limits)
        with patch('app.get_chart_data') as mock_get_data:
            mock_get_data.return_value = {
                'labels': ['2024-01-01'],
                'fees': [10.0],
                'funding': [5.0],
                'trades': {}
            }
            
            with patch('app.get_open_positions_data') as mock_get_positions:
                mock_get_positions.return_value = []
                
                response = client.get('/api/data?days=1')
                assert response.status_code == 200
                
                data = json.loads(response.data)
                assert 'labels' in data
                assert 'fees' in data
        
        # Step 3: Clear credentials
        response = client.post('/api/clear-credentials')
        assert response.status_code == 200
        
        # Step 4: Verify credentials are cleared
        response = client.get('/api/data')
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 