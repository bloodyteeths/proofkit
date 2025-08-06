"""
ProofKit Premium Certificate Generator

Creates official, expensive-looking single-page A4 certificates with premium fonts,
gold foil effects, and sophisticated security features.

Example usage:
    from core.models import SpecV1, DecisionResult
    from core.render_certificate_premium import generate_premium_certificate
    
    pdf_bytes = generate_premium_certificate(spec, decision, plot_path, certificate_no)
"""

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path as FilePath
from typing import Optional, Union

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Circle, Path, String, Rect
from reportlab.graphics import renderPDF

from core.models import SpecV1, DecisionResult

# A4 dimensions and layout constants
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm
SAFE_WIDTH = PAGE_WIDTH - (2 * MARGIN)
SAFE_HEIGHT = PAGE_HEIGHT - (2 * MARGIN)

# Premium color palette
COLOR_NAVY = colors.HexColor("#102A43")           # Deep navy for headers/rules
COLOR_SLATE = colors.HexColor("#334E68")          # Slate grey for body text
COLOR_CRIMSON = colors.HexColor("#C1292E")        # Crimson for FAIL
COLOR_EMERALD = colors.HexColor("#2E7D32")        # Emerald for PASS
COLOR_GOLD = colors.HexColor("#B79E34")           # Gold for seal outline
COLOR_SHADOW = colors.Color(0, 0, 0, alpha=0.1)   # 10% K shadow

# Micro-text for security borders
MICRO_TEXT = "AUTHENTICITY GUARANTEED BY PROOFKIT SECURE RENDER ENGINE · "


def _draw_micro_text(c, y):
    """Draw horizontal micro-text security border."""
    c.setFont("Helvetica", 6)
    c.setFillColor(COLOR_SLATE, alpha=0.3)
    c.drawString(MARGIN, y, (MICRO_TEXT * 8)[:int((PAGE_WIDTH - 2*MARGIN)/mm * 2)])


def register_fonts():
    """Register premium fonts for the certificate."""
    fonts_dir = FilePath(__file__).parent.parent / "fonts"
    
    # Register available fonts
    try:
        # Cormorant Garamond for headlines
        if (fonts_dir / "CormorantGaramond-Bold.ttf").exists():
            pdfmetrics.registerFont(TTFont('CormorantSC', 
                str(fonts_dir / "CormorantGaramond-Bold.ttf")))
        else:
            # Fallback to Times-Bold
            pass
            
        # Great Vibes for signatures
        if (fonts_dir / "GreatVibes-Regular.ttf").exists():
            pdfmetrics.registerFont(TTFont('GreatVibes', 
                str(fonts_dir / "GreatVibes-Regular.ttf")))
        else:
            # Fallback to Times-Italic
            pass
            
        # Inter for body (using Helvetica as fallback)
        # Since Inter files are problematic, we'll use Helvetica
        
    except Exception as e:
        print(f"Font registration warning: {e}")


def create_premium_canvas(canvas_obj, doc):
    """
    Add premium design elements with security features.
    
    Args:
        canvas_obj: ReportLab canvas object
        doc: Document template
    """
    canvas_obj.saveState()
    
    # 1. TOP AND BOTTOM BORDER RULES (0.5pt navy)
    canvas_obj.setStrokeColor(COLOR_NAVY)
    canvas_obj.setLineWidth(0.5)
    # Top rule
    canvas_obj.line(MARGIN, PAGE_HEIGHT - MARGIN, 
                   PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN)
    # Bottom rule
    canvas_obj.line(MARGIN, MARGIN, 
                   PAGE_WIDTH - MARGIN, MARGIN)
    
    # 2. MICRO-TEXT SECURITY BORDERS (top and bottom only - matches working implementation)
    _draw_micro_text(canvas_obj, PAGE_HEIGHT - MARGIN + 1*mm)  # Top
    _draw_micro_text(canvas_obj, MARGIN - 3*mm)  # Bottom
    
    # 3. NO WATERMARK (removed per user request)
    
    # 4. PAGE NUMBERS
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(COLOR_SLATE)
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


def create_header_section(certificate_no: str) -> list:
    """Create header with certificate number."""
    elements = []
    
    # Try to use Cormorant Garamond, fallback to Times-Bold
    try:
        title_font = 'CormorantSC'
    except:
        title_font = 'Times-Bold'
    
    # Header line style
    header_style = ParagraphStyle(
        'HeaderLine',
        fontName='Helvetica',
        fontSize=9,
        textColor=COLOR_SLATE,
        alignment=TA_CENTER,
        spaceAfter=6*mm
    )
    
    elements.append(Paragraph(f"ProofKit Certificate – {certificate_no}", header_style))
    
    # Main title with small caps effect (using uppercase with smaller size)
    title_style = ParagraphStyle(
        'MainTitle',
        fontName=title_font,
        fontSize=18,
        textColor=COLOR_NAVY,
        alignment=TA_CENTER,
        spaceAfter=8*mm,
        leading=22,
        tracking=-0.15  # Tighter tracking
    )
    
    elements.append(Paragraph("POWDER-COAT CURE VALIDATION CERTIFICATE", title_style))
    
    return elements


