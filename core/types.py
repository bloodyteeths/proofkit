"""
ProofKit Core Types

TypedDict and dataclass definitions for decision envelope structure,
providing backward compatibility for both dict and attribute access patterns.

This module ensures that decision objects can be accessed safely using
both dictionary-style (decision['field']) and attribute-style (decision.field)
access patterns across the codebase.

Example usage:
    from core.types import DecisionEnvelope, safe_get_attr
    
    # Create envelope
    envelope = DecisionEnvelope(
        industry="powder",
        status="PASS", 
        pass=True,
        reasons=["All requirements met"],
        warnings=[],
        flags={}
    )
    
    # Safe access patterns
    industry = safe_get_attr(envelope, 'industry', 'unknown')
    status = envelope.get('status', 'UNKNOWN')  # dict-style
    pass_result = envelope.pass  # attribute-style
"""

from typing import Dict, Any, List, Union, Optional, TypedDict
from typing_extensions import NotRequired
from dataclasses import dataclass


class DecisionEnvelopeDict(TypedDict, total=False):
    """TypedDict for decision envelope structure with optional fields."""
    industry: NotRequired[str]
    status: NotRequired[str] 
    reasons: NotRequired[List[str]]
    warnings: NotRequired[List[str]]
    flags: NotRequired[Dict[str, Any]]
    # Legacy fields for backward compatibility
    decision: NotRequired[str]  # Maps to status
    pass_: NotRequired[bool]    # Use pass_ instead of reserved 'pass' keyword


