import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  IconButton,
  Box,
  Typography,
  LinearProgress,
  Chip,
  Tooltip,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  useTheme,
  alpha,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  TrendingUp,
  TrendingDown,
  AccessTime,
  Warning,
} from '@mui/icons-material';
import { getPositionsDetailed } from '../utils/api';
import { formatCurrency, formatNumber, formatDateTime } from '../utils/formatters';

const REFRESH_INTERVAL = 120000; // 120 seconds (2 minutes)

const PositionsCard = ({ onRefresh }) => {
  const theme = useTheme();
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const isLoadingRef = useRef(false);

  const loadPositions = useCallback(async () => {
    // Prevent concurrent requests
    if (isLoadingRef.current) {
      console.log('Skipping positions load - already loading');
      return;
    }
    
    try {
      isLoadingRef.current = true;
      setError(null);
      
      // Add small delay to debounce multiple calls
      await new Promise(resolve => setTimeout(resolve, 100));
      
      const response = await getPositionsDetailed();
      
      // Only update positions if we got valid data
      if (response.data && Array.isArray(response.data)) {
        setPositions(prevPositions => {
          // Don't update to empty array if we already have positions
          if (response.data.length === 0 && prevPositions.length > 0) {
            return prevPositions;
          }
          return response.data;
        });
        setLastUpdate(new Date());
      }
    } catch (error) {
      console.error('Error loading positions:', error);
      // Don't clear existing positions on error
      if (error.response?.status === 429) {
        setError('Rate limit exceeded. Slowing down refresh rate...');
        // Temporarily slow down refresh on rate limit
        setTimeout(() => setError(null), 10000);
      } else {
        setError('Failed to load positions');
      }
    } finally {
      setLoading(false);
      isLoadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    let interval;
    let mounted = true;
    
    // Initial load with small delay to prevent multiple simultaneous calls
    const loadInitial = async () => {
      if (mounted) {
        await new Promise(resolve => setTimeout(resolve, 500));
        if (mounted) {
          loadPositions();
        }
      }
    };
    
    loadInitial();
    
    // Set up auto-refresh
    const timeoutId = setTimeout(() => {
      if (mounted) {
        interval = setInterval(() => {
          if (mounted) {
            loadPositions();
          }
        }, REFRESH_INTERVAL);
      }
    }, REFRESH_INTERVAL);
    
    return () => {
      mounted = false;
      clearTimeout(timeoutId);
      if (interval) clearInterval(interval);
    };
  }, []); // Remove loadPositions dependency to avoid recreating interval

  const handleRefresh = async () => {
    setLoading(true);
    await loadPositions();
    if (onRefresh) onRefresh();
  };

  const getRowColor = (position) => {
    if (position.netUnrealizedPnl > 0) {
      return alpha(theme.palette.success.main, 0.08);
    } else if (position.netUnrealizedPnl < 0) {
      return alpha(theme.palette.error.main, 0.08);
    }
    return 'transparent';
  };

  const renderFundingBars = (hourlyFunding) => {
    if (!hourlyFunding || hourlyFunding.length === 0) return null;

    return (
      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
        {hourlyFunding.map((value, index) => {
          const height = Math.min(Math.abs(value) * 10, 20);
          const color = value >= 0 ? theme.palette.success.main : theme.palette.error.main;
          
          return (
            <Tooltip key={index} title={`Hour ${index + 1}: ${formatCurrency(value)}`}>
              <Box
                sx={{
                  width: 8,
                  height: `${height}px`,
                  backgroundColor: color,
                  borderRadius: 0.5,
                  opacity: 0.8,
                  transition: 'all 0.3s',
                  '&:hover': {
                    opacity: 1,
                    transform: 'scaleY(1.2)',
                  },
                }}
              />
            </Tooltip>
          );
        })}
      </Box>
    );
  };

  return (
    <Card>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h6">Open Positions</Typography>
            {positions.length > 0 && (
              <Chip
                label={`${positions.length} Active`}
                size="small"
                color="primary"
                variant="outlined"
              />
            )}
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {lastUpdate && (
              <Typography variant="caption" color="text.secondary">
                Updated: {lastUpdate.toLocaleTimeString()}
              </Typography>
            )}
            <Tooltip title="Refresh positions">
              <IconButton onClick={handleRefresh} disabled={loading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
        }
      />
      
      {loading && <LinearProgress />}
      
      <CardContent>
        {error ? (
          <Alert severity="error">{error}</Alert>
        ) : positions.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="body1" color="text.secondary">
              No open positions
            </Typography>
          </Box>
        ) : (
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell align="right">Side</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="right">Entry Price</TableCell>
                  <TableCell align="right">Current Price</TableCell>
                  <TableCell align="right">Unrealized P&L</TableCell>
                  <TableCell align="right">Funding</TableCell>
                  <TableCell align="right">Fees</TableCell>
                  <TableCell align="right">Net P&L</TableCell>
                  <TableCell align="center">Funding History (8h)</TableCell>
                  <TableCell align="center">Funding Rates</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {positions.map((position) => (
                  <TableRow
                    key={position.symbol}
                    sx={{
                      backgroundColor: getRowColor(position),
                      '&:hover': {
                        backgroundColor: alpha(theme.palette.action.hover, 0.08),
                      },
                    }}
                  >
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" fontWeight="medium">
                          {position.symbol}
                        </Typography>
                        {position.dataIsCapped && (
                          <Tooltip title="Historical data is limited">
                            <Warning fontSize="small" color="warning" />
                          </Tooltip>
                        )}
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={position.side.toUpperCase()}
                        size="small"
                        color={position.side === 'long' ? 'success' : 'error'}
                        icon={position.side === 'long' ? <TrendingUp /> : <TrendingDown />}
                      />
                    </TableCell>
                    <TableCell align="right">{formatNumber(Math.abs(position.size))}</TableCell>
                    <TableCell align="right">{formatCurrency(position.avgPrice)}</TableCell>
                    <TableCell align="right">{formatCurrency(position.currentPrice)}</TableCell>
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        color={position.unrealizedPnl >= 0 ? 'success.main' : 'error.main'}
                        fontWeight="medium"
                      >
                        {formatCurrency(position.unrealizedPnl)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        color={position.accumulatedFunding >= 0 ? 'success.main' : 'error.main'}
                      >
                        {formatCurrency(position.accumulatedFunding)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" color="error.main">
                        {formatCurrency(-Math.abs(position.accumulatedFees))}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        color={position.netUnrealizedPnl >= 0 ? 'success.main' : 'error.main'}
                        fontWeight="bold"
                      >
                        {formatCurrency(position.netUnrealizedPnl)}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      {renderFundingBars(position.hourlyFunding)}
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                        <Chip
                          label={`Current: ${(position.fundingRateCurrent * 100).toFixed(4)}%`}
                          size="small"
                          variant="outlined"
                        />
                        <Chip
                          label={`Predicted: ${(position.fundingRatePredicted * 100).toFixed(4)}%`}
                          size="small"
                          variant="outlined"
                          color="info"
                        />
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
        
        {positions.length > 0 && (
          <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
            <AccessTime fontSize="small" color="action" />
            <Typography variant="caption" color="text.secondary">
              Auto-refreshes every 2 minutes
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default PositionsCard; 