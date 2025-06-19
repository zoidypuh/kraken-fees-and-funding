"""
Async Kraken Futures API client for improved performance.
"""
import json
import hashlib
import hmac
import base64
import time
import logging
import asyncio
import aiohttp
from typing import List, Dict, Optional
from datetime import datetime, timezone

from kraken_client import KrakenAPIError, get_signature, FUTURES_BASE_URL, MAX_RETRIES, INITIAL_RETRY_DELAY

# Configure logging
logger = logging.getLogger(__name__)


async def make_async_request(session: aiohttp.ClientSession, path: str, api_key: str, api_secret: str, query: dict = None) -> dict:
    """
    Make authenticated async request to Kraken Futures API with retry logic.
    """
    url = f"{FUTURES_BASE_URL}{path}"
    
    # Prepare query string
    query = query or {}
    query_str = "&".join(f"{k}={v}" for k, v in query.items()) if query else ""
    
    if query_str:
        url += f"?{query_str}"
    
    # Retry logic with exponential backoff
    retry_delay = INITIAL_RETRY_DELAY
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            # Generate nonce for this attempt
            nonce = str(int(time.time() * 1000))
            
            # Prepare headers
            headers = {
                "APIKey": api_key,
                "Authent": get_signature(api_secret, query_str, nonce, path),
                "Nonce": nonce
            }
            
            # Make the async request
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                
                # Check for API errors in response
                if "error" in data and data["error"]:
                    raise KrakenAPIError(f"API Error: {data['error']}")
                
                return data
                
        except aiohttp.ClientResponseError as e:
            # Check if it's a rate limit error
            if e.status == 429:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Rate limit hit, retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
            
            last_error = f"HTTP Error {e.status}: {e.message}"
            
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            last_error = str(e)
        
        # If we get here and it's not the last attempt, retry with backoff
        if attempt < MAX_RETRIES - 1:
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
    
    # All retries exhausted
    raise KrakenAPIError(f"Request failed after {MAX_RETRIES} attempts: {last_error}")


async def get_account_logs_async(session: aiohttp.ClientSession, api_key: str, api_secret: str, since_ts: int, before_ts: int) -> list:
    """
    Async version of get_account_logs.
    """
    all_logs = []
    current_before = before_ts
    max_iterations = 10
    iteration = 0
    
    logger.info(f"[Async] Fetching logs from {since_ts} to {before_ts}")
    
    while iteration < max_iterations:
        iteration += 1
        
        try:
            data = await make_async_request(
                session,
                "/api/history/v3/account-log",
                api_key,
                api_secret,
                {"limit": 500, "since": since_ts, "before": current_before}
            )
            
            logs = data.get("logs", []) if isinstance(data, dict) else data
            
            if not logs:
                break
            
            logger.info(f"[Async] Fetched {len(logs)} log entries in iteration {iteration}")
            all_logs.extend(logs)
            
            if len(logs) < 500:
                break
                
            # Get the date of the oldest log for pagination
            last_log = logs[-1]
            last_date = last_log.get("date")
            
            if not last_date:
                break
                
            new_before = int(datetime.strptime(last_date, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            
            if new_before >= current_before:
                break
                
            current_before = new_before
            
        except Exception as e:
            logger.error(f"[Async] Error in pagination: {str(e)}")
            raise
    
    logger.info(f"[Async] Total logs fetched: {len(all_logs)}")
    return all_logs


async def get_execution_events_async(session: aiohttp.ClientSession, api_key: str, api_secret: str, since_ts: int, before_ts: int) -> list:
    """
    Async version of get_execution_events.
    """
    all_executions = []
    continuation_token = None
    
    logger.info(f"[Async] Fetching execution events from {since_ts} to {before_ts}")
    
    while True:
        try:
            query = {
                "since": since_ts,
                "before": before_ts,
                "sort": "asc"
            }
            
            if continuation_token:
                query["continuation_token"] = continuation_token
            
            data = await make_async_request(
                session,
                "/api/history/v3/executions",
                api_key,
                api_secret,
                query
            )
            
            executions = data.get("executions") or data.get("elements") or []
            
            if not executions:
                break
            
            logger.info(f"[Async] Fetched {len(executions)} execution events")
            all_executions.extend(executions)
            
            continuation_token = data.get("continuationToken") or data.get("continuation_token")
            if not continuation_token:
                break
                
        except Exception as e:
            logger.error(f"[Async] Error fetching executions: {str(e)}")
            raise
    
    logger.info(f"[Async] Total execution events fetched: {len(all_executions)}")
    return all_executions


async def fetch_data_parallel_async(api_key: str, api_secret: str, since_ts: int, before_ts: int):
    """
    Fetch execution events and account logs in parallel using async/await.
    """
    async with aiohttp.ClientSession() as session:
        # Create tasks for parallel execution
        tasks = [
            get_execution_events_async(session, api_key, api_secret, since_ts, before_ts),
            get_account_logs_async(session, api_key, api_secret, since_ts, before_ts)
        ]
        
        # Execute tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        executions = []
        logs = []
        errors = []
        
        # Process results
        if isinstance(results[0], Exception):
            errors.append(f"Error fetching executions: {str(results[0])}")
        else:
            executions = results[0]
            
        if isinstance(results[1], Exception):
            errors.append(f"Error fetching logs: {str(results[1])}")
        else:
            logs = results[1]
        
        return executions, logs, errors 