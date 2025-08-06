"""
ProofKit Professional ISO-Style Certificate Generator

Creates authoritative single-page A4 certificates with calibration lab aesthetics.
Features logo watermark/seal, baseline grid, micro-text borders, and CMYK colors.

Example usage:
    from core.models import SpecV1, DecisionResult
    from core.render_certificate_pro import generate_certificate_pdf
    
    pdf_bytes = generate_certificate_pdf(spec, decision, plot_path, certificate_no)
"""

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Tuple

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, Frame, PageTemplate, BaseDocTemplate
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Circle, Path
from reportlab.graphics import renderPDF
from reportlab.lib.colors import CMYKColor

from core.models import SpecV1, DecisionResult

# A4 dimensions and layout constants
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm
SAFE_WIDTH = PAGE_WIDTH - (2 * MARGIN)
SAFE_HEIGHT = PAGE_HEIGHT - (2 * MARGIN)
BASELINE_GRID = 6 * mm  # 6mm baseline grid

# Professional CMYK color palette
COLOR_NAVY_CMYK = CMYKColor(0.93, 0.76, 0.00, 0.73)      # Deep navy #102A43
COLOR_SLATE_CMYK = CMYKColor(0.80, 0.48, 0.00, 0.59)     # Slate grey #334E68
COLOR_SLATE_LABEL = CMYKColor(0.65, 0.35, 0.00, 0.49)    # Label grey #576981
COLOR_CRIMSON_CMYK = CMYKColor(0.00, 0.79, 0.76, 0.24)   # Crimson #C1292E
COLOR_EMERALD_CMYK = CMYKColor(0.82, 0.00, 0.77, 0.51)   # Emerald #2E7D32
COLOR_GOLD_CMYK = CMYKColor(0.25, 0.36, 0.80, 0.20)      # Gold accent #B79E34
COLOR_BLACK_CMYK = CMYKColor(0, 0, 0, 1)                 # Pure black
COLOR_WHITE = colors.white

# Micro-text for security borders  
MICRO_TEXT = "AUTHENTICITY GUARANTEED BY PROOFKIT SECURE RENDER ENGINE · "


def _draw_micro_text(c, y):
    """Draw horizontal micro-text security border."""
    c.setFont("Helvetica", 6)
    c.setFillColor(COLOR_SLATE_CMYK, alpha=0.3)
    c.drawString(MARGIN, y, (MICRO_TEXT * 8)[:int((PAGE_WIDTH - 2*MARGIN)/mm * 2)])


def create_logo_shapes():
    """Create ProofKit logo as ReportLab shapes (checkmark in circle)."""
    drawing = Drawing(40, 40)
    
    # Green circle background
    circle = Circle(20, 20, 16)
    circle.fillColor = CMYKColor(0.50, 0.00, 0.62, 0.00)  # Green #23C48E
    circle.strokeColor = None
    drawing.add(circle)
    
    # White checkmark path
    checkmark = Path()
    checkmark.moveTo(13, 20)
    checkmark.lineTo(17, 24)
    checkmark.lineTo(25, 16)
    checkmark.strokeColor = COLOR_WHITE
    checkmark.strokeWidth = 2.5
    checkmark.strokeLineCap = 1  # Round caps
    checkmark.strokeLineJoin = 1  # Round joins
    checkmark.fillColor = None
    drawing.add(checkmark)
    
    return drawing


def create_certificate_canvas(canvas_obj, doc):
    """
    Add sophisticated design elements to each page.
    
    Args:
        canvas_obj: ReportLab canvas object
        doc: Document template
    """
    canvas_obj.saveState()
    
    # 1. MICRO-TEXT BORDER (top and bottom only - matches working implementation)
    _draw_micro_text(canvas_obj, PAGE_HEIGHT - MARGIN + 1*mm)  # Top
    _draw_micro_text(canvas_obj, MARGIN - 3*mm)  # Bottom
    
    # 2. MAIN BORDER (0.5pt navy)
    canvas_obj.setStrokeColor(COLOR_NAVY_CMYK)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.rect(MARGIN, MARGIN, SAFE_WIDTH, SAFE_HEIGHT)
    
    # 3. NO WATERMARK (removed per user request)
    
    # 4. TOP HEADER LINE (thin 0.5pt navy)
    canvas_obj.setStrokeColor(COLOR_NAVY_CMYK)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN, PAGE_HEIGHT - MARGIN - 15*mm, 
                   PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN - 15*mm)
    
    # 5. PAGE NUMBERS
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(COLOR_SLATE_CMYK)
    page_num = getattr(doc, '_pageNumber', 1)
    total_pages = getattr(doc, '_totalPages', 1)
    canvas_obj.drawRightString(PAGE_WIDTH - MARGIN, MARGIN - 8*mm, f"Page {page_num} of {total_pages}")
    
    canvas_obj.restoreState()


