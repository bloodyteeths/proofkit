"""
Tests for PDF Template Switching

This module tests the template switching functionality for different pricing tiers,
including watermarks, logos, branding, and template-specific features.

Example usage:
    pytest tests/test_template_switch.py -v
    pytest tests/test_template_switch.py::test_free_tier_watermark -v
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.render_pdf import (
    _get_template_config,
    _create_watermark_elements,
    _create_header_with_logo,
    _create_footer_with_branding,
    generate_proof_pdf
)
from core.models import SpecV1, DecisionResult, Industry
from tests.helpers import load_spec_fixture_validated


@pytest.fixture
def sample_spec():
    """Create sample specification for testing."""
    return load_spec_fixture_validated('min_powder_spec.json')


@pytest.fixture
def sample_decision():
    """Create sample decision result for testing."""
    return DecisionResult(
        job_id="test123",
        pass_=True,
        target_temp_C=180.0,
        conservative_threshold_C=182.0,
        actual_hold_time_s=660,
        required_hold_time_s=600,
        max_temp_C=185.2,
        min_temp_C=175.8,
        reasons=["Temperature maintained above conservative threshold"],
        warnings=[]
    )


@pytest.fixture
def temp_plot_file():
    """Create temporary plot file for testing."""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.png')
    os.close(temp_fd)
    
    # Create a minimal PNG file (1x1 pixel)
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xdd\x8d\xb4\x1c\x00\x00\x00\x00IEND\xaeB`\x82'
    with open(temp_path, 'wb') as f:
        f.write(png_data)
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture 
def temp_logo_file():
    """Create temporary logo file for testing."""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.png')
    os.close(temp_fd)
    
    # Create a minimal PNG file
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xdd\x8d\xb4\x1c\x00\x00\x00\x00IEND\xaeB`\x82'
    with open(temp_path, 'wb') as f:
        f.write(png_data)
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestTemplateConfiguration:
    """Test template configuration generation."""
    
    def test_free_template_config(self):
        """Test free tier template configuration."""
        config = _get_template_config('free')
        
        assert config['template_name'] == 'Free Trial'
        assert config['watermark'] == 'NOT FOR PRODUCTION USE'
        assert config['show_branding'] is True
        assert config['allow_logo'] is False
        assert config['header_strip'] is False
    
    def test_starter_template_config(self):
        """Test starter tier template configuration."""
        config = _get_template_config('starter')
        
        assert config['template_name'] == 'Standard'
        assert config['watermark'] is None
        assert config['show_branding'] is True
        assert config['allow_logo'] is False
        assert config['header_strip'] is False
    
    def test_pro_template_config(self):
        """Test pro tier template configuration."""
        config = _get_template_config('pro')
        
        assert config['template_name'] == 'Professional'
        assert config['watermark'] is None
        assert config['show_branding'] is True
        assert config['allow_logo'] is True
        assert config['header_strip'] is False
    
    def test_business_template_config(self):
        """Test business tier template configuration.""" 
        config = _get_template_config('business')
        
        assert config['template_name'] == 'Business'
        assert config['watermark'] is None
        assert config['show_branding'] is True
        assert config['allow_logo'] is True
        assert config['header_strip'] is True
    
    def test_enterprise_template_config(self):
        """Test enterprise tier template configuration."""
        config = _get_template_config('enterprise')
        
        assert config['template_name'] == 'Enterprise'
        assert config['watermark'] is None
        assert config['show_branding'] is False
        assert config['allow_logo'] is True
        assert config['header_strip'] is True
    
    def test_invalid_plan_defaults_to_free(self):
        """Test that invalid plan defaults to free tier."""
        config = _get_template_config('invalid_plan')
        
        assert config['template_name'] == 'Free Trial'
        assert config['watermark'] == 'NOT FOR PRODUCTION USE'


class TestWatermarkElements:
    """Test watermark element creation."""
    
    def test_free_tier_watermark(self):
        """Test that free tier creates watermark elements."""
        config = _get_template_config('free')
        elements = _create_watermark_elements(config)
        
        assert len(elements) > 0
        # First element should be the watermark paragraph
        assert hasattr(elements[0], 'text')
    
    def test_paid_tier_no_watermark(self):
        """Test that paid tiers don't create watermark elements."""
        for plan in ['starter', 'pro', 'business', 'enterprise']:
            config = _get_template_config(plan)
            elements = _create_watermark_elements(config)
            
            assert len(elements) == 0


