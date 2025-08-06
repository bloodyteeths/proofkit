#!/usr/bin/env python3
"""Generate a demo certificate with the fixed implementation."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO

# Import required libraries
import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Circle, Rect, Group
from svglib.svglib import svg2rlg

# Configuration
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm
SAFE_WIDTH = PAGE_WIDTH - 2*MARGIN
SAFE_HEIGHT = PAGE_HEIGHT - 2*MARGIN

COLOR_NAVY = colors.HexColor("#102A43")
COLOR_SLATE = colors.HexColor("#334E68")
COLOR_EMERALD = colors.HexColor("#2E7D32")
COLOR_CRIMSON = colors.HexColor("#C1292E")
COLOR_GOLD = colors.HexColor("#B79E34")

MICRO_TEXT = "AUTHENTICITY GUARANTEED BY PROOFKIT SECURE RENDER ENGINE · "

# Register available fonts (using what we have for demo)
def register_demo_fonts():
    """Register available fonts for demo."""
    # Use available TTF fonts
    if Path("fonts/CormorantGaramond-Bold.ttf").exists():
        pdfmetrics.registerFont(TTFont("CormorantGaramondSC-ExtraBold", 
                                       "fonts/CormorantGaramond-Bold.ttf"))
    else:
        print("Using Helvetica-Bold for headlines")
    
    if Path("fonts/GreatVibes-Regular.ttf").exists():
        pdfmetrics.registerFont(TTFont("GreatVibes-Regular", 
                                       "fonts/GreatVibes-Regular.ttf"))
    else:
        print("Using Times-Italic for signatures")
    
    # Register Helvetica as Inter substitutes
    # Built-in fonts don't need registration

def load_logo():
    """Load SVG logo."""
    if Path("assets/proofkit_logo_icon.svg").exists():
        return svg2rlg("assets/proofkit_logo_icon.svg")
    return None

def _draw_horizontal_micro(c, y):
    """Draw horizontal micro-text line."""
    c.setFont("Helvetica", 6)  # Using Helvetica as Inter substitute
    c.setFillColor(COLOR_SLATE, alpha=0.3)
    c.drawString(MARGIN, y, (MICRO_TEXT * 10)[:int(SAFE_WIDTH/mm * 2)])

def _draw_vertical_micro(c, x, y_start):
    """Draw vertical micro-text using text object."""
    t = c.beginText()
    t.setFont("Helvetica", 6)  # Using Helvetica as Inter substitute
    t.setFillColor(COLOR_SLATE, alpha=0.3)
    t.setTextOrigin(x, y_start)
    line_height = 6 * 0.3528 * mm  # 1pt = 0.3528 mm
    n_lines = int(SAFE_HEIGHT / line_height)
    for _ in range(n_lines):
        t.textLine(MICRO_TEXT[:42])
    c.drawText(t)

def paint_canvas(canvas_obj, doc):
    """Paint static elements on canvas."""
    canvas_obj.saveState()
    
    # Borders
    canvas_obj.setStrokeColor(COLOR_NAVY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN, PAGE_HEIGHT - MARGIN, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN)
    canvas_obj.line(MARGIN, MARGIN, PAGE_WIDTH - MARGIN, MARGIN)
    
    # Micro-text (fixed implementation)
    _draw_horizontal_micro(canvas_obj, PAGE_HEIGHT - MARGIN + 1*mm)
    _draw_horizontal_micro(canvas_obj, MARGIN - 3*mm)
    _draw_vertical_micro(canvas_obj, MARGIN - 3*mm, MARGIN)
    _draw_vertical_micro(canvas_obj, PAGE_WIDTH - MARGIN + 1*mm, MARGIN)
    
    # Logo watermark
    logo = load_logo()
    if logo:
        canvas_obj.saveState()
        scale = (120*mm) / max(logo.width, logo.height)
        canvas_obj.translate(PAGE_WIDTH/2, PAGE_HEIGHT/2)
        canvas_obj.scale(scale, scale)
        canvas_obj.setFillAlpha(0.05)
        canvas_obj.setStrokeAlpha(0.05)
        renderPDF.draw(logo, canvas_obj, -logo.width/2, -logo.height/2)
        canvas_obj.restoreState()
    
    canvas_obj.restoreState()

def create_qr_code(data):
    """Generate QR code."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
                      box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    img_buffer = BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return Image(img_buffer, width=30*mm, height=30*mm)

