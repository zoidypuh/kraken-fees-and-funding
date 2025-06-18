"""
Minimal Kraken Futures API client for the dashboard.
Contains only the functionality needed for the web application.
"""
import json
import urllib.request
import urllib.parse
import hashlib
import hmac
import base64
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import List, Dict

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 3  # Reduced from 5
INITIAL_RETRY_DELAY = 10  # Increased from 5 seconds
FUTURES_BASE_URL = "https://futures.kraken.com"


class KrakenAPIError(Exception):
    """Custom exception for Kraken API errors."""
    pass


def get_signature(private_key: str, data: str, nonce: str, path: str) -> str:
    """Generate API signature for authenticated requests."""
    return base64.b64encode(
        hmac.new(
            key=base64.b64decode(private_key),
            msg=hashlib.sha256((data + nonce + path.removeprefix("/derivatives")).encode()).digest(),
            digestmod=hashlib.sha512,
        ).digest()
    ).decode()


def generate_signature(api_secret: str, data: str, nonce: str, path: str) -> str:
    """
    Generate signature for Kraken Futures API.
    
    Args:
        api_secret: Base64 encoded API secret
        data: Query string + body data
        nonce: Nonce value
        path: API path
        
    Returns:
        Base64 encoded signature
    """
    # Remove /derivatives prefix from path if present
    path_for_sig = path.removeprefix("/derivatives")
    
    # Create message: SHA256(data + nonce + path)
    message = hashlib.sha256((data + nonce + path_for_sig).encode()).digest()
    
    # Sign with HMAC-SHA512
    signature = hmac.new(
        key=base64.b64decode(api_secret),
        msg=message,
        digestmod=hashlib.sha512
    ).digest()
    
    return base64.b64encode(signature).decode()


def make_request(path: str, api_key: str, api_secret: str, query: dict = None) -> dict:
    """
    Make authenticated request to Kraken Futures API.
    
    Args:
        path: API endpoint path (e.g., "/api/history/v3/account-log")
        api_key: Kraken API key
        api_secret: Kraken API secret
        query: Query parameters
        
    Returns:
        Response data as dict
        
    Raises:
        KrakenAPIError: If request fails
    """
    url = f"{FUTURES_BASE_URL}{path}"
    
    # Prepare query string
    query = query or {}
    query_str = urllib.parse.urlencode(query) if query else ""
    
    if query_str:
        url += f"?{query_str}"
    
    # Check if this is an execution events request (needs different auth)
    is_executions = "executions" in path
    
    # Generate nonce
    nonce = str(int(time.time() * 1000))
    
    # Prepare headers
    headers = {
        "APIKey": api_key,
        "Authent": get_signature(api_secret, query_str, nonce, path),
        "Nonce": nonce
    }
    
    try:
        # Make the request
        req = urllib.request.Request(
            url=url,
            headers=headers,
            method="GET"
        )
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
            # Check for API errors in response
            if "error" in data and data["error"]:
                raise KrakenAPIError(f"API Error: {data['error']}")
            
            return data
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        logger.error(f"HTTP Error {e.code}: {e.reason}")
        logger.error(f"Error body: {error_body}")
        raise KrakenAPIError(f"HTTP Error {e.code}: {e.reason} - {error_body}")
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise KrakenAPIError(f"Request failed: {str(e)}")


