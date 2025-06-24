"""
Trading volumes API route.
"""
from flask import Blueprint, jsonify, request
import logging
from datetime import datetime, timezone, timedelta
import time

from kraken_client import (
    get_fills, get_execution_events, KrakenAPIError
)
from .auth import require_api_credentials

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
        
        # Calculate time range
        current_ts = int(time.time() * 1000)
        start_ts = current_ts - (days * 24 * 60 * 60 * 1000)
        
        logger.info(f"Fetching trading volumes for last {days} days")
        
        # First, try to get recent fills (more accurate for volume)
        daily_volumes = {}
        
        try:
            # Get recent fills (usually last 100)
            fills = get_fills(api_key, api_secret, limit=100)
            logger.info(f"Fetched {len(fills)} recent fills")
            
            # Debug: log first fill to see structure
            if fills and len(fills) > 0:
                logger.info(f"Sample fill keys: {list(fills[0].keys())}")
                logger.info(f"Sample fill: {fills[0]}")
            
            # Process fills
            for fill in fills:
                fill_time_str = fill.get('fillTime', '')
                size = fill.get('size', 0)
                mark_price = fill.get('markPrice', 0) or fill.get('price', 0)
                
                if not fill_time_str or not size or not mark_price:
                    continue
                    
                try:
                    # Parse fill time
                    fill_time = datetime.fromisoformat(fill_time_str.replace('Z', '+00:00'))
                    fill_ts = int(fill_time.timestamp() * 1000)
                    
                    # Skip if outside our time range
                    if fill_ts < start_ts or fill_ts > current_ts:
                        continue
                        
                    day_key = fill_time.date().isoformat()
                    
                    # Calculate USD volume = quantity × mark price
                    usd_volume = abs(float(size)) * float(mark_price)
                    
                    # Accumulate volume for each day
                    if day_key not in daily_volumes:
                        daily_volumes[day_key] = 0
                    
                    daily_volumes[day_key] += usd_volume
                    logger.debug(f"Added fill volume ${usd_volume:.2f} (size: {size}, price: {mark_price}) for date {day_key}")
                    
                except Exception as e:
                    logger.warning(f"Error processing fill: {e}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Error fetching fills: {e}")
            
        # Always fetch execution events to ensure we get complete trade history
        # (fills endpoint only returns last 100 fills which might not cover 30 days)
        logger.info("Fetching execution events for complete trade history")
        
        try:
            executions = get_execution_events(
                api_key, api_secret, 
                start_ts, current_ts
            )
            logger.info(f"Fetched {len(executions)} execution events")
            
            # Debug: log first entry to see structure
            if executions and len(executions) > 0:
                logger.info(f"Sample execution keys: {list(executions[0].keys())}")
                logger.info(f"Sample execution: {executions[0]}")
            
            trades_found = 0
            for execution in executions:
                # Execution events are all trades, no need to filter
                
                # Get timestamp and convert to date
                timestamp = execution.get('timestamp')
                if not timestamp:
                    continue
                
                # Navigate to the nested execution data
                event = execution.get('event', {})
                exec_data = event.get('execution', {}).get('execution', {})
                
                if not exec_data:
                    logger.debug(f"No execution data found in event")
                    continue
                
                # Look for quantity and price from the nested structure
                quantity = abs(float(exec_data.get('quantity', 0) or 0))
                price = float(exec_data.get('price', 0) or 0)
                
                # Also can use usdValue directly if available
                usd_value = float(exec_data.get('usdValue', 0) or 0)
                
                # Skip if we don't have valid trade data
                if quantity == 0 or (price == 0 and usd_value == 0):
                    logger.debug(f"Skipping incomplete execution: qty={quantity}, price={price}, usdValue={usd_value}")
                    continue
                    
                try:
                    # Convert timestamp to date
                    if isinstance(timestamp, str):
                        exec_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        # Assume milliseconds timestamp
                        exec_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                    
                    day_key = exec_time.date().isoformat()
                    
                    # Calculate USD volume - prefer usdValue if available
                    if usd_value > 0:
                        volume = usd_value
                    else:
                        volume = quantity * price
                    
                    # Accumulate volume for each day
                    if day_key not in daily_volumes:
                        daily_volumes[day_key] = 0
                    
                    daily_volumes[day_key] += volume
                    trades_found += 1
                    logger.debug(f"Added execution volume ${volume:.2f} (qty: {quantity}, price: {price}, usdValue: {usd_value}) for date {day_key}")
                    
                except Exception as e:
                    logger.warning(f"Error processing execution: {e}")
                    continue
                    
            logger.info(f"Found {trades_found} trades out of {len(executions)} execution events")
                    
        except Exception as e:
            logger.error(f"Error fetching trade logs: {e}")
            # Continue with whatever data we have
        
        # Generate all dates for the requested period
        current_date = datetime.now(timezone.utc).date()
        result = []
        
        for i in range(days):
            date = (current_date - timedelta(days=days-1-i))
            date_str = date.isoformat()
            
            volume = daily_volumes.get(date_str, 0)
            result.append({
                'date': date_str,
                'volume': round(volume, 4)
            })
        
        logger.info(f"Returning {len(result)} days of volume data")
        
        return jsonify({
            'data': result,
            'period': f'{days} days',
            'total_volume': round(sum(daily_volumes.values()), 4)
        })
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching trading volumes: {e}")
        return jsonify({'error': 'Failed to fetch trading volumes'}), 500 