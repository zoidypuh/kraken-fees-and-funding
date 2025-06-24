import React, { useState, useEffect, useMemo } from 'react';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { LocalizationProvider } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import theme from './theme/theme';
import darkTheme from './theme/darkTheme';
import Dashboard from './components/Dashboard';
import AuthDialog from './components/AuthDialog';
import { checkAuthStatus } from './utils/api';

function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [authDialogOpen, setAuthDialogOpen] = useState(false);

  const currentTheme = useMemo(
    () => (darkMode ? darkTheme : theme),
    [darkMode]
  );

  useEffect(() => {
    // Load dark mode preference
    const savedDarkMode = localStorage.getItem('darkMode') === 'true';
    setDarkMode(savedDarkMode);

    // Check authentication status
    checkAuth();

    // Listen for unauthorized events
    window.addEventListener('unauthorized', handleUnauthorized);
    return () => window.removeEventListener('unauthorized', handleUnauthorized);
  }, []);

  const checkAuth = async () => {
    try {
      const response = await checkAuthStatus();
      setAuthenticated(response.data.authenticated);
      if (!response.data.authenticated) {
        setAuthDialogOpen(true);
      }
    } catch (error) {
      console.error('Error checking auth status:', error);
      setAuthDialogOpen(true);
    } finally {
      setLoading(false);
    }
  };

  const handleUnauthorized = () => {
    setAuthenticated(false);
    setAuthDialogOpen(true);
  };

  const toggleDarkMode = () => {
    const newDarkMode = !darkMode;
    setDarkMode(newDarkMode);
    localStorage.setItem('darkMode', newDarkMode.toString());
  };

  const handleAuthSuccess = () => {
    setAuthenticated(true);
    setAuthDialogOpen(false);
  };

  if (loading) {
    return null; // Or a loading spinner
  }

  return (
    <ThemeProvider theme={currentTheme}>
      <LocalizationProvider dateAdapter={AdapterDateFns}>
        <CssBaseline />
        <Dashboard
          darkMode={darkMode}
          toggleDarkMode={toggleDarkMode}
          authenticated={authenticated}
          onAuthRequired={() => setAuthDialogOpen(true)}
        />
        <AuthDialog
          open={authDialogOpen}
          onClose={() => setAuthDialogOpen(false)}
          onSuccess={handleAuthSuccess}
        />
      </LocalizationProvider>
    </ThemeProvider>
  );
}

export default App; 