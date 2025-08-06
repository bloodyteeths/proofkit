#!/usr/bin/env python3
"""ProofKit Certificate Generator - Fixed version with all corrections applied."""

import os
import sys
import json
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

# Required imports - install with: pip install reportlab svglib qrcode pillow
try:
    import qrcode
    from PIL import Image as PILImage
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
except ImportError as e:
    print(f"Missing required dependency: {e}")
    print("Install with: pip install reportlab svglib qrcode pillow")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────
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

REQUIRED = [
    "fonts/CormorantGaramondSC-ExtraBold.otf",
    "fonts/Inter-Regular.otf",
    "fonts/Inter-Medium.otf",
    "fonts/GreatVibes-Regular.otf",
    "assets/proofkit_logo_icon.svg"
]

# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────
def verify_files():
    """Verify all required files exist. Abort if any missing."""
    missing = [p for p in REQUIRED if not Path(p).exists()]
    if missing:
        raise RuntimeError("Missing required files:\n" + "\n".join(" • " + m for m in missing))

def register_fonts():
    """Register fonts with their correct PostScript names."""
    mapping = {
        "CormorantGaramondSC-ExtraBold": "fonts/CormorantGaramondSC-ExtraBold.otf",
        "Inter": "fonts/Inter-Regular.otf",
        "Inter-Medium": "fonts/Inter-Medium.otf",
        "GreatVibes-Regular": "fonts/GreatVibes-Regular.otf",
    }
    for ps_name, path in mapping.items():
        if not Path(path).exists():
            raise RuntimeError(f"Missing font {path}")
        pdfmetrics.registerFont(TTFont(ps_name, path))

def load_logo():
    """Load SVG logo using svglib."""
    logo = svg2rlg("assets/proofkit_logo_icon.svg")
    if not logo:
        raise RuntimeError("Failed to parse SVG logo")
    return logo

def _draw_horizontal_micro(c, y):
    """Draw horizontal micro-text line."""
    c.setFont("Inter", 6)
    c.setFillColor(COLOR_SLATE, alpha=0.3)
    c.drawString(MARGIN, y, (MICRO_TEXT * 10)[:300])

def _draw_vertical_micro(c, x, y_start):
    """Draw vertical micro-text using text object to avoid rotation issues."""
    t = c.beginText()
    t.setFont("Inter", 6)
    t.setFillColor(COLOR_SLATE, alpha=0.3)
    t.setTextOrigin(x, y_start)
    line_height = 6 * 0.3528 * mm  # 1pt = 0.3528 mm
    n_lines = int(SAFE_HEIGHT / line_height)
    for _ in range(n_lines):
        t.textLine(MICRO_TEXT[:42])  # 42 chars ≈ fits in margin
    c.drawText(t)

# ──────────────────────────────────────────────────────────────────
# Canvas painter
# ──────────────────────────────────────────────────────────────────
def paint_static(canvas_obj, doc, logo):
    """Paint static elements: borders, micro-text, watermark."""
    canvas_obj.saveState()
    
    # Top and bottom borders (0.5pt navy)
    canvas_obj.setStrokeColor(COLOR_NAVY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN, PAGE_HEIGHT - MARGIN, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN)
    canvas_obj.line(MARGIN, MARGIN, PAGE_WIDTH - MARGIN, MARGIN)
    
    # Horizontal micro-text
    _draw_horizontal_micro(canvas_obj, PAGE_HEIGHT - MARGIN + 1*mm)
    _draw_horizontal_micro(canvas_obj, MARGIN - 3*mm)
    
    # Vertical micro-text (fixed to avoid rotation issues)
    _draw_vertical_micro(canvas_obj, MARGIN - 3*mm, MARGIN)
    _draw_vertical_micro(canvas_obj, PAGE_WIDTH - MARGIN + 1*mm, MARGIN)
    
    # Logo watermark (5% opacity, 120mm diameter, centered)
    canvas_obj.saveState()
    scale = (120*mm) / max(logo.width, logo.height)
    canvas_obj.translate(PAGE_WIDTH/2, PAGE_HEIGHT/2)
    canvas_obj.scale(scale, scale)
    canvas_obj.setFillAlpha(0.05)
    canvas_obj.setStrokeAlpha(0.05)
    renderPDF.draw(logo, canvas_obj, -logo.width/2, -logo.height/2)
    canvas_obj.restoreState()
    
    canvas_obj.restoreState()

