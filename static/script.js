// static/script.js - v11 with Validation System
// Multi-invoice + validation system + error highlighting

let uploadedRows = [];
let currentValidationSession = null;

const previewTable = document.getElementById('previewTable');
const generateBtn = document.getElementById('generateBtn');
const jsonOutput = document.getElementById('json-output');
const postBtn = document.getElementById('postBtn');
const activityLog = document.getElementById('activityLog');
const downloadJsonBtn = document.getElementById('downloadJsonBtn');
const lastCreatedBox = document.getElementById('lastCreated');
const lastInvoiceList = document.getElementById('lastInvoiceList');

// New validation UI elements
const validateBtn = document.getElementById('validateBtn');
const validationPanel = document.getElementById('validationPanel');
const validationProgress = document.getElementById('validationProgress');
const validationResults = document.getElementById('validationResults');

function addActivityLog(message, type = 'info') {
  const now = new Date();
  const timeStr = now.toLocaleTimeString();

  const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️', validation: '🔍' };
  const colors = { info: '#8ab4f8', success: '#4caf50', error: '#ff6b6b', warning: '#ffb74d', validation: '#9c27b0' };

  const logEntry = document.createElement('div');
  logEntry.style.color = colors[type] || colors.info;
  logEntry.style.marginBottom = '6px';
  logEntry.textContent = `[${timeStr}] ${icons[type] || ''} ${message}`;

  activityLog.appendChild(logEntry);
  activityLog.scrollTop = activityLog.scrollHeight;
}

function clearPreviewHighlights() {
  const table = document.querySelector("#previewTable table");
  if (!table) return;
  Array.from(table.rows).forEach((row, idx) => {
    Array.from(row.cells).forEach(cell => {
      cell.style.backgroundColor = "";
      cell.style.color = "";
      cell.title = "";
    });
  });
}

function showValidationPanel() {
  if (validationPanel) {
    validationPanel.style.display = 'block';
  }
}

function hideValidationPanel() {
  if (validationPanel) {
    validationPanel.style.display = 'none';
  }
}

function updateValidationProgress(percentage, message) {
  if (validationProgress) {
    const progressBar = validationProgress.querySelector('.progress-bar');
    const progressText = validationProgress.querySelector('.progress-text');
    
    if (progressBar) {
      progressBar.style.width = percentage + '%';
      progressBar.setAttribute('aria-valuenow', percentage);
    }
    
    if (progressText) {
      progressText.textContent = message || `${percentage}% Complete`;
    }
  }
}

