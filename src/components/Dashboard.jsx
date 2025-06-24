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
import { getFeeInfo } from '../utils/api';

const Dashboard = ({ darkMode, toggleDarkMode, authenticated, onAuthRequired }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [feeInfo, setFeeInfo] = useState(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [positionsKey, setPositionsKey] = useState(0);

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
      />
      
      <Toolbar /> {/* Spacing for fixed header */}
      
      <Box sx={{ flex: 1 }}>
        <Fade in timeout={800}>
          <Box>
            {/* Full-width Chart Container with Summary Cards Overlay */}
            <Box
              sx={{
                position: 'relative',
                width: '100%',
                backgroundColor: theme.palette.background.default,
                overflow: 'hidden',
              }}
            >
              {/* Chart takes full width */}
              <Box sx={{ width: '100%' }}>
                <ChartCard />
              </Box>
              
              {/* Summary Cards Overlay */}
              <Box
                sx={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  padding: { xs: 2, sm: 3, md: 4 },
                  pointerEvents: 'none', // Allow chart interactions below
                  '& > *': {
                    pointerEvents: 'auto', // But allow card interactions
                  },
                }}
              >
                <SummaryCards authenticated={authenticated} />
              </Box>
            </Box>

            {/* Positions Section - Still in Container */}
            <Container
              maxWidth="xl"
              sx={{
                py: { xs: 2, sm: 3, md: 4 },
                px: { xs: 2, sm: 3 },
              }}
            >
              <PositionsCard 
                key={positionsKey}
                onRefresh={refreshPositions}
              />
            </Container>
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