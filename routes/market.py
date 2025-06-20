"""
Market data API routes.
"""
from flask import Blueprint, jsonify, request
import logging
from typing import List, Dict

from kraken_client import get_ticker, batch_get_tickers, get_fee_info, KrakenAPIError
from .auth import require_api_credentials

# Import async functions from unified client
from kraken_client import is_async_available
ASYNC_AVAILABLE = is_async_available()

logger = logging.getLogger(__name__)

market = Blueprint('market', __name__, url_prefix='/api/market')


@market.route('/ticker/<symbol>')
@require_api_credentials
def get_ticker_data(api_key: str, api_secret: str, symbol: str):
    """Get current ticker data for a symbol."""
    try:
        ticker = get_ticker(api_key, api_secret, symbol)
        
        if not ticker:
            return jsonify({'error': f'No data for symbol {symbol}'}), 404
        
        return jsonify({
            'symbol': ticker.get('symbol', symbol),
            'markPrice': ticker.get('markPrice'),
            'bid': ticker.get('bid'),
            'ask': ticker.get('ask'),
            'last': ticker.get('last'),
            'volume24h': ticker.get('volume24h'),
            'timestamp': ticker.get('timestamp')
        })
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching ticker: {e}")
        return jsonify({'error': 'Failed to fetch ticker data'}), 500


@market.route('/tickers', methods=['POST'])
@require_api_credentials
def get_multiple_tickers(api_key: str, api_secret: str):
    """Get ticker data for multiple symbols."""
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        
        if not symbols:
            return jsonify({'error': 'No symbols provided'}), 400
        
        # Limit to prevent abuse
        if len(symbols) > 50:
            return jsonify({'error': 'Too many symbols (max 50)'}), 400
        
        tickers = batch_get_tickers(api_key, api_secret, symbols)
        
        # Format response
        result = {}
        for symbol, price in tickers.items():
            result[symbol] = {
                'symbol': symbol,
                'markPrice': price
            }
        
        return jsonify(result)
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching tickers: {e}")
        return jsonify({'error': 'Failed to fetch ticker data'}), 500


@market.route('/price/<symbol>')
@require_api_credentials
def get_mark_price(api_key: str, api_secret: str, symbol: str):
    """Get just the mark price for a symbol (lightweight endpoint)."""
    try:
        ticker = get_ticker(api_key, api_secret, symbol)
        
        if not ticker or 'markPrice' not in ticker:
            return jsonify({'error': f'No price data for {symbol}'}), 404
        
        return jsonify({
            'symbol': symbol,
            'price': float(ticker['markPrice'])
        })
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching price: {e}")
        return jsonify({'error': 'Failed to fetch price'}), 500


@market.route('/fees')
@require_api_credentials
def get_fee_information(api_key: str, api_secret: str):
    """Get current fee information including 30-day volume and fee rates."""
    try:
        fee_info = get_fee_info(api_key, api_secret)
        
        # Format the response
        return jsonify({
            'volume_30d': fee_info.get('volume_30d', 0),
            'volume_30d_formatted': f"${fee_info.get('volume_30d', 0):,.2f}",
            'maker_fee': fee_info.get('maker_fee', 0),
            'maker_fee_percentage': f"{fee_info.get('maker_fee', 0) * 100:.4f}%",
            'taker_fee': fee_info.get('taker_fee', 0),
            'taker_fee_percentage': f"{fee_info.get('taker_fee', 0) * 100:.4f}%"
        })
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error fetching fee info: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching fee info: {e}")
        return jsonify({'error': 'Failed to fetch fee information'}), 500 