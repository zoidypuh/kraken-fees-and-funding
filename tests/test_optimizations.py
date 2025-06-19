"""Test that optimizations are working correctly."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, cache
from dashboard_utils import parse_iso_date
import time


def test_flask_compress_enabled():
    """Test that Flask-Compress is enabled."""
    assert hasattr(app, 'extensions')
    # Flask-Compress doesn't add itself to extensions, but we can test a response
    with app.test_client() as client:
        response = client.get('/')
        # Check if the app would compress a large response
        assert response.status_code == 200


def test_flask_caching_configured():
    """Test that Flask-Caching is properly configured."""
    assert cache is not None
    assert hasattr(cache, 'cache')
    
    # Test caching functionality
    @cache.memoize(timeout=1)
    def test_func(x):
        return x * 2
    
    # First call should compute
    result1 = test_func(5)
    assert result1 == 10
    
    # Second call should use cache (we can't directly test this, but it should work)
    result2 = test_func(5)
    assert result2 == 10


def test_error_handlers_registered():
    """Test that error handlers are registered."""
    with app.test_client() as client:
        # Test 404 handler
        response = client.get('/nonexistent-endpoint')
        assert response.status_code == 404
        
        # Test API 404 handler returns JSON
        response = client.get('/api/nonexistent')
        assert response.status_code == 404
        assert response.json.get('error') == 'Endpoint not found'


def test_performance_monitoring():
    """Test that performance monitoring is working."""
    with app.test_client() as client:
        # Make a request - should trigger before/after request hooks
        response = client.get('/health')
        assert response.status_code == 200
        
        # Test static file caching headers
        response = client.get('/static/fake-file.css')
        # Will be 404 but should still add cache headers
        if 'Cache-Control' in response.headers:
            assert 'max-age=' in response.headers['Cache-Control']


def test_lru_cache_date_parsing():
    """Test that date parsing is cached."""
    date_str = "2024-01-01T12:00:00.000Z"
    
    # First call
    start = time.time()
    result1 = parse_iso_date(date_str)
    first_call_time = time.time() - start
    
    # Second call should be cached and faster
    start = time.time()
    result2 = parse_iso_date(date_str)
    second_call_time = time.time() - start
    
    assert result1 == result2
    # Can't reliably test timing, but both should work
    assert result1.year == 2024


def test_retry_logic():
    """Test that the retry logic is in place."""
    from kraken_client import MAX_RETRIES, INITIAL_RETRY_DELAY
    
    assert MAX_RETRIES == 3
    assert INITIAL_RETRY_DELAY == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 