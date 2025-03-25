function fetchBudgetsFromApi(isArchived) {
  const apiKey = getApiKey();
  if (!apiKey) {
    showError('API key not configured');
    return [];
  }

  const url = `${CONFIG.API_URL}/api/budgets?is_archived=${isArchived}`;
  
  const options = {
    method: 'get',
    headers: { 
      'key-authorization': apiKey,
      'Content-Type': 'application/json'
    },
    muteHttpExceptions: true
  };

  try {
    const response = UrlFetchApp.fetch(url, options);
    const responseCode = response.getResponseCode();

    if (responseCode !== 200) {
      showError(`API returned status ${responseCode}`);
      return [];
    }

    const budgets = JSON.parse(response.getContentText());
    return budgets || [];

  } catch (error) {
    showError(`Error fetching budgets: ${error.message}`);
    return [];
  }
}

function importBudgets() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  const importSheet = sheet.getSheetByName("Budgets_Import");

  if (!importSheet) {
    showError("Budgets_Import sheet not found.");
    return;
  }

  // Fetch both active and archived budgets
  const activeBudgets = fetchBudgetsFromApi(false);
  const archivedBudgets = fetchBudgetsFromApi(true);

  if (activeBudgets.length === 0 && archivedBudgets.length === 0) {
    showError("No budget data available.");
    return;
  }

  // Clear old data while keeping headers (Row 1)
  if (importSheet.getLastRow() > 1) {
    importSheet.getRange(2, 1, importSheet.getLastRow() - 1, importSheet.getLastColumn()).clearContent();
  }

  // Write active budgets
  if (activeBudgets.length > 0) {
    const activeRows = activeBudgets.map(budget => [
      budget.id,
      budget.project_id,
      budget.project_title,
      budget.cost_code_id || '',
      budget.cost_code_title || '',
      budget.labor_hours || 0,
      budget.labor_cost || 0,
      budget.progress_value || 0,
      budget.quantity || 0,
      budget.status
    ]);
    
    importSheet.getRange(2, 1, activeRows.length, activeRows[0].length).setValues(activeRows);
  }

  // Add separator
  const separatorRow = [["", "", "", "", "", "", "", "", "", "-------------------"]];
  importSheet.getRange(2 + activeBudgets.length, 1, 1, separatorRow[0].length).setValues(separatorRow);

  // Write archived budgets
  if (archivedBudgets.length > 0) {
    const archivedRows = archivedBudgets.map(budget => [
      budget.id,
      budget.project_id,
      budget.project_title,
      budget.cost_code_id || '',
      budget.cost_code_title || '',
      budget.labor_hours || 0,
      budget.labor_cost || 0,
      budget.progress_value || 0,
      budget.quantity || 0,
      budget.status
    ]);
    
    importSheet.getRange(3 + activeBudgets.length, 1, archivedRows.length, archivedRows[0].length).setValues(archivedRows);
  }

  SpreadsheetApp.getUi().alert("Budgets imported successfully!");
}