@dataclass
class DecisionEnvelope:
    """
    Decision envelope structure that supports both dict and attribute access.
    
    This class provides backward compatibility for legacy code that expects
    dictionary access while also supporting modern attribute access patterns.
    """
    industry: str = "powder"
    status: str = "UNKNOWN"
    pass_: bool = False  # Note: using pass_ since pass is reserved keyword
    reasons: List[str] = None
    warnings: List[str] = None  
    flags: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize mutable default values."""
        if self.reasons is None:
            self.reasons = []
        if self.warnings is None:
            self.warnings = []
        if self.flags is None:
            self.flags = {}
    
    def __getitem__(self, key: str) -> Any:
        """Enable dictionary-style access: envelope['key']"""
        # Handle legacy field name mappings
        if key == 'decision':
            return self.status
        elif key == 'pass':
            return self.pass_
        elif hasattr(self, key):
            return getattr(self, key)
        else:
            raise KeyError(f"'{key}' not found in DecisionEnvelope")
    
    def __setitem__(self, key: str, value: Any):
        """Enable dictionary-style assignment: envelope['key'] = value"""
        # Handle legacy field name mappings
        if key == 'decision':
            self.status = value
        elif key == 'pass':
            self.pass_ = value
        elif hasattr(self, key):
            setattr(self, key, value)
        else:
            raise KeyError(f"'{key}' not found in DecisionEnvelope")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Enable dictionary-style get: envelope.get('key', default)"""
        try:
            return self[key]
        except KeyError:
            return default
    
    def keys(self):
        """Return available keys for dict-like interface."""
        return ['industry', 'status', 'pass', 'reasons', 'warnings', 'flags', 'decision', 'pass_']
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dictionary for serialization."""
        return {
            'industry': self.industry,
            'status': self.status,
            'pass': self.pass_,
            'reasons': self.reasons,
            'warnings': self.warnings,
            'flags': self.flags,
            # Legacy field mappings
            'decision': self.status,
            'pass_': self.pass_
        }
    
    def __getattr__(self, name: str) -> Any:
        """Handle special property access for reserved keywords like 'pass'."""
        if name == 'pass':
            return self.pass_
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __setattr__(self, name: str, value: Any) -> None:
        """Handle special property assignment for reserved keywords like 'pass'."""
        if name == 'pass':
            super().__setattr__('pass_', value)
        else:
            super().__setattr__(name, value)


def safe_get_attr(obj: Union[Dict[str, Any], Any], attr: str, default: Any = None) -> Any:
    """
    Safely get attribute from either dict or object, handling legacy field mappings.
    
    Args:
        obj: Dictionary or object to get attribute from
        attr: Attribute name to retrieve
        default: Default value if attribute not found
        
    Returns:
        Attribute value or default
        
    Example:
        # Works with dicts
        value = safe_get_attr({'status': 'PASS'}, 'status', 'UNKNOWN')
        
        # Works with objects
        value = safe_get_attr(decision_obj, 'industry', 'unknown')
        
        # Handles legacy mappings
        value = safe_get_attr(old_dict, 'decision', 'UNKNOWN')  # Maps to 'status'
    """
    if isinstance(obj, dict):
        # Handle legacy field name mappings for dict access
        if attr == 'industry' and 'industry' not in obj:
            return default
        elif attr == 'status' and 'decision' in obj and 'status' not in obj:
            return obj.get('decision', default)
        elif attr == 'pass' and 'pass' in obj:
            return obj.get('pass', default) 
        elif attr == 'pass_' and 'pass_' in obj:
            return obj.get('pass_', default)
        elif attr == 'pass' and 'pass_' in obj and 'pass' not in obj:
            return obj.get('pass_', default)
        else:
            return obj.get(attr, default)
    else:
        # Handle object attribute access
        if hasattr(obj, attr):
            return getattr(obj, attr, default)
        
        # Handle legacy field name mappings for object access  
        elif attr == 'industry' and hasattr(obj, 'industry'):
            return getattr(obj, 'industry', default)
        elif attr == 'status' and hasattr(obj, 'status'):
            return getattr(obj, 'status', default)
        elif attr == 'pass' and hasattr(obj, 'pass_'):
            return getattr(obj, 'pass_', default)
        elif attr == 'reasons' and hasattr(obj, 'reasons'):
            return getattr(obj, 'reasons', default)
        elif attr == 'warnings' and hasattr(obj, 'warnings'):
            return getattr(obj, 'warnings', default)
        elif attr == 'flags' and hasattr(obj, 'flags'):
            return getattr(obj, 'flags', default)
        else:
            return default


def create_decision_envelope(
    industry: str = "powder",
    status: str = "UNKNOWN", 
    pass_result: bool = False,
    reasons: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    flags: Optional[Dict[str, Any]] = None
) -> DecisionEnvelope:
    """
    Create a properly structured decision envelope.
    
    Args:
        industry: Industry type (powder, haccp, etc.)
        status: Decision status (PASS, FAIL, INDETERMINATE) 
        pass_result: Boolean pass/fail result
        reasons: List of decision reasons
        warnings: List of warnings
        flags: Additional flags
        
    Returns:
        DecisionEnvelope with normalized structure
    """
    return DecisionEnvelope(
        industry=industry,
        status=status,
        pass_=pass_result,
        reasons=reasons or [],
        warnings=warnings or [],
        flags=flags or {}
    )


# Usage example in comments:
"""
Example usage for backward compatibility:

from core.types import DecisionEnvelope, safe_get_attr

# Create envelope (new way)
envelope = DecisionEnvelope(
    industry="powder",
    status="PASS",
    pass_=True,
    reasons=["Temperature requirements met"],
    warnings=[],
    flags={"fallback_used": False}
)

# Access patterns that work:
industry = envelope.industry                    # Attribute access
industry = envelope['industry']                 # Dict access
industry = envelope.get('industry', 'unknown')  # Safe dict access
industry = safe_get_attr(envelope, 'industry', 'unknown')  # Universal safe access

# Legacy field mappings:
status = envelope['decision']      # Maps to envelope.status
pass_result = envelope['pass']     # Maps to envelope.pass_
pass_result = envelope.pass        # Property access

# Works with old dict format too:
old_dict = {'decision': 'PASS', 'pass_': True}
status = safe_get_attr(old_dict, 'status', 'UNKNOWN')     # Gets 'decision' 
pass_result = safe_get_attr(old_dict, 'pass', False)      # Gets 'pass_'
"""