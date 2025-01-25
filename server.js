const express = require('express');
const fetch = require('node-fetch'); // or `undici`/`axios`, up to you

const app = express();
const PORT = 3000;

// Basic route to fetch Jupiter Perps positions for a given wallet
app.get('/positions', async (req, res) => {
  try {
    // Hardcode a walletAddress for now, or pull from req.query
    const walletAddress = '6vMjsGU63evYuwwGsDHBRnKs1stALR7SYN5V57VZLXca';

    // Construct the Jupiter API URL
    const apiUrl = `https://perps-api.jup.ag/v1/positions?walletAddress=${walletAddress}&showTpslRequests=true`;

    // Fetch from Jupiter's Perps API
    const response = await fetch(apiUrl);
    const data = await response.json();

    // Return data as JSON
    res.json(data);

  } catch (error) {
    console.error('Error fetching positions:', error);
    res.status(500).json({ error: 'Failed to fetch positions' });
  }
});

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});