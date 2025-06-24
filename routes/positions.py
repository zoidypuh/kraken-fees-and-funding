"""
Position-related API routes.
"""
from flask import Blueprint, jsonify, request, current_app
import logging
from typing import List, Dict
import hashlib

from kraken_client import (
    get_open_positions, batch_get_tickers, 
    batch_get_position_accumulated_data, KrakenAPIError,
    get_funding_rates, get_account_logs, ENTRY_TYPE_FUNDING_RATE_CHANGE,
    get_fee_info
)
from .auth import require_api_credentials
import time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

positions = Blueprint('positions', __name__, url_prefix='/api/positions')


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


def format_position_data(kraken_pos: dict, current_price: float, 
                        accumulated_data: dict, maker_fee: float = 0.0) -> dict:
    """Format position data with all calculated fields."""
    unrealized_pnl = calculate_unrealized_pnl(kraken_pos, current_price)
    accumulated_funding = accumulated_data.get('accumulated_funding', 0.0)
    accumulated_fees = accumulated_data.get('accumulated_fees', 0.0)
    
    # Calculate estimated closing fees
    # Formula: position quantity × mark price × maker fee
    size = kraken_pos['size']
    closing_fees = abs(size) * current_price * maker_fee
    closing_fees = round(closing_fees, 2)
    
    # Calculate net P&L based on user requirement:
    # - Negative accumulated_funding is a cost (subtract its absolute value)
    # - Positive accumulated_funding is income (add it)
    # - Include estimated closing fees in the calculation
    if accumulated_funding < 0:
        # Negative funding is a cost
        net_pnl = round(unrealized_pnl - abs(accumulated_funding) - accumulated_fees - closing_fees, 2)
    else:
        # Positive funding is income
        net_pnl = round(unrealized_pnl + accumulated_funding - accumulated_fees - closing_fees, 2)
    
    side = 'long' if size > 0 else 'short'
    
    return {
        'symbol': kraken_pos['symbol'],
        'size': size,
        'avgPrice': kraken_pos['price'],
        'currentPrice': current_price,
        'unrealizedPnl': round(unrealized_pnl, 2),
        'accumulatedFunding': round(accumulated_funding, 2),
        'accumulatedFees': round(accumulated_fees, 2),
        'closingFees': closing_fees,
        'netUnrealizedPnl': net_pnl,
        'openedDate': accumulated_data.get('true_opened_date_utc'),
        'dataIsCapped': accumulated_data.get('data_is_capped', False),
        'error': accumulated_data.get('error'),
        'side': side
    }


