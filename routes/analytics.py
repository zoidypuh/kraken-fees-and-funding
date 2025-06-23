"""
Analytics and chart data API routes.
"""
from flask import Blueprint, jsonify, request
import logging
from datetime import datetime, timezone, timedelta
import time
import hashlib

from kraken_client import (
    get_account_logs, KrakenAPIError, 
    ENTRY_TYPE_FUNDING_RATE_CHANGE, ENTRY_TYPE_FUTURES_TRADE
)
from .auth import require_api_credentials
from functools import lru_cache

logger = logging.getLogger(__name__)

analytics = Blueprint('analytics', __name__, url_prefix='/api/analytics')

# Simple in-memory cache for chart data
chart_data_cache = {}
CACHE_TTL = 300  # 5 minutes cache


def format_summary_data(period_days: int, total_fees: float, total_funding: float,
                       total_cost: float, trade_count: int, avg_daily_fees: float,
                       avg_daily_funding: float) -> dict:
    """Format analytics summary data."""
    return {
        'period': f'{period_days} days',
        'totalFees': round(total_fees, 2),
        'totalFunding': round(total_funding, 2),
        'totalCost': round(total_cost, 2),
        'tradeCount': trade_count,
        'avgDailyFees': round(avg_daily_fees, 2),
        'avgDailyFunding': round(avg_daily_funding, 2)
    }


