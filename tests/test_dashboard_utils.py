"""
Tests for dashboard_utils module.
"""
import pytest
from datetime import datetime, timezone, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard_utils import (
    get_period_boundaries,
    extract_asset_from_contract,
    aggregate_logs_by_day,
    calculate_unrealized_pnl
)


class TestDashboardUtils:
    """Test suite for dashboard_utils functions."""
    
    def test_get_period_boundaries_basic(self):
        """Test basic period boundary calculation."""
        # Test with 30 days
        since_ts, before_ts = get_period_boundaries(30)
        
        # Check that timestamps are integers
        assert isinstance(since_ts, int)
        assert isinstance(before_ts, int)
        
        # Check that before_ts is greater than since_ts
        assert before_ts > since_ts
        
        # Check that the difference is approximately 30 days (in milliseconds)
        diff_ms = before_ts - since_ts
        diff_days = diff_ms / (1000 * 60 * 60 * 24)
        assert 29.5 < diff_days < 30.5  # Allow some tolerance
    
    def test_get_period_boundaries_various_periods(self):
        """Test period boundaries for various day counts."""
        test_cases = [1, 7, 14, 30, 90, 365]
        
        for days in test_cases:
            since_ts, before_ts = get_period_boundaries(days)
            
            # Convert to datetime for easier checking
            since_dt = datetime.fromtimestamp(since_ts / 1000, tz=timezone.utc)
            before_dt = datetime.fromtimestamp(before_ts / 1000, tz=timezone.utc)
            
            # Check that dates are reasonable
            now = datetime.now(timezone.utc)
            assert since_dt < before_dt
            # before_ts is the start of tomorrow, which could be in the future
            assert before_dt <= now + timedelta(days=1)
            assert (now - since_dt).days <= days + 1  # Allow 1 day tolerance
    
    def test_extract_asset_from_contract_futures(self):
        """Test extracting asset from futures contract symbols."""
        test_cases = [
            ("PI_XBTUSD", "BTC"),  # XBT is converted to BTC
            ("PF_ETHUSD", "ETH"),
            ("FI_XBTUSD_240329", "BTC"),  # XBT is converted to BTC
            ("FF_ETHUSD_240628", "ETH"),
            ("PF_SOLUSD", "SOL"),
            ("PI_LTCUSD", "PILTC"),  # PI_ prefix is not removed
        ]
        
        for contract, expected_asset in test_cases:
            assert extract_asset_from_contract(contract) == expected_asset
    
    def test_extract_asset_from_contract_special_cases(self):
        """Test extracting asset from special contract formats."""
        test_cases = [
            ("XBTUSD", "BTC"),  # Direct pair - XBT converted to BTC
            ("ETHUSD", "ETH"),  # Direct pair
            ("BTC-PERP", "Unknown"),  # Perpetual format - no USD suffix, returns Unknown
            ("ETH-PERP", "Unknown"),  # Perpetual format - no USD suffix, returns Unknown
            ("", "Unknown"),  # Empty string
            ("INVALID", "Unknown"),  # Invalid format
            ("USD", "Unknown"),  # Just USD
        ]
        
        for contract, expected_asset in test_cases:
            assert extract_asset_from_contract(contract) == expected_asset
    
    def test_extract_asset_from_contract_case_insensitive(self):
        """Test that asset extraction is case insensitive."""
        test_cases = [
            ("pi_xbtusd", "BTC"),  # XBT converted to BTC
            ("PF_ethusd", "ETH"),
            ("Pi_XbTuSd", "BTC"),  # XBT converted to BTC
        ]
        
        for contract, expected_asset in test_cases:
            assert extract_asset_from_contract(contract) == expected_asset
    
    def test_aggregate_logs_by_day_empty(self):
        """Test aggregating empty log list."""
        result = aggregate_logs_by_day([])
        assert result == {}
    
    def test_aggregate_logs_by_day_single_day(self):
        """Test aggregating logs from a single day."""
        logs = [
            {
                "date": "2024-01-15T10:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": 10.50,
                "funding_rate": 0.0001
            },
            {
                "date": "2024-01-15T14:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": 15.25,
                "funding_rate": 0.0002
            },
            {
                "date": "2024-01-15T18:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": -5.00,
                "funding_rate": -0.0001
            }
        ]
        
        result = aggregate_logs_by_day(logs)
        
        assert "2024-01-15" in result
        # Positive funding is inverted to negative (cost), negative funding becomes positive (income)
        assert result["2024-01-15"]["funding"] == -10.50 + (-15.25) + 5.00  # = -20.75
        assert "trades" in result["2024-01-15"]
    
    def test_aggregate_logs_by_day_multiple_days(self):
        """Test aggregating logs across multiple days."""
        logs = [
            {
                "date": "2024-01-15T10:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": 10.00,
                "funding_rate": 0.0001
            },
            {
                "date": "2024-01-16T10:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": 20.00,
                "funding_rate": 0.0002
            },
            {
                "date": "2024-01-17T10:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": -30.00,
                "funding_rate": -0.0003
            }
        ]
        
        result = aggregate_logs_by_day(logs)
        
        assert len(result) == 3
        assert result["2024-01-15"]["funding"] == -10.00  # Positive becomes negative (cost)
        assert result["2024-01-16"]["funding"] == -20.00  # Positive becomes negative (cost)
        assert result["2024-01-17"]["funding"] == 30.00   # Negative becomes positive (income)
    
    def test_aggregate_logs_by_day_missing_fields(self):
        """Test aggregating logs with missing fields."""
        logs = [
            {
                "date": "2024-01-15T10:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": 10.00,
                "funding_rate": 0.0001
            },
            {
                "date": "2024-01-15T14:30:00.000Z",
                "info": "funding rate change",
                # Missing realized_funding
                "funding_rate": 0.0002
            },
            {
                "date": "2024-01-15T18:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": 20.00,
                # Missing funding_rate
            },
            {
                # Missing date
                "info": "funding rate change",
                "realized_funding": 30.00,
                "funding_rate": 0.0003
            }
        ]
        
        result = aggregate_logs_by_day(logs)
        
        # Should only process logs with valid date and info type
        assert "2024-01-15" in result
        assert result["2024-01-15"]["funding"] == -10.00 + (-20.00)  # -30.00
        assert "trades" in result["2024-01-15"]
    
    def test_aggregate_logs_by_day_invalid_dates(self):
        """Test handling of invalid date formats."""
        logs = [
            {
                "date": "2024-01-15T10:30:00.000Z",
                "realized_funding": 10.00,
                "funding_rate": 0.0001
            },
            {
                "date": "invalid-date",
                "realized_funding": 20.00,
                "funding_rate": 0.0002
            },
            {
                "date": "2024-01-15",  # Missing time
                "realized_funding": 30.00,
                "funding_rate": 0.0003
            }
        ]
        
        result = aggregate_logs_by_day(logs)
        
        # Should process valid dates and handle invalid ones gracefully
        assert "2024-01-15" in result
        # The exact count depends on how the function handles invalid dates
    
    def test_aggregate_logs_by_day_numeric_strings(self):
        """Test handling of numeric values as strings."""
        logs = [
            {
                "date": "2024-01-15T10:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": "10.50",  # String
                "funding_rate": "0.0001"  # String
            },
            {
                "date": "2024-01-15T14:30:00.000Z",
                "info": "funding rate change",
                "realized_funding": 15.25,  # Number
                "funding_rate": 0.0002  # Number
            }
        ]
        
        result = aggregate_logs_by_day(logs)
        
        # Should handle both string and numeric values
        assert "2024-01-15" in result
        assert result["2024-01-15"]["funding"] == -10.50 + (-15.25)  # -25.75
        assert "trades" in result["2024-01-15"]


