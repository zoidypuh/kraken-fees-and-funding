"""
Kraken Futures Dashboard - Main Flask Application
"""
import os
import logging
from flask import Flask, render_template, jsonify
from flask_compress import Compress
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize extensions
compress = Compress()
cache = Cache()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri="memory://"
)


def create_app(config_name=None):
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder='frontend/templates',
        static_folder='frontend/static'
    )
    
    # Configure Flask directly with environment variables
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Cache configuration
    # Use /tmp for cache in production (Google App Engine)
    if os.environ.get('GAE_ENV', '').startswith('standard'):
        app.config['CACHE_TYPE'] = 'simple'  # In-memory cache for production
    else:
        app.config['CACHE_TYPE'] = 'filesystem'
        app.config['CACHE_DIR'] = os.path.join(os.path.dirname(__file__), '.cache')
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes
    
    # Initialize extensions
    compress.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register routes
    register_routes(app)
    
    # Log startup info
    env = os.environ.get('FLASK_ENV', 'production')
    logger.info(f"Starting Kraken Dashboard in {env} mode")
    logger.info(f"Cache type: {app.config.get('CACHE_TYPE', 'simple')}")
    
    return app


def register_routes(app):
    """Register all route blueprints."""
    # Import blueprints
    from routes.auth import auth
    from routes.positions import positions
    from routes.market import market
    from routes.analytics import analytics
    
    # Register blueprints
    app.register_blueprint(auth)
    app.register_blueprint(positions)
    app.register_blueprint(market)
    app.register_blueprint(analytics)
    
    # Root route
    @app.route('/')
    def index():
        """Serve the main dashboard page."""
        return render_template('index.html')
    
    # Health check
    @app.route('/health')
    @limiter.exempt
    def health_check():
        """Simple health check endpoint."""
        return jsonify({
            'status': 'healthy',
            'service': 'kraken-dashboard'
        })
    
    # API info
    @app.route('/api')
    def api_info():
        """List available API endpoints."""
        return jsonify({
            'version': '2.0',
            'endpoints': {
                'auth': {
                    'GET /api/auth/status': 'Check authentication status',
                    'POST /api/auth/credentials': 'Set API credentials',
                    'DELETE /api/auth/credentials': 'Clear API credentials'
                },
                'positions': {
                    'GET /api/positions/': 'Get open positions (basic)',
                    'GET /api/positions/detailed': 'Get positions with P&L'
                },
                'market': {
                    'GET /api/market/ticker/<symbol>': 'Get ticker data',
                    'POST /api/market/tickers': 'Get multiple tickers',
                    'GET /api/market/price/<symbol>': 'Get mark price only'
                },
                'analytics': {
                    'GET /api/analytics/chart-data': 'Get chart data',
                    'GET /api/analytics/fees': 'Get fees data',
                    'GET /api/analytics/funding': 'Get funding data',
                    'GET /api/analytics/summary': 'Get summary statistics'
                },

            }
        })
    
    # Legacy endpoints for backward compatibility
    @app.route('/api/test')
    def test_endpoint():
        """Test endpoint."""
        return jsonify({'status': 'ok', 'message': 'API is working'})
    
    # Redirect old endpoints
    @app.route('/api/set-credentials', methods=['POST'])
    def legacy_set_credentials():
        """Redirect to new auth endpoint."""
        from flask import redirect, url_for
        return redirect(url_for('auth.set_credentials'), code=307)
    
    @app.route('/api/clear-credentials', methods=['POST', 'DELETE'])
    def legacy_clear_credentials():
        """Redirect to new auth endpoint."""
        from flask import redirect, url_for
        return redirect(url_for('auth.clear_credentials'), code=307)
    
    @app.route('/api/validate-credentials', methods=['POST'])
    def legacy_validate_credentials():
        """Redirect to new auth endpoint."""
        from flask import redirect, url_for
        # Since we don't have a separate validate endpoint, redirect to set_credentials
        return redirect(url_for('auth.set_credentials'), code=307)
    
    @app.route('/api/data')
    def legacy_data():
        """Redirect to new analytics endpoint."""
        from flask import redirect, url_for
        return redirect(url_for('analytics.get_chart_data'), code=307)


def register_error_handlers(app):
    """Register error handlers."""
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors."""
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        """Handle rate limit errors."""
        return jsonify({'error': 'Rate limit exceeded', 'message': str(error.description)}), 429
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        logger.error(f"Internal error: {error}")
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handle unexpected exceptions."""
        logger.error(f"Unhandled exception: {error}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500


if __name__ == '__main__':
    # For development only
    app = create_app('development')
    app.run(host='0.0.0.0', port=5000, debug=True) 