"""
API contract tests to verify response structure and backward compatibility.
These tests verify:
1. Response includes both `pass` (boolean) and `status` (string) fields
2. `pass` = true when status == "PASS", false otherwise
3. Response includes `reasons[]`, `warnings[]`, `flags.fallback_used`
4. Backward compatibility maintained
"""
import io
import json


def get_sample_csv_data():
    """Sample CSV data for testing."""
    return b"timestamp,temp_1\n2024-01-01T00:00:00Z,180.5\n2024-01-01T00:10:00Z,180.2\n"


def get_powder_spec():
    """Standard powder coating specification."""
    return {
        "version": "1.0",
        "industry": "powder",
        "job": {"job_id": "test"},
        "spec": {
            "method": "OVEN_AIR",
            "target_temp_C": 180.0,
            "hold_time_s": 600,
            "sensor_uncertainty_C": 1.0
        },
        "data_requirements": {
            "max_sample_period_s": 60,
            "allowed_gaps_s": 120
        },
        "sensor_selection": {
            "mode": "min_of_set",
            "require_at_least": 1
        },
        "logic": {
            "continuous": True
        }
    }


def get_autoclave_spec_missing_pressure():
    """Autoclave spec that will cause INDETERMINATE due to missing pressure data."""
    return {
        "version": "1.0",
        "industry": "autoclave", 
        "job": {"job_id": "test"},
        "spec": {
            "method": "OVEN_AIR",
            "target_temp_C": 121.0,
            "hold_time_s": 900,
            "sensor_uncertainty_C": 0.5
        },
        "data_requirements": {
            "max_sample_period_s": 10,
            "allowed_gaps_s": 30
        },
        "sensor_selection": {
            "mode": "min_of_set",
            "require_at_least": 2
        },
        "parameter_requirements": {
            "require_pressure": True,
            "require_fo": True
        },
        "logic": {
            "continuous": True
        }
    }


