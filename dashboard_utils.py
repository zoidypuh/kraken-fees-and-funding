"""
Utilities for the Kraken funding dashboard.
Contains only the functions needed for the web application.
"""
from datetime import datetime, timedelta, timezone
import pytz
from typing import List, Dict, Tuple
from functools import lru_cache
import math


def get_utc() -> pytz.timezone:
    """Get UTC timezone object."""
    return pytz.UTC


def get_period_boundaries(days_back: int, timezone_obj: pytz.timezone = None) -> Tuple[int, int]:
    """
    Get start and end timestamps for a period going back N days in UTC.
    Days are calculated as complete 24-hour periods from 00:00 to 00:00 UTC.
    
    Args:
        days_back: Number of days to go back
        timezone_obj: Timezone object (defaults to UTC)
    
    Returns:
        Tuple of (start_timestamp_ms, end_timestamp_ms)
    """
    if timezone_obj is None:
        timezone_obj = get_utc()
    
    # Get current time in UTC
    now_utc = datetime.now(timezone_obj)
    
    # Calculate the start date (days_back days ago at 00:00 UTC)
    start_date = now_utc.date() - timedelta(days=days_back - 1)  # -1 because we include today
    start_of_period = timezone_obj.localize(
        datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    )
    
    # End is start of next day (exclusive)
    end_of_period = timezone_obj.localize(
        datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0)
    ) + timedelta(days=1)
    
    # Convert to UTC timestamps in milliseconds
    since_ts = int(start_of_period.timestamp() * 1000)
    before_ts = int(end_of_period.timestamp() * 1000)
    
    return since_ts, before_ts


def extract_asset_from_contract(contract: str) -> str:
    """
    Extract asset name from contract string.
    Examples: 
    - "PF_BTCUSD" -> "BTC"
    - "pf_xbtusd" -> "BTC"
    - "FI_ETHUSD_241225" -> "ETH"
    """
    if not contract:
        return "Unknown"
    
    # Convert to uppercase for consistent processing
    contract_upper = contract.upper()
    
    # Remove prefixes
    contract_upper = contract_upper.replace("PF_", "").replace("FI_", "")
    
    # Special cases for common assets
    if "XBTUSD" in contract_upper or "BTCUSD" in contract_upper:
        return "BTC"
    elif "ETHUSD" in contract_upper:
        return "ETH"
    elif "SOLUSD" in contract_upper:
        return "SOL"
    elif "XRPUSD" in contract_upper:
        return "XRP"
    elif "DOGEUSD" in contract_upper:
        return "DOGE"
    elif "ADAUSD" in contract_upper:
        return "ADA"
    elif "AVAXUSD" in contract_upper:
        return "AVAX"
    elif "MATICUSD" in contract_upper:
        return "MATIC"
    elif "DOTUSD" in contract_upper:
        return "DOT"
    elif "LINKUSD" in contract_upper:
        return "LINK"
    
    # Generic extraction (everything before USD)
    if "USD" in contract_upper:
        asset = contract_upper.split("USD")[0]
        # Remove any remaining special characters
        asset = asset.replace("_", "").replace("-", "")
        return asset if asset else "Unknown"
    
    return "Unknown"


def aggregate_logs_by_day(logs: List[Dict], timezone_obj: pytz.timezone = None) -> Dict[str, Dict]:
    """
    Aggregate log entries by day for the dashboard.
    
    Args:
        logs: List of log entries
        timezone_obj: Timezone for day boundaries (defaults to UTC)
    
    Returns:
        Dict mapping date strings to aggregated data including trade details
    """
    if timezone_obj is None:
        timezone_obj = get_utc()
    
    daily_data = {}
    
    for entry in logs:
        # Parse entry timestamp
        date_str = entry.get("date", "")
        try:
            entry_time = parse_iso_date(date_str)
            # Convert to specified timezone (UTC by default)
            entry_time_local = entry_time.astimezone(timezone_obj)
            # Get the date
            day_key = entry_time_local.date().isoformat()
        except:
            continue
        
        if day_key not in daily_data:
            daily_data[day_key] = {
                'fees': 0.0,
                'funding': 0.0,
                'trades': {},  # Use dict for aggregation
                'trades_list': []  # Final list of aggregated trades
            }
        
        # Process based on entry type
        if entry.get("info") == "futures trade":
            fee = abs(float(entry.get("fee") or 0))
            daily_data[day_key]['fees'] += fee
            
            # Extract trade details
            asset = extract_asset_from_contract(entry.get("contract", ""))
            price = abs(float(entry.get("trade_price") or entry.get("mark_price") or 0))
            quantity = abs(float(entry.get("quantity") or entry.get("size") or 0))
            
            # Create aggregation key
            agg_key = f"{asset}_{price}"
            
            if agg_key not in daily_data[day_key]['trades']:
                daily_data[day_key]['trades'][agg_key] = {
                    'asset': asset,
                    'price': price,
                    'quantity': 0,
                    'fee': 0,
                    'count': 0,
                    'first_time': entry_time_local.strftime("%H:%M:%S")
                }
            
            # Aggregate
            daily_data[day_key]['trades'][agg_key]['quantity'] += quantity
            daily_data[day_key]['trades'][agg_key]['fee'] += fee
            daily_data[day_key]['trades'][agg_key]['count'] += 1
            
        elif entry.get("info") == "funding rate change":
            funding_val = float(entry.get("realized_funding") or 0)
            # Invert the sign: positive funding is a cost, negative is income
            funding = -funding_val if funding_val > 0 else abs(funding_val)
            daily_data[day_key]['funding'] += funding
    
    # Convert aggregated trades to list and sort
    for day_key in daily_data:
        trades_dict = daily_data[day_key]['trades']
        trades_list = list(trades_dict.values())
        # Sort by asset name first, then by price (descending)
        trades_list.sort(key=lambda x: (x['asset'], -x['price']))
        daily_data[day_key]['trades'] = trades_list
        # Remove temporary dict
        del daily_data[day_key]['trades_list']
    
    return daily_data


def calculate_unrealized_pnl(position: Dict, current_price: float) -> float:
    """
    Calculate unrealized P&L for a position.
    
    Args:
        position: Position dict with 'size', 'price' (average entry price), and 'side'
        current_price: Current market price
        
    Returns:
        Unrealized P&L in USD
    """
    if not current_price or current_price <= 0:
        return 0.0
    
    size = float(position.get('size', 0))
    if size == 0:
        return 0.0
    
    # For Kraken futures, size is already directional:
    # Positive size = long position, negative size = short position
    avg_price = float(position.get('price', 0))
    
    if avg_price <= 0:
        return 0.0
    
    # Calculate P&L based on position direction
    if size > 0:  # Long position
        # P&L = (current price - average price) * size
        pnl = (current_price - avg_price) * abs(size)
    else:  # Short position
        # P&L = (average price - current price) * size
        pnl = (avg_price - current_price) * abs(size)
    
    return round(pnl, 2)


# LRU cache for frequent date parsing operations
@lru_cache(maxsize=2000)
def parse_iso_date(date_str: str) -> datetime:
    """
    Parse ISO date string with caching for performance.
    """
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc) 