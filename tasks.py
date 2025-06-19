"""
Celery tasks for asynchronous processing
"""
from celery_app import celery_app
from celery import group
from kraken_client import (
    get_position_accumulated_data, get_open_positions,
    get_execution_events, get_account_logs, KrakenAPIError
)
from dashboard_utils import get_period_boundaries
from app import process_chart_data
import logging
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def calculate_position_data_async(self, api_key: str, api_secret: str, position: dict) -> dict:
    """
    Calculate position data asynchronously.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        position: Position dictionary
        
    Returns:
        Position data with accumulated fees and funding
    """
    try:
        logger.info(f"[Task {self.request.id}] Calculating data for position {position.get('symbol')}")
        result = get_position_accumulated_data(api_key, api_secret, position)
        logger.info(f"[Task {self.request.id}] Successfully calculated position data")
        return result
    except KrakenAPIError as exc:
        logger.error(f"[Task {self.request.id}] Kraken API error: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Unexpected error: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def batch_calculate_positions(api_key: str, api_secret: str, positions: List[dict]) -> List[dict]:
    """
    Calculate multiple positions in parallel.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        positions: List of position dictionaries
        
    Returns:
        List of position data with accumulated fees and funding
    """
    logger.info(f"Starting batch calculation for {len(positions)} positions")
    
    # Create a group of tasks
    job = group(
        calculate_position_data_async.s(api_key, api_secret, pos) 
        for pos in positions
    )
    
    # Execute and return results
    result = job.apply_async()
    
    # Wait for results with timeout
    try:
        results = result.get(timeout=120)  # 2 minute timeout
        logger.info(f"Successfully calculated {len(results)} positions")
        return results
    except Exception as e:
        logger.error(f"Batch calculation failed: {e}")
        raise


@celery_app.task(bind=True, max_retries=3)
def update_chart_data_async(self, api_key: str, api_secret: str, days: int = 30) -> dict:
    """
    Update chart data asynchronously.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        days: Number of days to fetch
        
    Returns:
        Chart data dictionary
    """
    try:
        logger.info(f"[Task {self.request.id}] Fetching chart data for {days} days")
        
        # Get time boundaries
        since_ts, before_ts = get_period_boundaries(days)
        
        # Fetch execution events and logs
        executions = get_execution_events(api_key, api_secret, since_ts, before_ts)
        logs = get_account_logs(api_key, api_secret, since_ts, before_ts)
        
        # Process the data
        result = process_chart_data(executions, logs, days)
        
        logger.info(f"[Task {self.request.id}] Successfully processed chart data")
        return result
        
    except KrakenAPIError as exc:
        logger.error(f"[Task {self.request.id}] Kraken API error: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Unexpected error: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def refresh_all_positions_async(api_key: str, api_secret: str) -> dict:
    """
    Refresh all positions and their accumulated data.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        
    Returns:
        Dictionary with positions and status
    """
    try:
        logger.info("Refreshing all positions")
        
        # Get open positions
        positions = get_open_positions(api_key, api_secret)
        
        if not positions:
            return {
                'positions': [],
                'status': 'success',
                'message': 'No open positions'
            }
        
        # Calculate accumulated data for each position
        results = batch_calculate_positions(api_key, api_secret, positions)
        
        return {
            'positions': results,
            'status': 'success',
            'count': len(results),
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to refresh positions: {e}")
        return {
            'positions': [],
            'status': 'error',
            'error': str(e)
        }


@celery_app.task
def periodic_data_update(api_key: str, api_secret: str) -> dict:
    """
    Periodic task to update both chart data and positions.
    Can be scheduled with Celery beat.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        
    Returns:
        Update status
    """
    logger.info("Starting periodic data update")
    
    results = {
        'chart_data': None,
        'positions': None,
        'errors': []
    }
    
    # Update chart data
    try:
        chart_task = update_chart_data_async.delay(api_key, api_secret, 30)
        results['chart_data'] = chart_task.get(timeout=60)
    except Exception as e:
        logger.error(f"Chart update failed: {e}")
        results['errors'].append(f"Chart update failed: {str(e)}")
    
    # Update positions
    try:
        positions_task = refresh_all_positions_async.delay(api_key, api_secret)
        results['positions'] = positions_task.get(timeout=60)
    except Exception as e:
        logger.error(f"Positions update failed: {e}")
        results['errors'].append(f"Positions update failed: {str(e)}")
    
    results['status'] = 'partial' if results['errors'] else 'success'
    results['timestamp'] = datetime.utcnow().isoformat()
    
    return results 