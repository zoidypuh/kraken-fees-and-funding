"""
Position-related API routes.
"""
from flask import Blueprint, jsonify, request
import logging
from typing import List, Dict

from kraken_client import (
    get_open_positions, batch_get_tickers, 
    batch_get_position_accumulated_data, KrakenAPIError
)
from .auth import require_api_credentials

# Async support removed - Flask doesn't support async views without additional setup

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
                        accumulated_data: dict) -> dict:
    """Format position data with all calculated fields."""
    unrealized_pnl = calculate_unrealized_pnl(kraken_pos, current_price)
    accumulated_funding = accumulated_data.get('accumulated_funding', 0.0)
    accumulated_fees = accumulated_data.get('accumulated_fees', 0.0)
    
    # Calculate net P&L based on user requirement:
    # - Negative accumulated_funding is a cost (subtract its absolute value)
    # - Positive accumulated_funding is income (add it)
    if accumulated_funding < 0:
        # Negative funding is a cost
        net_pnl = round(unrealized_pnl - abs(accumulated_funding) - accumulated_fees, 2)
    else:
        # Positive funding is income
        net_pnl = round(unrealized_pnl + accumulated_funding - accumulated_fees, 2)
    
    size = kraken_pos['size']
    side = 'long' if size > 0 else 'short'
    
    return {
        'symbol': kraken_pos['symbol'],
        'size': size,
        'avgPrice': kraken_pos['price'],
        'currentPrice': current_price,
        'unrealizedPnl': round(unrealized_pnl, 2),
        'accumulatedFunding': round(accumulated_funding, 2),
        'accumulatedFees': round(accumulated_fees, 2),
        'netUnrealizedPnl': net_pnl,
        'openedDate': accumulated_data.get('true_opened_date_utc'),
        'dataIsCapped': accumulated_data.get('data_is_capped', False),
        'error': accumulated_data.get('error'),
        'side': side
    }


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


@positions.route('/detailed')
@require_api_credentials
def get_positions_detailed(api_key: str, api_secret: str):
    """Get positions with current prices and P&L calculations."""
    try:
        positions = get_open_positions(api_key, api_secret)
        
        if not positions:
            return jsonify([])
        
        # Get current prices for all symbols
        symbols = [pos['symbol'] for pos in positions]
        tickers = batch_get_tickers(api_key, api_secret, symbols)
        
        # Get accumulated data (funding & fees) - using optimized version
        position_data = batch_get_position_accumulated_data(api_key, api_secret, positions)
        
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
            
            # Format position data with calculations
            position_data = format_position_data(pos, current_price, acc_data)
            result.append(position_data)
        
        return jsonify(result)
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching detailed positions: {e}")
        return jsonify({'error': 'Failed to fetch position details'}), 500


@positions.route('/<symbol>/history')
@require_api_credentials
def get_position_history(api_key: str, api_secret: str, symbol: str):
    """Get historical data for a specific position."""
    try:
        # This would fetch position-specific historical data
        # For now, return a placeholder
        return jsonify({
            'symbol': symbol,
            'message': 'Position history endpoint - to be implemented'
        })
        
    except Exception as e:
        logger.error(f"Error fetching position history: {e}")
        return jsonify({'error': 'Failed to fetch position history'}), 500


# Async endpoint removed - Flask doesn't support async views without additional setup 