/**
 * ProofKit Analytics Configuration
 * 
 * Centralized configuration for Google Analytics 4 and Google Ads
 * conversion tracking. Update these values for production deployment.
 */

window.ProofKitAnalytics = {
    // Google Analytics 4 Configuration
    ga4: {
        measurementId: 'G-756618Z0XS', // ProofKit GA4 Measurement ID
        
        // Privacy-focused configuration
        config: {
            anonymize_ip: true,
            allow_google_signals: false,
            allow_ad_personalization_signals: false,
            enhanced_measurement: {
                scrolls: true,
                outbound_clicks: true,
                site_search: false,
                video_engagement: false,
                file_downloads: true
            },
            custom_map: {
                'custom_parameter_1': 'industry_type',
                'custom_parameter_2': 'compliance_standard',
                'custom_parameter_3': 'validation_result'
            },
            send_page_view: true,
            session_expires: 30, // minutes
            
            // Debug mode (set to false in production)
            debug_mode: false
        }
    },
    
    // Google Ads Configuration  
    googleAds: {
        conversionId: 'AW-XXXXXXXXX', // TODO: Replace with actual Google Ads Conversion ID
        
        conversions: {
            // Lead generation conversion
            signup: {
                label: 'XXXXXXXXX/xxxxx', // TODO: Replace with actual signup conversion label
                value: 5,
                currency: 'USD'
            },
            
            // Primary conversion - successful validation
            compile_ok: {
                label: 'XXXXXXXXX/xxxxx', // TODO: Replace with actual validation conversion label  
                value: 10,
                currency: 'USD'
            },
            
            // Revenue conversion - purchase/upgrade
            purchase: {
                label: 'XXXXXXXXX/xxxxx', // TODO: Replace with actual purchase conversion label
                currency: 'USD'
                // value is dynamic based on purchase amount
            }
        }
    },
    
    // Event Configuration
    events: {
        // File upload event parameters
        file_upload: {
            category: 'Engagement',
            value: 1
        },
        
        // Successful validation event (primary conversion)
        compile_ok: {
            category: 'Conversion', 
            value: 10
        },
        
        // User signup event (lead conversion)
        sign_up: {
            category: 'Conversion',
            value: 5
        },
        
        // Purchase event (revenue conversion)
        purchase: {
            category: 'Conversion'
            // value is dynamic
        },
        
        // Page view tracking
        page_view: {
            category: 'Engagement'
        },
        
        // Engagement tracking
        engagement: {
            category: 'Engagement',
            values: {
                navigation_click: 1,
                cta_click: 3,
                file_download: 2,
                verify_page_view: 2
            }
        },
        
        // Error tracking
        exception: {
            category: 'Error',
            fatal: false
        }
    },
    
    // Industry-specific configurations
    industries: {
        powder_coat: {
            displayName: 'Powder Coating',
            standards: ['ISO 2368', 'Qualicoat'],
            targetTemp: 180,
            holdTime: 600
        },
        autoclave: {
            displayName: 'Autoclave Sterilization', 
            standards: ['CFR Title 21 Part 11', 'ISO 13485'],
            targetTemp: 132,
            holdTime: 240
        },
        concrete: {
            displayName: 'Concrete Curing',
            standards: ['ASTM C31', 'DOT Specifications'], 
            targetTemp: 23,
            holdTime: 172800 // 48 hours
        },
        coldchain: {
            displayName: 'Cold Chain Storage',
            standards: ['USP 797', 'FDA Guidelines'],
            targetTemp: 4,
            holdTime: 7776000 // 90 days
        },
        sterile: {
            displayName: 'Sterile Processing',
            standards: ['CFR Title 21 Part 11', 'EU GMP Annex 11'],
            targetTemp: 121,
            holdTime: 900
        },
        haccp: {
            displayName: 'HACCP Cooling',
            standards: ['FDA Food Code', 'FSMA'],
            targetTemp: 41,
            holdTime: 21600 // 6 hours
        }
    },
    
    // Cookie consent integration
    consent: {
        // Local storage key for consent status
        storageKey: 'cookie_consent',
        
        // Consent values
        values: {
            analytics: 'analytics',
            essential: 'essential'
        },
        
        // Consent banner timing
        showDelay: 1500, // milliseconds
        
        // Message duration
        messageTimeout: 4000 // milliseconds
    },
    
    // Debug and testing configuration
    debug: {
        // Enable console logging
        enableLogging: true,
        
        // Log event details
        logEvents: true,
        
        // Test mode (prevents actual tracking)
        testMode: false,
        
        // Mock GA4 responses
        mockResponses: false
    },
    
    // Performance configuration
    performance: {
        // Script load timeout
        scriptTimeout: 5000,
        
        // Event batching
        batchEvents: true,
        batchSize: 10,
        batchTimeout: 1000,
        
        // Rate limiting
        maxEventsPerMinute: 60
    }
};

