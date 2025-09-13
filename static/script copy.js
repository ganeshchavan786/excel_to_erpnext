// static/script.js
// Place this file under your project's static/ folder.

let uploadedRows = [];

const previewTable = document.getElementById('previewTable');
const generateBtn = document.getElementById('generateBtn');
const jsonOutput = document.getElementById('json-output');
const postBtn = document.getElementById('postBtn');
const activityLog = document.getElementById('activityLog');
const downloadJsonBtn = document.getElementById('downloadJsonBtn');
const lastCreatedBox = document.getElementById('lastCreated');
const lastInvoiceNoSpan = document.getElementById('lastInvoiceNo');

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

// Upload handler
document.getElementById('uploadBtn').addEventListener('click', () => {
  const fileInput = document.getElementById('fileInput');
  activityLog.innerHTML = '';
  generateBtn.disabled = true;
  postBtn.disabled = true;
  jsonOutput.textContent = '';
  downloadJsonBtn.disabled = true;
  hideLastInvoice();

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

      // Render preview (first 5)
      let table = '<table class="table table-striped table-bordered"><thead><tr>';
      data.columns.forEach(col => table += `<th>${col}</th>`);
      table += '</tr></thead><tbody>';
      uploadedRows.slice(0, 5).forEach(row => {
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
  const apiToken = document.getElementById('apiTokenInput').value.trim();
  const endpoint = document.getElementById('endpointInput').value.trim();

  postBtn.disabled = true;
  downloadJsonBtn.disabled = true;
  jsonOutput.textContent = '';
  hideLastInvoice();

  if (uploadedRows.length === 0) {
    addActivityLog('No data to generate JSON.', 'error');
    return;
  }

  addActivityLog('Generating JSON...', 'info');

  fetch('/generate_json', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows: uploadedRows, company, remarks, api_token: apiToken, endpoint })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog(data.error, 'error');
        postBtn.disabled = true;
        return;
      }

      addActivityLog('JSON generated successfully.', 'success');
      jsonOutput.textContent = JSON.stringify(data.invoice || data.invoices, null, 2);
      window.generatedInvoice = data.invoice || data.invoices;
      postBtn.disabled = false;
      downloadJsonBtn.disabled = false;
    })
    .catch(err => {
      addActivityLog('JSON generation failed: ' + err, 'error');
      postBtn.disabled = true;
    });
});

// Post Invoice(s)
document.getElementById('postBtn').addEventListener('click', () => {
  const apiToken = document.getElementById('apiTokenInput').value.trim();
  const endpoint = document.getElementById('endpointInput').value.trim();

  if (!window.generatedInvoice) {
    addActivityLog('No generated invoice to post.', 'error');
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ invoice: window.generatedInvoice, api_token: apiToken, endpoint })
  })
    .then(res => res.json())
    .then(data => {
      if (data.error) {
        addActivityLog("❌ Error: " + data.error, "error");
        return;
      }

      // Case 1: Multiple invoices
      if (Array.isArray(data.results)) {
        data.results.forEach(res => {
          if (res.success) {
            addActivityLog(`✅ Invoice ${res.invoice_no} posted successfully!`, "success");
            showLastInvoice(res.invoice_no);
          } else {
            addActivityLog(`❌ Invoice ${res.invoice_no} failed: ${res.error}`, "error");
          }
        });
      }
      // Case 2: Single invoice
      else if (data.success && data.response) {
        let voucherNo = "";
        try {
          if (data.response.data && data.response.data.name) {
            voucherNo = data.response.data.name;
          } else if (data.response.name) {
            voucherNo = data.response.name;
          }
        } catch (e) { voucherNo = ""; }

        if (voucherNo) {
          addActivityLog(`✅ Invoice posted successfully! Voucher No: ${voucherNo}`, "success");
          showLastInvoice(voucherNo);
        } else {
          addActivityLog("✅ Invoice posted successfully!", "success");
        }
      }
      // Unexpected response
      else {
        addActivityLog("⚠️ Unexpected response: " + JSON.stringify(data), "warning");
      }
    })
    .catch(err => addActivityLog('Post failed: ' + err, 'error'));
});

// Download JSON
downloadJsonBtn.addEventListener('click', () => {
  if (!window.generatedInvoice) return;
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(window.generatedInvoice, null, 2));
  const dlAnchor = document.createElement('a');
  dlAnchor.setAttribute("href", dataStr);
  const fileName = `sales_invoice_${new Date().toISOString().slice(0, 10)}.json`;
  dlAnchor.setAttribute("download", fileName);
  document.body.appendChild(dlAnchor);
  dlAnchor.click();
  dlAnchor.remove();
});

function showLastInvoice(no) {
  lastInvoiceNoSpan.textContent = no;
  lastCreatedBox.style.display = "block";
}

function hideLastInvoice() {
  lastInvoiceNoSpan.textContent = "";
  lastCreatedBox.style.display = "none";
}

// simple HTML escape
function escapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
