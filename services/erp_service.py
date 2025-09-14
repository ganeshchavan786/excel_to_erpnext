# services/erp_service.py - Enhanced with Bulk Operations
import requests
from urllib.parse import quote
import json

def _headers(api_token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"token {api_token}"
    }

def _get(api_token, base_url, path):
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        r = requests.get(url, headers=_headers(api_token), timeout=15)
        return r.status_code, r
    except Exception as e:
        return None, str(e)

def _verify_resource(api_token, base_url, doctype, name):
    """Generic verifier for any ERPNext doctype resource"""
    if not name:
        return False, f"{doctype} is empty"
    path = f"api/resource/{doctype}/{quote(str(name))}"
    status, resp = _get(api_token, base_url, path)
    if status == 200:
        try:
            return True, resp.json().get('data', {})
        except Exception:
            return True, "OK"
    elif status is None:
        return False, f"{doctype} verification failed: {resp}"
    else:
        return False, f"{doctype} '{name}' not found in ERPNext (status {status})"

# ========== BULK FETCH FUNCTIONS (NEW) ==========

def bulk_fetch_customers(api_token, base_url, limit=1000):
    """
    Fetch all customers with essential fields for validation
    Returns: (success, data/error_message)
    """
    try:
        path = "api/resource/Customer"
        params = f"?fields=[\"name\",\"customer_name\",\"gstin\",\"territory\",\"disabled\",\"customer_group\"]&limit_page_length={limit}"
        status, resp = _get(api_token, base_url, path + params)
        
        if status == 200:
            data = resp.json()
            customers = data.get("data", [])
            return True, {
                "customers": customers,
                "count": len(customers),
                "message": f"Fetched {len(customers)} customers successfully"
            }
        else:
            return False, f"Failed to fetch customers: Status {status}"
            
    except Exception as e:
        return False, f"Error fetching customers: {str(e)}"

def bulk_fetch_items(api_token, base_url, limit=1000):
    """
    Fetch all items with essential fields for validation
    Returns: (success, data/error_message)
    """
    try:
        path = "api/resource/Item"
        params = f"?fields=[\"item_code\",\"item_name\",\"gst_hsn_code\",\"standard_rate\",\"stock_uom\",\"disabled\",\"has_variants\",\"is_stock_item\"]&limit_page_length={limit}"
        status, resp = _get(api_token, base_url, path + params)
        
        if status == 200:
            data = resp.json()
            items = data.get("data", [])
            return True, {
                "items": items,
                "count": len(items),
                "message": f"Fetched {len(items)} items successfully"
            }
        else:
            return False, f"Failed to fetch items: Status {status}"
            
    except Exception as e:
        return False, f"Error fetching items: {str(e)}"

def bulk_fetch_uoms(api_token, base_url, limit=500):
    """
    Fetch all UOMs for validation
    Returns: (success, data/error_message)
    """
    try:
        path = "api/resource/UOM"
        params = f"?fields=[\"uom_name\",\"enabled\"]&limit_page_length={limit}"
        status, resp = _get(api_token, base_url, path + params)
        
        if status == 200:
            data = resp.json()
            uoms = data.get("data", [])
            return True, {
                "uoms": uoms,
                "count": len(uoms),
                "message": f"Fetched {len(uoms)} UOMs successfully"
            }
        else:
            return False, f"Failed to fetch UOMs: Status {status}"
            
    except Exception as e:
        return False, f"Error fetching UOMs: {str(e)}"

def batch_verify_customers(api_token, base_url, customer_names):
    """
    Verify multiple customers in batch
    Returns: Dict with results for each customer
    """
    results = {}
    
    for customer in customer_names:
        if not customer or not customer.strip():
            results[customer] = {"found": False, "error": "Empty customer name"}
            continue
            
        try:
            success, data = verify_customer(api_token, customer, base_url)
            results[customer] = {
                "found": success,
                "data": data if success else None,
                "error": data if not success else None
            }
        except Exception as e:
            results[customer] = {"found": False, "error": str(e)}
    
    return results

