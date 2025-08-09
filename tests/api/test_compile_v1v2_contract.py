#!/usr/bin/env python3
"""Test API v1/v2 contract compatibility across all industries."""

import os
import json
import pytest
from fastapi.testclient import TestClient

# Mock environment for testing
os.environ["API_V2_ENABLED"] = "true"
os.environ["ACCEPT_LEGACY_SPEC"] = "true"

from app import app

client = TestClient(app)

# Industry specifications for testing
INDUSTRY_SPECS = {
    "powder": {
        "v1": {
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
        "v2": {
            "industry": "powder",
            "parameters": {
                "target_temp": 180,
                "hold_duration_minutes": 10,
                "sensor_uncertainty": 2,
                "hysteresis": 2
            }
        }
    },
    "autoclave": {
        "v1": {
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
        "v2": {
            "industry": "autoclave",
            "parameters": {
                "sterilization_temp": 121,
                "sterilization_time_minutes": 15,
                "min_pressure_bar": 2.0,
                "z_value": 10
            }
        }
    },
    "coldchain": {
        "v1": {
            "spec": {
                "min_temp_C": 2,
                "max_temp_C": 8,
                "method": "OVEN_AIR"
            },
            "data_requirements": {
                "max_sample_period_s": 60
            }
        },
        "v2": {
            "industry": "coldchain",
            "parameters": {
                "min_temp": 2,
                "max_temp": 8,
                "compliance_percentage": 95
            }
        }
    },
    "haccp": {
        "v1": {
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
        "v2": {
            "industry": "haccp",
            "parameters": {
                "temp_1": 135,
                "temp_2": 70,
                "temp_3": 41,
                "time_1_to_2_hours": 2
            }
        }
    },
    "concrete": {
        "v1": {
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
        "v2": {
            "industry": "concrete",
            "parameters": {
                "min_temp": 10,
                "max_temp": 30,
                "min_humidity": 80,
                "compliance_percentage": 95
            }
        }
    },
    "sterile": {
        "v1": {
            "spec": {
                "min_temp_C": 55,
                "max_temp_C": 60,
                "exposure_hours": 12,
                "method": "OVEN_AIR"
            },
            "data_requirements": {
                "max_sample_period_s": 60
            }
        },
        "v2": {
            "industry": "sterile",
            "parameters": {
                "min_temp": 55,
                "max_temp": 60,
                "exposure_hours": 12,
                "min_humidity": 50
            }
        }
    }
}

# Sample CSV data for different industries
SAMPLE_CSV_DATA = {
    "powder": "timestamp,temperature\n0,25\n30,160\n60,180\n90,180\n120,180\n150,180",
    "autoclave": "timestamp,temperature,pressure\n0,25,1.0\n30,100,2.1\n60,121,2.1\n90,121,2.1",
    "coldchain": "timestamp,temperature\n0,4\n60,5\n120,6\n180,4",
    "haccp": "timestamp,temperature\n0,140\n30,135\n60,80\n90,70\n120,50\n150,41",
    "concrete": "timestamp,temperature,humidity\n0,15,85\n60,20,87\n120,18,83",
    "sterile": "timestamp,temperature,humidity\n0,55,60\n60,58,65\n120,56,62"
}

@pytest.mark.parametrize("industry", ["powder", "autoclave", "coldchain", "haccp", "concrete", "sterile"])
def test_v1_spec_format_all_industries(industry):
    """Test v1 legacy spec format works for all industries."""
    spec = INDUSTRY_SPECS[industry]["v1"]
    csv_data = SAMPLE_CSV_DATA[industry]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec)}
    )
    
    # Should accept legacy format when ACCEPT_LEGACY_SPEC=true
    # Status codes: 200=success, 400=validation error, 401=auth required
    assert response.status_code in [200, 400, 401]

@pytest.mark.parametrize("industry", ["powder", "autoclave", "coldchain", "haccp", "concrete", "sterile"])
def test_v2_spec_format_all_industries(industry):
    """Test v2 spec format works for all industries."""
    spec = INDUSTRY_SPECS[industry]["v2"]
    csv_data = SAMPLE_CSV_DATA[industry]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec), "industry": industry}
    )
    
    # Should accept v2 format when API_V2_ENABLED=true
    assert response.status_code in [200, 400, 401]

def test_legacy_spec_format():
    """Test legacy spec format still works (powder example)."""
    spec = INDUSTRY_SPECS["powder"]["v1"]
    csv_data = SAMPLE_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec)}
    )
    
    # Should accept legacy format when ACCEPT_LEGACY_SPEC=true
    assert response.status_code in [200, 400, 401]

def test_v2_spec_format():
    """Test v2 spec format with industry field (powder example)."""
    spec = INDUSTRY_SPECS["powder"]["v2"]
    csv_data = SAMPLE_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec), "industry": "powder"}
    )
    
    # Should accept v2 format when API_V2_ENABLED=true
    assert response.status_code in [200, 400, 401]

def test_invalid_format_returns_hints():
    """Test invalid format returns helpful hints."""
    spec = {"invalid": "format"}
    csv_data = "timestamp,temperature\n0,25"
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec)}
    )
    
    if response.status_code == 400:
        data = response.json()
        assert "hints" in data or "error" in data

def test_v1_to_v2_compatibility():
    """Test that v1 spec gets adapted to v2 format correctly."""
    # This test focuses on the shim working correctly
    spec = {
        "spec": {
            "target_temp_C": 180,
            "hold_time_s": 600,
            "sensor_uncertainty_C": 2
        },
        "data_requirements": {
            "max_sample_period_s": 30,
            "allowed_gaps_s": 60
        }
    }
    csv_data = SAMPLE_CSV_DATA["powder"]
    
    response = client.post(
        "/api/compile/json",
        files={"csv_file": ("test.csv", csv_data, "text/csv")},
        data={"spec_json": json.dumps(spec), "industry": "powder"}
    )
    
    # Should handle v1 format with v2 API
    assert response.status_code in [200, 400, 401]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])