def create_status_badge(decision: DecisionResult) -> Table:
    """Create centered PASS/FAIL badge with shadow."""
    status = "PASS" if decision.pass_ else "FAIL"
    status_color = COLOR_EMERALD if decision.pass_ else COLOR_CRIMSON
    
    # Try to use Cormorant for badge
    try:
        badge_font = 'CormorantSC'
    except:
        badge_font = 'Times-Bold'
    
    # Create badge with exact dimensions
    badge_data = [[status]]
    badge_table = Table(badge_data, colWidths=[60*mm], rowHeights=[18*mm])
    
    # Apply rounded rect style with shadow
    badge_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), status_color),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, 0), badge_font),
        ('FONTSIZE', (0, 0), (0, 0), 18),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 0),
        ('TOPPADDING', (0, 0), (0, 0), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 0),
        ('ROUNDEDCORNERS', [5]),
        # Shadow effect
        ('LINEBELOW', (0, 0), (0, 0), 3, COLOR_SHADOW),
    ]))
    
    # Center the badge
    container_data = [['', badge_table, '']]
    container = Table(container_data, colWidths=[55*mm, 60*mm, 55*mm])
    container.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (2, 0), 'MIDDLE'),
    ]))
    
    return container


def create_two_column_tables(spec: SpecV1, decision: DecisionResult) -> Table:
    """Create two-column layout with fixed widths (65mm label / 35mm value)."""
    
    # Specification Details (left column)
    spec_data = [
        ['Specification Details', ''],
        ['Target Temperature', f"{spec.spec.target_temp_C}°C"],
        ['Hold Time Required', f"{spec.spec.hold_time_s}s"],
        ['Sensor Uncertainty', f"±{spec.spec.sensor_uncertainty_C}°C"],
        ['Conservative Threshold', f"{spec.spec.target_temp_C + spec.spec.sensor_uncertainty_C}°C"],
    ]
    
    if spec.data_requirements:
        spec_data.extend([
            ['Max Sample Period', f"{spec.data_requirements.max_sample_period_s}s"],
            ['Allowed Gaps', f"{spec.data_requirements.allowed_gaps_s}s"],
        ])
    
    if spec.logic:
        logic_type = "Continuous" if spec.logic.continuous else "Cumulative"
        spec_data.append(['Hold Logic', logic_type])
    
    spec_table = Table(spec_data, colWidths=[52.5*mm, 27.5*mm])
    spec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_NAVY),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('FONT', (0, 0), (1, 0), 'Helvetica-Bold', 10),
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('FONT', (0, 1), (0, -1), 'Helvetica', 9),
        ('FONT', (1, 1), (1, -1), 'Helvetica-Bold', 9),
        ('TEXTCOLOR', (0, 1), (0, -1), COLOR_SLATE),
        ('TEXTCOLOR', (1, 1), (1, -1), colors.black),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (1, 0), 1, COLOR_NAVY),
        ('LINEAFTER', (0, 1), (0, -1), 0.5, colors.Color(0.9, 0.9, 0.9)),
        ('TOPPADDING', (0, 0), (1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (1, -1), 4),
        ('LEFTPADDING', (0, 0), (1, -1), 6),
        ('RIGHTPADDING', (0, 0), (1, -1), 6),
    ]))
    
    # Results Summary (right column)
    status_text = 'PASS' if decision.pass_ else 'FAIL'
    status_color = COLOR_EMERALD if decision.pass_ else COLOR_CRIMSON
    
    results_data = [
        ['Results Summary', ''],
        ['Status', status_text],
        ['Actual Hold Time', f"{int(decision.actual_hold_time_s)}s"],
        ['Required Hold Time', f"{int(decision.required_hold_time_s)}s"],
        ['Max Temperature', f"{decision.max_temp_C:.1f}°C"],
        ['Min Temperature', f"{decision.min_temp_C:.1f}°C"],
        ['Conservative Threshold', f"{decision.conservative_threshold_C:.1f}°C"],
    ]
    
    results_table = Table(results_data, colWidths=[52.5*mm, 27.5*mm])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_NAVY),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('FONT', (0, 0), (1, 0), 'Helvetica-Bold', 10),
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('FONT', (0, 1), (0, -1), 'Helvetica', 9),
        ('FONT', (1, 1), (1, -1), 'Helvetica-Bold', 9),
        ('TEXTCOLOR', (0, 1), (0, -1), COLOR_SLATE),
        ('TEXTCOLOR', (1, 1), (1, 1), status_color),  # Status color
        ('TEXTCOLOR', (1, 2), (1, -1), colors.black),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (1, 0), 1, COLOR_NAVY),
        ('LINEAFTER', (0, 1), (0, -1), 0.5, colors.Color(0.9, 0.9, 0.9)),
        ('TOPPADDING', (0, 0), (1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (1, -1), 4),
        ('LEFTPADDING', (0, 0), (1, -1), 6),
        ('RIGHTPADDING', (0, 0), (1, -1), 6),
    ]))
    
    # Combine both tables with gutter
    combined_data = [[spec_table, '', results_table]]
    combined_table = Table(combined_data, colWidths=[82*mm, 6*mm, 82*mm])
    combined_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (2, 0), 'TOP'),
    ]))
    
    return combined_table