def get_account_logs(api_key: str, api_secret: str, since_ts: int, before_ts: int, limit: int = 500) -> list:
    """
    Fetch account logs between timestamps.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        since_ts: Start timestamp in milliseconds
        before_ts: End timestamp in milliseconds
        limit: Number of entries per request (max 500)
    
    Returns:
        List of log entries
    """
    all_logs = []
    current_before = before_ts
    max_iterations = 10  # Safety limit to prevent infinite loops
    iteration = 0
    
    logger.info(f"Fetching logs from {since_ts} to {before_ts}, limit per request: {limit}")
    
    while iteration < max_iterations:
        iteration += 1
        logger.debug(f"Pagination iteration {iteration}, current_before: {current_before}")
        
        try:
            data = make_request(
                "/api/history/v3/account-log",
                api_key,
                api_secret,
                {"limit": limit, "since": since_ts, "before": current_before}
            )
            
            # Handle various response formats
            if not data:
                logger.warning("Empty response from API")
                break
            
            if isinstance(data, dict):
                # Check if it's an error response
                if data.get("error"):
                    raise KrakenAPIError(f"API returned error: {data['error']}")
                
                # Get logs from response
                logs = data.get("logs", [])
            elif isinstance(data, list):
                # Sometimes the API returns a list directly
                logs = data
            else:
                logger.warning(f"Unexpected response type: {type(data)}")
                break
            
            if not logs:
                logger.info("No more logs to fetch")
                break
            
            logger.info(f"Fetched {len(logs)} log entries in iteration {iteration}")
            all_logs.extend(logs)
            
            # If we got fewer logs than requested, we've reached the end
            if len(logs) < limit:
                logger.info("Received fewer logs than limit, pagination complete")
                break
            
            # If we're just validating credentials (limit=1), don't paginate
            if limit == 1:
                logger.info("Credential validation mode, not paginating")
                break
                
            # Use the date of the oldest log as the new 'before'
            # The logs should be sorted newest to oldest
            last_log = logs[-1]
            last_date = last_log.get("date")
            
            if not last_date:
                logger.warning("No date in last log entry, stopping pagination")
                break
                
            new_before = int(datetime.strptime(last_date, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            
            # Check if we're making progress
            if new_before >= current_before:
                logger.warning("Pagination not making progress, stopping")
                break
                
            current_before = new_before
            
            # Add delay between pagination requests
            if iteration < max_iterations:
                time.sleep(1)
            
        except KrakenAPIError:
            # Re-raise API errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error in pagination: {str(e)}")
            raise KrakenAPIError(f"Error fetching account logs: {str(e)}")
    
    if iteration >= max_iterations:
        logger.warning(f"Reached maximum iterations ({max_iterations}) while paginating")
    
    logger.info(f"Total logs fetched: {len(all_logs)}")
    return all_logs


def get_execution_events(api_key: str, api_secret: str, since_ts: int, before_ts: int) -> list:
    """
    Fetch execution events (trades) between timestamps.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        since_ts: Start timestamp in milliseconds
        before_ts: End timestamp in milliseconds
        
    Returns:
        List of execution events
    """
    all_executions = []
    continuation_token = None
    
    # This endpoint actually uses milliseconds, not seconds!
    logger.info(f"Fetching execution events from {since_ts} to {before_ts} (milliseconds)")
    logger.info(f"Date range: {datetime.fromtimestamp(since_ts/1000, tz=timezone.utc)} to {datetime.fromtimestamp(before_ts/1000, tz=timezone.utc)}")
    
    while True:
        try:
            # Build query parameters - using milliseconds
            query = {
                "since": since_ts,
                "before": before_ts,
                "sort": "asc"
            }
            
            # Add continuation token if we have one (for pagination)
            if continuation_token:
                query["continuation_token"] = continuation_token
            
            logger.info(f"Request query parameters: {query}")
            
            # Make request to executions endpoint
            data = make_request(
                "/api/history/v3/executions",
                api_key,
                api_secret,
                query
            )
            
            # Log the raw response for debugging
            logger.info(f"Raw response from executions API: {json.dumps(data, indent=2)}")
            
            # Handle response
            if not data:
                logger.warning("Empty response from executions API")
                break
            
            # Check for different possible field names
            executions = data.get("executions") or data.get("elements") or data.get("fills") or []
            
            # Special handling for Kraken's execution events structure
            if not executions and "elements" in data:
                executions = data["elements"]
                logger.info(f"Found {len(executions)} elements in response")
            
            if not executions:
                logger.info("No executions found in response")
                logger.info(f"Available keys in response: {list(data.keys())}")
                break
            
            logger.info(f"Fetched {len(executions)} execution events")
            all_executions.extend(executions)
            
            # Check for continuation token for pagination
            continuation_token = data.get("continuationToken") or data.get("continuation_token")
            if not continuation_token:
                break
                
            # Add delay between pagination requests
            time.sleep(0.5)
            
        except KrakenAPIError:
            # Re-raise API errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching executions: {str(e)}")
            raise KrakenAPIError(f"Error fetching execution events: {str(e)}")
    
    logger.info(f"Total execution events fetched: {len(all_executions)}")
    return all_executions


def get_open_positions(api_key: str, api_secret: str) -> list:
    """
    Fetch open positions from Kraken Futures API.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        
    Returns:
        List of open positions
    """
    try:
        logger.info("Fetching open positions")
        
        # Make request to open positions endpoint
        data = make_request(
            "/derivatives/api/v3/openpositions",
            api_key,
            api_secret
        )
        
        # Log the raw response for debugging
        logger.debug(f"Raw response from open positions API: {json.dumps(data, indent=2)}")
        
        # Handle response
        if not data:
            logger.warning("Empty response from open positions API")
            return []
        
        # Check for the result field which contains the positions
        if "result" in data and data["result"] == "success":
            positions = data.get("openPositions", [])
            logger.info(f"Found {len(positions)} open positions")
            return positions
        elif "openPositions" in data:
            # Sometimes the API returns positions directly
            positions = data["openPositions"]
            logger.info(f"Found {len(positions)} open positions")
            return positions
        else:
            logger.warning(f"Unexpected response structure. Available keys: {list(data.keys())}")
            return []
            
    except KrakenAPIError:
        # Re-raise API errors
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching open positions: {str(e)}")
        raise KrakenAPIError(f"Error fetching open positions: {str(e)}")


def find_true_position_open_time(api_key: str, api_secret: str, position_symbol: str, position_size: float, current_ts: int) -> int:
    """
    Find when a position was opened by looking at execution history.
    This works by going backwards in time and tracking the net position.
    When the net position reaches zero, we've found when the position was opened.
    """
    logger.info(f"Finding open time for {position_symbol} with current size {position_size}")
    
    MAX_LOOKBACK_DAYS = 730  # Look back up to 2 years
    CHUNK_DAYS = 30  # Smaller chunks for more granular search
    
    # Track net position as we go back in time
    net_position = position_size
    all_executions = []
    
    end_chunk_ts = current_ts
    
    for chunk_num in range(MAX_LOOKBACK_DAYS // CHUNK_DAYS):
        start_chunk_ts = end_chunk_ts - (CHUNK_DAYS * 24 * 60 * 60 * 1000)
        logger.debug(f"Searching chunk {chunk_num}: "
                     f"{datetime.fromtimestamp(start_chunk_ts/1000, tz=timezone.utc).date()} to "
                     f"{datetime.fromtimestamp(end_chunk_ts/1000, tz=timezone.utc).date()}")

        chunk_executions = get_execution_events(api_key, api_secret, start_chunk_ts, end_chunk_ts)
        
        if not chunk_executions:
            end_chunk_ts = start_chunk_ts
            continue

        # Extract and filter executions for this symbol
        symbol_executions = []
        for e in chunk_executions:
            if isinstance(e, dict):
                timestamp = e.get('timestamp')
                if isinstance(timestamp, (int, float)):
                    exec_s = None
                    exec_q = 0.0
                    exec_direction = None
                    
                    event = e.get('event', {})
                    if 'execution' in event:
                        exec_wrapper = event['execution']
                        exec_detail = exec_wrapper.get('execution', exec_wrapper)
                        order = exec_detail.get('order', {})
                        exec_s = (order.get('tradeable') or exec_detail.get('tradeable') or exec_detail.get('symbol', '')).upper()
                        exec_q = float(exec_detail.get('quantity', 0))
                        exec_direction = order.get('direction', '').lower()
                    else:
                        exec_s = e.get('symbol', '').upper()
                        exec_q = float(e.get('quantity', e.get('size', 0)))
                        exec_direction = e.get('direction', '').lower()
                    
                    if exec_s == position_symbol.upper() and exec_q != 0:
                        # Adjust quantity based on direction
                        if exec_direction == 'sell':
                            exec_q = -exec_q
                        symbol_executions.append((timestamp, exec_q, e))

        if symbol_executions:
            # Sort by timestamp (newest first since we're going backwards)
            symbol_executions.sort(key=lambda x: x[0], reverse=True)
            all_executions.extend(symbol_executions)
            
            # Calculate net position at the start of this chunk
            for ts, qty, _ in symbol_executions:
                net_position -= qty
                logger.debug(f"After trade at {datetime.fromtimestamp(ts/1000, tz=timezone.utc)}: "
                           f"qty={qty:.4f}, net_position={net_position:.4f}")
                
                # If we've reached zero or crossed it, we found the opening
                if abs(net_position) < 0.0001:  # Close to zero
                    logger.info(f"Found position open at {datetime.fromtimestamp(ts/1000, tz=timezone.utc)}")
                    return ts
        
        end_chunk_ts = start_chunk_ts
    
    # If we couldn't find the exact opening, use the oldest trade we found
    if all_executions:
        oldest_ts = min(exec[0] for exec in all_executions)
        logger.warning(f"Could not find exact position open. Using oldest trade at "
                      f"{datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc)}")
        return oldest_ts
    
    # Fallback: no trades found at all
    logger.warning(f"No trades found for {position_symbol}. Defaulting to 30 days ago.")
    return current_ts - (30 * 24 * 60 * 60 * 1000)


def get_position_accumulated_data(api_key: str, api_secret: str, position: dict) -> dict:
    """
    Calculate accumulated funding and fees for a position since it was opened.
    This function uses the fillTime from the position data to determine when to start accumulating.
    """
    try:
        current_ts = int(time.time() * 1000)
        symbol = position.get("symbol", "").upper()
        position_size = abs(float(position.get("size", 0)))

        if not symbol or position_size == 0:
            return {"accumulated_funding": 0.0, "accumulated_fees": 0.0, "data_is_capped": False, "error": "Missing symbol or size"}

        # fillTime is deprecated and unreliable - always use trade history
        true_opened_ts = find_true_position_open_time(api_key, api_secret, symbol, position_size, current_ts)
        
        ONE_YEAR_AGO_TS = current_ts - (365 * 24 * 60 * 60 * 1000)
        fetch_from_ts = true_opened_ts
        data_is_capped = False
        if true_opened_ts < ONE_YEAR_AGO_TS:
            logger.warning(f"Position {symbol} is over a year old. Capping data accumulation to 1 year for performance.")
            fetch_from_ts = ONE_YEAR_AGO_TS
            data_is_capped = True

        logger.info(f"Fetching full history for {symbol} from {datetime.fromtimestamp(fetch_from_ts/1000, tz=timezone.utc).date()}")
        all_account_logs = get_account_logs(api_key, api_secret, fetch_from_ts, current_ts)
        all_execution_events = get_execution_events(api_key, api_secret, fetch_from_ts, current_ts)
        
        accumulated_funding = 0.0
        accumulated_fees = 0.0
        
        if all_account_logs:
            for log in all_account_logs:
                if log.get('funding_rate') is not None and log.get('realized_funding') is not None:
                    log_date_str = log.get("date")
                    try:
                        log_ts = datetime.fromisoformat(log_date_str.replace('Z', '+00:00')).timestamp() * 1000
                        if log_ts < true_opened_ts: continue
                    except (ValueError, TypeError): pass
                
                    log_contract = log.get("contract", "").upper()
                    if symbol in log_contract:
                        accumulated_funding += abs(float(log.get('realized_funding', 0)))

        if all_execution_events:
            for execution in all_execution_events:
                exec_time = execution.get('timestamp', 0)
                if exec_time < true_opened_ts: continue

                exec_s = ""
                fee = 0.0
                event = execution.get('event', {})
                if 'execution' in event:
                    exec_wrapper = event['execution']
                    exec_detail = exec_wrapper.get('execution', exec_wrapper)
                    order = exec_detail.get('order', {})
                    exec_s = (order.get('tradeable') or exec_detail.get('tradeable') or '').upper()
                    fee = abs(float(exec_detail.get('orderData', {}).get('fee', 0)))
                
                if exec_s == symbol and fee > 0:
                    accumulated_fees += fee
        
        return {
            "accumulated_funding": round(accumulated_funding, 2),
            "accumulated_fees": round(accumulated_fees, 2),
            "data_is_capped": data_is_capped,
            "true_opened_date_utc": datetime.fromtimestamp(true_opened_ts/1000, tz=timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error calculating accumulated data for {position.get('symbol')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"accumulated_funding": 0.0, "accumulated_fees": 0.0, "data_is_capped": False, "error": str(e)} 