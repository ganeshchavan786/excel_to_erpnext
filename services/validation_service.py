# services/validation_service.py
import uuid
from datetime import datetime
from typing import Dict, List, Tuple, Any
import json

class ValidationService:
    """
    Memory-based validation orchestrator for ERPNext masters validation
    Manages validation sessions, progress tracking, and results
    """
    
    def __init__(self):
        # Memory storage for validation sessions
        self.validation_sessions = {}
        self.master_cache = {}
        
    def create_validation_session(self, rows: List[Dict], columns: List[str]) -> str:
        """Create new validation session and return session_id"""
        session_id = str(uuid.uuid4())
        
        session = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "status": "initialized",
            "total_records": len(rows),
            "processed_records": 0,
            "rows": rows,
            "columns": columns,
            
            # Validation results
            "customer_validation": {
                "status": "pending",
                "passed": 0,
                "warnings": 0,
                "failed": 0,
                "errors": [],
                "suggestions": []
            },
            "item_validation": {
                "status": "pending", 
                "passed": 0,
                "warnings": 0,
                "failed": 0,
                "errors": [],
                "suggestions": []
            },
            
            # Overall summary
            "validation_summary": {
                "can_proceed": False,
                "critical_errors": 0,
                "warnings": 0,
                "auto_corrections": []
            }
        }
        
        self.validation_sessions[session_id] = session
        return session_id
    
    def get_validation_status(self, session_id: str) -> Dict:
        """Get current validation status"""
        session = self.validation_sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
            
        return {
            "session_id": session_id,
            "status": session["status"],
            "progress": {
                "total_records": session["total_records"],
                "processed_records": session["processed_records"],
                "percentage": round((session["processed_records"] / session["total_records"]) * 100, 2) if session["total_records"] > 0 else 0
            },
            "customer_validation": session["customer_validation"],
            "item_validation": session["item_validation"],
            "validation_summary": session["validation_summary"]
        }
    
    def validate_excel_data(self, session_id: str, api_token: str, base_url: str) -> Dict:
        """
        Main validation orchestrator
        Progressive validation: Customer -> Items -> Summary
        """
        session = self.validation_sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        
        try:
            session["status"] = "validating"
            
            # Step 1: Customer Validation
            self._validate_customers(session, api_token, base_url)
            
            # Step 2: Item Validation  
            self._validate_items(session, api_token, base_url)
            
            # Step 3: Generate Summary
            self._generate_validation_summary(session)
            
            session["status"] = "completed"
            return self.get_validation_status(session_id)
            
        except Exception as e:
            session["status"] = "failed"
            session["validation_summary"]["error"] = str(e)
            return {"error": str(e)}
    
    def _validate_customers(self, session: Dict, api_token: str, base_url: str):
        """Customer-specific validation logic"""
        from .customer_validator import CustomerValidator
        
        validator = CustomerValidator(api_token, base_url)
        rows = session["rows"]
        
        # Extract unique customers from rows
        customers = set()
        for row in rows:
            customer = row.get("Customer") or row.get("Customer Name") or ""
            if customer.strip():
                customers.add(customer.strip())
        
        customer_list = list(customers)
        session["customer_validation"]["status"] = "validating"
        
        # Validate customer batch
        results = validator.validate_customer_batch(customer_list)
        
        # Process results
        for result in results:
            if result["status"] == "passed":
                session["customer_validation"]["passed"] += 1
            elif result["status"] == "warning":
                session["customer_validation"]["warnings"] += 1
                session["customer_validation"]["errors"].append({
                    "type": "warning",
                    "customer": result["customer"],
                    "message": result["message"],
                    "suggestion": result.get("suggestion")
                })
            else:  # failed
                session["customer_validation"]["failed"] += 1
                session["customer_validation"]["errors"].append({
                    "type": "error",
                    "customer": result["customer"],
                    "message": result["message"],
                    "suggestion": result.get("suggestion")
                })
        
        session["customer_validation"]["status"] = "completed"
        session["processed_records"] = len(customer_list)
    
    def _validate_items(self, session: Dict, api_token: str, base_url: str):
        """Item-specific validation logic"""
        from .item_validator import ItemValidator
        
        validator = ItemValidator(api_token, base_url)
        rows = session["rows"]
        
        # Extract unique items from rows
        items = set()
        for row in rows:
            item_code = row.get("Item Code") or row.get("Item") or ""
            if item_code.strip():
                items.add(item_code.strip())
        
        item_list = list(items)
        session["item_validation"]["status"] = "validating"
        
        # Validate item batch
        results = validator.validate_item_batch(item_list)
        
        # Process results
        for result in results:
            if result["status"] == "passed":
                session["item_validation"]["passed"] += 1
            elif result["status"] == "warning":
                session["item_validation"]["warnings"] += 1
                session["item_validation"]["errors"].append({
                    "type": "warning",
                    "item": result["item"],
                    "message": result["message"],
                    "suggestion": result.get("suggestion")
                })
            else:  # failed
                session["item_validation"]["failed"] += 1
                session["item_validation"]["errors"].append({
                    "type": "error", 
                    "item": result["item"],
                    "message": result["message"],
                    "suggestion": result.get("suggestion")
                })
        
        session["item_validation"]["status"] = "completed"
        session["processed_records"] += len(item_list)
    
    def _generate_validation_summary(self, session: Dict):
        """Generate overall validation summary"""
        customer_val = session["customer_validation"]
        item_val = session["item_validation"]
        summary = session["validation_summary"]
        
        # Count critical errors
        critical_errors = customer_val["failed"] + item_val["failed"]
        warnings = customer_val["warnings"] + item_val["warnings"]
        
        summary["critical_errors"] = critical_errors
        summary["warnings"] = warnings
        summary["can_proceed"] = critical_errors == 0
        
        # Generate auto-correction suggestions
        auto_corrections = []
        
        # Customer auto-corrections
        for error in customer_val["errors"]:
            if error.get("suggestion") and error["type"] == "warning":
                auto_corrections.append({
                    "type": "customer",
                    "original": error["customer"],
                    "suggested": error["suggestion"]
                })
        
        # Item auto-corrections
        for error in item_val["errors"]:
            if error.get("suggestion") and error["type"] == "warning":
                auto_corrections.append({
                    "type": "item", 
                    "original": error["item"],
                    "suggested": error["suggestion"]
                })
        
        summary["auto_corrections"] = auto_corrections
    
    def get_validation_report(self, session_id: str) -> Dict:
        """Get detailed validation report"""
        session = self.validation_sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        
        return {
            "session_id": session_id,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_records": session["total_records"],
                "customer_validation": {
                    "total_customers": session["customer_validation"]["passed"] + 
                                     session["customer_validation"]["warnings"] + 
                                     session["customer_validation"]["failed"],
                    "passed": session["customer_validation"]["passed"],
                    "warnings": session["customer_validation"]["warnings"],
                    "failed": session["customer_validation"]["failed"]
                },
                "item_validation": {
                    "total_items": session["item_validation"]["passed"] + 
                                 session["item_validation"]["warnings"] + 
                                 session["item_validation"]["failed"],
                    "passed": session["item_validation"]["passed"],
                    "warnings": session["item_validation"]["warnings"],
                    "failed": session["item_validation"]["failed"]
                },
                "can_proceed": session["validation_summary"]["can_proceed"],
                "critical_errors": session["validation_summary"]["critical_errors"],
                "total_warnings": session["validation_summary"]["warnings"]
            },
            "detailed_errors": {
                "customers": session["customer_validation"]["errors"],
                "items": session["item_validation"]["errors"]
            },
            "auto_corrections": session["validation_summary"]["auto_corrections"]
        }
    
    def apply_corrections(self, session_id: str, corrections: List[Dict]) -> Dict:
        """Apply auto-corrections to session data"""
        session = self.validation_sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        
        applied_count = 0
        for correction in corrections:
            if correction["type"] == "customer":
                # Apply customer name correction to all matching rows
                for row in session["rows"]:
                    if (row.get("Customer") or row.get("Customer Name") or "").strip() == correction["original"]:
                        if "Customer" in row:
                            row["Customer"] = correction["suggested"]
                        if "Customer Name" in row:
                            row["Customer Name"] = correction["suggested"]
                        applied_count += 1
            
            elif correction["type"] == "item":
                # Apply item code correction to all matching rows
                for row in session["rows"]:
                    if (row.get("Item Code") or row.get("Item") or "").strip() == correction["original"]:
                        if "Item Code" in row:
                            row["Item Code"] = correction["suggested"]
                        if "Item" in row:
                            row["Item"] = correction["suggested"]
                        applied_count += 1
        
        return {
            "success": True,
            "applied_corrections": applied_count,
            "message": f"Applied {applied_count} corrections successfully"
        }
    
    def cleanup_validation_session(self, session_id: str):
        """Clean up session from memory"""
        if session_id in self.validation_sessions:
            del self.validation_sessions[session_id]
            return True
        return False

# Global instance for Flask app
validation_service = ValidationService()