def create_decision_reasons(decision: DecisionResult) -> list:
    """Create decision reasons list."""
    elements = []
    
    if not decision.reasons:
        return elements
    
    reasons_header = ParagraphStyle(
        'ReasonsHeader',
        fontSize=10,
        textColor=COLOR_NAVY,
        fontName='Helvetica-Bold',
        spaceAfter=3*mm
    )
    elements.append(Paragraph("Decision Reasons", reasons_header))
    
    reason_style = ParagraphStyle(
        'Reason',
        fontSize=9,
        textColor=COLOR_SLATE,
        fontName='Helvetica',
        leftIndent=5*mm,
        spaceAfter=2*mm,
        leading=10.8  # 10.8pt leading for Inter 9pt equivalent
    )
    
    for reason in decision.reasons:
        elements.append(Paragraph(f"• {reason}", reason_style))
    
    return elements


def create_verification_section(verification_hash: str, job_id: Optional[str] = None) -> Table:
    """Create verification section with hash and QR code."""
    # Create QR code with verification URL if job_id is available
    if job_id:
        short_id = job_id[:10] if len(job_id) > 10 else job_id
        qr_data = f"https://www.proofkit.net/verify/{short_id}"
    else:
        qr_data = verification_hash
    
    qr_image = create_qr_code(qr_data)
    
    # Hash display
    hash_style = ParagraphStyle('Hash', fontSize=8, textColor=COLOR_SLATE,
                                fontName='Courier')
    
    hash_data = [
        [Paragraph('<b>Verification Hash:</b>', 
                  ParagraphStyle('HashLabel', fontSize=9, textColor=COLOR_NAVY))],
        [Paragraph(verification_hash, hash_style)],
    ]
    
    hash_table = Table(hash_data, colWidths=[120*mm])
    hash_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (0, -1), 2),
        ('BOTTOMPADDING', (0, 0), (0, -1), 2),
    ]))
    
    # QR code with caption
    qr_caption = Paragraph('Scan to verify', 
                          ParagraphStyle('QRCaption', fontSize=8, 
                                       textColor=COLOR_SLATE, alignment=TA_CENTER))
    
    qr_data = [[qr_image], [qr_caption]]
    qr_table = Table(qr_data, colWidths=[30*mm])
    qr_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 1), 'CENTER'),
    ]))
    
    # Combine hash and QR
    verify_data = [[hash_table, qr_table]]
    verify_table = Table(verify_data, colWidths=[135*mm, 35*mm])
    verify_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (1, 0), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    
    return verify_table


