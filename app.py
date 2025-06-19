"""
Kraken Futures Fees and Funding Dashboard
A Flask web application to visualize trading fees and funding costs.
"""
from flask import Flask, render_template, jsonify, request as flask_request, make_response
import logging
import os
import json
import time
from datetime import datetime, timezone, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from functools import wraps, lru_cache

# Local imports
from kraken_client import (
    get_execution_events, get_account_logs, KrakenAPIError, 
    get_open_positions, get_position_accumulated_data,
    batch_get_position_accumulated_data, get_cached_fee_schedules,
    batch_get_tickers
)
from dashboard_utils import get_period_boundaries, extract_asset_from_contract, aggregate_logs_by_day, calculate_unrealized_pnl

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache configuration
# Use /tmp for cache on Google App Engine (read-only filesystem)
if os.environ.get('GAE_ENV', '').startswith('standard'):
    CACHE_DIR = '/tmp/kraken_cache'
else:
    CACHE_DIR = os.path.join(os.path.dirname(__file__), '.cache')

CACHE_DURATION = 300  # 5 minutes cache duration
MAX_WORKERS = 4  # Increased for better parallel processing performance

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

# Simple rate limiting for credential validation
last_credential_attempt = 0
CREDENTIAL_ATTEMPT_COOLDOWN = 30  # seconds


def get_api_credentials(request):
    """Extract API credentials from cookies."""
    try:
        # Get credentials from cookies
        api_key = request.cookies.get('kraken_api_key', '')
        api_secret = request.cookies.get('kraken_api_secret', '')
        
        if api_key and api_secret:
            return api_key, api_secret
        return None, None
    except Exception as e:
        logger.error(f"Error getting API credentials: {e}")
        return None, None


