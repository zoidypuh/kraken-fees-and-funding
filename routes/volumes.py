"""
Trading volumes API route.
"""
from flask import Blueprint, jsonify, request
import logging

from kraken_client import KrakenAPIError
from .auth import require_api_credentials
from unified_data_service import unified_data_service

logger = logging.getLogger(__name__)

volumes = Blueprint('volumes', __name__, url_prefix='/api/volumes')

@volumes.route('')
@require_api_credentials
def get_trading_volumes(api_key: str, api_secret: str):
    """Get daily trading volumes for specified number of days."""
    try:
        days_str = request.args.get('days', '30')
        try:
            days = int(days_str)
        except ValueError:
            return jsonify({'error': 'Days must be a valid integer'}), 400
        
        if days < 1 or days > 90:
            return jsonify({'error': 'Days must be between 1 and 90'}), 400
        
        # Check if force refresh is requested
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        
        if force_refresh:
            unified_data_service.clear_cache(api_key)
        
        logger.info(f"Fetching trading volumes for last {days} days")
        
        # Get data from unified service
        data = unified_data_service.get_processed_data(api_key, api_secret, days)
        
        # Format volume data
        result = []
        for day_data in data['daily_data']:
            result.append({
                'date': day_data['date'],
                'volume': day_data['volume']
            })
        
        logger.info(f"Returning {len(result)} days of volume data")
        
        return jsonify({
            'data': result,
            'period': f'{days} days',
            'total_volume': data['summary']['total_volume']
        })
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching trading volumes: {e}")
        return jsonify({'error': 'Failed to fetch trading volumes'}), 500 