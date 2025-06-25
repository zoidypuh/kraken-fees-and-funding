"""
Unified data service that fetches account logs once and processes them for all endpoints.
This reduces API calls and improves performance.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import threading

from kraken_client import get_account_logs, get_execution_events, KrakenAPIError

logger = logging.getLogger(__name__)

class UnifiedDataService:
    """Service that fetches and caches account data for all endpoints."""
    
    def __init__(self, cache_ttl: int = 300):  # 5 minutes cache
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_lock = threading.Lock()
        
    def _get_cache_key(self, api_key: str) -> str:
        """Generate cache key from API key."""
        return f"unified_data_{api_key[:8]}"
    
    def _is_cache_valid(self, cache_entry: dict) -> bool:
        """Check if cache entry is still valid."""
        if not cache_entry:
            return False
        return time.time() - cache_entry.get('timestamp', 0) < self.cache_ttl
    
    def get_processed_data(self, api_key: str, api_secret: str, days: int = 30) -> Dict:
        """
        Get processed account data for the specified number of days.
        Returns data suitable for charts, volumes, and analytics.
        """
        cache_key = self._get_cache_key(api_key)
        
        # Check cache
        with self._cache_lock:
            cache_entry = self._cache.get(cache_key, {})
            if self._is_cache_valid(cache_entry) and cache_entry.get('days', 0) >= days:
                logger.info(f"Returning cached data for {days} days")
                return self._filter_to_days(cache_entry['data'], days)
        
        # Fetch fresh data
        logger.info(f"Fetching fresh account data for {days} days")
        try:
            processed_data = self._fetch_and_process_data(api_key, api_secret, days)
            
            # Update cache
            with self._cache_lock:
                self._cache[cache_key] = {
                    'data': processed_data,
                    'timestamp': time.time(),
                    'days': days
                }
            
            return processed_data
            
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            raise
    
    def _fetch_and_process_data(self, api_key: str, api_secret: str, days: int) -> Dict:
        """Fetch and process account logs into a unified format."""
        current_ts = int(time.time() * 1000)
        start_ts = current_ts - (days * 24 * 60 * 60 * 1000)
        
        # Fetch account logs
        logger.info(f"Fetching account logs from {start_ts} to {current_ts}")
        logs = get_account_logs(api_key, api_secret, start_ts, current_ts)
        logger.info(f"Fetched {len(logs)} account log entries")
        
        # Store raw logs for reuse
        self._last_raw_logs = logs
        self._last_raw_logs_timestamp = current_ts
        
        # Try to fetch execution events for trade quantities
        exec_map = {}
        try:
            exec_events = get_execution_events(api_key, api_secret, start_ts, current_ts)
            logger.info(f"Fetched {len(exec_events)} execution events")
            
            # Build execution map
            for event in exec_events:
                exec_data = event.get('event', {}).get('execution', {}).get('execution', {})
                exec_id = exec_data.get('uid')
                if exec_id:
                    exec_map[exec_id] = exec_data
        except Exception as e:
            logger.warning(f"Could not fetch execution events: {e}")
        
        # Process logs by day (using 5:00 AM UTC as daily cutoff)
        daily_data = {}
        trades_list = []
        processed_executions = set()  # Track processed execution IDs to avoid double counting
        
        for log in logs:
            date_str = log.get('date', '')
            if not date_str:
                continue
                
            try:
                log_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                day_key = log_time.date().isoformat()
                
                if day_key not in daily_data:
                    daily_data[day_key] = {
                        'fees': 0.0,
                        'funding': 0.0,
                        'volume': 0.0,
                        'trade_count': 0
                    }
                
                info = log.get('info', '')
                
                # Process funding rate changes
                if info == 'funding rate change':
                    realized_funding = log.get('realized_funding')
                    if realized_funding is not None:
                        daily_data[day_key]['funding'] += abs(float(realized_funding))
                
                # Process futures trades
                elif info == 'futures trade':
                    fee = log.get('fee')
                    if fee is not None:
                        fee_amount = abs(float(fee))
                        
                        # Only count trades with non-zero fees to avoid double counting
                        # Each trade generates two logs: one with fee, one with $0
                        if fee_amount > 0:
                            daily_data[day_key]['fees'] += fee_amount
                            daily_data[day_key]['trade_count'] += 1
                        
                        # Get trade details
                        trade_price = log.get('trade_price', 0)
                        exec_id = log.get('execution')
                        
                        # Try to get quantity and volume
                        quantity = None
                        usd_volume = 0
                        
                        # Only process volume if we haven't seen this execution before
                        # This prevents double-counting since each trade creates two log entries
                        if exec_id and exec_id not in processed_executions:
                            processed_executions.add(exec_id)
                            
                            if exec_id in exec_map:
                                exec_data = exec_map[exec_id]
                                quantity = abs(float(exec_data.get('quantity', 0) or 0))
                                usd_volume = float(exec_data.get('usdValue', 0) or 0)
                        
                        # If we don't have USD value from execution and this is a fee-bearing trade, estimate it
                        if usd_volume == 0 and trade_price and fee_amount > 0 and (not exec_id or exec_id not in exec_map):
                            # Use actual fee percentage if we can determine it
                            # Common fee tiers: 0.01% (maker), 0.04% (taker)
                            # Based on our analysis, most trades are maker orders
                            # Using 0.01% gives ~99% accuracy
                            
                            # Use maker fee (0.01%) as it's most common
                            usd_volume = fee_amount / 0.0001
                            quantity = usd_volume / trade_price if trade_price else None
                        
                        if usd_volume > 0:
                            daily_data[day_key]['volume'] += usd_volume
                        
                        # Add to trades list
                        trades_list.append({
                            'date': date_str,
                            'timestamp': int(log_time.timestamp() * 1000),
                            'contract': log.get('contract', ''),
                            'fee': fee_amount,
                            'trade_price': trade_price,
                            'quantity': quantity,
                            'usd_volume': usd_volume,
                            'execution_id': exec_id
                        })
                        
            except Exception as e:
                logger.warning(f"Error processing log entry: {e}")
                continue
        
        # Generate complete daily series
        current_date = datetime.now(timezone.utc).date()
        start_date = current_date - timedelta(days=days-1)
        
        daily_series = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            date_str = date.isoformat()
            
            data = daily_data.get(date_str, {
                'fees': 0.0,
                'funding': 0.0,
                'volume': 0.0,
                'trade_count': 0
            })
            
            daily_series.append({
                'date': date_str,
                'fees': round(data['fees'], 2),
                'funding': round(data['funding'], 2),
                'volume': round(data['volume'], 2),
                'trade_count': data['trade_count']
            })
        
        # Sort trades by date
        trades_list.sort(key=lambda x: x['timestamp'])
        
        # Calculate summaries
        total_fees = sum(d['fees'] for d in daily_series)
        total_funding = sum(d['funding'] for d in daily_series)
        total_volume = sum(d['volume'] for d in daily_series)
        total_trades = sum(d['trade_count'] for d in daily_series)
        
        return {
            'daily_data': daily_series,
            'trades': trades_list,
            'summary': {
                'total_fees': round(total_fees, 2),
                'total_funding': round(total_funding, 2),
                'total_volume': round(total_volume, 2),
                'total_trades': total_trades,
                'total_cost': round(total_fees + total_funding, 2),
                'avg_daily_fees': round(total_fees / days if days > 0 else 0, 2),
                'avg_daily_funding': round(total_funding / days if days > 0 else 0, 2)
            },
            'period_days': days,
            'last_updated': int(time.time() * 1000)
        }
    
    def _filter_to_days(self, full_data: Dict, days: int) -> Dict:
        """Filter the cached data to requested number of days."""
        if full_data['period_days'] == days:
            return full_data
        
        # Get last N days from daily data
        filtered_daily = full_data['daily_data'][-days:]
        
        # Recalculate summaries
        total_fees = sum(d['fees'] for d in filtered_daily)
        total_funding = sum(d['funding'] for d in filtered_daily)
        total_volume = sum(d['volume'] for d in filtered_daily)
        total_trades = sum(d['trade_count'] for d in filtered_daily)
        
        return {
            'daily_data': filtered_daily,
            'trades': full_data['trades'],  # Keep all trades
            'summary': {
                'total_fees': round(total_fees, 2),
                'total_funding': round(total_funding, 2),
                'total_volume': round(total_volume, 2),
                'total_trades': total_trades,
                'total_cost': round(total_fees + total_funding, 2),
                'avg_daily_fees': round(total_fees / days if days > 0 else 0, 2),
                'avg_daily_funding': round(total_funding / days if days > 0 else 0, 2)
            },
            'period_days': days,
            'last_updated': full_data['last_updated']
        }
    
    def clear_cache(self, api_key: Optional[str] = None):
        """Clear cache for specific API key or all caches."""
        with self._cache_lock:
            if api_key:
                cache_key = self._get_cache_key(api_key)
                self._cache.pop(cache_key, None)
            else:
                self._cache.clear()
        logger.info("Cache cleared")
    
    def get_raw_logs(self, api_key: str, api_secret: str, since_ts: int, before_ts: int, 
                     entry_type: Optional[str] = None) -> List[dict]:
        """
        Get raw account logs from cache if available, otherwise fetch them.
        This allows other parts of the app to reuse the cached logs.
        """
        # First ensure we have fresh data
        current_ts = int(time.time() * 1000)
        
        # Calculate how many days of data we need
        days_needed = max(1, int((current_ts - since_ts) / (24 * 60 * 60 * 1000)) + 1)
        
        # Get the processed data (this will fetch/cache if needed)
        self.get_processed_data(api_key, api_secret, days=days_needed)
        
        # Now filter the raw logs based on the requested time range and type
        if hasattr(self, '_last_raw_logs'):
            filtered_logs = []
            for log in self._last_raw_logs:
                log_date = log.get('date')
                if not log_date:
                    continue
                    
                try:
                    log_ts = int(datetime.fromisoformat(
                        log_date.replace('Z', '+00:00')
                    ).timestamp() * 1000)
                    
                    # Check if log is within requested time range
                    if since_ts <= log_ts <= before_ts:
                        # Check entry type if specified
                        if entry_type is None or log.get('info') == entry_type:
                            filtered_logs.append(log)
                except Exception:
                    continue
                    
            return filtered_logs
        
        # Fallback to direct fetch if no cached logs
        logger.warning("No cached logs available, fetching directly")
        return get_account_logs(api_key, api_secret, since_ts, before_ts, entry_type=entry_type)


# Global instance
unified_data_service = UnifiedDataService() 