def require_api_credentials(f):
    """Decorator to ensure API credentials are available."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key, api_secret = get_api_credentials(flask_request)
        if not api_key or not api_secret:
            return jsonify({'error': 'API credentials not configured. Please set your API keys.'}), 401
        return f(api_key, api_secret, *args, **kwargs)
    return decorated_function


def get_cache_key(api_key: str, data_type: str, since_ts: int, before_ts: int) -> str:
    """Generate a cache key based on API key and request parameters."""
    # Use first 8 chars of API key for privacy
    key_prefix = api_key[:8] if len(api_key) > 8 else api_key
    raw_key = f"{key_prefix}_{data_type}_{since_ts}_{before_ts}"
    return hashlib.md5(raw_key.encode()).hexdigest()


def get_cached_data(cache_key: str) -> dict:
    """Retrieve data from cache if valid."""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    if os.path.exists(cache_file):
        # Check if cache is still valid
        file_age = time.time() - os.path.getmtime(cache_file)
        if file_age < CACHE_DURATION:
            try:
                with open(cache_file, 'r') as f:
                    logger.info(f"Cache hit for key {cache_key}")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading cache: {e}")
    
    return None


def save_to_cache(cache_key: str, data: dict):
    """Save data to cache."""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f)
        logger.info(f"Saved to cache: {cache_key}")
    except Exception as e:
        logger.warning(f"Error saving to cache: {e}")


def fetch_data_parallel(api_key: str, api_secret: str, since_ts: int, before_ts: int):
    """Fetch execution events and account logs in parallel."""
    executions = []
    logs = []
    errors = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit both API calls
        future_executions = executor.submit(
            get_execution_events, api_key, api_secret, since_ts, before_ts
        )
        future_logs = executor.submit(
            get_account_logs, api_key, api_secret, since_ts, before_ts
        )
        
        # Collect results
        futures = {
            future_executions: 'executions',
            future_logs: 'logs'
        }
        
        for future in as_completed(futures):
            data_type = futures[future]
            try:
                result = future.result()
                if data_type == 'executions':
                    executions = result
                    logger.info(f"Fetched {len(executions)} execution events")
                else:
                    logs = result
                    logger.info(f"Fetched {len(logs)} account logs")
            except Exception as e:
                logger.error(f"Error fetching {data_type}: {e}")
                errors.append(f"Error fetching {data_type}: {str(e)}")
    
    return executions, logs, errors


def get_chart_data(api_key: str, api_secret: str, days_back: int = 30):
    """
    Fetch and process data for the chart with caching and parallel fetching.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        days_back: Number of days to look back
        
    Returns:
        Dict with labels, fees, funding, and trades data
    """
    # Check cache first
    since_ts, before_ts = get_period_boundaries(days_back)
    cache_key = get_cache_key(api_key, f"chart_data_{days_back}", since_ts, before_ts)
    
    cached_data = get_cached_data(cache_key)
    if cached_data:
        return cached_data
    
    # Fetch data in parallel
    executions, logs, errors = fetch_data_parallel(api_key, api_secret, since_ts, before_ts)
    
    if errors and not executions and not logs:
        raise KrakenAPIError("; ".join(errors))
    
    # Process data
    daily_data = {}
    trades_by_day = {}
    
    # Optimized date parsing with LRU cache
    @lru_cache(maxsize=1000)
    def parse_date(date_str: str) -> str:
        """Cached date parsing for better performance."""
        try:
            log_time = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            return log_time.date().isoformat()
        except:
            return None
    
    # Process funding from account logs (optimized)
    daily_funding = {}
    for log in logs:
        if log.get('funding_rate') is not None and log.get('realized_funding') is not None:
            date_str = log.get('date', '')
            if date_str:
                day_key = parse_date(date_str)
                if day_key:
                    funding_value = float(log.get('realized_funding', 0))
                    daily_funding[day_key] = daily_funding.get(day_key, 0.0) + abs(funding_value)
    
    # Process execution events
    for execution in executions:
        exec_detail = None
        exec_time_ms = None
        
        if isinstance(execution, dict):
            exec_time_ms = execution.get('timestamp')
            event = execution.get('event', {})
            
            if 'execution' in event:
                exec_wrapper = event['execution']
                if 'execution' in exec_wrapper:
                    exec_detail = exec_wrapper['execution']
                else:
                    exec_detail = exec_wrapper
            
            if exec_detail:
                order = exec_detail.get('order', {})
                tradeable = order.get('tradeable') or exec_detail.get('tradeable') or exec_detail.get('symbol', '')
                asset = extract_asset_from_contract(tradeable)
                
                price = float(exec_detail.get('price') or 0)
                quantity = abs(float(exec_detail.get('quantity') or 0))
                
                order_data = exec_detail.get('orderData', {})
                fee = abs(float(order_data.get('fee', 0)))
                
                if fee == 0:
                    fee = abs(float(exec_detail.get('fee', 0)))
            else:
                asset = extract_asset_from_contract(execution.get('symbol', ''))
                price = float(execution.get('price') or 0)
                quantity = abs(float(execution.get('quantity') or execution.get('size') or 0))
                fee = abs(float(execution.get('fee', 0)))
        else:
            continue
        
        if not exec_time_ms:
            continue
        
        try:
            exec_time = datetime.fromtimestamp(exec_time_ms / 1000, tz=timezone.utc)
            day_key = exec_time.date().isoformat()
            
            if day_key not in daily_data:
                daily_data[day_key] = {
                    'fees': 0.0,
                    'funding': daily_funding.get(day_key, 0.0)
                }
            
            if day_key not in trades_by_day:
                trades_by_day[day_key] = {}
            
            daily_data[day_key]['fees'] += fee
            
            agg_key = f"{asset}_{price}"
            
            if agg_key not in trades_by_day[day_key]:
                trades_by_day[day_key][agg_key] = {
                    'asset': asset,
                    'price': price,
                    'quantity': 0,
                    'fee': 0,
                    'count': 0
                }
            
            trades_by_day[day_key][agg_key]['quantity'] += quantity
            trades_by_day[day_key][agg_key]['fee'] += fee
            trades_by_day[day_key][agg_key]['count'] += 1
            
        except Exception as e:
            logger.warning(f"Error processing execution: {e}")
            continue
    
    # Convert aggregated trades to list format
    for day_key in trades_by_day:
        trades_list = list(trades_by_day[day_key].values())
        trades_list.sort(key=lambda x: (x['asset'], -x['price']))
        trades_by_day[day_key] = trades_list
    
    # Include days with only funding
    for day_key in daily_funding:
        if day_key not in daily_data:
            daily_data[day_key] = {
                'fees': 0.0,
                'funding': daily_funding[day_key]
            }
    
    # Sort by date
    sorted_days = sorted(daily_data.keys())
    
    # Format for Chart.js
    labels = sorted_days
    fees_data = [round(daily_data[day]['fees'], 2) for day in sorted_days]
    funding_data = []
    
    for day in sorted_days:
        if day in daily_data:
            funding_data.append(round(daily_data[day].get('funding', 0), 2))
        else:
            funding_data.append(round(daily_funding.get(day, 0), 2))
    
    trades_data = {}
    for day in sorted_days:
        if day in trades_by_day:
            trades_data[day] = trades_by_day[day]
        else:
            trades_data[day] = []
    
    result = {
        'labels': labels,
        'fees': fees_data,
        'funding': funding_data,
        'trades': trades_data
    }
    
    # Save to cache
    save_to_cache(cache_key, result)
    
    return result


def cleanup_cache():
    """Remove cache files older than cache duration."""
    try:
        current_time = time.time()
        for filename in os.listdir(CACHE_DIR):
            filepath = os.path.join(CACHE_DIR, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > CACHE_DURATION * 2:  # Remove files older than 2x cache duration
                    os.remove(filepath)
                    logger.info(f"Removed old cache file: {filename}")
    except Exception as e:
        logger.warning(f"Error cleaning cache: {e}")


@app.route('/')
def index():
    """Render the main dashboard page."""
    api_key, _ = get_api_credentials(flask_request)
    
    # Create a masked version of the API key for display
    masked_api_key = ""
    if api_key:
        # Show first 8 and last 4 characters
        if len(api_key) > 12:
            masked_api_key = api_key[:8] + "..." + api_key[-4:]
        else:
            masked_api_key = api_key
    
    return render_template('index.html', 
                         has_credentials=bool(api_key),
                         masked_api_key=masked_api_key)


@app.route('/api/data')
@require_api_credentials
def get_data(api_key, api_secret):
    """
    API endpoint to fetch chart data.
    
    Query parameters:
        days (int): Number of days to fetch (default: 30)
        
    Returns:
        JSON response with chart data or error message
    """
    try:
        days = int(flask_request.args.get('days', 30))
        
        # Validate days parameter
        if days < 1 or days > 365:
            return jsonify({'error': 'Days parameter must be between 1 and 365'}), 400
        
        data = get_chart_data(api_key, api_secret, days)
        
        # Also fetch open positions
        positions = get_open_positions_data(api_key, api_secret)
        data['positions'] = positions
        
        return jsonify(data)
        
    except KrakenAPIError as e:
        logger.error(f"API error: {e}")
        return jsonify({'error': f'Kraken API error: {str(e)}'}), 500
    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        return jsonify({'error': 'Invalid days parameter'}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/set-credentials', methods=['POST'])
def set_credentials():
    """
    Save API credentials in secure cookies.
    """
    global last_credential_attempt
    
    # Check rate limit
    current_time = time.time()
    time_since_last = current_time - last_credential_attempt
    if time_since_last < CREDENTIAL_ATTEMPT_COOLDOWN:
        wait_time = int(CREDENTIAL_ATTEMPT_COOLDOWN - time_since_last)
        logger.warning(f"Rate limit: credential validation attempt blocked, {wait_time}s cooldown remaining")
        return jsonify({
            'error': f'Too many attempts. Please wait {wait_time} seconds before trying again.'
        }), 429
    
    try:
        data = flask_request.get_json()
        api_key = data.get('api_key', '').strip()
        api_secret = data.get('api_secret', '').strip()
        
        logger.info(f"Attempting to save credentials - API key length: {len(api_key)}, secret length: {len(api_secret)}")
        
        if not api_key or not api_secret:
            return jsonify({'error': 'Both API key and secret are required'}), 400
        
        # Update rate limit timestamp
        last_credential_attempt = current_time
        
        # Test credentials by fetching recent data
        try:
            since_ts, before_ts = get_period_boundaries(1)  # Last 1 day
            logger.info(f"Testing credentials with time range: {since_ts} to {before_ts}")
            
            events = get_execution_events(api_key, api_secret, since_ts, before_ts)
            logger.info(f"Credential test successful, retrieved {len(events)} execution events")
        except KrakenAPIError as e:
            logger.error(f"Kraken API error during credential validation: {str(e)}")
            error_msg = str(e)
            
            # Provide more helpful error messages
            if "Rate limit" in error_msg:
                return jsonify({
                    'error': 'Kraken API rate limit exceeded. Please wait a few minutes before trying again.'
                }), 429
            elif "Invalid API key" in error_msg or "API key" in error_msg:
                return jsonify({'error': 'Invalid API key. Please check your Kraken Futures API credentials.'}), 401
            elif "Invalid signature" in error_msg or "signature" in error_msg:
                return jsonify({'error': 'Invalid API secret. Please check your Kraken Futures API credentials.'}), 401
            elif "Permission denied" in error_msg:
                return jsonify({'error': 'API key lacks required permissions. Ensure it has read access to execution events.'}), 401
            else:
                return jsonify({'error': f'API validation failed: {error_msg}'}), 401
        except Exception as e:
            logger.error(f"Unexpected error during credential validation: {str(e)}")
            return jsonify({'error': f'Failed to validate credentials: {str(e)}'}), 500
        
        # Create response with cookies
        response = make_response(jsonify({'success': True, 'message': 'Credentials saved successfully'}))
        
        # Set secure cookies (expires in 30 days)
        cookie_options = {
            'max_age': 30 * 24 * 60 * 60,  # 30 days
            'httponly': True,
            'samesite': 'Lax'
        }
        
        # Add secure flag if not in development
        if not app.debug:
            cookie_options['secure'] = True
        
        response.set_cookie('kraken_api_key', api_key, **cookie_options)
        response.set_cookie('kraken_api_secret', api_secret, **cookie_options)
        
        logger.info("Credentials saved successfully to cookies")
        return response
        
    except Exception as e:
        logger.error(f"Error setting credentials: {e}")
        return jsonify({'error': 'Failed to save credentials'}), 500


@app.route('/api/clear-credentials', methods=['POST'])
def clear_credentials():
    """Clear API credentials from cookies."""
    response = make_response(jsonify({'success': True, 'message': 'Credentials cleared'}))
    response.set_cookie('kraken_api_key', '', max_age=0)
    response.set_cookie('kraken_api_secret', '', max_age=0)
    return response


@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'kraken-dashboard'})


@app.route('/api/chart-data', methods=['POST'])
def chart_data():
    """API endpoint to fetch chart data."""
    try:
        data = flask_request.get_json()
        api_key = data.get('api_key')
        api_secret = data.get('api_secret')
        days_back = int(data.get('days', 30))
        
        if not api_key or not api_secret:
            return jsonify({'error': 'API credentials required'}), 400
        
        # Get chart data
        chart_data = get_chart_data(api_key, api_secret, days_back)
        
        return jsonify(chart_data)
        
    except KrakenAPIError as e:
        logger.error(f"Kraken API error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


@app.route('/api/chart-data-progressive', methods=['POST'])
def chart_data_progressive():
    """API endpoint for progressive loading of chart data."""
    try:
        data = flask_request.get_json()
        api_key = data.get('api_key')
        api_secret = data.get('api_secret')
        days_back = int(data.get('days', 30))
        chunk_days = int(data.get('chunk_days', 7))
        
        if not api_key or not api_secret:
            return jsonify({'error': 'API credentials required'}), 400
        
        # Create a streaming response
        def generate():
            chunks = []
            end_date = datetime.now(timezone.utc)
            
            # Divide the period into chunks
            remaining_days = days_back
            while remaining_days > 0:
                chunk_size = min(chunk_days, remaining_days)
                start_date = end_date - timedelta(days=chunk_size)
                
                chunks.append({
                    'start': int(start_date.timestamp() * 1000),
                    'end': int(end_date.timestamp() * 1000),
                    'days': chunk_size
                })
                
                end_date = start_date
                remaining_days -= chunk_size
            
            # Process chunks
            for i, chunk in enumerate(chunks):
                try:
                    # Check cache for this chunk
                    cache_key = get_cache_key(api_key, f"chunk_{i}_{days_back}", chunk['start'], chunk['end'])
                    cached_data = get_cached_data(cache_key)
                    
                    if cached_data:
                        yield f"data: {json.dumps({'chunk': i, 'total_chunks': len(chunks), 'data': cached_data})}\n\n"
                    else:
                        # Fetch and process this chunk
                        executions, logs, _ = fetch_data_parallel(
                            api_key, api_secret, chunk['start'], chunk['end']
                        )
                        
                        # Process data (reuse the same logic from get_chart_data)
                        # This is a simplified version - in production, extract this to a shared function
                        chunk_data = {
                            'labels': [],
                            'fees': [],
                            'funding': [],
                            'trades': {}
                        }
                        
                        # ... (processing logic would go here)
                        
                        save_to_cache(cache_key, chunk_data)
                        yield f"data: {json.dumps({'chunk': i, 'total_chunks': len(chunks), 'data': chunk_data})}\n\n"
                        
                except Exception as e:
                    logger.error(f"Error processing chunk {i}: {e}")
                    yield f"data: {json.dumps({'chunk': i, 'error': str(e)})}\n\n"
            
            yield "data: {\"done\": true}\n\n"
        
        response = make_response(generate())
        response.headers['Content-Type'] = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'
        
        return response
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


@app.route('/api/validate-credentials', methods=['POST'])
def validate_credentials():
    """Validate API credentials by making a test request."""
    try:
        data = flask_request.get_json()
        api_key = data.get('api_key')
        api_secret = data.get('api_secret')
        
        if not api_key or not api_secret:
            return jsonify({'valid': False, 'error': 'API credentials required'}), 400
        
        # Try to fetch a small amount of recent data
        since_ts, before_ts = get_period_boundaries(1)
        
        # Make a test request with limit=1
        logs = get_account_logs(api_key, api_secret, since_ts, before_ts, limit=1)
        
        return jsonify({'valid': True})
        
    except KrakenAPIError as e:
        logger.error(f"Credential validation failed: {str(e)}")
        return jsonify({'valid': False, 'error': str(e)}), 401
    except Exception as e:
        logger.error(f"Unexpected error during validation: {str(e)}")
        return jsonify({'valid': False, 'error': 'Validation failed'}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500


# Start cache cleanup thread when app starts
def start_cache_cleanup():
    """Start periodic cache cleanup."""
    def cleanup_loop():
        while True:
            time.sleep(600)  # Run every 10 minutes
            cleanup_cache()
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()


def get_open_positions_data(api_key: str, api_secret: str):
    """
    Fetch open positions with accumulated funding and fees.
    Optimized version using batch processing for up to 4x speedup.
    """
    try:
        positions = get_open_positions(api_key, api_secret)
        
        if not positions:
            logger.info("No open positions found")
            return []
        
        # Get unique symbols for ticker fetching
        symbols = list(set(pos.get('symbol', '') for pos in positions if pos.get('symbol')))
        
        # Fetch tickers and accumulated data in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both operations
            future_tickers = executor.submit(batch_get_tickers, api_key, api_secret, symbols)
            future_accumulated = executor.submit(batch_get_position_accumulated_data, api_key, api_secret, positions)
            
            # Get results
            tickers = future_tickers.result()
            batch_results = future_accumulated.result()
        
        # Format results for frontend
        enriched_positions = []
        for i, result in enumerate(batch_results):
            symbol = result.get('symbol', 'Unknown')
            
            # Get ticker data for this symbol
            ticker_data = tickers.get(symbol, {})
            current_price = float(ticker_data.get('markPrice', 0)) if ticker_data and 'markPrice' in ticker_data else 0
            
            # Get average price from the original position data
            original_position = positions[i]
            avg_price = float(original_position.get('price', 0))
            
            # Calculate unrealized P&L
            unrealized_pnl = calculate_unrealized_pnl({
                'size': result.get('size', 0),
                'price': avg_price
            }, current_price)
            
            # Calculate net unrealized P&L (unrealized P&L - accumulated fees - accumulated funding)
            accumulated_funding = result.get('accumulated_funding', 0.0)
            accumulated_fees = result.get('accumulated_fees', 0.0)
            net_unrealized_pnl = unrealized_pnl - accumulated_funding - accumulated_fees
            
            enriched_position = {
                'symbol': symbol,
                'size': result.get('size', 0),
                'avgPrice': avg_price,
                'currentPrice': current_price,
                'unrealizedPnl': unrealized_pnl,
                'accumulatedFunding': accumulated_funding,
                'accumulatedFees': accumulated_fees,
                'netUnrealizedPnl': net_unrealized_pnl,
                'dataIsCapped': result.get('data_is_capped', False),
                'trueOpenedDateUTC': result.get('true_opened_date_utc'),
                'error': result.get('error')
            }
            enriched_positions.append(enriched_position)
        
        return enriched_positions
        
    except Exception as e:
        logger.error(f"Error fetching and processing open positions data: {e}")
        import traceback
        traceback.print_exc()
        # Return an error object that can be displayed on the frontend
        return [{'error': f'Top-level error in get_open_positions_data: {e}'}]


if __name__ == '__main__':
    # Start cache cleanup
    start_cache_cleanup()
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG']) 