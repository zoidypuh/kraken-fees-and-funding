"""
Simplified Kraken Futures API client for the dashboard.
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
import threading
from datetime import datetime, timezone
import os
from typing import List, Dict, Tuple, Optional, Any, Union
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2
FUTURES_BASE_URL = "https://futures.kraken.com"

# Account log entry types
ENTRY_TYPE_FUTURES_TRADE = "futures trade"
ENTRY_TYPE_FUNDING_RATE_CHANGE = "funding rate change"

# Rate limiting
class RateLimiter:
    """Simple rate limiter to avoid hitting API limits."""
    def __init__(self, min_interval=0.5):
        self.min_interval = min_interval
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limit."""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                time.sleep(wait_time)
            self.last_request_time = time.time()

# Global rate limiter
_rate_limiter = RateLimiter(min_interval=0.5)


class KrakenAPIError(Exception):
    """Custom exception for Kraken API errors."""
    pass


def get_api_credentials(request) -> Tuple[Optional[str], Optional[str]]:
    """Extract API credentials from cookies or environment variables."""
    try:
        # First try cookies, then environment variables
        sources = [
            (request.cookies.get('kraken_api_key'), request.cookies.get('kraken_api_secret')),
            (os.environ.get('KRAKEN_API_KEY'), os.environ.get('KRAKEN_API_SECRET'))
        ]
        
        for api_key, api_secret in sources:
            if api_key and api_secret:
                # Clean up credentials
                api_key = api_key.strip().replace('\r', '').replace('\n', '')
                api_secret = api_secret.strip().replace('\r', '').replace('\n', '')
                return api_key, api_secret
                
        return None, None
    except Exception as e:
        logger.error(f"Error getting API credentials: {e}")
        return None, None


def generate_signature(api_secret: str, data: str, nonce: str, path: str) -> str:
    """Generate API signature for authenticated requests."""
    path_for_sig = path.removeprefix("/derivatives")
    message = hashlib.sha256((data + nonce + path_for_sig).encode()).digest()
    signature = hmac.new(
        key=base64.b64decode(api_secret),
        msg=message,
        digestmod=hashlib.sha512
    ).digest()
    return base64.b64encode(signature).decode()


def _handle_api_response(data: Any, expected_field: str = None, 
                        empty_default: Any = None) -> Any:
    """
    Generic handler for API responses.
    
    Args:
        data: Response data
        expected_field: Field to extract from response
        empty_default: Default value if response is empty
        
    Returns:
        Processed response data
    """
    if not data:
        logger.warning("Empty response from API")
        return empty_default if empty_default is not None else {}
    
    # Check for API errors
    if isinstance(data, dict) and data.get("error"):
        raise KrakenAPIError(f"API returned error: {data['error']}")
    
    # If no specific field requested, return as-is
    if not expected_field:
        return data
    
    # Handle success response structure
    if isinstance(data, dict):
        if data.get("result") == "success" and expected_field in data:
            return data[expected_field]
        elif expected_field in data:
            return data[expected_field]
    
    logger.warning(f"Expected field '{expected_field}' not found in response")
    return empty_default if empty_default is not None else {}


