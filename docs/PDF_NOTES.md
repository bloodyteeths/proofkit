# PDF Generation & Compliance Notes

## Overview

ProofKit generates professional PDF certificates using ReportLab with PDF/A-3 compliance and RFC 3161 timestamping for industrial temperature validation processes.

## PDF/A-3 Compliance

PDF/A-3 is an ISO standard (ISO 19005-3:2012) for long-term document preservation that allows file attachments.

### Key Benefits
- **Long-term readability**: Documents remain accessible decades later
- **Self-contained**: All fonts and resources embedded
- **Tamper evidence**: Digital signatures and metadata integrity
- **File attachments**: Can embed evidence files (CSV data, manifests)

### Implementation Details

Our PDF/A-3u (Unicode) implementation includes:

```python
# XMP metadata for PDF/A identification
pdfaid_part = "3"
pdfaid_conformance = "U"  # Unicode support

# Required metadata fields
metadata = {
    '/Title': 'ProofKit Certificate - {job_id}',
    '/Author': 'ProofKit v1.0', 
    '/Subject': 'Temperature validation certificate',
    '/Creator': 'ProofKit v1.0 - Temperature Validation System',
    '/Producer': 'ReportLab + PyPDF2 (PDF/A-3u compliant)'
}
```

### Compliance Features

1. **Embedded Fonts**: All fonts embedded for consistent rendering
2. **Color Management**: Device-independent color spaces  
3. **Metadata**: Dublin Core and XMP metadata required
4. **File Attachments**: Evidence ZIP and manifest.txt embedded
5. **Digital Signatures**: RFC 3161 timestamp tokens

## Deterministic Output

### Challenge
PDF generation can include timestamps, unique IDs, and other dynamic content that prevents byte-identical outputs.

### Solutions Implemented

1. **Deterministic Timestamps**
   ```python
   # Use fixed timestamp providers for testing
   now_provider = lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
   ```

2. **Consistent Fonts & Layout**
   ```python
   # Use ReportLab built-in fonts (Helvetica family)
   # Avoid system fonts that vary across platforms
   ```

3. **Fixed Color Palette**
   ```python
   # Industry-specific deterministic colors
   INDUSTRY_COLORS = {
       Industry.POWDER: {
           'primary': '#2E5BBA',
           'target': '#219653',
           'threshold': '#D73502'
       }
   }
   ```

4. **Stable Hash Generation**
   ```python
   def compute_pdf_hash(pdf_bytes: bytes) -> str:
       return hashlib.sha256(pdf_bytes).hexdigest()
   ```

### Testing Approach

Due to ReportLab's internal timestamp insertion, perfect byte-for-byte determinism is challenging. Our tests verify:

- **Content consistency**: Same key text content appears
- **Size similarity**: Generated PDFs within reasonable size bounds  
- **Structural validity**: Valid PDF structure and metadata

## Security Features

### Tamper Detection
- SHA-256 hashes of all embedded files
- Root hash computed from all file hashes
- QR codes contain verification URLs

### RFC 3161 Timestamping
```python
# Cryptographic proof of creation time
timestamp_token = generate_rfc3161_timestamp(pdf_content)
xmp_metadata.add_timestamp_info(timestamp_token)
```

### Watermarks & Draft Mode
- `is_draft=True` adds "DRAFT" watermark for non-production use
- Free tier includes "NOT FOR PRODUCTION USE" watermark
- Security micro-text borders on certificate templates

## Template Tiers

### Free Tier
- Basic PDF with watermark
- Temperature graph included
- ProofKit branding

### Starter Tier  
- Clean PDF without watermark
- No temperature graph
- ProofKit branding

### Pro Tier
- Full featured PDF
- Temperature graph included
- Custom logo support
- ProofKit branding

### Business/Enterprise Tiers
- Premium certificate templates
- Header strips and advanced formatting
- Optional branding removal (Enterprise)

## File Structure

```
core/
├── render_pdf.py           # Main PDF generator (routes to templates)
├── render_certificate.py   # ISO-style certificate template
├── render_certificate_pro.py      # Professional certificate template  
└── render_certificate_premium.py  # Premium certificate template
```

## Validation & Testing

### PDF Structure Validation
```python
import pikepdf

# Validate PDF structure
with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
    assert len(pdf.pages) >= 1
    assert pdf.Root is not None
    assert "/Title" in pdf.docinfo
```

### Content Verification
```python
# Extract and verify text content
def verify_pdf_contains_text(pdf_bytes, expected_texts):
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            contents = page.Contents.read_bytes()
            # Verify expected text appears
```

### Regression Testing

Key test coverage:
- ✅ PASS/FAIL/INDETERMINATE banners
- ✅ Fallback sensor detection notes  
- ✅ Required vs present sensor counts
- ✅ PDF/A-3 basic compliance
- ✅ Deterministic output verification
- ✅ Temperature value display
- ✅ Verification hash inclusion

## Common Issues & Solutions

### 1. Font Embedding Failures
**Problem**: Custom fonts not found on deployment systems
**Solution**: Use ReportLab built-in fonts (Helvetica, Times, Courier)

### 2. Image Loading Errors
**Problem**: Plot images not found or corrupted
**Solution**: Validate file existence and add fallback error messages

### 3. PDF/A Compliance Failures
**Problem**: Missing dependencies or malformed metadata
**Solution**: Graceful fallback to basic PDF generation

### 4. Timestamp Variance
**Problem**: RFC 3161 timestamps vary, breaking determinism
**Solution**: Mock timestamp providers in tests

## Dependencies

```toml
# Required for PDF generation
reportlab = ">=4.0.4,<4.1.0"
qrcode = ">=7.4.2,<7.5.0"

# Optional for enhanced features  
PyPDF2 = ">=3.0.0"          # PDF manipulation
pikepdf = ">=9.0.0"         # PDF validation (dev)
cryptography = ">=41.0.0"   # RFC 3161 timestamps
rfc3161ng = ">=2.1.0"       # Timestamp client
lxml = ">=4.9.0"            # XMP metadata
```

## Performance Considerations

- **Memory**: Large CSV files embedded as attachments increase PDF size
- **Generation Time**: RFC 3161 timestamping adds 1-3 seconds per PDF
- **File Size**: Embedded plots and data typically result in 500KB-2MB PDFs
- **Concurrency**: ReportLab is thread-safe for concurrent PDF generation

## Future Enhancements

1. **Digital Signatures**: Add customer PKI certificate signatures
2. **Advanced Templates**: Industry-specific certificate layouts
3. **Multilingual**: Support for multiple languages in certificates
4. **Batch Generation**: Optimize for high-volume certificate production