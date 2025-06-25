#!/usr/bin/env python3
"""Script to check volume calculation accuracy against Kraken's official numbers."""

import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from unified_data_service import UnifiedDataService
from kraken_client import get_fee_schedule_volumes
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()

console = Console()

def check_volume_accuracy():
    """Compare our calculated volume with Kraken's official 30-day volume."""
    api_key = os.getenv('KRAKEN_API_KEY')
    api_secret = os.getenv('KRAKEN_API_SECRET')
    
    if not api_key or not api_secret:
        console.print("[red]KRAKEN_API_KEY and KRAKEN_API_SECRET must be set in .env file[/red]")
        return
    
    # Ensure credentials are cleaned
    api_key = api_key.strip()
    api_secret = api_secret.strip()
    
    console.print("\n[bold]Checking Volume Calculation Accuracy[/bold]\n")
    
    # Get official Kraken 30-day volume
    console.print("Fetching official Kraken 30-day volume...", style="cyan")
    try:
        fee_data = get_fee_schedule_volumes(api_key, api_secret)
        official_volume = 0.0
        
        if "volumesByFeeSchedule" in fee_data:
            volumes_dict = fee_data["volumesByFeeSchedule"]
            if volumes_dict:
                official_volume = float(next(iter(volumes_dict.values())))
        elif "volume" in fee_data:
            official_volume = float(fee_data["volume"])
            
        console.print(f"Official 30-day volume: [green]${official_volume:,.2f}[/green]\n")
    except Exception as e:
        console.print(f"[red]Error fetching official volume: {e}[/red]")
        return
    
    # Calculate volume using our unified data service
    console.print("Calculating volume using unified data service...", style="cyan")
    service = UnifiedDataService()
    
    # Get data for exactly 30 days
    data = service.get_processed_data(api_key, api_secret, days=30)
    
    # Sum up volumes
    calculated_volume = 0.0
    daily_volumes = {}
    
    volumes_data = data.get('daily_data', [])
    for day_data in volumes_data:
        date = day_data['date']
        volume = day_data['volume']
        calculated_volume += volume
        daily_volumes[date] = volume
    
    console.print(f"Calculated 30-day volume: [yellow]${calculated_volume:,.2f}[/yellow]\n")
    
    # Calculate accuracy
    difference = calculated_volume - official_volume
    percentage_diff = (difference / official_volume * 100) if official_volume > 0 else 0
    accuracy = 100 - abs(percentage_diff)
    
    # Display comparison
    comparison_table = Table(title="Volume Comparison", show_header=True)
    comparison_table.add_column("Metric", style="cyan")
    comparison_table.add_column("Value", style="white", justify="right")
    
    comparison_table.add_row("Official Kraken Volume", f"${official_volume:,.2f}")
    comparison_table.add_row("Calculated Volume", f"${calculated_volume:,.2f}")
    comparison_table.add_row("Difference", f"${difference:,.2f}")
    comparison_table.add_row("Percentage Difference", f"{percentage_diff:+.2f}%")
    comparison_table.add_row("Accuracy", f"{accuracy:.2f}%")
    
    console.print(comparison_table)
    console.print()
    
    # Show daily breakdown for last 7 days
    console.print("[bold]Daily Volume Breakdown (Last 7 Days)[/bold]")
    daily_table = Table(show_header=True)
    daily_table.add_column("Date", style="cyan")
    daily_table.add_column("Volume", style="green", justify="right")
    daily_table.add_column("Trades", style="yellow", justify="center")
    
    # Sort and show last 7 days
    sorted_days = sorted(volumes_data, key=lambda x: x['date'], reverse=True)[:7]
    
    for day_data in sorted_days:
        daily_table.add_row(
            day_data['date'],
            f"${day_data['volume']:,.2f}",
            str(day_data['trade_count'])
        )
    
    console.print(daily_table)
    
    # Analysis notes
    notes = []
    if abs(percentage_diff) > 1:
        notes.append(f"⚠️  Volume difference exceeds 1% ({percentage_diff:+.2f}%)")
    
    if accuracy >= 99:
        notes.append("✅ Excellent accuracy (≥99%)")
    elif accuracy >= 95:
        notes.append("👍 Good accuracy (≥95%)")
    else:
        notes.append("❌ Poor accuracy (<95%)")
    
    if notes:
        console.print("\n[bold]Analysis:[/bold]")
        for note in notes:
            console.print(f"  {note}")
    
    # Additional debugging info
    console.print("\n[dim]Debug Information:[/dim]")
    console.print(f"  • Daily cutoff: Midnight UTC")
    console.print(f"  • Number of days with data: {len(volumes_data)}")
    console.print(f"  • Total trades in period: {sum(d['trade_count'] for d in volumes_data)}")
    
    # Check if we're missing days
    if len(volumes_data) < 30:
        console.print(f"  • [yellow]Warning: Only {len(volumes_data)} days of data (expected 30)[/yellow]")

if __name__ == "__main__":
    check_volume_accuracy() 