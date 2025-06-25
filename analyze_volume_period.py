#!/usr/bin/env python3
"""
Analyze the actual period Kraken uses for 30-day volume calculation.
Compares account logs volume with the official 30-day volume from fee info.
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import print as rprint

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from kraken_client import get_account_logs, get_fee_info, get_execution_events, KrakenAPIError

load_dotenv()
console = Console()

def analyze_volume_period(api_key: str, api_secret: str):
    """Find the actual period used for Kraken's 30-day volume calculation."""
    try:
        # First, get the official 30-day volume from Kraken
        console.print("\n[cyan]Fetching official 30-day volume from Kraken fee info...[/cyan]")
        fee_info = get_fee_info(api_key, api_secret)
        official_30d_volume = fee_info.get('volume_30d', 0)
        console.print(f"[green]Official 30-day volume: ${official_30d_volume:,.2f}[/green]")
        
        # Calculate 1% tolerance range
        tolerance = 0.01  # 1%
        min_volume = official_30d_volume * (1 - tolerance)
        max_volume = official_30d_volume * (1 + tolerance)
        console.print(f"[yellow]Target range (±1%): ${min_volume:,.2f} - ${max_volume:,.2f}[/yellow]")
        
        # Fetch account logs for a longer period (e.g., 35 days to be safe)
        current_ts = int(time.time() * 1000)
        start_ts = current_ts - (35 * 24 * 60 * 60 * 1000)
        
        console.print(f"\n[cyan]Fetching account logs for last 35 days...[/cyan]")
        logs = get_account_logs(
            api_key, api_secret, 
            start_ts, current_ts,
            entry_type=["futures trade"]
        )
        console.print(f"[green]Fetched {len(logs)} futures trade entries[/green]")
        
        # Also fetch execution events for accurate volumes
        console.print(f"\n[cyan]Fetching execution events for volume data...[/cyan]")
        exec_events = []
        try:
            exec_events = get_execution_events(api_key, api_secret, start_ts, current_ts)
            console.print(f"[green]Fetched {len(exec_events)} execution events[/green]")
        except Exception as e:
            console.print(f"[yellow]Could not fetch execution events: {e}[/yellow]")
        
        # Build execution map
        exec_map = {}
        if exec_events:
            for event in exec_events:
                exec_data = event.get('event', {}).get('execution', {}).get('execution', {})
                exec_id = exec_data.get('uid')
                if exec_id:
                    exec_map[exec_id] = exec_data
        
        # Process trades and calculate volumes
        trades = []
        for log in logs:
            if log.get('info') == 'futures trade' and log.get('fee') is not None:
                date_str = log.get('date', '')
                if not date_str:
                    continue
                
                try:
                    # Parse timestamp
                    trade_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    trade_ts = int(trade_time.timestamp() * 1000)
                    
                    # Get trade details
                    trade_price = log.get('trade_price', 0)
                    fee = abs(float(log.get('fee', 0)))
                    exec_id = log.get('execution')
                    
                    # Try to get volume
                    volume = 0
                    quantity = None
                    
                    if exec_id and exec_id in exec_map:
                        exec_data = exec_map[exec_id]
                        quantity = abs(float(exec_data.get('quantity', 0) or 0))
                        volume = float(exec_data.get('usdValue', 0) or 0)
                        if volume == 0 and quantity and trade_price:
                            volume = quantity * trade_price
                    elif trade_price and fee:
                        # Estimate volume from fee (assuming 0.04% taker fee)
                        estimated_qty = fee / (trade_price * 0.0004)
                        volume = estimated_qty * trade_price
                    
                    if volume > 0:
                        trades.append({
                            'timestamp': trade_ts,
                            'datetime': trade_time,
                            'volume': volume,
                            'fee': fee,
                            'price': trade_price,
                            'quantity': quantity
                        })
                        
                except Exception as e:
                    continue
        
        # Sort trades by timestamp (newest first)
        trades.sort(key=lambda x: x['timestamp'], reverse=True)
        console.print(f"\n[green]Found {len(trades)} trades with volume data[/green]")
        
        # Calculate cumulative volume starting from most recent
        console.print("\n[cyan]Calculating cumulative volume from most recent trades...[/cyan]")
        cumulative_volume = 0
        found_trade = None
        
        # Create a progress table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Trade #", justify="right", style="dim")
        table.add_column("Date/Time", style="cyan")
        table.add_column("Volume", justify="right", style="green")
        table.add_column("Cumulative", justify="right", style="blue")
        table.add_column("% of Target", justify="right", style="yellow")
        
        for i, trade in enumerate(trades):
            cumulative_volume += trade['volume']
            percentage = (cumulative_volume / official_30d_volume) * 100
            
            # Show every 50th trade or important ones
            if i % 50 == 0 or (min_volume <= cumulative_volume <= max_volume):
                table.add_row(
                    str(i + 1),
                    trade['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                    f"${trade['volume']:,.2f}",
                    f"${cumulative_volume:,.2f}",
                    f"{percentage:.2f}%"
                )
            
            # Check if we've reached the target range
            if min_volume <= cumulative_volume <= max_volume:
                found_trade = trade
                console.print(table)
                break
        
        if found_trade:
            console.print(f"\n[green]✓ Found matching trade![/green]")
            console.print(f"\nTrade that brought volume within 1% of target:")
            rprint({
                'timestamp': found_trade['timestamp'],
                'datetime': found_trade['datetime'].strftime('%Y-%m-%d %H:%M:%S UTC'),
                'volume': f"${found_trade['volume']:,.2f}",
                'cumulative_volume': f"${cumulative_volume:,.2f}",
                'official_volume': f"${official_30d_volume:,.2f}",
                'difference': f"${abs(cumulative_volume - official_30d_volume):,.2f}",
                'percentage': f"{(cumulative_volume / official_30d_volume * 100):.2f}%"
            })
            
            # Calculate time difference
            now = datetime.now(timezone.utc)
            time_diff = now - found_trade['datetime']
            days_diff = time_diff.total_seconds() / (24 * 60 * 60)
            
            console.print(f"\n[yellow]Time Analysis:[/yellow]")
            console.print(f"  Trade timestamp: {found_trade['datetime'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
            console.print(f"  Current time:    {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            console.print(f"  Time difference: {time_diff}")
            console.print(f"  [bold green]Days: {days_diff:.2f}[/bold green]")
            console.print(f"  Hours: {days_diff * 24:.1f}")
            
            # Additional insights
            console.print(f"\n[cyan]Insights:[/cyan]")
            if 29.5 <= days_diff <= 30.5:
                console.print("  ✓ Kraken appears to use a standard 30-day rolling window")
            elif 29 <= days_diff <= 29.5:
                console.print("  ⚠ Kraken might be using a slightly shorter period (~29.5 days)")
            elif 30.5 <= days_diff <= 31:
                console.print("  ⚠ Kraken might be using a slightly longer period (~30.5 days)")
            else:
                console.print(f"  ⚠ Unexpected period: {days_diff:.2f} days")
            
            # Check timezone effects
            trade_hour = found_trade['datetime'].hour
            console.print(f"\n  Trade occurred at {trade_hour}:00 UTC")
            if trade_hour == 0:
                console.print("  → Might indicate daily reset at midnight UTC")
            elif trade_hour in [4, 5]:
                console.print("  → Might indicate daily reset at midnight EST/EDT")
            elif trade_hour in [7, 8]:
                console.print("  → Might indicate daily reset at midnight PST/PDT")
            
        else:
            console.print("\n[red]✗ Could not find trades that match the official volume[/red]")
            console.print(f"Calculated total volume from {len(trades)} trades: ${cumulative_volume:,.2f}")
            console.print(f"This is {(cumulative_volume / official_30d_volume * 100):.2f}% of the official volume")
            
    except KrakenAPIError as e:
        console.print(f"[red]Kraken API Error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    api_key = os.getenv('KRAKEN_API_KEY')
    api_secret = os.getenv('KRAKEN_API_SECRET')
    
    if not api_key or not api_secret:
        console.print("[red]Error: API credentials not found in .env[/red]")
        sys.exit(1)
    
    analyze_volume_period(api_key, api_secret) 