def create_qr_code(data: str, size: float = 30*mm) -> Image:
    """Create QR code for verification."""
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


def create_header_section(certificate_no: str) -> Table:
    """Create header with title and certificate number."""
    # Main headline in caps (EB Garamond would be serif, using Helvetica-Bold as substitute)
    title_style = ParagraphStyle(
        'MainTitle',
        fontName='Times-Bold',  # Serif substitute for EB Garamond
        fontSize=18,
        textColor=COLOR_NAVY_CMYK,
        alignment=TA_LEFT,
        leading=BASELINE_GRID * 3
    )
    
    # Certificate number (Inter would be sans-serif, using Helvetica)
    cert_style = ParagraphStyle(
        'CertNo',
        fontName='Helvetica',
        fontSize=9,
        textColor=COLOR_SLATE_CMYK,
        alignment=TA_RIGHT,
        leading=BASELINE_GRID * 3
    )
    
    header_data = [[
        Paragraph("PROOFKIT CERTIFICATE OF POWDER-COAT VALIDATION", title_style),
        Paragraph(f"Certificate No. {certificate_no}", cert_style)
    ]]
    
    header_table = Table(header_data, colWidths=[120*mm, 50*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (1, 0), 'TOP'),
        ('TOPPADDING', (0, 0), (1, 0), 0),
        ('BOTTOMPADDING', (0, 0), (1, 0), BASELINE_GRID),
    ]))
    
    return header_table


def create_status_badge(decision: DecisionResult) -> Table:
    """Create centered PASS/FAIL badge with drop shadow effect."""
    status = "PASS" if decision.pass_ else "FAIL"
    status_color = COLOR_EMERALD_CMYK if decision.pass_ else COLOR_CRIMSON_CMYK
    
    # Badge with fixed 18mm height
    badge_data = [[status]]
    badge_table = Table(badge_data, colWidths=[60*mm], rowHeights=[18*mm])
    
    badge_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), status_color),
        ('TEXTCOLOR', (0, 0), (0, 0), COLOR_WHITE),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 16),
        ('ROUNDEDCORNERS', [5]),
        ('LINEBELOW', (0, 0), (0, 0), 3, colors.Color(0, 0, 0, alpha=0.1)),  # Shadow effect
    ]))
    
    # Center container
    container_data = [['', badge_table, '']]
    container = Table(container_data, colWidths=[55*mm, 60*mm, 55*mm])
    container.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (2, 0), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (2, 0), 0),
        ('BOTTOMPADDING', (0, 0), (2, 0), BASELINE_GRID),
    ]))
    
    return container


def create_specification_column(spec: SpecV1) -> Table:
    """Create left column with fixed-width columns."""
    spec_data = [
        [Paragraph('<b>Specification Details</b>', 
                  ParagraphStyle('Header', fontSize=10, textColor=COLOR_NAVY_CMYK))],
    ]
    
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
    
    # Fixed column widths: 65mm label, 35mm value
    label_style = ParagraphStyle('Label', fontSize=9, textColor=COLOR_SLATE_LABEL, 
                                 fontName='Helvetica')
    value_style = ParagraphStyle('Value', fontSize=9, textColor=COLOR_BLACK_CMYK,
                                 fontName='Helvetica', alignment=TA_RIGHT)
    
    for field, value in details:
        spec_data.append([
            Paragraph(field, label_style),
            Paragraph(value, value_style)
        ])
    
    spec_table = Table(spec_data, colWidths=[45*mm, 25*mm])
    spec_table.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('BACKGROUND', (0, 0), (1, 0), colors.Color(0.95, 0.95, 0.95)),
        ('LINEBELOW', (0, 0), (1, 0), 0.5, COLOR_NAVY_CMYK),
        ('TOPPADDING', (0, 0), (1, 0), BASELINE_GRID/2),
        ('BOTTOMPADDING', (0, 0), (1, 0), BASELINE_GRID/2),
        ('TOPPADDING', (0, 1), (1, -1), BASELINE_GRID/3),
        ('BOTTOMPADDING', (0, 1), (1, -1), BASELINE_GRID/3),
        ('GRID', (0, 1), (1, -1), 0.25, COLOR_SLATE_CMYK),
    ]))
    
    return spec_table


