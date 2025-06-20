# Kraken Futures Fees and Funding Dashboard

A Flask web application to visualize trading fees and funding costs for Kraken Futures.

## Project Structure

```
project-root/
│
├── backend/                    # Backend application code
│   ├── app.py                 # Main Flask application
│   ├── config.py              # Configuration settings
│   ├── models.py              # Data models
│   ├── api.py                 # API routes blueprint
│   ├── kraken_client.py       # Unified Kraken client (sync + async)

│   ├── dashboard_utils.py     # Utility functions

│   └── requirements.txt       # Python dependencies
│
├── frontend/                   # Frontend assets
│   ├── static/                # Static files
│   │   ├── css/              # Stylesheets
│   │   ├── js/               # JavaScript files
│   │   └── images/           # Images
│   └── templates/             # HTML templates
│       └── index.html        # Main dashboard template
│
├── documentation/             # Project documentation
│   ├── PRODUCTION_DEPLOYMENT.md # Production deployment guide
│   └── optimization.md          # Performance optimizations
│
├── tests/                     # Test suite
│   └── test_*.py             # Test files
│
├── logs/                      # Application logs
├── .env                       # Environment variables (create this)
├── main.py                    # Application entry point
└── README.md                  # This file
```

## Features

- **Real-time Dashboard**: View your trading fees and funding costs in an intuitive web interface
- **Open Positions Tracking**: Monitor all open positions with real-time P&L calculations
- **Historical Analysis**: Analyze fees and funding over customizable time periods (7, 30, 60, 90 days)
- **Detailed Breakdowns**: See fee breakdowns by trade with hover tooltips
- **Cumulative Views**: Track cumulative costs over time
- **Secure**: API credentials stored in encrypted cookies or environment variables
- **Performance Optimized**: 
  - Async client for 2-3x faster API calls
  - Smart caching to reduce API calls
  - **Production Ready**: Includes scripts for production deployment with Gunicorn and Nginx

## Quick Start

### 1. Clone the repository
```bash
git clone <repository-url>
cd kraken-fees-and-funding-dashboard
```

### 2. Set up Python environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 3. Configure environment variables
Create a `.env` file in the project root:
```env
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key-here

# Optional: Set API credentials via environment
KRAKEN_API_KEY=your-api-key
KRAKEN_API_SECRET=your-api-secret


```

### 4. Run the application
```bash
python main.py
```

The application will be available at `http://localhost:5000`

## API Credentials

You can provide Kraken API credentials in two ways:

1. **Through the web interface** (recommended): Click on the API key icon in the header
2. **Through environment variables**: Set `KRAKEN_API_KEY` and `KRAKEN_API_SECRET` in your `.env` file

## Development



### Running Tests

```bash
pytest tests/
```

## Production Deployment

See `documentation/PRODUCTION_DEPLOYMENT.md` for detailed production deployment instructions.

### Quick Production Start

```bash
# Set up environment
cp env.production.example .env
# Edit .env with your configuration

# Start all services
./start_production.sh

# Or for network access from other devices
./start_production_network.sh
```

## API Endpoints

All API endpoints are prefixed with `/api/`:

- `GET /api/data?days=N` - Fetch chart data for N days
- `POST /api/set-credentials` - Save API credentials
- `POST /api/clear-credentials` - Clear saved credentials


## Performance Optimizations

The application includes several performance optimizations:

- **Caching**: Automatic caching of API responses
- **Parallel API calls**: Concurrent fetching of data
- **Rate limiting**: Protection against API rate limits
- **Async support**: Optional async I/O with aiohttp
- **Response compression**: Gzip compression for smaller payloads

## Troubleshooting

### Common Issues

1. **"API credentials not configured"**
   - Ensure you've entered valid API credentials
   - Check that your API key has read permissions for Futures

2. **Rate limit errors**
   - The app implements automatic retry with exponential backoff
   - If persistent, wait a few minutes before retrying

3. **No data showing**
   - Verify you have trading history in the selected time period
   - Check browser console for any JavaScript errors

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here] 