"""
Tests for M16 Documentation and OpenAPI features.

This module tests the documentation improvements and OpenAPI tag organization
implemented in M16.
"""

import pytest
import json
from app import app


class TestDocumentationM16:
    """Test documentation and OpenAPI features."""
    
    def setup_method(self):
        """Set up test environment."""
        # Get OpenAPI schema directly from the app
        self.schema = app.openapi()
    
    def test_openapi_schema_has_tags(self):
        """Test that OpenAPI schema includes all required tags."""
        tags = [tag["name"] for tag in self.schema.get("tags", [])]
        
        # Check for industry-specific tags
        required_tags = ["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"]
        for tag in required_tags:
            assert tag in tags, f"Missing required tag: {tag}"
        
        # Check for functional tags
        functional_tags = ["compile", "presets", "auth", "validation", "verify", "download", "health"]
        for tag in functional_tags:
            assert tag in tags, f"Missing functional tag: {tag}"
    
    def test_industry_endpoints_have_correct_tags(self):
        """Test that industry endpoints have the correct OpenAPI tags."""
        industry_endpoints = [
            ("/powder-coat", "powder"),
            ("/haccp", "haccp"),
            ("/autoclave", "autoclave"),
            ("/sterile", "sterile"),
            ("/concrete", "concrete"),
            ("/cold-chain", "coldchain"),
        ]
        
        for endpoint, expected_tag in industry_endpoints:
            # Find the endpoint in the schema
            found = False
            for path, methods in self.schema.get("paths", {}).items():
                if path == endpoint:
                    for method in methods.values():
                        if "tags" in method:
                            assert expected_tag in method["tags"], f"Endpoint {endpoint} missing tag {expected_tag}"
                            found = True
                            break
                    break
            assert found, f"Endpoint {endpoint} not found in OpenAPI schema"
    
    def test_api_endpoints_have_correct_tags(self):
        """Test that API endpoints have the correct OpenAPI tags."""
        api_endpoints = [
            ("/api/compile", "compile"),
            ("/api/compile/json", "compile"),
            ("/api/presets", "presets"),
            ("/api/presets/{industry}", "presets"),
            ("/auth/request-link", "auth"),
            ("/auth/verify", "auth"),
            ("/auth/logout", "auth"),
            ("/api/validation-pack/{job_id}", "validation"),
            ("/download/{job_id}/validation-pack", "validation"),
            ("/verify/{bundle_id}", "verify"),
            ("/download/{bundle_id}/{file_type}", "download"),
            ("/health", "health"),
        ]
        
        for endpoint, expected_tag in api_endpoints:
            # Find the endpoint in the schema
            found = False
            for path, methods in self.schema.get("paths", {}).items():
                if path == endpoint:
                    for method in methods.values():
                        if "tags" in method:
                            assert expected_tag in method["tags"], f"Endpoint {endpoint} missing tag {expected_tag}"
                            found = True
                            break
                    break
            assert found, f"Endpoint {endpoint} not found in OpenAPI schema"
    
    def test_openapi_schema_structure(self):
        """Test that OpenAPI schema has proper structure."""
        # Check required OpenAPI fields
        assert "openapi" in self.schema
        assert "info" in self.schema
        assert "paths" in self.schema
        
        # Check info structure
        info = self.schema["info"]
        assert "title" in info
        assert "version" in info
        assert info["title"] == "ProofKit"
        
        # Check paths structure
        paths = self.schema["paths"]
        assert isinstance(paths, dict)
        assert len(paths) > 0
    
    def test_tag_descriptions(self):
        """Test that tags have proper descriptions."""
        tags = self.schema.get("tags", [])
        tag_dict = {tag["name"]: tag for tag in tags}
        
        # Check that industry tags have descriptions
        industry_tags = ["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"]
        for tag_name in industry_tags:
            if tag_name in tag_dict:
                tag = tag_dict[tag_name]
                assert "description" in tag, f"Tag {tag_name} missing description"
                assert len(tag["description"]) > 0, f"Tag {tag_name} has empty description"
    
    def test_endpoint_descriptions(self):
        """Test that endpoints have proper descriptions."""
        # Check a few key endpoints have descriptions
        key_endpoints = [
            "/api/compile",
            "/api/compile/json",
            "/health",
            "/verify/{bundle_id}",
        ]
        
        for endpoint in key_endpoints:
            if endpoint in self.schema.get("paths", {}):
                path_item = self.schema["paths"][endpoint]
                for method, operation in path_item.items():
                    if method in ["get", "post", "put", "delete"]:
                        assert "summary" in operation, f"Endpoint {endpoint} {method} missing summary"
                        assert len(operation["summary"]) > 0, f"Endpoint {endpoint} {method} has empty summary"
    
    def test_openapi_schema_is_valid_json(self):
        """Test that OpenAPI schema can be serialized to valid JSON."""
        try:
            json_str = json.dumps(self.schema)
            parsed = json.loads(json_str)
            assert parsed == self.schema
        except (TypeError, ValueError) as e:
            pytest.fail(f"OpenAPI schema is not valid JSON: {e}")
    
    def test_all_endpoints_have_tags(self):
        """Test that all endpoints have at least one tag."""
        paths = self.schema.get("paths", {})
        
        for path, methods in paths.items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "delete"]:
                    assert "tags" in operation, f"Endpoint {path} {method} missing tags"
                    assert len(operation["tags"]) > 0, f"Endpoint {path} {method} has empty tags" 