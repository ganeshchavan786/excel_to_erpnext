# app.py — v11 (with hardcoded credentials)
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
import uuid

from services.excel_service import read_rows_from_buffer
from services.erp_service import verify_invoice_masters, post_invoice_to_erp

app = Flask(__name__)
app.secret_key = 'vrushali-infotech-sales-invoice-2025'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
COMPANY_STATE = "Maharashtra"   # your company state (used to decide IGST vs CGST+SGST)
DEFAULT_COMPANY = "Vrushali Infotech Pvt Ltd"

# Hardcoded API credentials
DEFAULT_API_TOKEN = "6b9c2cfc6e6aaaf:a362001e6dfee4c"
DEFAULT_ENDPOINT = "https://vrushaliinfotech.com/api/resource/Sales%20Invoice"

# Small mapping — extend if you want more exact "state code - StateName" strings.
STATE_CODE_MAP = {
    "Maharashtra": "27-Maharashtra",
    "Gujarat": "24-Gujarat",
    "Karnataka": "29-Karnataka",
    "Delhi": "07-Delhi",
    "Tamil Nadu": "33-Tamil Nadu",
    "West Bengal": "19-West Bengal",
    "Andhra Pradesh": "37-Andhra Pradesh",
    "Telangana": "36-Telangana",
    # add more as needed
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _state_to_place_of_supply(state_name):
    if not state_name:
        return ""
    s = state_name.strip()
    return STATE_CODE_MAP.get(s, s)  # prefer mapped "code-name", else raw state


def _decide_gst_category_and_place(first_row):
    """
    Return tuple (gst_category, gstin, place_of_supply_str).
    gst_category -> "Registered" | "Unregistered" | "Overseas"
    """
    country = (first_row.get("Country") or first_row.get("country") or "").strip()
    gstin = (first_row.get("GSTIN") or first_row.get("gstin") or first_row.get("GST No") or "").strip()

    # Overseas if country present and not India
    if country and country.lower() not in ("india", "in", "india (in)"):
        return "Overseas", gstin, country

    if gstin:
        return "Registered", gstin, _state_to_place_of_supply(first_row.get("Customer State") or first_row.get("State") or "")
    # default fallback
    return "Unregistered", gstin, _state_to_place_of_supply(first_row.get("Customer State") or first_row.get("State") or "")


def build_invoice(rows_for_invoice):
    """
    Build a single Sales Invoice dict from a list of row-dicts (all rows for one Invoice No)
    - Removes Sales Order / Purchase Order linking in item lines (independent invoice)
    - Adds gst_category, gstin (if any), place_of_supply
    - Creates taxes lines per item (In-state -> CGST+SGST ; Out-of-state -> IGST)
    """
    if not rows_for_invoice:
        return None

    first = rows_for_invoice[0]
    customer = (first.get("Customer") or first.get("Customer Name") or first.get("customer") or "").strip()
    if not customer:
        raise ValueError("Customer missing for invoice group")

    # smart gst_category / gstin / place of supply
    gst_category, gstin, place_of_supply_value = _decide_gst_category_and_place(first)

    posting_date = first.get("Posting Date") or first.get("Invoice Date") or datetime.now().strftime("%Y-%m-%d")
    due_date = first.get("Due Date") or posting_date

    invoice = {
        "doctype": "Sales Invoice",
        "customer": customer,
        "company": (first.get("Company") or DEFAULT_COMPANY),
        "posting_date": posting_date,
        "due_date": due_date,
        "customer_po_no": first.get("Purchase Order No") or "",
        "items": [],
        "taxes": [],
        # helpful fields for ERPNext India compliance:
        "gst_category": gst_category,      # Registered / Unregistered / Overseas
        # include GSTIN only when available (ERPNext will verify)
        **({"gstin": gstin} if gstin else {}),
        # place_of_supply: use mapped state-code if available else raw state (string)
        **({"place_of_supply": place_of_supply_value} if place_of_supply_value else {}),
        "remarks": first.get("Remarks") or "Generated from Excel Uploader",
    }

    # Items: deliberately DO NOT include sales_order/purchase_order to avoid LinkValidation
    for r in rows_for_invoice:
        item_code = (r.get("Item Code") or r.get("Item") or "").strip()
        item_name = (r.get("Item Name") or item_code).strip() or item_code
        description = (r.get("Description") or item_name).strip()
        try:
            qty = float(r.get("Qty") or r.get("Quantity") or 1)
        except Exception:
            qty = 1.0
        try:
            rate = float(r.get("Rate") or 0)
        except Exception:
            rate = 0.0

        uom = (r.get("UOM") or "Nos").strip()
        hsn_code = str(r.get("GST HSN Code") or r.get("hsn_code") or "").strip()
        gst_rate = float(r.get("GST Rate (%)") or r.get("GST Rate") or 0) if r.get("GST Rate") or r.get("GST Rate (%)") else 0.0
        warehouse = (r.get("Warehouse") or "").strip()

        item = {
            "item_code": item_code,
            "item_name": item_name,
            "description": description,
            "qty": qty,
            "rate": rate,
            "uom": uom,
            "gst_hsn_code": hsn_code,
            # intentionally not adding sales_order / purchase_order (independent invoice)
            "warehouse": warehouse if warehouse else None,
            "income_account": (r.get("Income Account") or "Sales - VIPL"),
            # retain GST rate on item for tax calc later
            "gst_rate": gst_rate
        }
        # remove None values for cleanliness
        item = {k: v for k, v in item.items() if v is not None}
        invoice["items"].append(item)

    # Build taxes aggregated by rate, but for ERPNext we add per-rate lines.
    # Determine whether supply is intra-state (CGST+SGST) or inter-state (IGST)
    # We'll base decision on place_of_supply vs COMPANY_STATE (name or code)
    place_of_supply_raw = invoice.get("place_of_supply", "")
    intra_state = False
    if isinstance(place_of_supply_raw, str) and place_of_supply_raw:
        # if our mapping returned "27-Maharashtra" we detect "Maharashtra" presence,
        # else match by raw state name
        if COMPANY_STATE.lower() in place_of_supply_raw.lower():
            intra_state = True
        else:
            # if place_of_supply is just state name and matches
            if place_of_supply_raw.strip().lower() == COMPANY_STATE.strip().lower():
                intra_state = True

    # For each item, add taxes accordingly. We will append a separate tax row
    # for each item-rate combination. ERPNext accepts item_wise_tax_detail JSON.
    for it in invoice["items"]:
        rate = float(it.get("gst_rate") or 0)
        if rate <= 0:
            continue
        taxable_value = round(it["qty"] * it["rate"], 2)
        key = it.get("item_code") or it.get("item_name")
        if intra_state:
            half_rate = round(rate / 2.0, 6)
            half_tax_amount = round((taxable_value * half_rate) / 100.0, 2)
            # CGST
            invoice["taxes"].append({
                "charge_type": "On Net Total",
                "account_head": "Output Tax CGST - VIPL",
                "description": f"CGST @ {half_rate}%",
                "rate": half_rate,
                "item_wise_tax_detail": json.dumps({key: [half_rate, half_tax_amount]})
            })
            # SGST
            invoice["taxes"].append({
                "charge_type": "On Net Total",
                "account_head": "Output Tax SGST - VIPL",
                "description": f"SGST @ {half_rate}%",
                "rate": half_rate,
                "item_wise_tax_detail": json.dumps({key: [half_rate, half_tax_amount]})
            })
        else:
            # IGST full
            tax_amount = round((taxable_value * rate) / 100.0, 2)
            invoice["taxes"].append({
                "charge_type": "On Net Total",
                "account_head": "Output Tax IGST - VIPL",
                "description": f"IGST @ {rate}%",
                "rate": rate,
                "item_wise_tax_detail": json.dumps({key: [rate, tax_amount]})
            })

    # Done
    return invoice


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{filename}")
        file.save(filepath)
        try:
            rows, columns = read_rows_from_buffer(filepath)
        except Exception as e:
            os.remove(filepath)
            return jsonify({'error': f'File reading failed: {str(e)}'}), 400
        os.remove(filepath)
        return jsonify({'success': True, 'rows': rows, 'columns': columns})
    else:
        return jsonify({'error': 'Invalid file type'}), 400


@app.route("/generate_json", methods=["POST"])
def generate_json():
    """
    Accepts JSON: { rows: [...], company: "..." (optional), remarks: "..." (optional) }
    Groups rows by 'Invoice No' if present; else treats all rows as single invoice.
    Returns { success: True, invoices: { INV-001: {...}, ... } }
    """
    data = request.get_json()
    rows = data.get("rows", []) or []
    company = (data.get("company") or DEFAULT_COMPANY).strip()
    remarks = data.get("remarks", "Generated from Excel Uploader").strip()

    if not rows:
        return jsonify({'error': 'No data rows found'}), 400

    # If 'Invoice No' present, group by it; else single invoice id
    groups = {}
    if any("Invoice No" in r or "InvoiceNo" in r for r in rows):
        for r in rows:
            inv = r.get("Invoice No") or r.get("InvoiceNo") or "__NO_INV__"
            groups.setdefault(str(inv), []).append(r)
    else:
        groups["__SINGLE__"] = rows

    invoices = {}
    errors = {}
    for inv_no, group_rows in groups.items():
        try:
            invoice = build_invoice(group_rows)
            invoice["company"] = company
            invoice["remarks"] = remarks
            invoices[inv_no] = invoice
        except Exception as e:
            errors[inv_no] = str(e)

    if errors and not invoices:
        return jsonify({'error': 'All invoice builds failed', 'details': errors}), 400

    return jsonify({'success': True, 'invoices': invoices, 'errors': errors})


@app.route("/post_invoice", methods=["POST"])
def post_invoice():
    """
    Accepts JSON:
    {
      api_token: "key:secret" (optional - uses default if not provided),
      endpoint: "https://example.com/api/resource/Sales%20Invoice" (optional - uses default if not provided),
      invoices: { INV-001: {...}, ... } OR invoice: { ... }   # support both
    }

    Verifies masters for each invoice, posts if ok, returns per-invoice results.
    """
    data = request.get_json() or {}
    api_token = (data.get("api_token") or DEFAULT_API_TOKEN).strip()
    endpoint = (data.get("endpoint") or DEFAULT_ENDPOINT).strip()

    # collect invoices param
    invoices_map = {}
    if data.get("invoices"):
        invoices_map = data["invoices"]
    elif data.get("invoice"):
        invoices_map = {"__single__": data["invoice"]}
    else:
        return jsonify({'error': 'No invoice data provided'}), 400

    if not api_token or ':' not in api_token:
        return jsonify({'error': 'API token is required in key:secret format'}), 400

    base_url = '/'.join(endpoint.split('/')[:3])

    results = {}
    for inv_key, inv_payload in invoices_map.items():
        try:
            # verify masters (customer, company, items, uoms, warehouses, taxes/templates, etc.)
            ok, message = verify_invoice_masters(api_token, inv_payload, base_url=base_url)
            if not ok:
                results[inv_key] = {"success": False, "error": f"Master verification failed: {message}"}
                continue

            success, resp = post_invoice_to_erp(api_token, inv_payload, endpoint)
            if success:
                # Extract invoice number from response if available
                invoice_name = ""
                if isinstance(resp, dict) and resp.get('data', {}).get('name'):
                    invoice_name = resp['data']['name']
                
                results[inv_key] = {
                    "success": True, 
                    "response": resp,
                    "invoice_no": invoice_name or inv_key
                }
            else:
                results[inv_key] = {
                    "success": False, 
                    "response": resp,
                    "invoice_no": inv_key
                }
        except Exception as e:
            results[inv_key] = {
                "success": False, 
                "error": str(e),
                "invoice_no": inv_key
            }

    return jsonify({"success": True, "results": results})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)