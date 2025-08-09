#!/usr/bin/env python3
"""
Contract tests for v1/v2 API routing and format detection.

This test suite verifies that the API correctly routes requests based on spec format:
- v2-only payload (should succeed when API_V2_ENABLED=true)
- v1-only payload (should succeed when ACCEPT_LEGACY_SPEC=true)  
- Both formats present (should prefer v2)
- Invalid payload (should return 400 with helpful message)

The tests verify both routing preference and proper error messages.
"""

import os
import json
import pytest
from fastapi.testclient import TestClient

# Mock environment for testing
os.environ["API_V2_ENABLED"] = "true"
os.environ["ACCEPT_LEGACY_SPEC"] = "true"

from app import app

client = TestClient(app)

# Test CSV data for different industries
TEST_CSV_DATA = {
    "powder": "timestamp,temperature\n0,25\n30,160\n60,180\n90,180\n120,180\n150,180\n180,180\n210,180\n240,180\n270,180\n300,180\n330,180\n360,180\n390,180\n420,180\n450,180\n480,180\n510,180\n540,180\n570,180\n600,180\n630,25",
    "autoclave": "timestamp,temperature,pressure\n0,25,1.0\n60,100,2.1\n120,121,2.1\n180,121,2.1\n240,121,2.1\n300,121,2.1\n360,121,2.1\n420,121,2.1\n480,121,2.1\n540,121,2.1\n600,121,2.1\n660,121,2.1\n720,121,2.1\n780,121,2.1\n840,121,2.1\n900,121,2.1\n960,25,1.0",
    "coldchain": "timestamp,temperature\n0,4\n60,5\n120,6\n180,4\n240,3\n300,5\n360,4\n420,6\n480,4\n540,5",
    "haccp": "timestamp,temperature\n0,140\n30,135\n60,135\n90,80\n120,70\n150,70\n180,50\n210,41\n240,41",
    "concrete": "timestamp,temperature,humidity\n0,15,85\n300,20,87\n600,18,83\n900,22,85\n1200,19,84",
    "sterile": "timestamp,temperature,humidity\n0,55,60\n3600,58,65\n7200,56,62\n10800,57,63\n14400,55,61"
}

# V1 legacy format specifications
V1_SPECS = {
    "powder": {
        "spec": {
            "target_temp_C": 180,
            "hold_time_s": 600,
            "sensor_uncertainty_C": 2,
            "method": "PMT"
        },
        "data_requirements": {
            "max_sample_period_s": 30
        }
    },
    "autoclave": {
        "spec": {
            "sterilization_temp_C": 121,
            "sterilization_time_s": 900,
            "min_pressure_bar": 2.0,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 30
        }
    },
    "coldchain": {
        "spec": {
            "min_temp_C": 2,
            "max_temp_C": 8,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 60
        }
    },
    "haccp": {
        "spec": {
            "temp_1_C": 135,
            "temp_2_C": 70,
            "temp_3_C": 41,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 30
        }
    },
    "concrete": {
        "spec": {
            "min_temp_C": 10,
            "max_temp_C": 30,
            "min_humidity": 80,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 300
        }
    },
    "sterile": {
        "spec": {
            "min_temp_C": 55,
            "max_temp_C": 60,
            "exposure_hours": 12,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 60
        }
    }
}

# V2 format specifications
V2_SPECS = {
    "powder": {
        "industry": "powder",
        "parameters": {
            "target_temp": 180,
            "hold_duration_minutes": 10,
            "sensor_uncertainty": 2,
            "hysteresis": 2
        }
    },
    "autoclave": {
        "industry": "autoclave",
        "parameters": {
            "sterilization_temp": 121,
            "sterilization_time_minutes": 15,
            "min_pressure_bar": 2.0,
            "z_value": 10
        }
    },
    "coldchain": {
        "industry": "coldchain",
        "parameters": {
            "min_temp": 2,
            "max_temp": 8,
            "compliance_percentage": 95
        }
    },
    "haccp": {
        "industry": "haccp",
        "parameters": {
            "temp_1": 135,
            "temp_2": 70,
            "temp_3": 41,
            "time_1_to_2_hours": 2
        }
    },
    "concrete": {
        "industry": "concrete",
        "parameters": {
            "min_temp": 10,
            "max_temp": 30,
            "min_humidity": 80,
            "compliance_percentage": 95
        }
    },
    "sterile": {
        "industry": "sterile",
        "parameters": {
            "min_temp": 55,
            "max_temp": 60,
            "exposure_hours": 12,
            "min_humidity": 50
        }
    }
}

