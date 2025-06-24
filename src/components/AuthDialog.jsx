import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Alert,
  Box,
  Typography,
  CircularProgress,
  IconButton,
  InputAdornment,
} from '@mui/material';
import {
  Visibility,
  VisibilityOff,
  Security as SecurityIcon,
} from '@mui/icons-material';
import { setCredentials } from '../utils/api';

const AuthDialog = ({ open, onClose, onSuccess }) => {
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [showSecret, setShowSecret] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!apiKey || !apiSecret) {
      setError('Please enter both API key and secret');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await setCredentials(apiKey, apiSecret);
      if (response.data.success) {
        onSuccess();
        // Clear form
        setApiKey('');
        setApiSecret('');
      } else {
        setError(response.data.error || 'Failed to save credentials');
      }
    } catch (error) {
      setError(error.response?.data?.error || 'Failed to save credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 2,
        },
      }}
    >
      <form onSubmit={handleSubmit}>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pb: 1 }}>
          <SecurityIcon color="primary" />
          <Typography variant="h6" component="span">
            Kraken API Configuration
          </Typography>
        </DialogTitle>
        
        <DialogContent>
          <Box sx={{ mb: 2 }}>
            <Alert severity="info" sx={{ mb: 3 }}>
              Please enter your Kraken Futures API credentials. You can create API keys from your{' '}
              <a
                href="https://futures.kraken.com/trade/settings/api"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'inherit', fontWeight: 'bold' }}
              >
                Kraken Futures settings
              </a>
              .
            </Alert>
          </Box>

          <TextField
            fullWidth
            label="API Key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            margin="normal"
            variant="outlined"
            disabled={loading}
            autoFocus
            required
          />

          <TextField
            fullWidth
            label="API Secret"
            type={showSecret ? 'text' : 'password'}
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            margin="normal"
            variant="outlined"
            disabled={loading}
            required
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowSecret(!showSecret)}
                    edge="end"
                    disabled={loading}
                  >
                    {showSecret ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </DialogContent>

        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={onClose} disabled={loading} color="inherit">
            Cancel
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={loading || !apiKey || !apiSecret}
            sx={{ minWidth: 120 }}
          >
            {loading ? (
              <CircularProgress size={24} color="inherit" />
            ) : (
              'Connect'
            )}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};

export default AuthDialog; 