// Environment-specific overrides
(function() {
    const hostname = window.location.hostname;
    
    // Development environment
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.includes('dev')) {
        window.ProofKitAnalytics.debug.enableLogging = true;
        window.ProofKitAnalytics.debug.logEvents = true;
        window.ProofKitAnalytics.ga4.config.debug_mode = true;
        console.log('ProofKit Analytics: Development mode enabled');
    }
    
    // Staging environment  
    if (hostname.includes('staging') || hostname.includes('test')) {
        window.ProofKitAnalytics.debug.testMode = true;
        console.log('ProofKit Analytics: Test mode enabled');
    }
    
    // Production environment
    if (hostname === 'proofkit.dev' || hostname === 'www.proofkit.dev') {
        window.ProofKitAnalytics.debug.enableLogging = false;
        window.ProofKitAnalytics.debug.logEvents = false;
        window.ProofKitAnalytics.ga4.config.debug_mode = false;
        console.log('ProofKit Analytics: Production mode enabled');
    }
})();

// Validation function to check configuration completeness
window.ProofKitAnalytics.validate = function() {
    const config = window.ProofKitAnalytics;
    const issues = [];
    
    // Check GA4 configuration
    if (config.ga4.measurementId === 'G-XXXXXXXXXX' || config.ga4.measurementId === '') {
        issues.push('GA4 Measurement ID not configured');
    }
    
    // Check Google Ads configuration
    if (config.googleAds.conversionId === 'AW-XXXXXXXXX') {
        issues.push('Google Ads Conversion ID not configured');
    }
    
    // Check conversion labels
    Object.keys(config.googleAds.conversions).forEach(key => {
        if (config.googleAds.conversions[key].label.includes('xxxxx')) {
            issues.push(`Google Ads ${key} conversion label not configured`);
        }
    });
    
    // Log results
    if (issues.length > 0) {
        console.warn('ProofKit Analytics Configuration Issues:', issues);
        return false;
    } else {
        console.log('ProofKit Analytics Configuration: All settings valid');
        return true;
    }
};

// Auto-validate configuration on load
document.addEventListener('DOMContentLoaded', function() {
    window.ProofKitAnalytics.validate();
});

// Enhanced tracking functions
window.trackConversion = function(eventName, value, additionalParams = {}) {
  const cookieConsent = localStorage.getItem('cookie_consent');
  if (cookieConsent === 'analytics' && window.gtag) {
    const eventData = {
      'send_to': 'G-756618Z0XS',
      'event_category': 'Certificate',
      'event_label': eventName,
      'value': value || 1,
      ...additionalParams
    };
    
    gtag('event', 'conversion', eventData);
    
    // Google Ads conversion tracking (uncomment when ads ID is available)
    // gtag('event', 'conversion', {
    //   'send_to': 'AW-XXXXXXXXXX/CONVERSION_LABEL',
    //   'value': value || 1,
    //   'currency': 'USD'
    // });
    
    if (window.ProofKitAnalytics.debug.logEvents) {
      console.log('Conversion tracked:', eventName, eventData);
    }
  }
};

// Enhanced ecommerce for certificate generation
window.trackCertificateGeneration = function(jobId, industry, result, additionalData = {}) {
  const cookieConsent = localStorage.getItem('cookie_consent');
  if (cookieConsent === 'analytics' && window.gtag) {
    const eventData = {
      'job_id': jobId,
      'industry': industry,
      'result': result,
      'event_category': 'Certificate',
      'event_label': industry + '_' + result,
      ...additionalData
    };
    
    gtag('event', 'certificate_generated', eventData);
    
    // Track as conversion for successful certificates
    if (result === 'PASS') {
      window.trackConversion('certificate_pass', 1, {
        'job_id': jobId,
        'industry': industry
      });
    }
    
    if (window.ProofKitAnalytics.debug.logEvents) {
      console.log('Certificate generation tracked:', eventData);
    }
  }
};

// Track form submissions
window.trackFormSubmission = function(formType, additionalData = {}) {
  const cookieConsent = localStorage.getItem('cookie_consent');
  if (cookieConsent === 'analytics' && window.gtag) {
    gtag('event', 'form_submit', {
      'event_category': 'Form',
      'event_label': formType,
      'form_type': formType,
      ...additionalData
    });
    
    if (window.ProofKitAnalytics.debug.logEvents) {
      console.log('Form submission tracked:', formType, additionalData);
    }
  }
};

// Track file uploads
window.trackFileUpload = function(fileName, fileSize, fileType = 'csv') {
  const cookieConsent = localStorage.getItem('cookie_consent');
  if (cookieConsent === 'analytics' && window.gtag) {
    gtag('event', 'file_upload', {
      'event_category': 'Upload',
      'event_label': fileType,
      'file_name': fileName,
      'file_size': fileSize,
      'file_type': fileType
    });
    
    if (window.ProofKitAnalytics.debug.logEvents) {
      console.log('File upload tracked:', fileName, fileSize);
    }
  }
};

// Export for module systems (if needed)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = window.ProofKitAnalytics;
}