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



# enhanced customer details check
def verify_customer_details(api_token, customer, base_url):
    ok, data_or_msg = verify_customer(api_token, customer, base_url)
    if not ok:
        return False, data_or_msg

    # data_or_msg is likely dict of customer fields if ok
    if isinstance(data_or_msg, dict):
        cust = data_or_msg
        # Try to find GST fields in common places
        gst_keys = ['gstin', 'tax_id', 'gst_number', 'gstin_uin', 'gst']
        found = {}
        for k in gst_keys:
            if k in cust and cust.get(k):
                found['gst'] = cust.get(k)
                break

        # Address/state check sometimes in 'customer_primary_address' or separate Address doctype - we do best-effort:
        state = cust.get('state') or cust.get('territory') or cust.get('customer_group')

        # Return success but include discovered details
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

    # Taxes Templates - we verify account_head names used in taxes (these are Sales Taxes and Charges Templates)
    for tax in invoice.get("taxes", []):
        acct = tax.get("account_head")
        if acct:
            ok, msg = verify_tax_template(api_token, acct, base_url)
            if not ok:
                # Not fatal in all cases, but report
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
            # return server response text for debugging
            return False, {'status_code': r.status_code, 'response_text': r.text}
    except Exception as e:
        return False, str(e)
