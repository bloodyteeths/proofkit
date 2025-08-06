"""
ProofKit ISO-Style Certificate Generator

Creates professional single-page A4 certificates with ISO-9001 calibration lab aesthetics.
Features watermarks, security lines, signature fields, and two-column layout.

Example usage:
    from core.models import SpecV1, DecisionResult
    from core.render_certificate import generate_certificate_pdf
    
    pdf_bytes = generate_certificate_pdf(spec, decision, plot_path, verification_hash)
"""

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Dict, Any

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, KeepTogether, Frame, PageTemplate, BaseDocTemplate
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics import renderPDF

from core.models import SpecV1, DecisionResult

# A4 dimensions and layout constants
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm
SAFE_WIDTH = PAGE_WIDTH - (2 * MARGIN)
SAFE_HEIGHT = PAGE_HEIGHT - (2 * MARGIN)

# Professional color palette
COLOR_NAVY = colors.HexColor("#102A43")           # Deep navy for headers
COLOR_SLATE = colors.HexColor("#334E68")          # Slate grey for body text
COLOR_CRIMSON = colors.HexColor("#C1292E")        # Crimson for FAIL
COLOR_EMERALD = colors.HexColor("#2E7D32")        # Emerald for PASS
COLOR_LIGHT_GREY = colors.HexColor("#F7F9FC")     # Very light grey for backgrounds
COLOR_MID_GREY = colors.HexColor("#9FB3C8")       # Mid grey for borders
COLOR_MICRO_TEXT = colors.HexColor("#E4E7EB")     # Very light for watermarks

# Micro-text for security borders
MICRO_TEXT = "AUTHENTICITY GUARANTEED BY PROOFKIT SECURE RENDER ENGINE · "


def register_fonts():
    """Register custom fonts for professional appearance."""
    # Using built-in fonts but aliasing for consistency
    # In production, you'd register actual EB Garamond and Inter fonts
    pass


def _draw_micro_text(c, y):
    """Draw horizontal micro-text security border."""
    c.setFont("Helvetica", 6)
    c.setFillColor(COLOR_SLATE, alpha=0.3)
    c.drawString(MARGIN, y, (MICRO_TEXT * 8)[:int((PAGE_WIDTH - 2*MARGIN)/mm * 2)])


def create_watermark_canvas(canvas_obj, doc):
    """
    Add security features and micro-text borders to each page.
    
    Args:
        canvas_obj: ReportLab canvas object
        doc: Document template
    """
    canvas_obj.saveState()
    
    # Add borders
    canvas_obj.setStrokeColor(COLOR_NAVY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN, PAGE_HEIGHT - MARGIN, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN)
    canvas_obj.line(MARGIN, MARGIN, PAGE_WIDTH - MARGIN, MARGIN)
    
    # Add micro-text security borders (top and bottom only)
    _draw_micro_text(canvas_obj, PAGE_HEIGHT - MARGIN + 1*mm)  # Top
    _draw_micro_text(canvas_obj, MARGIN - 3*mm)  # Bottom
    
    # Add page numbers
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(COLOR_SLATE)
    page_num = getattr(doc, '_pageNumber', 1)
    total_pages = getattr(doc, '_totalPages', 1) 
    canvas_obj.drawRightString(PAGE_WIDTH - MARGIN, MARGIN - 8*mm, f"Page {page_num} of {total_pages}")
    
    canvas_obj.restoreState()