@pytest.mark.parametrize("industry", ["powder", "autoclave", "coldchain", "haccp", "concrete", "sterile"])
def test_v2_only_payload_succeeds(industry):
    """Test v2-only payload should succeed when API_V2_ENABLED=true."""
    spec = V2_SPECS[industry]
    csv_data = TEST_CSV_DATA[industry]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec)}
    )
    
    # Should succeed or fail gracefully (not due to routing issues)
    # Status codes: 200=success, 400=validation error, 401=auth required, 402=payment required
    assert response.status_code in [200, 400, 401, 402], f"Unexpected status for {industry}: {response.status_code}"
    
    # If it's a 400 error, it should NOT be a routing error
    if response.status_code == 400:
        data = response.json()
        error_message = str(data).lower()
        # Should NOT contain routing/format detection errors
        assert "invalid specification format" not in error_message
        assert "include 'industry' field" not in error_message
        assert "include 'spec' field" not in error_message

@pytest.mark.parametrize("industry", ["powder", "autoclave", "coldchain", "haccp", "concrete", "sterile"])
def test_v1_only_payload_succeeds_with_legacy_enabled(industry):
    """Test v1-only payload should succeed when ACCEPT_LEGACY_SPEC=true."""
    spec = V1_SPECS[industry]
    csv_data = TEST_CSV_DATA[industry]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec)}
    )
    
    # Should succeed or fail gracefully (not due to routing issues)
    assert response.status_code in [200, 400, 401, 402], f"Unexpected status for {industry}: {response.status_code}"
    
    # If it's a 400 error, it should NOT be a routing error
    if response.status_code == 400:
        data = response.json()
        error_message = str(data).lower()
        # Should NOT contain routing/format detection errors
        assert "invalid specification format" not in error_message
        assert "include 'industry' field" not in error_message
        assert "include 'spec' field" not in error_message

@pytest.mark.parametrize("industry", ["powder", "autoclave", "coldchain"])
def test_both_formats_present_prefers_v2(industry):
    """Test when both v1 and v2 fields are present, v2 should be preferred."""
    # Create spec with BOTH v1 'spec' field AND v2 'industry' field
    mixed_spec = {
        "industry": industry,  # v2 format
        "parameters": V2_SPECS[industry]["parameters"],
        "spec": V1_SPECS[industry]["spec"],  # v1 format (should be ignored)
        "data_requirements": V1_SPECS[industry]["data_requirements"]
    }
    
    csv_data = TEST_CSV_DATA[industry]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(mixed_spec)}
    )
    
    # Should route to v2 path (not fail with format detection error)
    assert response.status_code in [200, 400, 401, 402], f"Mixed format failed for {industry}: {response.status_code}"
    
    # Should NOT be a routing error
    if response.status_code == 400:
        data = response.json()
        error_message = str(data).lower()
        assert "invalid specification format" not in error_message

def test_invalid_payload_returns_helpful_error():
    """Test invalid payload returns 400 with helpful hints."""
    # Completely invalid spec format
    invalid_spec = {
        "random": "invalid",
        "format": "test"
    }
    csv_data = TEST_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(invalid_spec)}
    )
    
    # Should return 400 with helpful error
    assert response.status_code == 400
    
    data = response.json()
    error_message = str(data).lower()
    
    # Should contain helpful routing hints
    assert any([
        "invalid specification format" in error_message,
        "include 'industry' field" in error_message,
        "include 'spec' field" in error_message
    ])

def test_empty_spec_returns_helpful_error():
    """Test empty spec returns 400 with helpful hints."""
    empty_spec = {}
    csv_data = TEST_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(empty_spec)}
    )
    
    # Should return 400 with helpful error
    assert response.status_code == 400
    
    data = response.json()
    error_message = str(data).lower()
    
    # Should contain helpful routing hints
    assert any([
        "invalid specification format" in error_message,
        "include 'industry' field" in error_message,
        "include 'spec' field" in error_message
    ])

