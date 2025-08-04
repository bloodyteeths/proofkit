"""
Structured JSON logging infrastructure for ProofKit.

This module provides standardized JSON logging with request tracking,
compatible with log aggregation services like CloudWatch, ELK, and DataDog.

Example usage:
    >>> from core.logging import get_logger, setup_logging
    >>> setup_logging()
    >>> logger = get_logger(__name__)
    >>> logger.info("Processing started", extra={"request_id": "abc123"})
"""

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Formats log records as JSON with consistent fields for log aggregation.
    Includes timestamp, level, message, and additional context fields.
    
    Example:
        >>> formatter = JSONFormatter()
        >>> handler = logging.StreamHandler()
        >>> handler.setFormatter(formatter)
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.
        
        Args:
            record: Python logging record to format
            
        Returns:
            JSON formatted log string
        """
        log_entry: Dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        
        # Add request context if available
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        
        if hasattr(record, 'path'):
            log_entry["path"] = record.path
            
        if hasattr(record, 'method'):
            log_entry["method"] = record.method
            
        if hasattr(record, 'status'):
            log_entry["status"] = record.status
            
        if hasattr(record, 'duration_ms'):
            log_entry["duration_ms"] = record.duration_ms
            
        if hasattr(record, 'client_ip'):
            log_entry["client_ip"] = record.client_ip
        
        # Add any extra fields from the log record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'lineno', 'funcName', 'created',
                          'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'getMessage', 'exc_info',
                          'exc_text', 'stack_info', 'request_id', 'path', 'method',
                          'status', 'duration_ms', 'client_ip']:
                log_entry[key] = value
        
        # Handle exception information
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic request/response logging.
    
    Logs all incoming requests with response status and timing.
    Generates unique request IDs for request correlation.
    
    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> app.add_middleware(RequestLoggingMiddleware)
    """
    
    def __init__(self, app, logger_name: str = "proofkit.requests"):
        """
        Initialize request logging middleware.
        
        Args:
            app: FastAPI application instance
            logger_name: Logger name for request logs
        """
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and log details with timing.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler
            
        Returns:
            HTTP response with logging context
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Store request ID in request state for access in handlers
        request.state.request_id = request_id
        
        # Get client IP (handle proxy headers)
        client_ip = self._get_client_ip(request)
        
        # Record start time
        start_time = time.time()
        
        # Log request start
        self.logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": client_ip,
                "user_agent": request.headers.get("user-agent", ""),
                "query_params": str(request.query_params) if request.query_params else None
            }
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log successful response
            self.logger.info(
                f"Request completed: {request.method} {request.url.path}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip
                }
            )
            
            # Add request ID to response headers for debugging
            response.headers["X-Request-ID"] = request_id
            
            return response
        
        except Exception as e:
            # Calculate duration for failed requests
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log request failure
            self.logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "error": str(e)
                },
                exc_info=True
            )
            
            # Re-raise the exception
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request headers.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Client IP address as string
        """
        # Check for forwarded headers (load balancer/proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fall back to direct client
        if request.client:
            return request.client.host
        
        return "unknown"


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    logger_name: Optional[str] = None
) -> None:
    """
    Configure application-wide logging with JSON formatting.
    
    Sets up structured logging compatible with log aggregation services.
    Configures both application and request logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Log format type ("json" or "text")
        logger_name: Specific logger to configure (None for root)
        
    Example:
        >>> setup_logging(level="DEBUG", format_type="json")
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatter
    if format_type.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Configure handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(numeric_level)
    
    # Configure logger
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    logger.addHandler(handler)
    logger.setLevel(numeric_level)
    
    # Prevent duplicate logs from propagating to parent loggers
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance for a specific module.
    
    Args:
        name: Logger name (typically __name__ from calling module)
        
    Returns:
        Configured logger instance
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Module initialized", extra={"module": "core.logging"})
    """
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    request: Optional[Request] = None,
    **kwargs
) -> None:
    """
    Log message with request context if available.
    
    Convenience function for adding request context to log messages.
    Extracts request ID and other context from FastAPI request object.
    
    Args:
        logger: Logger instance to use
        level: Log level (info, warning, error, etc.)
        message: Log message
        request: FastAPI request object for context
        **kwargs: Additional context fields
        
    Example:
        >>> logger = get_logger(__name__)
        >>> log_with_context(logger, "info", "Processing file", request=request, file_size=1024)
    """
    extra_fields = dict(kwargs)
    
    if request:
        # Extract request context
        if hasattr(request.state, 'request_id'):
            extra_fields['request_id'] = request.state.request_id
        
        extra_fields['path'] = request.url.path
        extra_fields['method'] = request.method
        
        if request.client:
            extra_fields['client_ip'] = request.client.host
    
    # Get logging method
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message, extra=extra_fields)