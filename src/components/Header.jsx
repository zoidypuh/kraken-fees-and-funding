import React, { useState, useEffect } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Box,
  Chip,
  Avatar,
  Tooltip,
  useTheme,
  useMediaQuery,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import {
  Brightness4,
  Brightness7,
  Key as KeyIcon,
  TrendingUp,
  TrendingDown,
  ShowChart,
  TableChart,
  CurrencyBitcoin,
} from '@mui/icons-material';
import { formatPercentage, formatCurrency } from '../utils/formatters';
import { getTicker } from '../utils/api';

const Header = ({ darkMode, toggleDarkMode, feeInfo, onAuthClick, view, onViewChange }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [btcPrice, setBtcPrice] = useState(null);
  const [btcFeeCalculation, setBtcFeeCalculation] = useState(null);

  useEffect(() => {
    const fetchBtcPrice = async () => {
      try {
        const response = await getTicker('PF_XBTUSD');
        console.log('Ticker response:', response.data);
        
        if (response.data && response.data.markPrice) {
          const price = parseFloat(response.data.markPrice);
          
          if (isNaN(price)) {
            console.error('Invalid BTC price:', response.data.markPrice);
            return;
          }
          
          setBtcPrice(price);
          
          // Calculate fees if we have fee info
          if (feeInfo && feeInfo.maker_fee != null) {
            const btcAmount = 10;
            const priceIncrease = 100;
            
            const buyPrice = price;
            const sellPrice = price + priceIncrease;
            
            const buyOrderValue = btcAmount * buyPrice;
            const sellOrderValue = btcAmount * sellPrice;
            
            // Ensure maker_fee is a number
            const makerFeeRate = parseFloat(feeInfo.maker_fee) || 0;
            
            // Debug logging
            console.log('BTC Fee Calculation:', {
              price,
              makerFeeRate,
              buyOrderValue,
              sellOrderValue,
              feeInfo
            });
            
            // Calculate fees
            const buyFee = buyOrderValue * makerFeeRate;
            const sellFee = sellOrderValue * makerFeeRate;
            const totalFees = buyFee + sellFee;
            
            // Calculate profit
            const grossProfit = (sellPrice - buyPrice) * btcAmount; // Should be $1000
            const netProfit = grossProfit - totalFees;
            
            setBtcFeeCalculation({
              buyFee,
              sellFee,
              totalFees,
              buyPrice,
              sellPrice,
              grossProfit,
              netProfit
            });
          }
        }
      } catch (error) {
        console.error('Error fetching BTC price:', error);
      }
    };

    // Fetch on mount and when fee info changes
    if (feeInfo) {
      fetchBtcPrice();
      
      // Refresh every 30 seconds
      const interval = setInterval(fetchBtcPrice, 30000);
      return () => clearInterval(interval);
    }
  }, [feeInfo]);

  return (
    <AppBar
      position="fixed"
      elevation={3}
      sx={{
        backdropFilter: 'blur(8px)',
        backgroundColor: theme.palette.mode === 'dark'
          ? 'rgba(18, 18, 18, 0.95)'
          : 'rgba(255, 255, 255, 0.98)',
        borderBottom: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Toolbar sx={{ gap: 2 }}>
        {/* Logo only */}
        <Avatar
          src="/image.png"
          alt="Kraken"
          sx={{ width: 36, height: 36 }}
        />

        {/* View Toggle - Centered */}
        <Box sx={{ flexGrow: 1, display: 'flex', justifyContent: 'center' }}>
          <ToggleButtonGroup
            value={view}
            exclusive
            onChange={(event, newView) => {
              if (newView !== null) {
                onViewChange(newView);
              }
            }}
            size="small"
            sx={{
              borderRadius: 2,
            }}
          >
            <ToggleButton 
              value="positions" 
              sx={{ px: 2 }}
            >
              <TableChart sx={{ mr: 1 }} />
              Open Positions
            </ToggleButton>
            <ToggleButton 
              value="trading" 
              sx={{ px: 2 }}
            >
              <ShowChart sx={{ mr: 1 }} />
              Trading Cost Activity
            </ToggleButton>
            <ToggleButton 
              value="volume" 
              sx={{ px: 2 }}
            >
              <TrendingUp sx={{ mr: 1 }} />
              Trading Volume
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>

        {/* Right side - Fee Info and Actions */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {/* Fee Info */}
          {feeInfo && !isMobile && (
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <Tooltip title="30-day trading volume">
                <Chip
                  icon={<TrendingUp fontSize="small" />}
                  label={`Vol: ${feeInfo.volume_30d_formatted}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontFamily: 'monospace' }}
                />
              </Tooltip>
              {feeInfo && !btcFeeCalculation && (
                <Chip
                  icon={<CurrencyBitcoin fontSize="small" />}
                  label="Loading BTC..."
                  size="small"
                  variant="outlined"
                  sx={{ fontFamily: 'monospace' }}
                />
              )}
              {btcFeeCalculation && (
                <Tooltip title={
                  <Box>
                    <div style={{ marginBottom: '4px', fontWeight: 'bold' }}>10 BTC Trade Scenario:</div>
                    <div>Buy at {formatCurrency(btcFeeCalculation.buyPrice)}: Fee = {formatCurrency(btcFeeCalculation.buyFee)}</div>
                    <div>Sell at {formatCurrency(btcFeeCalculation.sellPrice)}: Fee = {formatCurrency(btcFeeCalculation.sellFee)}</div>
                    <div style={{ marginTop: '4px', borderTop: '1px solid rgba(255,255,255,0.3)', paddingTop: '4px' }}>
                      Gross Profit: {formatCurrency(btcFeeCalculation.grossProfit)}
                    </div>
                    <div>Total Fees: {formatCurrency(btcFeeCalculation.totalFees)}</div>
                    <div style={{ fontWeight: 'bold', color: btcFeeCalculation.netProfit > 0 ? '#4caf50' : '#f44336' }}>
                      Net Profit: {formatCurrency(btcFeeCalculation.netProfit)}
                    </div>
                  </Box>
                }>
                  <Chip
                    icon={<CurrencyBitcoin fontSize="small" />}
                    label={`10 BTC +$100: Net ${formatCurrency(btcFeeCalculation.netProfit)}`}
                    size="small"
                    variant="outlined"
                    color={btcFeeCalculation.netProfit > 0 ? "success" : "error"}
                    sx={{ 
                      fontFamily: 'monospace',
                      borderWidth: '2px',
                      '&:hover': {
                        borderWidth: '2px',
                      }
                    }}
                  />
                </Tooltip>
              )}
              <Tooltip title="Maker fee rate">
                <Chip
                  label={`Maker: ${feeInfo.maker_fee_percentage}`}
                  size="small"
                  color="success"
                  sx={{ fontFamily: 'monospace' }}
                />
              </Tooltip>
              <Tooltip title="Taker fee rate">
                <Chip
                  label={`Taker: ${feeInfo.taker_fee_percentage}`}
                  size="small"
                  color="warning"
                  sx={{ fontFamily: 'monospace' }}
                />
              </Tooltip>
            </Box>
          )}

          {/* Actions */}
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Tooltip title="API Configuration">
              <IconButton
                onClick={onAuthClick}
                color="inherit"
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  width: 40,
                  height: 40,
                }}
              >
                <KeyIcon />
              </IconButton>
            </Tooltip>

            <Tooltip title={darkMode ? 'Light mode' : 'Dark mode'}>
              <IconButton
                onClick={toggleDarkMode}
                color="inherit"
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  width: 40,
                  height: 40,
                }}
              >
                {darkMode ? <Brightness7 /> : <Brightness4 />}
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header; 