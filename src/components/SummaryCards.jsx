import React, { useState, useEffect } from 'react';
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  Skeleton,
  useTheme,
  alpha,
} from '@mui/material';
import {
  AttachMoney,
  TrendingDown,
  ShowChart,
  AccountBalance,
} from '@mui/icons-material';
import { getChartData } from '../utils/api';
import { formatCurrency } from '../utils/formatters';

const SummaryCard = ({ title, value, icon, color, loading }) => {
  const theme = useTheme();

  return (
    <Card
      sx={{
        height: '100%',
        borderTop: `4px solid ${theme.palette[color].main}`,
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: theme.shadows[8],
        },
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 48,
              height: 48,
              borderRadius: 2,
              backgroundColor: alpha(theme.palette[color].main, 0.1),
              color: theme.palette[color].main,
              mr: 2,
            }}
          >
            {icon}
          </Box>
          <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 500 }}>
            {title}
          </Typography>
        </Box>
        {loading ? (
          <Skeleton variant="text" width="60%" height={40} />
        ) : (
          <Typography variant="h4" sx={{ fontWeight: 600, color: theme.palette[color].main }}>
            {value}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

const SummaryCards = ({ authenticated }) => {
  const [loading, setLoading] = useState(true);
  const [summaryData, setSummaryData] = useState({
    totalFees: 0,
    totalFunding: 0,
    totalCost: 0,
    netPnL: 0,
  });

  useEffect(() => {
    if (authenticated) {
      loadSummaryData();
    }
  }, [authenticated]);

  const loadSummaryData = async () => {
    try {
      setLoading(true);
      const response = await getChartData(90); // Get 90 days of data
      const data = response.data;

      // Calculate totals
      const totalFees = data.fees.reduce((sum, val) => sum + val, 0);
      const totalFunding = data.funding.reduce((sum, val) => sum + val, 0);
      const totalCost = totalFees + totalFunding;

      setSummaryData({
        totalFees,
        totalFunding,
        totalCost,
        netPnL: -totalCost, // Negative because these are costs
      });
    } catch (error) {
      console.error('Error loading summary data:', error);
    } finally {
      setLoading(false);
    }
  };

  const cards = [
    {
      title: 'Total Fees (90d)',
      value: formatCurrency(Math.abs(summaryData.totalFees)),
      icon: <AttachMoney />,
      color: 'primary',
    },
    {
      title: 'Total Funding (90d)',
      value: formatCurrency(Math.abs(summaryData.totalFunding)),
      icon: <TrendingDown />,
      color: 'secondary',
    },
    {
      title: 'Total Cost (90d)',
      value: formatCurrency(Math.abs(summaryData.totalCost)),
      icon: <ShowChart />,
      color: 'warning',
    },
    {
      title: 'Net Impact (90d)',
      value: formatCurrency(summaryData.netPnL),
      icon: <AccountBalance />,
      color: summaryData.netPnL >= 0 ? 'success' : 'error',
    },
  ];

  return (
    <Grid container spacing={3}>
      {cards.map((card, index) => (
        <Grid item xs={12} sm={6} md={3} key={index}>
          <SummaryCard
            title={card.title}
            value={card.value}
            icon={card.icon}
            color={card.color}
            loading={loading}
          />
        </Grid>
      ))}
    </Grid>
  );
};

export default SummaryCards; 