def make_request(path: str, api_key: str, api_secret: str, 
                query: dict = None) -> dict:
    """Make an authenticated request to Kraken Futures API."""
    # Rate limiting
    _rate_limiter.wait_if_needed()
    
    url = f"https://futures.kraken.com{path}"
    
    # Prepare query string
    query_str = ""
    if query:
        query_str = urllib.parse.urlencode(query)
        url += "?" + query_str
    
    # Generate signature
    nonce = str(int(time.time() * 1000))
    authent = generate_signature(api_secret, query_str, nonce, path)
    
    # Headers
    headers = {
        "APIKey": api_key,
        "Authent": authent,
        "Nonce": nonce
    }
    
    try:
        logger.debug(f"Making request to {url}")
        
        # Make request
        req = urllib.request.Request(
            method="GET",
            url=url,
            headers=headers
        )
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
        
        # Log response structure for ticker endpoints
        if "/tickers/" in path:
            logger.debug(f"Ticker response structure: {json.dumps(data, indent=2)}")
        
        # Check for errors
        if data.get("result") == "error":
            error_msg = data.get("error", "Unknown API error")
            logger.error(f"API error response: {error_msg}")
            raise KrakenAPIError(f"API Error: {error_msg}")
        
        return data
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        logger.error(f"HTTP error {e.code}: {error_body}")
        raise KrakenAPIError(f"HTTP {e.code}: {error_body}")
    except urllib.error.URLError as e:
        logger.error(f"Network error: {str(e)}")
        raise KrakenAPIError(f"Network error: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        raise KrakenAPIError(f"Invalid JSON response: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise KrakenAPIError(f"Unexpected error: {str(e)}")


def _fetch_paginated_data(api_key: str, api_secret: str, endpoint: str,
                         since_ts: int, before_ts: int, 
                         query_params: dict = None,
                         response_field: str = "logs",
                         continuation_field: str = None,
                         max_iterations: int = 10) -> list:
    """
    Generic paginated data fetcher.
    
    Args:
        api_key: Kraken API key
        api_secret: Kraken API secret
        endpoint: API endpoint
        since_ts: Start timestamp
        before_ts: End timestamp
        query_params: Additional query parameters
        response_field: Field containing the data in response
        continuation_field: Field containing pagination token
        max_iterations: Maximum pagination iterations
        
    Returns:
        List of all fetched items
    """
    all_items = []
    current_before = before_ts
    continuation_token = None
    iteration = 0
    
    logger.info(f"Fetching {response_field} from {since_ts} to {before_ts}")
    
    while iteration < max_iterations:
        iteration += 1
        
        # Build query
        query = {"since": since_ts, "before": current_before}
        if query_params:
            query.update(query_params)
        if continuation_token and continuation_field:
            query[continuation_field] = continuation_token
        
        try:
            data = make_request(endpoint, api_key, api_secret, query)
            items = _handle_api_response(data, response_field, [])
            
            if not items:
                logger.info("No more items to fetch")
                break
            
            logger.info(f"Fetched {len(items)} items in iteration {iteration}")
            all_items.extend(items)
            
            # Check for continuation
            if continuation_field:
                continuation_token = data.get(continuation_field)
                if not continuation_token:
                    break
            else:
                # Use date-based pagination
                if len(items) < query.get("limit", 500):
                    break
                
                last_item = items[-1]
                last_date = last_item.get("date")
                if not last_date:
                    break
                
                new_before = int(datetime.strptime(
                    last_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                ).replace(tzinfo=timezone.utc).timestamp() * 1000)
                
                if new_before >= current_before:
                    break
                    
                current_before = new_before
                
        except KrakenAPIError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in pagination: {str(e)}")
            raise KrakenAPIError(f"Error fetching {response_field}: {str(e)}")
    
    logger.info(f"Total {response_field} fetched: {len(all_items)}")
    return all_items


# Public API Functions

def get_account_logs(api_key: str, api_secret: str, since_ts: int, 
                    before_ts: int, limit: int = 500, 
                    entry_type: Union[str, List[str]] = None) -> list:
    """Fetch account logs between timestamps."""
    query_params = {"limit": limit}
    if entry_type:
        query_params["entry_type"] = entry_type
    
    return _fetch_paginated_data(
        api_key, api_secret,
        "/api/history/v3/account-log",
        since_ts, before_ts,
        query_params=query_params,
        response_field="logs"
    )


def get_execution_events(api_key: str, api_secret: str, 
                        since_ts: int, before_ts: int) -> list:
    """Fetch execution events (trades) between timestamps."""
    return _fetch_paginated_data(
        api_key, api_secret,
        "/api/history/v3/executions",
        since_ts, before_ts,
        query_params={"sort": "asc"},
        response_field="elements",
        continuation_field="continuation_token"
    )


def get_open_positions(api_key: str, api_secret: str) -> list:
    """Fetch open positions from Kraken Futures API."""
    try:
        logger.info("Fetching open positions")
        data = make_request("/derivatives/api/v3/openpositions", api_key, api_secret)
        return _handle_api_response(data, "openPositions", [])
    except KrakenAPIError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching open positions: {str(e)}")
        raise KrakenAPIError(f"Error fetching open positions: {str(e)}")


def get_fills(api_key: str, api_secret: str, limit: int = 100) -> list:
    """Get recent fills using the /fills endpoint."""
    try:
        logger.info(f"Fetching {limit} recent fills")
        data = make_request(
            "/derivatives/api/v3/fills",
            api_key, api_secret,
            {"limit": limit}
        )
        return _handle_api_response(data, "fills", [])
    except KrakenAPIError:
        raise
    except Exception as e:
        logger.error(f"Error fetching fills: {str(e)}")
        raise KrakenAPIError(f"Error fetching fills: {str(e)}")


def find_true_position_open_time(api_key: str, api_secret: str, 
                                position_symbol: str, position_size: float, 
                                current_ts: int) -> int:
    """Find when a position was opened by looking at recent fills."""
    logger.info(f"Finding open time for {position_symbol} with current size {position_size}")
    
    fills = get_fills(api_key, api_secret, limit=100)
    
    if not fills:
        logger.warning(f"No fills found. Defaulting to 30 days ago.")
        return current_ts - (30 * 24 * 60 * 60 * 1000)
    
    # Track net position as we go back in time
    net_position = position_size
    symbol_fills = []
    
    # Filter and process fills for this symbol
    for fill in fills:
        if not isinstance(fill, dict):
            continue
            
        fill_symbol = fill.get('symbol', '').upper()
        fill_size = float(fill.get('size', 0))
        fill_side = fill.get('side', '').lower()
        fill_time = fill.get('fillTime')
        
        if fill_symbol == position_symbol.upper() and fill_size != 0 and fill_time:
            try:
                fill_ts = int(datetime.fromisoformat(
                    fill_time.replace('Z', '+00:00')
                ).timestamp() * 1000)
                
                fill_qty = fill_size if fill_side != 'sell' else -fill_size
                symbol_fills.append((fill_ts, fill_qty, fill))
            except (ValueError, TypeError):
                logger.warning(f"Could not parse fill time: {fill_time}")
                continue
    
    if not symbol_fills:
        logger.warning(f"No fills found for {position_symbol}. Defaulting to 30 days ago.")
        return current_ts - (30 * 24 * 60 * 60 * 1000)
    
    # Sort by timestamp (newest first)
    symbol_fills.sort(key=lambda x: x[0], reverse=True)
    
    # Calculate net position going backwards in time
    for ts, qty, _ in symbol_fills:
        net_position -= qty
        logger.debug(f"After fill at {datetime.fromtimestamp(ts/1000, tz=timezone.utc)}: "
                   f"qty={qty:.4f}, net_position={net_position:.4f}")
        
        if abs(net_position) < 0.0001:  # Close to zero
            logger.info(f"Found position open at {datetime.fromtimestamp(ts/1000, tz=timezone.utc)}")
            return ts
    
    # Use the oldest fill if we couldn't find exact opening
    oldest_ts = min(fill[0] for fill in symbol_fills)
    logger.info(f"Using oldest fill at {datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc)}")
    return oldest_ts


def get_position_accumulated_data(api_key: str, api_secret: str, position: dict) -> dict:
    """Calculate accumulated funding and fees for a position since it was opened."""
    try:
        current_ts = int(time.time() * 1000)
        symbol = position.get("symbol", "").upper()
        raw_position_size = float(position.get("size", 0))
        position_size = abs(raw_position_size)
        
        if not symbol or position_size == 0:
            return {
                "accumulated_funding": 0.0, 
                "accumulated_fees": 0.0, 
                "data_is_capped": False, 
                "error": "Missing symbol or size"
            }

        # Find true open time
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

        logger.info(f"Fetching logs for {symbol} from {datetime.fromtimestamp(fetch_from_ts/1000, tz=timezone.utc).date()}")
        
        # Fetch both funding and trade logs in a single API call
        all_logs = get_account_logs(
            api_key, api_secret, fetch_from_ts, current_ts,
            entry_type=[ENTRY_TYPE_FUNDING_RATE_CHANGE, ENTRY_TYPE_FUTURES_TRADE]
        )
        
        accumulated_funding = 0.0
        accumulated_fees = 0.0
        
        # Process logs
        for log in all_logs:
            log_contract = log.get("contract", "")
            entry_type_raw = log.get("info", "")
            
            if log_contract and symbol in log_contract.upper():
                if entry_type_raw == ENTRY_TYPE_FUNDING_RATE_CHANGE:
                    realized_funding = log.get('realized_funding')
                    if realized_funding is not None:
                        accumulated_funding += float(realized_funding)
                        
                elif entry_type_raw == ENTRY_TYPE_FUTURES_TRADE:
                    fee_value = log.get("fee")
                    if fee_value is not None:
                        accumulated_fees += abs(float(fee_value))
        
        logger.info(f"Position {symbol}: funding=${accumulated_funding:.2f}, fees=${accumulated_fees:.2f}")
        
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


def _make_simple_api_call(endpoint: str, api_key: str, api_secret: str,
                         expected_field: str = None) -> dict:
    """Make a simple API call and handle the response."""
    try:
        logger.info(f"Fetching {endpoint}")
        data = make_request(endpoint, api_key, api_secret)
        result = _handle_api_response(data, expected_field)
        logger.debug(f"Response from {endpoint}: {json.dumps(result, indent=2)}")
        return result
    except KrakenAPIError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching {endpoint}: {str(e)}")
        raise KrakenAPIError(f"Error fetching {endpoint}: {str(e)}")


def get_fee_schedule_volumes(api_key: str, api_secret: str) -> dict:
    """Get fee schedule volumes for the last 30 days."""
    return _make_simple_api_call("/derivatives/api/v3/feeschedules/volumes", 
                                api_key, api_secret)


def get_fee_schedules(api_key: str, api_secret: str) -> dict:
    """Get all fee schedules with taker and maker fee percentages."""
    return _make_simple_api_call("/derivatives/api/v3/feeschedules", 
                                api_key, api_secret)


# Cache for fee schedules
_fee_schedule_cache = {}
_fee_schedule_cache_lock = threading.Lock()
_fee_schedule_cache_ttl = 3600  # 1 hour TTL


def get_cached_fee_schedules(api_key: str, api_secret: str) -> dict:
    """Get fee schedules with caching."""
    cache_key = f"{api_key[:8]}..."
    
    with _fee_schedule_cache_lock:
        if cache_key in _fee_schedule_cache:
            cached_data, cached_time = _fee_schedule_cache[cache_key]
            if time.time() - cached_time < _fee_schedule_cache_ttl:
                logger.debug("Using cached fee schedules")
                return cached_data
    
    # Fetch fresh data
    logger.debug("Fetching fresh fee schedules")
    data = get_fee_schedules(api_key, api_secret)
    
    # Update cache
    with _fee_schedule_cache_lock:
        _fee_schedule_cache[cache_key] = (data, time.time())
    
    return data


def get_fee_info(api_key: str, api_secret: str) -> dict:
    """Get combined fee information including 30-day volume and current fee percentages."""
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_volumes = executor.submit(get_fee_schedule_volumes, api_key, api_secret)
            future_schedules = executor.submit(get_cached_fee_schedules, api_key, api_secret)
            
            volumes_data = future_volumes.result()
            schedules_data = future_schedules.result()
        
        result = {
            "volume_30d": 0.0,
            "maker_fee": 0.0,
            "taker_fee": 0.0,
            "fee_schedules": schedules_data
        }
        
        # Parse volume data
        if volumes_data:
            if "volumesByFeeSchedule" in volumes_data:
                volumes_dict = volumes_data["volumesByFeeSchedule"]
                if volumes_dict:
                    result["volume_30d"] = float(next(iter(volumes_dict.values())))
            elif "volume" in volumes_data:
                result["volume_30d"] = float(volumes_data["volume"])
        
        # Parse fee schedule data
        if schedules_data:
            schedules = schedules_data.get("feeSchedules", [])
            if schedules:
                current_schedule = schedules[0]
                tiers = current_schedule.get("tiers", [])
                
                # Find applicable tier based on volume
                applicable_tier = None
                for tier in tiers:
                    if result["volume_30d"] >= float(tier.get("usdVolume", 0)):
                        applicable_tier = tier
                    else:
                        break
                
                if applicable_tier:
                    result["maker_fee"] = float(applicable_tier.get("makerFee", 0)) / 100
                    result["taker_fee"] = float(applicable_tier.get("takerFee", 0)) / 100
                elif tiers:
                    # Use first tier if no applicable tier found
                    result["maker_fee"] = float(tiers[0].get("makerFee", 0)) / 100
                    result["taker_fee"] = float(tiers[0].get("takerFee", 0)) / 100
        
        logger.info(f"Fee info: volume={result['volume_30d']}, maker={result['maker_fee']*100:.4f}%, taker={result['taker_fee']*100:.4f}%")
        return result
        
    except Exception as e:
        logger.error(f"Error getting fee info: {str(e)}")
        raise KrakenAPIError(f"Error getting fee info: {str(e)}")


def batch_get_position_accumulated_data(api_key: str, api_secret: str, 
                                       positions: List[dict]) -> List[dict]:
    """Process multiple positions sequentially."""
    results = []
    
    for pos in positions:
        try:
            result = get_position_accumulated_data(api_key, api_secret, pos)
            result.update({
                'symbol': pos.get('symbol'),
                'size': pos.get('size')
            })
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing position {pos.get('symbol')}: {e}")
            results.append({
                'symbol': pos.get('symbol'),
                'size': pos.get('size'),
                'error': str(e),
                'accumulated_funding': 0.0,
                'accumulated_fees': 0.0
            })
    
    return results


def get_ticker(api_key: str, api_secret: str, symbol: str) -> dict:
    """Get ticker information for a symbol.
    
    The ticker endpoint returns fundingRate and fundingRatePrediction directly in the response.
    """
    try:
        logger.info(f"Fetching ticker data for {symbol}")
        data = make_request(f"/derivatives/api/v3/tickers/{symbol}", api_key, api_secret)
        
        # Log the raw response for debugging
        logger.debug(f"Raw ticker response: {json.dumps(data, indent=2)}")
        
        # The ticker data is returned nested under "ticker" key
        if data and data.get("result") == "success" and "ticker" in data:
            ticker_data = data["ticker"]
            logger.info(f"Ticker data for {symbol}: fundingRate={ticker_data.get('fundingRate')}, fundingRatePrediction={ticker_data.get('fundingRatePrediction')}")
            return ticker_data
        
        return {}
    except KrakenAPIError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching ticker for {symbol}: {str(e)}")
        raise KrakenAPIError(f"Error fetching ticker: {str(e)}")


def get_funding_rates(api_key: str, api_secret: str, symbol: str) -> dict:
    """Get current and predicted funding rates for a symbol.
    
    Returns:
        dict with 'current' and 'predicted' funding rates
    """
    try:
        ticker_data = get_ticker(api_key, api_secret, symbol)
        logger.debug(f"Ticker data for {symbol}: {json.dumps(ticker_data, indent=2)}")
        
        # Extract funding rates
        current_rate = ticker_data.get("fundingRate", 0)
        predicted_rate = ticker_data.get("fundingRatePrediction", 0)
        
        result = {
            "current": float(current_rate) if current_rate is not None else 0,
            "predicted": float(predicted_rate) if predicted_rate is not None else 0
        }
        
        logger.info(f"Funding rates for {symbol}: current={result['current']}, predicted={result['predicted']}")
        return result
        
    except Exception as e:
        logger.error(f"Error getting funding rates for {symbol}: {str(e)}")
        return {"current": 0, "predicted": 0}


def batch_get_tickers(api_key: str, api_secret: str, symbols: List[str]) -> Dict[str, dict]:
    """Fetch ticker data for multiple symbols."""
    tickers = {}
    
    for symbol in symbols:
        try:
            tickers[symbol] = get_ticker(api_key, api_secret, symbol)
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            tickers[symbol] = {"error": str(e)}
    
    return tickers


 