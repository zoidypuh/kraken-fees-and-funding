from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta, timezone
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
import warnings
warnings.filterwarnings('ignore')

from kraken_client import get_funding_rate, get_historical_funding, get_public_funding_rates, get_public_ticker

funding = Blueprint('funding', __name__, url_prefix='/api/funding')

@funding.route('/history/<symbol>')
def get_funding_history(symbol):
    """Get funding rate history for a symbol with statistics and predictions"""
    try:
        # Get current funding rate from public endpoint
        current_ticker = get_public_ticker(symbol)
        
        current_rate_data = None
        if current_ticker:
            current_rate_data = {
                'rate': current_ticker.get('fundingRate', 0),
                'next_funding_time': _format_time_until_next_funding()
            }
        
        # Get historical funding rates (last 30 days for analysis)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=30)
        
        # Fetch historical funding data from public endpoint
        historical_data = get_public_funding_rates(
            symbol=symbol,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )
        
        if not historical_data:
            return jsonify({
                'current': None,
                'history': [],
                'statistics': {
                    'accumulated7d': 0,
                    'accumulated30d': 0,
                    'accumulated365d': 0
                },
                'predictions': {
                    'predicted7d': 0,
                    'predicted30d': 0,
                    'predicted365d': 0
                }
            })
        
        # Get last 8 hours of data (funding happens every 8 hours)
        eight_hours_ago = end_time - timedelta(hours=8)
        last_8_hours = []
        
        for entry in historical_data:
            # Parse the timestamp properly
            entry_time_str = entry['timestamp']
            if isinstance(entry_time_str, str):
                # Remove 'Z' suffix and add timezone info
                entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
            else:
                # If it's already a datetime object
                entry_time = entry_time_str
                
            # Make end_time timezone aware if it isn't
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            if eight_hours_ago.tzinfo is None:
                eight_hours_ago = eight_hours_ago.replace(tzinfo=timezone.utc)
                
            if entry_time >= eight_hours_ago:
                last_8_hours.append({
                    'time': entry_time.strftime('%Y-%m-%d %H:%M UTC'),
                    'rate': float(entry.get('rate', 0))
                })
        
        # Sort by time descending (most recent first)
        last_8_hours.sort(key=lambda x: x['time'], reverse=True)
        
        # Calculate historical accumulated rates (absolute values)
        rates_7d = []
        rates_30d = []
        rates_365d = []  # We'll extrapolate for 365d
        
        # Make end_time timezone aware if it isn't
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        
        for entry in historical_data:
            # Parse the timestamp properly
            entry_time_str = entry['timestamp']
            if isinstance(entry_time_str, str):
                entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
            else:
                entry_time = entry_time_str
                
            rate = abs(float(entry.get('rate', 0)))  # Use absolute value
            
            days_ago = (end_time - entry_time).days
            
            if days_ago <= 7:
                rates_7d.append(rate)
            if days_ago <= 30:
                rates_30d.append(rate)
            rates_365d.append(rate)  # Collect all for extrapolation
        
        # Calculate accumulated rates (sum of absolute values)
        # Funding happens every hour (24 times per day)
        accumulated_7d = sum(rates_7d)
        accumulated_30d = sum(rates_30d)
        
        # Extrapolate for 365 days based on average hourly rate
        if rates_30d:
            avg_hourly_rate = accumulated_30d / (30 * 24)  # Average per hour
            accumulated_365d = avg_hourly_rate * 365 * 24  # 365 days * 24 hours
        else:
            accumulated_365d = 0
        
        # Prepare data for prediction model
        if len(historical_data) > 10:  # Need enough data for ARIMA
            # Create time series data
            funding_rates = [abs(float(entry['rate'])) for entry in historical_data]
            funding_rates.reverse()  # Make chronological
            
            # Predict future funding rates
            predictions = _predict_funding_rates(funding_rates)
        else:
            # Fallback: use simple average
            avg_rate = np.mean([abs(float(entry['rate'])) for entry in historical_data]) if historical_data else 0
            predictions = {
                'predicted7d': avg_rate * 24 * 7,  # 24 times per day * 7 days
                'predicted30d': avg_rate * 24 * 30,
                'predicted365d': avg_rate * 24 * 365
            }
        
        return jsonify({
            'current': current_rate_data,
            'history': last_8_hours,
            'statistics': {
                'accumulated7d': accumulated_7d,
                'accumulated30d': accumulated_30d,
                'accumulated365d': accumulated_365d
            },
            'predictions': predictions
        })
        
    except Exception as e:
        print(f"Error fetching funding history: {str(e)}")
        return jsonify({'error': str(e)}), 500


def _format_time_until_next_funding():
    """Calculate time until next funding (top of the next hour)"""
    now = datetime.now(timezone.utc)
    
    # Next funding is at the top of the next hour
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    
    time_until = next_hour - now
    minutes = int(time_until.total_seconds() // 60)
    
    return f"{minutes}m"


def _predict_funding_rates(historical_rates, periods_ahead=365*24):
    """Predict future funding rates using ARIMA model"""
    try:
        # Use ARIMA model for time series prediction
        # Parameters (p,d,q) = (1,0,1) work well for funding rates
        model = ARIMA(historical_rates, order=(1, 0, 1))
        model_fit = model.fit()
        
        # Make predictions
        forecast = model_fit.forecast(steps=periods_ahead)
        
        # Calculate accumulated predictions (absolute values)
        # Funding happens 24 times per day (every hour)
        predicted_7d = sum(abs(x) for x in forecast[:24*7])
        predicted_30d = sum(abs(x) for x in forecast[:24*30])
        predicted_365d = sum(abs(x) for x in forecast)
        
        return {
            'predicted7d': predicted_7d,
            'predicted30d': predicted_30d,
            'predicted365d': predicted_365d
        }
        
    except Exception as e:
        print(f"Error in ARIMA prediction: {str(e)}")
        # Fallback to simple moving average
        avg_rate = np.mean(historical_rates[-30:]) if len(historical_rates) > 30 else np.mean(historical_rates)
        return {
            'predicted7d': avg_rate * 24 * 7,
            'predicted30d': avg_rate * 24 * 30,
            'predicted365d': avg_rate * 24 * 365
        }


@funding.route('/predict/<symbol>')
def predict_funding(symbol):
    """Get funding rate predictions for a symbol"""
    try:
        days = int(request.args.get('days', 30))
        
        # Get historical data for prediction
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=max(days, 30))
        
        historical_data = get_public_funding_rates(
            symbol=symbol,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )
        
        if not historical_data or len(historical_data) < 10:
            return jsonify({
                'error': 'Insufficient historical data for prediction'
            }), 400
        
        # Prepare data
        funding_rates = [abs(float(entry['rate'])) for entry in historical_data]
        funding_rates.reverse()  # Make chronological
        
        # Get predictions
        predictions = _predict_funding_rates(funding_rates, periods_ahead=days*24)
        
        return jsonify({
            'symbol': symbol,
            'days': days,
            'predictions': predictions,
            'model': 'ARIMA(1,0,1)',
            'data_points_used': len(funding_rates)
        })
        
    except Exception as e:
        print(f"Error predicting funding rates: {str(e)}")
        return jsonify({'error': str(e)}), 500 