import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Grid,
  Skeleton,
  Chip,
  CircularProgress,
  useTheme,
  Divider,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  History,
  ShowChart,
  AutoGraph,
} from '@mui/icons-material';
import { getFundingHistory, getPredictedFunding } from '../utils/api';

const FundingCard = () => {
  const theme = useTheme();
  const [loading, setLoading] = useState(true);
  const [currentRate, setCurrentRate] = useState(null);
  const [historicalRates, setHistoricalRates] = useState([]);
  const [statistics, setStatistics] = useState({
    accumulated7d: 0,
    accumulated30d: 0,
    accumulated365d: 0,
  });
  const [predictions, setPredictions] = useState({
    predicted7d: 0,
    predicted30d: 0,
    predicted365d: 0,
  });

  useEffect(() => {
    loadFundingData();
    // Refresh every 5 minutes
    const interval = setInterval(loadFundingData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const loadFundingData = async () => {
    try {
      setLoading(true);
      
      // Fetch funding history for BTC perpetual
      const response = await getFundingHistory('PF_XBTUSD');
      
      if (response.data) {
        const { current, history, statistics, predictions } = response.data;
        
        setCurrentRate(current);
        setHistoricalRates(history);
        setStatistics(statistics);
        setPredictions(predictions);
      }
    } catch (error) {
      console.error('Error loading funding data:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatAbsoluteRate = (rate) => {
    if (rate === null || rate === undefined) return '-';
    const absRate = Math.abs(parseFloat(rate));
    // Display as USD per 1 BTC with appropriate precision
    return `$${absRate.toFixed(6)} per BTC`;
  };

  const formatAccumulatedRate = (rate) => {
    if (rate === null || rate === undefined) return '-';
    const absRate = Math.abs(parseFloat(rate));
    // Display accumulated USD per 1 BTC
    return `$${absRate.toFixed(4)} per BTC`;
  };

  const StatBox = ({ title, value, icon, color = 'primary' }) => (
    <Box
      sx={{
        p: 2,
        borderRadius: 2,
        backgroundColor: theme.palette.mode === 'dark' 
          ? 'rgba(255, 255, 255, 0.05)' 
          : 'rgba(0, 0, 0, 0.02)',
        border: `1px solid ${theme.palette.divider}`,
        textAlign: 'center',
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1 }}>
        {icon}
      </Box>
      <Typography variant="caption" color="text.secondary" display="block">
        {title}
      </Typography>
      <Typography variant="h6" fontWeight="bold" color={`${color}.main`}>
        {value}
      </Typography>
    </Box>
  );

  return (
    <Card
      sx={{
        maxWidth: 1200,
        mx: 'auto',
        backgroundColor: theme.palette.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.05)'
          : 'rgba(255, 255, 255, 0.98)',
        backdropFilter: 'blur(10px)',
      }}
    >
      <CardContent>
        {/* Title */}
        <Typography variant="h5" gutterBottom sx={{ fontWeight: 600, mb: 3 }}>
          Bitcoin Perpetual Hourly Funding Rates
        </Typography>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* Current Funding Rate */}
            <Box sx={{ textAlign: 'center', mb: 4 }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Current Funding Rate (USD per 1 BTC)
              </Typography>
              <Typography 
                variant="h2" 
                fontWeight="bold"
                sx={{
                  color: currentRate?.rate >= 0 ? theme.palette.success.main : theme.palette.error.main,
                }}
              >
                {currentRate ? formatAbsoluteRate(currentRate.rate) : '-'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Next funding in {currentRate?.next_funding_time || '-'}
              </Typography>
            </Box>

            {/* 8-Hour History Table */}
            <Box sx={{ mb: 4 }}>
              <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>
                Hourly Funding History (Last 8 Hours)
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Time</TableCell>
                      <TableCell align="right">Funding Rate (USD/BTC)</TableCell>
                      <TableCell align="right">Direction</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {historicalRates.map((rate, index) => (
                      <TableRow key={index}>
                        <TableCell>{rate.time}</TableCell>
                        <TableCell align="right">
                          <Typography 
                            variant="body2" 
                            fontWeight="medium"
                            color={rate.rate >= 0 ? 'success.main' : 'error.main'}
                          >
                            {formatAbsoluteRate(rate.rate)}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Chip
                            size="small"
                            icon={rate.rate >= 0 ? <TrendingUp /> : <TrendingDown />}
                            label={rate.rate >= 0 ? 'Long' : 'Short'}
                            color={rate.rate >= 0 ? 'success' : 'error'}
                            variant="outlined"
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>

            <Divider sx={{ my: 3 }} />

            {/* Statistics Grid */}
            <Grid container spacing={3}>
              {/* Historical Statistics */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>
                  <History sx={{ verticalAlign: 'middle', mr: 1 }} />
                  Historical Accumulated Funding (USD per BTC)
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={4}>
                    <StatBox
                      title="7 Days"
                      value={formatAccumulatedRate(statistics.accumulated7d)}
                      icon={<ShowChart color="primary" />}
                      color="primary"
                    />
                  </Grid>
                  <Grid item xs={4}>
                    <StatBox
                      title="30 Days"
                      value={formatAccumulatedRate(statistics.accumulated30d)}
                      icon={<ShowChart color="primary" />}
                      color="primary"
                    />
                  </Grid>
                  <Grid item xs={4}>
                    <StatBox
                      title="365 Days"
                      value={formatAccumulatedRate(statistics.accumulated365d)}
                      icon={<ShowChart color="primary" />}
                      color="primary"
                    />
                  </Grid>
                </Grid>
              </Grid>

              {/* Predicted Statistics */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>
                  <AutoGraph sx={{ verticalAlign: 'middle', mr: 1 }} />
                  Predicted Accumulated Funding (ML Model)
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={4}>
                    <StatBox
                      title="Next 7 Days"
                      value={formatAccumulatedRate(predictions.predicted7d)}
                      icon={<AutoGraph color="secondary" />}
                      color="secondary"
                    />
                  </Grid>
                  <Grid item xs={4}>
                    <StatBox
                      title="Next 30 Days"
                      value={formatAccumulatedRate(predictions.predicted30d)}
                      icon={<AutoGraph color="secondary" />}
                      color="secondary"
                    />
                  </Grid>
                  <Grid item xs={4}>
                    <StatBox
                      title="Next 365 Days"
                      value={formatAccumulatedRate(predictions.predicted365d)}
                      icon={<AutoGraph color="secondary" />}
                      color="secondary"
                    />
                  </Grid>
                </Grid>
              </Grid>
            </Grid>

            {/* Model Info */}
            <Box sx={{ mt: 3, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">
                Predictions based on ARIMA time series model with hourly funding rate patterns
              </Typography>
            </Box>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default FundingCard; 