def generate_demo_certificate():
    """Generate a demo certificate."""
    register_demo_fonts()
    
    # Test data
    spec = {
        "job_id": "PC-2024-DEMO",
        "target_temp_C": 170.0,
        "hold_time_s": 480,
        "sensor_uncertainty_C": 2.0,
        "conservative_threshold_C": 172.0,
        "max_sample_period_s": 10,
        "allowed_gaps_s": 30,
        "hold_logic": "Continuous"
    }
    
    decision = {
        "pass": True,
        "actual_hold_time_s": 540,
        "required_hold_time_s": 480,
        "max_temp_C": 175.3,
        "min_temp_C": 171.2,
        "conservative_threshold_C": 172.0,
        "reasons": [
            "Temperature maintained above conservative threshold (172.0°C) for required duration",
            "Actual hold time (540s) exceeded minimum requirement (480s) by 12.5%",
            "Maximum ramp rate (3.2°C/min) within acceptable limits",
            "All quality checks passed successfully"
        ],
        "verification_hash": "a7f3d2e8b9c1f4a6e5d8c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2"
    }
    
    certificate_no = "PC-2024-DEMO"
    
    # Create PDF
    pdf_path = "proofkit_certificate_DEMO_FIXED.pdf"
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"ProofKit Certificate - {certificate_no}"
    )
    
    elements = []
    
    # Try to use custom fonts, fall back to built-in
    try:
        title_font = "CormorantGaramondSC-ExtraBold"
    except:
        title_font = "Helvetica-Bold"
    
    try:
        sig_font = "GreatVibes-Regular"
    except:
        sig_font = "Times-Italic"
    
    # Header
    header_style = ParagraphStyle('Header', fontName='Helvetica', fontSize=9,
                                 textColor=COLOR_SLATE, alignment=TA_CENTER,
                                 spaceAfter=6*mm)
    elements.append(Paragraph(f"ProofKit Certificate – {certificate_no}", header_style))
    
    # Title
    title_style = ParagraphStyle('Title', fontName=title_font, fontSize=18,
                                textColor=COLOR_NAVY, alignment=TA_CENTER,
                                spaceAfter=8*mm, leading=22)
    elements.append(Paragraph("POWDER-COAT CURE VALIDATION CERTIFICATE", title_style))
    
    # Status badge
    status = "PASS"
    status_color = COLOR_EMERALD
    
    badge_data = [[status]]
    badge_table = Table(badge_data, colWidths=[60*mm], rowHeights=[18*mm])
    badge_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), status_color),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, 0), title_font),
        ('FONTSIZE', (0, 0), (0, 0), 18),
        ('ROUNDEDCORNERS', [5]),
    ]))
    
    container = Table([['', badge_table, '']], colWidths=[55*mm, 60*mm, 55*mm])
    container.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'CENTER')]))
    elements.append(container)
    elements.append(Spacer(1, 8*mm))
    
    # Two-column tables
    spec_data = [
        ['Specification Details', ''],
        ['Target Temperature', f"{spec['target_temp_C']}°C"],
        ['Hold Time Required', f"{spec['hold_time_s']}s"],
        ['Sensor Uncertainty', f"±{spec['sensor_uncertainty_C']}°C"],
        ['Conservative Threshold', f"{spec['conservative_threshold_C']}°C"],
        ['Max Sample Period', f"{spec.get('max_sample_period_s', 10)}s"],
        ['Allowed Gaps', f"{spec.get('allowed_gaps_s', 30)}s"],
        ['Hold Logic', spec.get('hold_logic', 'Continuous')],
    ]
    
    spec_table = Table(spec_data, colWidths=[52*mm, 28*mm])
    spec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_NAVY),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('FONT', (0, 0), (1, 0), 'Helvetica-Bold', 10),
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('FONT', (0, 1), (0, -1), 'Helvetica', 9),
        ('FONT', (1, 1), (1, -1), 'Helvetica-Bold', 9),
        ('TEXTCOLOR', (0, 1), (0, -1), COLOR_SLATE),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (1, -1), 3),
    ]))
    
    results_data = [
        ['Results Summary', ''],
        ['Status', 'PASS'],
        ['Actual Hold Time', f"{decision['actual_hold_time_s']}s"],
        ['Required Hold Time', f"{decision['required_hold_time_s']}s"],
        ['Max Temperature', f"{decision['max_temp_C']:.1f}°C"],
        ['Min Temperature', f"{decision['min_temp_C']:.1f}°C"],
        ['Conservative Threshold', f"{decision['conservative_threshold_C']:.1f}°C"],
    ]
    
    results_table = Table(results_data, colWidths=[52*mm, 28*mm])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), COLOR_NAVY),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('FONT', (0, 0), (1, 0), 'Helvetica-Bold', 10),
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('FONT', (0, 1), (0, -1), 'Helvetica', 9),
        ('FONT', (1, 1), (1, -1), 'Helvetica-Bold', 9),
        ('TEXTCOLOR', (0, 1), (0, -1), COLOR_SLATE),
        ('TEXTCOLOR', (1, 1), (1, 1), COLOR_EMERALD),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (1, -1), 3),
    ]))
    
    combined = Table([[spec_table, '', results_table]], colWidths=[82*mm, 6*mm, 82*mm])
    combined.setStyle(TableStyle([('VALIGN', (0, 0), (2, 0), 'TOP')]))
    elements.append(combined)
    elements.append(Spacer(1, 6*mm))
    
    # Decision reasons
    header_style = ParagraphStyle('ReasonsHeader', fontName='Helvetica-Bold',
                                 fontSize=10, textColor=COLOR_NAVY, spaceAfter=3*mm)
    elements.append(Paragraph("Decision Reasons", header_style))
    
    reason_style = ParagraphStyle('Reason', fontName='Helvetica', fontSize=9,
                                 textColor=COLOR_SLATE, leftIndent=5*mm,
                                 spaceAfter=2*mm, leading=10.8)
    
    for reason in decision['reasons']:
        elements.append(Paragraph(f"• {reason}", reason_style))
    elements.append(Spacer(1, 6*mm))
    
    # Verification
    qr_image = create_qr_code(decision['verification_hash'])
    
    hash_style = ParagraphStyle('Hash', fontName='Helvetica', fontSize=8,
                               textColor=COLOR_SLATE)
    
    hash_data = [
        [Paragraph('<b>Verification Hash:</b>',
                  ParagraphStyle('HashLabel', fontName='Helvetica-Bold',
                               fontSize=9, textColor=COLOR_NAVY))],
        [Paragraph(decision['verification_hash'], hash_style)],
    ]
    
    hash_table = Table(hash_data, colWidths=[120*mm])
    
    qr_caption = Paragraph('Scan to verify',
                          ParagraphStyle('Caption', fontName='Helvetica',
                                       fontSize=8, textColor=COLOR_SLATE,
                                       alignment=TA_CENTER))
    
    qr_data = [[qr_image], [qr_caption]]
    qr_table = Table(qr_data, colWidths=[30*mm])
    qr_table.setStyle(TableStyle([('ALIGN', (0, 0), (0, 1), 'CENTER')]))
    
    verify_data = [[hash_table, qr_table]]
    verify_table = Table(verify_data, colWidths=[135*mm, 35*mm])
    verify_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (1, 0), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(verify_table)
    elements.append(Spacer(1, 8*mm))
    
    # Signatures with seal
    seal_drawing = Drawing(25*mm, 25*mm)
    
    # Gold circle
    gold_circle = Circle(12.5*mm, 12.5*mm, 10*mm)
    gold_circle.strokeColor = COLOR_GOLD
    gold_circle.strokeWidth = 0.5
    gold_circle.fillColor = None
    seal_drawing.add(gold_circle)
    
    # Add logo to seal
    logo = load_logo()
    if logo:
        svg_scale = (16*mm) / max(logo.width, logo.height)
        seal_logo = Drawing(20*mm, 20*mm)
        seal_logo.scale(svg_scale, svg_scale)
        seal_logo.translate(2.5*mm, 2.5*mm)
        # Add all logo contents
        for item in logo.contents:
            seal_logo.add(item)
        seal_drawing.add(seal_logo)
    
    sig_style = ParagraphStyle('SigLabel', fontName=sig_font, fontSize=10,
                              textColor=COLOR_SLATE, alignment=TA_CENTER)
    
    date_style = ParagraphStyle('DateLabel', fontName='Helvetica', fontSize=8,
                               textColor=COLOR_SLATE, alignment=TA_CENTER)
    
    sig_data = [
        ['', '', '', ''],
        ['_' * 30, '', '_' * 30, ''],
        [Paragraph('Process Engineer', sig_style), '',
         Paragraph('Quality Manager', sig_style), seal_drawing],
        ['', '', '', ''],
        ['_' * 15, '', '_' * 15, ''],
        [Paragraph('Date', date_style), '', Paragraph('Date', date_style), ''],
    ]
    
    sig_table = Table(sig_data, colWidths=[60*mm, 20*mm, 60*mm, 30*mm],
                     rowHeights=[5*mm, 8*mm, 8*mm, 3*mm, 8*mm, 8*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 2), (3, 2), 'RIGHT'),
        ('VALIGN', (3, 2), (3, 2), 'BOTTOM'),
        ('SPAN', (3, 2), (3, 3)),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 6*mm))
    
    # Footer
    footer_style = ParagraphStyle('Footer', fontName='Helvetica', fontSize=8,
                                 textColor=COLOR_SLATE, alignment=TA_CENTER)
    timestamp = datetime.now(timezone.utc)
    footer_text = f"Generated by ProofKit v1.0 | {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    elements.append(Paragraph(footer_text, footer_style))
    
    # Build PDF
    doc.build(elements, onFirstPage=paint_canvas, onLaterPages=paint_canvas)
    
    return pdf_path

if __name__ == "__main__":
    pdf_path = generate_demo_certificate()
    print(f"✅ Generated fixed certificate: {pdf_path}")
    print("\nKey improvements in this version:")
    print("  ✓ Micro-text properly rendered horizontally (no vertical letter dripping)")
    print("  ✓ Two-column layout with fixed 52mm/28mm label/value columns")
    print("  ✓ Status badge: 60mm × 18mm rounded rectangle")
    print("  ✓ Seal with gold circle border (0.5pt #B79E34)")
    print("  ✓ Logo watermark at 5% opacity, 120mm diameter")
    print("  ✓ All margins exactly 20mm (safe area 170×257mm)")
    print("\n📄 Open the PDF to verify the layout matches expectations")