function displayValidationResults(results) {
  if (!validationResults) return;
  
  const summary = results.summary || {};
  const errors = results.detailed_errors || {};
  const corrections = results.auto_corrections || [];
  
  let html = `
    <div class="validation-summary mb-3">
      <h5>Validation Summary</h5>
      <div class="row">
        <div class="col-md-6">
          <div class="card">
            <div class="card-body">
              <h6 class="card-title">👥 Customer Validation</h6>
              <p class="mb-1">✅ Passed: ${summary.customer_validation?.passed || 0}</p>
              <p class="mb-1">⚠️ Warnings: ${summary.customer_validation?.warnings || 0}</p>
              <p class="mb-0">❌ Failed: ${summary.customer_validation?.failed || 0}</p>
            </div>
          </div>
        </div>
        <div class="col-md-6">
          <div class="card">
            <div class="card-body">
              <h6 class="card-title">📦 Item Validation</h6>
              <p class="mb-1">✅ Passed: ${summary.item_validation?.passed || 0}</p>
              <p class="mb-1">⚠️ Warnings: ${summary.item_validation?.warnings || 0}</p>
              <p class="mb-0">❌ Failed: ${summary.item_validation?.failed || 0}</p>
            </div>
          </div>
        </div>
      </div>
      
      <div class="mt-3">
        <div class="alert ${summary.can_proceed ? 'alert-success' : 'alert-danger'}">
          <strong>${summary.can_proceed ? '✅ Ready to Proceed' : '❌ Critical Errors Found'}</strong>
          <br>Critical Errors: ${summary.critical_errors || 0} | Warnings: ${summary.total_warnings || 0}
        </div>
      </div>
    </div>
  `;
  
  // Customer Errors
  if (errors.customers && errors.customers.length > 0) {
    html += `
      <div class="validation-errors mb-3">
        <h6>Customer Issues</h6>
        <div class="list-group">
    `;
    
    errors.customers.forEach(error => {
      const alertClass = error.type === 'error' ? 'list-group-item-danger' : 'list-group-item-warning';
      html += `
        <div class="list-group-item ${alertClass}">
          <strong>${error.customer}</strong>: ${error.message}
          ${error.suggestion ? `<br><small>💡 Suggestion: ${error.suggestion}</small>` : ''}
        </div>
      `;
    });
    
    html += `</div></div>`;
  }
  
  // Item Errors
  if (errors.items && errors.items.length > 0) {
    html += `
      <div class="validation-errors mb-3">
        <h6>Item Issues</h6>
        <div class="list-group">
    `;
    
    errors.items.forEach(error => {
      const alertClass = error.type === 'error' ? 'list-group-item-danger' : 'list-group-item-warning';
      html += `
        <div class="list-group-item ${alertClass}">
          <strong>${error.item}</strong>: ${error.message}
          ${error.suggestion ? `<br><small>💡 Suggestion: ${error.suggestion}</small>` : ''}
        </div>
      `;
    });
    
    html += `</div></div>`;
  }
  
  // Auto-corrections
  if (corrections.length > 0) {
    html += `
      <div class="auto-corrections mb-3">
        <h6>🔧 Suggested Auto-corrections</h6>
        <div class="correction-list">
    `;
    
    corrections.forEach((correction, index) => {
      html += `
        <div class="form-check">
          <input class="form-check-input" type="checkbox" id="correction_${index}" checked>
          <label class="form-check-label" for="correction_${index}">
            ${correction.type === 'customer' ? '👥' : '📦'} 
            "${correction.original}" → "${correction.suggested}"
          </label>
        </div>
      `;
    });
    
    html += `
        </div>
        <button type="button" class="btn btn-success btn-sm mt-2" onclick="applyCorrections()">
          Apply Selected Corrections
        </button>
      </div>
    `;
  }
  
  // Action buttons
  html += `
    <div class="validation-actions">
      <button type="button" class="btn btn-primary" onclick="proceedToGenerate()" ${summary.can_proceed ? '' : 'disabled'}>
        📋 Generate JSON
      </button>
      <button type="button" class="btn btn-secondary ms-2" onclick="retryValidation()">
        🔄 Retry Validation
      </button>
      <button type="button" class="btn btn-outline-secondary ms-2" onclick="skipValidation()">
        ⏭️ Skip & Generate
      </button>
    </div>
  `;
  
  validationResults.innerHTML = html;
}

// Upload file (enhanced with validation support)
document.getElementById('uploadBtn').addEventListener('click', () => {
  const fileInput = document.getElementById('fileInput');
  activityLog.innerHTML = '';
  generateBtn.disabled = true;
  postBtn.disabled = true;
  jsonOutput.textContent = '';
  downloadJsonBtn.disabled = true;
  hideLastInvoices();
  hideValidationPanel();

  if (!fileInput.files.length) {
    addActivityLog('Please select a file first.', 'error');
    return;
  }

  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append('file', file);

  addActivityLog('Uploading and processing...', 'info');

  fetch('/upload', { method: 'POST', body: formData })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog(data.error, 'error');
        return;
      }
      uploadedRows = data.rows || [];
      addActivityLog(`File uploaded successfully. Showing first ${Math.min(uploadedRows.length, 5)} rows.`, 'success');

      if (uploadedRows.length === 0) {
        previewTable.innerHTML = '<p>No data found in file.</p>';
        return;
      }

      // Render preview
      let table = '<table class="table table-striped table-bordered"><thead><tr>';
      data.columns.forEach(col => table += `<th>${col}</th>`);
      table += '</tr></thead><tbody>';
      uploadedRows.slice(0,5).forEach(row => {
        table += '<tr>';
        data.columns.forEach(col => table += `<td>${escapeHtml(String(row[col] || ''))}</td>`);
        table += '</tr>';
      });
      table += '</tbody></table>';
      previewTable.innerHTML = table;
      
      // Enable validation button
      if (validateBtn) {
        validateBtn.disabled = false;
      }
      generateBtn.disabled = false;
    })
    .catch(err => addActivityLog('Upload failed: ' + err, 'error'));
});