@lru_cache(maxsize=2000)
def parse_iso_date(date_str: str) -> datetime:
    """Parse ISO date string with caching for performance."""
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


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
        
        # Create cache key based on API key
        cache_key = hashlib.md5(f"{api_key}:90days".encode()).hexdigest()
        
        # Check if force refresh is requested
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        
        # Check cache (unless force refresh)
        if not force_refresh and cache_key in chart_data_cache:
            cached_data, cached_time = chart_data_cache[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                logger.info(f"Using cached data for {days} days")
                # Filter cached data to requested days
                return jsonify(filter_data_to_days(cached_data, days))
        
        # On refresh, always fetch 90 days of data
        logger.info("Fetching fresh data from Kraken API")
        current_ts = int(time.time() * 1000)
        ninety_days_ago = current_ts - (90 * 24 * 60 * 60 * 1000)
        
        # Fetch account logs with funding and fee entries
        try:
            logs = get_account_logs(
                api_key, api_secret, 
                ninety_days_ago, current_ts,
                entry_type=[ENTRY_TYPE_FUNDING_RATE_CHANGE, ENTRY_TYPE_FUTURES_TRADE]
            )
            logger.info(f"Fetched {len(logs)} account logs")
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise KrakenAPIError(f"Error fetching data: {str(e)}")
        
        # Process logs by UTC day
        daily_data = {}
        
        for log in logs:
            date_str = log.get('date', '')
            if not date_str:
                continue
                
            try:
                # Parse date and get UTC day
                log_time = parse_iso_date(date_str)
                day_key = log_time.date().isoformat()
                
                if day_key not in daily_data:
                    daily_data[day_key] = {
                        'fees': 0.0,
                        'funding': 0.0
                    }
                
                # Process based on entry type
                entry_type = log.get('info', '')
                
                if entry_type == ENTRY_TYPE_FUNDING_RATE_CHANGE:
                    # Funding rate change
                    realized_funding = log.get('realized_funding')
                    if realized_funding is not None:
                        # Store the absolute value of funding
                        daily_data[day_key]['funding'] += abs(float(realized_funding))
                        
                elif entry_type == ENTRY_TYPE_FUTURES_TRADE:
                    # Trade with fee
                    fee = log.get('fee')
                    if fee is not None:
                        daily_data[day_key]['fees'] += abs(float(fee))
                        
            except Exception as e:
                logger.warning(f"Error processing log entry: {e}")
                continue
        
        # Generate all dates for 90 days
        current_date = datetime.now(timezone.utc).date()
        all_data = []
        
        for i in range(90):
            date = (current_date - timedelta(days=89-i))
            date_str = date.isoformat()
            
            if date_str in daily_data:
                all_data.append({
                    'date': date_str,
                    'fees': round(daily_data[date_str]['fees'], 2),
                    'funding': round(daily_data[date_str]['funding'], 2)
                })
            else:
                all_data.append({
                    'date': date_str,
                    'fees': 0.0,
                    'funding': 0.0
                })
        
        # Cache the 90-day result
        cache_result = {'data': all_data}
        chart_data_cache[cache_key] = (cache_result, time.time())
        logger.info("Cached 90 days of chart data")
        
        # Return filtered data for requested days
        return jsonify(filter_data_to_days(cache_result, days))
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching chart data: {e}")
        return jsonify({'error': 'Failed to fetch chart data'}), 500


def filter_data_to_days(full_data: dict, days: int) -> dict:
    """Filter the full 90-day data to the requested number of days."""
    data_list = full_data.get('data', [])
    
    # Get the last N days
    filtered_data = data_list[-days:] if len(data_list) >= days else data_list
    
    # Convert to the expected format
    labels = []
    fees = []
    funding = []
    
    for item in filtered_data:
        labels.append(item['date'])
        fees.append(item['fees'])
        funding.append(item['funding'])
    
    # Calculate totals
    total_fees = sum(fees)
    total_funding = sum(funding)
    
    return {
        'labels': labels,
        'fees': fees,
        'funding': funding,
        'trades': {},  # No longer tracking individual trades
        'total_fees': round(total_fees, 2),
        'total_funding': round(total_funding, 2),
        'total_cost': round(total_fees + total_funding, 2)
    }


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
        
        # Use the main chart-data endpoint to get cached data
        cache_key = hashlib.md5(f"{api_key}:90days".encode()).hexdigest()
        
        # Check cache
        if cache_key in chart_data_cache:
            cached_data, cached_time = chart_data_cache[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                filtered = filter_data_to_days(cached_data, days)
                return jsonify({
                    'labels': filtered['labels'],
                    'fees': filtered['fees'],
                    'total': filtered['total_fees']
                })
        
        # If no cache, return empty data and suggest refresh
        return jsonify({
            'labels': [],
            'fees': [],
            'total': 0,
            'message': 'No cached data available. Please refresh the main chart first.'
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
        
        # Use the main chart-data endpoint to get cached data
        cache_key = hashlib.md5(f"{api_key}:90days".encode()).hexdigest()
        
        # Check cache
        if cache_key in chart_data_cache:
            cached_data, cached_time = chart_data_cache[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                filtered = filter_data_to_days(cached_data, days)
                return jsonify({
                    'labels': filtered['labels'],
                    'funding': filtered['funding'],
                    'total': filtered['total_funding']
                })
        
        # If no cache, return empty data and suggest refresh
        return jsonify({
            'labels': [],
            'funding': [],
            'total': 0,
            'message': 'No cached data available. Please refresh the main chart first.'
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
        
        # Use the main chart-data endpoint to get cached data
        cache_key = hashlib.md5(f"{api_key}:90days".encode()).hexdigest()
        
        # Check cache
        if cache_key in chart_data_cache:
            cached_data, cached_time = chart_data_cache[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                filtered = filter_data_to_days(cached_data, days)
                
                # Count non-zero fee days as trade days
                trade_days = sum(1 for fee in filtered['fees'] if fee > 0)
                
                # Create summary data
                summary_data = format_summary_data(
                    period_days=days,
                    total_fees=filtered['total_fees'],
                    total_funding=filtered['total_funding'],
                    total_cost=filtered['total_cost'],
                    trade_count=trade_days,  # Approximate trade count by days with fees
                    avg_daily_fees=filtered['total_fees'] / days if days > 0 else 0,
                    avg_daily_funding=filtered['total_funding'] / days if days > 0 else 0
                )
                
                return jsonify(summary_data)
        
        # If no cache, return empty summary
        summary_data = format_summary_data(
            period_days=days,
            total_fees=0,
            total_funding=0,
            total_cost=0,
            trade_count=0,
            avg_daily_fees=0,
            avg_daily_funding=0
        )
        
        return jsonify({
            **summary_data,
            'message': 'No cached data available. Please refresh the main chart first.'
        })
        
    except Exception as e:
        logger.error(f"Error fetching summary: {e}")
        return jsonify({'error': 'Failed to fetch summary'}), 500


 