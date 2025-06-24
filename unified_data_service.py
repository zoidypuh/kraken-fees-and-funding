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
        
        # Process logs by day
        daily_data = {}
        trades_list = []
        
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
                        daily_data[day_key]['fees'] += fee_amount
                        daily_data[day_key]['trade_count'] += 1
                        
                        # Get trade details
                        trade_price = log.get('trade_price', 0)
                        exec_id = log.get('execution')
                        
                        # Try to get quantity and volume
                        quantity = None
                        usd_volume = 0
                        
                        if exec_id and exec_id in exec_map:
                            exec_data = exec_map[exec_id]
                            quantity = abs(float(exec_data.get('quantity', 0) or 0))
                            usd_volume = float(exec_data.get('usdValue', 0) or 0)
                        elif trade_price and fee_amount:
                            # Estimate quantity from fee (assuming 0.04% taker fee)
                            quantity = fee_amount / (trade_price * 0.0004)
                            usd_volume = quantity * trade_price
                        
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


# Global instance
unified_data_service = UnifiedDataService() 