def create_results_column(decision: DecisionResult) -> Table:
    """Create right column with results."""
    results_data = [
        [Paragraph('<b>Results Summary</b>', 
                  ParagraphStyle('Header', fontSize=10, textColor=COLOR_NAVY_CMYK))],
    ]
    
    status_color = COLOR_EMERALD_CMYK if decision.pass_ else COLOR_CRIMSON_CMYK
    
    details = [
        ('Status', 'PASS' if decision.pass_ else 'FAIL'),
        ('Actual Hold Time', f"{int(decision.actual_hold_time_s)}s"),
        ('Required Hold Time', f"{int(decision.required_hold_time_s)}s"),
        ('Max Temperature', f"{decision.max_temp_C:.1f}°C"),
        ('Min Temperature', f"{decision.min_temp_C:.1f}°C"),
        ('Conservative Threshold', f"{decision.conservative_threshold_C:.1f}°C"),
    ]
    
    label_style = ParagraphStyle('Label', fontSize=9, textColor=COLOR_SLATE_LABEL,
                                 fontName='Helvetica')
    value_style = ParagraphStyle('Value', fontSize=9, textColor=COLOR_BLACK_CMYK,
                                 fontName='Helvetica', alignment=TA_RIGHT)
    
    for i, (field, value) in enumerate(details):
        if field == 'Status':
            # Special styling for status
            status_style = ParagraphStyle('Status', fontSize=9, textColor=status_color,
                                         fontName='Helvetica-Bold', alignment=TA_RIGHT)
            results_data.append([
                Paragraph(field, label_style),
                Paragraph(value, status_style)
            ])
        else:
            results_data.append([
                Paragraph(field, label_style),
                Paragraph(value, value_style)
            ])
    
    results_table = Table(results_data, colWidths=[45*mm, 25*mm])
    results_table.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('BACKGROUND', (0, 0), (1, 0), colors.Color(0.95, 0.95, 0.95)),
        ('LINEBELOW', (0, 0), (1, 0), 0.5, COLOR_NAVY_CMYK),
        ('TOPPADDING', (0, 0), (1, 0), BASELINE_GRID/2),
        ('BOTTOMPADDING', (0, 0), (1, 0), BASELINE_GRID/2),
        ('TOPPADDING', (0, 1), (1, -1), BASELINE_GRID/3),
        ('BOTTOMPADDING', (0, 1), (1, -1), BASELINE_GRID/3),
        ('GRID', (0, 1), (1, -1), 0.25, COLOR_SLATE_CMYK),
    ]))
    
    return results_table


def create_decision_reasons(decision: DecisionResult) -> list:
    """Create compact decision reasons."""
    elements = []
    
    if not decision.reasons:
        return elements
    
    reasons_style = ParagraphStyle(
        'ReasonsHeader',
        fontSize=9,
        textColor=COLOR_NAVY_CMYK,
        fontName='Helvetica-Bold',
        leading=BASELINE_GRID
    )
    elements.append(Paragraph("Decision Reasons", reasons_style))
    
    reason_style = ParagraphStyle(
        'Reason',
        fontSize=8,
        textColor=COLOR_SLATE_CMYK,
        leftIndent=5*mm,
        leading=BASELINE_GRID * 0.75,
        fontName='Helvetica'
    )
    
    for reason in decision.reasons:
        elements.append(Paragraph(f"• {reason}", reason_style))
    
    return elements


