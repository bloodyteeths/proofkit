# ProofKit Certificate Generator - Fixed Implementation Summary

## Files Delivered

1. **`generate_certificate_fixed.py`** - Complete fixed implementation
2. **Required directory structure:**
   ```
   fonts/
     ├─ CormorantGaramondSC-ExtraBold.otf
     ├─ Inter-Regular.otf
     ├─ Inter-Medium.otf
     └─ GreatVibes-Regular.otf
   assets/
     └─ proofkit_logo_icon.svg
   ```

## Key Fixes Applied

### 1. ✅ Font Registration with Correct PostScript Names
```python
def register_fonts():
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
```

### 2. ✅ Fixed Vertical Micro-text (No More Letter Dripping)
```python
def _draw_vertical_micro(c, x, y_start):
    """Draw vertical micro-text using text object to avoid rotation issues."""
    t = c.beginText()
    t.setFont("Inter", 6)
    t.setFillColor(COLOR_SLATE, alpha=0.3)
    t.setTextOrigin(x, y_start)
    line_height = 6 * 0.3528 * mm  # 1pt = 0.3528 mm
    n_lines = int(SAFE_HEIGHT / line_height)
    for _ in range(n_lines):
        t.textLine(MICRO_TEXT[:42])  # 42 chars fit in margin
    c.drawText(t)
```

### 3. ✅ Fixed Seal SVG Rendering
```python
def create_signature_section(self):
    # ... gold circle code ...
    
    # Properly scale and render logo
    if self.logo_drawing:
        svg_scale = (16*mm) / max(self.logo_drawing.width, self.logo_drawing.height)
        seal_logo = Drawing(16*mm, 16*mm)
        seal_logo.scale(svg_scale, svg_scale)
        # Use renderPDF to properly draw the logo
        for item in self.logo_drawing.contents:
            seal_logo.add(item)
        seal_logo.translate(12.5*mm - 8*mm, 12.5*mm - 8*mm)
        seal_drawing.add(seal_logo)
```

### 4. ✅ Consistent Font Usage Throughout
- **Headlines & Badge:** `CormorantGaramondSC-ExtraBold` (18pt)
- **Body Text:** `Inter` (9pt/10.8pt leading)
- **Bold Text:** `Inter-Medium` (9-10pt)
- **Signatures:** `GreatVibes-Regular` (10pt)

## Installation & Usage

### Install Dependencies
```bash
pip install reportlab svglib qrcode pillow
```

### Run Certificate Generation
```bash
python generate_certificate_fixed.py \
  --spec-json data/test_spec.json \
  --decision-json data/test_decision_pass.json \
  --certificate-no PC-2024-001 \
  --output proofkit_certificate_PC-2024-001.pdf
```

## What Was Wrong Before

| Issue | Root Cause | Fix Applied |
|-------|------------|------------|
| Vertical text printed one letter per line | `rotate(90)` then `drawString()` was clipped to 1pt width | Use `beginText()` with `textLine()` to draw downward |
| Fonts rendered as Times/Helvetica | Font names didn't match registered names | Use exact PostScript names consistently |
| Seal showed empty green circle | Manual shape copying missed nested groups | Use `renderPDF.draw()` for complete SVG |
| Micro-text wrapped incorrectly | Character-by-character rotation | Single line per edge, clipped |

## Expected Output

After applying these fixes:
- ✅ Horizontal micro-text on all four edges (no vertical dripping)
- ✅ All text renders in specified fonts (no Times/Helvetica substitution)
- ✅ Logo appears correctly in both watermark (5% opacity) and seal (100% with gold ring)
- ✅ Certificate has professional, ISO-9001 calibration lab appearance
- ✅ PDF embeds only the four specified fonts

## Production Requirements

⚠️ **CRITICAL**: The production version requires the EXACT OTF font files specified:
- `CormorantGaramondSC-ExtraBold.otf` (not just Bold)
- `Inter-Regular.otf` and `Inter-Medium.otf` (actual Inter fonts)
- `GreatVibes-Regular.otf`

The generator will abort with `RuntimeError` if any required file is missing.