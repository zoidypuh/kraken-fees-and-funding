# Kraken Fees and Funding Dashboard

A Flask web application to visualize trading fees and funding costs from Kraken Futures.

## Features

- Real-time visualization of trading fees and funding costs
- Interactive charts showing daily breakdown
- Open positions tracking with accumulated costs
- Secure credential storage using browser cookies
- Data caching for improved performance

## Requirements

- Python 3.7+
- Kraken Futures API credentials (read-only)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/kraken-fees-and-funding-dashboard.git
cd kraken-fees-and-funding-dashboard
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your Kraken Futures API credentials:
```
KRAKEN_FUTURES_API_KEY=your_api_key_here
KRAKEN_FUTURES_API_SECRET=your_api_secret_here
```

## Usage

1. Start the Flask application:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5000`

3. Enter your Kraken Futures API credentials (or they'll be loaded from .env)

4. View your trading fees, funding costs, and open positions

## Security

- API credentials are stored securely in HTTP-only cookies
- Credentials are never sent to external servers
- All data processing happens locally

## License

MIT 