def create_verification_section(verification_hash: str, job_id: Optional[str] = None) -> Table:
    """Create verification with full hash and QR."""
    # Create QR code with verification URL if job_id is available
    if job_id:
        short_id = job_id[:10] if len(job_id) > 10 else job_id
        qr_data = f"https://www.proofkit.net/verify/{short_id}"
    else:
        qr_data = verification_hash
    
    qr_image = create_qr_code(qr_data)
    
    verify_style = ParagraphStyle('Verify', fontSize=9, textColor=COLOR_NAVY_CMYK,
                                  fontName='Helvetica-Bold')
    hash_style = ParagraphStyle('Hash', fontSize=7, textColor=COLOR_BLACK_CMYK,
                                fontName='Courier', wordWrap='CJK')
    
    # Show full hash with wrapping
    verify_data = [
        [Paragraph('Verification Hash:', verify_style)],
        [Paragraph(verification_hash, hash_style)],
    ]
    
    verify_table = Table(verify_data, colWidths=[110*mm])
    verify_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (0, -1), BASELINE_GRID/4),
        ('BOTTOMPADDING', (0, 0), (0, -1), BASELINE_GRID/4),
    ]))
    
    # QR with caption
    qr_caption = Paragraph('Scan to verify', 
                          ParagraphStyle('Caption', fontSize=7,
                                       textColor=COLOR_SLATE_CMYK, alignment=TA_CENTER))
    
    qr_section = Table([[qr_image], [qr_caption]], colWidths=[30*mm])
    qr_section.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 1), 'CENTER'),
    ]))
    
    # Combine
    full_data = [[verify_table, qr_section]]
    full_table = Table(full_data, colWidths=[130*mm, 40*mm])
    full_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (1, 0), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    
    return full_table


def create_signature_section_with_seal() -> Table:
    """Create signatures with logo seal."""
    sig_style = ParagraphStyle('SigLabel', fontSize=8, textColor=COLOR_SLATE_CMYK,
                               fontName='Helvetica')
    
    # Create logo seal (20mm diameter with gold circle)
    seal_drawing = Drawing(25*mm, 25*mm)
    
    # Gold circle border
    gold_circle = Circle(12.5*mm, 12.5*mm, 10*mm)
    gold_circle.strokeColor = COLOR_GOLD_CMYK
    gold_circle.strokeWidth = 0.5
    gold_circle.fillColor = None
    seal_drawing.add(gold_circle)
    
    # Logo inside (scaled down)
    inner_circle = Circle(12.5*mm, 12.5*mm, 8*mm)
    inner_circle.fillColor = CMYKColor(0.50, 0.00, 0.62, 0.00)
    inner_circle.strokeColor = None
    seal_drawing.add(inner_circle)
    
    # Checkmark
    checkmark = Path()
    checkmark.moveTo(8*mm, 12.5*mm)
    checkmark.lineTo(11*mm, 15.5*mm)
    checkmark.lineTo(17*mm, 9.5*mm)
    checkmark.strokeColor = COLOR_WHITE
    checkmark.strokeWidth = 1.5
    checkmark.fillColor = None
    seal_drawing.add(checkmark)
    
    sig_data = [
        [Paragraph('Process Engineer', sig_style), 
         '', 
         Paragraph('Quality Manager', sig_style),
         ''],
        ['_' * 25, '', '_' * 25, seal_drawing],
        [Paragraph('Signature', sig_style), 
         '', 
         Paragraph('Signature', sig_style),
         ''],
        ['', '', '', ''],
        ['_' * 15, '', '_' * 15, ''],
        [Paragraph('Date', sig_style), 
         '', 
         Paragraph('Date', sig_style),
         ''],
    ]
    
    sig_table = Table(sig_data, colWidths=[60*mm, 20*mm, 60*mm, 30*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('VALIGN', (3, 1), (3, 1), 'MIDDLE'),
        ('SPAN', (3, 1), (3, 2)),
        ('FONTSIZE', (0, 0), (2, -1), 8),
        ('TEXTCOLOR', (0, 0), (2, -1), COLOR_SLATE_CMYK),
    ]))
    
    return sig_table


