import React, { useState, useEffect } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Typography,
  Box,
  CircularProgress,
  Alert,
  IconButton,
  Tooltip,
  Chip,
  useTheme,
  alpha,
  LinearProgress,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  TrendingUp,
} from '@mui/icons-material';
import { getTradingVolumes } from '../utils/api';
import { formatNumber, formatCurrency } from '../utils/formatters';
import { format } from 'date-fns';

const VolumeCard = () => {
  const theme = useTheme();
  const [volumes, setVolumes] = useState([]);
  const [totalVolume, setTotalVolume] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const loadVolumes = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await getTradingVolumes(30);
      const data = response.data;
      
      if (data && data.data) {
        setVolumes(data.data);
        setTotalVolume(data.total_volume || 0);
        setLastUpdate(new Date());
      }
    } catch (error) {
      console.error('Error loading volumes:', error);
      setError('Failed to load trading volumes');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVolumes();
  }, []);

  const handleRefresh = () => {
    loadVolumes();
  };

  const getRowColor = (volume) => {
    if (volume > 500000) { // $500k+
      return alpha(theme.palette.primary.main, 0.08);
    } else if (volume > 100000) { // $100k+
      return alpha(theme.palette.info.main, 0.08);
    }
    return 'transparent';
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
            <Typography variant="h6">Trading Volume (30 Days)</Typography>
            {totalVolume > 0 && (
              <Chip
                icon={<TrendingUp />}
                label={`Total: ${formatCurrency(totalVolume)}`}
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
            <Tooltip title="Refresh volumes">
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
        ) : volumes.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="body1" color="text.secondary">
              No trading volume data available
            </Typography>
          </Box>
        ) : (
          <TableContainer 
            component={Paper} 
            variant="outlined"
            sx={{ maxHeight: '600px' }}
          >
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Date</TableCell>
                  <TableCell align="right">Volume (USD)</TableCell>
                  <TableCell align="center">Visual</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {volumes.map((item) => {
                  const maxVolume = Math.max(...volumes.map(v => v.volume));
                  const percentage = maxVolume > 0 ? (item.volume / maxVolume) * 100 : 0;
                  
                  return (
                    <TableRow
                      key={item.date}
                      sx={{
                        backgroundColor: getRowColor(item.volume),
                        '&:hover': {
                          backgroundColor: alpha(theme.palette.action.hover, 0.08),
                        },
                      }}
                    >
                      <TableCell>
                        <Typography variant="body2">
                          {format(new Date(item.date), 'MMM dd, yyyy')}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2" fontWeight="medium">
                          {formatCurrency(item.volume)}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Box
                            sx={{
                              width: `${percentage}%`,
                              minWidth: 4,
                              height: 20,
                              backgroundColor: theme.palette.primary.main,
                              borderRadius: 1,
                              transition: 'all 0.3s ease',
                            }}
                          />
                          <Typography variant="caption" color="text.secondary">
                            {percentage.toFixed(0)}%
                          </Typography>
                        </Box>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
};

export default VolumeCard; 