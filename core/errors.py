"""Centralized error handling and response helpers."""

from typing import List, Optional, Dict, Any
from fastapi.responses import JSONResponse

class DataQualityError(Exception):
    """Raised when data quality checks fail."""
    pass


class ValidationError(Exception):
    """General validation error for invalid data or configuration."""
    pass


class RequiredSignalMissingError(Exception):
    """
    Raised when required signals for industry validation are missing.
    
    This error should result in INDETERMINATE status, not FAIL,
    since the validation cannot be performed without the required data.
    """
    
    def __init__(self, missing_signals: List[str], available_signals: List[str] = None, industry: str = None):
        """
        Initialize RequiredSignalMissingError.
        
        Args:
            missing_signals: List of required signal names that are missing
            available_signals: List of available signal names in the data
            industry: Industry type for context-specific error messages
        """
        self.missing_signals = missing_signals
        self.available_signals = available_signals or []
        self.industry = industry
        
        # Build descriptive error message
        if len(missing_signals) == 1:
            msg = f"Required signal missing: {missing_signals[0]}"
        else:
            msg = f"Required signals missing: {', '.join(missing_signals)}"
        
        if industry:
            msg = f"{industry} validation requires {msg.lower()}"
        
        if available_signals:
            msg += f" (available: {', '.join(available_signals)})"
        
        super().__init__(msg)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON serialization."""
        return {
            'error_type': 'RequiredSignalMissingError',
            'missing_signals': self.missing_signals,
            'available_signals': self.available_signals,
            'industry': self.industry,
            'message': str(self)
        }

def validation_error_response(
    errors: List[str],
    code: int = 400,
    industry: Optional[str] = None,
    hints: Optional[List[str]] = None
) -> JSONResponse:
    """Create standardized validation error response."""
    
    # Generate actionable hints if not provided
    if not hints:
        hints = []
        error_text = " ".join(errors).lower()
        
        if "column" in error_text or "field" in error_text:
            hints.append("Check CSV column names match expected: timestamp, temperature, pressure, humidity")
            hints.append("Ensure timestamp column exists and is numeric (seconds or Unix time)")
            hints.append("Temperature values should be numeric (Celsius by default)")
        
        if "spec" in error_text or "parameter" in error_text:
            hints.append("Verify specification JSON has 'industry' and 'parameters' fields")
            hints.append("Check parameter names match industry requirements")
            hints.append(f"Industry '{industry}' expects specific parameters - see /industries/{industry}")
        
        if "industry" in error_text:
            hints.append("Supported industries: powder, autoclave, coldchain, haccp, concrete, sterile")
            hints.append("Industry can be specified in spec JSON or as form field")
            hints.append("Check spelling and use lowercase industry names")
    
    # Take top 3 most relevant hints
    hints = hints[:3]
    
    response_body = {
        "error": "Validation Error",
        "code": code,
        "messages": errors,
        "hints": hints
    }
    
    if industry:
        response_body["industry"] = industry
        response_body["docs_url"] = f"/industries/{industry}"
    
    return JSONResponse(status_code=code, content=response_body)

def industry_not_found_response(industry: str) -> JSONResponse:
    """Create response for unknown industry."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "Unknown Industry",
            "code": 400,
            "industry": industry,
            "message": f"Industry '{industry}' is not supported",
            "supported_industries": [
                "powder",
                "autoclave", 
                "coldchain",
                "haccp",
                "concrete",
                "sterile"
            ],
            "hints": [
                "Use lowercase industry names",
                "Check spelling carefully",
                "See /examples for working configurations"
            ]
        }
    )

def missing_columns_response(required: List[str], found: List[str]) -> JSONResponse:
    """Create response for missing CSV columns."""
    missing = set(required) - set(found)
    
    return JSONResponse(
        status_code=400,
        content={
            "error": "Missing CSV Columns",
            "code": 400,
            "required_columns": required,
            "found_columns": found,
            "missing_columns": list(missing),
            "hints": [
                f"Add missing columns: {', '.join(missing)}",
                "Column names are case-sensitive",
                "Use 'timestamp' not 'time' or 'Time'"
            ]
        }
    )