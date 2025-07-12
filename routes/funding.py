from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
import warnings
warnings.filterwarnings('ignore')

from kraken_client import get_funding_rate, get_historical_funding, get_public_funding_rates, get_public_ticker

funding = Blueprint('funding', __name__)

@funding.route('/funding/history/<symbol>')
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
        end_time = datetime.utcnow()
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
            entry_time = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
            if entry_time >= eight_hours_ago:
                last_8_hours.append({
                    'time': entry_time.strftime('%Y-%m-%d %H:%M UTC'),
                    'rate': float(entry['rate'])
                })
        
        # Sort by time descending (most recent first)
        last_8_hours.sort(key=lambda x: x['time'], reverse=True)
        
        # Calculate historical accumulated rates (absolute values)
        rates_7d = []
        rates_30d = []
        rates_365d = []  # We'll extrapolate for 365d
        
        for entry in historical_data:
            entry_time = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
            rate = abs(float(entry['rate']))  # Use absolute value
            
            days_ago = (end_time - entry_time).days
            
            if days_ago <= 7:
                rates_7d.append(rate)
            if days_ago <= 30:
                rates_30d.append(rate)
            rates_365d.append(rate)  # Collect all for extrapolation
        
        # Calculate accumulated rates (sum of absolute values)
        # Funding happens 3 times per day (every 8 hours)
        accumulated_7d = sum(rates_7d)
        accumulated_30d = sum(rates_30d)
        
        # Extrapolate for 365 days based on average daily rate
        if rates_30d:
            avg_daily_rate = (accumulated_30d / 30) * 3  # 3 funding periods per day
            accumulated_365d = avg_daily_rate * 365 / 3
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
                'predicted7d': avg_rate * 3 * 7,  # 3 times per day * 7 days
                'predicted30d': avg_rate * 3 * 30,
                'predicted365d': avg_rate * 3 * 365
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
    """Calculate time until next funding (0:00, 8:00, or 16:00 UTC)"""
    now = datetime.utcnow()
    current_hour = now.hour
    
    # Funding times are 0:00, 8:00, 16:00 UTC
    if current_hour < 8:
        next_funding_hour = 8
    elif current_hour < 16:
        next_funding_hour = 16
    else:
        next_funding_hour = 0
    
    if next_funding_hour == 0:
        # Next funding is tomorrow at 00:00
        next_funding = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        # Next funding is today
        next_funding = now.replace(hour=next_funding_hour, minute=0, second=0, microsecond=0)
    
    time_until = next_funding - now
    hours = int(time_until.total_seconds() // 3600)
    minutes = int((time_until.total_seconds() % 3600) // 60)
    
    return f"{hours}h {minutes}m"


def _predict_funding_rates(historical_rates, periods_ahead=365*3):
    """Predict future funding rates using ARIMA model"""
    try:
        # Use ARIMA model for time series prediction
        # Parameters (p,d,q) = (1,0,1) work well for funding rates
        model = ARIMA(historical_rates, order=(1, 0, 1))
        model_fit = model.fit()
        
        # Make predictions
        forecast = model_fit.forecast(steps=periods_ahead)
        
        # Calculate accumulated predictions (absolute values)
        # Funding happens 3 times per day
        predicted_7d = sum(abs(x) for x in forecast[:3*7])
        predicted_30d = sum(abs(x) for x in forecast[:3*30])
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
            'predicted7d': avg_rate * 3 * 7,
            'predicted30d': avg_rate * 3 * 30,
            'predicted365d': avg_rate * 3 * 365
        }


@funding.route('/funding/predict/<symbol>')
def predict_funding(symbol):
    """Get funding rate predictions for a symbol"""
    try:
        days = int(request.args.get('days', 30))
        
        # Get historical data for prediction
        end_time = datetime.utcnow()
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
        predictions = _predict_funding_rates(funding_rates, periods_ahead=days*3)
        
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