// Start Validation
if (validateBtn) {
  validateBtn.addEventListener('click', () => {
    startValidation();
  });
}

function startValidation() {
  const apiToken = document.getElementById('apiTokenInput').value.trim();
  const endpoint = document.getElementById('endpointInput').value.trim() || 'https://vrushaliinfotech.com';

  if (!apiToken) {
    addActivityLog('Please enter API token for validation.', 'error');
    return;
  }

  if (uploadedRows.length === 0) {
    addActivityLog('No data to validate.', 'error');
    return;
  }

  addActivityLog('Starting comprehensive validation...', 'validation');
  showValidationPanel();
  updateValidationProgress(10, 'Initializing validation...');

  const columns = uploadedRows.length > 0 ? Object.keys(uploadedRows[0]) : [];

  fetch('/start_validation', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      rows: uploadedRows,
      columns: columns,
      api_token: apiToken,
      endpoint: endpoint
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog(`Validation failed: ${data.error}`, 'error');
        hideValidationPanel();
        return;
      }

      currentValidationSession = data.session_id;
      addActivityLog('Validation completed successfully!', 'validation');
      updateValidationProgress(100, 'Validation completed');

      // Display results
      if (data.validation_result) {
        setTimeout(() => {
          getValidationReport();
        }, 500);
      }
    })
    .catch(err => {
      addActivityLog('Validation request failed: ' + err, 'error');
      hideValidationPanel();
    });
}

function getValidationReport() {
  if (!currentValidationSession) return;

  fetch(`/validation_report/${currentValidationSession}`)
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog(`Failed to get validation report: ${data.error}`, 'error');
        return;
      }

      displayValidationResults(data);
      addActivityLog(`Validation report generated. Found ${data.summary?.critical_errors || 0} critical errors.`, 'validation');
    })
    .catch(err => {
      addActivityLog('Failed to fetch validation report: ' + err, 'error');
    });
}

function applyCorrections() {
  if (!currentValidationSession) return;

  // Collect selected corrections
  const corrections = [];
  const checkboxes = document.querySelectorAll('.correction-list input[type="checkbox"]:checked');
  
  checkboxes.forEach((checkbox, index) => {
    const label = checkbox.nextElementSibling.textContent;
    const match = label.match(/(customer|item).*?"(.+?)" → "(.+?)"/);
    
    if (match) {
      corrections.push({
        type: match[1] === '👥' ? 'customer' : 'item',
        original: match[2],
        suggested: match[3]
      });
    }
  });

  if (corrections.length === 0) {
    addActivityLog('No corrections selected.', 'warning');
    return;
  }

  addActivityLog(`Applying ${corrections.length} corrections...`, 'validation');

  fetch('/apply_corrections', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      session_id: currentValidationSession,
      corrections: corrections
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog(`Failed to apply corrections: ${data.error}`, 'error');
        return;
      }

      addActivityLog(`Applied ${data.applied_corrections} corrections successfully!`, 'success');
      
      // Retry validation after corrections
      retryValidation();
    })
    .catch(err => {
      addActivityLog('Failed to apply corrections: ' + err, 'error');
    });
}

function retryValidation() {
  addActivityLog('Retrying validation...', 'validation');
  startValidation();
}

function proceedToGenerate() {
  addActivityLog('Proceeding to JSON generation...', 'info');
  generateJsonWithValidation();
}

function skipValidation() {
  addActivityLog('Skipping validation and generating JSON...', 'warning');
  hideValidationPanel();
  generateJsonWithValidation(true);
}

