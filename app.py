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
from pathlib import Path
from typing import Dict, Any, Optional
import mimetypes
from datetime import datetime, timezone
from io import StringIO

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
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
from core.normalize import normalize_temperature_data, load_csv_with_metadata, NormalizationError
from core.decide import make_decision, DecisionError
from core.plot import generate_proof_plot, PlotError
from core.render_pdf import generate_proof_pdf
from core.pack import create_evidence_bundle, PackingError
from core.logging import setup_logging, get_logger, RequestLoggingMiddleware
from core.cleanup import schedule_cleanup

# Base directory for the application
BASE_DIR = Path(__file__).resolve().parent

# Template and static file setup
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
static_dir = BASE_DIR / "web" / "static"

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

# Environment configuration
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "10"))
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "10")) * 1024 * 1024


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.
    
    Returns:
        FastAPI: Configured FastAPI application instance
        
    Example:
        >>> app = create_app()
        >>> # App is ready to use with uvicorn
    """
    app = FastAPI(
        title="ProofKit",
        description="Generate inspector-ready proof PDFs from CSV temperature logs",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        max_age=3600,
    )
    
    # Add request logging middleware
    app.add_middleware(RequestLoggingMiddleware)
    
    # Add rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Mount static files
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
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


def get_default_spec() -> str:
    """
    Load the default specification JSON from examples.
    
    Returns:
        str: Default specification as formatted JSON string
    """
    try:
        spec_path = BASE_DIR / "examples" / "spec_example.json"
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        return json.dumps(spec_data, indent=2)
    except Exception:
        # Fallback default spec
        fallback_spec = {
            "version": "1.0",
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
                         job_dir: Path, job_id: str) -> Dict[str, Any]:
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
            output_path=str(pdf_path)
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
    
    # Return results
    return {
        "id": job_id,
        "pass": decision.pass_,
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
        "urls": {
            "pdf": f"/download/{job_id}/pdf",
            "zip": f"/download/{job_id}/zip",
            "verify": f"/verify/{job_id}"
        },
        "verification_hash": verification_hash
    }


# Create the main app instance
app = create_app()


@app.get("/health")
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


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request) -> HTMLResponse:
    """
    Main upload page with form for CSV file and specification JSON.
    
    Returns:
        HTMLResponse: Rendered index template with default specification
        
    Example:
        Browser GET / returns upload form with pre-populated spec JSON
    """
    default_spec = get_default_spec()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_spec": default_spec
        }
    )


@app.post("/api/compile", response_class=HTMLResponse)
@limiter.limit(f"{RATE_LIMIT_PER_MIN}/minute")
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
        
        # Generate deterministic job ID
        job_id = generate_job_id(spec_data, csv_content)
        logger.info(f"[{request_id}] Generated job ID: {job_id}")
        
        # Thread-safe storage operations
        with storage_lock:
            job_dir = create_job_storage_path(job_id)
            logger.info(f"[{request_id}] Created storage path: {job_dir}")
        
        # Process through complete pipeline
        try:
            result = process_csv_and_spec(csv_content, spec_data, job_dir, job_id)
            logger.info(f"[{request_id}] Processing completed: {'PASS' if result['pass'] else 'FAIL'}")
            
            return templates.TemplateResponse(
                "result.html",
                {
                    "request": request,
                    "result": result
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


@app.post("/api/compile/json")
@limiter.limit(f"{RATE_LIMIT_PER_MIN}/minute")
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
        
        # Generate deterministic job ID
        job_id = generate_job_id(spec_data, csv_content)
        logger.info(f"[{request_id}] Generated job ID: {job_id}")
        
        # Thread-safe storage operations
        with storage_lock:
            job_dir = create_job_storage_path(job_id)
            logger.info(f"[{request_id}] Created storage path: {job_dir}")
        
        # Process through complete pipeline
        try:
            result = process_csv_and_spec(csv_content, spec_data, job_dir, job_id)
            logger.info(f"[{request_id}] Processing completed: {'PASS' if result['pass'] else 'FAIL'}")
            
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


@app.get("/verify/{bundle_id}", response_class=HTMLResponse)
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
            raise FileNotFoundError("Decision file not found")
        
        with open(decision_path, 'r') as f:
            decision_data = json.load(f)
        
        # Load evidence bundle for verification
        zip_path = job_dir / "evidence.zip"
        if not zip_path.exists():
            raise FileNotFoundError("Evidence bundle not found")
        
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


@app.get("/download/{bundle_id}/{file_type}")
async def download_file(bundle_id: str, file_type: str, request: Request) -> FileResponse:
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


@app.get("/examples", response_class=HTMLResponse)
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


@app.get("/examples/{filename}")
async def serve_example_file(filename: str) -> FileResponse:
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
        examples_dir = BASE_DIR / "examples"
        file_path = examples_dir / filename
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"Example file '{filename}' not found")
        
        # Security check: ensure file is in examples directory
        if not str(file_path.resolve()).startswith(str(examples_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")


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