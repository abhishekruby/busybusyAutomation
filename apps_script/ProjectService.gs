function fetchProjectsFromApi(isArchived) {
  const apiKey = getApiKey();
  if (!apiKey) {
    showError('API key not configured');
    return [];
  }

  const timezone = Session.getScriptTimeZone();
  const url = `${CONFIG.API_URL}/api/projects?is_archived=${isArchived}&timezone=${timezone}`;
  
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

    const projects = JSON.parse(response.getContentText());
    return projects || [];

  } catch (error) {
    showError(`Error fetching projects: ${error.message}`);
    return [];
  }
}

function importProjects() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  const importSheet = sheet.getSheetByName("Projects_Import");

  if (!importSheet) {
    showError("Projects_Import sheet not found.");
    return;
  }

  // Fetch both active and archived projects
  const activeProjects = fetchProjectsFromApi(false);
  const archivedProjects = fetchProjectsFromApi(true);

  if (activeProjects.length === 0 && archivedProjects.length === 0) {
    showError("No project data available.");
    return;
  }

  // Clear old data while keeping headers (Row 1)
  if (importSheet.getLastRow() > 1) {
    importSheet.getRange(2, 1, importSheet.getLastRow() - 1, importSheet.getLastColumn()).clearContent();
  }

  // Write active projects
  if (activeProjects.length > 0) {
    const activeRows = activeProjects.map(project => [
      project.id,
      project.number,
      project.customer,
      project.address1,
      project.address2,
      project.city,
      project.state,
      project.postal_code,
      project.phone,
      ...project.project_names,
      project.group_name,
      project.latitude,
      project.longitude,
      project.has_reminder,
      project.location_radius,
      project.additional_info,
      project.created_on,
      project.updated_on,
      project.requires_gps,
      project.requires_gps_children,
      project.status
    ]);
    
    importSheet.getRange(2, 1, activeRows.length, activeRows[0].length).setValues(activeRows);
  }

  // Add separator
  const separatorRow = [["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "-------------------"]];
  importSheet.getRange(2 + activeProjects.length, 1, 1, separatorRow[0].length).setValues(separatorRow);

  // Write archived projects
  if (archivedProjects.length > 0) {
    const archivedRows = archivedProjects.map(project => [
      // Same mapping as active projects
      project.id,
      project.number,
      project.customer,
      project.address1,
      project.address2,
      project.city,
      project.state,
      project.postal_code,
      project.phone,
      ...project.project_names,
      project.group_name,
      project.latitude,
      project.longitude,
      project.has_reminder,
      project.location_radius,
      project.additional_info,
      project.created_on,
      project.updated_on,
      project.requires_gps,
      project.requires_gps_children,
      project.status
    ]);
    
    importSheet.getRange(3 + activeProjects.length, 1, archivedRows.length, archivedRows[0].length).setValues(archivedRows);
  }

  SpreadsheetApp.getUi().alert("Projects imported successfully!");
}