# ──────────────────────────────────────────────────────────────────
# Certificate Generator Class
# ──────────────────────────────────────────────────────────────────
class CertificateGenerator:
    """Certificate generator with strict file requirements."""
    
    def __init__(self):
        verify_files()
        register_fonts()
        self.logo_drawing = load_logo()
    
    def create_canvas_elements(self, canvas_obj, doc):
        """Wrapper for canvas painting."""
        paint_static(canvas_obj, doc, self.logo_drawing)
    
    def create_qr_code(self, data: str) -> Image:
        """Generate QR code image."""
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
        
        return Image(img_buffer, width=30*mm, height=30*mm)
    
    def create_header(self, certificate_no: str) -> list:
        """Create header with headline using correct font names."""
        elements = []
        
        # Certificate number line
        header_style = ParagraphStyle(
            'Header',
            fontName='Inter',  # Fixed: use 'Inter' not 'Inter-Regular'
            fontSize=9,
            textColor=COLOR_SLATE,
            alignment=TA_CENTER,
            spaceAfter=6*mm
        )
        elements.append(Paragraph(f"ProofKit Certificate – {certificate_no}", header_style))
        
        # Headline with correct font name
        title_style = ParagraphStyle(
            'Title',
            fontName='CormorantGaramondSC-ExtraBold',  # Fixed: exact PostScript name
            fontSize=18,
            textColor=COLOR_NAVY,
            alignment=TA_CENTER,
            spaceAfter=8*mm,
            leading=22
        )
        elements.append(Paragraph("POWDER-COAT CURE VALIDATION CERTIFICATE", title_style))
        
        return elements
    
    def create_status_badge(self, is_pass: bool) -> Table:
        """Create PASS/FAIL badge with correct font."""
        status = "PASS" if is_pass else "FAIL"
        status_color = COLOR_EMERALD if is_pass else COLOR_CRIMSON
        
        badge_data = [[status]]
        badge_table = Table(badge_data, colWidths=[60*mm], rowHeights=[18*mm])
        
        badge_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), status_color),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
            ('FONTNAME', (0, 0), (0, 0), 'CormorantGaramondSC-ExtraBold'),  # Fixed
            ('FONTSIZE', (0, 0), (0, 0), 18),
            ('ROUNDEDCORNERS', [5]),
        ]))
        
        # Center the badge
        container_data = [['', badge_table, '']]
        container = Table(container_data, colWidths=[55*mm, 60*mm, 55*mm])
        container.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ]))
        
        return container
    
    def create_two_column_tables(self, spec: dict, decision: dict) -> Table:
        """Create two-column layout with correct font names."""
        # Specification Details
        spec_data = [
            ['Specification Details', ''],
            ['Target Temperature', f"{spec['target_temp_C']}°C"],
            ['Hold Time Required', f"{spec['hold_time_s']}s"],
            ['Sensor Uncertainty', f"±{spec['sensor_uncertainty_C']}°C"],
            ['Conservative Threshold', f"{spec['conservative_threshold_C']}°C"],
            ['Max Sample Period', f"{spec.get('max_sample_period_s', 'N/A')}s"],
            ['Allowed Gaps', f"{spec.get('allowed_gaps_s', 'N/A')}s"],
            ['Hold Logic', spec.get('hold_logic', 'Continuous')],
        ]
        
        spec_table = Table(spec_data, colWidths=[52*mm, 28*mm])
        spec_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), COLOR_NAVY),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('FONT', (0, 0), (1, 0), 'Inter-Medium', 10),  # Fixed
            ('SPAN', (0, 0), (1, 0)),
            ('ALIGN', (0, 0), (1, 0), 'CENTER'),
            ('FONT', (0, 1), (0, -1), 'Inter', 9),  # Fixed
            ('FONT', (1, 1), (1, -1), 'Inter-Medium', 9),  # Fixed
            ('TEXTCOLOR', (0, 1), (0, -1), COLOR_SLATE),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (1, -1), 3),
            ('LEADING', (0, 1), (1, -1), 10.8),
        ]))
        
        # Results Summary
        status = 'PASS' if decision['pass'] else 'FAIL'
        status_color = COLOR_EMERALD if decision['pass'] else COLOR_CRIMSON
        
        results_data = [
            ['Results Summary', ''],
            ['Status', status],
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
            ('FONT', (0, 0), (1, 0), 'Inter-Medium', 10),  # Fixed
            ('SPAN', (0, 0), (1, 0)),
            ('ALIGN', (0, 0), (1, 0), 'CENTER'),
            ('FONT', (0, 1), (0, -1), 'Inter', 9),  # Fixed
            ('FONT', (1, 1), (1, -1), 'Inter-Medium', 9),  # Fixed
            ('TEXTCOLOR', (0, 1), (0, -1), COLOR_SLATE),
            ('TEXTCOLOR', (1, 1), (1, 1), status_color),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (1, -1), 3),
            ('LEADING', (0, 1), (1, -1), 10.8),
        ]))
        
        # Combine tables
        combined_data = [[spec_table, '', results_table]]
        combined = Table(combined_data, colWidths=[82*mm, 6*mm, 82*mm])
        combined.setStyle(TableStyle([
            ('VALIGN', (0, 0), (2, 0), 'TOP'),
        ]))
        
        return combined
    
    def create_decision_reasons(self, reasons: list) -> list:
        """Create decision reasons list with correct fonts."""
        elements = []
        
        if not reasons:
            return elements
        
        header_style = ParagraphStyle(
            'ReasonsHeader',
            fontName='Inter-Medium',  # Fixed
            fontSize=10,
            textColor=COLOR_NAVY,
            spaceAfter=3*mm
        )
        elements.append(Paragraph("Decision Reasons", header_style))
        
        reason_style = ParagraphStyle(
            'Reason',
            fontName='Inter',  # Fixed
            fontSize=9,
            textColor=COLOR_SLATE,
            leftIndent=5*mm,
            spaceAfter=2*mm,
            leading=10.8
        )
        
        for reason in reasons:
            elements.append(Paragraph(f"• {reason}", reason_style))
        
        return elements
    
    def create_verification_section(self, verification_hash: str) -> Table:
        """Create verification with hash and QR."""
        qr_image = self.create_qr_code(verification_hash)
        
        hash_style = ParagraphStyle(
            'Hash',
            fontName='Inter',  # Fixed
            fontSize=8,
            textColor=COLOR_SLATE
        )
        
        hash_data = [
            [Paragraph('<b>Verification Hash:</b>', 
                      ParagraphStyle('HashLabel', fontName='Inter-Medium',  # Fixed
                                   fontSize=9, textColor=COLOR_NAVY))],
            [Paragraph(verification_hash, hash_style)],
        ]
        
        hash_table = Table(hash_data, colWidths=[120*mm])
        
        # QR with caption
        qr_caption = Paragraph('Scan to verify',
                              ParagraphStyle('Caption', fontName='Inter',  # Fixed
                                           fontSize=8, textColor=COLOR_SLATE,
                                           alignment=TA_CENTER))
        
        qr_data = [[qr_image], [qr_caption]]
        qr_table = Table(qr_data, colWidths=[30*mm])
        qr_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 1), 'CENTER'),
        ]))
        
        # Combine
        verify_data = [[hash_table, qr_table]]
        verify_table = Table(verify_data, colWidths=[135*mm, 35*mm])
        verify_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (1, 0), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        
        return verify_table
    
    def create_signature_section(self) -> Table:
        """Create signature band with properly rendered seal."""
        # Create seal drawing with gold circle
        seal_drawing = Drawing(25*mm, 25*mm)
        
        # Gold circle border
        gold_circle = Circle(12.5*mm, 12.5*mm, 10*mm)
        gold_circle.strokeColor = COLOR_GOLD
        gold_circle.strokeWidth = 0.5
        gold_circle.fillColor = None
        seal_drawing.add(gold_circle)
        
        # Fixed: Properly scale and add logo to seal
        if self.logo_drawing:
            svg_scale = (16*mm) / max(self.logo_drawing.width, self.logo_drawing.height)
            seal_logo = Drawing(16*mm, 16*mm)
            seal_logo.scale(svg_scale, svg_scale)
            # Use renderPDF to properly draw the logo
            for item in self.logo_drawing.contents:
                seal_logo.add(item)
            # Position logo in center of seal
            seal_logo.translate(12.5*mm - 8*mm, 12.5*mm - 8*mm)
            seal_drawing.add(seal_logo)
        
        # Signature lines and labels
        sig_style = ParagraphStyle(
            'SigLabel',
            fontName='GreatVibes-Regular',  # Fixed: exact name
            fontSize=10,
            textColor=COLOR_SLATE,
            alignment=TA_CENTER
        )
        
        date_style = ParagraphStyle(
            'DateLabel',
            fontName='Inter',  # Fixed
            fontSize=8,
            textColor=COLOR_SLATE,
            alignment=TA_CENTER
        )
        
        sig_data = [
            ['', '', '', ''],
            ['_' * 30, '', '_' * 30, ''],
            [Paragraph('Process Engineer', sig_style), '',
             Paragraph('Quality Manager', sig_style), seal_drawing],
            ['', '', '', ''],
            ['_' * 15, '', '_' * 15, ''],
            [Paragraph('Date', date_style), '', Paragraph('Date', date_style), ''],
        ]
        
        sig_table = Table(sig_data,
                         colWidths=[60*mm, 20*mm, 60*mm, 30*mm],
                         rowHeights=[5*mm, 8*mm, 8*mm, 3*mm, 8*mm, 8*mm])
        
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (2, -1), 'CENTER'),
            ('ALIGN', (3, 2), (3, 2), 'RIGHT'),
            ('VALIGN', (3, 2), (3, 2), 'BOTTOM'),
            ('SPAN', (3, 2), (3, 3)),
        ]))
        
        return sig_table
    
    def create_footer(self, timestamp: datetime) -> Paragraph:
        """Create footer line."""
        footer_style = ParagraphStyle(
            'Footer',
            fontName='Inter',  # Fixed
            fontSize=8,
            textColor=COLOR_SLATE,
            alignment=TA_CENTER
        )
        
        footer_text = f"Generated by ProofKit v1.0 | {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        return Paragraph(footer_text, footer_style)
    
    def generate_certificate(self, spec: dict, decision: dict, 
                           certificate_no: str, plot_path: str = None) -> bytes:
        """Generate the certificate PDF."""
        # Create temp file
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
            
            # Build content
            elements = []
            
            # Header and title
            elements.extend(self.create_header(certificate_no))
            
            # Status badge
            elements.append(self.create_status_badge(decision['pass']))
            elements.append(Spacer(1, 8*mm))
            
            # Two-column tables
            elements.append(self.create_two_column_tables(spec, decision))
            elements.append(Spacer(1, 6*mm))
            
            # Decision reasons
            if 'reasons' in decision:
                elements.extend(self.create_decision_reasons(decision['reasons']))
                elements.append(Spacer(1, 6*mm))
            
            # Temperature plot (if provided)
            if plot_path and os.path.exists(plot_path):
                try:
                    plot_title = ParagraphStyle(
                        'PlotTitle',
                        fontName='Inter-Medium',  # Fixed
                        fontSize=10,
                        textColor=COLOR_NAVY,
                        alignment=TA_CENTER,
                        spaceAfter=4*mm
                    )
                    elements.append(Paragraph("Temperature Profile", plot_title))
                    
                    plot_img = Image(plot_path, width=140*mm, height=65*mm)
                    plot_img.hAlign = 'CENTER'
                    elements.append(plot_img)
                    elements.append(Spacer(1, 6*mm))
                except:
                    pass  # Skip if plot cannot be loaded
            
            # Verification
            verification_hash = decision.get('verification_hash', 
                hashlib.sha256(f"{certificate_no}{decision['pass']}".encode()).hexdigest())
            elements.append(self.create_verification_section(verification_hash))
            elements.append(Spacer(1, 8*mm))
            
            # Signatures with seal
            elements.append(self.create_signature_section())
            elements.append(Spacer(1, 6*mm))
            
            # Footer
            elements.append(self.create_footer(datetime.now(timezone.utc)))
            
            # Build PDF
            doc.build(
                elements,
                onFirstPage=self.create_canvas_elements,
                onLaterPages=self.create_canvas_elements
            )
            
            # Read PDF bytes
            with open(temp_path, 'rb') as f:
                pdf_bytes = f.read()
            
            return pdf_bytes
            
        finally:
            # Clean up
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass


def main():
    """Main entry point for certificate generation."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate ProofKit Certificate')
    parser.add_argument('--spec-json', required=True, help='Path to specification JSON')
    parser.add_argument('--decision-json', required=True, help='Path to decision JSON')
    parser.add_argument('--certificate-no', required=True, help='Certificate number')
    parser.add_argument('--plot-path', help='Optional path to temperature plot image')
    parser.add_argument('--output', help='Output PDF path (default: proofkit_certificate_{certificate_no}.pdf)')
    
    args = parser.parse_args()
    
    # Load JSON data
    with open(args.spec_json, 'r') as f:
        spec = json.load(f)
    
    with open(args.decision_json, 'r') as f:
        decision = json.load(f)
    
    # Generate certificate
    try:
        generator = CertificateGenerator()
        pdf_bytes = generator.generate_certificate(
            spec=spec,
            decision=decision,
            certificate_no=args.certificate_no,
            plot_path=args.plot_path
        )
        
        # Save PDF
        output_path = args.output or f"proofkit_certificate_{args.certificate_no}.pdf"
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        
        print(f"✓ Certificate generated: {output_path}")
        print(f"  Size: {len(pdf_bytes):,} bytes")
        
    except RuntimeError as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()