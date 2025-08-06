#!/usr/bin/env python3
"""
Test version of certificate generator that uses available fonts.
This demonstrates the layout with substitute fonts.
In production, the exact OTF fonts specified must be provided.
"""

import os
import sys
import json
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

# Required imports
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

# Constants
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


class TestCertificateGenerator:
    """Test certificate generator using available fonts."""
    
    def __init__(self):
        self.fonts_registered = False
        self.logo_drawing = None
        self.register_fonts()
        self.load_logo()
    
    def register_fonts(self):
        """Register available fonts for testing."""
        try:
            # Use TTF fonts that exist
            if Path("fonts/CormorantGaramond-Bold.ttf").exists():
                pdfmetrics.registerFont(TTFont('CormorantSC', 
                    'fonts/CormorantGaramond-Bold.ttf'))
            else:
                print("Warning: Using Helvetica-Bold instead of Cormorant")
            
            if Path("fonts/GreatVibes-Regular.ttf").exists():
                pdfmetrics.registerFont(TTFont('GreatVibes', 
                    'fonts/GreatVibes-Regular.ttf'))
            else:
                print("Warning: Using Times-Italic instead of Great Vibes")
            
            # Use Helvetica for Inter substitutes
            self.fonts_registered = True
        except Exception as e:
            print(f"Font registration warning: {e}")
    
    def load_logo(self):
        """Load SVG logo."""
        try:
            if Path("assets/proofkit_logo_icon.svg").exists():
                self.logo_drawing = svg2rlg("assets/proofkit_logo_icon.svg")
            else:
                print("Warning: Logo SVG not found")
        except Exception as e:
            print(f"Logo loading warning: {e}")
    
    def create_canvas_elements(self, canvas_obj, doc):
        """Add borders, watermark, and micro-text."""
        canvas_obj.saveState()
        
        # Top and bottom borders
        canvas_obj.setStrokeColor(COLOR_NAVY)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(MARGIN, PAGE_HEIGHT - MARGIN, 
                       PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN)
        canvas_obj.line(MARGIN, MARGIN, 
                       PAGE_WIDTH - MARGIN, MARGIN)
        
        # Micro-text borders (clipped)
        micro_text = "AUTHENTICITY GUARANTEED BY PROOFKIT SECURE RENDER ENGINE · "
        canvas_obj.setFont("Helvetica", 6)
        canvas_obj.setFillColor(COLOR_SLATE)
        canvas_obj.setFillAlpha(0.3)
        
        # Clipping path
        canvas_obj.saveState()
        p = canvas_obj.beginPath()
        p.rect(MARGIN, MARGIN, SAFE_WIDTH, SAFE_HEIGHT)
        canvas_obj.clipPath(p, stroke=0)
        
        # Draw micro-text (single line per edge, clipped)
        canvas_obj.drawString(MARGIN, PAGE_HEIGHT - MARGIN - 2*mm, micro_text * 10)
        canvas_obj.drawString(MARGIN, MARGIN + 2*mm, micro_text * 10)
        
        canvas_obj.saveState()
        canvas_obj.translate(MARGIN + 2*mm, MARGIN)
        canvas_obj.rotate(90)
        canvas_obj.drawString(0, 0, micro_text * 10)
        canvas_obj.restoreState()
        
        canvas_obj.saveState()
        canvas_obj.translate(PAGE_WIDTH - MARGIN - 2*mm, PAGE_HEIGHT - MARGIN)
        canvas_obj.rotate(-90)
        canvas_obj.drawString(0, 0, micro_text * 10)
        canvas_obj.restoreState()
        
        canvas_obj.restoreState()
        
        # Logo watermark
        if self.logo_drawing:
            canvas_obj.saveState()
            canvas_obj.translate(PAGE_WIDTH/2, PAGE_HEIGHT/2)
            canvas_obj.setFillAlpha(0.05)
            canvas_obj.setStrokeAlpha(0.05)
            
            scale_factor = (120*mm) / max(self.logo_drawing.width, self.logo_drawing.height)
            canvas_obj.scale(scale_factor, scale_factor)
            canvas_obj.translate(-self.logo_drawing.width/2, -self.logo_drawing.height/2)
            renderPDF.draw(self.logo_drawing, canvas_obj, 0, 0)
            
            canvas_obj.restoreState()
        
        canvas_obj.restoreState()
    
    def create_qr_code(self, data: str) -> Image:
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
    
    def generate_certificate(self, spec: dict, decision: dict, 
                           certificate_no: str, plot_path: str = None) -> bytes:
        """Generate the certificate PDF."""
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_fd)
        
        try:
            doc = SimpleDocTemplate(
                temp_path, pagesize=A4,
                rightMargin=MARGIN, leftMargin=MARGIN,
                topMargin=MARGIN, bottomMargin=MARGIN,
                title=f"ProofKit Certificate - {certificate_no}"
            )
            
            elements = []
            
            # Header
            header_style = ParagraphStyle('Header', fontName='Helvetica', fontSize=9,
                                         textColor=COLOR_SLATE, alignment=TA_CENTER,
                                         spaceAfter=6*mm)
            elements.append(Paragraph(f"ProofKit Certificate – {certificate_no}", header_style))
            
            # Title
            try:
                title_font = 'CormorantSC'
            except:
                title_font = 'Helvetica-Bold'
            
            title_style = ParagraphStyle('Title', fontName=title_font, fontSize=18,
                                        textColor=COLOR_NAVY, alignment=TA_CENTER,
                                        spaceAfter=8*mm)
            elements.append(Paragraph("POWDER-COAT CURE VALIDATION CERTIFICATE", title_style))
            
            # Status badge
            status = "PASS" if decision['pass'] else "FAIL"
            status_color = COLOR_EMERALD if decision['pass'] else COLOR_CRIMSON
            
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
                ['Target Temperature', f"{spec.get('target_temp_C', 170)}°C"],
                ['Hold Time Required', f"{spec.get('hold_time_s', 480)}s"],
                ['Sensor Uncertainty', f"±{spec.get('sensor_uncertainty_C', 2)}°C"],
                ['Conservative Threshold', f"{spec.get('conservative_threshold_C', 172)}°C"],
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
            
            status_color2 = COLOR_EMERALD if decision['pass'] else COLOR_CRIMSON
            results_data = [
                ['Results Summary', ''],
                ['Status', 'PASS' if decision['pass'] else 'FAIL'],
                ['Actual Hold Time', f"{decision.get('actual_hold_time_s', 0)}s"],
                ['Required Hold Time', f"{decision.get('required_hold_time_s', 480)}s"],
                ['Max Temperature', f"{decision.get('max_temp_C', 0):.1f}°C"],
                ['Min Temperature', f"{decision.get('min_temp_C', 0):.1f}°C"],
                ['Conservative Threshold', f"{decision.get('conservative_threshold_C', 172):.1f}°C"],
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
                ('TEXTCOLOR', (1, 1), (1, 1), status_color2),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('TOPPADDING', (0, 0), (1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (1, -1), 3),
            ]))
            
            combined = Table([[spec_table, '', results_table]], colWidths=[82*mm, 6*mm, 82*mm])
            combined.setStyle(TableStyle([('VALIGN', (0, 0), (2, 0), 'TOP')]))
            elements.append(combined)
            elements.append(Spacer(1, 6*mm))
            
            # Decision reasons
            if 'reasons' in decision and decision['reasons']:
                header_style = ParagraphStyle('ReasonsHeader', fontName='Helvetica-Bold',
                                             fontSize=10, textColor=COLOR_NAVY, spaceAfter=3*mm)
                elements.append(Paragraph("Decision Reasons", header_style))
                
                reason_style = ParagraphStyle('Reason', fontName='Helvetica', fontSize=9,
                                             textColor=COLOR_SLATE, leftIndent=5*mm,
                                             spaceAfter=2*mm)
                for reason in decision['reasons']:
                    elements.append(Paragraph(f"• {reason}", reason_style))
                elements.append(Spacer(1, 6*mm))
            
            # Verification
            verification_hash = decision.get('verification_hash',
                hashlib.sha256(f"{certificate_no}{decision['pass']}".encode()).hexdigest())
            
            qr_image = self.create_qr_code(verification_hash)
            
            hash_style = ParagraphStyle('Hash', fontName='Helvetica', fontSize=8,
                                       textColor=COLOR_SLATE)
            hash_data = [
                [Paragraph('<b>Verification Hash:</b>',
                          ParagraphStyle('HashLabel', fontName='Helvetica-Bold',
                                       fontSize=9, textColor=COLOR_NAVY))],
                [Paragraph(verification_hash, hash_style)],
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
            gold_circle = Circle(12.5*mm, 12.5*mm, 10*mm)
            gold_circle.strokeColor = COLOR_GOLD
            gold_circle.strokeWidth = 0.5
            gold_circle.fillColor = None
            seal_drawing.add(gold_circle)
            
            if self.logo_drawing:
                logo_group = Group()
                scale = (16*mm) / max(self.logo_drawing.width, self.logo_drawing.height)
                logo_group.scale(scale, scale)
                logo_group.translate(
                    12.5*mm - (self.logo_drawing.width * scale / 2),
                    12.5*mm - (self.logo_drawing.height * scale / 2)
                )
                for shape in self.logo_drawing.contents:
                    logo_group.add(shape)
                seal_drawing.add(logo_group)
            
            try:
                sig_font = 'GreatVibes'
            except:
                sig_font = 'Times-Italic'
            
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
            doc.build(elements, onFirstPage=self.create_canvas_elements,
                     onLaterPages=self.create_canvas_elements)
            
            with open(temp_path, 'rb') as f:
                pdf_bytes = f.read()
            
            return pdf_bytes
            
        finally:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass


def main():
    """Test the certificate generator."""
    # Load test data
    with open('data/test_spec.json', 'r') as f:
        spec = json.load(f)
    
    with open('data/test_decision_pass.json', 'r') as f:
        decision = json.load(f)
    
    # Generate certificate
    generator = TestCertificateGenerator()
    pdf_bytes = generator.generate_certificate(
        spec=spec,
        decision=decision,
        certificate_no="PC-2024-TEST"
    )
    
    # Save PDF
    output_path = "proofkit_certificate_PC-2024-TEST.pdf"
    with open(output_path, 'wb') as f:
        f.write(pdf_bytes)
    
    print(f"✓ Test certificate generated: {output_path}")
    print(f"  Size: {len(pdf_bytes):,} bytes")
    print("\n⚠️  This uses substitute fonts. Production requires exact OTF files.")


if __name__ == "__main__":
    main()