def create_signature_section_with_seal() -> Table:
    """Create signature section with Great Vibes font and gold seal."""
    # Try to use Great Vibes for captions
    try:
        sig_font = 'GreatVibes'
        sig_size = 10
    except:
        sig_font = 'Times-Italic'
        sig_size = 9
    
    # Create seal drawing (20mm with gold circle)
    seal_drawing = Drawing(25*mm, 25*mm)
    
    # Gold circle border (0.5pt)
    gold_circle = Circle(12.5*mm, 12.5*mm, 10*mm)
    gold_circle.strokeColor = COLOR_GOLD
    gold_circle.strokeWidth = 0.5
    gold_circle.fillColor = None
    seal_drawing.add(gold_circle)
    
    # ProofKit logo inside (checkmark)
    inner_circle = Circle(12.5*mm, 12.5*mm, 8*mm)
    inner_circle.fillColor = COLOR_EMERALD
    inner_circle.strokeColor = None
    seal_drawing.add(inner_circle)
    
    # White checkmark
    checkmark = Path()
    checkmark.moveTo(7*mm, 12.5*mm)
    checkmark.lineTo(10.5*mm, 16*mm)
    checkmark.lineTo(18*mm, 9*mm)
    checkmark.strokeColor = colors.white
    checkmark.strokeWidth = 1.8
    checkmark.strokeLineCap = 1
    checkmark.fillColor = None
    seal_drawing.add(checkmark)
    
    # Signature lines and labels
    sig_style = ParagraphStyle('SigLabel', fontSize=sig_size, 
                               textColor=COLOR_SLATE, fontName=sig_font,
                               alignment=TA_CENTER)
    
    # Small caps style for titles
    title_style = ParagraphStyle('SigTitle', fontSize=8, 
                                textColor=COLOR_SLATE, fontName='Helvetica',
                                alignment=TA_CENTER)
    
    sig_data = [
        ['', '', '', ''],  # Space
        ['_' * 30, '', '_' * 30, ''],  # Signature lines (60mm each)
        [Paragraph('Process Engineer', title_style), '',
         Paragraph('Quality Manager', title_style), seal_drawing],
        ['', '', '', ''],  # Space
        ['_' * 15, '', '_' * 15, ''],  # Date boxes (30mm each)
        [Paragraph('Date', title_style), '', 
         Paragraph('Date', title_style), ''],
    ]
    
    sig_table = Table(sig_data, 
                     colWidths=[60*mm, 20*mm, 60*mm, 30*mm],
                     rowHeights=[5*mm, 8*mm, 8*mm, 3*mm, 8*mm, 8*mm])
    
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 2), (3, 2), 'RIGHT'),
        ('VALIGN', (3, 2), (3, 2), 'BOTTOM'),
        ('SPAN', (3, 2), (3, 3)),  # Seal spans two rows
    ]))
    
    return sig_table


def create_footer(timestamp: Optional[datetime] = None) -> Paragraph:
    """Create footer line."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    footer_style = ParagraphStyle(
        'Footer',
        fontSize=8,
        textColor=COLOR_SLATE,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    footer_text = f"Generated by ProofKit v1.0 | {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    return Paragraph(footer_text, footer_style)


def generate_premium_certificate(
    spec: SpecV1,
    decision: DecisionResult,
    plot_path: Optional[Union[str, FilePath]] = None,
    certificate_no: Optional[str] = None,
    verification_hash: Optional[str] = None,
    output_path: Optional[Union[str, FilePath]] = None,
    timestamp: Optional[datetime] = None
) -> bytes:
    """
    Generate premium certificate with exact specifications.
    
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
    # Register fonts
    register_fonts()
    
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
        # Create document with exact A4 size and margins
        doc = SimpleDocTemplate(
            temp_path,
            pagesize=A4,
            rightMargin=MARGIN,
            leftMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
            title=f"ProofKit Certificate - {certificate_no}"
        )
        
        # Build content
        elements = []
        
        # Header and title
        elements.extend(create_header_section(certificate_no))
        
        # Status badge
        elements.append(create_status_badge(decision))
        elements.append(Spacer(1, 8*mm))
        
        # Two-column tables
        elements.append(create_two_column_tables(spec, decision))
        elements.append(Spacer(1, 6*mm))
        
        # Decision reasons
        reasons = create_decision_reasons(decision)
        if reasons:
            elements.extend(reasons)
            elements.append(Spacer(1, 6*mm))
        
        # Temperature profile (if provided)
        if plot_path and os.path.exists(plot_path):
            try:
                plot_title = ParagraphStyle(
                    'PlotTitle',
                    fontSize=10,
                    textColor=COLOR_NAVY,
                    fontName='Helvetica-Bold',
                    alignment=TA_CENTER,
                    spaceAfter=4*mm
                )
                elements.append(Paragraph("Temperature Profile", plot_title))
                
                # Add plot image
                plot_img = Image(str(plot_path), width=140*mm, height=65*mm)
                plot_img.hAlign = 'CENTER'
                elements.append(plot_img)
                elements.append(Spacer(1, 6*mm))
            except:
                pass
        
        # Verification section
        elements.append(create_verification_section(verification_hash, spec.job.job_id))
        elements.append(Spacer(1, 8*mm))
        
        # Signature section with seal
        elements.append(create_signature_section_with_seal())
        elements.append(Spacer(1, 6*mm))
        
        # Footer
        elements.append(create_footer(timestamp))
        
        # Build PDF with premium canvas
        doc.build(
            elements,
            onFirstPage=create_premium_canvas,
            onLaterPages=create_premium_canvas
        )
        
        # Read PDF bytes
        with open(temp_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Save to output path if provided
        if output_path:
            output_filename = f"proofkit_certificate_{certificate_no}.pdf"
            if isinstance(output_path, str):
                if not output_path.endswith('.pdf'):
                    output_path = output_filename
            elif isinstance(output_path, FilePath):
                output_path = output_path.parent / output_filename
            
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