// Enhanced Generate JSON with validation integration
function generateJsonWithValidation(skipValidation = false) {
  const company = document.getElementById('companyInput').value.trim() || 'Vrushali Infotech Pvt Ltd';
  const remarks = document.getElementById('remarksInput').value.trim() || 'Generated from Excel Uploader';
  const apiToken = document.getElementById('apiTokenInput').value.trim();
  const endpoint = document.getElementById('endpointInput').value.trim();

  postBtn.disabled = true;
  downloadJsonBtn.disabled = true;
  jsonOutput.textContent = '';
  clearPreviewHighlights();
  hideLastInvoices();

  if (uploadedRows.length === 0) {
    addActivityLog('No data to generate JSON.', 'error');
    return;
  }

  addActivityLog('Generating JSON...', 'info');

  fetch('/generate_json', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      rows: uploadedRows,
      company,
      remarks,
      api_token: apiToken,
      endpoint,
      skip_validation: skipValidation
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        if (data.validation_errors && !skipValidation) {
          addActivityLog('Validation errors found during JSON generation. Please fix them first.', 'error');
          currentValidationSession = data.session_id;
          getValidationReport();
          return;
        }
        addActivityLog(data.error, 'error');
        return;
      }

      addActivityLog('JSON generated successfully.', 'success');
      jsonOutput.textContent = JSON.stringify(data.invoices, null, 2);
      window.generatedInvoices = data.invoices;
      postBtn.disabled = false;
      downloadJsonBtn.disabled = false;
      hideValidationPanel();
    })
    .catch(err => {
      addActivityLog('JSON generation failed: ' + err, 'error');
      postBtn.disabled = true;
    });
}

// Generate JSON (original function - now calls enhanced version)
document.getElementById('generateBtn').addEventListener('click', () => {
  generateJsonWithValidation();
});

// Post invoices (fixed response handling)
document.getElementById('postBtn').addEventListener('click', () => {
  const apiToken = document.getElementById('apiTokenInput').value.trim();
  const endpoint = document.getElementById('endpointInput').value.trim();

  if (!window.generatedInvoices) {
    addActivityLog('No generated invoices to post.', 'error');
    return;
  }
  if (!apiToken) {
    addActivityLog('Please enter API token.', 'error');
    return;
  }
  if (!endpoint) {
    addActivityLog('Please enter API endpoint.', 'error');
    return;
  }

  addActivityLog('Posting invoices to ERPNext...', 'info');

  fetch('/post_invoice', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({invoices: window.generatedInvoices, api_token: apiToken, endpoint})
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog('Error: ' + data.error, 'error');
        return;
      }

      if (data.results) {
        const posted = [];
        const results = data.results;
        
        // Handle different response formats
        if (Array.isArray(results)) {
          // Array format: [{success: true, invoice_no: "INV-001", response: {...}}]
          results.forEach(r => {
            if (r.success) {
              const invoiceNo = r.invoice_no || 'Unknown';
              addActivityLog(`Invoice ${invoiceNo} posted successfully`, 'success');
              posted.push(invoiceNo);
            } else {
              const invoiceNo = r.invoice_no || 'Unknown';
              addActivityLog(`Invoice ${invoiceNo} failed: ${JSON.stringify(r.response)}`, 'error');
            }
          });
        } else if (typeof results === 'object') {
          // Object format: {INV-001: {success: true, response: {...}}}
          Object.keys(results).forEach(invKey => {
            const r = results[invKey];
            if (r.success) {
              addActivityLog(`Invoice ${invKey} posted successfully`, 'success');
              posted.push(invKey);
            } else {
              addActivityLog(`Invoice ${invKey} failed: ${JSON.stringify(r.response || r.error)}`, 'error');
            }
          });
        }
        
        if (posted.length > 0) {
          showLastInvoices(posted);
          addActivityLog(`Successfully posted ${posted.length} invoice(s)`, 'success');
        }
      } else {
        addActivityLog('No results returned from server', 'warning');
      }
    })
    .catch(err => addActivityLog('Post failed: ' + err, 'error'));
});

// Download JSON (unchanged)
downloadJsonBtn.addEventListener('click', () => {
  if (!window.generatedInvoices) return;
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(window.generatedInvoices, null, 2));
  const dlAnchor = document.createElement('a');
  dlAnchor.setAttribute("href", dataStr);
  const fileName = `sales_invoices_${new Date().toISOString().slice(0,10)}.json`;
  dlAnchor.setAttribute("download", fileName);
  document.body.appendChild(dlAnchor);
  dlAnchor.click();
  dlAnchor.remove();
});

function showLastInvoices(list) {
  lastInvoiceList.innerHTML = "";
  list.forEach(no => {
    const li = document.createElement("li");
    li.textContent = no;
    lastInvoiceList.appendChild(li);
  });
  lastCreatedBox.style.display = "block";
}

function hideLastInvoices() {
  lastInvoiceList.innerHTML = "";
  lastCreatedBox.style.display = "none";
}

function escapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}