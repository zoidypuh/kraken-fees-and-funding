"""
Authentication and credential management routes.
"""
from flask import Blueprint, jsonify, request, make_response, current_app
from functools import wraps
import logging
import time
from datetime import datetime, timezone

from kraken_client import get_api_credentials, get_execution_events, KrakenAPIError

logger = logging.getLogger(__name__)

auth = Blueprint('auth', __name__, url_prefix='/api/auth')

# Rate limiting for credential validation
last_credential_attempt = 0
CREDENTIAL_ATTEMPT_COOLDOWN = 30  # seconds


def require_api_credentials(f):
    """Decorator to ensure API credentials are available."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key, api_secret = get_api_credentials(request)
        if not api_key or not api_secret:
            return jsonify({'error': 'API credentials not configured'}), 401
        return f(api_key, api_secret, *args, **kwargs)
    return decorated_function


@auth.route('/status')
def auth_status():
    """Check if API credentials are configured."""
    api_key, api_secret = get_api_credentials(request)
    return jsonify({
        'authenticated': bool(api_key and api_secret),
        'hasApiKey': bool(api_key),
        'apiKeyLength': len(api_key) if api_key else 0
    })


@auth.route('/credentials', methods=['POST'])
def set_credentials():
    """Save API credentials."""
    global last_credential_attempt
    
    # Check rate limit
    current_time = time.time()
    time_since_last = current_time - last_credential_attempt
    if time_since_last < CREDENTIAL_ATTEMPT_COOLDOWN:
        wait_time = int(CREDENTIAL_ATTEMPT_COOLDOWN - time_since_last)
        return jsonify({
            'error': f'Too many attempts. Please wait {wait_time} seconds.'
        }), 429
    
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        api_secret = data.get('api_secret', '').strip()
        
        # Clean credentials
        api_key = api_key.replace('\r', '').replace('\n', '')
        api_secret = api_secret.replace('\r', '').replace('\n', '')
        
        if not api_key or not api_secret:
            return jsonify({'error': 'Both API key and secret are required'}), 400
        
        # Update rate limit timestamp
        last_credential_attempt = current_time
        
        # Test credentials
        try:
            since_ts = int((datetime.now(timezone.utc).timestamp() - 86400) * 1000)
            before_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            # Minimal test to validate credentials
            executions = get_execution_events(api_key, api_secret, since_ts, before_ts)
            logger.info(f"Credentials validated, fetched {len(executions)} events")
            
        except KrakenAPIError as e:
            error_msg = str(e)
            if "EAPI:Invalid key" in error_msg:
                return jsonify({'error': 'Invalid API key'}), 401
            elif "EAPI:Invalid signature" in error_msg:
                return jsonify({'error': 'Invalid API secret'}), 401
            elif "EGeneral:Permission denied" in error_msg:
                return jsonify({'error': 'Permission denied. Check API permissions'}), 401
            else:
                return jsonify({'error': f'Validation failed: {error_msg}'}), 401
        
        # Create response with secure cookies
        response = make_response(jsonify({'success': True}))
        
        cookie_flags = {
            'max_age': 30 * 24 * 60 * 60,  # 30 days
            'httponly': True,
            'samesite': 'Lax'
        }
        
        if not current_app.debug:
            cookie_flags['secure'] = True
        
        response.set_cookie('kraken_api_key', api_key, **cookie_flags)
        response.set_cookie('kraken_api_secret', api_secret, **cookie_flags)
        
        return response
        
    except Exception as e:
        logger.error(f"Error saving credentials: {e}")
        return jsonify({'error': 'Failed to save credentials'}), 500


@auth.route('/credentials', methods=['DELETE'])
def clear_credentials():
    """Clear stored API credentials."""
    response = make_response(jsonify({'success': True}))
    response.set_cookie('kraken_api_key', '', max_age=0)
    response.set_cookie('kraken_api_secret', '', max_age=0)
    return response 