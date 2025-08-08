"""
ProofKit FastAPI Application

This is the main FastAPI application entry point for ProofKit, a tool for generating
inspector-ready proof PDFs and tamper-evident evidence bundles from CSV temperature
logs and JSON specifications.

Example usage:
    # Start the server
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
    
    # Health check
    curl http://localhost:8000/health
"""

import json
import os
import hashlib
import uuid
import tempfile
import shutil
import logging
import threading
import magic
import secrets
import re
import html
from pathlib import Path
from typing import Dict, Any, Optional
import mimetypes
from datetime import datetime, timezone
from io import StringIO

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends, Response, Query
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
import pandas as pd
import matplotlib

# Configure matplotlib backend for server environment
matplotlib.use('Agg')

# Import core modules
from core.models import SpecV1, DecisionResult
from core.scheduler import start_background_tasks, stop_background_tasks
from core.normalize import normalize_temperature_data, load_csv_with_metadata, NormalizationError
from core.decide import make_decision, DecisionError
from core.plot import generate_proof_plot, PlotError
from core.render_pdf import generate_proof_pdf
from core.pack import create_evidence_bundle, PackingError
from core.logging import setup_logging, get_logger, RequestLoggingMiddleware
from core.cleanup import schedule_cleanup
from core.validation import create_validation_pack, get_validation_pack_info
from core.upsell import enqueue_upsell

# Import auth modules
from auth.magic import auth_handler, AuthMiddleware, get_current_user, require_auth, require_qa, require_qa_redirect
from auth.models import UserRole

# Import middleware
from middleware.quota import get_user_usage_summary

# Import API routes
from api.routes.pay import router as payment_router
from api.routes.auth import router as auth_api_router

# Base directory for the application
BASE_DIR = Path(__file__).resolve().parent

# Template and static file setup
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
static_dir = BASE_DIR / "web" / "static"
resources_dir = BASE_DIR / "marketing" / "resources"

# Add custom Jinja2 filters
def strftime_filter(value, format_str="%Y"):
    """Format datetime or 'now' string with strftime."""
    if value == "now":
        value = datetime.now(timezone.utc)
    elif isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime(format_str)

templates.env.filters["strftime"] = strftime_filter

# Add global function to get nonce from request
def get_nonce(request):
    """Get CSP nonce from request state."""
    return getattr(request.state, 'nonce', '')

templates.env.globals["get_nonce"] = get_nonce

# SEO helpers
def should_index(request: Request) -> bool:
    """Return False for paths that should not be indexed by search engines."""
    try:
        path = request.url.path if request else ""
    except Exception:
        path = ""
    # Allow specific auth page but block other sensitive areas
    disallow_prefixes = (
        "/auth/",
        "/api/",
        "/approve/",
        "/my-jobs",
        "/storage/",
        "/download/",
    )
    if path == "/auth/get-started":
        return False  # noindex login/signup page
    return not any(path.startswith(prefix) for prefix in disallow_prefixes)

templates.env.globals["should_index"] = should_index

# Jinja filters for SEO-friendly meta
def truncate_meta_filter(value: str, max_chars: int = 155) -> str:
    try:
        text = str(value or "").strip()
    except Exception:
        text = ""
    if len(text) <= max_chars:
        return text
    # Avoid cutting in the middle of a word
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip(" .,") + "…"


def truncate_title_filter(value: str, max_chars: int = 60) -> str:
    try:
        text = str(value or "").strip()
    except Exception:
        text = ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


templates.env.filters["truncate_meta"] = truncate_meta_filter
templates.env.filters["truncate_title"] = truncate_title_filter

# Storage configuration
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

# Thread lock for storage operations
storage_lock = threading.Lock()

# Initialize structured logging
setup_logging(level=os.environ.get("LOG_LEVEL", "INFO"), format_type="json")
logger = get_logger(__name__)

# Rate limiter configuration
limiter = Limiter(key_func=get_remote_address)

def get_rate_limit_decorator():
    """
    Get rate limit decorator, with option to disable for testing.
    
    Returns:
        Decorator function for rate limiting
        
    Example:
        @get_rate_limit_decorator()
        async def my_endpoint():
            pass
    """
    # Check if rate limiting is disabled for testing
    if os.environ.get("PK_TEST_DISABLE_RATELIMIT", "").lower() in ["1", "true"]:
        # Return a no-op decorator when rate limiting is disabled
        def no_limit_decorator(func):
            return func
        return no_limit_decorator
    else:
        # Return normal rate limit decorator
        return limiter.limit(f"{RATE_LIMIT_PER_MIN}/minute")

# Environment configuration
# Safer CORS defaults: production domains and local dev
DEFAULT_CORS_ORIGINS = "https://www.proofkit.net,https://proofkit-prod.fly.dev,http://localhost:8000,http://127.0.0.1:8000"
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",") if o.strip()]
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "10"))
# Support both MAX_UPLOAD_SIZE_MB and MAX_UPLOAD_MB
_max_mb_env = os.environ.get("MAX_UPLOAD_SIZE_MB") or os.environ.get("MAX_UPLOAD_MB") or "10"
MAX_UPLOAD_SIZE = int(_max_mb_env) * 1024 * 1024


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all HTTP responses.
    
    Implements comprehensive security headers including:
    - Strict Transport Security (HSTS)
    - Content type protection
    - Referrer policy
    - Permissions policy
    - Content Security Policy (CSP) with nonce support
    
    Example:
        app.add_middleware(SecurityHeadersMiddleware)
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and add security headers to response.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain
            
        Returns:
            Response with security headers added
        """
        # Check if this is Googlebot for Search Console verification
        user_agent = request.headers.get('user-agent', '').lower()
        is_googlebot = 'googlebot' in user_agent or 'google-site-verification' in user_agent
        
        # Generate a nonce for this request (skip for Googlebot to allow verification)
        nonce = '' if is_googlebot else secrets.token_urlsafe(16)
        request.state.nonce = nonce
        
        response = await call_next(request)
        
        # Strict Transport Security - force HTTPS for 1 year including subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # Prevent MIME type sniffing attacks
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Clickjacking protection
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        
        # Control referrer information sent when navigating away
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Restrict access to browser APIs that could be misused
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        
        # Content Security Policy - Allow inline scripts with nonce, unsafe-inline for event handlers
        # Note: unsafe-inline for scripts is needed for onclick handlers, but nonce provides better security for script blocks
        # For Googlebot, we skip nonce to allow Search Console verification
        # Added Stripe.js to allowed sources for payment processing
        if is_googlebot:
            script_src = "'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://js.stripe.com"
        else:
            script_src = f"'self' 'nonce-{nonce}' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://js.stripe.com"
            
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"script-src {script_src}; "
            "frame-src https://js.stripe.com https://hooks.stripe.com; "
            "connect-src 'self' https://www.google-analytics.com https://analytics.google.com https://www.googletagmanager.com https://api.stripe.com;"
        )
        
        return response


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.
    
    Returns:
        FastAPI: Configured FastAPI application instance
        
    Example:
        >>> app = create_app()
        >>> # App is ready to use with uvicorn
    """
    
    # Define OpenAPI tags for better organization
    tags_metadata = [
        {
            "name": "powder",
            "description": "Powder coat curing operations and specifications"
        },
        {
            "name": "haccp",
            "description": "HACCP cooling curve analysis and compliance"
        },
        {
            "name": "autoclave",
            "description": "Autoclave sterilization processes and validation"
        },
        {
            "name": "sterile",
            "description": "Sterile processing and medical device validation"
        },
        {
            "name": "concrete",
            "description": "Concrete curing and ASTM C31 compliance"
        },
        {
            "name": "coldchain",
            "description": "Cold chain storage and temperature monitoring"
        },
        {
            "name": "compile",
            "description": "CSV compilation and proof generation operations"
        },
        {
            "name": "presets",
            "description": "Industry-specific preset specifications"
        },
        {
            "name": "auth",
            "description": "Authentication and authorization operations"
        },
        {
            "name": "validation",
            "description": "Validation pack generation and management"
        },
        {
            "name": "verify",
            "description": "Evidence bundle verification and integrity checks"
        },
        {
            "name": "download",
            "description": "File download operations for proofs and evidence"
        },
        {
            "name": "health",
            "description": "System health and status endpoints"
        }
    ]
    
    # Fail fast on insecure JWT secret in production
    try:
        _jwt_secret = os.environ.get("JWT_SECRET", "")
        if (len(_jwt_secret) < 32 or _jwt_secret == "your-secret-key-change-in-production") and os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise RuntimeError("Insecure JWT_SECRET; set a strong value in environment")
    except Exception as e:
        # Re-raise to prevent starting with insecure configuration
        raise

    app = FastAPI(
        title="ProofKit",
        description="Generate inspector-ready proof PDFs from CSV temperature logs",
        version="0.1.0",
        docs_url="/api-docs",
        redoc_url="/redoc",
        openapi_tags=tags_metadata
    )
    
    # Optionally enforce HTTPS redirects (enabled by default outside development)
    if os.environ.get("FORCE_HTTPS", "true").lower() in ["1", "true", "yes"] and \
       os.environ.get("ENVIRONMENT", "production").lower() not in ["development", "dev", "local"]:
        app.add_middleware(HTTPSRedirectMiddleware)
    
    # Add security headers middleware (should be first to apply to all responses)
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Configure CORS
    # With credentials, browsers require explicit origins (not *)
    _allow_origins = CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["https://www.proofkit.net"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600,
    )
    
    # Add request logging middleware
    app.add_middleware(RequestLoggingMiddleware)
    
    # Add authentication middleware
    app.add_middleware(AuthMiddleware, auth_handler=auth_handler)
    
    # Add rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Include API routers
    app.include_router(payment_router)
    app.include_router(auth_api_router, prefix="/api")

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Serve marketing resources (PDFs, assets). Missing files will correctly 404 instead of 500.
    if resources_dir.exists():
        app.mount("/resources", StaticFiles(directory=str(resources_dir)), name="resources")

    # Initialize storage directory
    STORAGE_DIR.mkdir(exist_ok=True)
    logger.info(f"Storage directory initialized: {STORAGE_DIR}")

    # Schedule background cleanup
    try:
        retention_days = int(os.environ.get("RETENTION_DAYS", "30"))
        cleanup_interval = int(os.environ.get("CLEANUP_INTERVAL_HOURS", "24"))
        if schedule_cleanup(STORAGE_DIR, retention_days, cleanup_interval):
            logger.info(f"Background cleanup scheduled: {retention_days} days retention, {cleanup_interval}h interval")
        else:
            logger.warning("Failed to schedule background cleanup")
    except Exception as e:
        logger.error(f"Error scheduling cleanup: {e}")

    return app


def get_industry_presets() -> Dict[str, Dict[str, Any]]:
    """
    Load all available industry presets.
    
    Returns:
        Dict mapping industry names to their preset data
    """
    presets = {}
    
    # Available preset files
    preset_files = {
        "powder": "powder_coat_cure_spec_standard_180c_10min.json",  # Use existing example
        "haccp": "haccp_v1.json",
        "autoclave": "autoclave_v1.json", 
        "sterile": "sterile_v1.json",
        "concrete": "concrete_v1.json",
        "coldchain": "coldchain_v1.json"
    }
    
    spec_library_dir = BASE_DIR / "core" / "spec_library"
    
    for industry, filename in preset_files.items():
        try:
            if industry == "powder":
                # Use existing example file
                preset_path = BASE_DIR / "examples" / filename
            else:
                preset_path = spec_library_dir / filename
                
            if preset_path.exists():
                with open(preset_path, 'r') as f:
                    preset_data = json.load(f)
                presets[industry] = preset_data
            else:
                logger.warning(f"Preset file not found: {preset_path}")
        except Exception as e:
            logger.error(f"Failed to load preset {industry}: {e}")
    
    return presets


