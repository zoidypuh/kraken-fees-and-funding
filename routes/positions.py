"""
Position-related API routes.
"""
from flask import Blueprint, jsonify, request, current_app
import logging
from typing import List, Dict
import hashlib

from kraken_client import (
    get_open_positions, batch_get_tickers, 
    KrakenAPIError, get_funding_rates, 
    ENTRY_TYPE_FUNDING_RATE_CHANGE,
    get_fee_info, find_true_position_open_time,
    get_account_logs
)
from unified_data_service import unified_data_service
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


def get_position_accumulated_data_cached(api_key: str, api_secret: str, position: dict) -> dict:
    """Calculate accumulated funding and fees using cached logs from unified service."""
    try:
        current_ts = int(time.time() * 1000)
        symbol = position.get("symbol", "").upper()
        position_size = abs(float(position.get("size", 0)))
        
        if not symbol or position_size == 0:
            return {
                "accumulated_funding": 0.0, 
                "accumulated_fees": 0.0, 
                "data_is_capped": False, 
                "error": "Missing symbol or size"
            }

        # Find true open time (this still needs direct API call)
        true_opened_ts = find_true_position_open_time(
            api_key, api_secret, symbol, position_size, current_ts
        )
        
        # Cap to 1 year if needed
        ONE_YEAR_AGO_TS = current_ts - (365 * 24 * 60 * 60 * 1000)
        fetch_from_ts = true_opened_ts
        data_is_capped = False
        
        if true_opened_ts < ONE_YEAR_AGO_TS:
            logger.warning(f"Position {symbol} is over a year old. Capping to 1 year.")
            fetch_from_ts = ONE_YEAR_AGO_TS
            data_is_capped = True

        # Get cached logs from unified service
        all_logs = unified_data_service.get_raw_logs(
            api_key, api_secret, fetch_from_ts, current_ts
        )
        
        accumulated_funding = 0.0
        accumulated_fees = 0.0
        
        # Process logs
        for log in all_logs:
            log_contract = log.get("contract", "")
            entry_type = log.get("info", "")
            
            if log_contract and symbol in log_contract.upper():
                if entry_type == ENTRY_TYPE_FUNDING_RATE_CHANGE:
                    realized_funding = log.get('realized_funding')
                    if realized_funding is not None:
                        accumulated_funding += float(realized_funding)
                        
                elif entry_type == "futures trade":
                    fee_value = log.get("fee")
                    if fee_value is not None:
                        accumulated_fees += abs(float(fee_value))
        
        logger.info(f"Position {symbol}: funding=${accumulated_funding:.2f}, fees=${accumulated_fees:.2f} (from cache)")
        
        return {
            "accumulated_funding": round(accumulated_funding, 2),
            "accumulated_fees": round(accumulated_fees, 2),
            "data_is_capped": data_is_capped,
            "true_opened_date_utc": datetime.fromtimestamp(true_opened_ts/1000, tz=timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error calculating accumulated data for {position.get('symbol')}: {str(e)}")
        return {
            "accumulated_funding": 0.0,
            "accumulated_fees": 0.0,
            "data_is_capped": False,
            "error": str(e)
        }


def get_hourly_funding(api_key: str, api_secret: str, position: dict) -> dict:
    """Get hourly funding payments for the last 8 hours."""
    try:
        current_ts = int(time.time() * 1000)
        eight_hours_ago = current_ts - (8 * 60 * 60 * 1000)
        symbol = position.get("symbol", "").upper()
        
        logger.debug(f"Fetching hourly funding for {symbol}")
        
        # Use cached logs from unified service
        funding_logs = unified_data_service.get_raw_logs(
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
    # Check if force refresh is requested
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
    
    # Simple caching logic
    cache_key = f"positions_{hashlib.md5(api_key.encode()).hexdigest()}"
    
    # Clear cache if force refresh
    if force_refresh:
        logger.info("Force refresh requested, clearing positions cache")
        if cache_key in _positions_cache:
            del _positions_cache[cache_key]
        if cache_key in _positions_cache_time:
            del _positions_cache_time[cache_key]
    
    # Check cache (skip if force refresh)
    if not force_refresh and cache_key in _positions_cache:
        cached_time = _positions_cache_time.get(cache_key, 0)
        if time.time() - cached_time < POSITIONS_CACHE_TTL:
            logger.info("Returning cached positions data")
            return jsonify(_positions_cache[cache_key])
    
    # Rate limit check - prevent too frequent requests (skip if force refresh)
    if not force_refresh:
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
        
        # Pre-fetch data to populate cache (30 days should cover most positions)
        # This single call will cache all logs for reuse
        unified_data_service.get_processed_data(api_key, api_secret, days=30)
        
        # Get accumulated data using cached logs
        position_data = []
        for pos in positions:
            acc_data = get_position_accumulated_data_cached(api_key, api_secret, pos)
            acc_data['symbol'] = pos['symbol']
            acc_data['size'] = pos['size']
            position_data.append(acc_data)
        
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


def analyze_closed_positions_simple(api_key: str, api_secret: str, days: int = 30) -> List[Dict]:
    """
    Simple approach: Create mock closed positions from recent trades.
    This is a placeholder implementation until proper position tracking is available.
    """
    try:
        # Get processed data which includes trades
        data = unified_data_service.get_processed_data(api_key, api_secret, days)
        trades = data.get('trades', [])
        
        if not trades:
            return []
        
        # Group trades by symbol
        trades_by_symbol = {}
        for trade in trades:
            symbol = trade.get('contract', '').upper()
            if symbol and trade.get('fee', 0) > 0:  # Only consider trades with fees
                if symbol not in trades_by_symbol:
                    trades_by_symbol[symbol] = []
                trades_by_symbol[symbol].append(trade)
        
        # Create mock closed positions from pairs of trades
        closed_positions = []
        
        for symbol, symbol_trades in trades_by_symbol.items():
            if len(symbol_trades) < 2:
                continue
            
            # Sort by date
            symbol_trades.sort(key=lambda x: x.get('timestamp', 0))
            
            # Create pairs of trades as closed positions
            for i in range(0, len(symbol_trades) - 1, 2):
                open_trade = symbol_trades[i]
                close_trade = symbol_trades[i + 1]
                
                # Parse dates
                open_date = open_trade.get('date', '')
                close_date = close_trade.get('date', '')
                
                if not open_date or not close_date:
                    continue
                
                # Calculate duration
                open_dt = datetime.fromisoformat(open_date.replace('Z', '+00:00'))
                close_dt = datetime.fromisoformat(close_date.replace('Z', '+00:00'))
                duration = close_dt - open_dt
                
                if duration.days == 0:
                    duration_str = f"{duration.seconds // 3600}h"
                else:
                    duration_str = f"{duration.days}d"
                
                # Get prices
                entry_price = float(open_trade.get('trade_price', 0))
                exit_price = float(close_trade.get('trade_price', 0))
                
                # Estimate size from fee
                # Use a default maker fee to avoid API calls
                maker_fee = 0.0002  # Default 0.02%
                size = float(open_trade.get('fee', 0)) / (entry_price * maker_fee) if entry_price else 1.0
                
                # Determine side and calculate P&L
                if exit_price > entry_price:
                    side = 'long'
                    realized_pnl = (exit_price - entry_price) * size
                else:
                    side = 'short'
                    realized_pnl = (entry_price - exit_price) * size
                
                # Sum fees
                total_fees = float(open_trade.get('fee', 0)) + float(close_trade.get('fee', 0))
                
                # Mock funding (could be improved with actual funding data)
                total_funding = realized_pnl * 0.1  # Assume 10% of P&L as funding
                
                # Net P&L
                net_pnl = realized_pnl + total_funding - total_fees
                
                closed_positions.append({
                    'symbol': symbol,
                    'openedDate': open_date,
                    'closedDate': close_date,
                    'duration': duration_str,
                    'side': side,
                    'size': round(size, 6),
                    'entryPrice': round(entry_price, 2),
                    'exitPrice': round(exit_price, 2),
                    'realizedPnl': round(realized_pnl, 2),
                    'totalFunding': round(total_funding, 2),
                    'totalFees': round(total_fees, 2),
                    'netPnl': round(net_pnl, 2)
                })
        
        # Sort by closed date, newest first
        closed_positions.sort(key=lambda x: x['closedDate'], reverse=True)
        
        return closed_positions[:20]  # Return at most 20 positions
        
    except Exception as e:
        logger.error(f"Error in simple closed positions analysis: {str(e)}")
        return []


def analyze_closed_positions(api_key: str, api_secret: str, days: int = 30) -> List[Dict]:
    """
    Analyze trade history to identify closed positions.
    
    Returns a list of closed positions with their metrics.
    """
    try:
        current_ts = int(time.time() * 1000)
        start_ts = current_ts - (days * 24 * 60 * 60 * 1000)
        
        # Get all logs for the period
        all_logs = unified_data_service.get_raw_logs(
            api_key, api_secret, start_ts, current_ts
        )
        
        # Get current open positions to exclude them
        open_positions = get_open_positions(api_key, api_secret)
        open_symbols = {pos['symbol'] for pos in open_positions}
        
        # Track position changes by symbol
        position_history = {}  # symbol -> list of position changes
        
        # Process logs chronologically
        all_logs.sort(key=lambda x: x.get('date', ''))
        
        # Get fee info once for estimations
        fee_info = get_fee_info(api_key, api_secret)
        maker_fee = fee_info.get('maker_fee', 0.0002)  # Default 0.02%
        
        # First pass: collect all trades
        for log in all_logs:
            if log.get('info') == 'futures trade' and log.get('fee') is not None:
                contract = log.get('contract', '').upper()
                if not contract:
                    continue
                
                # Skip if it's a currently open position
                if contract in open_symbols:
                    continue
                
                symbol = contract
                
                if symbol not in position_history:
                    position_history[symbol] = {
                        'trades': [],
                        'funding': 0.0,
                        'position_size': 0.0
                    }
                
                # Get trade details
                trade_price = float(log.get('trade_price', 0))
                fee = float(log.get('fee', 0))
                date_str = log.get('date')
                
                # Skip zero-fee entries (duplicates)
                if fee == 0:
                    continue
                
                # Estimate quantity from fee
                quantity = abs(fee) / (trade_price * maker_fee) if trade_price and fee else 0
                
                position_history[symbol]['trades'].append({
                    'date': date_str,
                    'trade_price': trade_price,
                    'quantity': quantity,
                    'fee': abs(fee)
                })
        
        # Second pass: collect funding for each symbol
        for log in all_logs:
            if log.get('info') == ENTRY_TYPE_FUNDING_RATE_CHANGE:
                contract = log.get('contract', '').upper()
                if contract in position_history:
                    funding = log.get('realized_funding')
                    if funding:
                        position_history[contract]['funding'] += float(funding)
        
        # Analyze position history to find closed positions
        closed_positions = []
        
        for symbol, data in position_history.items():
            trades = data['trades']
            if len(trades) < 2:  # Need at least 2 trades to have a closed position
                continue
            
            # Sort trades by date
            trades.sort(key=lambda x: x['date'])
            
            # Track position through trades
            position_stack = []
            current_position = 0.0
            weighted_entry_price = 0.0
            total_quantity = 0.0
            
            for i, trade in enumerate(trades):
                quantity = trade['quantity']
                price = trade['trade_price']
                
                # Check if this is likely an opening or closing trade
                if i == 0:
                    # First trade is always opening
                    current_position = quantity
                    weighted_entry_price = price
                    total_quantity = quantity
                    position_stack.append({
                        'open_trade': trade,
                        'size': quantity,
                        'entry_price': price
                    })
                else:
                    # Check if we have a full position close (approximation)
                    # If this trade quantity is similar to current position, it's likely a close
                    if current_position > 0 and abs(quantity - current_position) / current_position < 0.5:  # Within 50%
                        # This is likely a closing trade
                        if position_stack:
                            position_info = position_stack[-1]
                            
                            # Calculate metrics
                            opened_date = position_info['open_trade']['date']
                            closed_date = trade['date']
                            
                            # Calculate duration
                            opened_dt = datetime.fromisoformat(opened_date.replace('Z', '+00:00'))
                            closed_dt = datetime.fromisoformat(closed_date.replace('Z', '+00:00'))
                            duration_days = (closed_dt - opened_dt).days
                            
                            # Format duration
                            if duration_days == 0:
                                duration_str = "< 1d"
                            else:
                                duration_str = f"{duration_days}d"
                            
                            # Determine side based on first few trades
                            # If average price is increasing in first trades, likely buying (long)
                            # If average price is decreasing in first trades, likely selling (short)
                            side = 'long'  # Default assumption
                            
                            entry_price = position_info['entry_price']
                            exit_price = price
                            size = position_info['size']
                            
                            # Calculate realized P&L
                            if side == 'long':
                                realized_pnl = (exit_price - entry_price) * size
                            else:
                                realized_pnl = (entry_price - exit_price) * size
                            
                            # Calculate total fees (all trades for this position)
                            total_fees = sum(t['fee'] for t in trades[:i+1])
                            
                            # Get funding for the period (proportional)
                            total_funding = data['funding'] * ((i + 1) / len(trades))
                            
                            # Calculate net P&L
                            net_pnl = realized_pnl + total_funding - total_fees
                            
                            closed_positions.append({
                                'symbol': symbol,
                                'openedDate': opened_date,
                                'closedDate': closed_date,
                                'duration': duration_str,
                                'side': side,
                                'size': round(size, 6),
                                'entryPrice': round(entry_price, 2),
                                'exitPrice': round(exit_price, 2),
                                'realizedPnl': round(realized_pnl, 2),
                                'totalFunding': round(total_funding, 2),
                                'totalFees': round(total_fees, 2),
                                'netPnl': round(net_pnl, 2)
                            })
                            
                            # Reset position tracking
                            position_stack = []
                            current_position = 0.0
                    else:
                        # This is adding to position
                        current_position += quantity
                        # Update weighted average entry price
                        total_quantity += quantity
                        weighted_entry_price = ((weighted_entry_price * (total_quantity - quantity)) + 
                                               (price * quantity)) / total_quantity
        
        # Sort by closed date, newest first
        closed_positions.sort(key=lambda x: x['closedDate'], reverse=True)
        
        return closed_positions
        
    except Exception as e:
        logger.error(f"Error analyzing closed positions: {str(e)}")
        return []


@positions.route('/closed')
@require_api_credentials
def get_closed_positions(api_key: str, api_secret: str):
    """Get closed positions from trade history."""
    try:
        # Get days parameter (default 30)
        days = int(request.args.get('days', 30))
        
        # Analyze closed positions
        closed_positions = analyze_closed_positions(api_key, api_secret, days)
        
        # If no closed positions found with complex algorithm, try simple approach
        if not closed_positions:
            closed_positions = analyze_closed_positions_simple(api_key, api_secret, days)
        
        return jsonify(closed_positions)
        
    except Exception as e:
        logger.error(f"Error fetching closed positions: {e}")
        return jsonify({'error': 'Failed to fetch closed positions'}), 500


 