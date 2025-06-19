"""
API Blueprint for Kraken Dashboard
Handles all API endpoints for data fetching and credential management.
"""
from flask import Blueprint, jsonify, request as flask_request, make_response
import time
import logging

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Import necessary functions from main app
# These will be injected when blueprint is registered
logger = logging.getLogger(__name__)


def init_api_blueprint(app, limiter, cache, get_chart_data, get_open_positions_data, 
                      process_chart_data, get_period_boundaries, get_cache_key,
                      get_execution_events, KrakenAPIError, require_api_credentials):
    """Initialize the API blueprint with app dependencies."""
    
    @api_bp.route('/data')
    @require_api_credentials
    @limiter.limit("30 per minute")
    def get_data(api_key, api_secret):
        """API endpoint to fetch chart data."""
        try:
            days = int(flask_request.args.get('days', 30))
            
            if days < 1 or days > 365:
                return jsonify({'error': 'Days parameter must be between 1 and 365'}), 400
            
            data = get_chart_data(api_key, api_secret, days)
            positions = get_open_positions_data(api_key, api_secret)
            data['positions'] = positions
            
            return jsonify(data)
            
        except KrakenAPIError as e:
            logger.error(f"API error: {e}")
            return jsonify({'error': f'Kraken API error: {str(e)}'}), 500
        except ValueError as e:
            logger.error(f"Invalid parameter: {e}")
            return jsonify({'error': 'Invalid days parameter'}), 400
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    
    @api_bp.route('/set-credentials', methods=['POST'])
    @limiter.limit("5 per minute")
    def set_credentials():
        """Save API credentials in secure cookies."""
        try:
            data = flask_request.get_json()
            api_key = data.get('api_key', '').strip()
            api_secret = data.get('api_secret', '').strip()
            
            if not api_key or not api_secret:
                return jsonify({'error': 'Both API key and secret are required'}), 400
            
            # Test credentials
            try:
                since_ts, before_ts = get_period_boundaries(1)
                events = get_execution_events(api_key, api_secret, since_ts, before_ts)
                logger.info(f"Credential test successful, retrieved {len(events)} execution events")
            except KrakenAPIError as e:
                error_msg = str(e)
                if "Rate limit" in error_msg:
                    return jsonify({'error': 'Kraken API rate limit exceeded. Please wait a few minutes.'}), 429
                elif "Invalid API key" in error_msg:
                    return jsonify({'error': 'Invalid API key.'}), 401
                elif "Invalid signature" in error_msg:
                    return jsonify({'error': 'Invalid API secret.'}), 401
                else:
                    return jsonify({'error': f'API validation failed: {error_msg}'}), 401
            
            # Create response with cookies
            response = make_response(jsonify({'success': True, 'message': 'Credentials saved successfully'}))
            
            cookie_options = {
                'max_age': 30 * 24 * 60 * 60,  # 30 days
                'httponly': True,
                'samesite': 'Lax'
            }
            
            if not app.debug:
                cookie_options['secure'] = True
            
            response.set_cookie('kraken_api_key', api_key, **cookie_options)
            response.set_cookie('kraken_api_secret', api_secret, **cookie_options)
            
            return response
            
        except Exception as e:
            logger.error(f"Error setting credentials: {e}")
            return jsonify({'error': 'Failed to save credentials'}), 500
    
    @api_bp.route('/clear-credentials', methods=['POST'])
    def clear_credentials():
        """Clear API credentials from cookies."""
        response = make_response(jsonify({'success': True, 'message': 'Credentials cleared'}))
        response.set_cookie('kraken_api_key', '', max_age=0)
        response.set_cookie('kraken_api_secret', '', max_age=0)
        return response
    
    @api_bp.route('/validate-credentials', methods=['POST'])
    @limiter.limit("5 per minute")
    def validate_credentials():
        """Validate API credentials by making a test request."""
        try:
            data = flask_request.get_json()
            api_key = data.get('api_key', '').strip()
            api_secret = data.get('api_secret', '').strip()
            
            if not api_key or not api_secret:
                return jsonify({'valid': False, 'error': 'Missing credentials'}), 400
            
            # Test with minimal data
            since_ts, before_ts = get_period_boundaries(1)
            get_execution_events(api_key, api_secret, since_ts, before_ts)
            
            return jsonify({'valid': True})
            
        except KrakenAPIError as e:
            logger.error(f"Validation failed: {e}")
            return jsonify({'valid': False, 'error': str(e)}), 401
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return jsonify({'valid': False, 'error': 'Validation failed'}), 500
    
    return api_bp 