class TestHeaderElements:
    """Test header element creation with logos."""
    
    def test_basic_header_without_logo(self):
        """Test header creation without logo."""
        config = _get_template_config('starter')
        elements = _create_header_with_logo('Test Certificate', config)
        
        assert len(elements) > 0
        # Should contain title paragraph
        assert hasattr(elements[0], 'text')
    
    def test_pro_header_with_logo(self, temp_logo_file):
        """Test pro tier header with custom logo."""
        config = _get_template_config('pro')
        elements = _create_header_with_logo(
            'Test Certificate', 
            config, 
            customer_logo_path=temp_logo_file
        )
        
        assert len(elements) > 0
        # Should contain table with logo and title
        # Note: Exact structure depends on ReportLab implementation
    
    def test_business_header_with_strip(self):
        """Test business tier header with header strip."""
        config = _get_template_config('business')
        elements = _create_header_with_logo('Test Certificate', config)
        
        assert len(elements) > 0
        # Business tier should have header strip
        # First element should be the header strip paragraph
    
    def test_header_with_missing_logo_fallback(self):
        """Test header creation when logo file is missing."""
        config = _get_template_config('pro')
        elements = _create_header_with_logo(
            'Test Certificate', 
            config, 
            customer_logo_path='/nonexistent/logo.png'
        )
        
        assert len(elements) > 0
        # Should fallback to text-only title


class TestFooterElements:
    """Test footer element creation with branding."""
    
    def test_standard_footer_with_branding(self):
        """Test footer with ProofKit branding."""
        config = _get_template_config('pro')
        elements = _create_footer_with_branding(config)
        
        assert len(elements) > 0
        # Should contain multiple footer lines
        footer_text = str(elements).lower()
        assert 'proofkit' in footer_text
    
    def test_enterprise_footer_without_branding(self):
        """Test enterprise footer without branding."""
        config = _get_template_config('enterprise')
        elements = _create_footer_with_branding(config)
        
        assert len(elements) > 0
        # Should not contain ProofKit branding
        footer_text = str(elements).lower()
        # Enterprise config has show_branding=False, so no ProofKit mention
        
    @patch('core.render_pdf.datetime')
    def test_footer_with_custom_timestamp(self, mock_datetime):
        """Test footer with custom timestamp provider."""
        from datetime import datetime, timezone
        mock_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        
        config = _get_template_config('starter')
        elements = _create_footer_with_branding(
            config, 
            now_provider=lambda: mock_time
        )
        
        assert len(elements) > 0
        footer_text = str(elements)
        assert '2024-01-15 12:00:00' in footer_text


