# Kraken Fees and Funding Dashboard - React Version

A modern React-based dashboard for visualizing trading fees and funding costs for Kraken Futures, built with Material UI.

## Features

### 🎨 Modern UI with Material Design
- Clean, professional interface using Material UI components
- Light and dark theme support
- Responsive design for desktop and mobile devices
- Smooth animations and transitions

### 📊 Enhanced Visualizations
- Interactive charts with multiple view modes (fees, funding, combined, cumulative)
- Real-time position monitoring with auto-refresh (5-second intervals)
- Visual funding rate history with bar indicators
- Color-coded profit/loss indicators

### 🚀 Performance Improvements
- React-based architecture for better state management
- Efficient data caching
- Optimized API calls
- Smooth loading states and error handling

### 📱 Responsive Components
- Summary cards showing 90-day totals
- Positions table with detailed P&L calculations
- Chart controls with period selection (7-90 days)
- Mobile-optimized layouts

## Tech Stack

- **Frontend**: React 18 with Vite
- **UI Framework**: Material UI (MUI) v5
- **Charts**: Recharts
- **State Management**: React hooks
- **Styling**: Material UI theme system + CSS
- **HTTP Client**: Axios
- **Backend**: Flask (Python) - unchanged from original

## Prerequisites

- Node.js 18+ and npm
- Python 3.7+
- Kraken Futures API credentials

## Installation

1. Clone the repository and switch to the react branch:
```bash
git clone https://github.com/zoidypuh/kraken-fees-and-funding.git
cd kraken-fees-and-funding-dashboard
git checkout react
```

2. Install Python dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Install Node.js dependencies:
```bash
npm install
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Running the Application

### Development Mode

1. Start the Flask backend:
```bash
python app.py
```

2. In a new terminal, start the React development server:
```bash
npm run dev
```

3. Open http://localhost:3000 in your browser

### Production Build

1. Build the React app:
```bash
npm run build
```

2. The built files will be in the `dist` directory

## Key Components

### React Components
- **App.jsx**: Main application component with theme provider
- **Dashboard.jsx**: Layout container for all dashboard sections
- **Header.jsx**: Top navigation with theme toggle and API settings
- **SummaryCards.jsx**: 90-day cost summary display
- **PositionsCard.jsx**: Real-time positions table with auto-refresh
- **ChartCard.jsx**: Interactive cost visualization charts
- **AuthDialog.jsx**: API credentials configuration modal

### Material UI Theme
- Custom light and dark themes
- Consistent color palette
- Typography system
- Component overrides for consistent styling

## Features Comparison

### New in React Version
- ✅ Material Design UI
- ✅ Smooth animations and transitions
- ✅ Better mobile responsiveness
- ✅ Improved loading states
- ✅ Component-based architecture
- ✅ Modern development experience

### Maintained from Original
- ✅ All API functionality
- ✅ 5-second position refresh
- ✅ Fee and funding calculations
- ✅ Chart visualizations
- ✅ Dark mode support
- ✅ API credential management

## Development

### Project Structure
```
kraken-fees-and-funding-dashboard/
├── src/
│   ├── components/       # React components
│   ├── theme/           # Material UI themes
│   ├── utils/           # API and utility functions
│   ├── App.jsx          # Main app component
│   └── main.jsx         # Entry point
├── public/              # Static assets
├── app.py              # Flask backend (unchanged)
├── vite.config.js      # Vite configuration
└── package.json        # Node dependencies
```

### Available Scripts
- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License. 