# services/customer_validator.py
import re
from typing import List, Dict, Tuple
import difflib
import requests
from urllib.parse import quote

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

class CustomerValidator:
    """
    Customer-specific validation for ERPNext masters
    Handles customer existence, GSTIN validation, smart matching
    """
    
    def __init__(self, api_token: str, base_url: str):
        self.api_token = api_token
        self.base_url = base_url
        self.customer_cache = {}
        self.gstin_cache = {}
        
    def validate_customer_batch(self, customer_list: List[str]) -> List[Dict]:
        """
        Validate batch of customers
        Returns list of validation results
        """
        results = []
        
        # Bulk fetch customers first time for better performance
        if not self.customer_cache:
            self._load_customer_cache()
        
        for customer in customer_list:
            result = self._validate_single_customer(customer)
            results.append(result)
        
        return results
    
    def _load_customer_cache(self):
        """Load all customers from ERPNext into memory cache"""
        try:
            print("Loading customer cache...")  # Debug line
            path = "api/resource/Customer"
            params = "?fields=[\"name\",\"customer_name\",\"gstin\",\"territory\",\"disabled\"]&limit_page_length=1000"
            status, resp = _get(self.api_token, self.base_url, path + params)
            
            print(f"API Status: {status}")  # Debug line
            
            if status == 200:
                data = resp.json()
                customers = data.get("data", [])
                print(f"Found {len(customers)} customers")  # Debug line
                
                for customer in customers:
                    name = customer.get("name", "")
                    customer_name = customer.get("customer_name", "")
                    gstin = customer.get("gstin", "")
                    disabled = customer.get("disabled", 0)
                    
                    # Store by both name and customer_name for flexible matching
                    customer_info = {
                        "name": name,
                        "customer_name": customer_name,
                        "gstin": gstin,
                        "disabled": disabled,
                        "territory": customer.get("territory", "")
                    }
                    
                    if name:
                        self.customer_cache[name.lower()] = customer_info
                    if customer_name and customer_name != name:
                        self.customer_cache[customer_name.lower()] = customer_info
                    
                    # Store GSTIN for duplicate check
                    if gstin:
                        self.gstin_cache[gstin] = customer_info
            else:
                print(f"API Error: Status {status}")  # Debug line
                        
        except Exception as e:
            print(f"Error loading customer cache: {e}")
    
    def _validate_single_customer(self, customer: str) -> Dict:
        """Validate single customer with smart matching"""
        if not customer or not customer.strip():
            return {
                "customer": customer,
                "status": "failed",
                "message": "Customer name is empty",
                "suggestion": None
            }
        
        customer_clean = customer.strip()
        customer_lower = customer_clean.lower()
        
        # 1. Exact match check
        if customer_lower in self.customer_cache:
            customer_info = self.customer_cache[customer_lower]
            if customer_info.get("disabled"):
                return {
                    "customer": customer,
                    "status": "warning", 
                    "message": "Customer is disabled in ERPNext",
                    "suggestion": "Enable customer or use different customer"
                }
            return {
                "customer": customer,
                "status": "passed",
                "message": "Customer found and active"
            }
        
        # 2. Partial match / typo detection
        suggestion = self._find_similar_customer(customer_clean)
        if suggestion:
            return {
                "customer": customer,
                "status": "warning",
                "message": f"Customer not found exactly, similar customer available",
                "suggestion": suggestion
            }
        
        # 3. GSTIN validation if provided
        gstin_result = self._validate_gstin_format(customer_clean)
        if gstin_result.get("has_gstin"):
            return {
                "customer": customer,
                "status": "failed",
                "message": f"Customer not found. GSTIN format: {gstin_result['message']}",
                "suggestion": "Create new customer with this GSTIN"
            }
        
        # 4. No match found
        return {
            "customer": customer,
            "status": "failed",
            "message": "Customer not found in ERPNext",
            "suggestion": "Create new customer"
        }
    
    def _find_similar_customer(self, customer: str) -> str:
        """Find similar customer using fuzzy matching"""
        if not self.customer_cache:
            return None
        
        customer_names = []
        for cache_key, customer_info in self.customer_cache.items():
            # Add both name and customer_name for matching
            customer_names.append(customer_info.get("name", ""))
            customer_names.append(customer_info.get("customer_name", ""))
        
        # Remove empty names
        customer_names = [name for name in customer_names if name]
        
        # Find best matches using difflib
        matches = difflib.get_close_matches(customer, customer_names, n=1, cutoff=0.6)
        
        if matches:
            return matches[0]
        
        return None
    
    def _validate_gstin_format(self, customer_data: str) -> Dict:
        """
        Validate GSTIN format if present in customer data
        GSTIN format: 15 characters - 2 digits (state) + 10 alphanumeric + 1 alphabet + 1 digit + 1 alphabet/digit
        """
        # Look for GSTIN pattern in customer string (sometimes people put GSTIN with customer name)
        gstin_pattern = r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]\b'
        gstin_match = re.search(gstin_pattern, customer_data.upper())
        
        if not gstin_match:
            return {"has_gstin": False, "message": "No GSTIN found"}
        
        gstin = gstin_match.group()
        
        # Validate GSTIN format
        if len(gstin) != 15:
            return {
                "has_gstin": True,
                "gstin": gstin,
                "valid": False,
                "message": "GSTIN must be 15 characters"
            }
        
        # Check state code (first 2 digits)
        state_code = gstin[:2]
        if not state_code.isdigit() or int(state_code) < 1 or int(state_code) > 37:
            return {
                "has_gstin": True,
                "gstin": gstin,
                "valid": False,
                "message": "Invalid state code in GSTIN"
            }
        
        # Check if GSTIN already exists for different customer
        if gstin in self.gstin_cache:
            existing_customer = self.gstin_cache[gstin]
            return {
                "has_gstin": True,
                "gstin": gstin,
                "valid": True,
                "message": f"GSTIN already exists for customer: {existing_customer.get('customer_name', existing_customer.get('name'))}"
            }
        
        return {
            "has_gstin": True,
            "gstin": gstin,
            "valid": True,
            "message": "GSTIN format is valid"
        }
    
    def get_customer_suggestions(self, partial_name: str, limit: int = 5) -> List[Dict]:
        """Get customer suggestions for autocomplete"""
        if not self.customer_cache or not partial_name:
            return []
        
        partial_lower = partial_name.lower()
        suggestions = []
        
        for cache_key, customer_info in self.customer_cache.items():
            if partial_lower in cache_key:
                suggestions.append({
                    "name": customer_info.get("name"),
                    "customer_name": customer_info.get("customer_name"),
                    "gstin": customer_info.get("gstin", ""),
                    "territory": customer_info.get("territory", ""),
                    "disabled": customer_info.get("disabled", False)
                })
                
                if len(suggestions) >= limit:
                    break
        
        return suggestions
    
    def verify_customer_details(self, customer: str) -> Dict:
        """Get detailed customer information"""
        customer_lower = customer.lower()
        
        if customer_lower in self.customer_cache:
            return {
                "found": True,
                "details": self.customer_cache[customer_lower]
            }
        
        # If not in cache, try direct API call
        try:
            status, resp = _verify_resource(self.api_token, self.base_url, "Customer", customer)
            if status:
                return {
                    "found": True,
                    "details": resp if isinstance(resp, dict) else {"name": customer}
                }
        except:
            pass
        
        return {
            "found": False,
            "details": None
        }

class CustomerValidator:
    """
    Customer-specific validation for ERPNext masters
    Handles customer existence, GSTIN validation, smart matching
    """
    
    def __init__(self, api_token: str, base_url: str):
        self.api_token = api_token
        self.base_url = base_url
        self.customer_cache = {}
        self.gstin_cache = {}
        
    def validate_customer_batch(self, customer_list: List[str]) -> List[Dict]:
        """
        Validate batch of customers
        Returns list of validation results
        """
        results = []
        
        # Bulk fetch customers first time for better performance
        if not self.customer_cache:
            self._load_customer_cache()
        
        for customer in customer_list:
            result = self._validate_single_customer(customer)
            results.append(result)
        
        return results
    
    def _load_customer_cache(self):
        """Load all customers from ERPNext into memory cache"""
        try:
            path = "api/resource/Customer"
            params = "?fields=[\"name\",\"customer_name\",\"gstin\",\"territory\",\"disabled\"]&limit_page_length=1000"
            status, resp = _get(self.api_token, self.base_url, path + params)
            
            if status == 200:
                data = resp.json()
                customers = data.get("data", [])
                
                for customer in customers:
                    name = customer.get("name", "")
                    customer_name = customer.get("customer_name", "")
                    gstin = customer.get("gstin", "")
                    disabled = customer.get("disabled", 0)
                    
                    # Store by both name and customer_name for flexible matching
                    customer_info = {
                        "name": name,
                        "customer_name": customer_name,
                        "gstin": gstin,
                        "disabled": disabled,
                        "territory": customer.get("territory", "")
                    }
                    
                    if name:
                        self.customer_cache[name.lower()] = customer_info
                    if customer_name and customer_name != name:
                        self.customer_cache[customer_name.lower()] = customer_info
                    
                    # Store GSTIN for duplicate check
                    if gstin:
                        self.gstin_cache[gstin] = customer_info
                        
        except Exception as e:
            print(f"Error loading customer cache: {e}")
    
    def _validate_single_customer(self, customer: str) -> Dict:
        """Validate single customer with smart matching"""
        if not customer or not customer.strip():
            return {
                "customer": customer,
                "status": "failed",
                "message": "Customer name is empty",
                "suggestion": None
            }
        
        customer_clean = customer.strip()
        customer_lower = customer_clean.lower()
        
        # 1. Exact match check
        if customer_lower in self.customer_cache:
            customer_info = self.customer_cache[customer_lower]
            if customer_info.get("disabled"):
                return {
                    "customer": customer,
                    "status": "warning", 
                    "message": "Customer is disabled in ERPNext",
                    "suggestion": "Enable customer or use different customer"
                }
            return {
                "customer": customer,
                "status": "passed",
                "message": "Customer found and active"
            }
        
        # 2. Partial match / typo detection
        suggestion = self._find_similar_customer(customer_clean)
        if suggestion:
            return {
                "customer": customer,
                "status": "warning",
                "message": f"Customer not found exactly, similar customer available",
                "suggestion": suggestion
            }
        
        # 3. GSTIN validation if provided
        gstin_result = self._validate_gstin_format(customer_clean)
        if gstin_result.get("has_gstin"):
            return {
                "customer": customer,
                "status": "failed",
                "message": f"Customer not found. GSTIN format: {gstin_result['message']}",
                "suggestion": "Create new customer with this GSTIN"
            }
        
        # 4. No match found
        return {
            "customer": customer,
            "status": "failed",
            "message": "Customer not found in ERPNext",
            "suggestion": "Create new customer"
        }
    
    def _find_similar_customer(self, customer: str) -> str:
        """Find similar customer using fuzzy matching"""
        if not self.customer_cache:
            return None
        
        customer_names = []
        for cache_key, customer_info in self.customer_cache.items():
            # Add both name and customer_name for matching
            customer_names.append(customer_info.get("name", ""))
            customer_names.append(customer_info.get("customer_name", ""))
        
        # Remove empty names
        customer_names = [name for name in customer_names if name]
        
        # Find best matches using difflib
        matches = difflib.get_close_matches(customer, customer_names, n=1, cutoff=0.6)
        
        if matches:
            return matches[0]
        
        return None
    
    def _validate_gstin_format(self, customer_data: str) -> Dict:
        """
        Validate GSTIN format if present in customer data
        GSTIN format: 15 characters - 2 digits (state) + 10 alphanumeric + 1 alphabet + 1 digit + 1 alphabet/digit
        """
        # Look for GSTIN pattern in customer string (sometimes people put GSTIN with customer name)
        gstin_pattern = r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]\b'
        gstin_match = re.search(gstin_pattern, customer_data.upper())
        
        if not gstin_match:
            return {"has_gstin": False, "message": "No GSTIN found"}
        
        gstin = gstin_match.group()
        
        # Validate GSTIN format
        if len(gstin) != 15:
            return {
                "has_gstin": True,
                "gstin": gstin,
                "valid": False,
                "message": "GSTIN must be 15 characters"
            }
        
        # Check state code (first 2 digits)
        state_code = gstin[:2]
        if not state_code.isdigit() or int(state_code) < 1 or int(state_code) > 37:
            return {
                "has_gstin": True,
                "gstin": gstin,
                "valid": False,
                "message": "Invalid state code in GSTIN"
            }
        
        # Check if GSTIN already exists for different customer
        if gstin in self.gstin_cache:
            existing_customer = self.gstin_cache[gstin]
            return {
                "has_gstin": True,
                "gstin": gstin,
                "valid": True,
                "message": f"GSTIN already exists for customer: {existing_customer.get('customer_name', existing_customer.get('name'))}"
            }
        
        return {
            "has_gstin": True,
            "gstin": gstin,
            "valid": True,
            "message": "GSTIN format is valid"
        }
    
    def get_customer_suggestions(self, partial_name: str, limit: int = 5) -> List[Dict]:
        """Get customer suggestions for autocomplete"""
        if not self.customer_cache or not partial_name:
            return []
        
        partial_lower = partial_name.lower()
        suggestions = []
        
        for cache_key, customer_info in self.customer_cache.items():
            if partial_lower in cache_key:
                suggestions.append({
                    "name": customer_info.get("name"),
                    "customer_name": customer_info.get("customer_name"),
                    "gstin": customer_info.get("gstin", ""),
                    "territory": customer_info.get("territory", ""),
                    "disabled": customer_info.get("disabled", False)
                })
                
                if len(suggestions) >= limit:
                    break
        
        return suggestions
    
    def verify_customer_details(self, customer: str) -> Dict:
        """Get detailed customer information"""
        customer_lower = customer.lower()
        
        if customer_lower in self.customer_cache:
            return {
                "found": True,
                "details": self.customer_cache[customer_lower]
            }
        
        # If not in cache, try direct API call
        try:
            status, resp = _verify_resource(self.api_token, self.base_url, "Customer", customer)
            if status:
                return {
                    "found": True,
                    "details": resp if isinstance(resp, dict) else {"name": customer}
                }
        except:
            pass
        
        return {
            "found": False,
            "details": None
        }