def batch_verify_items(api_token, base_url, item_codes):
    """
    Verify multiple items in batch
    Returns: Dict with results for each item
    """
    results = {}
    
    for item in item_codes:
        if not item or not item.strip():
            results[item] = {"found": False, "error": "Empty item code"}
            continue
            
        try:
            success, data = verify_item(api_token, item, base_url)
            results[item] = {
                "found": success,
                "data": data if success else None,
                "error": data if not success else None
            }
        except Exception as e:
            results[item] = {"found": False, "error": str(e)}
    
    return results

def get_customer_by_name(api_token, base_url, customer_name):
    """
    Get customer details by name with additional fields
    Returns: (success, customer_data/error_message)
    """
    try:
        path = f"api/resource/Customer/{quote(customer_name)}"
        status, resp = _get(api_token, base_url, path)
        
        if status == 200:
            return True, resp.json().get('data', {})
        else:
            return False, f"Customer '{customer_name}' not found"
            
    except Exception as e:
        return False, f"Error fetching customer: {str(e)}"

def get_item_by_code(api_token, base_url, item_code):
    """
    Get item details by code with additional fields
    Returns: (success, item_data/error_message)
    """
    try:
        path = f"api/resource/Item/{quote(item_code)}"
        status, resp = _get(api_token, base_url, path)
        
        if status == 200:
            return True, resp.json().get('data', {})
        else:
            return False, f"Item '{item_code}' not found"
            
    except Exception as e:
        return False, f"Error fetching item: {str(e)}"

def validate_gstin_format(gstin):
    """
    Validate GSTIN format
    GSTIN: 15 characters - 2 digits (state) + 10 alphanumeric + 1 alphabet + 1 digit + 1 alphabet/digit
    Returns: (valid, message)
    """
    import re
    
    if not gstin or not gstin.strip():
        return False, "GSTIN is empty"
    
    gstin_clean = gstin.strip().upper()
    
    # Length check
    if len(gstin_clean) != 15:
        return False, "GSTIN must be 15 characters"
    
    # Pattern check
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][Z][0-9A-Z]$'
    if not re.match(pattern, gstin_clean):
        return False, "Invalid GSTIN format"
    
    # State code check (01-37)
    state_code = int(gstin_clean[:2])
    if state_code < 1 or state_code > 37:
        return False, "Invalid state code in GSTIN"
    
    return True, "GSTIN format is valid"

def search_customers_by_pattern(api_token, base_url, pattern, limit=10):
    """
    Search customers using pattern matching
    Returns: (success, matching_customers/error_message)
    """
    try:
        # ERPNext supports filters - we'll use "like" operator
        path = "api/resource/Customer"
        filters = f'[["Customer", "customer_name", "like", "%{pattern}%"]]'
        params = f"?fields=[\"name\",\"customer_name\",\"gstin\"]&filters={quote(filters)}&limit_page_length={limit}"
        
        status, resp = _get(api_token, base_url, path + params)
        
        if status == 200:
            data = resp.json()
            customers = data.get("data", [])
            return True, customers
        else:
            return False, f"Search failed: Status {status}"
            
    except Exception as e:
        return False, f"Error searching customers: {str(e)}"

def search_items_by_pattern(api_token, base_url, pattern, limit=10):
    """
    Search items using pattern matching
    Returns: (success, matching_items/error_message)
    """
    try:
        path = "api/resource/Item"
        filters = f'[["Item", "item_code", "like", "%{pattern}%"]]'
        params = f"?fields=[\"item_code\",\"item_name\",\"standard_rate\"]&filters={quote(filters)}&limit_page_length={limit}"
        
        status, resp = _get(api_token, base_url, path + params)
        
        if status == 200:
            data = resp.json()
            items = data.get("data", [])
            return True, items
        else:
            return False, f"Search failed: Status {status}"
            
    except Exception as e:
        return False, f"Error searching items: {str(e)}"

# ========== EXISTING FUNCTIONS (ENHANCED) ==========

# Specific verifiers
def verify_customer(api_token, customer, base_url):
    return _verify_resource(api_token, base_url, "Customer", customer)

def verify_item(api_token, item, base_url):
    return _verify_resource(api_token, base_url, "Item", item)

def verify_company(api_token, company, base_url):
    return _verify_resource(api_token, base_url, "Company", company)

def verify_warehouse(api_token, warehouse, base_url):
    return _verify_resource(api_token, base_url, "Warehouse", warehouse)

def verify_uom(api_token, uom, base_url):
    return _verify_resource(api_token, base_url, "UOM", uom)

