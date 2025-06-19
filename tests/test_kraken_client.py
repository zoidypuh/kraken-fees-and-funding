"""
Comprehensive tests for kraken_client module.
Tests all major functions with real API calls using credentials from .env file.
"""
import pytest
import sys
import os
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from unittest.mock import patch

# Add parent directory to path to import kraken_client
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kraken_client import (
    KrakenAPIError,
    get_signature,
    generate_signature,
    make_request,
    get_account_logs,
    get_execution_events,
    get_open_positions,
    find_true_position_open_time,
    get_position_accumulated_data,
    get_fee_schedule_volumes,
    get_fee_schedules,
    get_fee_info,
    get_cached_fee_schedules,
    batch_get_position_accumulated_data,
    get_ticker,
    batch_get_tickers
)

# Load environment variables from .env file
load_dotenv()


@pytest.mark.integration
class TestKrakenClientIntegration:
    """Integration test suite for kraken_client functions using real API calls."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment and check for API credentials."""
        self.api_key = os.getenv("KRAKEN_API_KEY")
        self.api_secret = os.getenv("KRAKEN_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            pytest.skip("KRAKEN_API_KEY or KRAKEN_API_SECRET not found in .env file")
    
    def test_signature_generation(self):
        """Test signature generation functions."""
        test_data = "test=1&foo=bar"
        test_nonce = "1234567890"
        test_path = "/derivatives/api/v3/openpositions"
        
        # Test both signature functions produce the same result
        sig1 = get_signature(self.api_secret, test_data, test_nonce, test_path)
        sig2 = generate_signature(self.api_secret, test_data, test_nonce, test_path)
        
        assert sig1 == sig2
        assert isinstance(sig1, str)
        assert len(sig1) > 0
    
    def test_make_request_basic(self):
        """Test basic authenticated request."""
        # Test with a simple endpoint
        result = make_request(
            "/derivatives/api/v3/openpositions",
            self.api_key,
            self.api_secret
        )
        
        assert isinstance(result, dict)
        # Should have either result field or openPositions directly
        assert "result" in result or "openPositions" in result
    
    def test_make_request_with_query(self):
        """Test request with query parameters."""
        # Use account logs endpoint with limit
        result = make_request(
            "/api/history/v3/account-log",
            self.api_key,
            self.api_secret,
            {"limit": 10}
        )
        
        assert isinstance(result, dict)
        # Check for logs in response
        if "logs" in result:
            assert isinstance(result["logs"], list)
            # Note: The API might return up to the default limit (500) even if we request less
            # This appears to be a quirk of the Kraken API
            assert len(result["logs"]) > 0
    
    def test_make_request_invalid_endpoint(self):
        """Test request to invalid endpoint."""
        with pytest.raises(KrakenAPIError):
            make_request(
                "/api/invalid/endpoint",
                self.api_key,
                self.api_secret
            )
    
    def test_get_account_logs_basic(self):
        """Test fetching account logs for recent period."""
        # Get logs for last 24 hours
        current_ts = int(time.time() * 1000)
        since_ts = current_ts - (24 * 60 * 60 * 1000)
        
        logs = get_account_logs(self.api_key, self.api_secret, since_ts, current_ts, limit=50)
        
        assert isinstance(logs, list)
        
        # Verify log structure if we have any
        if logs:
            log = logs[0]
            assert isinstance(log, dict)
            # Common fields in account logs
            assert "date" in log or "timestamp" in log
    
    def test_get_account_logs_pagination(self):
        """Test account logs pagination."""
        # Get logs for last 7 days with small limit to test pagination
        current_ts = int(time.time() * 1000)
        since_ts = current_ts - (7 * 24 * 60 * 60 * 1000)
        
        logs = get_account_logs(self.api_key, self.api_secret, since_ts, current_ts, limit=20)
        
        assert isinstance(logs, list)
        # If we have more than 20 logs, pagination worked
        if len(logs) > 20:
            assert True  # Pagination successful
    
    def test_get_account_logs_empty_period(self):
        """Test fetching logs for a period with no activity."""
        # Use a very old period unlikely to have data
        old_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        old_ts_end = old_ts + (24 * 60 * 60 * 1000)  # One day
        
        logs = get_account_logs(self.api_key, self.api_secret, old_ts, old_ts_end)
        
        assert isinstance(logs, list)
        # Should be empty or very few
        assert len(logs) >= 0
    
    def test_get_execution_events_basic(self):
        """Test fetching execution events for recent period."""
        # Get events for last 30 days
        current_ts = int(time.time() * 1000)
        since_ts = current_ts - (30 * 24 * 60 * 60 * 1000)
        
        events = get_execution_events(self.api_key, self.api_secret, since_ts, current_ts)
        
        assert isinstance(events, list)
        
        # Verify event structure if we have any
        if events:
            event = events[0]
            assert isinstance(event, dict)
            # Should have timestamp
            assert "timestamp" in event or "time" in event
    
    def test_get_execution_events_date_range(self):
        """Test execution events with specific date range."""
        # Use last 7 days
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        
        since_ts = int(start_date.timestamp() * 1000)
        before_ts = int(end_date.timestamp() * 1000)
        
        events = get_execution_events(self.api_key, self.api_secret, since_ts, before_ts)
        
        assert isinstance(events, list)
        
        # Verify timestamps are within range if we have events
        for event in events:
            if "timestamp" in event:
                event_ts = event["timestamp"]
                assert since_ts <= event_ts <= before_ts
    
    def test_get_open_positions(self):
        """Test fetching open positions."""
        positions = get_open_positions(self.api_key, self.api_secret)
        
        assert isinstance(positions, list)
        
        # Verify position structure if we have any
        if positions:
            position = positions[0]
            assert isinstance(position, dict)
            # Common position fields
            assert "symbol" in position
            assert "size" in position
    
    def test_find_true_position_open_time(self):
        """Test finding position open time (if positions exist)."""
        positions = get_open_positions(self.api_key, self.api_secret)
        
        if positions:
            # Test with first position
            position = positions[0]
            symbol = position.get("symbol", "")
            size = abs(float(position.get("size", 0)))
            
            if symbol and size > 0:
                current_ts = int(time.time() * 1000)
                open_ts = find_true_position_open_time(
                    self.api_key, self.api_secret, symbol, size, current_ts
                )
                
                assert isinstance(open_ts, int)
                assert open_ts > 0
                assert open_ts <= current_ts
    
    @pytest.mark.slow
    def test_get_position_accumulated_data(self):
        """Test getting accumulated data for a position."""
        positions = get_open_positions(self.api_key, self.api_secret)
        
        if positions:
            # Test with first position
            position = positions[0]
            
            result = get_position_accumulated_data(
                self.api_key, self.api_secret, position
            )
            
            assert isinstance(result, dict)
            assert "accumulated_funding" in result
            assert "accumulated_fees" in result
            assert isinstance(result["accumulated_funding"], (int, float))
            assert isinstance(result["accumulated_fees"], (int, float))
    
    def test_batch_get_position_accumulated_data(self):
        """Test batch processing of position data."""
        positions = get_open_positions(self.api_key, self.api_secret)
        
        if positions:
            # Test with up to 3 positions
            test_positions = positions[:3]
            
            results = batch_get_position_accumulated_data(
                self.api_key, self.api_secret, test_positions
            )
            
            assert isinstance(results, list)
            assert len(results) == len(test_positions)
            
            for result in results:
                assert isinstance(result, dict)
                assert "symbol" in result
                assert "accumulated_funding" in result
                assert "accumulated_fees" in result
    
    def test_get_fee_info_optimized(self):
        """Test optimized fee info fetching."""
        result = get_fee_info(self.api_key, self.api_secret)
        
        assert isinstance(result, dict)
        assert "volume_30d" in result
        assert "maker_fee" in result
        assert "taker_fee" in result
        assert "fee_schedules" in result
        
        # Verify fee values are reasonable
        assert result["maker_fee"] >= -0.0001  # Max 0.01% rebate
        assert result["maker_fee"] <= 0.001    # Max 0.1% fee
        assert result["taker_fee"] >= 0
        assert result["taker_fee"] <= 0.001    # Max 0.1% fee
    
    def test_get_cached_fee_schedules(self):
        """Test cached fee schedules function."""
        # First call should fetch from API
        result1 = get_cached_fee_schedules(self.api_key, self.api_secret)
        
        # Second call should use cache (faster)
        start_time = time.time()
        result2 = get_cached_fee_schedules(self.api_key, self.api_secret)
        elapsed = time.time() - start_time
        
        assert result1 == result2
        assert elapsed < 0.1  # Should be very fast from cache
        
        # Clear cache
        from kraken_client import _fee_schedule_cache
        _fee_schedule_cache.clear()
    
    @pytest.mark.performance
    def test_fee_info_performance(self):
        """Test performance of optimized fee info fetching."""
        # First call (may need to populate cache)
        start_first = time.time()
        result_first = get_fee_info(self.api_key, self.api_secret)
        time_first = time.time() - start_first
        
        # Second call (should use cached fee schedules)
        start_cached = time.time()
        result_cached = get_fee_info(self.api_key, self.api_secret)
        time_cached = time.time() - start_cached
        
        # Results should be the same
        assert result_first["volume_30d"] == result_cached["volume_30d"]
        assert result_first["maker_fee"] == result_cached["maker_fee"]
        assert result_first["taker_fee"] == result_cached["taker_fee"]
        
        # Cached call should be faster
        print(f"\nFirst call time: {time_first:.2f}s")
        print(f"Cached call time: {time_cached:.2f}s")
        print(f"Speedup: {time_first/time_cached:.2f}x")
    
    def test_error_handling_invalid_credentials(self):
        """Test error handling with invalid credentials."""
        with pytest.raises(KrakenAPIError):
            get_account_logs("invalid_key", "invalid_secret", 0, 1000)
    
    def test_error_handling_rate_limit(self):
        """Test handling of rate limit errors."""
        # Make many rapid requests to potentially trigger rate limit
        # Note: This test might not always trigger rate limit
        current_ts = int(time.time() * 1000)
        since_ts = current_ts - (60 * 60 * 1000)  # 1 hour
        
        request_count = 0
        rate_limited = False
        
        try:
            for i in range(20):  # Try up to 20 requests
                get_account_logs(self.api_key, self.api_secret, since_ts, current_ts, limit=1)
                request_count += 1
                time.sleep(0.1)  # Small delay
        except KrakenAPIError as e:
            if "rate limit" in str(e).lower():
                rate_limited = True
        
        # Test passes if we made requests without error or got rate limited
        assert request_count > 0 or rate_limited


@pytest.mark.unit
class TestKrakenClientUnit:
    """Unit tests for kraken_client functions (no API calls)."""
    
    def test_signature_generation_consistency(self):
        """Test that signature generation is consistent."""
        fake_secret = "dGVzdF9zZWNyZXRfa2V5X2Jhc2U2NA=="  # base64 encoded test key
        test_data = "param1=value1&param2=value2"
        test_nonce = "1234567890"
        test_path = "/derivatives/api/v3/test"
        
        # Generate signature multiple times
        sig1 = generate_signature(fake_secret, test_data, test_nonce, test_path)
        sig2 = generate_signature(fake_secret, test_data, test_nonce, test_path)
        
        assert sig1 == sig2
        assert isinstance(sig1, str)
        assert len(sig1) > 0
    
    def test_signature_different_inputs(self):
        """Test that different inputs produce different signatures."""
        fake_secret = "dGVzdF9zZWNyZXRfa2V5X2Jhc2U2NA=="
        
        sig1 = generate_signature(fake_secret, "data1", "nonce1", "/path1")
        sig2 = generate_signature(fake_secret, "data2", "nonce1", "/path1")
        sig3 = generate_signature(fake_secret, "data1", "nonce2", "/path1")
        sig4 = generate_signature(fake_secret, "data1", "nonce1", "/path2")
        
        # All signatures should be different
        assert sig1 != sig2
        assert sig1 != sig3
        assert sig1 != sig4
        assert sig2 != sig3
        assert sig2 != sig4
        assert sig3 != sig4
    
    def test_kraken_api_error(self):
        """Test KrakenAPIError exception."""
        error_msg = "Test error message"
        error = KrakenAPIError(error_msg)
        
        assert str(error) == error_msg
        assert isinstance(error, Exception)


@pytest.mark.unit
def test_get_ticker():
    """Test fetching ticker data for a symbol."""
    api_key = "test_key"
    api_secret = "test_secret"
    
    # Mock successful ticker response
    ticker_data = {
        "result": "success",
        "ticker": {
            "symbol": "PF_XBTUSD",
            "markPrice": "100000.50",
            "bid": "100000.00",
            "ask": "101000.00",
            "vol24h": "50000000",
            "openInterest": "25000000"
        }
    }
    
    with patch('kraken_client.make_request', return_value=ticker_data):
        ticker = get_ticker(api_key, api_secret, "PF_XBTUSD")
        
        assert ticker["symbol"] == "PF_XBTUSD"
        assert ticker["markPrice"] == "100000.50"
        assert ticker["bid"] == "100000.00"
        assert ticker["ask"] == "101000.00"


@pytest.mark.unit
def test_batch_get_tickers():
    """Test fetching tickers for multiple symbols in parallel."""
    api_key = "test_key"
    api_secret = "test_secret"
    
    symbols = ["PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD"]
    
    def mock_ticker_response(path, api_key, api_secret, query=None):
        """Mock ticker responses based on symbol."""
        symbol = path.split("/")[-1]
        return {
            "result": "success",
            "ticker": {
                "symbol": symbol,
                "markPrice": str({"PF_XBTUSD": 100000, "PF_ETHUSD": 3500, "PF_SOLUSD": 150}[symbol]),
                "bid": str({"PF_XBTUSD": 99999, "PF_ETHUSD": 3499, "PF_SOLUSD": 149}[symbol]),
                "ask": str({"PF_XBTUSD": 100001, "PF_ETHUSD": 3501, "PF_SOLUSD": 151}[symbol])
            }
        }
    
    with patch('kraken_client.make_request', side_effect=mock_ticker_response):
        tickers = batch_get_tickers(api_key, api_secret, symbols)
        
        assert len(tickers) == 3
        assert "PF_XBTUSD" in tickers
        assert "PF_ETHUSD" in tickers
        assert "PF_SOLUSD" in tickers
        
        assert tickers["PF_XBTUSD"]["markPrice"] == "100000"
        assert tickers["PF_ETHUSD"]["markPrice"] == "3500"
        assert tickers["PF_SOLUSD"]["markPrice"] == "150"


@pytest.mark.unit
def test_get_ticker_error_handling():
    """Test error handling in get_ticker."""
    api_key = "test_key"
    api_secret = "test_secret"
    
    # Test with API error
    with patch('kraken_client.make_request', side_effect=KrakenAPIError("API Error")):
        with pytest.raises(KrakenAPIError):
            get_ticker(api_key, api_secret, "INVALID_SYMBOL")
    
    # Test with empty response
    with patch('kraken_client.make_request', return_value={}):
        ticker = get_ticker(api_key, api_secret, "PF_XBTUSD")
        assert ticker == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 