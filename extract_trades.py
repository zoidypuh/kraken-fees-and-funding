#!/usr/bin/env python3
"""
Extract and display the last 30 futures trades from Kraken account logs.
Shows: Date, Contract, Quantity, Trade Price, Fee
"""
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import print as rprint

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from kraken_client import get_account_logs, get_execution_events, KrakenAPIError

load_dotenv()
console = Console()

def get_trade_quantity(api_key: str, api_secret: str, execution_id: str, start_ts: int, end_ts: int):
    """Try to get trade quantity from execution events."""
    try:
        # Fetch execution events for the time period
        executions = get_execution_events(api_key, api_secret, start_ts, end_ts)
        
        # Look for matching execution
        for exec_event in executions:
            event = exec_event.get('event', {})
            exec_data = event.get('execution', {}).get('execution', {})
            
            if exec_data.get('uid') == execution_id:
                return abs(float(exec_data.get('quantity', 0) or 0))
        
        return None
    except:
        return None

def extract_futures_trades(api_key: str, api_secret: str, days: int = 30):
    """Extract and display the last 30 futures trades."""
    try:
        current_ts = int(time.time() * 1000)
        start_ts = current_ts - (days * 24 * 60 * 60 * 1000)
        
        console.print(f"\n[cyan]Fetching futures trades for the last {days} days...[/cyan]")
        
        # Fetch logs filtered by futures trade
        logs = get_account_logs(
            api_key, api_secret, 
            start_ts, current_ts,
            entry_type=["futures trade"]
        )
        
        console.print(f"[green]Found {len(logs)} futures trade entries[/green]")
        
        # Filter for actual trades with fees
        trades = []
        for log in logs:
            if log.get('info') == 'futures trade' and log.get('fee') is not None:
                trades.append(log)
        
        console.print(f"[green]Found {len(trades)} trades with fees[/green]")
        
        # Sort by date and take last 30
        trades.sort(key=lambda x: x.get('date', ''))
        last_30_trades = trades[-30:]
        
        # Try to fetch execution events for quantity data
        console.print("[cyan]Fetching execution details for quantities...[/cyan]")
        exec_events = None
        try:
            exec_events = get_execution_events(api_key, api_secret, start_ts, current_ts)
            console.print(f"[green]Fetched {len(exec_events)} execution events[/green]")
        except Exception as e:
            console.print(f"[yellow]Could not fetch execution events: {e}[/yellow]")
        
        # Build execution map if we have events
        exec_map = {}
        if exec_events:
            for exec_event in exec_events:
                event = exec_event.get('event', {})
                exec_data = event.get('execution', {}).get('execution', {})
                exec_id = exec_data.get('uid')
                if exec_id:
                    exec_map[exec_id] = exec_data
        
        # Display trades table
        table = Table(show_header=True, header_style="bold magenta", title="Last 30 Futures Trades")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Date", style="cyan")
        table.add_column("Contract", style="yellow")
        table.add_column("Quantity", justify="right", style="green")
        table.add_column("Trade Price", justify="right", style="blue")
        table.add_column("Fee", justify="right", style="red")
        table.add_column("USD Value", justify="right", style="magenta")
        
        total_fees = 0
        total_volume = 0
        
        for idx, trade in enumerate(last_30_trades, 1):
            date_str = trade.get('date', '')
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
            
            contract = trade.get('contract', 'N/A').upper()
            trade_price = trade.get('trade_price', 0)
            fee = abs(float(trade.get('fee', 0)))
            
            # Try to get quantity from execution map
            quantity = None
            exec_id = trade.get('execution')
            if exec_id and exec_id in exec_map:
                exec_data = exec_map[exec_id]
                quantity = abs(float(exec_data.get('quantity', 0) or 0))
                # Also check for USD value in execution
                usd_value = float(exec_data.get('usdValue', 0) or 0)
            else:
                # Estimate quantity from fee if we have a fee rate
                # Assuming 0.04% taker fee as default
                if trade_price and fee:
                    estimated_qty = fee / (trade_price * 0.0004)
                    quantity = estimated_qty
                    usd_value = quantity * trade_price
                else:
                    usd_value = 0
            
            # Format values
            quantity_str = f"{quantity:.6f}" if quantity else "N/A"
            price_str = f"${trade_price:,.2f}" if trade_price else "N/A"
            fee_str = f"${fee:.6f}"
            usd_str = f"${usd_value:,.2f}" if usd_value else "N/A"
            
            total_fees += fee
            if usd_value:
                total_volume += usd_value
            
            table.add_row(str(idx), date_str, contract, quantity_str, price_str, fee_str, usd_str)
        
        console.print(table)
        
        # Summary
        console.print(f"\n[yellow]Summary:[/yellow]")
        console.print(f"  Total Fees Paid: [red]${total_fees:.4f}[/red]")
        console.print(f"  Total Volume: [green]${total_volume:,.2f}[/green]")
        console.print(f"  Average Fee per Trade: [red]${total_fees/len(last_30_trades):.4f}[/red]")
        
        # Show raw data for the most recent trade
        if last_30_trades:
            console.print(f"\n[yellow]Most Recent Trade (Raw Data):[/yellow]")
            recent_trade = last_30_trades[-1]
            exec_id = recent_trade.get('execution')
            
            # Show trade log
            console.print("\n[cyan]Trade Log Entry:[/cyan]")
            rprint({
                'date': recent_trade.get('date'),
                'contract': recent_trade.get('contract'),
                'trade_price': recent_trade.get('trade_price'),
                'fee': recent_trade.get('fee'),
                'execution_id': exec_id,
                'mark_price': recent_trade.get('mark_price')
            })
            
            # Show execution details if available
            if exec_id and exec_id in exec_map:
                console.print("\n[cyan]Execution Details:[/cyan]")
                rprint(exec_map[exec_id])
            
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
    
    extract_futures_trades(api_key, api_secret, days=30) 