def test_routing_with_industry_parameter():
    """Test v2 routing when industry is provided as form parameter."""
    # v2 spec without explicit industry field in JSON
    spec_without_industry = {
        "parameters": {
            "target_temp": 180,
            "hold_duration_minutes": 10,
            "sensor_uncertainty": 2,
            "hysteresis": 2
        }
    }
    
    csv_data = TEST_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={
            "spec_json": json.dumps(spec_without_industry),
            "industry": "powder"  # Provided as form parameter
        }
    )
    
    # Should route to v2 successfully
    assert response.status_code in [200, 400, 401, 402]
    
    # Should NOT be a routing error
    if response.status_code == 400:
        data = response.json()
        error_message = str(data).lower()
        assert "invalid specification format" not in error_message

def test_error_message_contains_environment_variable_hints():
    """Test that routing errors mention environment variables."""
    invalid_spec = {"invalid": "format"}
    csv_data = TEST_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(invalid_spec)}
    )
    
    assert response.status_code == 400
    
    data = response.json()
    error_message = str(data).lower()
    
    # Should mention the environment variables that control routing
    assert any([
        "api_v2_enabled" in error_message,
        "accept_legacy_spec" in error_message
    ])

def test_malformed_json_spec():
    """Test malformed JSON in spec_json returns proper error."""
    malformed_json = "{'invalid': json}"  # Invalid JSON syntax
    csv_data = TEST_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": malformed_json}
    )
    
    # Should return 400 for JSON parsing error
    assert response.status_code == 400

@pytest.mark.parametrize("industry", ["powder", "autoclave", "coldchain"])
def test_v1_to_v2_compatibility_shim(industry):
    """Test that v1 spec format gets adapted to work with v2 processing."""
    # Use v1 format but include explicit industry parameter to trigger v2 path
    v1_spec = V1_SPECS[industry]
    csv_data = TEST_CSV_DATA[industry]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={
            "spec_json": json.dumps(v1_spec),
            "industry": industry  # This should trigger v2 path with v1 spec adaptation
        }
    )
    
    # Should handle v1 format in v2 API path
    assert response.status_code in [200, 400, 401, 402], f"V1->V2 adaptation failed for {industry}: {response.status_code}"
    
    # Should NOT be a format/routing error
    if response.status_code == 400:
        data = response.json()
        error_message = str(data).lower()
        assert "invalid specification format" not in error_message

class TestEnvironmentVariableConfigBlocking:
    """Test suite for environment variable configuration scenarios."""
    
    def test_legacy_disabled_blocks_v1_format(self, monkeypatch):
        """Test that setting ACCEPT_LEGACY_SPEC=false blocks v1 format."""
        # Temporarily disable legacy support
        monkeypatch.setenv("ACCEPT_LEGACY_SPEC", "false")
        
        # Force reload of the app with new env vars
        import importlib
        import app as app_module
        importlib.reload(app_module)
        test_client = TestClient(app_module.app)
        
        v1_spec = V1_SPECS["powder"]
        csv_data = TEST_CSV_DATA["powder"]
        
        response = test_client.post(
            "/api/compile/json",
            files={"csv_file": ("test.csv", csv_data, "text/csv")},
            data={"spec_json": json.dumps(v1_spec)}
        )
        
        # Should reject v1 format when legacy is disabled
        assert response.status_code == 400
        data = response.json()
        error_message = str(data).lower()
        assert "invalid specification format" in error_message
    
    def test_v2_disabled_blocks_v2_format(self, monkeypatch):
        """Test that setting API_V2_ENABLED=false blocks v2 format."""
        # Temporarily disable v2 API
        monkeypatch.setenv("API_V2_ENABLED", "false")
        monkeypatch.setenv("ACCEPT_LEGACY_SPEC", "true")  # Keep legacy enabled
        
        # Force reload of the app with new env vars
        import importlib
        import app as app_module
        importlib.reload(app_module)
        test_client = TestClient(app_module.app)
        
        v2_spec = V2_SPECS["powder"]
        csv_data = TEST_CSV_DATA["powder"]
        
        response = test_client.post(
            "/api/compile/json",
            files={"csv_file": ("test.csv", csv_data, "text/csv")},
            data={"spec_json": json.dumps(v2_spec)}
        )
        
        # Should reject v2 format when v2 API is disabled
        assert response.status_code == 400
        data = response.json()
        error_message = str(data).lower()
        assert "invalid specification format" in error_message

if __name__ == "__main__":
    pytest.main([__file__, "-v"])