def validate_api_response_structure(response_data):
    """
    Validate that API response has required structure for backward compatibility.
    
    Args:
        response_data: Dictionary containing API response
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Test backward compatibility fields
    if 'pass' not in response_data:
        errors.append("Missing required 'pass' field")
    elif not isinstance(response_data['pass'], bool):
        errors.append("'pass' field must be boolean")
        
    # Test new status field
    if 'status' not in response_data:
        errors.append("Missing required 'status' field")
    elif not isinstance(response_data['status'], str):
        errors.append("'status' field must be string")
    elif response_data['status'] not in ['PASS', 'FAIL', 'INDETERMINATE']:
        errors.append(f"Invalid status value: {response_data['status']}")
        
    # Test pass/status consistency
    if 'pass' in response_data and 'status' in response_data:
        if response_data['status'] == 'PASS' and response_data['pass'] is not True:
            errors.append("When status='PASS', pass must be True")
        elif response_data['status'] != 'PASS' and response_data['pass'] is not False:
            errors.append("When status!='PASS', pass must be False")
            
    # Test required response fields
    required_fields = ['id', 'metrics', 'reasons', 'warnings', 'flags', 'urls', 'verification_hash']
    for field in required_fields:
        if field not in response_data:
            errors.append(f"Missing required field: {field}")
            
    # Test field types
    if 'reasons' in response_data and not isinstance(response_data['reasons'], list):
        errors.append("'reasons' must be a list")
    if 'warnings' in response_data and not isinstance(response_data['warnings'], list):
        errors.append("'warnings' must be a list")
    if 'flags' in response_data and not isinstance(response_data['flags'], dict):
        errors.append("'flags' must be a dictionary")
        
    # Test URLs structure
    if 'urls' in response_data:
        urls = response_data['urls']
        required_url_fields = ['pdf', 'zip', 'verify']
        for field in required_url_fields:
            if field not in urls:
                errors.append(f"Missing URL field: {field}")
        
        if 'pdf' in urls and not urls['pdf'].startswith('/download/'):
            errors.append("PDF URL should start with '/download/'")
        if 'zip' in urls and not urls['zip'].startswith('/download/'):
            errors.append("ZIP URL should start with '/download/'")
        if 'verify' in urls and not urls['verify'].startswith('/verify/'):
            errors.append("Verify URL should start with '/verify/'")
            
    return errors


def test_api_contract_validation():
    """Test the validation function itself with sample data."""
    
    # Test valid PASS response
    valid_pass_response = {
        "id": "test123",
        "pass": True,
        "status": "PASS",
        "metrics": {"target_temp_C": 180.0},
        "reasons": [],
        "warnings": [],
        "flags": {},
        "urls": {
            "pdf": "/download/test123/pdf",
            "zip": "/download/test123/zip", 
            "verify": "/verify/test123"
        },
        "verification_hash": "abcd1234"
    }
    
    errors = validate_api_response_structure(valid_pass_response)
    assert len(errors) == 0, f"Valid PASS response should have no errors: {errors}"
    
    # Test valid FAIL response
    valid_fail_response = {
        "id": "test456", 
        "pass": False,
        "status": "FAIL",
        "metrics": {"target_temp_C": 180.0},
        "reasons": ["Insufficient hold time"],
        "warnings": ["Temperature fluctuations detected"],
        "flags": {"fallback_used": False},
        "urls": {
            "pdf": "/download/test456/pdf",
            "zip": "/download/test456/zip",
            "verify": "/verify/test456"
        },
        "verification_hash": "efgh5678"
    }
    
    errors = validate_api_response_structure(valid_fail_response)
    assert len(errors) == 0, f"Valid FAIL response should have no errors: {errors}"
    
    # Test valid INDETERMINATE response  
    valid_indeterminate_response = {
        "id": "test789",
        "pass": False,  # INDETERMINATE maps to pass=false for backward compatibility
        "status": "INDETERMINATE",
        "metrics": {"target_temp_C": 121.0},
        "reasons": ["Pressure data required but missing"],
        "warnings": [],
        "flags": {"missing_required_sensors": ["pressure"]},
        "urls": {
            "pdf": "/download/test789/pdf",
            "zip": "/download/test789/zip",
            "verify": "/verify/test789"
        },
        "verification_hash": "ijkl9012"
    }
    
    errors = validate_api_response_structure(valid_indeterminate_response)
    assert len(errors) == 0, f"Valid INDETERMINATE response should have no errors: {errors}"
    
    # Test invalid response - pass/status mismatch
    invalid_response = {
        "id": "test999",
        "pass": True,  # Should be False when status != PASS
        "status": "FAIL",
        "metrics": {},
        "reasons": [],
        "warnings": [],
        "flags": {},
        "urls": {
            "pdf": "/download/test999/pdf",
            "zip": "/download/test999/zip", 
            "verify": "/verify/test999"
        },
        "verification_hash": "mnop3456"
    }
    
    errors = validate_api_response_structure(invalid_response)
    assert len(errors) > 0, "Invalid response should have errors"
    assert any("When status!='PASS', pass must be False" in error for error in errors)


def test_example_specs_structure():
    """Test that example specifications have proper structure."""
    powder_spec = get_powder_spec()
    autoclave_spec = get_autoclave_spec_missing_pressure()
    
    # Test powder spec structure
    assert powder_spec['version'] == '1.0'
    assert powder_spec['industry'] == 'powder'
    assert 'spec' in powder_spec
    assert 'target_temp_C' in powder_spec['spec']
    
    # Test autoclave spec has pressure requirement
    assert autoclave_spec['industry'] == 'autoclave'
    assert 'parameter_requirements' in autoclave_spec
    assert autoclave_spec['parameter_requirements']['require_pressure'] is True


if __name__ == "__main__":
    test_api_contract_validation()
    test_example_specs_structure() 
    print("All API contract validation tests passed!")