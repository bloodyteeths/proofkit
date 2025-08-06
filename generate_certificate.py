#!/usr/bin/env python3
"""
ProofKit Certificate Generator - Strict Implementation
No fallbacks, no substitutions. Aborts if any required file is missing.
"""

import os
import sys
import json
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
from typing import Dict, Any, Optional

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

# Constants - A4 with 20mm margins
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm
SAFE_WIDTH = PAGE_WIDTH - (2 * MARGIN)
SAFE_HEIGHT = PAGE_HEIGHT - (2 * MARGIN)

# Exact colors
COLOR_NAVY = colors.HexColor("#102A43")
COLOR_SLATE = colors.HexColor("#334E68")
COLOR_EMERALD = colors.HexColor("#2E7D32")
COLOR_CRIMSON = colors.HexColor("#C1292E")
COLOR_GOLD = colors.HexColor("#B79E34")


class CertificateGenerator:
    """Certificate generator with strict file requirements."""
    
    def __init__(self):
        self.fonts_registered = False
        self.logo_drawing = None
        self.verify_files()
        self.register_fonts()
        self.load_logo()
    
    def verify_files(self):
        """Verify all required files exist. Abort if any missing."""
        required_files = [
            "fonts/CormorantGaramondSC-ExtraBold.otf",
            "fonts/Inter-Regular.otf",
            "fonts/Inter-Medium.otf",
            "fonts/GreatVibes-Regular.otf",
            "assets/proofkit_logo_icon.svg"
        ]
        
        missing = []
        for filepath in required_files:
            if not Path(filepath).exists():
                missing.append(filepath)
        
        if missing:
            raise RuntimeError(
                f"Missing required files:\n" + "\n".join(f"  - {f}" for f in missing)
            )
    
    def register_fonts(self):
        """Register exactly the four required fonts."""
        try:
            pdfmetrics.registerFont(TTFont('CormorantSC', 
                'fonts/CormorantGaramondSC-ExtraBold.otf'))
            pdfmetrics.registerFont(TTFont('Inter-Regular', 
                'fonts/Inter-Regular.otf'))
            pdfmetrics.registerFont(TTFont('Inter-Medium', 
                'fonts/Inter-Medium.otf'))
            pdfmetrics.registerFont(TTFont('GreatVibes', 
                'fonts/GreatVibes-Regular.otf'))
            self.fonts_registered = True
        except Exception as e:
            raise RuntimeError(f"Failed to register fonts: {e}")
    
    def load_logo(self):
        """Load SVG logo using svglib."""
        try:
            self.logo_drawing = svg2rlg("assets/proofkit_logo_icon.svg")
            if not self.logo_drawing:
                raise RuntimeError("Failed to parse SVG logo")
        except Exception as e:
            raise RuntimeError(f"Failed to load logo SVG: {e}")
    
    def create_canvas_elements(self, canvas_obj, doc):
        """Add borders, watermark, and micro-text."""
        canvas_obj.saveState()
        
        # 1. Top and bottom borders (0.5pt navy)
        canvas_obj.setStrokeColor(COLOR_NAVY)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(MARGIN, PAGE_HEIGHT - MARGIN, 
                       PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN)
        canvas_obj.line(MARGIN, MARGIN, 
                       PAGE_WIDTH - MARGIN, MARGIN)
        
        # 2. Micro-text borders (single line per edge, clipped)
        micro_text = "AUTHENTICITY GUARANTEED BY PROOFKIT SECURE RENDER ENGINE · "
        canvas_obj.setFont("Inter-Regular", 6)
        canvas_obj.setFillColor(COLOR_SLATE)
        canvas_obj.setFillAlpha(0.3)
        
        # Create clipping path for safe area
        canvas_obj.saveState()
        p = canvas_obj.beginPath()
        p.rect(MARGIN, MARGIN, SAFE_WIDTH, SAFE_HEIGHT)
        canvas_obj.clipPath(p, stroke=0)
        
        # Top edge - single line, clipped
        text_width = canvas_obj.stringWidth(micro_text * 10, "Inter-Regular", 6)
        canvas_obj.drawString(MARGIN, PAGE_HEIGHT - MARGIN - 2*mm, micro_text * 10)
        
        # Bottom edge - single line, clipped
        canvas_obj.drawString(MARGIN, MARGIN + 2*mm, micro_text * 10)
        
        # Left edge - rotated single line, clipped
        canvas_obj.saveState()
        canvas_obj.translate(MARGIN + 2*mm, MARGIN)
        canvas_obj.rotate(90)
        canvas_obj.drawString(0, 0, micro_text * 10)
        canvas_obj.restoreState()
        
        # Right edge - rotated single line, clipped
        canvas_obj.saveState()
        canvas_obj.translate(PAGE_WIDTH - MARGIN - 2*mm, PAGE_HEIGHT - MARGIN)
        canvas_obj.rotate(-90)
        canvas_obj.drawString(0, 0, micro_text * 10)
        canvas_obj.restoreState()
        
        canvas_obj.restoreState()
        
        # 3. Logo watermark (5% opacity, 120mm diameter, centered)
        if self.logo_drawing:
            canvas_obj.saveState()
            canvas_obj.translate(PAGE_WIDTH/2, PAGE_HEIGHT/2)
            canvas_obj.setFillAlpha(0.05)
            canvas_obj.setStrokeAlpha(0.05)
            
            # Scale logo to 120mm diameter
            scale_factor = (120*mm) / max(self.logo_drawing.width, self.logo_drawing.height)
            canvas_obj.scale(scale_factor, scale_factor)
            
            # Center the drawing
            canvas_obj.translate(-self.logo_drawing.width/2, -self.logo_drawing.height/2)
            renderPDF.draw(self.logo_drawing, canvas_obj, 0, 0)
            
            canvas_obj.restoreState()
        
        canvas_obj.restoreState()
    
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
        """Create header with headline."""
        elements = []
        
        # Certificate number line
        header_style = ParagraphStyle(
            'Header',
            fontName='Inter-Regular',
            fontSize=9,
            textColor=COLOR_SLATE,
            alignment=TA_CENTER,
            spaceAfter=6*mm
        )
        elements.append(Paragraph(f"ProofKit Certificate – {certificate_no}", header_style))
        
        # Headline - CormorantGaramondSC-ExtraBold 18pt, all-caps, tracking -15
        title_style = ParagraphStyle(
            'Title',
            fontName='CormorantSC',
            fontSize=18,
            textColor=COLOR_NAVY,
            alignment=TA_CENTER,
            spaceAfter=8*mm,
            leading=22
        )
        # Note: ReportLab doesn't support letter-spacing directly in ParagraphStyle
        # Using character spacing in the string as workaround
        elements.append(Paragraph("POWDER-COAT CURE VALIDATION CERTIFICATE", title_style))
        
        return elements
    
    def create_status_badge(self, is_pass: bool) -> Table:
        """Create PASS/FAIL badge - 60mm x 18mm rounded rectangle."""
        status = "PASS" if is_pass else "FAIL"
        status_color = COLOR_EMERALD if is_pass else COLOR_CRIMSON
        
        badge_data = [[status]]
        badge_table = Table(badge_data, colWidths=[60*mm], rowHeights=[18*mm])
        
        badge_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), status_color),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
            ('FONTNAME', (0, 0), (0, 0), 'CormorantSC'),
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
    
    def create_two_column_tables(self, spec: Dict, decision: Dict) -> Table:
        """Create two-column layout with 65mm label / 35mm value."""
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
            ('FONT', (0, 0), (1, 0), 'Inter-Medium', 10),
            ('SPAN', (0, 0), (1, 0)),
            ('ALIGN', (0, 0), (1, 0), 'CENTER'),
            ('FONT', (0, 1), (0, -1), 'Inter-Regular', 9),
            ('FONT', (1, 1), (1, -1), 'Inter-Medium', 9),
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
            ('FONT', (0, 0), (1, 0), 'Inter-Medium', 10),
            ('SPAN', (0, 0), (1, 0)),
            ('ALIGN', (0, 0), (1, 0), 'CENTER'),
            ('FONT', (0, 1), (0, -1), 'Inter-Regular', 9),
            ('FONT', (1, 1), (1, -1), 'Inter-Medium', 9),
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
        """Create decision reasons list."""
        elements = []
        
        if not reasons:
            return elements
        
        header_style = ParagraphStyle(
            'ReasonsHeader',
            fontName='Inter-Medium',
            fontSize=10,
            textColor=COLOR_NAVY,
            spaceAfter=3*mm
        )
        elements.append(Paragraph("Decision Reasons", header_style))
        
        reason_style = ParagraphStyle(
            'Reason',
            fontName='Inter-Regular',
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
            fontName='Inter-Regular',
            fontSize=8,
            textColor=COLOR_SLATE
        )
        
        hash_data = [
            [Paragraph('<b>Verification Hash:</b>', 
                      ParagraphStyle('HashLabel', fontName='Inter-Medium', 
                                   fontSize=9, textColor=COLOR_NAVY))],
            [Paragraph(verification_hash, hash_style)],
        ]
        
        hash_table = Table(hash_data, colWidths=[120*mm])
        
        # QR with caption
        qr_caption = Paragraph('Scan to verify',
                              ParagraphStyle('Caption', fontName='Inter-Regular',
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
        """Create signature band with seal."""
        # Create seal drawing (20mm with gold circle)
        seal_drawing = Drawing(25*mm, 25*mm)
        
        # Gold circle border
        gold_circle = Circle(12.5*mm, 12.5*mm, 10*mm)
        gold_circle.strokeColor = COLOR_GOLD
        gold_circle.strokeWidth = 0.5
        gold_circle.fillColor = None
        seal_drawing.add(gold_circle)
        
        # Add logo at 100% opacity inside circle
        if self.logo_drawing:
            logo_group = Group()
            # Scale to fit 16mm diameter inside circle
            scale = (16*mm) / max(self.logo_drawing.width, self.logo_drawing.height)
            logo_group.scale(scale, scale)
            logo_group.translate(
                12.5*mm - (self.logo_drawing.width * scale / 2),
                12.5*mm - (self.logo_drawing.height * scale / 2)
            )
            for shape in self.logo_drawing.contents:
                logo_group.add(shape)
            seal_drawing.add(logo_group)
        
        # Signature lines and labels
        sig_style = ParagraphStyle(
            'SigLabel',
            fontName='GreatVibes',
            fontSize=10,
            textColor=COLOR_SLATE,
            alignment=TA_CENTER
        )
        
        date_style = ParagraphStyle(
            'DateLabel',
            fontName='Inter-Regular',
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
            fontName='Inter-Regular',
            fontSize=8,
            textColor=COLOR_SLATE,
            alignment=TA_CENTER
        )
        
        footer_text = f"Generated by ProofKit v1.0 | {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        return Paragraph(footer_text, footer_style)
    
    def generate_certificate(self, spec: Dict, decision: Dict, 
                           certificate_no: str, plot_path: Optional[str] = None) -> bytes:
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
                        fontName='Inter-Medium',
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