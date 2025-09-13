// static/script.js (v11) - Fixed forEach error + hardcoded credentials
// Multi-invoice + error highlighting + improved logs

let uploadedRows = [];

const previewTable = document.getElementById('previewTable');
const generateBtn = document.getElementById('generateBtn');
const jsonOutput = document.getElementById('json-output');
const postBtn = document.getElementById('postBtn');
const activityLog = document.getElementById('activityLog');
const downloadJsonBtn = document.getElementById('downloadJsonBtn');
const lastCreatedBox = document.getElementById('lastCreated');
const lastInvoiceList = document.getElementById('lastInvoiceList'); // list for posted invoices

// Pre-fill the hardcoded values
document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('companyInput').value = 'Vrushali Infotech Pvt Ltd';
  document.getElementById('apiTokenInput').value = '6b9c2cfc6e6aaaf:a362001e6dfee4c';
  document.getElementById('endpointInput').value = 'https://vrushaliinfotech.com/api/resource/Sales%20Invoice';
});

function addActivityLog(message, type = 'info') {
  const now = new Date();
  const timeStr = now.toLocaleTimeString();

  const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
  const colors = { info: '#8ab4f8', success: '#4caf50', error: '#ff6b6b', warning: '#ffb74d' };

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

// Upload file
document.getElementById('uploadBtn').addEventListener('click', () => {
  const fileInput = document.getElementById('fileInput');
  activityLog.innerHTML = '';
  generateBtn.disabled = true;
  postBtn.disabled = true;
  jsonOutput.textContent = '';
  downloadJsonBtn.disabled = true;
  hideLastInvoices();

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
        generateBtn.disabled = true;
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
      generateBtn.disabled = false;
    })
    .catch(err => addActivityLog('Upload failed: ' + err, 'error'));
});

// Generate JSON
document.getElementById('generateBtn').addEventListener('click', () => {
  const company = document.getElementById('companyInput').value.trim() || 'Vrushali Infotech Pvt Ltd';
  const remarks = document.getElementById('remarksInput').value.trim() || 'Generated from Excel Uploader';

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
    body: JSON.stringify({rows: uploadedRows, company, remarks})
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog(data.error, 'error');
        return;
      }

      addActivityLog('JSON generated successfully.', 'success');
      jsonOutput.textContent = JSON.stringify(data.invoices, null, 2);
      window.generatedInvoices = data.invoices; // multiple invoices
      postBtn.disabled = false;
      downloadJsonBtn.disabled = false;
    })
    .catch(err => {
      addActivityLog('JSON generation failed: ' + err, 'error');
      postBtn.disabled = true;
    });
});

// Post invoices
document.getElementById('postBtn').addEventListener('click', () => {
  const apiToken = document.getElementById('apiTokenInput').value.trim();
  const endpoint = document.getElementById('endpointInput').value.trim();

  if (!window.generatedInvoices) {
    addActivityLog('No generated invoices to post.', 'error');
    return;
  }

  addActivityLog('Posting invoices to ERPNext...', 'info');

  fetch('/post_invoice', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      invoices: window.generatedInvoices, 
      api_token: apiToken || undefined,  // Let backend use default if empty
      endpoint: endpoint || undefined    // Let backend use default if empty
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog('Error: ' + data.error, 'error');
        return;
      }

      if (data.results) {
        const posted = [];
        // data.results is an object, not array - iterate over key-value pairs
        Object.entries(data.results).forEach(([invKey, result]) => {
          const invoiceNo = result.invoice_no || invKey;
          if (result.success) {
            addActivityLog(`Invoice ${invoiceNo} posted successfully!`, 'success');
            posted.push(invoiceNo);
            
            // Log response details if available
            if (result.response && result.response.data) {
              addActivityLog(`  → Name: ${result.response.data.name || 'N/A'}`, 'info');
            }
          } else {
            const errorMsg = result.error || (result.response && result.response.response_text) || 'Unknown error';
            addActivityLog(`Invoice ${invoiceNo} failed: ${errorMsg}`, 'error');
            
            // Log status code if available
            if (result.response && result.response.status_code) {
              addActivityLog(`  → Status: ${result.response.status_code}`, 'warning');
            }
          }
        });
        
        if (posted.length > 0) {
          showLastInvoices(posted);
          addActivityLog(`Successfully posted ${posted.length} invoice(s)!`, 'success');
        }
      }
    })
    .catch(err => addActivityLog('Post failed: ' + err, 'error'));
});

// Download JSON
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