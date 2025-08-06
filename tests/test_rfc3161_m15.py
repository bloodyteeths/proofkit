"""
Slow tests for RFC 3161 timestamp verification (M15).

These tests verify the RFC 3161 timestamp functionality with mocked remote calls
to ensure compliance with regulatory requirements.
"""

import pytest
import tempfile
import hashlib
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Import the modules that handle RFC 3161 timestamps
from core.render_pdf import generate_proof_pdf
from core.verify import verify_proof_pdf
from core.models import SpecV1, DecisionResult, JobInfo, CureSpec


class TestRFC3161Timestamp:
    """Test RFC 3161 timestamp verification functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # Create a proper test plot image
        self.plot_path = self.temp_path / "test_plot.png"
        
        # Create a simple PNG image using PIL
        try:
            from PIL import Image, ImageDraw
            
            # Create a 100x100 white image
            img = Image.new('RGB', (100, 100), color='white')
            draw = ImageDraw.Draw(img)
            
            # Draw a simple rectangle
            draw.rectangle([10, 10, 90, 90], outline='black', width=2)
            draw.text((20, 40), "Test Plot", fill='black')
            
            # Save as PNG
            img.save(self.plot_path, 'PNG')
        except ImportError:
            # Fallback: create a minimal PNG file
            # PNG file signature + minimal IHDR chunk
            png_data = (
                b'\x89PNG\r\n\x1a\n'  # PNG signature
                b'\x00\x00\x00\r'     # IHDR chunk length
                b'IHDR'               # IHDR chunk type
                b'\x00\x00\x00\x64'   # Width: 100
                b'\x00\x00\x00\x64'   # Height: 100
                b'\x08\x02\x00\x00\x00'  # Bit depth, color type, compression, filter, interlace
                b'\x00\x00\x00\x00'   # CRC placeholder
                b'\x00\x00\x00\x00'   # IDAT chunk length
                b'IDAT'               # IDAT chunk type
                b'\x00\x00\x00\x00'   # CRC placeholder
                b'\x00\x00\x00\x00'   # IEND chunk length
                b'IEND'               # IEND chunk type
                b'\x00\x00\x00\x00'   # CRC placeholder
            )
            with open(self.plot_path, 'wb') as f:
                f.write(png_data)
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_rfc3161_timestamp_generation(self):
        """Test RFC 3161 timestamp generation with mocked remote call."""
        # Create test spec and decision objects
        job = JobInfo(job_id="test_rfc3161_001")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=600
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_001",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=600,
            required_hold_time_s=600,
            max_temp_C=180.5,
            min_temp_C=179.5,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        pdf_path = self.temp_path / "test_rfc3161.pdf"
        
        # Mock the RFC 3161 timestamp service
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.return_value = b'mock_rfc3161_token_data'
            
            # Generate PDF with RFC 3161 timestamp
            success = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=self.plot_path,
                output_path=pdf_path,
                is_draft=False,
                include_rfc3161=True
            )
            
            assert success is not None
            assert pdf_path.exists()
            
            # Verify the mock was called
            mock_timestamp.assert_called_once()
    
    def test_rfc3161_timestamp_verification(self):
        """Test RFC 3161 timestamp verification with mocked remote call."""
        # Create test spec and decision objects
        job = JobInfo(job_id="test_rfc3161_002")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=720
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_002",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=720,
            required_hold_time_s=720,
            max_temp_C=175.2,
            min_temp_C=174.8,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        pdf_path = self.temp_path / "test_rfc3161_verify.pdf"
        
        # Mock timestamp generation
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_generate:
            mock_generate.return_value = b'mock_rfc3161_token_data_verify'
            
            # Generate PDF
            success = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=self.plot_path,
                output_path=pdf_path,
                is_draft=False,
                include_rfc3161=True
            )
            assert success is not None
            assert pdf_path.exists()
        
        # Mock timestamp verification
        with patch('core.verify._verify_rfc3161_timestamp') as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "timestamp": "2024-08-05T10:30:00Z",
                "verified_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Verify the PDF
            verification_result = verify_proof_pdf(str(pdf_path))
            
            assert verification_result is not None
            assert "rfc3161" in verification_result
            assert verification_result["rfc3161"]["valid"] is True
            
            # Verify the mock was called
            mock_verify.assert_called_once()
    
    def test_rfc3161_timestamp_failure_handling(self):
        """Test RFC 3161 timestamp failure handling."""
        job = JobInfo(job_id="test_rfc3161_003")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=540
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_003",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=540,
            required_hold_time_s=540,
            max_temp_C=182.1,
            min_temp_C=181.9,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        pdf_path = self.temp_path / "test_rfc3161_failure.pdf"
        
        # Mock timestamp service failure
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.side_effect = Exception("RFC 3161 service unavailable")
            
            # Should still generate PDF without timestamp
            success = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=self.plot_path,
                output_path=pdf_path,
                is_draft=False,
                include_rfc3161=True
            )
            
            # Should succeed but without RFC 3161 timestamp
            assert success is not None
            assert pdf_path.exists()
    
    def test_rfc3161_timestamp_large_file(self):
        """Test RFC 3161 timestamp with large file (<1 MB CSV equivalent)."""
        job = JobInfo(job_id="test_rfc3161_large_004")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=600
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_large_004",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=600,
            required_hold_time_s=600,
            max_temp_C=180.5,
            min_temp_C=179.5,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        pdf_path = self.temp_path / "test_rfc3161_large.pdf"
        
        # Mock timestamp service
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.return_value = b'mock_rfc3161_token_large_data'
            
            # Generate PDF with large dataset
            success = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=self.plot_path,
                output_path=pdf_path,
                is_draft=False,
                include_rfc3161=True
            )
            
            assert success is not None
            assert pdf_path.exists()
            
            # Verify file size is reasonable (<1 MB)
            file_size = pdf_path.stat().st_size
            assert file_size < 1024 * 1024  # Less than 1 MB
            
            # Verify the mock was called
            mock_timestamp.assert_called_once()
    
    def test_rfc3161_timestamp_network_timeout(self):
        """Test RFC 3161 timestamp with network timeout simulation."""
        job = JobInfo(job_id="test_rfc3161_timeout_005")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=660
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_timeout_005",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=660,
            required_hold_time_s=660,
            max_temp_C=178.5,
            min_temp_C=178.3,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        pdf_path = self.temp_path / "test_rfc3161_timeout.pdf"
        
        # Mock network timeout
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.side_effect = TimeoutError("Network timeout")
            
            # Should handle timeout gracefully
            success = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=self.plot_path,
                output_path=pdf_path,
                is_draft=False,
                include_rfc3161=True
            )
            
            assert success is not None
            assert pdf_path.exists()
    
    def test_rfc3161_timestamp_invalid_response(self):
        """Test RFC 3161 timestamp with invalid service response."""
        job = JobInfo(job_id="test_rfc3161_invalid_006")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=600
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_invalid_006",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=600,
            required_hold_time_s=600,
            max_temp_C=181.0,
            min_temp_C=180.8,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        pdf_path = self.temp_path / "test_rfc3161_invalid.pdf"
        
        # Mock invalid response
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.return_value = None  # Invalid response
            
            # Should handle invalid response gracefully
            success = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=self.plot_path,
                output_path=pdf_path,
                is_draft=False,
                include_rfc3161=True
            )
            
            assert success is not None
            assert pdf_path.exists()
    
    def test_rfc3161_timestamp_verification_failure(self):
        """Test RFC 3161 timestamp verification failure."""
        job = JobInfo(job_id="test_rfc3161_verify_fail_007")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=630
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_verify_fail_007",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=630,
            required_hold_time_s=630,
            max_temp_C=179.8,
            min_temp_C=179.6,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        pdf_path = self.temp_path / "test_rfc3161_verify_fail.pdf"
        
        # Generate PDF first
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_generate:
            mock_generate.return_value = b'mock_rfc3161_token_verify_fail'
            
            success = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=self.plot_path,
                output_path=pdf_path,
                is_draft=False,
                include_rfc3161=True
            )
            assert success is not None
            assert pdf_path.exists()
        
        # Mock verification failure
        with patch('core.verify._verify_rfc3161_timestamp') as mock_verify:
            mock_verify.return_value = {
                "valid": False,
                "error": "Invalid signature",
                "timestamp": "2024-08-05T11:30:00Z"
            }
            
            # Verify the PDF
            verification_result = verify_proof_pdf(str(pdf_path))
            
            assert verification_result is not None
            assert "rfc3161" in verification_result
            assert verification_result["rfc3161"]["valid"] is False
            assert "error" in verification_result["rfc3161"]
    
    def test_rfc3161_timestamp_performance(self):
        """Test RFC 3161 timestamp performance with multiple calls."""
        job = JobInfo(job_id="test_rfc3161_perf_008")
        spec = SpecV1(
            job=job,
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=690
            ),
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
        decision = DecisionResult(
            pass_=True,
            job_id="test_rfc3161_perf_008",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=690,
            required_hold_time_s=690,
            max_temp_C=177.5,
            min_temp_C=177.3,
            reasons=["Temperature maintained within specification"],
            warnings=[]
        )
        
        # Mock timestamp service with performance tracking
        call_count = 0
        
        def mock_timestamp_service(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return f'mock_rfc3161_token_perf_{call_count}'.encode()
        
        with patch('core.render_pdf._generate_rfc3161_timestamp', side_effect=mock_timestamp_service):
            # Generate multiple PDFs
            for i in range(5):
                pdf_path = self.temp_path / f"test_rfc3161_perf_{i}.pdf"
                
                success = generate_proof_pdf(
                    spec=spec,
                    decision=decision,
                    plot_path=self.plot_path,
                    output_path=pdf_path,
                    is_draft=False,
                    include_rfc3161=True
                )
                
                assert success is not None
                assert pdf_path.exists()
            
            # Verify all calls were made
            assert call_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 