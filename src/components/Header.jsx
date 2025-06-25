import React from 'react';
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
} from '@mui/icons-material';
import { formatPercentage } from '../utils/formatters';

const Header = ({ darkMode, toggleDarkMode, feeInfo, onAuthClick, view, onViewChange }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

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
        {/* Logo and Title */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Avatar
            src="/image.png"
            alt="Kraken"
            sx={{ width: 36, height: 36 }}
          />
          <Typography
            variant="h6"
            component="h1"
            sx={{
              fontWeight: 600,
              background: 'linear-gradient(45deg, #2196F3 30%, #21CBF3 90%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              display: { xs: 'none', sm: 'block' },
            }}
          >
            Kraken Dashboard
          </Typography>
        </Box>

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