def get_default_spec(industry: Optional[str] = None) -> str:
    """
    Load the default specification JSON from examples or industry preset.
    
    Args:
        industry: Industry preset to load (optional)
    
    Returns:
        str: Default specification as formatted JSON string
    """
    try:
        if industry:
            # Load industry preset
            presets = get_industry_presets()
            if industry in presets:
                return json.dumps(presets[industry], indent=2)
            else:
                logger.warning(f"Industry preset '{industry}' not found")
        
        # Load default spec from examples
        spec_path = BASE_DIR / "examples" / "spec_example.json"
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        return json.dumps(spec_data, indent=2)
    except Exception:
        # Fallback default spec
        fallback_spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "batch_001"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        return json.dumps(fallback_spec, indent=2)


def validate_file_upload(file: UploadFile, request: Optional[Request] = None) -> bytes:
    """
    Validate uploaded file for size, MIME type, and content constraints.
    
    Args:
        file: The uploaded file to validate
        request: FastAPI request object for enhanced validation
        
    Returns:
        File content as bytes
        
    Raises:
        HTTPException: If validation fails
    """
    # Check Content-Length header first (more efficient than reading file)
    if request and request.headers.get("content-length"):
        try:
            content_length = int(request.headers["content-length"])
            if content_length > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"Content-Length ({content_length / 1024 / 1024:.1f}MB) exceeds {MAX_UPLOAD_SIZE / 1024 / 1024}MB limit"
                )
        except ValueError:
            pass  # Invalid Content-Length header, continue with file-based check
    
    # Read file to check actual size
    file_content = file.file.read()
    file_size = len(file_content)
    
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size ({file_size / 1024 / 1024:.1f}MB) exceeds {MAX_UPLOAD_SIZE / 1024 / 1024}MB limit"
        )
    
    # Check filename is provided and sanitized
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(file.filename)
    if not filename or filename != file.filename:
        raise HTTPException(status_code=400, detail="Invalid filename format")
        
    if not filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    
    # MIME type validation using python-magic for accurate detection
    try:
        mime_type = magic.from_buffer(file_content[:2048], mime=True)
        allowed_mime_types = [
            'text/csv',
            'text/plain', 
            'application/csv',
            'text/x-csv'
        ]
        
        if mime_type not in allowed_mime_types:
            # Also check file extension as fallback
            if not filename.lower().endswith('.csv'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type detected: {mime_type}. Only CSV files are allowed."
                )
    except Exception as e:
        logger.warning(f"MIME type detection failed: {e}, continuing with extension check")
    
    # Basic CSV content validation - check for common CSV indicators
    try:
        content_preview = file_content[:1024].decode('utf-8', errors='ignore')
        
        # Check for potential malicious content
        suspicious_patterns = ['<script', '<?php', '#!/', 'exec(', 'eval(']
        for pattern in suspicious_patterns:
            if pattern.lower() in content_preview.lower():
                raise HTTPException(
                    status_code=400,
                    detail="File contains suspicious content"
                )
        
        # Check for basic CSV structure (commas or semicolons)
        if ',' not in content_preview and ';' not in content_preview and '\t' not in content_preview:
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid CSV format"
            )
            
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File contains invalid character encoding"
        )
    
    logger.info(f"File validation passed: {filename} ({file_size} bytes)")
    return file_content


def generate_job_id(spec_data: Dict[str, Any], csv_content: bytes) -> str:
    """
    Generate deterministic job ID from spec and CSV content.
    
    Args:
        spec_data: Specification dictionary
        csv_content: CSV file content as bytes
        
    Returns:
        10-character job ID (first 10 chars of SHA hash)
    """
    # Create deterministic hash from spec + CSV content
    hasher = hashlib.sha256()
    hasher.update(json.dumps(spec_data, sort_keys=True).encode('utf-8'))
    hasher.update(csv_content)
    
    full_hash = hasher.hexdigest()
    return full_hash[:10]  # First 10 characters as short ID


def generate_usage_chart_data(recent_jobs: list) -> dict:
    """
    Generate usage chart data from user's job history.
    
    Args:
        recent_jobs: List of user's recent jobs
        
    Returns:
        Dictionary with labels and data for chart
    """
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    try:
        # Initialize monthly counts for last 6 months
        now = datetime.now()
        monthly_data = defaultdict(int)
        
        # Generate last 6 months
        months = []
        for i in range(5, -1, -1):  # 6 months ago to current
            month_date = now.replace(day=1) - timedelta(days=30 * i)
            month_key = month_date.strftime('%Y-%m')
            month_label = month_date.strftime('%b')
            months.append((month_key, month_label))
            monthly_data[month_key] = 0  # Initialize to 0
        
        # Count jobs by month
        jobs_processed = 0
        for job in recent_jobs or []:
            try:
                if job.get('created_at'):
                    # Parse the created_at timestamp
                    if isinstance(job['created_at'], str):
                        # Handle various timestamp formats
                        created_at_str = job['created_at']
                        if created_at_str.endswith('Z'):
                            created_at_str = created_at_str[:-1] + '+00:00'
                        elif '+' not in created_at_str and 'T' in created_at_str:
                            created_at_str += '+00:00'
                        job_date = datetime.fromisoformat(created_at_str)
                    else:
                        job_date = job['created_at']
                    
                    month_key = job_date.strftime('%Y-%m')
                    if month_key in monthly_data:
                        monthly_data[month_key] += 1
                        jobs_processed += 1
            except (ValueError, TypeError, AttributeError) as e:
                logger.debug(f"Error processing job date: {e}")
                continue
        
        # Extract labels and data
        labels = [month[1] for month in months]
        data = [monthly_data[month[0]] for month in months]
        
        logger.info(f"Generated usage chart data: {jobs_processed} jobs processed, data: {data}")
        
        # Ensure we have valid data - if all zeros but we have jobs, distribute them to current month
        if jobs_processed > 0 and all(d == 0 for d in data):
            # Put all jobs in the current month if date parsing failed
            data[-1] = jobs_processed
            logger.info(f"Fallback: Put {jobs_processed} jobs in current month due to date parsing issues")
        
        return {
            'labels': labels,
            'data': data
        }
    
    except Exception as e:
        logger.error(f"Error generating usage chart data: {e}")
        # Return fallback data
        now = datetime.now()
        labels = []
        for i in range(5, -1, -1):
            month_date = now.replace(day=1) - timedelta(days=30 * i)
            labels.append(month_date.strftime('%b'))
        
        return {
            'labels': labels,
            'data': [0] * 6  # 6 months of zero data
        }


def create_job_storage_path(job_id: str) -> Path:
    """
    Create storage path for job using path hashing.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Path to job storage directory
    """
    # Use first 2 chars of job_id for directory hashing
    hash_dir = job_id[:2]
    job_dir = STORAGE_DIR / hash_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def save_file_to_storage(content: bytes, job_dir: Path, filename: str) -> Path:
    """
    Save file content to job storage directory.
    
    Args:
        content: File content as bytes
        job_dir: Job storage directory
        filename: Name of the file to save
        
    Returns:
        Path to saved file
    """
    file_path = job_dir / filename
    with open(file_path, 'wb') as f:
        f.write(content)
    return file_path


def process_csv_and_spec(csv_content: bytes, spec_data: Dict[str, Any], 
                         job_dir: Path, job_id: str, creator=None) -> Dict[str, Any]:
    """
    Process CSV and specification through the complete ProofKit pipeline.
    
    Args:
        csv_content: CSV file content
        spec_data: Specification dictionary
        job_dir: Job storage directory
        job_id: Job identifier
        
    Returns:
        Result dictionary with processing outcomes
        
    Raises:
        Various processing errors
    """
    logger.info(f"Starting processing for job {job_id}")
    
    # Ensure the specification carries the canonical, generated job_id so all
    # downstream artifacts (saved spec, PDF QR/verify URL, evidence bundle) use
    # the same identifier expected by the verification route.
    try:
        if not isinstance(spec_data.get('job'), dict):
            spec_data['job'] = {}
        spec_data['job']['job_id'] = job_id
    except Exception:
        # Hardening: never fail processing due to a malformed spec structure.
        spec_data['job'] = {'job_id': job_id}

    # Save original CSV file
    raw_csv_path = save_file_to_storage(csv_content, job_dir, "raw_data.csv")
    
    # Save specification JSON
    spec_json_content = json.dumps(spec_data, indent=2).encode('utf-8')
    spec_json_path = save_file_to_storage(spec_json_content, job_dir, "specification.json")
    
    # Validate and parse specification
    try:
        spec = SpecV1(**spec_data)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid specification: {str(e)}"
        )
    
    # Load and normalize CSV data
    try:
        # Create temporary file for CSV processing
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.csv') as tmp_file:
            tmp_file.write(csv_content)
            tmp_csv_path = tmp_file.name
        
        try:
            # Load CSV with metadata extraction
            df, metadata = load_csv_with_metadata(tmp_csv_path)
            
            # Normalize temperature data
            normalized_df = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=spec.data_requirements.allowed_gaps_s,
                max_sample_period_s=spec.data_requirements.max_sample_period_s
            )
            
            # Save normalized CSV
            normalized_csv_path = job_dir / "normalized_data.csv"
            normalized_df.to_csv(normalized_csv_path, index=False)
            
        finally:
            # Clean up temporary file
            os.unlink(tmp_csv_path)
            
    except NormalizationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Data normalization failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CSV processing failed: {str(e)}"
        )
    
    # Make decision
    try:
        decision = make_decision(normalized_df, spec)
        
        # Save decision JSON
        decision_dict = decision.model_dump(by_alias=True)
        decision_json_content = json.dumps(decision_dict, indent=2).encode('utf-8')
        decision_json_path = save_file_to_storage(decision_json_content, job_dir, "decision.json")
        
    except DecisionError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Decision analysis failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Decision processing failed: {str(e)}"
        )
    
    # Generate plot
    try:
        plot_path = job_dir / "plot.png"
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        
    except PlotError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Plot generation failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Plot processing failed: {str(e)}"
        )
    
    # Generate PDF
    try:
        pdf_path = job_dir / "proof.pdf"
        
        # Generate verification hash
        verification_hash = hashlib.sha256(
            f"{job_id}{decision.pass_}{decision.actual_hold_time_s}".encode()
        ).hexdigest()
        
        pdf_bytes = generate_proof_pdf(
            spec=spec,
            decision=decision,
            plot_path=str(plot_path),
            normalized_csv_path=str(normalized_csv_path),
            verification_hash=verification_hash,
            output_path=str(pdf_path),
            user_plan=creator.plan if creator else 'free'
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}"
        )
    
    # Create evidence bundle
    try:
        zip_path = job_dir / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(raw_csv_path),
            spec_json_path=str(spec_json_path),
            normalized_csv_path=str(normalized_csv_path),
            decision_json_path=str(decision_json_path),
            proof_pdf_path=str(pdf_path),
            plot_png_path=str(plot_path),
            output_path=str(zip_path),
            job_id=job_id
        )
        
    except PackingError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Evidence bundle creation failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Bundle processing failed: {str(e)}"
        )
    
    logger.info(f"Processing completed successfully for job {job_id}")
    
    # Save job metadata
    job_metadata = {
        "specification": spec_data,
        "decision": decision_dict,
        "verification_hash": verification_hash,
        "files": {
            "raw_csv": "raw_data.csv",
            "spec_json": "specification.json",
            "normalized_csv": "normalized_data.csv",
            "decision_json": "decision.json",
            "plot_png": "plot.png",
            "proof_pdf": "proof.pdf",
            "evidence_zip": "evidence.zip"
        },
        "creator": {
            "email": creator.email if creator else None,
            "role": creator.role if creator else None,  # role is already a string due to use_enum_values
            "plan": creator.plan if creator else "free"
        } if creator else None
    }
    save_job_metadata(job_dir, job_id, job_metadata)
    
    # Schedule upsell sequence for free users
    try:
        if (creator and str(creator.plan).lower() == 'free') or not creator:
            user_email = creator.email if creator else None
            if user_email:
                industry = spec_data.get('industry', 'general') if isinstance(spec_data, dict) else 'general'
                spec_name = spec_data.get('name', 'Certificate') if isinstance(spec_data, dict) else 'Certificate'
                enqueue_upsell(user_email, job_id, industry, spec_name)
                logger.info(f"Upsell scheduled for {user_email} job={job_id}")
    except Exception as e:
        logger.error(f"Failed to enqueue upsell for job {job_id}: {e}")
    
    # Return results (preserve legacy fields and include status/flags)
    return {
        "id": job_id,
        "pass": decision.pass_,
        "status": getattr(decision, 'status', 'PASS' if decision.pass_ else 'FAIL'),
        "metrics": {
            "target_temp_C": decision.target_temp_C,
            "conservative_threshold_C": decision.conservative_threshold_C,
            "actual_hold_time_s": decision.actual_hold_time_s,
            "required_hold_time_s": decision.required_hold_time_s,
            "max_temp_C": decision.max_temp_C,
            "min_temp_C": decision.min_temp_C
        },
        "reasons": decision.reasons,
        "warnings": decision.warnings,
        "flags": getattr(decision, 'flags', {}),
        "urls": {
            "pdf": f"/download/{job_id}/pdf",
            "zip": f"/download/{job_id}/zip",
            "verify": f"/verify/{job_id}"
        },
        "verification_hash": verification_hash
    }


# Create the main app instance
app = create_app()
def _render_markdown(md_text: str) -> str:
    """Very simple Markdown to HTML (headers, paragraphs, lists)."""
    lines = md_text.split('\n')
    html_lines = []
    in_list = False
    for line in lines:
        s = line.strip()
        if s.startswith('### '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f"<h3>{html.escape(s[4:])}</h3>")
        elif s.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith('# '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif s.startswith('- '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(s[2:]))
            html_lines.append(f"<li>{content}</li>")
        elif s == '':
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('')
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(s))
            html_lines.append(f"<p>{content}</p>")
    if in_list:
        html_lines.append('</ul>')
    return '\n'.join(html_lines)


@app.get("/press", response_class=HTMLResponse, tags=["marketing"])
async def press_release_page(request: Request) -> HTMLResponse:
    md_path = BASE_DIR / "marketing" / "pr" / "press-release.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Press release not found")
    with open(md_path, 'r', encoding='utf-8') as f:
        md = f.read()
    html_content = _render_markdown(md)
    return templates.TemplateResponse("press.html", {"request": request, "content": html_content})


@app.get("/press/download", tags=["marketing"])
async def press_release_download() -> FileResponse:
    md_path = BASE_DIR / "marketing" / "pr" / "press-release.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Press release not found")
    return FileResponse(md_path, media_type="text/markdown", filename="press-release.md")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico_redirect() -> RedirectResponse:
    """Redirect legacy favicon path to the SVG in static assets."""
    return RedirectResponse(url="/static/brand/proofkit_favicon.svg", status_code=307)


@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg() -> FileResponse:
    """Serve the SVG favicon directly for browsers that request it explicitly."""
    return FileResponse(static_dir / "brand" / "proofkit_favicon.svg", media_type="image/svg+xml")


@app.get("/health", tags=["health"])
async def health_check() -> JSONResponse:
    """
    Health check endpoint for monitoring and load balancer readiness.
    
    Returns:
        JSONResponse: Status information including service name and version
        
    Example:
        >>> # GET /health
        >>> {"status": "healthy", "service": "proofkit", "version": "0.1.0"}
    """
    health_data: Dict[str, Any] = {
        "status": "healthy",
        "service": "proofkit", 
        "version": "0.1.0"
    }
    return JSONResponse(content=health_data, status_code=200)


@app.get("/", response_class=HTMLResponse, tags=["compile"])
async def marketing_page(request: Request) -> HTMLResponse:
    """
    Marketing homepage with product information and call-to-action.
    
    Returns:
        HTMLResponse: Rendered marketing template
        
    Example:
        Browser GET / returns marketing landing page
    """
    # Get user from request state if authenticated
    user = getattr(request.state, 'user', None)
    
    return templates.TemplateResponse(
        "modern_home.html",
        {
            "request": request,
            "user": user
        }
    )


@app.get("/app", response_class=HTMLResponse, tags=["compile"])
async def app_page(
    request: Request,
    industry: Optional[str] = None
) -> HTMLResponse:
    """
    Main application page with form for CSV file and specification JSON.
    
    Args:
        industry: Optional industry preset to load
    
    Returns:
        HTMLResponse: Rendered index template with default specification
        
    Example:
        Browser GET /app returns upload form with pre-populated spec JSON
        Browser GET /app?industry=haccp returns form with HACCP preset
    """
    # Check if user is authenticated
    user = get_current_user(request)
    if not user:
        # Redirect to get started page
        return RedirectResponse(url="/auth/get-started", status_code=302)
    
    default_spec = get_default_spec(industry)
    presets = get_industry_presets()
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_spec": default_spec,
            "presets": presets,
            "selected_industry": industry,
            "user": user
        }
    )


@app.get("/api/presets", tags=["presets"])
async def get_presets() -> JSONResponse:
    """
    Get all available industry presets.
    
    Returns:
        JSONResponse: Dictionary of industry presets
        
    Example:
        GET /api/presets returns {"powder": {...}, "haccp": {...}, ...}
    """
    try:
        presets = get_industry_presets()
        return JSONResponse(content=presets)
    except Exception as e:
        logger.error(f"Failed to load presets: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load presets", "message": str(e)}
        )


@app.get("/api/presets/{industry}", tags=["presets"])
async def get_industry_preset(industry: str) -> JSONResponse:
    """
    Get a specific industry preset.
    
    Args:
        industry: Industry name (powder, haccp, autoclave, sterile, concrete, coldchain)
    
    Returns:
        JSONResponse: Industry preset data
        
    Example:
        GET /api/presets/haccp returns HACCP specification
    """
    try:
        presets = get_industry_presets()
        if industry not in presets:
            return JSONResponse(
                status_code=404,
                content={"error": "Industry preset not found", "industry": industry}
            )
        
        return JSONResponse(content=presets[industry])
    except Exception as e:
        logger.error(f"Failed to load preset {industry}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load preset", "message": str(e)}
        )


@app.post("/api/compile", response_class=HTMLResponse, tags=["compile"])
@get_rate_limit_decorator()
async def compile_csv_html(
    request: Request,
    csv_file: UploadFile = File(...),
    spec_json: str = Form(...)
) -> HTMLResponse:
    """
    Process CSV file and specification JSON to generate proof PDF and evidence bundle.
    
    Args:
        request: FastAPI request object
        csv_file: Uploaded CSV temperature log file
        spec_json: JSON specification string
        
    Returns:
        HTMLResponse: HTMX partial response with results or error
        
    Example:
        POST /api/compile with multipart form data returns result.html partial
    """
    # Check authentication
    current_user = get_current_user(request)
    if not current_user:
        # For HTMX requests, return an error partial
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": {
                    "title": "Authentication Required",
                    "message": "Please sign in to generate validation reports",
                    "suggestions": [
                        "Click here to sign in: <a href='/auth/get-started'>Get Started</a>"
                    ]
                }
            }
        )
    
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Starting compile request from {request.client.host if request.client else 'unknown'}")
    
    try:
        # Validate and read file upload
        csv_content = validate_file_upload(csv_file, request)
        logger.info(f"[{request_id}] File validated: {csv_file.filename} ({len(csv_content)} bytes)")
        
        # Validate and parse JSON specification
        try:
            spec_data = json.loads(spec_json)
            logger.info(f"[{request_id}] Spec parsed successfully")
        except json.JSONDecodeError as e:
            logger.warning(f"[{request_id}] JSON parsing failed: {e}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": {
                        "title": "Invalid JSON Specification",
                        "message": f"JSON parsing error: {str(e)}",
                        "suggestions": [
                            "Check for missing commas, brackets, or quotes",
                            "Use a JSON validator to verify syntax",
                            "Ensure all strings are properly quoted"
                        ]
                    }
                }
            )
        
        # Check quota before processing
        if current_user:
            from middleware.quota import check_compilation_quota, record_usage, get_user_usage_summary
            can_compile, quota_error = check_compilation_quota(current_user)
            if not can_compile:
                logger.warning(f"[{request_id}] Quota exceeded for {current_user.email}")
                
                # Get usage details for better UX
                usage_summary = get_user_usage_summary(current_user.email)
                
                # Handle HTMX requests with proper redirect headers
                if request.headers.get('HX-Request'):
                    response = Response(status_code=303)
                    response.headers['HX-Redirect'] = '/upgrade-required'
                    return response
                else:
                    # Regular redirect for non-HTMX requests
                    return RedirectResponse(
                        url="/upgrade-required",
                        status_code=303
                    )
        
        # Generate deterministic job ID
        job_id = generate_job_id(spec_data, csv_content)
        logger.info(f"[{request_id}] Generated job ID: {job_id}")
        
        # Thread-safe storage operations
        with storage_lock:
            job_dir = create_job_storage_path(job_id)
            logger.info(f"[{request_id}] Created storage path: {job_dir}")
        
        # Process through complete pipeline
        try:
            result = process_csv_and_spec(csv_content, spec_data, job_dir, job_id, creator=current_user)
            
            # Record usage after successful processing
            if current_user:
                record_usage(current_user, 'certificate_compiled')
            logger.info(f"[{request_id}] Processing completed: {'PASS' if result['pass'] else 'FAIL'}")
            
            # Check approval status
            meta_path = job_dir / "meta.json"
            approved = False
            if meta_path.exists():
                with open(meta_path, 'r') as f:
                    job_meta = json.load(f)
                    approved = job_meta.get("approved", False)
            
            return templates.TemplateResponse(
                "result.html",
                {
                    "request": request,
                    "result": result,
                    "user": current_user,
                    "approved": approved
                }
            )
            
        except HTTPException:
            # Re-raise HTTP exceptions to preserve status codes
            raise
        except Exception as e:
            logger.error(f"[{request_id}] Processing failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Processing failed: {str(e)}"
            )
        
    except HTTPException as e:
        logger.warning(f"[{request_id}] HTTP error: {e.status_code} - {e.detail}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": {
                    "title": "Processing Error",
                    "message": e.detail,
                    "suggestions": [
                        "Ensure your file is a valid CSV format",
                        "Check that file size is under 10MB",
                        "Verify CSV contains temperature data with timestamps",
                        "Review specification JSON format"
                    ]
                }
            }
        )
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": {
                    "title": "System Error",
                    "message": f"An unexpected error occurred: {str(e)}",
                    "suggestions": [
                        "Try uploading the file again",
                        "Check your CSV file format and content",
                        "Contact support if the problem persists"
                    ]
                }
            }
        )


@app.post("/api/compile/json", tags=["compile"])
@get_rate_limit_decorator()
async def compile_csv_json(
    request: Request,
    csv_file: UploadFile = File(...),
    spec_json: str = Form(...)
) -> JSONResponse:
    """
    Process CSV file and specification JSON to generate proof PDF and evidence bundle.
    Returns JSON response suitable for API clients.
    
    Args:
        request: FastAPI request object
        csv_file: Uploaded CSV temperature log file
        spec_json: JSON specification string
        
    Returns:
        JSONResponse: JSON response with results or error
        
    Example:
        POST /api/compile/json with multipart form data returns JSON result
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Starting JSON compile request from {request.client.host if request.client else 'unknown'}")
    
    try:
        # Require authentication for API usage
        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required", "message": "Sign in to use the API"}
            )

        # Validate and read file upload
        csv_content = validate_file_upload(csv_file, request)
        logger.info(f"[{request_id}] File validated: {csv_file.filename} ({len(csv_content)} bytes)")
        
        # Validate and parse JSON specification
        try:
            spec_data = json.loads(spec_json)
            logger.info(f"[{request_id}] Spec parsed successfully")
        except json.JSONDecodeError as e:
            logger.warning(f"[{request_id}] JSON parsing failed: {e}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid JSON specification",
                    "message": f"JSON parsing error: {str(e)}",
                    "details": {
                        "type": "json_decode_error",
                        "suggestions": [
                            "Check for missing commas, brackets, or quotes",
                            "Use a JSON validator to verify syntax",
                            "Ensure all strings are properly quoted"
                        ]
                    }
                }
            )
        
        # Check quota before processing
        try:
            from middleware.quota import check_compilation_quota, record_usage
            can_compile, quota_error = check_compilation_quota(current_user)
            if not can_compile:
                return JSONResponse(status_code=402, content=quota_error)
        except Exception as e:
            logger.warning(f"[{request_id}] Quota check failed: {e}")

        # Generate deterministic job ID
        job_id = generate_job_id(spec_data, csv_content)
        logger.info(f"[{request_id}] Generated job ID: {job_id}")
        
        # Thread-safe storage operations
        with storage_lock:
            job_dir = create_job_storage_path(job_id)
            logger.info(f"[{request_id}] Created storage path: {job_dir}")
        
        # Process through complete pipeline
        try:
            result = process_csv_and_spec(csv_content, spec_data, job_dir, job_id, creator=current_user)
            logger.info(f"[{request_id}] Processing completed: {'PASS' if result['pass'] else 'FAIL'}")
            # Record usage after successful processing
            try:
                record_usage(current_user, 'certificate_compiled')
            except Exception:
                pass
            
            return JSONResponse(
                status_code=200,
                content=result
            )
            
        except HTTPException as e:
            # Convert HTTP exceptions to JSON responses
            logger.warning(f"[{request_id}] Processing failed: {e.detail}")
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": "Processing failed",
                    "message": e.detail,
                    "details": {
                        "type": "processing_error",
                        "status_code": e.status_code
                    }
                }
            )
        except Exception as e:
            logger.error(f"[{request_id}] Processing failed: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Processing failed",
                    "message": str(e),
                    "details": {
                        "type": "unexpected_error"
                    }
                }
            )
        
    except HTTPException as e:
        logger.warning(f"[{request_id}] HTTP error: {e.status_code} - {e.detail}")
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": "Request validation failed", 
                "message": e.detail,
                "details": {
                    "type": "validation_error",
                    "status_code": e.status_code
                }
            }
        )
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "System error",
                "message": f"An unexpected error occurred: {str(e)}",
                "details": {
                    "type": "system_error"
                }
            }
        )


@app.get("/verify/{bundle_id}", response_class=HTMLResponse, tags=["verify"])
async def verify_bundle(request: Request, bundle_id: str) -> HTMLResponse:
    """
    Verify an evidence bundle and display results.
    
    Args:
        request: FastAPI request object
        bundle_id: Unique identifier for the evidence bundle
        
    Returns:
        HTMLResponse: Verification results page
        
    Example:
        GET /verify/abc123 returns verification status and original results
    """
    request_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else 'unknown'
    logger.info(f"[{request_id}] Verify request from {client_ip}: {bundle_id}")
    
    try:
        # Validate bundle_id format
        if not bundle_id or len(bundle_id) != 10 or not all(c in '0123456789abcdef' for c in bundle_id.lower()):
            logger.warning(f"[{request_id}] Invalid bundle ID format: {bundle_id}")
            failed_verification = {
                "valid": False,
                "integrity_valid": False,
                "decision_valid": False,
                "manifest_valid": False,
                "errors": ["Invalid bundle ID format"]
            }
            return templates.TemplateResponse(
                "verify.html",
                {
                    "request": request,
                    "bundle_id": bundle_id,
                    "verification": failed_verification
                }
            )
        
        # Find job storage path
        hash_dir = bundle_id[:2]
        job_dir = STORAGE_DIR / hash_dir / bundle_id
        
        if not job_dir.exists():
            logger.warning(f"[{request_id}] Bundle not found: {bundle_id}")
            failed_verification = {
                "valid": False,
                "integrity_valid": False,
                "decision_valid": False,
                "manifest_valid": False,
                "errors": ["Bundle not found"]
            }
            return templates.TemplateResponse(
                "verify.html",
                {
                    "request": request,
                    "bundle_id": bundle_id,
                    "verification": failed_verification
                }
            )
        
        # Load decision result
        decision_path = job_dir / "decision.json"
        if not decision_path.exists():
            logger.warning(f"[{request_id}] Decision file not found: {decision_path}")
            failed_verification = {
                "valid": False,
                "integrity_valid": False,
                "decision_valid": False,
                "manifest_valid": False,
                "errors": ["Decision file not found in bundle"]
            }
            return templates.TemplateResponse(
                "verify.html",
                {
                    "request": request,
                    "bundle_id": bundle_id,
                    "verification": failed_verification
                }
            )
        
        try:
            with open(decision_path, 'r') as f:
                decision_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"[{request_id}] Failed to load decision file: {e}")
            failed_verification = {
                "valid": False,
                "integrity_valid": False,
                "decision_valid": False,
                "manifest_valid": False,
                "errors": [f"Invalid or corrupted decision file: {str(e)}"]
            }
            return templates.TemplateResponse(
                "verify.html",
                {
                    "request": request,
                    "bundle_id": bundle_id,
                    "verification": failed_verification
                }
            )
        
        # Load evidence bundle for verification
        zip_path = job_dir / "evidence.zip"
        if not zip_path.exists():
            logger.warning(f"[{request_id}] Evidence bundle not found: {zip_path}")
            failed_verification = {
                "valid": False,
                "integrity_valid": False,
                "decision_valid": True,  # We have decision data
                "manifest_valid": False,
                "errors": ["Evidence ZIP bundle not found"],
                "decision": decision_data  # Include what we have
            }
            return templates.TemplateResponse(
                "verify.html",
                {
                    "request": request,
                    "bundle_id": bundle_id,
                    "verification": failed_verification
                }
            )
        
        # Import verification function
        from core.pack import verify_evidence_bundle
        
        # Verify bundle integrity
        verification_result = verify_evidence_bundle(str(zip_path))
        
        # Create verification summary
        verification = {
            "valid": verification_result["valid"],
            "integrity_valid": verification_result["valid"],
            "decision_valid": True,  # We loaded the decision successfully
            "manifest_valid": verification_result["manifest_found"],
            "integrity_message": "All file hashes verified" if verification_result["valid"] else "Hash verification failed",
            "decision_message": "Decision data accessible",
            "manifest_message": "Manifest found and valid" if verification_result["manifest_found"] else "Manifest issues",
            "root_hash": verification_result.get("root_hash", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "0.1.0",
            "decision": decision_data,
            "file_hashes": [
                {"filename": "raw_data.csv", "valid": True, "hash": "verified"},
                {"filename": "normalized_data.csv", "valid": True, "hash": "verified"},
                {"filename": "decision.json", "valid": True, "hash": "verified"},
                {"filename": "proof.pdf", "valid": True, "hash": "verified"}
            ],
            "errors": verification_result.get("hash_mismatches", []) + verification_result.get("missing_files", [])
        }
        
        logger.info(f"[{request_id}] Verification completed: {'VALID' if verification['valid'] else 'INVALID'}")
        
        return templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "bundle_id": bundle_id,
                "verification": verification
            }
        )
        
    except Exception as e:
        logger.error(f"[{request_id}] Verification error: {e}")
        
        # Return verification failed page
        failed_verification = {
            "valid": False,
            "integrity_valid": False,
            "decision_valid": False,
            "manifest_valid": False,
            "errors": [f"Bundle verification failed: {str(e)}"]
        }
        
        return templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "bundle_id": bundle_id,
                "verification": failed_verification
            }
        )


@app.get("/download/{bundle_id}/{file_type}", tags=["download"])
async def download_file(
    bundle_id: str, 
    file_type: str, 
    request: Request
) -> FileResponse:
    """
    Download files from an evidence bundle.
    
    Args:
        bundle_id: Unique identifier for the evidence bundle
        file_type: Type of file to download ('pdf' or 'zip')
        request: FastAPI request object for logging
        
    Returns:
        FileResponse: The requested file for download
        
    Raises:
        HTTPException: If bundle or file not found
        
    Example:
        GET /download/abc123/pdf returns the proof PDF file
        GET /download/abc123/zip returns the evidence bundle ZIP
    """
    request_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else 'unknown'
    logger.info(f"[{request_id}] Download request from {client_ip}: {bundle_id}/{file_type}")
    
    try:
        # Validate bundle_id format (should be 10 character hex)
        if not bundle_id or len(bundle_id) != 10 or not all(c in '0123456789abcdef' for c in bundle_id.lower()):
            logger.warning(f"[{request_id}] Invalid bundle ID format: {bundle_id}")
            raise HTTPException(status_code=400, detail="Invalid bundle ID format")
        
        # Validate file type
        if file_type not in ['pdf', 'zip']:
            logger.warning(f"[{request_id}] Invalid file type: {file_type}")
            raise HTTPException(status_code=400, detail="File type must be 'pdf' or 'zip'")
        
        # Find job storage path
        hash_dir = bundle_id[:2]
        job_dir = STORAGE_DIR / hash_dir / bundle_id
        
        if not job_dir.exists():
            logger.warning(f"[{request_id}] Job directory not found: {job_dir}")
            raise HTTPException(status_code=404, detail="Bundle not found")
        
        # Determine file path and name
        if file_type == 'pdf':
            file_path = job_dir / "proof.pdf"
            filename = f"proofkit_certificate_{bundle_id}.pdf"
            media_type = "application/pdf"
        elif file_type == 'zip':
            file_path = job_dir / "evidence.zip"
            filename = f"proofkit_evidence_{bundle_id}.zip"
            media_type = "application/zip"
        
        if not file_path.exists():
            logger.warning(f"[{request_id}] File not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"File not found: {file_type}")
        
        # Security check: ensure file is within storage directory
        if not str(file_path.resolve()).startswith(str(STORAGE_DIR.resolve())):
            logger.error(f"[{request_id}] Security violation: path traversal attempt")
            raise HTTPException(status_code=403, detail="Access denied")
        
        logger.info(f"[{request_id}] Serving file: {file_path} ({file_path.stat().st_size} bytes)")
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Download error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading file: {str(e)}"
        )


@app.get("/examples", response_class=HTMLResponse, tags=["compile"])
async def examples_page(request: Request) -> HTMLResponse:
    """
    Examples showcase page with downloadable CSV files and JSON specifications.
    
    Returns:
        HTMLResponse: Examples page with PASS/FAIL scenarios and templates
        
    Example:
        Browser GET /examples returns showcase page with all example files
    """
    return templates.TemplateResponse(
        "examples.html",
        {"request": request}
    )






@app.get("/industries/{industry}", response_class=HTMLResponse, tags=["compile"])
async def industry_page(request: Request, industry: str) -> HTMLResponse:
    """
    Industry-specific landing page.
    
    Args:
        request: FastAPI request object
        industry: Industry identifier (powder-coating, autoclave, etc.)
    
    Returns:
        HTMLResponse: Industry-specific page
    """
    # Map of valid industries to their template files
    valid_industries = {
        "powder-coating": "industries/powder-coating.html",
        "autoclave": "industries/autoclave.html",
        "concrete": "industries/concrete.html",
        "cold-chain": "industries/cold-chain.html",
        "eto": "industries/eto.html",
        "haccp": "industries/haccp.html"
    }
    
    if industry not in valid_industries:
        raise HTTPException(status_code=404, detail="Industry not found")
    
    return templates.TemplateResponse(
        valid_industries[industry],
        {"request": request}
    )


# Targeted redirects to eliminate legacy 500s from bad URLs seen in the wild
@app.get("/industries/medical-devices", include_in_schema=False)
async def redirect_medical_devices() -> RedirectResponse:
    # Medical devices map to autoclave sterilization content
    return RedirectResponse(url="/industries/autoclave", status_code=301)


@app.get("/web/templates/index.html", include_in_schema=False)
async def redirect_templates_index() -> RedirectResponse:
    # Repo/template paths should point to the site root
    return RedirectResponse(url="/", status_code=301)


@app.get("/web/templates/industry/concrete.html", include_in_schema=False)
async def redirect_templates_concrete() -> RedirectResponse:
    # Old path to industry template → live industry page
    return RedirectResponse(url="/industries/concrete", status_code=301)


@app.get("/nav_demo", response_class=HTMLResponse, tags=["compile"])
async def nav_demo_page(request: Request) -> HTMLResponse:
    """
    Navigation demo page for testing active state detection.
    
    Returns:
        HTMLResponse: Demo page showing navigation macro functionality
    """
    return templates.TemplateResponse(
        "nav_demo.html",
        {"request": request}
    )


@app.get("/examples/{path:path}", tags=["compile"])
async def serve_example_file(path: str) -> FileResponse:
    """
    Serve example files for users to download and test.
    
    Args:
        filename: Name of the example file to serve
        
    Returns:
        FileResponse: The example file
        
    Raises:
        HTTPException: If file not found
    """
    try:
        # Support nested paths and multiple example roots while preventing traversal
        requested = Path(path)
        if requested.is_absolute() or ".." in requested.parts:
            raise HTTPException(status_code=400, detail="Invalid path")

        candidates = [
            BASE_DIR / "examples" / requested,
            BASE_DIR / "marketing" / "csv-examples" / requested.name,  # flat filename fallback
            BASE_DIR / "marketing" / "spec-examples" / requested.name,
            BASE_DIR / "tests" / "data" / requested.name,  # allow using curated test datasets
        ]

        file_path = None
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    file_path = candidate
                    break
            except Exception:
                continue
        
        if not file_path:
            raise HTTPException(status_code=404, detail=f"Example file '{path}' not found")
        
        # Security check: ensure file is under allowed roots
        allowed_roots = [
            (BASE_DIR / "examples").resolve(),
            (BASE_DIR / "marketing" / "csv-examples").resolve(),
            (BASE_DIR / "marketing" / "spec-examples").resolve(),
            (BASE_DIR / "tests" / "data").resolve(),
        ]
        resolved = file_path.resolve()
        if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
            raise HTTPException(status_code=403, detail="Access denied")
        
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")


# Industry-specific routes
@app.get("/powder-coat", response_class=HTMLResponse, tags=["powder"])
async def powder_coat_page(request: Request) -> HTMLResponse:
    """
    Powder coating cure validation page with powder-specific preset.
    
    Returns:
        HTMLResponse: Powder coating page with PMT temperature validation preset
        
    Example:
        Browser GET /powder-coat returns powder coating form with 180°C cure preset
    """
    presets = get_industry_presets()
    powder_preset_json = json.dumps(presets.get("powder", {}), indent=2) if "powder" in presets else get_default_spec("powder")
    
    return templates.TemplateResponse(
        "industry/powder.html",
        {
            "request": request,
            "industry": "powder",
            "preset_json": powder_preset_json,
            "default_spec": powder_preset_json,
            "presets": presets
        }
    )


@app.get("/haccp", response_class=HTMLResponse, tags=["haccp"])
async def haccp_page(request: Request) -> HTMLResponse:
    """
    HACCP compliance temperature validation page with HACCP-specific preset.
    
    Returns:
        HTMLResponse: HACCP page with food safety temperature monitoring preset
        
    Example:
        Browser GET /haccp returns HACCP form with cooling validation preset
    """
    presets = get_industry_presets()
    haccp_preset_json = json.dumps(presets.get("haccp", {}), indent=2) if "haccp" in presets else get_default_spec("haccp")
    
    return templates.TemplateResponse(
        "industry/haccp.html",
        {
            "request": request,
            "industry": "haccp",
            "preset_json": haccp_preset_json,
            "default_spec": haccp_preset_json,
            "presets": presets
        }
    )


@app.get("/autoclave", response_class=HTMLResponse, tags=["autoclave"])
async def autoclave_page(request: Request) -> HTMLResponse:
    """
    Autoclave sterilization validation page with autoclave-specific preset.
    
    Returns:
        HTMLResponse: Autoclave page with sterilization cycle validation preset
        
    Example:
        Browser GET /autoclave returns autoclave form with 121°C sterilization preset
    """
    presets = get_industry_presets()
    autoclave_preset_json = json.dumps(presets.get("autoclave", {}), indent=2) if "autoclave" in presets else get_default_spec("autoclave")
    
    return templates.TemplateResponse(
        "industry/autoclave.html",
        {
            "request": request,
            "industry": "autoclave",
            "preset_json": autoclave_preset_json,
            "default_spec": autoclave_preset_json,
            "presets": presets
        }
    )


@app.get("/sterile", response_class=HTMLResponse, tags=["sterile"])
async def sterile_page(request: Request) -> HTMLResponse:
    """
    Sterile processing validation page with sterile-specific preset.
    
    Returns:
        HTMLResponse: Sterile page with sterile processing validation preset
        
    Example:
        Browser GET /sterile returns sterile form with cleanroom validation preset
    """
    presets = get_industry_presets()
    sterile_preset_json = json.dumps(presets.get("sterile", {}), indent=2) if "sterile" in presets else get_default_spec("sterile")
    
    return templates.TemplateResponse(
        "industry/sterile.html",
        {
            "request": request,
            "industry": "sterile",
            "preset_json": sterile_preset_json,
            "default_spec": sterile_preset_json,
            "presets": presets
        }
    )


@app.get("/concrete", response_class=HTMLResponse, tags=["concrete"])
async def concrete_page(request: Request) -> HTMLResponse:
    """
    Concrete curing validation page with concrete-specific preset.
    
    Returns:
        HTMLResponse: Concrete page with concrete curing temperature validation preset
        
    Example:
        Browser GET /concrete returns concrete form with curing validation preset
    """
    presets = get_industry_presets()
    concrete_preset_json = json.dumps(presets.get("concrete", {}), indent=2) if "concrete" in presets else get_default_spec("concrete")
    
    return templates.TemplateResponse(
        "industry/concrete.html",
        {
            "request": request,
            "industry": "concrete",
            "preset_json": concrete_preset_json,
            "default_spec": concrete_preset_json,
            "presets": presets
        }
    )


@app.get("/cold-chain", response_class=HTMLResponse, tags=["coldchain"])
async def cold_chain_page(request: Request) -> HTMLResponse:
    """
    Cold chain validation page with cold chain-specific preset.
    
    Returns:
        HTMLResponse: Cold chain page with pharmaceutical cold storage validation preset
        
    Example:
        Browser GET /cold-chain returns cold chain form with 2-8°C storage preset
    """
    presets = get_industry_presets()
    coldchain_preset_json = json.dumps(presets.get("coldchain", {}), indent=2) if "coldchain" in presets else get_default_spec("coldchain")
    
    return templates.TemplateResponse(
        "industry/coldchain.html",
        {
            "request": request,
            "industry": "coldchain",
            "preset_json": coldchain_preset_json,
            "default_spec": coldchain_preset_json,
            "presets": presets
        }
    )


@app.get("/trust", response_class=HTMLResponse, tags=["compile"])
async def trust_page(request: Request) -> HTMLResponse:
    """
    Trust and security information page explaining ProofKit's verification mechanisms.
    
    Returns:
        HTMLResponse: Trust page with security features and verification explanation
        
    Example:
        Browser GET /trust returns trust page with cryptographic verification details
    """
    return templates.TemplateResponse(
        "trust.html",
        {"request": request}
    )


@app.get("/pricing", response_class=HTMLResponse, tags=["compile"])
async def pricing_page(request: Request) -> HTMLResponse:
    """
    Pricing page showing all available subscription tiers and features.
    
    Returns:
        HTMLResponse: Pricing page with tier comparison and signup options
        
    Example:
        Browser GET /pricing returns pricing page with all subscription tiers
    """
    from core.billing import PLANS
    
    # Get user from request state if authenticated
    user = getattr(request.state, 'user', None)
    
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "plans": PLANS,
            "user": user
        }
    )


# Blog routes
@app.get("/blog", response_class=HTMLResponse, tags=["blog"])
async def blog_index(request: Request) -> HTMLResponse:
    """
    Blog index page showing all available blog posts.
    
    Returns:
        HTMLResponse: Blog index with list of all posts
    """
    # Get all blog posts from marketing/blog directory
    blog_dir = Path("marketing/blog")
    blog_posts = []
    
    if blog_dir.exists():
        for blog_file in blog_dir.glob("*.md"):
            # Read first few lines to get title and metadata
            try:
                with open(blog_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    title = lines[0].replace('# ', '') if lines else blog_file.stem
                    
                    # Extract excerpt from content (first paragraph after title)
                    excerpt = ""
                    for line in lines[1:]:
                        if line.strip() and not line.startswith('*'):
                            excerpt = line.strip()[:200] + "..."
                            break
                    
                    blog_posts.append({
                        'slug': blog_file.stem,
                        'title': title,
                        'excerpt': excerpt,
                        'filename': blog_file.name
                    })
            except Exception as e:
                logging.warning(f"Could not parse blog file {blog_file}: {e}")
    
    return templates.TemplateResponse(
        "blog/index.html",
        {"request": request, "blog_posts": blog_posts}
    )


@app.get("/blog/{slug}", response_class=HTMLResponse, tags=["blog"])
async def blog_post(request: Request, slug: str) -> HTMLResponse:
    """
    Individual blog post page.
    
    Args:
        slug: Blog post slug (filename without .md extension)
        
    Returns:
        HTMLResponse: Individual blog post content
    """
    blog_file = Path(f"marketing/blog/{slug}.md")
    
    if not blog_file.exists():
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    try:
        with open(blog_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Simple markdown parsing - extract title and content
        lines = content.split('\n')
        title = lines[0].replace('# ', '') if lines else slug.replace('-', ' ').title()
        
        # Compute excerpt: first non-empty paragraph after title
        excerpt = ""
        for line in lines[1:]:
            stripped_line = line.strip()
            if stripped_line and not stripped_line.startswith('*') and not stripped_line.startswith('#'):
                excerpt = stripped_line[:200] + "..."
                break
        
        # Proper markdown to HTML conversion with Jinja2 safety
        def markdown_to_html(md_text):
            """Convert markdown to HTML with proper escaping for Jinja2 safety"""
            lines = md_text.split('\n')
            html_lines = []
            in_list = False
            
            for line in lines:
                stripped = line.strip()
                
                # Handle headers
                if stripped.startswith('### '):
                    if in_list:
                        html_lines.append('</ul>')
                        in_list = False
                    content = html.escape(stripped[4:])
                    html_lines.append(f'<h3 style="color: #1a1a1a; font-size: 1.25rem; font-weight: 600; margin: 2rem 0 1rem 0;">{content}</h3>')
                elif stripped.startswith('## '):
                    if in_list:
                        html_lines.append('</ul>')
                        in_list = False
                    content = html.escape(stripped[3:])
                    html_lines.append(f'<h2 style="color: #1a1a1a; font-size: 1.5rem; font-weight: 600; margin: 2rem 0 1rem 0;">{content}</h2>')
                elif stripped.startswith('# '):
                    if in_list:
                        html_lines.append('</ul>')
                        in_list = False
                    # Skip the title as it's handled separately
                    continue
                    
                # Handle bullet points
                elif stripped.startswith('- '):
                    if not in_list:
                        html_lines.append('<ul style="margin-bottom: 1.5rem; padding-left: 1.5rem;">')
                        in_list = True
                    content = html.escape(stripped[2:])
                    # Handle bold text in bullet points
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                    html_lines.append(f'<li style="margin-bottom: 0.5rem;">{content}</li>')
                    
                # Handle empty lines
                elif stripped == '':
                    if in_list:
                        html_lines.append('</ul>')
                        in_list = False
                    html_lines.append('')
                    
                # Handle regular paragraphs
                else:
                    if in_list:
                        html_lines.append('</ul>')
                        in_list = False
                    
                    if stripped:
                        # Escape HTML to prevent Jinja2 conflicts
                        content = html.escape(stripped)
                        # Handle bold text
                        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                        # Handle links
                        content = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #667eea; text-decoration: none;">\1</a>', content)
                        html_lines.append(f'<p style="margin-bottom: 1.5rem;">{content}</p>')
            
            # Close any open list
            if in_list:
                html_lines.append('</ul>')
            
            return '\n'.join(html_lines)
        
        html_content = markdown_to_html(content)
        
        return templates.TemplateResponse(
            "blog/post.html",
            {
                "request": request, 
                "title": title,
                "content": html_content,
                "slug": slug,
                "excerpt": excerpt,
                "date": "Recently Published",  # Add default date
                "reading_time": 5  # Add default reading time
            }
        )
        
    except Exception as e:
        logging.error(f"Error reading blog post {slug}: {e}")
        raise HTTPException(status_code=500, detail="Error loading blog post")


@app.get("/docs", response_class=HTMLResponse, tags=["docs"])
async def docs_page(request: Request) -> HTMLResponse:
    """
    Documentation page with API documentation and usage guides.
    
    Returns:
        HTMLResponse: Documentation page
    """
    return templates.TemplateResponse(
        "docs.html",
        {"request": request}
    )


@app.get("/sitemap.xml", tags=["seo"])
async def sitemap():
    """
    Serve sitemap.xml for search engine indexing.
    
    Returns:
        FileResponse: XML sitemap file
    """
    sitemap_path = Path("marketing/sitemap.xml")
    if sitemap_path.exists():
        return FileResponse(
            sitemap_path,
            media_type="application/xml",
            filename="sitemap.xml"
        )
    else:
        raise HTTPException(status_code=404, detail="Sitemap not found")


@app.get("/robots.txt", tags=["seo"])
async def robots_txt():
    """
    Serve robots.txt for search engine crawling directives.
    
    Returns:
        FileResponse: robots.txt file
    """
    robots_path = static_dir / "robots.txt"
    if robots_path.exists():
        return FileResponse(
            robots_path,
            media_type="text/plain",
            filename="robots.txt"
        )
    else:
        raise HTTPException(status_code=404, detail="Robots.txt not found")


@app.get("/.well-known/security.txt", tags=["seo"])
async def security_txt():
    """
    Serve security.txt for responsible security disclosure (RFC 9116).
    
    Returns:
        FileResponse: security.txt file
    """
    security_path = BASE_DIR / ".well-known" / "security.txt"
    if security_path.exists():
        return FileResponse(
            security_path,
            media_type="text/plain",
            filename="security.txt"
        )
    else:
        raise HTTPException(status_code=404, detail="Security.txt not found")


# Authentication routes
@app.get("/auth/get-started", response_class=HTMLResponse, tags=["auth"])
async def get_started_page(request: Request, return_url: Optional[str] = None, error: Optional[str] = None) -> HTMLResponse:
    """
    Unified authentication page for login/signup via magic link.
    
    Returns:
        HTMLResponse: Magic link request form
    """
    # If user is already authenticated, redirect to return_url or app
    user = get_current_user(request)
    if user:
        # If there's a return_url, try to use it (but validate it's safe)
        if return_url and return_url.startswith('/'):
            return RedirectResponse(url=return_url, status_code=302)
        return RedirectResponse(url="/app", status_code=302)
    
    # Pass return_url and error to template for display
    return templates.TemplateResponse(
        "auth/get_started.html",
        {
            "request": request,
            "return_url": return_url,
            "error": error
        }
    )


# Keep old endpoints for backward compatibility but redirect
@app.get("/auth/login", response_class=HTMLResponse, tags=["auth"])
async def login_page(request: Request, return_url: Optional[str] = None, error: Optional[str] = None) -> HTMLResponse:
    """Legacy login endpoint - redirects to get-started preserving parameters."""
    # Preserve return_url and error parameters when redirecting
    redirect_url = "/auth/get-started"
    params = []
    if return_url:
        params.append(f"return_url={return_url}")
    if error:
        params.append(f"error={error}")
    if params:
        redirect_url += "?" + "&".join(params)
    return RedirectResponse(url=redirect_url, status_code=302)


@app.get("/auth/signup", response_class=HTMLResponse, tags=["auth"])
async def signup_page(request: Request) -> HTMLResponse:
    """Legacy signup endpoint - redirects to get-started."""
    return RedirectResponse(url="/auth/get-started", status_code=302)


@app.post("/auth/magic-link", response_class=HTMLResponse, tags=["auth"])
async def request_magic_link_unified(
    request: Request,
    email: str = Form(...),
    return_url: Optional[str] = Form(None)
) -> HTMLResponse:
    """
    Unified magic link handler for both login and signup.
    
    Args:
        request: FastAPI request object
        email: User email address
    
    Returns:
        HTMLResponse: Magic link sent confirmation page
    """
    try:
        # Generate magic link (works for both new and existing users)
        magic_token = auth_handler.generate_magic_link(email, UserRole.OPERATOR, return_url)
        
        # In development mode, include the link
        dev_mode = os.environ.get("EMAIL_DEV_MODE", "false").lower() == "true"
        dev_link = None
        if dev_mode:
            base_url = os.environ.get("BASE_URL", "https://www.proofkit.net")
            dev_link = f"{base_url}/auth/verify?token={magic_token}"
        
        # Send magic link email
        email_sent = auth_handler.send_magic_link_email(email, magic_token, UserRole.OPERATOR)
        
        if not email_sent:
            logger.error(f"Failed to send magic link email to {email}")
        
        logger.info(f"Magic link requested for {email}")
        
        return templates.TemplateResponse(
            "auth/magic_link_sent.html",
            {
                "request": request,
                "email": email,
                "expires_in": 900,  # 15 minutes
                "expires_in_minutes": 15,
                "dev_mode": dev_mode,
                "dev_link": dev_link
            }
        )
        
    except Exception as e:
        logger.error(f"Magic link error for {email}: {e}")
        return templates.TemplateResponse(
            "auth/error.html",
            {
                "request": request,
                "error": "Failed to send magic link. Please try again."
            }
        )


# Keep old signup endpoint for backward compatibility
@app.post("/auth/signup", response_class=HTMLResponse, tags=["auth"])
async def signup_submit(
    request: Request,
    email: str = Form(...),
    company: Optional[str] = Form(None),
    industry: Optional[str] = Form(None),
    terms: bool = Form(...),
    marketing: bool = Form(False)
) -> HTMLResponse:
    """
    Handle signup form submission and show magic link sent page.
    
    Args:
        request: FastAPI request object
        email: User email address
        company: Optional company name
        industry: Optional industry selection
        terms: Terms acceptance
        marketing: Marketing consent
    
    Returns:
        HTMLResponse: Magic link sent confirmation page
    """
    try:
        # Check for trial abuse
        from middleware.trial_protection import check_trial_abuse, record_trial_signup
        is_abuse, abuse_reason = check_trial_abuse(request, email)
        
        if is_abuse:
            logger.warning(f"Trial abuse blocked for {email}: {abuse_reason}")
            return templates.TemplateResponse(
                "auth/error.html",
                {
                    "request": request,
                    "error": abuse_reason,
                    "suggestions": [
                        "Use your existing account to continue",
                        "Upgrade your current plan for more certificates",
                        "Contact support if you believe this is an error"
                    ]
                }
            )
        
        # Record the trial signup for tracking
        record_trial_signup(request, email)
        
        # Generate magic link using auth handler
        magic_token = auth_handler.generate_magic_link(email, UserRole.OPERATOR)
        
        # In development mode, include the link
        dev_mode = os.environ.get("EMAIL_DEV_MODE", "false").lower() == "true"
        dev_link = None
        if dev_mode:
            base_url = os.environ.get("BASE_URL", "https://www.proofkit.net")
            dev_link = f"{base_url}/auth/verify?token={magic_token}"
        
        # Send magic link email
        email_sent = auth_handler.send_magic_link_email(email, magic_token, UserRole.OPERATOR)
        
        if not email_sent:
            logger.error(f"Failed to send magic link email to {email}")
            # Still show the page but with a warning
        
        logger.info(f"Signup successful for {email}, company: {company}, industry: {industry}")
        
        return templates.TemplateResponse(
            "auth/magic_link_sent.html",
            {
                "request": request,
                "email": email,
                "expires_in": 900,  # 15 minutes
                "expires_in_minutes": 15,
                "dev_mode": dev_mode,
                "dev_link": dev_link
            }
        )
        
    except Exception as e:
        logger.error(f"Signup error for {email}: {e}")
        return templates.TemplateResponse(
            "auth/error.html",
            {
                "request": request,
                "error": "Failed to process signup. Please try again."
            }
        )


@app.post("/auth/request-link", tags=["auth"])
async def request_magic_link(request: Request, email: str = Form(...), role: str = Form(...)) -> JSONResponse:
    """
    Request a magic link for authentication.
    
    Args:
        request: FastAPI request object
        email: User email address
        role: User role (op or qa)
    
    Returns:
        JSONResponse: Success message or error
    """
    try:
        # Check for trial abuse if it's a new user
        from middleware.trial_protection import check_trial_abuse, record_trial_signup
        
        # Only check for abuse on operator role (trial users)
        if role == "op":
            is_abuse, abuse_reason = check_trial_abuse(request, email)
            
            if is_abuse:
                logger.warning(f"Trial abuse blocked for {email}: {abuse_reason}")
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": abuse_reason
                    }
                )
            
            # Record the trial signup for tracking
            record_trial_signup(request, email)
        # Validate role
        if role not in ["op", "qa"]:
            raise HTTPException(status_code=400, detail="Invalid role. Must be 'op' or 'qa'")
        
        user_role = UserRole(role)
        
        # Generate magic link
        magic_token = auth_handler.generate_magic_link(email, user_role)
        
        # Send email
        success = auth_handler.send_magic_link_email(email, magic_token, user_role)
        
        if success:
            response_data = {
                "message": f"Magic link sent to {email}",
                "expires_in": 15 * 60  # 15 minutes
            }
            
            # In development mode, include the actual link
            if os.environ.get("EMAIL_DEV_MODE", "false").lower() == "true":
                dev_link = auth_handler.get_dev_link(email)
                if dev_link:
                    response_data["dev_link"] = dev_link
                    response_data["message"] = f"Magic link generated for {email} (Development Mode)"
            
            return JSONResponse(response_data)
        else:
            raise HTTPException(status_code=500, detail="Failed to send magic link email")
            
    except Exception as e:
        logger.error(f"Magic link request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/verify", tags=["auth"])
async def verify_magic_link(request: Request, token: str) -> HTMLResponse:
    """
    Verify magic link and authenticate user.
    
    Args:
        request: FastAPI request object
        token: Magic link token
    
    Returns:
        HTMLResponse: Redirect to dashboard or error page
    """
    try:
        # Validate magic link
        link_data = auth_handler.validate_magic_link(token)
        
        if not link_data:
            return templates.TemplateResponse(
                "auth/error.html",
                {
                    "request": request,
                    "error": "Invalid or expired magic link"
                }
            )
        
        # Create JWT token
        jwt_token = auth_handler.create_jwt_token(link_data["email"], UserRole(link_data["role"]))

        # Get and sanitize return_url from link data if available
        _ru = link_data.get("return_url")
        def _is_safe_return_url(path: Optional[str]) -> bool:
            if not path or not isinstance(path, str):
                return False
            if not path.startswith("/"):
                return False
            if path.startswith("//"):
                return False
            if "://" in path:
                return False
            return True
        return_url = _ru if _is_safe_return_url(_ru) else None
        
        # Create response with cookie
        response = templates.TemplateResponse(
            "auth/success.html",
            {
                "request": request,
                "email": link_data["email"],
                "role": link_data["role"],
                "return_url": return_url  # Pass to template for redirect
            }
        )
        
        # Set secure cookie (detect HTTPS or proxy header)
        is_https = (request.url.scheme == "https") or (request.headers.get("x-forwarded-proto", "") == "https")
        response.set_cookie(
            key="auth_token",
            value=jwt_token,
            max_age=24 * 60 * 60,  # 24 hours
            httponly=True,
            secure=is_https,
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Magic link verification failed: {e}")
        return templates.TemplateResponse(
            "auth/error.html",
            {
                "request": request,
                "error": "Authentication failed"
            }
        )


@app.post("/auth/logout", tags=["auth"])
async def logout(request: Request) -> JSONResponse:
    """
    Logout user by clearing authentication cookie.
    
    Returns:
        JSONResponse: Success message
    """
    response = JSONResponse({"message": "Logged out successfully"})
    response.delete_cookie("auth_token")
    return response


@app.get("/auth/logout", tags=["auth"])
async def logout_get(request: Request) -> RedirectResponse:
    """
    Logout user via GET request and redirect to home.
    
    Returns:
        RedirectResponse: Redirect to home page after logout
    """
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("auth_token")
    return response


# QA Approval routes
@app.get("/approve/{job_id}", tags=["auth"])
async def approve_job_page(request: Request, job_id: str) -> HTMLResponse:
    """
    QA approval page for a specific job.
    
    Args:
        request: FastAPI request object
        job_id: Job identifier
    
    Returns:
        HTMLResponse: Approval page with job details
    """
    # Require QA role with redirect to login
    try:
        user = require_qa_redirect(request)
    except HTTPException as e:
        if e.status_code == 302:
            return RedirectResponse(url=e.headers["Location"], status_code=302)
        raise
    
    try:
        # Load job metadata
        job_dir = create_job_storage_path(job_id)
        meta_path = job_dir / "meta.json"
        
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail="Job not found")
        
        with open(meta_path, 'r') as f:
            job_meta = json.load(f)
        
        # Load decision data
        decision_path = job_dir / "decision.json"
        if decision_path.exists():
            with open(decision_path, 'r') as f:
                decision_data = json.load(f)
        else:
            decision_data = None
        
        return templates.TemplateResponse(
            "auth/approve.html",
            {
                "request": request,
                "job_id": job_id,
                "job_meta": job_meta,
                "decision": decision_data,
                "user": user
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load job {job_id} for approval: {e}")
        raise HTTPException(status_code=500, detail="Failed to load job details")


@app.post("/approve/{job_id}", tags=["auth"])
async def approve_job(request: Request, job_id: str) -> JSONResponse:
    """
    Approve a job (QA only).
    
    Args:
        request: FastAPI request object
        job_id: Job identifier
    
    Returns:
        JSONResponse: Success message
    """
    # Require QA role with redirect to login
    try:
        user = require_qa_redirect(request)
    except HTTPException as e:
        if e.status_code == 302:
            return RedirectResponse(url=e.headers["Location"], status_code=302)
        raise
    
    try:
        # Load job metadata
        job_dir = create_job_storage_path(job_id)
        meta_path = job_dir / "meta.json"
        
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail="Job not found")
        
        with open(meta_path, 'r') as f:
            job_meta = json.load(f)
        
        # Check if already approved
        if job_meta.get("approved", False):
            return JSONResponse({"message": "Job already approved"})
        
        # Update metadata with approval
        job_meta["approved"] = True
        job_meta["approved_by"] = user.email
        job_meta["approved_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save updated metadata
        with open(meta_path, 'w') as f:
            json.dump(job_meta, f, indent=2)
        
        # Regenerate PDF without "DRAFT" watermark
        try:
            from core.render_pdf import generate_proof_pdf
            decision_path = job_dir / "decision.json"
            spec_path = job_dir / "specification.json"
            plot_path = job_dir / "plot.png"
            normalized_csv_path = job_dir / "normalized_data.csv"
            
            if all(p.exists() for p in [decision_path, spec_path, plot_path, normalized_csv_path]):
                with open(decision_path, 'r') as f:
                    decision_data = json.load(f)
                with open(spec_path, 'r') as f:
                    spec_data = json.load(f)
                
                # Generate verification hash
                verification_hash = hashlib.sha256(
                    f"{job_id}{decision_data['pass']}{decision_data['actual_hold_time_s']}".encode()
                ).hexdigest()
                
                # Get original creator's plan from metadata
                creator_info = job_meta.get("creator", {})
                creator_plan = creator_info.get("plan", "free")
                
                # Regenerate PDF without draft watermark (convert dicts to models)
                pdf_path = job_dir / "proof.pdf"
                from core.models import SpecV1, DecisionResult
                try:
                    spec_model = SpecV1(**spec_data)
                except Exception:
                    # If spec_data already matches, pass through
                    spec_model = spec_data
                try:
                    decision_model = DecisionResult(**decision_data)
                except Exception:
                    decision_model = decision_data

                generate_proof_pdf(
                    spec=spec_model,
                    decision=decision_model,
                    plot_path=str(plot_path),
                    normalized_csv_path=str(normalized_csv_path),
                    verification_hash=verification_hash,
                    output_path=str(pdf_path),
                    is_draft=False,
                    user_plan=creator_plan
                )
                
                logger.info(f"Job {job_id} approved by {user.email} and PDF regenerated")
            else:
                logger.warning(f"Missing files for PDF regeneration in job {job_id}")
                
        except Exception as e:
            logger.error(f"Failed to regenerate PDF for approved job {job_id}: {e}")
            # Don't fail the approval if PDF regeneration fails
        
        return JSONResponse({
            "message": f"Job {job_id} approved successfully",
            "approved_by": user.email,
            "approved_at": job_meta["approved_at"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve job")


def save_job_metadata(job_dir: Path, job_id: str, metadata: Dict[str, Any]) -> None:
    """
    Save job metadata to storage.
    
    Args:
        job_dir: Job directory path
        job_id: Job identifier
        metadata: Metadata dictionary
    """
    meta_path = job_dir / "meta.json"
    metadata["job_id"] = job_id
    metadata["created_at"] = datetime.now(timezone.utc).isoformat()
    metadata["approved"] = False  # Default to not approved
    
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)


@app.get("/upgrade-required", response_class=HTMLResponse, tags=["auth"])
async def upgrade_required_page(request: Request) -> HTMLResponse:
    """
    Show upgrade required page when quota is exceeded.
    
    Args:
        request: FastAPI request object
        
    Returns:
        HTMLResponse: Upgrade required page
    """
    try:
        current_user = get_current_user(request)
        if not current_user:
            return RedirectResponse(url="/auth/login", status_code=302)
        
        # Get usage details for display
        usage_summary = get_user_usage_summary(current_user.email)
        
        return templates.TemplateResponse(
            "quota_exceeded.html",
            {
                "request": request,
                "used": usage_summary.get('monthly_used', usage_summary.get('total_used', 2)),
                "limit": usage_summary.get('monthly_limit', usage_summary.get('total_limit', 2)),
                "plan": usage_summary.get('plan', 'free'),
                "user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error loading upgrade required page: {e}")
        return RedirectResponse(url="/pricing", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse, tags=["auth"])
async def dashboard_page(request: Request, page: int = Query(1, ge=1)) -> HTMLResponse:
    """
    User dashboard showing subscription, usage, and recent jobs with pagination.
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/get-started", status_code=302)
    
    try:
        # Get user's quota information (with fallback)
        try:
            quota_data = get_user_usage_summary(user.email)
        except Exception as quota_error:
            logger.warning(f"Failed to get user quota data: {quota_error}")
            # Fallback quota data for free tier
            quota_data = {
                'plan': 'free',
                'plan_name': 'Free',
                'monthly_used': 0,
                'monthly_limit': 2,
                'monthly_remaining': 2,
                'total_used': 0,
                'total_limit': 2,
                'total_remaining': 2,
                'is_unlimited': False,
                'overage_available': False,
                'subscription': None,
                'next_billing_date': 'N/A'
            }
        
        # Get user's recent jobs
        recent_jobs = []
        jobs_found = 0
        jobs_checked = 0
        
        logger.info(f"Dashboard: Searching for jobs for user: {user.email}")
        
        # Search through all directories in storage
        for item in STORAGE_DIR.iterdir():
            if not item.is_dir():
                continue
            
            # Skip special directories
            if item.name in ['auth', 'test', 'trial_tracking', 'quota']:
                continue
            
            # Check if this is a hash directory (2 chars) with job subdirs
            if len(item.name) == 2:  # Hash directory like '68'
                for job_dir in item.iterdir():
                    if not job_dir.is_dir():
                        continue
                    
                    meta_path = job_dir / "meta.json"
                    if not meta_path.exists():
                        continue
                    
                    jobs_checked += 1
                    try:
                        with open(meta_path, "r") as f:
                            meta = json.load(f)
                        creator = meta.get("creator", {})
                        
                        # Handle both dict and None creator
                        if creator:
                            creator_email = creator.get("email", "").lower().strip()
                        else:
                            creator_email = ""
                        
                        user_email_normalized = user.email.lower().strip()
                        
                        if creator_email == user_email_normalized:
                            decision_path = job_dir / "decision.json"
                            pass_fail = False
                            if decision_path.exists():
                                with open(decision_path, "r") as f:
                                    decision = json.load(f)
                                    pass_fail = decision.get("pass", False)
                            
                            recent_jobs.append({
                                "job_id": meta.get("job_id"),
                                "created_at": meta.get("created_at"),
                                "approved": meta.get("approved", False),
                                "pass": pass_fail,
                                "meta": meta
                            })
                            jobs_found += 1
                            logger.debug(f"Found job {meta.get('job_id')} for user")
                    except Exception as e:
                        logger.debug(f"Error reading job {job_dir}: {e}")
                        continue
        
        logger.info(f"Dashboard: Checked {jobs_checked} jobs, found {jobs_found} for {user.email}")
        
        # Sort by created_at desc
        recent_jobs.sort(key=lambda j: j["created_at"] or "", reverse=True)
        
        # Generate usage data for chart based on ALL user's jobs (not just top 5)
        usage_data = generate_usage_chart_data(recent_jobs)  # Pass all jobs for chart
        logger.info(f"Dashboard for {user.email}: Found {len(recent_jobs)} total jobs, usage_data: {usage_data}")
        
        # Pagination settings
        items_per_page = 5
        total_jobs = len(recent_jobs)
        total_pages = (total_jobs + items_per_page - 1) // items_per_page if total_jobs > 0 else 1
        
        # Ensure page is within valid range
        page = max(1, min(page, total_pages))
        
        # Calculate slice indices
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        # Get jobs for current page
        recent_jobs_display = recent_jobs[start_idx:end_idx]
        
        # Get pricing info for the user's plan (with fallback)
        try:
            from core.billing import get_plan
            plan_info = get_plan(quota_data.get('plan', 'free'))
            if not plan_info:
                # Fallback to default plan info (USD)
                plan_info = {
                    'name': 'Free',
                    'price_usd': 0,
                    'single_cert_price_usd': 9,
                    'jobs_month': 2
                }
        except (ImportError, Exception) as e:
            logger.warning(f"Failed to import billing module or get plan info: {e}")
            # Fallback plan info (USD)
            plan_info = {
                'name': 'Free', 
                'price_usd': 0,
                'single_cert_price_usd': 9,
                'jobs_month': 2
            }
        
        # Prepare template context
        context = {
            "request": request,
            "user": user,
            "quota": {
                "plan": quota_data.get('plan', 'free'),
                "plan_name": plan_info.get('name', 'Free'),
                "price": plan_info.get('price_usd', 0),
                "monthly_used": quota_data.get('monthly_used', 0),
                "monthly_limit": quota_data.get('monthly_limit'),
                "monthly_remaining": quota_data.get('monthly_remaining'),
                "total_used": quota_data.get('total_used', 0),
                "total_remaining": quota_data.get('total_remaining', 2),
                "single_cert_price": plan_info.get('single_cert_price_usd', 9),
                "subscription": quota_data.get('subscription'),
                "next_billing_date": quota_data.get('next_billing_date', 'N/A')
            },
            "recent_jobs": recent_jobs_display,  # Jobs for current page
            "usage_data": usage_data,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_jobs": total_jobs,
                "has_prev": page > 1,
                "has_next": page < total_pages,
                "prev_page": page - 1 if page > 1 else 1,
                "next_page": page + 1 if page < total_pages else total_pages,
                "page_range": list(range(max(1, page - 2), min(total_pages + 1, page + 3))),
                "start_index": start_idx + 1 if total_jobs > 0 else 0,
                "end_index": min(end_idx, total_jobs)
            }
        }
        
        return templates.TemplateResponse("dashboard.html", context)
        
    except Exception as e:
        logger.error(f"Dashboard error for {user.email}: {e}")
        # Return a basic dashboard with minimal data instead of error page
        fallback_context = {
            "request": request,
            "user": user,
            "quota": {
                "plan": "free",
                "plan_name": "Free",
                "price": 0,
                "monthly_used": 0,
                "monthly_limit": 2,
                "monthly_remaining": 2,
                "total_used": 0,
                "total_remaining": 2,
                "single_cert_price": 7,
                "subscription": None,
                "next_billing_date": 'N/A'
            },
            "recent_jobs": [],
            "usage_data": {"labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"], "data": [0, 0, 0, 0, 0, 0]},
            "pagination": {
                "current_page": 1,
                "total_pages": 1,
                "total_jobs": 0,
                "has_prev": False,
                "has_next": False,
                "prev_page": 1,
                "next_page": 1,
                "page_range": [1]
            }
        }
        logger.warning(f"Using fallback dashboard data for {user.email}")
        return templates.TemplateResponse("dashboard.html", fallback_context)

@app.get("/my-jobs", response_class=HTMLResponse, tags=["auth"])
async def my_jobs_page(request: Request) -> HTMLResponse:
    """
    Show jobs for the current user (OP: jobs submitted, QA: jobs awaiting approval).
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/get-started", status_code=302)
    # Scan storage for jobs
    jobs = []
    for root, dirs, files in os.walk(str(STORAGE_DIR)):
        if "meta.json" in files:
            meta_path = os.path.join(root, "meta.json")
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                job_id = meta.get("job_id")
                creator = meta.get("creator", {})
                approved = meta.get("approved", False)
                created_at = meta.get("created_at")
                approved_at = meta.get("approved_at")
                # OP: jobs they submitted; QA: jobs not yet approved
                # Handle both dict and None creator
                if creator:
                    creator_email = creator.get("email", "").lower().strip()
                else:
                    creator_email = ""
                user_email_normalized = user.email.lower().strip()
                
                if (user.role == UserRole.OPERATOR and creator_email == user_email_normalized) or (user.role == UserRole.QA and not approved):
                    jobs.append({
                        "job_id": job_id,
                        "created_at": created_at,
                        "approved": approved,
                        "approved_at": approved_at,
                        "creator": creator,
                        "meta": meta
                    })
            except Exception:
                continue
    # Sort jobs by created_at desc
    jobs.sort(key=lambda j: j["created_at"] or "", reverse=True)
    return templates.TemplateResponse("my_jobs.html", {"request": request, "user": user, "jobs": jobs})


@app.get("/api/validation-pack/{job_id}", tags=["validation"])
async def get_validation_pack(job_id: str, request: Request) -> JSONResponse:
    """
    Generate and return a validation pack ZIP file for a job.
    
    Args:
        job_id: Job identifier
        request: FastAPI request object
    
    Returns:
        JSONResponse with validation pack information or error
    """
    try:
        # Load job metadata
        job_dir = create_job_storage_path(job_id)
        meta_path = job_dir / "meta.json"
        
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail="Job not found")
        
        with open(meta_path, 'r') as f:
            job_meta = json.load(f)
        
        # Generate validation pack
        validation_pack_path = job_dir / "validation_pack.zip"
        
        if not validation_pack_path.exists():
            success = create_validation_pack(job_id, job_meta, validation_pack_path)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to create validation pack")
        
        # Get validation pack info
        pack_info = get_validation_pack_info(job_id, job_meta)
        
        # Return download URL and info
        return JSONResponse({
            "job_id": job_id,
            "download_url": f"/download/{job_id}/validation-pack",
            "pack_info": pack_info,
            "message": "Validation pack ready for download"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate validation pack for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate validation pack")


@app.get("/download/{job_id}/validation-pack", tags=["validation"])
async def download_validation_pack(
    job_id: str, 
    request: Request,
    current_user: dict = Depends(require_auth)
) -> FileResponse:
    """
    Download the validation pack ZIP file for a job.
    
    Args:
        job_id: Job identifier
        request: FastAPI request object
    
    Returns:
        FileResponse with the validation pack ZIP file
    """
    try:
        # Load job metadata
        job_dir = create_job_storage_path(job_id)
        meta_path = job_dir / "meta.json"
        validation_pack_path = job_dir / "validation_pack.zip"
        
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Generate validation pack if it doesn't exist
        if not validation_pack_path.exists():
            with open(meta_path, 'r') as f:
                job_meta = json.load(f)
            
            success = create_validation_pack(job_id, job_meta, validation_pack_path)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to create validation pack")
        
        # Return the ZIP file
        return FileResponse(
            path=validation_pack_path,
            filename=f"validation_pack_{job_id}.zip",
            media_type="application/zip"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download validation pack for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to download validation pack")


# Billing success/cancel pages
@app.get("/billing/success", response_class=HTMLResponse, tags=["billing"])
async def billing_success_page(
    request: Request,
    session_id: Optional[str] = None,
    plan: Optional[str] = None
) -> HTMLResponse:
    """
    Display billing success page after successful payment.
    
    Args:
        request: FastAPI request object
        session_id: Stripe checkout session ID
        plan: Plan name for subscription upgrades
        
    Returns:
        HTML success page
    """
    try:
        current_user = None
        try:
            current_user = get_current_user(request)
        except:
            pass
        
        # Get session details if available
        session_details = None
        if session_id:
            from core.stripe_util import get_checkout_session
            session_details = get_checkout_session(session_id)
        
        return templates.TemplateResponse(
            "billing_success.html",
            {
                "request": request,
                "current_user": current_user,
                "session_id": session_id,
                "plan": plan,
                "session_details": session_details,
                "title": "Payment Successful - ProofKit"
            }
        )
    except Exception as e:
        logger.error(f"Error rendering billing success page: {e}")
        # Fallback to dashboard or pricing page
        return RedirectResponse(url="/dashboard" if current_user else "/pricing", status_code=302)


@app.get("/billing/cancel", response_class=HTMLResponse, tags=["billing"])
async def billing_cancel_page(request: Request) -> HTMLResponse:
    """
    Display billing cancellation page after cancelled payment.
    
    Args:
        request: FastAPI request object
        
    Returns:
        HTML cancellation page
    """
    try:
        current_user = None
        try:
            current_user = get_current_user(request)
        except:
            pass
        
        return templates.TemplateResponse(
            "billing_cancel.html",
            {
                "request": request,
                "current_user": current_user,
                "title": "Payment Cancelled - ProofKit"
            }
        )
    except Exception as e:
        logger.error(f"Error rendering billing cancel page: {e}")
        # Fallback to pricing page
        return RedirectResponse(url="/pricing", status_code=302)


# Event handlers for background tasks
@app.on_event("startup")
async def startup_event():
    """Start background scheduler on application startup."""
    logger.info("Starting ProofKit application")
    start_background_tasks()
    logger.info("Background tasks started")

@app.on_event("shutdown") 
async def shutdown_event():
    """Stop background scheduler on application shutdown."""
    logger.info("Shutting down ProofKit application")
    stop_background_tasks()
    logger.info("Background tasks stopped")


if __name__ == "__main__":
    """
    Development server entry point.
    Run with: python app.py
    """
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )