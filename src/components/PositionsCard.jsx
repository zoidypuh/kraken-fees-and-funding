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
  Cached as CachedIcon,
} from '@mui/icons-material';
import { getPositionsDetailed } from '../utils/api';
import { formatCurrency, formatNumber, formatDateTime } from '../utils/formatters';
import { positionsCache, formatCacheAge } from '../utils/cache';

const REFRESH_INTERVAL = 30000; // 30 seconds

const PositionsCard = ({ onRefresh }) => {
  const theme = useTheme();
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [cacheInfo, setCacheInfo] = useState(null);
  const [isLoadingFresh, setIsLoadingFresh] = useState(false);
  const isLoadingRef = useRef(false);
  const [displayTime, setDisplayTime] = useState(null);

  const loadPositions = useCallback(async (showLoadingIndicator = true) => {
    // Prevent concurrent requests
    if (isLoadingRef.current) {
      return;
    }
    
    try {
      isLoadingRef.current = true;
      if (showLoadingIndicator) {
        setIsLoadingFresh(true);
      }
      setError(null);
      
      // Add small delay to debounce multiple calls
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // Check if this is a force refresh (manual refresh button click)
      const isForceRefresh = showLoadingIndicator && !cacheInfo;
      const response = await getPositionsDetailed(isForceRefresh);
      
      // Only update positions if we got valid data
      if (response.data && Array.isArray(response.data)) {
        setPositions(prevPositions => {
          // Don't update to empty array if we already have positions
          if (response.data.length === 0 && prevPositions.length > 0) {
            return prevPositions;
          }
          return response.data;
        });
        const now = new Date();
        setLastUpdate(now);
        setDisplayTime(now);
        setCacheInfo(null); // Clear cache info when fresh data is loaded
        
        // Cache the new data
        positionsCache.set(response.data);
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
      setIsLoadingFresh(false);
      isLoadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    let interval;
    let mounted = true;
    
    // Initial load strategy: show cached data immediately, then load fresh
    const loadInitial = async () => {
      // First, try to load from cache
      const cached = positionsCache.get();
      if (cached && cached.data && cached.data.length > 0) {
        setPositions(cached.data);
        setCacheInfo({
          isStale: cached.isStale,
          age: cached.age,
          timestamp: Date.now() - cached.age
        });
        // Set display time to when cache was saved
        setDisplayTime(new Date(Date.now() - cached.age));
        setLoading(false); // Don't show initial loading if we have cached data
        
        // If cache is fresh enough (< 30 seconds), don't immediately load new data
        if (!cached.isStale && cached.age < 30000) {
          return;
        }
      }
      
      // Load fresh data (with loading indicator only if no cached data)
      if (mounted) {
        await new Promise(resolve => setTimeout(resolve, 500));
        if (mounted) {
          loadPositions(!cached || cached.data.length === 0);
        }
      }
    };
    
    loadInitial();
    
    // Set up auto-refresh
    const timeoutId = setTimeout(() => {
      if (mounted) {
        interval = setInterval(() => {
          if (mounted) {
            // Auto-refresh: don't show loading indicator and don't force refresh
            loadPositions(false);
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
    try {
      // Clear local cache to force fresh data
      positionsCache.clear();
      setCacheInfo(null); // Clear cache info immediately
      setIsLoadingFresh(true); // Set loading state for refresh button
      setError(null);
      
      // Force fresh data from server by passing true as force refresh
      // This will bypass both local and server-side caches
      const response = await getPositionsDetailed(true);
      
      if (response.data && Array.isArray(response.data)) {
        setPositions(response.data);
        const now = new Date();
        setLastUpdate(now);
        setDisplayTime(now);
        
        // Cache the new data
        positionsCache.set(response.data);
      }
    } catch (error) {
      console.error('Error refreshing positions:', error);
      if (error.response?.status === 429) {
        setError('Rate limit exceeded. Please wait a moment.');
      } else {
        setError('Failed to refresh positions');
      }
    } finally {
      setIsLoadingFresh(false);
    }
    
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
      <Box sx={{ 
        display: 'flex', 
        gap: 0.5, 
        alignItems: 'center',
        justifyContent: 'center',
        height: 40,
      }}>
        {hourlyFunding.map((value, index) => {
          // Scale based on -$10 to +$10 range
          const maxValue = 10; // $10
          const normalizedValue = Math.max(-maxValue, Math.min(maxValue, value));
          const percentage = Math.abs(normalizedValue) / maxValue; // 0 to 1
          
          // Calculate height (max 30px for full $10)
          const height = Math.max(4, percentage * 30);
          
          // Simple red/green color based on positive/negative
          const color = value >= 0 ? theme.palette.success.main : theme.palette.error.main;
          
          return (
            <Tooltip 
              key={index} 
              title={
                <Box>
                  <Typography variant="caption">Hour {index + 1}</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {formatCurrency(value)}
                  </Typography>
                </Box>
              }
            >
              <Box
                sx={{
                  width: 12,
                  height: `${height}px`,
                  backgroundColor: color,
                  borderRadius: 6,
                  boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  transition: 'all 0.3s ease',
                  cursor: 'pointer',
                  opacity: 0.9,
                  '&:hover': {
                    transform: 'scale(1.1) translateY(-2px)',
                    boxShadow: '0 3px 6px rgba(0,0,0,0.3)',
                    opacity: 1,
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
    <Card 
      sx={{ 
        borderRadius: 3,
        mx: { xs: 2, sm: 3, md: 4 },
        boxShadow: theme.shadows[2],
        '&:hover': {
          boxShadow: theme.shadows[4],
        },
        transition: 'box-shadow 0.3s ease-in-out',
      }}
    >
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
            <Typography variant="body2" color="text.secondary">
              Updated: {displayTime ? displayTime.toLocaleTimeString() : 'Loading...'}
            </Typography>
            <Tooltip title={isLoadingFresh ? "Loading fresh data..." : "Refresh positions"}>
              <IconButton 
                onClick={handleRefresh} 
                disabled={loading || isLoadingFresh}
                size="small"
              >
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
        }
      />
      
      {(loading || isLoadingFresh) && <LinearProgress />}
      
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
                  <TableCell>Position Opened</TableCell>
                  <TableCell align="right">Side</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="right">Entry Price</TableCell>
                  <TableCell align="right">Current Price</TableCell>
                  <TableCell align="right">Unrealized P&L</TableCell>
                  <TableCell align="right">Funding</TableCell>
                  <TableCell align="right">Fees</TableCell>
                  <TableCell align="right">Net P&L</TableCell>
                  <TableCell align="center">Funding History (8h)</TableCell>
                  <TableCell align="center">Predicted Funding</TableCell>
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
                    <TableCell>
                      {position.openedDate ? (
                        <Typography variant="body2">
                          {formatDateTime(position.openedDate)}
                        </Typography>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          -
                        </Typography>
                      )}
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
                        <Tooltip title="Current funding rate × position size">
                          <Chip
                            label={`Current: ${formatCurrency(Math.abs(position.size) * position.fundingRateCurrent)}`}
                            size="small"
                            variant="outlined"
                          />
                        </Tooltip>
                        <Tooltip title="Predicted funding rate × position size">
                          <Chip
                            label={`Predicted: ${formatCurrency(Math.abs(position.size) * position.fundingRatePredicted)}`}
                            size="small"
                            variant="outlined"
                            color="info"
                          />
                        </Tooltip>
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
              Auto-refreshes every 30 seconds
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default PositionsCard; 