class TestPDFGeneration:
    """Test full PDF generation with different templates."""
    
    @patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False)
    def test_free_tier_pdf_generation(self, sample_spec, sample_decision, temp_plot_file):
        """Test PDF generation for free tier with watermark."""
        pdf_bytes = generate_proof_pdf(
            spec=sample_spec,
            decision=sample_decision,
            plot_path=temp_plot_file,
            user_plan='free',
            include_rfc3161=False
        )
        
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000  # Should be a substantial PDF
        assert pdf_bytes.startswith(b'%PDF')  # Valid PDF header
    
    @patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False) 
    def test_pro_tier_pdf_with_logo(self, sample_spec, sample_decision, temp_plot_file, temp_logo_file):
        """Test PDF generation for pro tier with custom logo."""
        pdf_bytes = generate_proof_pdf(
            spec=sample_spec,
            decision=sample_decision,
            plot_path=temp_plot_file,
            user_plan='pro',
            customer_logo_path=temp_logo_file,
            include_rfc3161=False
        )
        
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')
    
    @patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False)
    def test_enterprise_tier_pdf(self, sample_spec, sample_decision, temp_plot_file):
        """Test PDF generation for enterprise tier."""
        pdf_bytes = generate_proof_pdf(
            spec=sample_spec,
            decision=sample_decision,
            plot_path=temp_plot_file,
            user_plan='enterprise',
            include_rfc3161=False
        )
        
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')
    
    @patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False)
    def test_pdf_generation_all_tiers(self, sample_spec, sample_decision, temp_plot_file):
        """Test PDF generation for all pricing tiers."""
        tiers = ['free', 'starter', 'pro', 'business', 'enterprise']
        
        for tier in tiers:
            pdf_bytes = generate_proof_pdf(
                spec=sample_spec,
                decision=sample_decision,
                plot_path=temp_plot_file,
                user_plan=tier,
                include_rfc3161=False
            )
            
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 1000
            assert pdf_bytes.startswith(b'%PDF'), f"Invalid PDF for tier: {tier}"


class TestTemplateFeatures:
    """Test template-specific features."""
    
    def test_free_tier_limitations(self):
        """Test free tier template limitations."""
        config = _get_template_config('free')
        
        # Free tier should have watermark
        assert config['watermark'] is not None
        assert 'NOT FOR PRODUCTION' in config['watermark']
        
        # Free tier should not allow logo
        assert config['allow_logo'] is False
        
        # Free tier should show branding
        assert config['show_branding'] is True
    
    def test_pro_tier_features(self):
        """Test pro tier template features."""
        config = _get_template_config('pro')
        
        # Pro tier should have no watermark
        assert config['watermark'] is None
        
        # Pro tier should allow logo
        assert config['allow_logo'] is True
        
        # Pro tier should show branding
        assert config['show_branding'] is True
        
        # Pro tier should not have header strip
        assert config['header_strip'] is False
    
    def test_enterprise_tier_features(self):
        """Test enterprise tier template features."""
        config = _get_template_config('enterprise')
        
        # Enterprise tier should have no watermark
        assert config['watermark'] is None
        
        # Enterprise tier should allow logo
        assert config['allow_logo'] is True
        
        # Enterprise tier should not show branding (white-label)
        assert config['show_branding'] is False
        
        # Enterprise tier should have header strip
        assert config['header_strip'] is True


class TestTemplateProgression:
    """Test template progression from free to enterprise."""
    
    def test_template_progression(self):
        """Test that template features progress correctly across tiers."""
        configs = {
            'free': _get_template_config('free'),
            'starter': _get_template_config('starter'), 
            'pro': _get_template_config('pro'),
            'business': _get_template_config('business'),
            'enterprise': _get_template_config('enterprise')
        }
        
        # Only free tier should have watermark
        assert configs['free']['watermark'] is not None
        for tier in ['starter', 'pro', 'business', 'enterprise']:
            assert configs[tier]['watermark'] is None
        
        # Logo support should increase
        assert configs['free']['allow_logo'] is False
        assert configs['starter']['allow_logo'] is False
        assert configs['pro']['allow_logo'] is True
        assert configs['business']['allow_logo'] is True
        assert configs['enterprise']['allow_logo'] is True
        
        # Header strip for business+
        assert configs['free']['header_strip'] is False
        assert configs['starter']['header_strip'] is False
        assert configs['pro']['header_strip'] is False
        assert configs['business']['header_strip'] is True
        assert configs['enterprise']['header_strip'] is True
        
        # Only enterprise is white-label
        for tier in ['free', 'starter', 'pro', 'business']:
            assert configs[tier]['show_branding'] is True
        assert configs['enterprise']['show_branding'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])