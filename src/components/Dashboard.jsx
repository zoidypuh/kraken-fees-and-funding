import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Grid,
  Paper,
  Toolbar,
  useTheme,
  useMediaQuery,
  Fade,
  Fab,
  Zoom,
} from '@mui/material';
import { KeyboardArrowUp } from '@mui/icons-material';
import Header from './Header';
import PositionsCard from './PositionsCard';
import ChartCard from './ChartCard';
import SummaryCards from './SummaryCards';
import VolumeCard from './VolumeCard';
import { getFeeInfo } from '../utils/api';

const Dashboard = ({ darkMode, toggleDarkMode, authenticated, onAuthRequired }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [feeInfo, setFeeInfo] = useState(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [positionsKey, setPositionsKey] = useState(0);
  const [chartDays, setChartDays] = useState(7);
  const [chartData, setChartData] = useState(null);
  const [view, setView] = useState('positions'); // Default to positions view

  useEffect(() => {
    if (authenticated) {
      loadFeeInfo();
    }
  }, [authenticated]);

  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 300);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const loadFeeInfo = async () => {
    try {
      const response = await getFeeInfo();
      setFeeInfo(response.data);
    } catch (error) {
      console.error('Error loading fee info:', error);
    }
  };

  const handleScrollTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const refreshPositions = () => {
    setPositionsKey(prev => prev + 1);
  };

  if (!authenticated) {
    return null;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header
        darkMode={darkMode}
        toggleDarkMode={toggleDarkMode}
        feeInfo={feeInfo}
        onAuthClick={onAuthRequired}
        view={view}
        onViewChange={setView}
      />
      
      <Toolbar /> {/* Spacing for fixed header */}
      
      <Box
        sx={{
          flex: 1,
          width: '100%',
          overflow: 'hidden',
          mt: 3,
        }}
      >
        <Fade in timeout={800}>
          <Box sx={{ width: '100%' }}>
            {view === 'positions' ? (
              /* Positions View */
              <Box sx={{ mb: 3 }}>
                <PositionsCard 
                  key={positionsKey}
                  onRefresh={refreshPositions}
                />
              </Box>
            ) : view === 'trading' ? (
              /* Trading Cost Activity View */
              <>
                {/* Summary Cards - Above Chart */}
                <Box sx={{ 
                  mb: 3,
                  display: 'flex',
                  justifyContent: 'center',
                  px: { xs: 2, sm: 3, md: 4 },
                }}>
                  <Box sx={{ 
                    width: { xs: '100%', sm: '90%', md: '80%', lg: '60%' },
                    maxWidth: '900px',
                    display: 'flex',
                    justifyContent: 'center'
                  }}>
                    <SummaryCards 
                      authenticated={authenticated} 
                      days={chartDays}
                      chartData={chartData}
                    />
                  </Box>
                </Box>

                {/* Chart Section */}
                <Box sx={{ mb: 3 }}>
                  <ChartCard 
                    onDaysChange={setChartDays}
                    days={chartDays}
                    onDataLoad={setChartData}
                  />
                </Box>
              </>
            ) : (
              /* Trading Volume View */
              <Box sx={{ mb: 3 }}>
                <VolumeCard />
              </Box>
            )}
          </Box>
        </Fade>
      </Box>

      {/* Scroll to top button */}
      <Zoom in={showScrollTop}>
        <Fab
          color="primary"
          size="small"
          onClick={handleScrollTop}
          sx={{
            position: 'fixed',
            bottom: { xs: 16, sm: 24 },
            right: { xs: 16, sm: 24 },
            zIndex: theme.zIndex.fab,
          }}
        >
          <KeyboardArrowUp />
        </Fab>
      </Zoom>
    </Box>
  );
};

export default Dashboard; 