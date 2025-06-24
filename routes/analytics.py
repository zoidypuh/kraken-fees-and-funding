"""
Analytics and chart data API routes.
"""
from flask import Blueprint, jsonify, request
import logging
from datetime import datetime, timezone, timedelta
import time
import hashlib

from kraken_client import KrakenAPIError
from .auth import require_api_credentials
from unified_data_service import unified_data_service

logger = logging.getLogger(__name__)

analytics = Blueprint('analytics', __name__, url_prefix='/api/analytics')





@analytics.route('/chart-data')
@require_api_credentials
def get_chart_data(api_key: str, api_secret: str):
    """Get aggregated chart data for fees and funding."""
    try:
        days_str = request.args.get('days', '7')
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
        
        # Get data from unified service
        data = unified_data_service.get_processed_data(api_key, api_secret, days)
        
        # Format response for chart
        labels = []
        fees = []
        funding = []
        
        for day_data in data['daily_data']:
            labels.append(day_data['date'])
            fees.append(day_data['fees'])
            funding.append(day_data['funding'])
        
        return jsonify({
            'labels': labels,
            'fees': fees,
            'funding': funding,
            'trades': {},  # No longer tracking individual trades
            'total_fees': data['summary']['total_fees'],
            'total_funding': data['summary']['total_funding'],
            'total_cost': data['summary']['total_cost']
        })
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching chart data: {e}")
        return jsonify({'error': 'Failed to fetch chart data'}), 500





@analytics.route('/fees')
@require_api_credentials
def get_fees_data(api_key: str, api_secret: str):
    """Get trading fees data only."""
    try:
        days_str = request.args.get('days', '7')
        try:
            days = int(days_str)
        except ValueError:
            return jsonify({'error': 'Days must be a valid integer'}), 400
        
        if days < 1 or days > 90:
            return jsonify({'error': 'Days must be between 1 and 90'}), 400
        
        # Get data from unified service
        data = unified_data_service.get_processed_data(api_key, api_secret, days)
        
        # Format response for fees
        labels = []
        fees = []
        
        for day_data in data['daily_data']:
            labels.append(day_data['date'])
            fees.append(day_data['fees'])
        
        return jsonify({
            'labels': labels,
            'fees': fees,
            'total': data['summary']['total_fees']
        })
        
    except Exception as e:
        logger.error(f"Error fetching fees: {e}")
        return jsonify({'error': 'Failed to fetch fees data'}), 500


@analytics.route('/funding')
@require_api_credentials
def get_funding_data(api_key: str, api_secret: str):
    """Get funding costs data only."""
    try:
        days_str = request.args.get('days', '7')
        try:
            days = int(days_str)
        except ValueError:
            return jsonify({'error': 'Days must be a valid integer'}), 400
        
        if days < 1 or days > 90:
            return jsonify({'error': 'Days must be between 1 and 90'}), 400
        
        # Get data from unified service
        data = unified_data_service.get_processed_data(api_key, api_secret, days)
        
        # Format response for funding
        labels = []
        funding = []
        
        for day_data in data['daily_data']:
            labels.append(day_data['date'])
            funding.append(day_data['funding'])
        
        return jsonify({
            'labels': labels,
            'funding': funding,
            'total': data['summary']['total_funding']
        })
        
    except Exception as e:
        logger.error(f"Error fetching funding: {e}")
        return jsonify({'error': 'Failed to fetch funding data'}), 500


@analytics.route('/summary')
@require_api_credentials
def get_summary(api_key: str, api_secret: str):
    """Get summary statistics for a time period."""
    try:
        days_str = request.args.get('days', '7')
        try:
            days = int(days_str)
        except ValueError:
            return jsonify({'error': 'Days must be a valid integer'}), 400
        
        if days < 1 or days > 90:
            return jsonify({'error': 'Days must be between 1 and 90'}), 400
        
        # Get data from unified service
        data = unified_data_service.get_processed_data(api_key, api_secret, days)
        
        # Format summary data
        summary = data['summary']
        return jsonify({
            'period': f'{days} days',
            'totalFees': summary['total_fees'],
            'totalFunding': summary['total_funding'],
            'totalCost': summary['total_cost'],
            'tradeCount': summary['total_trades'],
            'avgDailyFees': summary['avg_daily_fees'],
            'avgDailyFunding': summary['avg_daily_funding']
        })
        
    except Exception as e:
        logger.error(f"Error fetching summary: {e}")
        return jsonify({'error': 'Failed to fetch summary'}), 500


@analytics.route('/preload')
@require_api_credentials
def preload_data(api_key: str, api_secret: str):
    """Preload account data for 30 days to populate cache."""
    try:
        logger.info("Preloading account data for 30 days")
        
        # Load 30 days of data into cache
        data = unified_data_service.get_processed_data(api_key, api_secret, 30)
        
        return jsonify({
            'status': 'success',
            'message': 'Data preloaded successfully',
            'period_days': data['period_days'],
            'last_updated': data['last_updated'],
            'summary': data['summary']
        })
        
    except Exception as e:
        logger.error(f"Error preloading data: {e}")
        return jsonify({'error': 'Failed to preload data'}), 500


 