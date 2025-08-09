"""
Test Decision Envelope Backward Compatibility

Tests that ensure the decision envelope structure works correctly with
both old dict-style access patterns and new attribute-style patterns.

This module validates:
1. DecisionEnvelope supports both dict and attribute access
2. safe_get_attr works with various data structures  
3. Legacy field mappings (decision -> status, pass -> pass_) work
4. Compilation function returns proper envelope structure
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.types import DecisionEnvelope, safe_get_attr, create_decision_envelope
from core.models import DecisionResult


class TestDecisionEnvelope:
    """Test DecisionEnvelope class functionality."""
    
    def test_envelope_creation(self):
        """Test creating a decision envelope."""
        envelope = create_decision_envelope(
            industry="powder",
            status="PASS",
            pass_result=True,
            reasons=["All requirements met"],
            warnings=["Minor issue"],
            flags={"test": True}
        )
        
        assert envelope.industry == "powder"
        assert envelope.status == "PASS"
        assert envelope.pass_ == True
        assert envelope.reasons == ["All requirements met"]
        assert envelope.warnings == ["Minor issue"]
        assert envelope.flags == {"test": True}
    
    def test_envelope_dict_access(self):
        """Test dictionary-style access patterns."""
        envelope = create_decision_envelope(
            industry="haccp",
            status="FAIL", 
            pass_result=False,
            reasons=["Temperature too high"]
        )
        
        # Basic dict access
        assert envelope['industry'] == "haccp"
        assert envelope['status'] == "FAIL"
        assert envelope['pass'] == False  # Maps to pass_
        assert envelope['reasons'] == ["Temperature too high"]
        
        # Legacy field mappings
        assert envelope['decision'] == "FAIL"  # Maps to status
        assert envelope['pass_'] == False
    
    def test_envelope_get_method(self):
        """Test get method with defaults."""
        envelope = create_decision_envelope(industry="powder")
        
        assert envelope.get('industry') == "powder"
        assert envelope.get('missing_key', 'default') == 'default'
        assert envelope.get('status', 'UNKNOWN') == "UNKNOWN"
        assert envelope.get('decision', 'UNKNOWN') == "UNKNOWN"  # Legacy mapping
    
    def test_envelope_property_access(self):
        """Test property access for 'pass' keyword."""
        envelope = create_decision_envelope(pass_result=True)
        
        # Property access - need to use getattr for reserved keyword
        assert getattr(envelope, 'pass') == True
        
        # Setting via property
        setattr(envelope, 'pass', False)
        assert envelope.pass_ == False
        assert getattr(envelope, 'pass') == False
    
    def test_envelope_dict_assignment(self):
        """Test dictionary-style assignment."""
        envelope = create_decision_envelope()
        
        envelope['industry'] = "autoclave"
        envelope['status'] = "PASS"
        envelope['pass'] = True
        envelope['decision'] = "INDETERMINATE"  # Should update status
        
        assert envelope.industry == "autoclave"
        assert envelope.status == "INDETERMINATE"  # Updated by legacy mapping
        assert envelope.pass_ == True
    
    def test_envelope_to_dict(self):
        """Test conversion to dictionary."""
        envelope = create_decision_envelope(
            industry="sterile",
            status="PASS",
            pass_result=True,
            reasons=["Valid"],
            warnings=[],
            flags={}
        )
        
        result_dict = envelope.to_dict()
        
        assert result_dict['industry'] == "sterile"
        assert result_dict['status'] == "PASS"
        assert result_dict['pass'] == True
        assert result_dict['decision'] == "PASS"  # Legacy mapping
        assert result_dict['pass_'] == True  # Legacy mapping


class TestSafeGetAttr:
    """Test safe_get_attr function."""
    
    def test_safe_get_dict_access(self):
        """Test safe getter with dictionary objects."""
        test_dict = {
            'industry': 'powder',
            'status': 'PASS',
            'pass_': True,
            'reasons': ['Valid'],
            'warnings': [],
            'flags': {}
        }
        
        assert safe_get_attr(test_dict, 'industry') == 'powder'
        assert safe_get_attr(test_dict, 'status') == 'PASS'
        assert safe_get_attr(test_dict, 'pass') == True  # Maps to pass_
        assert safe_get_attr(test_dict, 'missing', 'default') == 'default'
    
    def test_safe_get_legacy_dict_mappings(self):
        """Test safe getter with legacy dictionary field names."""
        legacy_dict = {
            'decision': 'FAIL',
            'pass_': False,
            'reasons': ['Temperature too low']
        }
        
        # Legacy mappings should work
        assert safe_get_attr(legacy_dict, 'status', 'UNKNOWN') == 'FAIL'  # decision -> status
        assert safe_get_attr(legacy_dict, 'pass', False) == False  # pass_ -> pass
        assert safe_get_attr(legacy_dict, 'industry', 'unknown') == 'unknown'  # Missing field
    
    def test_safe_get_object_access(self):
        """Test safe getter with object attribute access."""
        envelope = create_decision_envelope(
            industry="concrete",
            status="PASS",
            pass_result=True
        )
        
        assert safe_get_attr(envelope, 'industry') == "concrete"
        assert safe_get_attr(envelope, 'status') == "PASS"
        assert safe_get_attr(envelope, 'pass') == True
        assert safe_get_attr(envelope, 'missing', 'default') == 'default'
    
    def test_safe_get_decision_result_model(self):
        """Test safe getter with DecisionResult Pydantic model."""
        decision_result = DecisionResult(
            pass_=True,
            status="PASS",
            job_id="test_job",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=600.0,
            required_hold_time_s=600,
            max_temp_C=185.0,
            min_temp_C=175.0,
            reasons=["All requirements met"],
            warnings=[],
            flags={}
        )
        
        assert safe_get_attr(decision_result, 'status') == "PASS"
        assert safe_get_attr(decision_result, 'pass') == True  # Maps to pass_
        assert safe_get_attr(decision_result, 'pass_') == True
        assert safe_get_attr(decision_result, 'job_id') == "test_job"
        assert safe_get_attr(decision_result, 'reasons') == ["All requirements met"]
        assert safe_get_attr(decision_result, 'flags') == {}


class TestBackwardCompatibility:
    """Test backward compatibility scenarios."""
    
    def test_old_code_dict_access_pattern(self):
        """Test that old code using dict access patterns still works."""
        # Simulate old code expecting dictionary structure
        envelope = create_decision_envelope(
            industry="powder",
            status="PASS",
            pass_result=True,
            reasons=["Temperature requirements met"],
            warnings=["Minor timing issue"]
        )
        
        # Old code patterns that should continue to work
        industry = envelope.get('industry', 'unknown')
        decision = envelope.get('decision', 'UNKNOWN')  # Legacy field
        pass_result = envelope.get('pass', False)       # Legacy field  
        reasons = envelope.get('reasons', [])
        warnings = envelope.get('warnings', [])
        
        assert industry == "powder"
        assert decision == "PASS"
        assert pass_result == True
        assert reasons == ["Temperature requirements met"]
        assert warnings == ["Minor timing issue"]
    
    def test_new_code_attribute_access_pattern(self):
        """Test that new code using attribute access patterns works."""
        envelope = create_decision_envelope(
            industry="haccp",
            status="FAIL",
            pass_result=False
        )
        
        # New code patterns
        assert envelope.industry == "haccp"
        assert envelope.status == "FAIL"
        assert envelope.pass_ == False
        assert getattr(envelope, 'pass') == False  # Property access via getattr
        assert len(envelope.reasons) == 0  # Default empty list
        assert len(envelope.warnings) == 0  # Default empty list
        assert len(envelope.flags) == 0    # Default empty dict
    
    def test_mixed_access_patterns(self):
        """Test mixing dict and attribute access patterns."""
        envelope = create_decision_envelope(industry="sterile")
        
        # Mix of access patterns should work
        envelope['status'] = "INDETERMINATE"  # Dict assignment
        envelope.pass_ = None  # Attribute assignment 
        envelope['reasons'] = ["Inconclusive data"]  # Dict assignment
        
        # Read back using different patterns
        assert envelope.status == "INDETERMINATE"  # Attribute access
        assert envelope['status'] == "INDETERMINATE"  # Dict access
        assert envelope.get('decision') == "INDETERMINATE"  # Legacy mapping
        assert safe_get_attr(envelope, 'pass') is None  # Safe getter
    
    def test_json_serialization_compatibility(self):
        """Test that envelope can be JSON serialized like old dict format."""
        import json
        
        envelope = create_decision_envelope(
            industry="coldchain",
            status="PASS",
            pass_result=True,
            reasons=["Storage temperature maintained"],
            flags={"sensor_fallback": False}
        )
        
        # Should be able to serialize envelope dict representation
        envelope_dict = envelope.to_dict()
        json_str = json.dumps(envelope_dict, default=str)
        
        # Should deserialize back to usable dict
        restored_dict = json.loads(json_str)
        
        assert restored_dict['industry'] == "coldchain"
        assert restored_dict['status'] == "PASS"
        assert restored_dict['pass'] == True
        assert restored_dict['decision'] == "PASS"  # Legacy field
        assert restored_dict['reasons'] == ["Storage temperature maintained"]
        assert restored_dict['flags']['sensor_fallback'] == False
    
    def test_audit_runner_compatibility(self):
        """Test compatibility with audit runner access patterns."""
        # Simulate the audit runner's expected usage pattern
        
        # Create envelope like make_decision would return
        envelope = create_decision_envelope(
            industry="powder",
            status="PASS", 
            pass_result=True,
            reasons=["Hold time requirement met: 610s ≥ 600s"],
            warnings=[],
            flags={"fallback_used": False}
        )
        
        # Audit runner tries to get decision status
        decision = safe_get_attr(envelope, 'status', 'UNKNOWN')
        assert decision == "PASS"
        
        # Should also work with legacy field name
        decision_legacy = safe_get_attr(envelope, 'decision', 'UNKNOWN') 
        assert decision_legacy == "PASS"
        
        # Should handle missing industry field gracefully
        industry = safe_get_attr(envelope, 'industry', 'unknown')
        assert industry == "powder"
        
        # Test with old-style dict (before envelope introduction)
        old_dict = {'decision': 'FAIL', 'pass_': False}
        decision_from_old = safe_get_attr(old_dict, 'status', 'UNKNOWN')
        assert decision_from_old == 'FAIL'  # Maps from 'decision'
        
        pass_from_old = safe_get_attr(old_dict, 'pass', False)
        assert pass_from_old == False  # Maps from 'pass_'


if __name__ == "__main__":
    # Run a quick test to verify basic functionality
    envelope = create_decision_envelope(
        industry="powder",
        status="PASS",
        pass_result=True,
        reasons=["Test passed"]
    )
    
    print("✓ Envelope creation works")
    print(f"✓ Dict access: {envelope['status']}")
    print(f"✓ Attribute access: {envelope.status}")
    print(f"✓ Legacy mapping: {envelope['decision']}")
    print(f"✓ Safe getter: {safe_get_attr(envelope, 'industry')}")
    print("All basic tests passed!")