def create_footer(timestamp: Optional[datetime] = None) -> Paragraph:
    """Create footer."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    footer_style = ParagraphStyle(
        'Footer',
        fontSize=8,
        textColor=COLOR_SLATE_CMYK,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    footer_text = f"Generated by ProofKit v1.0 | {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    return Paragraph(footer_text, footer_style)


def generate_certificate_pdf(
    spec: SpecV1,
    decision: DecisionResult,
    plot_path: Optional[Union[str, Path]] = None,
    certificate_no: Optional[str] = None,
    verification_hash: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
    timestamp: Optional[datetime] = None
) -> bytes:
    """
    Generate professional ISO-style certificate with all enhancements.
    
    Args:
        spec: Specification data
        decision: Decision result
        plot_path: Optional path to temperature plot
        certificate_no: Certificate number (defaults to job_id)
        verification_hash: Verification hash for QR
        output_path: Optional output file path
        timestamp: Optional timestamp
        
    Returns:
        PDF content as bytes
    """
    # Use job_id as certificate number if not provided
    if certificate_no is None:
        certificate_no = spec.job.job_id
    
    # Generate verification hash if not provided
    if verification_hash is None:
        hash_data = f"{certificate_no}{decision.pass_}{decision.actual_hold_time_s}"
        verification_hash = hashlib.sha256(hash_data.encode()).hexdigest()
    
    # Create temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
    os.close(temp_fd)
    
    try:
        # Create document
        doc = SimpleDocTemplate(
            temp_path,
            pagesize=A4,
            rightMargin=MARGIN,
            leftMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
            title=f"ProofKit Certificate - {certificate_no}"
        )
        
        # Build content aligned to baseline grid
        elements = []
        
        # Header with certificate number
        elements.append(Spacer(1, BASELINE_GRID * 2))
        elements.append(create_header_section(certificate_no))
        elements.append(Spacer(1, BASELINE_GRID))
        
        # Status badge
        elements.append(create_status_badge(decision))
        elements.append(Spacer(1, BASELINE_GRID))
        
        # Two-column layout
        spec_column = create_specification_column(spec)
        results_column = create_results_column(decision)
        
        columns_data = [[spec_column, '', results_column]]
        columns_table = Table(columns_data, colWidths=[75*mm, 20*mm, 75*mm])
        columns_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (2, 0), 'TOP'),
        ]))
        elements.append(columns_table)
        elements.append(Spacer(1, BASELINE_GRID))
        
        # Decision reasons
        reasons = create_decision_reasons(decision)
        if reasons:
            elements.extend(reasons)
            elements.append(Spacer(1, BASELINE_GRID))
        
        # Temperature plot (if provided and exists)
        if plot_path and os.path.exists(plot_path):
            try:
                plot_style = ParagraphStyle(
                    'PlotTitle',
                    fontSize=9,
                    textColor=COLOR_NAVY_CMYK,
                    fontName='Helvetica-Bold',
                    alignment=TA_CENTER
                )
                elements.append(Paragraph("Temperature Profile", plot_style))
                elements.append(Spacer(1, BASELINE_GRID/2))
                
                plot_img = Image(str(plot_path), width=140*mm, height=60*mm)
                plot_img.hAlign = 'CENTER'
                elements.append(plot_img)
                elements.append(Spacer(1, BASELINE_GRID))
            except:
                pass
        
        # Verification section
        elements.append(create_verification_section(verification_hash, spec.job.job_id))
        elements.append(Spacer(1, BASELINE_GRID))
        
        # Signature section with seal
        elements.append(create_signature_section_with_seal())
        elements.append(Spacer(1, BASELINE_GRID))
        
        # Footer
        elements.append(create_footer(timestamp))
        
        # Build PDF with custom canvas
        doc.build(
            elements,
            onFirstPage=create_certificate_canvas,
            onLaterPages=create_certificate_canvas
        )
        
        # Read PDF bytes
        with open(temp_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Save to output path if provided
        if output_path:
            final_path = f"proofkit_certificate_{certificate_no}.pdf"
            if isinstance(output_path, str) and not output_path.endswith('.pdf'):
                output_path = final_path
            elif isinstance(output_path, Path):
                output_path = output_path.parent / final_path
                
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
        
        return pdf_bytes
        
    finally:
        # Clean up
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass