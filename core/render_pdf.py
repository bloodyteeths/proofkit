"""
ProofKit PDF Report Generator

Generates professional inspector-ready proof certificates using ReportLab.
Creates deterministic PDF reports with PASS/FAIL banners, specification details,
results, charts, and verification QR codes for powder-coat cure validation.

Key features:
- Deterministic rendering with consistent fonts and layout
- Professional inspector-ready certificate format
- PASS/FAIL banner with color coding
- Integrated spec box, results box, and temperature chart
- QR code with verification hash
- Hash integrity for tamper detection

Example usage:
    from core.models import SpecV1, DecisionResult
    from core.render_pdf import generate_proof_pdf
    
    spec = SpecV1(**spec_data)
    decision = DecisionResult(**decision_data)
    
    pdf_bytes = generate_proof_pdf(
        spec=spec,
        decision=decision,
        plot_path="/path/to/plot.png",
        normalized_csv_path="/path/to/normalized.csv",
        verification_hash="abc123..."
    )
"""

import hashlib
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Dict, Any, Callable

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import PyPDF2
# M12 Compliance imports
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509 import load_pem_x509_certificate
    import rfc3161ng
    from lxml import etree
    PDF_COMPLIANCE_AVAILABLE = True
except ImportError:
    PDF_COMPLIANCE_AVAILABLE = False

from core.models import SpecV1, DecisionResult, Industry
from core.policy import should_block_if_no_tsa, should_enforce_pdf_a3
from core.timestamp import get_timestamp_with_retry, TimestampResult

# Initialize logger
logger = logging.getLogger(__name__)

# Constants for deterministic rendering
FONT_SIZE_TITLE = 18
FONT_SIZE_HEADER = 14
FONT_SIZE_BODY = 10
FONT_SIZE_SMALL = 8

# Color scheme for professional appearance
COLOR_PASS = colors.Color(0.2, 0.6, 0.2)  # Green
COLOR_FAIL = colors.Color(0.8, 0.2, 0.2)  # Red
COLOR_HEADER = colors.Color(0.1, 0.1, 0.1)  # Dark gray
COLOR_LIGHT_GRAY = colors.Color(0.9, 0.9, 0.9)  # Light gray background

# Industry-specific color palettes for plots (deterministic)
INDUSTRY_COLORS = {
    Industry.POWDER: {
        'primary': '#2E5BBA',  # Deep blue
        'secondary': '#8ECAE6',  # Light blue
        'accent': '#FFB300',  # Amber
        'target': '#219653',  # Green
        'threshold': '#D73502'  # Red-orange
    },
    Industry.HACCP: {
        'primary': '#7B2CBF',  # Purple
        'secondary': '#C77DFF',  # Light purple
        'accent': '#F72585',  # Pink
        'target': '#10451D',  # Dark green
        'threshold': '#E71D36'  # Red
    },
    Industry.AUTOCLAVE: {
        'primary': '#0077B6',  # Ocean blue
        'secondary': '#90E0EF',  # Sky blue
        'accent': '#00B4D8',  # Cyan
        'target': '#2D6A4F',  # Forest green
        'threshold': '#D00000'  # Pure red
    },
    Industry.STERILE: {
        'primary': '#06FFA5',  # Mint green
        'secondary': '#B7E4C7',  # Light green
        'accent': '#52B788',  # Medium green
        'target': '#2D6A4F',  # Dark green
        'threshold': '#BA1A1A'  # Dark red
    },
    Industry.CONCRETE: {
        'primary': '#6C757D',  # Gray
        'secondary': '#ADB5BD',  # Light gray
        'accent': '#FFC107',  # Yellow
        'target': '#198754',  # Success green
        'threshold': '#DC3545'  # Danger red
    },
    Industry.COLDCHAIN: {
        'primary': '#0D47A1',  # Deep blue
        'secondary': '#BBDEFB',  # Very light blue
        'accent': '#03DAC6',  # Teal
        'target': '#1B5E20',  # Dark green
        'threshold': '#B71C1C'  # Dark red
    }
}

# Default color palette
DEFAULT_COLORS = INDUSTRY_COLORS[Industry.POWDER]


def get_industry_colors(industry: Optional[Industry] = None) -> Dict[str, str]:
    """
    Get color palette for specified industry.
    
    Args:
        industry: Industry type for color selection
        
    Returns:
        Dictionary containing industry-specific colors
    """
    if industry and industry in INDUSTRY_COLORS:
        return INDUSTRY_COLORS[industry]
    return DEFAULT_COLORS

# PDF/A-3u compliance constants
PDF_A3_NAMESPACE = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'xmp': 'http://ns.adobe.com/xap/1.0/',
    'pdf': 'http://ns.adobe.com/pdf/1.3/',
    'pdfaid': 'http://www.aiim.org/pdfa/ns/id/',
    'pdfaExtension': 'http://www.aiim.org/pdfa/ns/extension/',
    'pdfaSchema': 'http://www.aiim.org/pdfa/ns/schema#',
    'pdfaProperty': 'http://www.aiim.org/pdfa/ns/property#'
}

# RFC 3161 TSA URLs (using public TSAs for demonstration)
RFC3161_TSA_URLS = [
    'http://timestamp.apple.com/ts01',
    'http://time.certum.pl',
    'http://timestamp.digicert.com'
]

# Page margins and layout constants
MARGIN_LEFT = 0.75 * inch
MARGIN_RIGHT = 0.75 * inch
MARGIN_TOP = 0.75 * inch
MARGIN_BOTTOM = 0.75 * inch
PAGE_WIDTH = letter[0]
PAGE_HEIGHT = letter[1]
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT


class PDFValidationError(Exception):
    """Raised when PDF validation fails and should block download."""
    pass


def check_pdf_validation_gates(decision: DecisionResult, 
                              enable_rfc3161: bool = True,
                              timestamp_available: bool = None) -> Dict[str, Any]:
    """
    Check PDF validation gates that may block download.
    
    Args:
        decision: Decision result containing status
        enable_rfc3161: Whether RFC 3161 timestamping is enabled
        timestamp_available: Whether timestamp was successfully generated (for testing)
        
    Returns:
        Dictionary with validation gate results
        
    Raises:
        PDFValidationError: If validation fails when blocking is enabled
    """
    # Use policy settings (default permissive)
    enforce_pdf_a3 = should_enforce_pdf_a3()
    block_if_no_tsa = should_block_if_no_tsa()
    
    # Determine if timestamp is available
    if timestamp_available is None:
        # Check if dependencies are available and RFC 3161 is enabled
        timestamp_available = PDF_COMPLIANCE_AVAILABLE and enable_rfc3161
    
    validation_result = {
        "pdf_a3_required": enforce_pdf_a3,
        "rfc3161_required": block_if_no_tsa,
        "pdf_a3_available": PDF_COMPLIANCE_AVAILABLE,
        "rfc3161_available": timestamp_available,
        "should_block": False,
        "blocking_reasons": [],
        "gate_status": "PASS"
    }
    
    # Check PDF/A-3 gate
    if enforce_pdf_a3 and not PDF_COMPLIANCE_AVAILABLE:
        validation_result["should_block"] = True
        validation_result["blocking_reasons"].append("PDF/A-3 compliance required but dependencies unavailable")
    
    # Check RFC 3161 gate
    if block_if_no_tsa and not timestamp_available:
        validation_result["should_block"] = True
        validation_result["blocking_reasons"].append("RFC 3161 timestamp required but TSA unavailable")
    
    # Set overall gate status
    if validation_result["should_block"]:
        validation_result["gate_status"] = "BLOCKED"
        
        # Raise exception if blocking is enabled
        error_msg = "PDF validation failed: " + "; ".join(validation_result["blocking_reasons"])
        raise PDFValidationError(error_msg)
    
    return validation_result


def _setup_fonts():
    """Set up fonts for consistent rendering across systems."""
    # Use built-in fonts for maximum compatibility
    # ReportLab built-in fonts are consistent across platforms
    pass  # Built-in fonts (Helvetica, Times-Roman, etc.) are already available


def _create_qr_code(data: str, size: int = 100) -> Image:
    """
    Create a QR code image for verification data.
    
    Args:
        data: String data to encode in QR code
        size: Size of QR code in points
        
    Returns:
        ReportLab Image object containing QR code
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create QR code image in memory
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to BytesIO for ReportLab
    img_buffer = BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    # Create ReportLab Image
    return Image(img_buffer, width=size, height=size)


def _create_banner(decision: DecisionResult) -> Paragraph:
    """
    Create the PASS/FAIL/INDETERMINATE banner at the top of the document.
    
    Args:
        decision: Decision result containing status
        
    Returns:
        ReportLab Paragraph with styled banner
    """
    # Use decision.status as the primary source of truth
    status_text = getattr(decision, 'status', 'PASS' if decision.pass_ else 'FAIL')
    
    # Set color based on status
    if status_text == 'INDETERMINATE':
        status_color = colors.orange
    elif status_text == 'PASS':
        status_color = COLOR_PASS
    else:  # FAIL
        status_color = COLOR_FAIL
    
    banner_style = ParagraphStyle(
        'Banner',
        parent=getSampleStyleSheet()['Normal'],
        fontSize=24,
        textColor=status_color,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        spaceAfter=20,
        borderWidth=2,
        borderColor=status_color,
        borderPadding=10,
        backColor=colors.Color(0.98, 0.98, 0.98)
    )
    
    return Paragraph(f"<b>{status_text}</b>", banner_style)


def _create_spec_box(spec: SpecV1) -> Table:
    """
    Create the specification details box.
    
    Args:
        spec: Specification data
        
    Returns:
        ReportLab Table with specification details
    """
    spec_data = [
        ['Specification Details', ''],
        ['Job ID', spec.job.job_id],
        ['Method', spec.spec.method.value],
        ['Target Temperature', f"{spec.spec.target_temp_C}°C"],
        ['Hold Time Required', f"{spec.spec.hold_time_s}s ({spec.spec.hold_time_s // 60}m {spec.spec.hold_time_s % 60}s)"],
        ['Sensor Uncertainty', f"±{spec.spec.sensor_uncertainty_C}°C"],
        ['Conservative Threshold', f"{spec.spec.target_temp_C + spec.spec.sensor_uncertainty_C}°C"],
    ]
    
    # Add optional fields if present
    if spec.data_requirements:
        spec_data.extend([
            ['Max Sample Period', f"{spec.data_requirements.max_sample_period_s}s"],
            ['Allowed Gaps', f"{spec.data_requirements.allowed_gaps_s}s"],
        ])
    
    if spec.logic:
        logic_type = "Continuous" if spec.logic.continuous else "Cumulative"
        spec_data.append(['Hold Logic', logic_type])
    
    spec_table = Table(spec_data, colWidths=[2.5*inch, 2*inch])
    spec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_HEADER),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('FONT', (0, 0), (1, 0), 'Helvetica-Bold', FONT_SIZE_HEADER),
        ('FONT', (0, 1), (1, -1), 'Helvetica', FONT_SIZE_BODY),
        ('BACKGROUND', (0, 1), (1, -1), COLOR_LIGHT_GRAY),
        ('GRID', (0, 0), (1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (1, -1), 8),
        ('RIGHTPADDING', (0, 0), (1, -1), 8),
        ('TOPPADDING', (0, 0), (1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (1, -1), 6),
    ]))
    
    return spec_table


def _create_results_box(decision: DecisionResult) -> Table:
    """
    Create the results details box.
    
    Args:
        decision: Decision result data
        
    Returns:
        ReportLab Table with results details
    """
    # Use decision.status as source of truth for display
    status = getattr(decision, 'status', 'PASS' if decision.pass_ else 'FAIL')
    
    results_data = [
        ['Results Summary', ''],
        ['Status', status],
        ['Actual Hold Time', f"{decision.actual_hold_time_s}s ({int(decision.actual_hold_time_s) // 60}m {int(decision.actual_hold_time_s) % 60}s)"],
        ['Required Hold Time', f"{decision.required_hold_time_s}s"],
        ['Max Temperature', f"{decision.max_temp_C:.1f}°C"],
        ['Min Temperature', f"{decision.min_temp_C:.1f}°C"],
        ['Conservative Threshold', f"{decision.conservative_threshold_C:.1f}°C"],
    ]
    
    # Add fallback note if used
    try:
        if getattr(decision, 'flags', {}).get('fallback_used'):
            results_data.append(['Note', 'Auto-detected sensors'])
    except Exception:
        pass
    
    # Show required vs present sensors for safety-critical processes  
    try:
        flags = getattr(decision, 'flags', {})
        if flags.get('required_sensors') and flags.get('present_sensors'):
            required_sensors = flags['required_sensors']
            present_sensors = flags['present_sensors']
            results_data.append(['Required Sensors', f"{len(present_sensors)}/{len(required_sensors)}"])
    except Exception:
        pass
    
    results_table = Table(results_data, colWidths=[2.5*inch, 2*inch])
    
    # Status row color based on status
    if status == 'INDETERMINATE':
        status_color = colors.orange
    elif status == 'PASS':
        status_color = COLOR_PASS
    else:  # FAIL
        status_color = COLOR_FAIL
    
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_HEADER),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('FONT', (0, 0), (1, 0), 'Helvetica-Bold', FONT_SIZE_HEADER),
        ('BACKGROUND', (0, 1), (1, 1), status_color),
        ('TEXTCOLOR', (0, 1), (1, 1), colors.white),
        ('FONT', (0, 1), (1, 1), 'Helvetica-Bold', FONT_SIZE_BODY),
        ('FONT', (0, 2), (1, -1), 'Helvetica', FONT_SIZE_BODY),
        ('BACKGROUND', (0, 2), (1, -1), COLOR_LIGHT_GRAY),
        ('GRID', (0, 0), (1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (1, -1), 8),
        ('RIGHTPADDING', (0, 0), (1, -1), 8),
        ('TOPPADDING', (0, 0), (1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (1, -1), 6),
    ]))
    
    return results_table


def _create_reasons_section(decision: DecisionResult) -> list:
    """
    Create the reasons and warnings section with INDETERMINATE notes.
    
    Args:
        decision: Decision result data
        
    Returns:
        List of ReportLab flowables for reasons section
    """
    elements = []
    
    # INDETERMINATE status note
    status = getattr(decision, 'status', 'PASS' if decision.pass_ else 'FAIL')
    if status == 'INDETERMINATE':
        # Determine the gate that caused INDETERMINATE status
        gate_reason = "sensor data quality"  # Default reason
        
        # Check for specific reasons in decision flags or reasons
        if hasattr(decision, 'flags') and decision.flags:
            flags = decision.flags
            if flags.get('missing_required_sensors'):
                gate_reason = "missing required sensors"
            elif flags.get('insufficient_data'):
                gate_reason = "insufficient data quality"
            elif flags.get('sensor_validation_failed'):
                gate_reason = "sensor validation failure"
        elif decision.reasons:
            if any('required' in reason.lower() and 'sensor' in reason.lower() for reason in decision.reasons):
                gate_reason = "missing required sensors"
            elif any('data quality' in reason.lower() for reason in decision.reasons):
                gate_reason = "data quality issues"
        
        indeterminate_style = ParagraphStyle(
            'IndeterminateNote',
            parent=getSampleStyleSheet()['Normal'],
            fontSize=FONT_SIZE_BODY,
            textColor=colors.orange,
            fontName='Helvetica-Bold',
            spaceAfter=12,
            spaceBefore=8,
            borderWidth=1,
            borderColor=colors.orange,
            borderPadding=8,
            backColor=colors.Color(1.0, 0.95, 0.85),  # Light orange background
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph(
            f"<b>⚠ VALIDATION NOTES</b><br/>Review required due to {gate_reason}",
            indeterminate_style
        ))
        elements.append(Spacer(1, 10))
    
    # Reasons section
    if decision.reasons:
        reasons_style = ParagraphStyle(
            'ReasonsHeader',
            parent=getSampleStyleSheet()['Heading2'],
            fontSize=FONT_SIZE_HEADER,
            textColor=COLOR_HEADER,
            fontName='Helvetica-Bold',
            spaceAfter=8
        )
        elements.append(Paragraph("Decision Reasons:", reasons_style))
        
        reason_style = ParagraphStyle(
            'Reason',
            parent=getSampleStyleSheet()['Normal'],
            fontSize=FONT_SIZE_BODY,
            leftIndent=20,
            bulletIndent=10,
            spaceAfter=4
        )
        
        for i, reason in enumerate(decision.reasons, 1):
            elements.append(Paragraph(f"{i}. {reason}", reason_style))
        
        elements.append(Spacer(1, 10))
    
    # Warnings section
    if decision.warnings:
        warnings_style = ParagraphStyle(
            'WarningsHeader',
            parent=getSampleStyleSheet()['Heading2'],
            fontSize=FONT_SIZE_HEADER,
            textColor=colors.Color(0.8, 0.5, 0.0),  # Orange
            fontName='Helvetica-Bold',
            spaceAfter=8
        )
        elements.append(Paragraph("Warnings:", warnings_style))
        
        warning_style = ParagraphStyle(
            'Warning',
            parent=getSampleStyleSheet()['Normal'],
            fontSize=FONT_SIZE_BODY,
            leftIndent=20,
            bulletIndent=10,
            spaceAfter=4,
            textColor=colors.Color(0.8, 0.5, 0.0)
        )
        
        for i, warning in enumerate(decision.warnings, 1):
            elements.append(Paragraph(f"{i}. {warning}", warning_style))
    
    return elements


def _create_verification_section(verification_hash: str, job_id: Optional[str] = None) -> list:
    """
    Create the verification section with hash and QR code.
    
    Args:
        verification_hash: Hash string for verification
        job_id: Optional job ID for creating verification URL
        
    Returns:
        List of ReportLab flowables for verification section
    """
    elements = []
    
    # Verification header
    verify_style = ParagraphStyle(
        'VerifyHeader',
        parent=getSampleStyleSheet()['Heading2'],
        fontSize=FONT_SIZE_HEADER,
        textColor=COLOR_HEADER,
        fontName='Helvetica-Bold',
        spaceAfter=8
    )
    elements.append(Paragraph("Verification", verify_style))
    
    # Create QR code with verification URL if job_id is available, otherwise use hash
    if job_id:
        # Use the first 10 characters of job_id for a shorter URL
        short_id = job_id[:10] if len(job_id) > 10 else job_id
        qr_data = f"https://www.proofkit.net/verify/{short_id}"
    else:
        qr_data = verification_hash
    
    qr_image = _create_qr_code(qr_data, size=80)
    
    # Create verification table with hash and QR code
    hash_display = f"{verification_hash[:16]}...{verification_hash[-16:]}" if len(verification_hash) > 40 else verification_hash
    
    # Add verification URL if job_id is available
    if job_id:
        short_id = job_id[:10] if len(job_id) > 10 else job_id
        verify_url = f"https://www.proofkit.net/verify/{short_id}"
        verify_data = [
            ['Verification Hash:', hash_display],
            ['Verification URL:', verify_url],
            ['QR Code:', ''],
        ]
    else:
        verify_data = [
            ['Verification Hash:', hash_display],
            ['QR Code:', ''],
        ]
    
    verify_table = Table(verify_data, colWidths=[1.5*inch, 3*inch])
    verify_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', FONT_SIZE_BODY),
        ('FONT', (1, 0), (1, -1), 'Courier', FONT_SIZE_SMALL),
        ('VALIGN', (0, 0), (1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (1, -1), 8),
        ('RIGHTPADDING', (0, 0), (1, -1), 8),
        ('TOPPADDING', (0, 0), (1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (1, -1), 6),
    ]))
    
    # Create a combined table with verification info and QR code
    combined_data = [
        [verify_table, qr_image]
    ]
    
    combined_table = Table(combined_data, colWidths=[4*inch, 1*inch])
    combined_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (1, 0), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    
    elements.append(combined_table)
    
    return elements


def _create_footer_info(now_provider: Optional[Callable[[], datetime]] = None, 
                       pdf_a3_available: bool = True,
                       rfc3161_available: bool = True,
                       timestamp_pending: bool = False) -> Paragraph:
    """
    Create footer information with timestamp and system info.
    
    Args:
        now_provider: Optional function to provide current datetime (for testing)
        pdf_a3_available: Whether PDF/A-3 compliance is available
        rfc3161_available: Whether RFC 3161 timestamping is available
        timestamp_pending: Whether TSA timestamp is pending
    
    Returns:
        ReportLab Paragraph with footer information
    """
    # Use deterministic timestamp formatting
    if now_provider:
        timestamp = now_provider().strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=getSampleStyleSheet()['Normal'],
        fontSize=FONT_SIZE_SMALL,
        textColor=colors.gray,
        alignment=TA_CENTER,
        spaceAfter=0
    )
    
    footer_parts = [f"Generated by ProofKit v1.0 | {timestamp} | Powder-Coat Cure Validation Certificate"]
    
    # Add notes for unavailable features and pending timestamps
    notes = []
    if not pdf_a3_available:
        notes.append("PDF/A-3 compliance unavailable")
    if not rfc3161_available:
        notes.append("RFC 3161 timestamping unavailable")
    elif timestamp_pending:
        notes.append("RFC 3161 timestamp pending - retry queued")
    
    if notes:
        footer_parts.append(f"Note: {', '.join(notes)}")
    
    footer_text = "<br/>".join(footer_parts)
    return Paragraph(footer_text, footer_style)


# M12 Compliance functions for PDF/A-3u and RFC 3161

def _get_rfc3161_timestamp(data: bytes) -> Optional[Dict[str, Any]]:
    """
    Get RFC 3161 timestamp for data.
    
    Args:
        data: Data to timestamp
        
    Returns:
        Dictionary with timestamp information or None if failed
    """
    try:
        if not PDF_COMPLIANCE_AVAILABLE:
            # logger.warning("RFC 3161 timestamping not available - missing dependencies") # Original code had this line commented out
            return None
        
        # Mock implementation for testing - in production this would call a real TSA
        import hashlib
        import time
        
        # Create a mock timestamp response
        timestamp_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signature": hashlib.sha256(data + str(time.time()).encode()).hexdigest(),
            "certificate": "mock_certificate_data_for_testing"
        }
        
        # logger.info(f"Generated RFC 3161 timestamp: {timestamp_data['timestamp']}") # Original code had this line commented out
        return timestamp_data
        
    except Exception as e:
        # logger.error(f"Failed to generate RFC 3161 timestamp: {e}") # Original code had this line commented out
        return None


def _generate_rfc3161_timestamp(data: bytes, timestamp_provider: Optional[Callable[[], bytes]] = None) -> Optional[bytes]:
    """
    Generate RFC 3161 timestamp for given data.
    
    Args:
        data: Data to timestamp
        timestamp_provider: Optional provider function for timestamp bytes (for testing)
        
    Returns:
        RFC 3161 timestamp token or None if unavailable
    """
    if not PDF_COMPLIANCE_AVAILABLE:
        return None
    
    # Use provided timestamp if available (for testing)
    if timestamp_provider:
        return timestamp_provider()
    
    try:
        # Calculate hash of data
        digest = hashes.Hash(hashes.SHA256())
        digest.update(data)
        data_hash = digest.finalize()
        
        # Try each TSA URL
        for tsa_url in RFC3161_TSA_URLS:
            try:
                # Create timestamp request
                rt = rfc3161ng.RemoteTimestamper(tsa_url, hashname='sha256')
                
                # Get timestamp
                timestamp = rt.timestamp(data=data_hash)
                return timestamp
                
            except Exception as e:
                # print(f"TSA {tsa_url} failed: {e}") # Original code had this line commented out
                continue
        
        return None
    except Exception as e:
        # print(f"RFC 3161 timestamp generation failed: {e}") # Original code had this line commented out
        return None


def _create_xmp_metadata(spec: SpecV1, decision: DecisionResult, 
                        timestamp_info: Optional[Dict[str, Any]] = None,
                        now_provider: Optional[Callable[[], datetime]] = None) -> str:
    """
    Create XMP metadata for PDF/A-3u compliance.
    
    Args:
        spec: Specification data
        decision: Decision result
        timestamp_info: Optional timestamp information
        now_provider: Optional function to provide current datetime (for testing)
        
    Returns:
        XMP metadata as XML string
    """
    if now_provider:
        timestamp = now_provider().strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Build XMP metadata
    rdf_root = etree.Element(
        "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF",
        nsmap=PDF_A3_NAMESPACE
    )
    
    # Document description
    description = etree.SubElement(
        rdf_root,
        "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description",
        attrib={
            "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about": ""
        }
    )
    
    # Dublin Core metadata
    dc_title = etree.SubElement(description, "{http://purl.org/dc/elements/1.1/}title")
    dc_title_alt = etree.SubElement(dc_title, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt")
    dc_title_li = etree.SubElement(dc_title_alt, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li")
    dc_title_li.set("{http://www.w3.org/XML/1998/namespace}lang", "x-default")
    dc_title_li.text = f"ProofKit Certificate - {spec.job.job_id}"
    
    dc_creator = etree.SubElement(description, "{http://purl.org/dc/elements/1.1/}creator")
    dc_creator_seq = etree.SubElement(dc_creator, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Seq")
    dc_creator_li = etree.SubElement(dc_creator_seq, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li")
    dc_creator_li.text = "ProofKit v1.0"
    
    dc_subject = etree.SubElement(description, "{http://purl.org/dc/elements/1.1/}subject")
    dc_subject_bag = etree.SubElement(dc_subject, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Bag")
    dc_subject_li = etree.SubElement(dc_subject_bag, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li")
    dc_subject_li.text = f"Temperature validation, {spec.spec.method}, {'PASS' if decision.pass_ else 'FAIL'}"
    
    # XMP metadata
    xmp_create_date = etree.SubElement(description, "{http://ns.adobe.com/xap/1.0/}CreateDate")
    xmp_create_date.text = timestamp
    
    xmp_modify_date = etree.SubElement(description, "{http://ns.adobe.com/xap/1.0/}ModifyDate")
    xmp_modify_date.text = timestamp
    
    xmp_creator_tool = etree.SubElement(description, "{http://ns.adobe.com/xap/1.0/}CreatorTool")
    xmp_creator_tool.text = "ProofKit v1.0 - Temperature Validation System"
    
    # PDF/A identification
    pdfaid_part = etree.SubElement(description, "{http://www.aiim.org/pdfa/ns/id/}part")
    pdfaid_part.text = "3"
    
    pdfaid_conformance = etree.SubElement(description, "{http://www.aiim.org/pdfa/ns/id/}conformance")
    pdfaid_conformance.text = "U"
    
    # Add timestamp information if available
    if timestamp_info:
        timestamp_desc = etree.SubElement(description, "{http://ns.adobe.com/xap/1.0/}timestampInfo")
        timestamp_desc.text = f"RFC 3161 timestamp: {timestamp_info.get('timestamp', 'N/A')}"
    
    # Convert to string
    xmp_str = etree.tostring(
        rdf_root,
        encoding='utf-8',
        xml_declaration=True,
        pretty_print=True
    ).decode('utf-8')
    
    # Wrap in XMP packet
    xmp_packet = f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
{xmp_str}
</x:xmpmeta>
<?xpacket end="w"?>'''
    
    return xmp_packet


def _add_file_attachment(pdf_writer, manifest_content: str, 
                        filename: str = "manifest.txt") -> None:
    """
    Add file attachment to PDF for PDF/A-3u compliance.
    
    Args:
        pdf_writer: PDF writer object
        manifest_content: Content of manifest file
        filename: Name of attached file
    """
    if not PDF_COMPLIANCE_AVAILABLE:
        return
    
    try:
        # Create file specification
        file_spec = PyPDF2.generic.DictionaryObject({
            PyPDF2.generic.NameObject("/Type"): PyPDF2.generic.NameObject("/Filespec"),
            PyPDF2.generic.NameObject("/F"): PyPDF2.generic.TextStringObject(filename),
            PyPDF2.generic.NameObject("/UF"): PyPDF2.generic.TextStringObject(filename),
            PyPDF2.generic.NameObject("/EF"): PyPDF2.generic.DictionaryObject({
                PyPDF2.generic.NameObject("/F"): PyPDF2.generic.IndirectObject(
                    len(pdf_writer._objects), 0, pdf_writer
                )
            })
        })
        
        # Create embedded file stream
        embedded_file = PyPDF2.generic.DecodedStreamObject.create_decoded_stream_object(
            PyPDF2.generic.DictionaryObject({
                PyPDF2.generic.NameObject("/Type"): PyPDF2.generic.NameObject("/EmbeddedFile"),
                PyPDF2.generic.NameObject("/Length"): PyPDF2.generic.NumberObject(len(manifest_content.encode('utf-8'))),
                PyPDF2.generic.NameObject("/Filter"): PyPDF2.generic.NameObject("/FlateDecode")
            }),
            manifest_content.encode('utf-8')
        )
        
        # Add to PDF
        pdf_writer._objects.append(embedded_file)
        file_spec[PyPDF2.generic.NameObject("/EF")][PyPDF2.generic.NameObject("/F")] = embedded_file.indirect_reference
        
        # Add file attachment annotation (simplified version)
        # In a full implementation, this would be added to a specific page
        
    except Exception as e:
        # print(f"Failed to add file attachment: {e}") # Original code had this line commented out
        pass


def _add_draft_watermark(pdf_path: str) -> None:
    """
    Add a DRAFT watermark to the PDF.
    
    Args:
        pdf_path: Path to the PDF file to watermark
    """
    try:
        # Read the PDF
        with open(pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            pdf_writer = PyPDF2.PdfWriter()
        
        # Add watermark to each page
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            
            # Create watermark text
            watermark_text = "DRAFT"
            
            # Create a new page with watermark
            page.merge_page(_create_watermark_page(page.mediabox, watermark_text))
            pdf_writer.add_page(page)
        
        # Write the watermarked PDF back to the same file
        with open(pdf_path, 'wb') as f:
            pdf_writer.write(f)
            
    except Exception as e:
        # If watermarking fails, log but don't fail the entire process
        # print(f"Warning: Failed to add DRAFT watermark: {e}") # Original code had this line commented out
        pass


def _create_watermark_page(mediabox, text: str) -> PyPDF2.PageObject:
    """
    Create a watermark page with the given text.
    
    Args:
        mediabox: Media box of the target page
        text: Text to display as watermark
        
    Returns:
        Watermark page object
    """
    # Create a new page with the same size
    watermark_page = PyPDF2.PageObject.create_blank_page(
        width=float(mediabox.width),
        height=float(mediabox.height)
    )
    
    # Create a content stream for the watermark
    content = f"""
    BT
    /F1 48 Tf
    0.8 0.8 0.8 rg
    0.5 g
    {float(mediabox.width) / 2} {float(mediabox.height) / 2} Td
    ({text}) Tj
    ET
    """
    
    # Add the content stream to the page
    watermark_page.merge_content_streams(content)
    
    return watermark_page


def _create_docusign_signature_page() -> list:
    """
    Create DocuSign signature page elements.
    
    Returns:
        List of ReportLab flowables for signature page
    """
    elements = []
    
    # Page break
    elements.append(PageBreak())
    
    # Title
    signature_title_style = ParagraphStyle(
        'SignatureTitle',
        parent=getSampleStyleSheet()['Title'],
        fontSize=FONT_SIZE_TITLE,
        textColor=COLOR_HEADER,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        spaceAfter=30
    )
    elements.append(Paragraph("Digital Signature Page", signature_title_style))
    
    # Instructions
    instruction_style = ParagraphStyle(
        'SignatureInstruction',
        parent=getSampleStyleSheet()['Normal'],
        fontSize=FONT_SIZE_BODY,
        spaceAfter=20,
        alignment=TA_LEFT
    )
    
    elements.append(Paragraph(
        "This document is prepared for digital signature via DocuSign. "
        "Please sign in the designated areas below to certify the authenticity "
        "and accuracy of this temperature validation certificate.",
        instruction_style
    ))
    
    # Signature fields table
    signature_data = [
        ['Signature Field', 'Role', 'Date'],
        ['Inspector Signature:', 'Quality Inspector', ''],
        ['Supervisor Signature:', 'Quality Supervisor', ''],
        ['Manager Signature:', 'Quality Manager', '']
    ]
    
    signature_table = Table(signature_data, colWidths=[3*inch, 2*inch, 2*inch])
    signature_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (2, 0), COLOR_HEADER),
        ('TEXTCOLOR', (0, 0), (2, 0), colors.white),
        ('FONT', (0, 0), (2, 0), 'Helvetica-Bold', FONT_SIZE_HEADER),
        ('FONT', (0, 1), (2, -1), 'Helvetica', FONT_SIZE_BODY),
        ('BACKGROUND', (0, 1), (2, -1), COLOR_LIGHT_GRAY),
        ('GRID', (0, 0), (2, -1), 1, colors.black),
        ('VALIGN', (0, 0), (2, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (2, -1), 8),
        ('RIGHTPADDING', (0, 0), (2, -1), 8),
        ('TOPPADDING', (0, 0), (2, -1), 15),
        ('BOTTOMPADDING', (0, 0), (2, -1), 15),
    ]))
    
    elements.append(signature_table)
    elements.append(Spacer(1, 30))
    
    # DocuSign notice
    docusign_style = ParagraphStyle(
        'DocuSignNotice',
        parent=getSampleStyleSheet()['Normal'],
        fontSize=FONT_SIZE_SMALL,
        textColor=colors.gray,
        alignment=TA_CENTER,
        spaceAfter=0
    )
    elements.append(Paragraph(
        "This document will be electronically signed using DocuSign. "
        "Digital signatures provide the same legal validity as handwritten signatures.",
        docusign_style
    ))
    
    return elements


def _get_template_config(user_plan: str) -> Dict[str, Any]:
    """
    Get template configuration based on user plan.
    
    Args:
        user_plan: User's pricing plan (free, starter, pro, business, enterprise)
        
    Returns:
        Dictionary with template configuration
        
    Example:
        >>> config = _get_template_config('pro')
        >>> print(config['watermark'])
        None
    """
    configs = {
        'free': {
            'watermark': 'NOT FOR PRODUCTION USE',
            'watermark_color': colors.Color(0.8, 0.8, 0.8),
            'show_branding': True,
            'allow_logo': False,
            'header_strip': False,
            'template_name': 'Free Trial'
        },
        'starter': {
            'watermark': None,
            'watermark_color': None,
            'show_branding': True,
            'allow_logo': False,
            'header_strip': False,
            'template_name': 'Standard'
        },
        'pro': {
            'watermark': None,
            'watermark_color': None,
            'show_branding': True,
            'allow_logo': True,
            'header_strip': False,
            'template_name': 'Professional'
        },
        'business': {
            'watermark': None,
            'watermark_color': None,
            'show_branding': True,
            'allow_logo': True,
            'header_strip': True,
            'template_name': 'Business'
        },
        'enterprise': {
            'watermark': None,
            'watermark_color': None,
            'show_branding': False,
            'allow_logo': True,
            'header_strip': True,
            'template_name': 'Enterprise'
        }
    }
    
    return configs.get(user_plan, configs['free'])


def _create_watermark_elements(config: Dict[str, Any]) -> list:
    """
    Create watermark elements based on template configuration.
    
    Args:
        config: Template configuration dictionary
        
    Returns:
        List of ReportLab elements for watermark
    """
    elements = []
    
    if config.get('watermark'):
        watermark_style = ParagraphStyle(
            'Watermark',
            parent=getSampleStyleSheet()['Normal'],
            fontSize=14,
            textColor=config.get('watermark_color', colors.Color(0.8, 0.8, 0.8)),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            spaceBefore=10,
            spaceAfter=10,
            borderWidth=1,
            borderColor=config.get('watermark_color', colors.Color(0.8, 0.8, 0.8)),
            borderPadding=5,
            backColor=colors.Color(0.98, 0.98, 0.98)
        )
        elements.append(Paragraph(config['watermark'], watermark_style))
        elements.append(Spacer(1, 10))
    
    return elements


def _create_header_with_logo(title_text: str, config: Dict[str, Any], 
                           customer_logo_path: Optional[str] = None) -> list:
    """
    Create header section with optional customer logo.
    
    Args:
        title_text: Main title text
        config: Template configuration
        customer_logo_path: Optional path to customer logo
        
    Returns:
        List of ReportLab elements for header
    """
    elements = []
    
    # Business+ plans get header strip
    if config.get('header_strip'):
        header_strip_style = ParagraphStyle(
            'HeaderStrip',
            parent=getSampleStyleSheet()['Normal'],
            fontSize=8,
            textColor=colors.white,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            backColor=COLOR_HEADER
        )
        elements.append(Paragraph(f"Generated with ProofKit {config['template_name']} • Secure Certificate Validation", header_strip_style))
        elements.append(Spacer(1, 10))
    
    # Create title with logo if available and allowed
    if config.get('allow_logo') and customer_logo_path and os.path.exists(customer_logo_path):
        try:
            # Create table with logo and title
            logo_img = Image(customer_logo_path, width=1*inch, height=0.5*inch)
            
            title_style = ParagraphStyle(
                'TitleWithLogo',
                parent=getSampleStyleSheet()['Title'],
                fontSize=FONT_SIZE_TITLE,
                textColor=COLOR_HEADER,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                spaceAfter=20
            )
            title_para = Paragraph(title_text, title_style)
            
            header_data = [[logo_img, title_para]]
            header_table = Table(header_data, colWidths=[1.5*inch, 6.5*inch])
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (1, 0), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (1, 0), 0),
                ('RIGHTPADDING', (0, 0), (1, 0), 0),
            ]))
            elements.append(header_table)
            
        except Exception as e:
            # Fallback to text-only title if logo fails
            title_style = ParagraphStyle(
                'Title',
                parent=getSampleStyleSheet()['Title'],
                fontSize=FONT_SIZE_TITLE,
                textColor=COLOR_HEADER,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                spaceAfter=20
            )
            elements.append(Paragraph(title_text, title_style))
    else:
        # Standard text title
        title_style = ParagraphStyle(
            'Title',
            parent=getSampleStyleSheet()['Title'],
            fontSize=FONT_SIZE_TITLE,
            textColor=COLOR_HEADER,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            spaceAfter=20
        )
        elements.append(Paragraph(title_text, title_style))
    
    return elements


def _create_footer_with_branding(config: Dict[str, Any], 
                                now_provider: Optional[Callable[[], datetime]] = None,
                                pdf_a3_available: bool = True,
                                rfc3161_available: bool = True,
                                timestamp_pending: bool = False) -> list:
    """
    Create footer with conditional branding.
    
    Args:
        config: Template configuration
        now_provider: Optional function to provide current datetime
        pdf_a3_available: Whether PDF/A-3 compliance is available
        rfc3161_available: Whether RFC 3161 timestamping is available
        timestamp_pending: Whether TSA timestamp is pending
        
    Returns:
        List of ReportLab elements for footer
    """
    elements = []
    
    # Standard footer info
    if now_provider:
        timestamp = now_provider().strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    footer_lines = [
        f"Generated: {timestamp}",
        "This certificate provides cryptographic proof of temperature validation compliance."
    ]
    
    # Add branding for non-enterprise plans
    if config.get('show_branding', True):
        footer_lines.append("Powered by ProofKit • www.proofkit.net • Secure Temperature Validation")
    
    # Add availability notes in small gray text
    notes = []
    if not pdf_a3_available:
        notes.append("PDF/A-3 compliance unavailable")
    if not rfc3161_available:
        notes.append("RFC 3161 timestamping unavailable")
    elif timestamp_pending:
        notes.append("RFC 3161 timestamp pending - retry queued")
    
    if notes:
        footer_lines.append(f"Note: {', '.join(notes)}")
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=getSampleStyleSheet()['Normal'],
        fontSize=FONT_SIZE_SMALL,
        textColor=colors.Color(0.4, 0.4, 0.4),
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    for line in footer_lines:
        elements.append(Paragraph(line, footer_style))
        elements.append(Spacer(1, 3))
    
    return elements


def generate_proof_pdf(
    spec: SpecV1,
    decision: DecisionResult,
    plot_path: Union[str, Path],
    normalized_csv_path: Optional[Union[str, Path]] = None,
    verification_hash: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
    manifest_content: Optional[str] = None,
    enable_rfc3161: bool = True,
    esign_page: bool = False,
    industry: Optional[Industry] = None,
    is_draft: bool = False,
    include_rfc3161: bool = True,
    timestamp_provider: Optional[Callable[[], bytes]] = None,
    now_provider: Optional[Callable[[], datetime]] = None,
    user_plan: Optional[str] = None,
    customer_logo_path: Optional[str] = None,
    check_validation_gates: bool = True
) -> bytes:
    """
    Generate a professional proof certificate PDF with M12 compliance features.
    
    Args:
        spec: Specification data
        decision: Decision result data
        plot_path: Path to the temperature plot image
        normalized_csv_path: Optional path to normalized CSV data
        verification_hash: Optional verification hash for QR code
        output_path: Optional output file path (if None, returns bytes)
        manifest_content: Optional manifest content for PDF/A-3u embedding
        enable_rfc3161: Whether to generate RFC 3161 timestamps
        esign_page: Whether to include DocuSign signature page
        industry: Industry type for color palette selection
        is_draft: Whether to add DRAFT watermark (default: True)
        timestamp_provider: Optional provider function for timestamp bytes (for testing)
        now_provider: Optional function to provide current datetime (for testing)
        user_plan: Optional user plan for template selection (free, starter, pro, business, enterprise)
        customer_logo_path: Optional path to customer logo for pro+ plans
        check_validation_gates: Whether to check PDF validation gates (default: True)
        
    Returns:
        PDF content as bytes (PDF/A-3u compliant with RFC 3161 timestamps)
        
    Raises:
        FileNotFoundError: If plot image file is not found
        ValueError: If required data is invalid
        PDFValidationError: If PDF validation gates fail and blocking is enabled
    """
    # Check PDF validation gates if enabled
    if check_validation_gates:
        try:
            validation_result = check_pdf_validation_gates(
                decision=decision,
                enable_rfc3161=enable_rfc3161,
                timestamp_available=None  # Will be determined automatically
            )
            # Log validation result for debugging
            logger.debug(f"PDF validation gates result: {validation_result}")
        except PDFValidationError as e:
            logger.error(f"PDF validation blocked: {e}")
            # Re-raise to block PDF generation
            raise
    
    # Validate inputs
    if not os.path.exists(plot_path):
        raise FileNotFoundError(f"Plot image not found: {plot_path}")
    
    if normalized_csv_path and not os.path.exists(normalized_csv_path):
        raise FileNotFoundError(f"Normalized CSV not found: {normalized_csv_path}")
    
    # Generate verification hash if not provided
    if verification_hash is None:
        hash_data = f"{spec.job.job_id}{decision.pass_}{decision.actual_hold_time_s}"
        verification_hash = hashlib.sha256(hash_data.encode()).hexdigest()
    
    # Route to appropriate certificate renderer based on user plan
    plan = user_plan or 'free'
    
    # Use the premium certificate templates based on plan
    if plan in ['business', 'enterprise', 'premium']:
        # Use premium certificate template
        from core.render_certificate_premium import generate_premium_certificate
        return generate_premium_certificate(
            spec=spec,
            decision=decision,
            plot_path=plot_path,
            certificate_no=spec.job.job_id,
            verification_hash=verification_hash,
            output_path=output_path,
            timestamp=now_provider() if now_provider else None
        )
    elif plan in ['pro', 'professional']:
        # Use pro certificate template
        from core.render_certificate_pro import generate_certificate_pdf as generate_pro_certificate
        return generate_pro_certificate(
            spec=spec,
            decision=decision,
            plot_path=plot_path,
            certificate_no=spec.job.job_id,
            verification_hash=verification_hash,
            output_path=output_path,
            timestamp=now_provider() if now_provider else None
        )
    elif plan in ['starter', 'basic']:
        # Use basic certificate template without graph for starter
        from core.render_certificate import generate_certificate_pdf as generate_basic_certificate
        return generate_basic_certificate(
            spec=spec,
            decision=decision,
            plot_path=plot_path,
            verification_hash=verification_hash,
            output_path=output_path,
            timestamp=now_provider() if now_provider else None,
            include_graph=False  # Starter tier doesn't get the temperature graph
        )
    else:
        # Free plan - use basic certificate with graph but with watermark
        from core.render_certificate import generate_certificate_pdf as generate_basic_certificate
        return generate_basic_certificate(
            spec=spec,
            decision=decision,
            plot_path=plot_path,
            verification_hash=verification_hash,
            output_path=output_path,
            timestamp=now_provider() if now_provider else None,
            include_graph=True  # Free tier gets graph but with watermark
        )
    
    # Old implementation below (kept for reference, but not executed)
    # Determine template configuration based on user plan
    template_config = _get_template_config(user_plan or 'free')
    
    # Set up fonts
    _setup_fonts()
    
    # Determine industry for title customization
    if industry is None:
        industry = Industry.POWDER  # Default
    
    # Create initial PDF with ReportLab
    temp_pdf_path = None
    try:
        # Create temporary file for initial PDF
        temp_fd, temp_pdf_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_fd)
        
        # Create PDF document
        doc = SimpleDocTemplate(
            temp_pdf_path,
            pagesize=letter,
            rightMargin=MARGIN_RIGHT,
            leftMargin=MARGIN_LEFT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=f"ProofKit Certificate - {spec.job.job_id}"
        )
        
        # Build document content
        elements = []
        
        # Add watermark for free tier
        watermark_elements = _create_watermark_elements(template_config)
        elements.extend(watermark_elements)
        
        # Dynamic title based on industry
        industry_titles = {
            Industry.POWDER: "Powder-Coat Cure Validation Certificate",
            Industry.HACCP: "HACCP Temperature Validation Certificate", 
            Industry.AUTOCLAVE: "Autoclave Sterilization Validation Certificate",
            Industry.STERILE: "Sterile Processing Validation Certificate",
            Industry.CONCRETE: "Concrete Curing Validation Certificate",
            Industry.COLDCHAIN: "Cold Chain Storage Validation Certificate"
        }
        
        title_text = industry_titles.get(industry, "Temperature Validation Certificate")
        
        # Create header with template-specific features
        header_elements = _create_header_with_logo(title_text, template_config, customer_logo_path)
        elements.extend(header_elements)
        
        # PASS/FAIL Banner
        elements.append(_create_banner(decision))
        elements.append(Spacer(1, 15))
        
        # Two-column layout for spec and results boxes
        spec_box = _create_spec_box(spec)
        results_box = _create_results_box(decision)
        
        # Create table to hold both boxes side by side
        boxes_data = [[spec_box, results_box]]
        boxes_table = Table(boxes_data, colWidths=[4.5*inch, 4.5*inch])
        boxes_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (1, 0), 'TOP'),
            ('LEFTPADDING', (0, 0), (1, 0), 0),
            ('RIGHTPADDING', (0, 0), (1, 0), 0),
        ]))
        
        elements.append(boxes_table)
        elements.append(Spacer(1, 20))
        
        # Temperature chart
        chart_style = ParagraphStyle(
            'ChartHeader',
            parent=getSampleStyleSheet()['Heading2'],
            fontSize=FONT_SIZE_HEADER,
            textColor=COLOR_HEADER,
            fontName='Helvetica-Bold',
            spaceAfter=8,
            alignment=TA_CENTER
        )
        elements.append(Paragraph("Temperature Profile", chart_style))
        
        # Add plot image
        try:
            plot_image = Image(str(plot_path), width=6*inch, height=4*inch)
            plot_image.hAlign = 'CENTER'
            elements.append(plot_image)
        except Exception as e:
            # Fallback if image cannot be loaded
            error_style = ParagraphStyle(
                'Error',
                parent=getSampleStyleSheet()['Normal'],
                fontSize=FONT_SIZE_BODY,
                textColor=colors.red,
                alignment=TA_CENTER
            )
            elements.append(Paragraph(f"Error loading chart: {str(e)}", error_style))
        
        elements.append(Spacer(1, 20))
        
        # Reasons and warnings section
        reasons_elements = _create_reasons_section(decision)
        if reasons_elements:
            elements.extend(reasons_elements)
            elements.append(Spacer(1, 15))
        
        # Verification section
        verify_elements = _create_verification_section(verification_hash, spec.job.job_id)
        elements.extend(verify_elements)
        
        # Add DocuSign signature page if requested
        if esign_page:
            signature_elements = _create_docusign_signature_page()
            elements.extend(signature_elements)
        
        # Footer with template-specific branding and availability notes (placeholder for timestamp pending)
        elements.append(Spacer(1, 30))
        footer_elements = _create_footer_with_branding(
            template_config, 
            now_provider, 
            pdf_a3_available=PDF_COMPLIANCE_AVAILABLE,
            rfc3161_available=enable_rfc3161 and PDF_COMPLIANCE_AVAILABLE,
            timestamp_pending=False  # Will be updated after PDF enhancement
        )
        elements.extend(footer_elements)
        
        # Build initial PDF
        doc.build(elements)
        
        # Add DRAFT watermark only if explicitly requested
        if is_draft:
            _add_draft_watermark(temp_pdf_path)
        
        # If PDF compliance is not available, return basic PDF
        if not PDF_COMPLIANCE_AVAILABLE:
            with open(temp_pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            
            if output_path:
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)
            
            return pdf_bytes
        
        # Enhance PDF with PDF/A-3u compliance and RFC 3161 timestamps
        enhanced_pdf, timestamp_pending = _enhance_pdf_compliance(
            temp_pdf_path, spec, decision, verification_hash,
            manifest_content, include_rfc3161, output_path,
            timestamp_provider, now_provider
        )
        
        # Note: In a more sophisticated implementation, we could regenerate the footer
        # with the correct timestamp_pending flag, but for now we accept the minor
        # discrepancy that the footer shows generic availability rather than per-job status
        
        return enhanced_pdf
        
    finally:
        # Clean up temporary file
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.unlink(temp_pdf_path)
            except:
                pass


def _enhance_pdf_compliance(temp_pdf_path: str, spec: SpecV1, decision: DecisionResult,
                          verification_hash: str, manifest_content: Optional[str],
                          include_rfc3161: bool, output_path: Optional[Union[str, Path]],
                          timestamp_provider: Optional[Callable[[], bytes]] = None,
                          now_provider: Optional[Callable[[], datetime]] = None) -> tuple[bytes, bool]:
    """
    Enhance PDF with PDF/A-3u compliance and RFC 3161 timestamps.
    
    Args:
        temp_pdf_path: Path to temporary PDF file
        spec: Specification data
        decision: Decision result
        verification_hash: Verification hash
        manifest_content: Optional manifest content to embed
        include_rfc3161: Whether to add RFC 3161 timestamps
        output_path: Optional output path
        timestamp_provider: Optional provider function for timestamp bytes (for testing)
        now_provider: Optional function to provide current datetime (for testing)
        
    Returns:
        Tuple of (Enhanced PDF bytes, timestamp_pending flag)
    """
    try:
        # Read original PDF content first for RFC 3161 timestamping
        with open(temp_pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        # Read original PDF for processing
        with open(temp_pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            pdf_writer = PyPDF2.PdfWriter()
            
            # Copy all pages
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                pdf_writer.add_page(page)
            
            # Generate RFC 3161 timestamp if enabled using resilient implementation
            timestamp_info = None
            timestamp_pending = False
            
            if include_rfc3161:
                # Use testing provider if available, otherwise use resilient implementation
                if timestamp_provider:
                    rfc3161_token = timestamp_provider()
                    if rfc3161_token:
                        if now_provider:
                            ts = now_provider().isoformat()
                        else:
                            ts = datetime.now(timezone.utc).isoformat()
                        timestamp_info = {
                            'timestamp': ts,
                            'token': rfc3161_token.hex(),
                            'token_length': len(rfc3161_token),
                            'tsa_status': 'success'
                        }
                else:
                    # Use resilient timestamp implementation
                    timestamp_result = get_timestamp_with_retry(
                        pdf_content=pdf_content,
                        job_id=spec.job.job_id,
                        pdf_path=str(output_path) if output_path else temp_pdf_path,
                        now_provider=now_provider
                    )
                    
                    if timestamp_result.timestamp_info:
                        timestamp_info = timestamp_result.timestamp_info
                    
                    timestamp_pending = timestamp_result.pending
            
            # Create XMP metadata for PDF/A-3u
            xmp_metadata = _create_xmp_metadata(spec, decision, timestamp_info, now_provider)
            pdf_writer.add_metadata({
                '/Title': f'ProofKit Certificate - {spec.job.job_id}',
                '/Author': 'ProofKit v1.0',
                '/Subject': f'Temperature validation certificate - {"PASS" if decision.pass_ else "FAIL"}',
                '/Creator': 'ProofKit v1.0 - Temperature Validation System',
                '/Producer': 'ReportLab + PyPDF2 (PDF/A-3u compliant)',
                '/CreationDate': f"D:{(now_provider() if now_provider else datetime.now(timezone.utc)).strftime('%Y%m%d%H%M%S')}Z",
                '/ModDate': f"D:{(now_provider() if now_provider else datetime.now(timezone.utc)).strftime('%Y%m%d%H%M%S')}Z"
            })
            
            # Add XMP metadata stream
            xmp_stream = PyPDF2.generic.DecodedStreamObject.create_decoded_stream_object(
                PyPDF2.generic.DictionaryObject({
                    PyPDF2.generic.NameObject("/Type"): PyPDF2.generic.NameObject("/Metadata"),
                    PyPDF2.generic.NameObject("/Subtype"): PyPDF2.generic.NameObject("/XML"),
                    PyPDF2.generic.NameObject("/Length"): PyPDF2.generic.NumberObject(len(xmp_metadata.encode('utf-8')))
                }),
                xmp_metadata.encode('utf-8')
            )
            
            # Add manifest as file attachment if provided
            if manifest_content:
                _add_file_attachment(pdf_writer, manifest_content, "manifest.txt")
            
            # Write enhanced PDF
            if output_path:
                final_output_path = str(output_path)
            else:
                temp_fd, final_output_path = tempfile.mkstemp(suffix='.pdf')
                os.close(temp_fd)
            
            try:
                with open(final_output_path, 'wb') as output_file:
                    pdf_writer.write(output_file)
                
                # Read final PDF bytes
                with open(final_output_path, 'rb') as f:
                    final_pdf_bytes = f.read()
                
                return final_pdf_bytes, timestamp_pending
                
            finally:
                if not output_path and os.path.exists(final_output_path):
                    try:
                        os.unlink(final_output_path)
                    except:
                        pass
                        
    except Exception as e:
        # print(f"PDF compliance enhancement failed: {e}") # Original code had this line commented out
        # Fallback to basic PDF
        with open(temp_pdf_path, 'rb') as f:
            basic_pdf = f.read()
            
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(basic_pdf)
                
        return basic_pdf, False  # No timestamp pending for fallback


def compute_pdf_hash(pdf_bytes: bytes) -> str:
    """
    Compute SHA-256 hash of PDF content for integrity verification.
    
    Args:
        pdf_bytes: PDF content as bytes
        
    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(pdf_bytes).hexdigest()


# Usage example in comments:
"""
Example usage:

from core.models import SpecV1, DecisionResult
from core.render_pdf import generate_proof_pdf
import json

# Load spec and decision data
with open('spec.json', 'r') as f:
    spec_data = json.load(f)
with open('decision.json', 'r') as f:
    decision_data = json.load(f)

spec = SpecV1(**spec_data)
decision = DecisionResult(**decision_data)

# Generate PDF
pdf_bytes = generate_proof_pdf(
    spec=spec,
    decision=decision,
    plot_path="plot.png",
    normalized_csv_path="normalized.csv",
    verification_hash="abc123...",
    output_path="proof.pdf"
)

print(f"Generated PDF: {len(pdf_bytes)} bytes")
"""