def verify_payment_terms(api_token, payment_terms, base_url):
    return _verify_resource(api_token, base_url, "Payment Terms Template", payment_terms)

def verify_tax_template(api_token, tax_template, base_url):
    return _verify_resource(api_token, base_url, "Account", tax_template)

# Enhanced customer details check
def verify_customer_details(api_token, customer, base_url):
    ok, data_or_msg = verify_customer(api_token, customer, base_url)
    if not ok:
        return False, data_or_msg

    if isinstance(data_or_msg, dict):
        cust = data_or_msg
        gst_keys = ['gstin', 'tax_id', 'gst_number', 'gstin_uin', 'gst']
        found = {}
        for k in gst_keys:
            if k in cust and cust.get(k):
                found['gst'] = cust.get(k)
                break

        state = cust.get('state') or cust.get('territory') or cust.get('customer_group')

        return True, {'customer_doc': cust, 'gst_found': found.get('gst'), 'state_guess': state}
    else:
        return True, "OK"

def verify_invoice_masters(api_token, invoice, base_url="https://vrushaliinfotech.com"):
    """
    Verify required masters for invoice: Customer, Company, Items, UOM, Warehouse, Payment Terms, Taxes template.
    Returns (True, 'OK') or (False, 'msg')
    """
    remarks = []

    # Customer
    ok, msg = verify_customer(api_token, invoice.get("customer"), base_url)
    if not ok:
        remarks.append(msg)

    # Company
    ok, msg = verify_company(api_token, invoice.get("company"), base_url)
    if not ok:
        remarks.append(msg)

    # Items + UOM + Warehouse
    for item in invoice.get("items", []):
        name = item.get("item_code") or item.get("item_name")
        ok, msg = verify_item(api_token, name, base_url)
        if not ok:
            remarks.append(msg)

        if item.get("uom"):
            ok, msg = verify_uom(api_token, item["uom"], base_url)
            if not ok:
                remarks.append(msg)

        if item.get("warehouse"):
            ok, msg = verify_warehouse(api_token, item["warehouse"], base_url)
            if not ok:
                remarks.append(msg)

    # Payment Terms
    if invoice.get("payment_terms_template"):
        ok, msg = verify_payment_terms(api_token, invoice["payment_terms_template"], base_url)
        if not ok:
            remarks.append(msg)

    # Taxes Templates
    for tax in invoice.get("taxes", []):
        acct = tax.get("account_head")
        if acct:
            ok, msg = verify_tax_template(api_token, acct, base_url)
            if not ok:
                remarks.append(msg)

    if remarks:
        return False, "; ".join(remarks)
    return True, "All masters verified."

def post_invoice_to_erp(api_token, invoice, endpoint):
    headers = _headers(api_token)
    try:
        r = requests.post(endpoint, headers=headers, json=invoice, timeout=30)
        if r.status_code in (200, 201):
            try:
                return True, r.json()
            except Exception:
                return True, r.text
        else:
            return False, {'status_code': r.status_code, 'response_text': r.text}
    except Exception as e:
        return False, str(e)
    if not re.match(pattern, gstin_clean):
        return False, "Invalid GSTIN format"
    
    # State code check (01-37)
    state_code = int(gstin_clean[:2])
    if state_code < 1 or state_code > 37:
        return False, "Invalid state code in GSTIN"
    
    return True, "GSTIN format is valid"

def search_customers_by_pattern(api_token, base_url, pattern, limit=10):
    """
    Search customers using pattern matching
    Returns: (success, matching_customers/error_message)
    """
    try:
        # ERPNext supports filters - we'll use "like" operator
        path = "api/resource/Customer"
        filters = f'[["Customer", "customer_name", "like", "%{pattern}%"]]'
        params = f"?fields=[\"name\",\"customer_name\",\"gstin\"]&filters={quote(filters)}&limit_page_length={limit}"
        
        status, resp = _get(api_token, base_url, path + params)
        
        if status == 200:
            data = resp.json()
            customers = data.get("data", [])
            return True, customers
        else:
            return False, f"Search failed: Status {status}"
            
    except Exception as e:
        return False, f"Error searching customers: {str(e)}"

def search_items_by_pattern(api_token, base_url, pattern, limit=10):
    """
    Search items using pattern matching
    Returns: (success, matching_items/error_message)
    """
    try:
        path = "api/resource/Item"
        filters = f'[["Item", "item_code", "like", "%{pattern}%"]]'
        params = f"?fields=[\"item_code\",\"item_name\",\"standard_rate\"]&filters={quote(filters)}&limit_page_length={limit}"
        
        status, resp = _get(api_token, base_url, path + params)
        
        if status == 200:
            data = resp.json()
            items = data.get("data", [])
            return True, items
        else:
            return False, f"Search failed: Status {status}"
            
    except Exception as e:
        return False, f"Error searching items: {str(e)}"

# ========== EXISTING FUNCTIONS (ENHANCED) ==========

# Specific verifiers
def verify_customer(api_token, customer, base_url):
    return _verify_resource(api_token, base_url, "Customer", customer)

def verify_item(api_token, item, base_url):
    return _verify_resource(api_token, base_url, "Item", item)

def verify_company(api_token, company, base_url):
    return _verify_resource(api_token, base_url, "Company", company)

def verify_warehouse(api_token, warehouse, base_url):
    return _verify_resource(api_token, base_url, "Warehouse", warehouse)

def verify_uom(api_token, uom, base_url):
    return _verify_resource(api_token, base_url, "UOM", uom)

def verify_payment_terms(api_token, payment_terms, base_url):
    return _verify_resource(api_token, base_url, "Payment Terms Template", payment_terms)

def verify_tax_template(api_token, tax_template, base_url):
    return _verify_resource(api_token, base_url, "Account", tax_template)

# Enhanced customer details check
def verify_customer_details(api_token, customer, base_url):
    ok, data_or_msg = verify_customer(api_token, customer, base_url)
    if not ok:
        return False, data_or_msg

    if isinstance(data_or_msg, dict):
        cust = data_or_msg
        gst_keys = ['gstin', 'tax_id', 'gst_number', 'gstin_uin', 'gst']
        found = {}
        for k in gst_keys:
            if k in cust and cust.get(k):
                found['gst'] = cust.get(k)
                break

        state = cust.get('state') or cust.get('territory') or cust.get('customer_group')

        return True, {'customer_doc': cust, 'gst_found': found.get('gst'), 'state_guess': state}
    else:
        return True, "OK"

def verify_invoice_masters(api_token, invoice, base_url="https://vrushaliinfotech.com"):
    """
    Verify required masters for invoice: Customer, Company, Items, UOM, Warehouse, Payment Terms, Taxes template.
    Returns (True, 'OK') or (False, 'msg')
    """
    remarks = []

    # Customer
    ok, msg = verify_customer(api_token, invoice.get("customer"), base_url)
    if not ok:
        remarks.append(msg)

    # Company
    ok, msg = verify_company(api_token, invoice.get("company"), base_url)
    if not ok:
        remarks.append(msg)

    # Items + UOM + Warehouse
    for item in invoice.get("items", []):
        name = item.get("item_code") or item.get("item_name")
        ok, msg = verify_item(api_token, name, base_url)
        if not ok:
            remarks.append(msg)

        if item.get("uom"):
            ok, msg = verify_uom(api_token, item["uom"], base_url)
            if not ok:
                remarks.append(msg)

        if item.get("warehouse"):
            ok, msg = verify_warehouse(api_token, item["warehouse"], base_url)
            if not ok:
                remarks.append(msg)

    # Payment Terms
    if invoice.get("payment_terms_template"):
        ok, msg = verify_payment_terms(api_token, invoice["payment_terms_template"], base_url)
        if not ok:
            remarks.append(msg)

    # Taxes Templates
    for tax in invoice.get("taxes", []):
        acct = tax.get("account_head")
        if acct:
            ok, msg = verify_tax_template(api_token, acct, base_url)
            if not ok:
                remarks.append(msg)

    if remarks:
        return False, "; ".join(remarks)
    return True, "All masters verified."

def post_invoice_to_erp(api_token, invoice, endpoint):
    headers = _headers(api_token)
    try:
        r = requests.post(endpoint, headers=headers, json=invoice, timeout=30)
        if r.status_code in (200, 201):
            try:
                return True, r.json()
            except Exception:
                return True, r.text
        else:
            return False, {'status_code': r.status_code, 'response_text': r.text}
    except Exception as e:
        return False, str(e)