@pytest.mark.parametrize("days,expected_range", [
    (1, (0.5, 1.5)),
    (7, (6.5, 7.5)),
    (30, (29.5, 30.5)),
    (365, (364.5, 365.5)),
])
def test_get_period_boundaries_parametrized(days, expected_range):
    """Parametrized test for period boundaries."""
    since_ts, before_ts = get_period_boundaries(days)
    
    diff_ms = before_ts - since_ts
    diff_days = diff_ms / (1000 * 60 * 60 * 24)
    
    assert expected_range[0] < diff_days < expected_range[1]


@pytest.mark.parametrize("contract,expected", [
    ("PI_XBTUSD", "BTC"),  # XBT converted to BTC
    ("PF_ETHUSD", "ETH"),
    ("PF_ADAUSD", "ADA"),
    ("PI_DOGEUSD", "DOGE"),
    ("FI_XBTUSD_241227", "BTC"),  # XBT converted to BTC
    ("FF_SOLUSD_241227", "SOL"),
])
def test_extract_asset_parametrized(contract, expected):
    """Parametrized test for asset extraction."""
    assert extract_asset_from_contract(contract) == expected


@pytest.mark.unit
def test_calculate_unrealized_pnl():
    """Test unrealized P&L calculation for positions."""
    # Test long position with profit
    position = {'size': 10, 'price': 100}
    current_price = 110
    pnl = calculate_unrealized_pnl(position, current_price)
    assert pnl == 100.0  # (110 - 100) * 10 = 100
    
    # Test long position with loss
    position = {'size': 10, 'price': 100}
    current_price = 90
    pnl = calculate_unrealized_pnl(position, current_price)
    assert pnl == -100.0  # (90 - 100) * 10 = -100
    
    # Test short position with profit
    position = {'size': -10, 'price': 100}
    current_price = 90
    pnl = calculate_unrealized_pnl(position, current_price)
    assert pnl == 100.0  # (100 - 90) * 10 = 100
    
    # Test short position with loss
    position = {'size': -10, 'price': 100}
    current_price = 110
    pnl = calculate_unrealized_pnl(position, current_price)
    assert pnl == -100.0  # (100 - 110) * 10 = -100
    
    # Test edge cases
    assert calculate_unrealized_pnl({'size': 0, 'price': 100}, 110) == 0.0
    assert calculate_unrealized_pnl({'size': 10, 'price': 0}, 110) == 0.0
    assert calculate_unrealized_pnl({'size': 10, 'price': 100}, 0) == 0.0
    assert calculate_unrealized_pnl({}, 100) == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 