def get_hourly_funding(api_key: str, api_secret: str, position: dict) -> dict:
    """Get hourly funding payments for the last 8 hours."""
    try:
        current_ts = int(time.time() * 1000)
        eight_hours_ago = current_ts - (8 * 60 * 60 * 1000)
        symbol = position.get("symbol", "").upper()
        
        logger.debug(f"Fetching hourly funding for {symbol}")
        
        # Fetch funding logs for the last 8 hours
        funding_logs = get_account_logs(
            api_key, api_secret, eight_hours_ago, current_ts,
            entry_type=ENTRY_TYPE_FUNDING_RATE_CHANGE
        )
        
        logger.debug(f"Found {len(funding_logs)} funding logs for analysis")
        
        # Initialize hourly buckets
        hourly_funding = {}
        now = datetime.now(timezone.utc)
        
        # Create hour labels for the last 8 hours
        for i in range(8):
            hour_time = now - timedelta(hours=i)
            hour_label = hour_time.strftime("%H:00")
            hourly_funding[hour_label] = 0.0
        
        # Process funding logs
        matching_count = 0
        for log in funding_logs:
            log_contract = log.get("contract", "").upper()
            # Check if the contract matches the symbol
            if symbol.replace("_", "") in log_contract.replace("_", "").upper():
                matching_count += 1
                # Get the timestamp of the log
                log_date = log.get("date")
                if log_date:
                    log_time = datetime.strptime(log_date, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    hour_label = log_time.strftime("%H:00")
                    
                    # Add funding to the appropriate hour bucket
                    realized_funding = log.get('realized_funding')
                    if realized_funding is not None and hour_label in hourly_funding:
                        hourly_funding[hour_label] += float(realized_funding)
                        logger.debug(f"Added funding {realized_funding} to hour {hour_label}")
        
        logger.debug(f"Matched {matching_count} funding logs for {symbol}")
        
        # Return ordered list of funding values (oldest to newest)
        result = []
        for i in range(7, -1, -1):  # From 7 hours ago to current hour
            hour_time = now - timedelta(hours=i)
            hour_label = hour_time.strftime("%H:00")
            result.append(round(hourly_funding.get(hour_label, 0), 2))
        
        return {"hourly_funding": result}
        
    except Exception as e:
        logger.error(f"Error getting hourly funding for {position.get('symbol')}: {str(e)}")
        return {"hourly_funding": [0] * 8}


@positions.route('/')
@require_api_credentials
def get_positions(api_key: str, api_secret: str):
    """Get all open positions."""
    try:
        positions = get_open_positions(api_key, api_secret)
        
        if not positions:
            return jsonify([])
        
        # Get unique symbols
        symbols = list(set(pos['symbol'] for pos in positions))
        
        # Return basic position data
        result = []
        for pos in positions:
            result.append({
                'symbol': pos['symbol'],
                'size': pos['size'],
                'avgPrice': pos['price'],
                'side': pos.get('side', 'long' if pos['size'] > 0 else 'short')
            })
        
        return jsonify(result)
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return jsonify({'error': 'Failed to fetch positions'}), 500


# Simple in-memory cache for positions
_positions_cache = {}
_positions_cache_time = {}
POSITIONS_CACHE_TTL = 30  # 30 seconds

@positions.route('/detailed')
@require_api_credentials
def get_positions_detailed(api_key: str, api_secret: str):
    """Get positions with current prices and P&L calculations."""
    # Simple caching logic
    cache_key = f"positions_{hashlib.md5(api_key.encode()).hexdigest()}"
    
    # Check cache
    if cache_key in _positions_cache:
        cached_time = _positions_cache_time.get(cache_key, 0)
        if time.time() - cached_time < POSITIONS_CACHE_TTL:
            logger.info("Returning cached positions data")
            return jsonify(_positions_cache[cache_key])
    
    # Rate limit check - prevent too frequent requests
    last_request_time = _positions_cache_time.get(cache_key, 0)
    if time.time() - last_request_time < 5:  # Minimum 5 seconds between requests
        logger.warning("Request too frequent, returning cached or empty data")
        if cache_key in _positions_cache:
            return jsonify(_positions_cache[cache_key])
        else:
            return jsonify([])
    
    # Update last request time
    _positions_cache_time[cache_key] = time.time()
    
    try:
        positions = get_open_positions(api_key, api_secret)
        
        if not positions:
            return jsonify([])
        
        # Get current prices for all symbols
        symbols = [pos['symbol'] for pos in positions]
        tickers = batch_get_tickers(api_key, api_secret, symbols)
        
        # Get accumulated data (funding & fees) - using optimized version
        position_data = batch_get_position_accumulated_data(api_key, api_secret, positions)
        
        # Get fee info to get the maker fee rate
        fee_info = get_fee_info(api_key, api_secret)
        maker_fee = fee_info.get('maker_fee', 0.0)
        logger.info(f"Using maker fee rate: {maker_fee * 100:.4f}%")
        
        # Convert list to dict keyed by symbol for easier lookup
        position_data_map = {item['symbol']: item for item in position_data}
        
        # Build detailed response
        result = []
        for pos in positions:
            symbol = pos['symbol']
            ticker = tickers.get(symbol, {})
            # Extract mark price from ticker data
            current_price = float(ticker.get('markPrice', pos['price'])) if ticker else pos['price']
            acc_data = position_data_map.get(symbol, {})
            
            # Format position data with calculations (including maker fee)
            position_data = format_position_data(pos, current_price, acc_data, maker_fee)
            
            # Add funding rates
            funding_rates = get_funding_rates(api_key, api_secret, symbol)
            position_data['fundingRateCurrent'] = funding_rates['current']
            position_data['fundingRatePredicted'] = funding_rates['predicted']
            
            # Add hourly funding history
            hourly_data = get_hourly_funding(api_key, api_secret, pos)
            position_data['hourlyFunding'] = hourly_data['hourly_funding']
            
            result.append(position_data)
        
        # Cache successful result
        _positions_cache[cache_key] = result
        _positions_cache_time[cache_key] = time.time()
        logger.info(f"Cached {len(result)} positions for {POSITIONS_CACHE_TTL} seconds")
        
        return jsonify(result)
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        # Check if it's a rate limit error
        if "429" in str(e) or "Rate Limit" in str(e):
            # Don't cache rate limit errors
            return jsonify({'error': 'Rate limit exceeded. Please wait a moment.'}), 429
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching detailed positions: {e}")
        return jsonify({'error': 'Failed to fetch position details'}), 500


 