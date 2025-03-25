// Configuration
const CONFIG = {
  API_URL: 'YOUR_FASTAPI_URL',  // e.g., 'https://your-fastapi-server.com'
  API_KEY: 'YOUR_API_KEY'  // Store this securely
};

// Create menu
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('BusyBusy')
    .addItem('Import Projects', 'importProjects')
    .addItem('Import Budgets', 'importBudgets')  // Add this line
    .addToUi();
}

// Helper function to show errors
function showError(message) {
  SpreadsheetApp.getUi().alert('Error: ' + message);
}

// Get API key (you can implement your own secure way)
function getApiKey() {
  return CONFIG.API_KEY;
}

// Test connection
function testConnection() {
  try {
    const response = UrlFetchApp.fetch(CONFIG.API_URL + '/');
    const status = response.getResponseCode();
    if (status === 200) {
      SpreadsheetApp.getUi().alert('Connection successful!');
    } else {
      showError('Connection failed with status: ' + status);
    }
  } catch (error) {
    showError('Connection error: ' + error.message);
  }
}
