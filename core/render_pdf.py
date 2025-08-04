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
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

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

from core.models import SpecV1, DecisionResult


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

# Page margins and layout constants
MARGIN_LEFT = 0.75 * inch
MARGIN_RIGHT = 0.75 * inch
MARGIN_TOP = 0.75 * inch
MARGIN_BOTTOM = 0.75 * inch
PAGE_WIDTH = letter[0]
PAGE_HEIGHT = letter[1]
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT


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
    Create the PASS/FAIL banner at the top of the document.
    
    Args:
        decision: Decision result containing pass/fail status
        
    Returns:
        ReportLab Paragraph with styled banner
    """
    status_text = "PASS" if decision.pass_ else "FAIL"
    status_color = COLOR_PASS if decision.pass_ else COLOR_FAIL
    
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
    results_data = [
        ['Results Summary', ''],
        ['Status', 'PASS' if decision.pass_ else 'FAIL'],
        ['Actual Hold Time', f"{decision.actual_hold_time_s}s ({int(decision.actual_hold_time_s) // 60}m {int(decision.actual_hold_time_s) % 60}s)"],
        ['Required Hold Time', f"{decision.required_hold_time_s}s"],
        ['Max Temperature', f"{decision.max_temp_C:.1f}°C"],
        ['Min Temperature', f"{decision.min_temp_C:.1f}°C"],
        ['Conservative Threshold', f"{decision.conservative_threshold_C:.1f}°C"],
    ]
    
    results_table = Table(results_data, colWidths=[2.5*inch, 2*inch])
    
    # Status row color based on pass/fail
    status_color = COLOR_PASS if decision.pass_ else COLOR_FAIL
    
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
    Create the reasons and warnings section.
    
    Args:
        decision: Decision result data
        
    Returns:
        List of ReportLab flowables for reasons section
    """
    elements = []
    
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


def _create_verification_section(verification_hash: str) -> list:
    """
    Create the verification section with hash and QR code.
    
    Args:
        verification_hash: Hash string for verification
        
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
    
    # Create QR code
    qr_image = _create_qr_code(verification_hash, size=80)
    
    # Create verification table with hash and QR code
    hash_display = f"{verification_hash[:16]}...{verification_hash[-16:]}" if len(verification_hash) > 40 else verification_hash
    
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


def _create_footer_info() -> Paragraph:
    """
    Create footer information with timestamp and system info.
    
    Returns:
        ReportLab Paragraph with footer information
    """
    # Use deterministic timestamp formatting
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=getSampleStyleSheet()['Normal'],
        fontSize=FONT_SIZE_SMALL,
        textColor=colors.gray,
        alignment=TA_CENTER,
        spaceAfter=0
    )
    
    footer_text = f"Generated by ProofKit v1.0 | {timestamp} | Powder-Coat Cure Validation Certificate"
    return Paragraph(footer_text, footer_style)


def generate_proof_pdf(
    spec: SpecV1,
    decision: DecisionResult,
    plot_path: Union[str, Path],
    normalized_csv_path: Optional[Union[str, Path]] = None,
    verification_hash: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None
) -> bytes:
    """
    Generate a professional proof certificate PDF.
    
    Args:
        spec: Specification data
        decision: Decision result data
        plot_path: Path to the temperature plot image
        normalized_csv_path: Optional path to normalized CSV data
        verification_hash: Optional verification hash for QR code
        output_path: Optional output file path (if None, returns bytes)
        
    Returns:
        PDF content as bytes
        
    Raises:
        FileNotFoundError: If plot image file is not found
        ValueError: If required data is invalid
    """
    # Validate inputs
    if not os.path.exists(plot_path):
        raise FileNotFoundError(f"Plot image not found: {plot_path}")
    
    if normalized_csv_path and not os.path.exists(normalized_csv_path):
        raise FileNotFoundError(f"Normalized CSV not found: {normalized_csv_path}")
    
    # Generate verification hash if not provided
    if verification_hash is None:
        hash_data = f"{spec.job.job_id}{decision.pass_}{decision.actual_hold_time_s}"
        verification_hash = hashlib.sha256(hash_data.encode()).hexdigest()
    
    # Set up fonts
    _setup_fonts()
    
    # Create PDF buffer or file
    if output_path:
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=MARGIN_RIGHT,
            leftMargin=MARGIN_LEFT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=f"ProofKit Certificate - {spec.job.job_id}"
        )
        buffer = None
    else:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=MARGIN_RIGHT,
            leftMargin=MARGIN_LEFT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=f"ProofKit Certificate - {spec.job.job_id}"
        )
    
    # Build document content
    elements = []
    
    # Title
    title_style = ParagraphStyle(
        'Title',
        parent=getSampleStyleSheet()['Title'],
        fontSize=FONT_SIZE_TITLE,
        textColor=COLOR_HEADER,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        spaceAfter=20
    )
    elements.append(Paragraph("Powder-Coat Cure Validation Certificate", title_style))
    
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
    verify_elements = _create_verification_section(verification_hash)
    elements.extend(verify_elements)
    
    # Footer
    elements.append(Spacer(1, 30))
    elements.append(_create_footer_info())
    
    # Build PDF
    doc.build(elements)
    
    # Return bytes if no output path specified
    if buffer:
        buffer.seek(0)
        return buffer.getvalue()
    else:
        # Read the file and return bytes
        with open(output_path, 'rb') as f:
            return f.read()


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