def create_qr_code(data: str, size: float = 30*mm) -> Image:
    """
    Create QR code image for verification.
    
    Args:
        data: Verification hash string
        size: Size in points
        
    Returns:
        ReportLab Image object
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    img_buffer = BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return Image(img_buffer, width=size, height=size)


def create_header_section(spec: SpecV1) -> list:
    """Create certificate header with title and job ID."""
    elements = []
    
    # Header with job ID
    header_style = ParagraphStyle(
        'CertHeader',
        fontName='Helvetica',
        fontSize=8,
        textColor=COLOR_SLATE,
        alignment=TA_CENTER,
        spaceAfter=3*mm
    )
    elements.append(Paragraph(f"ProofKit Certificate – {spec.job.job_id}", header_style))
    
    # Main title
    title_style = ParagraphStyle(
        'CertTitle',
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=COLOR_NAVY,
        alignment=TA_CENTER,
        spaceAfter=8*mm,
        leading=20
    )
    elements.append(Paragraph("Powder-Coat Cure Validation Certificate", title_style))
    
    return elements


def create_status_badge(decision: DecisionResult) -> Table:
    """Create centered PASS/FAIL status badge."""
    status = "PASS" if decision.pass_ else "FAIL"
    status_color = COLOR_EMERALD if decision.pass_ else COLOR_CRIMSON
    
    # Create badge table with rounded appearance
    badge_data = [[status]]
    badge_table = Table(badge_data, colWidths=[60*mm], rowHeights=[12*mm])
    
    badge_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), status_color),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 14),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 0),
        ('TOPPADDING', (0, 0), (0, 0), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 0),
        ('LINEBELOW', (0, 0), (0, 0), 2, status_color),
        ('LINEABOVE', (0, 0), (0, 0), 2, status_color),
        ('LINEBEFORE', (0, 0), (0, 0), 2, status_color),
        ('LINEAFTER', (0, 0), (0, 0), 2, status_color),
    ]))
    
    # Center the badge
    container_data = [['', badge_table, '']]
    container = Table(container_data, colWidths=[55*mm, 60*mm, 55*mm])
    container.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (2, 0), 'MIDDLE'),
    ]))
    
    return container


def create_specification_column(spec: SpecV1) -> Table:
    """Create left column with specification details."""
    spec_data = [
        [Paragraph('<b>Specification Details</b>', 
                  ParagraphStyle('Header', fontSize=10, textColor=COLOR_NAVY))],
    ]
    
    # Create rows with proper formatting
    details = [
        ('Target Temperature', f"{spec.spec.target_temp_C}°C"),
        ('Hold Time Required', f"{spec.spec.hold_time_s}s"),
        ('Sensor Uncertainty', f"±{spec.spec.sensor_uncertainty_C}°C"),
        ('Conservative Threshold', f"{spec.spec.target_temp_C + spec.spec.sensor_uncertainty_C}°C"),
    ]
    
    if spec.data_requirements:
        details.extend([
            ('Max Sample Period', f"{spec.data_requirements.max_sample_period_s}s"),
            ('Allowed Gaps', f"{spec.data_requirements.allowed_gaps_s}s"),
        ])
    
    if spec.logic:
        logic_type = "Continuous" if spec.logic.continuous else "Cumulative"
        details.append(('Hold Logic', logic_type))
    
    # Style for field names and values
    field_style = ParagraphStyle('Field', fontSize=9, textColor=COLOR_SLATE, leftIndent=5*mm)
    value_style = ParagraphStyle('Value', fontSize=9, textColor=COLOR_NAVY, alignment=TA_RIGHT)
    
    for field, value in details:
        spec_data.append([
            Paragraph(field, field_style),
            Paragraph(value, value_style)
        ])
    
    spec_table = Table(spec_data, colWidths=[40*mm, 35*mm])
    spec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_LIGHT_GREY),
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (1, 0), 3*mm),
        ('BOTTOMPADDING', (0, 0), (1, 0), 3*mm),
        ('GRID', (0, 1), (1, -1), 0.5, COLOR_MID_GREY),
        ('TOPPADDING', (0, 1), (1, -1), 2*mm),
        ('BOTTOMPADDING', (0, 1), (1, -1), 2*mm),
        ('VALIGN', (0, 0), (1, -1), 'MIDDLE'),
    ]))
    
    return spec_table


def create_results_column(decision: DecisionResult) -> Table:
    """Create right column with results summary."""
    results_data = [
        [Paragraph('<b>Results Summary</b>', 
                  ParagraphStyle('Header', fontSize=10, textColor=COLOR_NAVY))],
    ]
    
    # Status with color coding
    status_color = COLOR_EMERALD if decision.pass_ else COLOR_CRIMSON
    status_text = '<font color="%s"><b>%s</b></font>' % (
        status_color.hexval(), 
        'PASS' if decision.pass_ else 'FAIL'
    )
    
    details = [
        ('Status', status_text),
        ('Actual Hold Time', f"{int(decision.actual_hold_time_s)}s"),
        ('Required Hold Time', f"{int(decision.required_hold_time_s)}s"),
        ('Max Temperature', f"{decision.max_temp_C:.1f}°C"),
        ('Min Temperature', f"{decision.min_temp_C:.1f}°C"),
        ('Conservative Threshold', f"{decision.conservative_threshold_C:.1f}°C"),
    ]
    
    field_style = ParagraphStyle('Field', fontSize=9, textColor=COLOR_SLATE, leftIndent=5*mm)
    value_style = ParagraphStyle('Value', fontSize=9, textColor=COLOR_NAVY, alignment=TA_RIGHT)
    
    for field, value in details:
        if field == 'Status':
            # Special handling for status to preserve HTML formatting
            results_data.append([
                Paragraph(field, field_style),
                Paragraph(value, value_style)
            ])
        else:
            results_data.append([
                Paragraph(field, field_style),
                Paragraph(value, value_style)
            ])
    
    results_table = Table(results_data, colWidths=[40*mm, 35*mm])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_LIGHT_GREY),
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (1, 0), 3*mm),
        ('BOTTOMPADDING', (0, 0), (1, 0), 3*mm),
        ('GRID', (0, 1), (1, -1), 0.5, COLOR_MID_GREY),
        ('TOPPADDING', (0, 1), (1, -1), 2*mm),
        ('BOTTOMPADDING', (0, 1), (1, -1), 2*mm),
        ('VALIGN', (0, 0), (1, -1), 'MIDDLE'),
    ]))
    
    return results_table


def create_two_column_section(spec: SpecV1, decision: DecisionResult) -> Table:
    """Create two-column layout for specifications and results."""
    spec_column = create_specification_column(spec)
    results_column = create_results_column(decision)
    
    columns_data = [[spec_column, '', results_column]]
    columns_table = Table(columns_data, colWidths=[80*mm, 10*mm, 80*mm])
    columns_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (2, 0), 'TOP'),
    ]))
    
    return columns_table


def create_decision_reasons(decision: DecisionResult) -> list:
    """Create decision reasons list."""
    elements = []
    
    if not decision.reasons:
        return elements
    
    reasons_style = ParagraphStyle(
        'ReasonsHeader',
        fontSize=10,
        textColor=COLOR_NAVY,
        fontName='Helvetica-Bold',
        spaceAfter=2*mm
    )
    elements.append(Paragraph("Decision Reasons", reasons_style))
    
    reason_style = ParagraphStyle(
        'Reason',
        fontSize=8,
        textColor=COLOR_SLATE,
        leftIndent=5*mm,
        spaceAfter=1*mm
    )
    
    for reason in decision.reasons:
        elements.append(Paragraph(f"• {reason}", reason_style))
    
    return elements


def create_verification_section(verification_hash: str, job_id: Optional[str] = None) -> Table:
    """Create verification section with hash and QR code."""
    # Truncate hash for display
    hash_display = f"{verification_hash[:16]}...{verification_hash[-16:]}"
    
    # Create QR code with verification URL if job_id is available
    if job_id:
        short_id = job_id[:10] if len(job_id) > 10 else job_id
        qr_data = f"https://www.proofkit.net/verify/{short_id}"
    else:
        qr_data = verification_hash
    
    qr_image = create_qr_code(qr_data)
    
    # Verification info
    verify_style = ParagraphStyle('Verify', fontSize=8, textColor=COLOR_SLATE)
    hash_style = ParagraphStyle('Hash', fontSize=7, textColor=COLOR_NAVY, 
                                fontName='Courier')
    
    verify_data = [
        [Paragraph('<b>Verification</b>', verify_style), ''],
        [Paragraph('Hash:', verify_style), Paragraph(hash_display, hash_style)],
        ['', ''],
    ]
    
    verify_table = Table(verify_data, colWidths=[20*mm, 60*mm])
    verify_table.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'LEFT'),
        ('TOPPADDING', (0, 0), (1, -1), 1*mm),
        ('BOTTOMPADDING', (0, 0), (1, -1), 1*mm),
    ]))
    
    # Combine with QR code
    qr_caption = Paragraph('Scan to verify', 
                          ParagraphStyle('Caption', fontSize=6, 
                                       textColor=COLOR_SLATE, alignment=TA_CENTER))
    
    qr_section = Table([[qr_image], [qr_caption]], colWidths=[30*mm])
    qr_section.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 1), 'CENTER'),
    ]))
    
    # Full verification section
    full_data = [[verify_table, '', qr_section]]
    full_table = Table(full_data, colWidths=[85*mm, 40*mm, 35*mm])
    full_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (2, 0), 'TOP'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    
    return full_table


def create_signature_section() -> Table:
    """Create signature fields for Process Engineer and Quality Manager."""
    sig_style = ParagraphStyle('SigLabel', fontSize=8, textColor=COLOR_SLATE)
    
    sig_data = [
        [Paragraph('Process Engineer', sig_style), 
         '', 
         Paragraph('Quality Manager', sig_style)],
        ['_' * 30, '', '_' * 30],
        [Paragraph('Signature', sig_style), 
         '', 
         Paragraph('Signature', sig_style)],
        ['', '', ''],
        ['_' * 20, '', '_' * 20],
        [Paragraph('Date', sig_style), 
         '', 
         Paragraph('Date', sig_style)],
    ]
    
    sig_table = Table(sig_data, colWidths=[70*mm, 30*mm, 70*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (2, -1), 8),
        ('TEXTCOLOR', (0, 0), (2, -1), COLOR_SLATE),
        ('TOPPADDING', (0, 0), (2, -1), 2*mm),
    ]))
    
    return sig_table


def create_footer(timestamp: Optional[datetime] = None) -> list:
    """Create footer with timestamp and value statement."""
    elements = []
    
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    # Value statement in small caps
    value_style = ParagraphStyle(
        'Value',
        fontSize=7,
        textColor=COLOR_MID_GREY,
        alignment=TA_CENTER,
        spaceAfter=2*mm
    )
    elements.append(Paragraph(
        "Independent third-party verification – replacement cost 110 USD",
        value_style
    ))
    
    # Footer line
    footer_style = ParagraphStyle(
        'Footer',
        fontSize=8,
        textColor=COLOR_SLATE,
        alignment=TA_CENTER
    )
    footer_text = f"Generated by ProofKit v1.0 | {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    elements.append(Paragraph(footer_text, footer_style))
    
    return elements


def generate_certificate_pdf(
    spec: SpecV1,
    decision: DecisionResult,
    plot_path: Union[str, Path],
    verification_hash: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
    timestamp: Optional[datetime] = None
) -> bytes:
    """
    Generate ISO-style single-page A4 certificate.
    
    Args:
        spec: Specification data
        decision: Decision result
        plot_path: Path to temperature plot image
        verification_hash: Verification hash for QR code
        output_path: Optional output file path
        timestamp: Optional timestamp for testing
        
    Returns:
        PDF content as bytes
    """
    # Generate verification hash if not provided
    if verification_hash is None:
        hash_data = f"{spec.job.job_id}{decision.pass_}{decision.actual_hold_time_s}"
        verification_hash = hashlib.sha256(hash_data.encode()).hexdigest()
    
    # Register fonts
    register_fonts()
    
    # Create temporary file for PDF
    temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
    os.close(temp_fd)
    
    try:
        # Create document with custom canvas
        doc = SimpleDocTemplate(
            temp_path,
            pagesize=A4,
            rightMargin=MARGIN,
            leftMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
            title=f"ProofKit Certificate - {spec.job.job_id}"
        )
        
        # Build content
        elements = []
        
        # Header and title
        elements.extend(create_header_section(spec))
        
        # Status badge
        elements.append(create_status_badge(decision))
        elements.append(Spacer(1, 8*mm))
        
        # Two-column section
        elements.append(create_two_column_section(spec, decision))
        elements.append(Spacer(1, 6*mm))
        
        # Decision reasons
        reasons = create_decision_reasons(decision)
        if reasons:
            elements.extend(reasons)
            elements.append(Spacer(1, 5*mm))
        
        # Temperature plot (if exists)
        if os.path.exists(plot_path):
            try:
                # Add plot title
                plot_style = ParagraphStyle(
                    'PlotTitle',
                    fontSize=10,
                    textColor=COLOR_NAVY,
                    fontName='Helvetica-Bold',
                    alignment=TA_CENTER,
                    spaceAfter=3*mm
                )
                elements.append(Paragraph("Temperature Profile", plot_style))
                
                # Add plot image
                plot_img = Image(str(plot_path), width=140*mm, height=70*mm)
                plot_img.hAlign = 'CENTER'
                elements.append(plot_img)
                elements.append(Spacer(1, 5*mm))
            except:
                pass
        
        # Verification section
        elements.append(create_verification_section(verification_hash, spec.job.job_id))
        elements.append(Spacer(1, 10*mm))
        
        # Signature section
        elements.append(create_signature_section())
        elements.append(Spacer(1, 8*mm))
        
        # Footer
        elements.extend(create_footer(timestamp))
        
        # Build PDF with watermark
        doc.build(
            elements,
            onFirstPage=create_watermark_canvas,
            onLaterPages=create_watermark_canvas
        )
        
        # Read PDF bytes
        with open(temp_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Save to output path if provided
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
        
        return pdf_bytes
        
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass