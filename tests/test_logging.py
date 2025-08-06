"""
ProofKit Logging Tests

Comprehensive test suite for structured JSON logging functionality including:
- Factory function for request loggers
- JSON formatting with structured output
- Request start/end logging with timing
- Error path logging with exception details
- Fixed request IDs for deterministic testing
- Stream capture for testing log output

Example usage:
    pytest tests/test_logging.py -v
"""

import json
import logging
import pytest
import time
import uuid
from datetime import datetime, timezone
from io import StringIO
from typing import Dict, Any
from unittest.mock import Mock, patch

from core.logging import (
    JSONFormatter,
    RequestLoggingMiddleware,
    get_request_logger,
    setup_logging,
    get_logger,
    log_with_context
)


class TestJSONFormatter:
    """Test JSON log formatting functionality."""
    
    def test_basic_formatting(self):
        """Test basic log record formatting as JSON."""
        formatter = JSONFormatter()
        
        # Create mock log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Format the record
        formatted = formatter.format(record)
        
        # Parse JSON to verify structure
        log_data = json.loads(formatted)
        
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["msg"] == "Test message"
        assert "time" in log_data
        
        # Verify timestamp format
        timestamp = datetime.fromisoformat(log_data["time"].replace("Z", "+00:00"))
        assert timestamp.tzinfo == timezone.utc
    
    def test_request_context_fields(self):
        """Test request context fields in log formatting."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Request processed",
            args=(),
            exc_info=None
        )
        
        # Add request context
        record.request_id = "test-123"
        record.path = "/api/compile"
        record.method = "POST"
        record.status = 200
        record.duration_ms = 150
        record.client_ip = "192.168.1.100"
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["request_id"] == "test-123"
        assert log_data["path"] == "/api/compile"
        assert log_data["method"] == "POST"
        assert log_data["status"] == 200
        assert log_data["duration_ms"] == 150
        assert log_data["client_ip"] == "192.168.1.100"
    
    def test_exception_formatting(self):
        """Test exception information in log formatting."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            import sys
            exc_info = sys.exc_info()
            
            record = logging.LogRecord(
                name="test.logger",
                level=logging.ERROR,
                pathname="/test/path.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=exc_info
            )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["level"] == "ERROR"
        assert log_data["msg"] == "Error occurred"
        assert "exception" in log_data
        assert "ValueError: Test exception" in log_data["exception"]
    
    def test_extra_fields(self):
        """Test additional fields in log records."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Custom data",
            args=(),
            exc_info=None
        )
        
        # Add custom fields
        record.file_size = 1024
        record.user_id = "user123"
        record.custom_field = "custom_value"
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["file_size"] == 1024
        assert log_data["user_id"] == "user123"
        assert log_data["custom_field"] == "custom_value"


class TestGetRequestLogger:
    """Test the request logger factory function."""
    
    def test_default_configuration(self):
        """Test logger creation with default parameters."""
        logger = get_request_logger()
        
        assert isinstance(logger, logging.Logger)
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
        assert isinstance(logger.handlers[0].formatter, JSONFormatter)
        assert logger.propagate is False
        assert hasattr(logger, '_request_id_provider')
    
    def test_custom_stream(self):
        """Test logger creation with custom StringIO stream."""
        buffer = StringIO()
        logger = get_request_logger(stream=buffer)
        
        # Log a message
        logger.info("Test message")
        
        # Check output captured in buffer
        output = buffer.getvalue()
        assert output.strip()  # Non-empty output
        
        # Parse JSON output
        log_data = json.loads(output.strip())
        assert log_data["level"] == "INFO"
        assert log_data["msg"] == "Test message"
        assert "time" in log_data
    
    def test_fixed_request_id_provider(self):
        """Test logger with fixed request ID provider for deterministic tests."""
        buffer = StringIO()
        fixed_id_provider = lambda: "fixed-test-id"
        
        logger = get_request_logger(
            stream=buffer,
            request_id_provider=fixed_id_provider
        )
        
        # Verify the provider is stored
        assert logger._request_id_provider() == "fixed-test-id"
        
        # Test logging with request context
        logger.info("Test request", extra={
            "request_id": logger._request_id_provider()
        })
        
        output = buffer.getvalue()
        log_data = json.loads(output.strip())
        assert log_data["request_id"] == "fixed-test-id"
    
    def test_unique_logger_names(self):
        """Test that different streams create unique logger instances."""
        buffer1 = StringIO()
        buffer2 = StringIO()
        
        logger1 = get_request_logger(stream=buffer1)
        logger2 = get_request_logger(stream=buffer2)
        
        # Should have different names to avoid conflicts
        assert logger1.name != logger2.name
        
        # Logging should go to separate streams
        logger1.info("Message 1")
        logger2.info("Message 2")
        
        assert "Message 1" in buffer1.getvalue()
        assert "Message 2" in buffer2.getvalue()
        assert "Message 1" not in buffer2.getvalue()
        assert "Message 2" not in buffer1.getvalue()
    
    def test_handler_cleanup(self):
        """Test that existing handlers are cleared when creating logger."""
        buffer = StringIO()
        
        # Create logger first time
        logger1 = get_request_logger(stream=buffer)
        initial_handler_count = len(logger1.handlers)
        
        # Create same logger again (same stream ID)
        logger2 = get_request_logger(stream=buffer)
        
        # Should have same number of handlers (cleaned up)
        assert len(logger2.handlers) == initial_handler_count


class TestRequestLoggingMiddleware:
    """Test request logging middleware functionality."""
    
    @pytest.fixture
    def mock_request(self):
        """Create mock FastAPI request for testing."""
        request = Mock()
        request.method = "GET"
        request.url.path = "/api/test"
        request.headers = {"user-agent": "test-agent"}
        request.query_params = {}
        request.client.host = "127.0.0.1"
        request.state = Mock()
        return request
    
    @pytest.fixture
    def mock_response(self):
        """Create mock FastAPI response for testing."""
        response = Mock()
        response.status_code = 200
        response.headers = {}
        return response
    
    def test_request_start_logging(self, mock_request):
        """Test logging of request start with proper context."""
        buffer = StringIO()
        
        # Create middleware with custom logger
        middleware = RequestLoggingMiddleware(None, logger_name="test.requests")
        
        # Replace logger with one that writes to our buffer
        test_logger = get_request_logger(stream=buffer)
        middleware.logger = test_logger
        
        # Mock call_next to return response
        async def mock_call_next(request):
            return Mock(status_code=200, headers={})
        
        # Run middleware dispatch
        import asyncio
        
        async def run_test():
            return await middleware.dispatch(mock_request, mock_call_next)
        
        asyncio.run(run_test())
        
        # Check log output
        output = buffer.getvalue()
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        
        # Should have at least 2 log entries (start and end)
        assert len(lines) >= 2
        
        # Parse first log entry (request start)
        start_log = json.loads(lines[0])
        assert start_log["msg"].startswith("Request started:")
        assert start_log["method"] == "GET"
        assert start_log["path"] == "/api/test"
        assert start_log["client_ip"] == "127.0.0.1"
        assert "request_id" in start_log
        
        # Parse last log entry (request completed)
        end_log = json.loads(lines[-1])
        assert end_log["msg"].startswith("Request completed:")
        assert end_log["status"] == 200
        assert "duration_ms" in end_log
        assert end_log["request_id"] == start_log["request_id"]
    
    def test_error_path_logging(self, mock_request):
        """Test logging when request processing fails."""
        buffer = StringIO()
        
        middleware = RequestLoggingMiddleware(None, logger_name="test.requests")
        test_logger = get_request_logger(stream=buffer)
        middleware.logger = test_logger
        
        # Mock call_next to raise exception
        async def mock_call_next_error(request):
            raise ValueError("Test error")
        
        import asyncio
        
        async def run_test():
            try:
                await middleware.dispatch(mock_request, mock_call_next_error)
            except ValueError:
                pass  # Expected
        
        asyncio.run(run_test())
        
        # Check error log output
        output = buffer.getvalue()
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        
        # Should have start and error logs
        assert len(lines) >= 2
        
        # Parse error log entry
        error_log = json.loads(lines[-1])
        assert error_log["level"] == "ERROR"
        assert error_log["msg"].startswith("Request failed:")
        assert error_log["status"] == 500
        assert error_log["error"] == "Test error"
        assert "duration_ms" in error_log
        assert "exception" in error_log
    
    def test_client_ip_extraction(self):
        """Test client IP extraction from various headers."""
        middleware = RequestLoggingMiddleware(None)
        
        # Test X-Forwarded-For header
        request1 = Mock()
        request1.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        request1.client = None
        
        ip1 = middleware._get_client_ip(request1)
        assert ip1 == "192.168.1.1"
        
        # Test X-Real-IP header
        request2 = Mock()
        request2.headers = {"X-Real-IP": "192.168.1.2"}
        request2.client = None
        
        ip2 = middleware._get_client_ip(request2)
        assert ip2 == "192.168.1.2"
        
        # Test direct client
        request3 = Mock()
        request3.headers = {}
        request3.client.host = "127.0.0.1"
        
        ip3 = middleware._get_client_ip(request3)
        assert ip3 == "127.0.0.1"
        
        # Test unknown case
        request4 = Mock()
        request4.headers = {}
        request4.client = None
        
        ip4 = middleware._get_client_ip(request4)
        assert ip4 == "unknown"


class TestUtilityFunctions:
    """Test utility logging functions."""
    
    def test_setup_logging_json_format(self):
        """Test setup_logging with JSON format."""
        buffer = StringIO()
        
        with patch('sys.stdout', buffer):
            setup_logging(level="DEBUG", format_type="json")
            
            logger = get_logger("test.setup")
            logger.info("Test message")
        
        output = buffer.getvalue()
        if output.strip():  # Only test if output was captured
            log_data = json.loads(output.strip())
            assert log_data["level"] == "INFO"
            assert log_data["msg"] == "Test message"
    
    def test_setup_logging_text_format(self):
        """Test setup_logging with text format."""
        setup_logging(level="INFO", format_type="text", logger_name="test.text")
        
        logger = get_logger("test.text")
        assert logger.level == logging.INFO
    
    def test_log_with_context_no_request(self):
        """Test log_with_context without request object."""
        buffer = StringIO()
        logger = get_request_logger(stream=buffer)
        
        log_with_context(
            logger,
            "info",
            "Processing file",
            file_size=1024,
            operation="normalize"
        )
        
        output = buffer.getvalue()
        log_data = json.loads(output.strip())
        
        assert log_data["msg"] == "Processing file"
        assert log_data["file_size"] == 1024
        assert log_data["operation"] == "normalize"
    
    def test_log_with_context_with_request(self):
        """Test log_with_context with request object."""
        buffer = StringIO()
        logger = get_request_logger(stream=buffer)
        
        # Mock request
        request = Mock()
        request.url.path = "/api/compile"
        request.method = "POST"
        request.state.request_id = "test-456"
        request.client.host = "192.168.1.50"
        
        log_with_context(
            logger,
            "info",
            "File processed",
            request=request,
            file_name="test.csv"
        )
        
        output = buffer.getvalue()
        log_data = json.loads(output.strip())
        
        assert log_data["msg"] == "File processed"
        assert log_data["request_id"] == "test-456"
        assert log_data["path"] == "/api/compile"
        assert log_data["method"] == "POST"
        assert log_data["client_ip"] == "192.168.1.50"
        assert log_data["file_name"] == "test.csv"


class TestIntegration:
    """Integration tests for logging functionality."""
    
    def test_full_request_lifecycle(self):
        """Test complete request logging lifecycle with JSON structure."""
        buffer = StringIO()
        
        # Create logger with fixed request ID for deterministic testing
        def fixed_id_provider():
            return "integration-test-123"
        
        logger = get_request_logger(
            stream=buffer,
            request_id_provider=fixed_id_provider
        )
        
        # Simulate request lifecycle
        request_id = logger._request_id_provider()
        
        # Request start
        logger.info("Request started: POST /api/compile", extra={
            "request_id": request_id,
            "method": "POST",
            "path": "/api/compile",
            "client_ip": "127.0.0.1",
            "user_agent": "pytest/1.0"
        })
        
        # Processing steps
        logger.info("File uploaded", extra={
            "request_id": request_id,
            "file_size": 2048,
            "file_type": "text/csv"
        })
        
        logger.info("Normalization complete", extra={
            "request_id": request_id,
            "rows_processed": 100,
            "processing_time_ms": 50
        })
        
        # Request complete
        logger.info("Request completed: POST /api/compile", extra={
            "request_id": request_id,
            "method": "POST",
            "path": "/api/compile",
            "status": 200,
            "duration_ms": 150
        })
        
        # Verify log output
        output = buffer.getvalue()
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        
        assert len(lines) == 4  # Four log entries
        
        # Verify all entries have consistent request ID
        for line in lines:
            log_data = json.loads(line)
            assert log_data["request_id"] == "integration-test-123"
            assert log_data["level"] == "INFO"
            assert "time" in log_data
        
        # Verify specific log content
        start_log = json.loads(lines[0])
        assert "Request started" in start_log["msg"]
        assert start_log["method"] == "POST"
        assert start_log["path"] == "/api/compile"
        
        file_log = json.loads(lines[1])
        assert file_log["file_size"] == 2048
        assert file_log["file_type"] == "text/csv"
        
        process_log = json.loads(lines[2])
        assert process_log["rows_processed"] == 100
        assert process_log["processing_time_ms"] == 50
        
        end_log = json.loads(lines[3])
        assert end_log["status"] == 200
        assert end_log["duration_ms"] == 150
    
    def test_json_output_structure_validation(self):
        """Test that all log output follows consistent JSON structure."""
        buffer = StringIO()
        logger = get_request_logger(stream=buffer)
        
        # Log various types of messages
        test_cases = [
            ("info", "Simple message", {}),
            ("warning", "Warning message", {"warning_code": "W001"}),
            ("error", "Error occurred", {"error_code": "E500", "details": "Something failed"}),
            ("debug", "Debug info", {"debug_data": {"nested": "value", "count": 42}})
        ]
        
        for level, message, extra in test_cases:
            log_method = getattr(logger, level)
            log_method(message, extra=extra)
        
        # Verify all outputs are valid JSON with required fields
        output = buffer.getvalue()
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        
        required_fields = ["time", "level", "logger", "msg"]
        
        for line in lines:
            log_data = json.loads(line)  # Will raise if invalid JSON
            
            # Check required fields
            for field in required_fields:
                assert field in log_data, f"Missing required field: {field}"
            
            # Verify timestamp format
            timestamp = datetime.fromisoformat(log_data["time"].replace("Z", "+00:00"))
            assert timestamp.tzinfo == timezone.utc
            
            # Verify level is uppercase
            assert log_data["level"] in ["INFO", "WARNING", "ERROR", "DEBUG"]
            
            # Verify logger name format
            assert log_data["logger"].startswith("proofkit.request.")