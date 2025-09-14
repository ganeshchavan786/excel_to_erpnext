# services/item_validator.py
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

class ItemValidator:
    """
    Item-specific validation for ERPNext masters
    Handles item existence, HSN validation, UOM checking, price variance
    """
    
    def __init__(self, api_token: str, base_url: str):
        self.api_token = api_token
        self.base_url = base_url
        self.item_cache = {}
        self.uom_cache = {}
        self.hsn_cache = {}
        
    def validate_item_batch(self, item_list: List[str]) -> List[Dict]:
        """
        Validate batch of items
        Returns list of validation results
        """
        results = []
        
        # Load caches if not already loaded
        if not self.item_cache:
            self._load_item_cache()
        if not self.uom_cache:
            self._load_uom_cache()
        
        for item in item_list:
            result = self._validate_single_item(item)
            results.append(result)
        
        return results
    
    def _load_item_cache(self):
        """Load all items from ERPNext into memory cache"""
        try:
            print("Loading item cache...")  # Debug line
            path = "api/resource/Item"
            params = "?fields=[\"item_code\",\"item_name\",\"gst_hsn_code\",\"standard_rate\",\"stock_uom\",\"disabled\",\"has_variants\",\"is_stock_item\"]&limit_page_length=1000"
            status, resp = _get(self.api_token, self.base_url, path + params)
            
            print(f"API Status: {status}")  # Debug line
            
            if status == 200:
                data = resp.json()
                items = data.get("data", [])
                print(f"Found {len(items)} items")  # Debug line
                
                for item in items:
                    item_code = item.get("item_code", "")
                    item_name = item.get("item_name", "")
                    
                    item_info = {
                        "item_code": item_code,
                        "item_name": item_name,
                        "gst_hsn_code": item.get("gst_hsn_code", ""),
                        "standard_rate": float(item.get("standard_rate", 0)),
                        "stock_uom": item.get("stock_uom", ""),
                        "disabled": item.get("disabled", 0),
                        "has_variants": item.get("has_variants", 0),
                        "is_stock_item": item.get("is_stock_item", 1)
                    }
                    
                    # Store by both item_code and item_name
                    if item_code:
                        self.item_cache[item_code.lower()] = item_info
                    if item_name and item_name != item_code:
                        self.item_cache[item_name.lower()] = item_info
            else:
                print(f"API Error: Status {status}")  # Debug line
                        
        except Exception as e:
            print(f"Error loading item cache: {e}")
    
    def _load_uom_cache(self):
        """Load UOM list from ERPNext"""
        try:
            print("Loading UOM cache...")  # Debug line
            path = "api/resource/UOM"
            params = "?fields=[\"uom_name\",\"enabled\"]&limit_page_length=500"
            status, resp = _get(self.api_token, self.base_url, path + params)
            
            if status == 200:
                data = resp.json()
                uoms = data.get("data", [])
                print(f"Found {len(uoms)} UOMs")  # Debug line
                
                for uom in uoms:
                    uom_name = uom.get("uom_name", "")
                    if uom_name:
                        self.uom_cache[uom_name.lower()] = {
                            "uom_name": uom_name,
                            "enabled": uom.get("enabled", 1)
                        }
                        
        except Exception as e:
            print(f"Error loading UOM cache: {e}")
    
    def _validate_single_item(self, item_code: str) -> Dict:
        """Validate single item with comprehensive checks"""
        if not item_code or not item_code.strip():
            return {
                "item": item_code,
                "status": "failed",
                "message": "Item code is empty",
                "suggestion": None
            }
        
        item_clean = item_code.strip()
        item_lower = item_clean.lower()
        
        # 1. Exact match check
        if item_lower in self.item_cache:
            item_info = self.item_cache[item_lower]
            
            # Check if disabled
            if item_info.get("disabled"):
                return {
                    "item": item_code,
                    "status": "warning",
                    "message": "Item is disabled in ERPNext",
                    "suggestion": "Enable item or use different item code"
                }
            
            # Check if has variants (template item)
            if item_info.get("has_variants"):
                return {
                    "item": item_code,
                    "status": "warning", 
                    "message": "Item is a template with variants",
                    "suggestion": "Use specific variant instead of template"
                }
            
            return {
                "item": item_code,
                "status": "passed",
                "message": "Item found and active",
                "details": item_info
            }
        
        # 2. Partial match / typo detection
        suggestion = self._find_similar_item(item_clean)
        if suggestion:
            return {
                "item": item_code,
                "status": "warning",
                "message": "Item not found exactly, similar item available",
                "suggestion": suggestion
            }
        
        # 3. No match found
        return {
            "item": item_code,
            "status": "failed",
            "message": "Item not found in ERPNext",
            "suggestion": "Create new item"
        }
    
    def _find_similar_item(self, item_code: str) -> str:
        """Find similar item using fuzzy matching"""
        if not self.item_cache:
            return None
        
        item_codes = []
        for cache_key, item_info in self.item_cache.items():
            item_codes.append(item_info.get("item_code", ""))
            item_codes.append(item_info.get("item_name", ""))
        
        # Remove empty codes
        item_codes = [code for code in item_codes if code]
        
        # Find best matches using difflib
        matches = difflib.get_close_matches(item_code, item_codes, n=1, cutoff=0.7)
        
        if matches:
            return matches[0]
        
        return None
    
    def validate_hsn_code(self, hsn_code: str) -> Dict:
        """Validate HSN code format and existence"""
        if not hsn_code or not hsn_code.strip():
            return {
                "valid": False,
                "message": "HSN code is empty"
            }
        
        hsn_clean = hsn_code.strip()
        
        # HSN code format validation (4, 6, or 8 digits)
        if not re.match(r'^\d{4}$|^\d{6}$|^\d{8}$', hsn_clean):
            return {
                "valid": False,
                "message": "HSN code must be 4, 6, or 8 digits"
            }
        
        return {
            "valid": True,
            "message": "HSN code format is valid",
            "hsn_code": hsn_clean
        }
    
    def validate_uom(self, uom: str) -> Dict:
        """Validate UOM existence"""
        if not uom or not uom.strip():
            return {
                "valid": False,
                "message": "UOM is empty",
                "suggestion": "Nos"
            }
        
        uom_clean = uom.strip()
        uom_lower = uom_clean.lower()
        
        # Check exact match
        if uom_lower in self.uom_cache:
            uom_info = self.uom_cache[uom_lower]
            if not uom_info.get("enabled"):
                return {
                    "valid": False,
                    "message": "UOM is disabled in ERPNext",
                    "suggestion": "Enable UOM or use different UOM"
                }
            return {
                "valid": True,
                "message": "UOM found and active"
            }
        
        # Common UOM standardizations
        uom_mappings = {
            "nos": "Nos",
            "each": "Nos", 
            "pcs": "Nos",
            "pieces": "Nos",
            "kg": "Kg",
            "kilogram": "Kg",
            "gram": "Gm",
            "gms": "Gm",
            "liter": "Litre",
            "litre": "Litre",
            "meter": "Meter",
            "metre": "Meter",
            "box": "Box",
            "carton": "Carton",
            "dozen": "Dozen"
        }
        
        # Check if standardization available
        if uom_lower in uom_mappings:
            standard_uom = uom_mappings[uom_lower]
            if standard_uom.lower() in self.uom_cache:
                return {
                    "valid": True,
                    "message": "UOM standardized",
                    "suggestion": standard_uom
                }
        
        return {
            "valid": False,
            "message": "UOM not found in ERPNext",
            "suggestion": "Nos"
        }
    
    def validate_item_rate(self, item_code: str, rate: float) -> Dict:
        """Validate item rate against standard rate"""
        if not item_code or rate is None:
            return {"valid": True, "message": "No rate validation needed"}
        
        item_lower = item_code.lower()
        if item_lower not in self.item_cache:
            return {"valid": True, "message": "Item not found for rate validation"}
        
        item_info = self.item_cache[item_lower]
        standard_rate = item_info.get("standard_rate", 0)
        
        if standard_rate == 0:
            return {"valid": True, "message": "No standard rate set"}
        
        # Check variance (20% threshold)
        variance = abs(rate - standard_rate) / standard_rate * 100
        
        if variance > 20:
            return {
                "valid": False,
                "message": f"Rate variance {variance:.1f}% from standard rate ₹{standard_rate}",
                "warning": True,
                "standard_rate": standard_rate,
                "current_rate": rate
            }
        
        return {
            "valid": True,
            "message": "Rate within acceptable range"
        }
    
    def get_item_suggestions(self, partial_code: str, limit: int = 5) -> List[Dict]:
        """Get item suggestions for autocomplete"""
        if not self.item_cache or not partial_code:
            return []
        
        partial_lower = partial_code.lower()
        suggestions = []
        
        for cache_key, item_info in self.item_cache.items():
            if partial_lower in cache_key:
                suggestions.append({
                    "item_code": item_info.get("item_code"),
                    "item_name": item_info.get("item_name"),
                    "gst_hsn_code": item_info.get("gst_hsn_code", ""),
                    "standard_rate": item_info.get("standard_rate", 0),
                    "stock_uom": item_info.get("stock_uom", ""),
                    "disabled": item_info.get("disabled", False)
                })
                
                if len(suggestions) >= limit:
                    break
        
        return suggestions
    
    def get_item_details(self, item_code: str) -> Dict:
        """Get detailed item information"""
        item_lower = item_code.lower()
        
        if item_lower in self.item_cache:
            return {
                "found": True,
                "details": self.item_cache[item_lower]
            }
        
        # If not in cache, try direct API call
        try:
            status, resp = _verify_resource(self.api_token, self.base_url, "Item", item_code)
            if status:
                return {
                    "found": True,
                    "details": resp if isinstance(resp, dict) else {"item_code": item_code}
                }
        except:
            pass
        
        return {
            "found": False,
            "details": None
        }