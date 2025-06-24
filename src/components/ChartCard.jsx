import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Box,
  Button,
  ButtonGroup,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Typography,
  CircularProgress,
  Alert,
  Chip,
  Paper,
  useTheme,
  Tooltip,
  IconButton,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  BarChart as BarChartIcon,
  ShowChart as LineChartIcon,
  Layers as LayersIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from 'recharts';
import { format } from 'date-fns';
import { getChartData } from '../utils/api';
import { formatCurrency, formatNumber } from '../utils/formatters';

const ChartCard = ({ days = 7, onDaysChange, onDataLoad }) => {
  const theme = useTheme();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [displayData, setDisplayData] = useState(null);
  const [chartMode, setChartMode] = useState('combined');
  const [cacheHit, setCacheHit] = useState(false);
  
  const isLoadingRef = useRef(false);
  const lastLoadTime = useRef(0);
  const loadTimeoutRef = useRef(null);

  // Initial load on mount
  useEffect(() => {
    const timer = setTimeout(() => {
      loadChartData();
    }, 500); // Small delay to let component settle
    
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps for mount only
  
  // Load when days change (but not on mount)
  useEffect(() => {
    if (!chartData) return; // Skip if no initial data yet
    
    // Clear any pending timeout
    if (loadTimeoutRef.current) {
      clearTimeout(loadTimeoutRef.current);
    }
    
    // Debounce the load call
    loadTimeoutRef.current = setTimeout(() => {
      loadChartData();
    }, 300);
    
    return () => {
      if (loadTimeoutRef.current) {
        clearTimeout(loadTimeoutRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  useEffect(() => {
    if (chartData) {
      processChartData();
    }
  }, [chartData, chartMode]);

  const loadChartData = useCallback(async () => {
    // Prevent concurrent requests
    if (isLoadingRef.current) {
      return;
    }
    
    // Rate limit: minimum 5 seconds between requests
    const now = Date.now();
    if (now - lastLoadTime.current < 5000) {
      console.log('Skipping request - too soon after last request');
      return;
    }
    
    isLoadingRef.current = true;
    lastLoadTime.current = now;
    
    setLoading(true);
    setError(null);
    const startTime = Date.now();

    try {
      const response = await getChartData(days);
      const data = response.data;
      setChartData(data);
      
      // Pass data to parent
      if (onDataLoad) {
        onDataLoad(data);
      }
      
      // Check if data was cached
      const loadTime = Date.now() - startTime;
      setCacheHit(loadTime < 500);
    } catch (error) {
      console.error('Error loading chart data:', error);
      // Handle rate limit errors specifically
      if (error.response?.status === 429) {
        setError('API rate limit reached. Please wait a moment before trying again.');
      } else {
        setError('Failed to load chart data');
      }
    } finally {
      setLoading(false);
      isLoadingRef.current = false;
    }
  }, [days, onDataLoad]);

  const processChartData = () => {
    if (!chartData) return;

    const data = chartData.labels.map((label, index) => {
      const baseData = {
        date: label,
        fees: Math.abs(chartData.fees[index]),
        funding: Math.abs(chartData.funding[index]),
        combined: Math.abs(chartData.fees[index] + chartData.funding[index]),
      };

      if (chartMode === 'cumulative') {
        const cumulativeFees = chartData.fees.slice(0, index + 1).reduce((sum, val) => sum + val, 0);
        const cumulativeFunding = chartData.funding.slice(0, index + 1).reduce((sum, val) => sum + val, 0);
        
        return {
          ...baseData,
          cumulativeFees: Math.abs(cumulativeFees),
          cumulativeFunding: Math.abs(cumulativeFunding),
          cumulativeTotal: Math.abs(cumulativeFees + cumulativeFunding),
        };
      }

      return baseData;
    });

    setDisplayData(data);
  };

  const handleRefresh = useCallback(() => {
    // Force refresh by clearing last load time
    lastLoadTime.current = 0;
    loadChartData();
  }, [loadChartData]);

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload) return null;

    return (
      <Paper
        sx={{
          p: 2,
          backgroundColor: theme.palette.background.paper,
          border: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Typography variant="subtitle2" gutterBottom>
          {format(new Date(label), 'MMM dd, yyyy')}
        </Typography>
        {payload.map((entry, index) => (
          <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box
              sx={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                backgroundColor: entry.color,
              }}
            />
            <Typography variant="body2">
              {entry.name}: {formatCurrency(entry.value)}
            </Typography>
          </Box>
        ))}
      </Paper>
    );
  };

  const renderChart = () => {
    if (!displayData || displayData.length === 0) return null;

    const commonProps = {
      data: displayData,
      margin: { top: 10, right: 30, left: 0, bottom: 0 },
    };

    switch (chartMode) {
      case 'fees':
        return (
          <BarChart {...commonProps}>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
            <XAxis
              dataKey="date"
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => `$${value}`}
            />
            <RechartsTooltip content={<CustomTooltip />} />
            <Bar
              dataKey="fees"
              fill={theme.palette.primary.main}
              name="Fees"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        );

      case 'funding':
        return (
          <BarChart {...commonProps}>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
            <XAxis
              dataKey="date"
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => `$${value}`}
            />
            <RechartsTooltip content={<CustomTooltip />} />
            <Bar
              dataKey="funding"
              fill={theme.palette.secondary.main}
              name="Funding"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        );

      case 'combined':
        return (
          <BarChart {...commonProps}>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
            <XAxis
              dataKey="date"
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => `$${value}`}
            />
            <RechartsTooltip content={<CustomTooltip />} />
            <Legend />
            <Bar
              dataKey="fees"
              stackId="a"
              fill={theme.palette.primary.main}
              name="Fees"
            />
            <Bar
              dataKey="funding"
              stackId="a"
              fill={theme.palette.secondary.main}
              name="Funding"
            />
          </BarChart>
        );

      case 'cumulative':
        return (
          <LineChart {...commonProps}>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
            <XAxis
              dataKey="date"
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              stroke={theme.palette.text.secondary}
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => `$${value}`}
            />
            <RechartsTooltip content={<CustomTooltip />} />
            <Legend />
            <Line
              type="monotone"
              dataKey="cumulativeFees"
              stroke={theme.palette.primary.main}
              name="Cumulative Fees"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="cumulativeFunding"
              stroke={theme.palette.secondary.main}
              name="Cumulative Funding"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="cumulativeTotal"
              stroke={theme.palette.error.main}
              name="Total Cost"
              strokeWidth={3}
              dot={false}
            />
            <ReferenceLine y={0} stroke={theme.palette.divider} />
          </LineChart>
        );

      default:
        return null;
    }
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
            <Typography variant="h6">Trading Costs Analysis</Typography>
            {cacheHit && (
              <Chip
                label="Cached"
                size="small"
                color="success"
                variant="outlined"
              />
            )}
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Period</InputLabel>
              <Select
                value={days}
                label="Period"
                onChange={(e) => onDaysChange && onDaysChange(e.target.value)}
              >
                <MenuItem value={7}>7 days</MenuItem>
                <MenuItem value={14}>14 days</MenuItem>
                <MenuItem value={30}>30 days</MenuItem>
                <MenuItem value={60}>60 days</MenuItem>
                <MenuItem value={90}>90 days</MenuItem>
              </Select>
            </FormControl>
            
            <ButtonGroup size="small" variant="outlined">
              <Tooltip title="Fees only">
                <Button
                  onClick={() => setChartMode('fees')}
                  variant={chartMode === 'fees' ? 'contained' : 'outlined'}
                >
                  <BarChartIcon />
                </Button>
              </Tooltip>
              <Tooltip title="Funding only">
                <Button
                  onClick={() => setChartMode('funding')}
                  variant={chartMode === 'funding' ? 'contained' : 'outlined'}
                >
                  <LineChartIcon />
                </Button>
              </Tooltip>
              <Tooltip title="Combined view">
                <Button
                  onClick={() => setChartMode('combined')}
                  variant={chartMode === 'combined' ? 'contained' : 'outlined'}
                >
                  <LayersIcon />
                </Button>
              </Tooltip>
              <Tooltip title="Cumulative view">
                <Button
                  onClick={() => setChartMode('cumulative')}
                  variant={chartMode === 'cumulative' ? 'contained' : 'outlined'}
                >
                  <TimelineIcon />
                </Button>
              </Tooltip>
            </ButtonGroup>

            <Tooltip title="Refresh data">
              <IconButton onClick={handleRefresh} disabled={loading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
        }
      />
      
      <CardContent>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Alert severity="error">{error}</Alert>
        ) : displayData ? (
          <ResponsiveContainer width="100%" height={400}>
            {renderChart()}
          </ResponsiveContainer>
        ) : (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="body1" color="text.secondary">
              No data available
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default ChartCard; 