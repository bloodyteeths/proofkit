#!/usr/bin/env python3
"""PDF inspector for QA validation with strong assertions."""

import sys
import json
import re
from pathlib import Path
from typing import Dict, Optional

def inspect_pdf_text(pdf_path: str) -> Dict:
    """Extract text and metadata from PDF with assertions."""
    result = {
        "path": pdf_path,
        "exists": Path(pdf_path).exists(),
        "size_bytes": 0,
        "banner": None,
        "banner_valid": False,
        "job_id": None,
        "hash": None,
        "verify_link": None,
        "qr_detected": False,
        "pdfa": False,
        "pdfa3": False,
        "embedded_files": 0,
        "assertions_passed": False
    }
    
    if not result["exists"]:
        return result
    
    pdf_bytes = Path(pdf_path).read_bytes()
    result["size_bytes"] = len(pdf_bytes)
    
    # Try to extract text content (basic approach)
    text = pdf_bytes.decode('latin-1', errors='ignore')
    
    # Assert banner exists and is valid
    if "PASS" in text and ("Certificate" in text or "Validation" in text):
        result["banner"] = "PASS"
        result["banner_valid"] = True
    elif "FAIL" in text and ("Certificate" in text or "Validation" in text):
        result["banner"] = "FAIL"
        result["banner_valid"] = True
    elif "INDETERMINATE" in text:
        result["banner"] = "INDETERMINATE"
        result["banner_valid"] = True
    
    # Look for job ID pattern
    job_id_match = re.search(r'Job ID[:\s]+([a-zA-Z0-9_-]+)', text)
    if not job_id_match:
        job_id_match = re.search(r'ID[:\s]+([a-zA-Z0-9_-]{8,})', text)
    if job_id_match:
        result["job_id"] = job_id_match.group(1)
    
    # Look for SHA-256 hash
    hash_match = re.search(r'SHA-?256[:\s]+([a-f0-9]{64})', text, re.IGNORECASE)
    if not hash_match:
        hash_match = re.search(r'Root Hash[:\s]+([a-f0-9]{64})', text, re.IGNORECASE)
    if not hash_match:
        hash_match = re.search(r'([a-f0-9]{64})', text)
    if hash_match:
        result["hash"] = hash_match.group(1)
    
    # Look for verify link
    verify_match = re.search(r'(https?://[^\s]+/verify/[a-zA-Z0-9_-]+)', text)
    if verify_match:
        result["verify_link"] = verify_match.group(1)
    
    # Check for QR code marker
    if "QR" in text or "/BitsPerComponent" in text or "QRCode" in text:
        result["qr_detected"] = True
    
    # Check for PDF/A markers
    if "PDF/A" in text or "pdfaid" in text:
        result["pdfa"] = True
    
    # Check for PDF/A-3 specific markers (embedded files)
    if "/EmbeddedFiles" in text or "/AF" in text or "PDF/A-3" in text:
        result["pdfa3"] = True
        # Count embedded files
        embedded_count = text.count("/EmbeddedFile")
        if embedded_count > 0:
            result["embedded_files"] = embedded_count
    
    # Try with pikepdf if available for stronger checks
    try:
        import pikepdf
        with pikepdf.open(pdf_path) as pdf:
            result["pages"] = len(pdf.pages)
            
            # Check for PDF/A metadata
            if "/Metadata" in pdf.Root:
                result["pdfa"] = True
                metadata = pdf.Root.Metadata
                if metadata and hasattr(metadata, 'read_bytes'):
                    xmp = metadata.read_bytes().decode('utf-8', errors='ignore')
                    if 'pdfaid:part>3' in xmp:
                        result["pdfa3"] = True
            
            # Check for embedded files (PDF/A-3)
            if "/Names" in pdf.Root:
                if "/EmbeddedFiles" in pdf.Root.Names:
                    result["pdfa3"] = True
                    result["embedded_files"] = len(pdf.Root.Names.EmbeddedFiles) if hasattr(pdf.Root.Names.EmbeddedFiles, '__len__') else 1
            
            # Extract metadata
            if pdf.docinfo:
                result["metadata"] = {
                    "title": str(pdf.docinfo.get("/Title", "")),
                    "author": str(pdf.docinfo.get("/Author", "")),
                    "producer": str(pdf.docinfo.get("/Producer", "")),
                    "creator": str(pdf.docinfo.get("/Creator", ""))
                }
            
            # Extract text from pages for better banner detection
            for page in pdf.pages:
                if hasattr(page, 'extract_text'):
                    page_text = str(page.extract_text())
                    if "PASS" in page_text and result["banner"] != "FAIL":
                        result["banner"] = "PASS"
                        result["banner_valid"] = True
                    elif "FAIL" in page_text and result["banner"] != "PASS":
                        result["banner"] = "FAIL"
                        result["banner_valid"] = True
                    
    except ImportError:
        pass
    except Exception as e:
        result["pikepdf_error"] = str(e)
    
    # Try with PyPDF2 as fallback
    if "pages" not in result:
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                result["pages"] = len(reader.pages)
                
                # Extract text from all pages
                full_text = ""
                for page in reader.pages:
                    full_text += page.extract_text()
                
                # Re-check banner in extracted text
                if "PASS" in full_text and result["banner"] != "FAIL":
                    result["banner"] = "PASS"
                    result["banner_valid"] = True
                elif "FAIL" in full_text and result["banner"] != "PASS":
                    result["banner"] = "FAIL"
                    result["banner_valid"] = True
                    
        except ImportError:
            pass
        except Exception as e:
            result["pypdf2_error"] = str(e)
    
    # Perform assertions
    assertions_passed = True
    assertions = []
    
    # Assert banner is valid
    if not result["banner_valid"]:
        assertions.append("Banner must be PASS/FAIL/INDETERMINATE")
        assertions_passed = False
    
    # Assert PDF/A-3 compliance (should have embedded files)
    if result["pdfa3"] and result["embedded_files"] < 1:
        assertions.append("PDF/A-3 should have at least 1 embedded file")
        assertions_passed = False
    
    # Assert hash exists
    if not result["hash"]:
        assertions.append("Root hash not found")
        assertions_passed = False
    
    result["assertions_passed"] = assertions_passed
    result["assertions"] = assertions
    
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: python inspect_pdf.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    result = inspect_pdf_text(pdf_path)
    
    print(json.dumps(result, indent=2))
    
    # Quick summary with assertions
    print("\n=== PDF Inspection Summary ===")
    print(f"File: {pdf_path}")
    print(f"Exists: {'✓' if result['exists'] else '✗'}")
    
    if result['exists']:
        print(f"Size: {result['size_bytes']:,} bytes")
        print(f"Banner: {result['banner'] or 'Not found'} {'✓' if result['banner_valid'] else '✗'}")
        print(f"Job ID: {result['job_id'] or 'Not found'}")
        print(f"Hash: {result['hash'][:16]}..." if result['hash'] else "Hash: Not found")
        print(f"PDF/A: {'✓' if result['pdfa'] else '✗'}")
        print(f"PDF/A-3: {'✓' if result['pdfa3'] else '✗'}")
        print(f"Embedded Files: {result['embedded_files']}")
        print(f"QR Code: {'✓' if result['qr_detected'] else '✗'}")
        
        if not result['assertions_passed']:
            print("\n⚠️ Assertions Failed:")
            for assertion in result.get('assertions', []):
                print(f"  - {assertion}")
        else:
            print("\n✅ All assertions passed")
    
    # Exit with error if assertions failed
    if not result['assertions_passed']:
        sys.exit(1)

if __name__ == "__main__":
    main()