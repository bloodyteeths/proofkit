/**
 * ProofKit Web Application JavaScript
 * 
 * Handles file upload, drag & drop, form validation, and UI interactions
 * for the ProofKit temperature log validation tool.
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    initializeFileUpload();
    initializeFormValidation();
    initializeProgressIndicator();
    initializeCookieConsent();
    initializePurchaseHandlers();
});

/**
 * Global helper function for single certificate purchase
 */
window.buySingleCert = function(event) {
    if (event) event.preventDefault();
    
    fetch('/api/buy-single', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            certificate_count: 1,
            success_url: window.location.origin + '/dashboard?purchase=success',
            cancel_url: window.location.href
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.checkout_url) {
            window.location.href = data.checkout_url;
        } else {
            throw new Error('No checkout URL received');
        }
    })
    .catch(error => {
        console.error('Purchase failed:', error);
        alert('Purchase failed. Please try again.');
    });
    
    return false;
};

/**
 * Initialize purchase-related event handlers
 */
function initializePurchaseHandlers() {
    // Add click handlers for any buy-single links
    document.querySelectorAll('a[href="/api/buy-single"]').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            window.buySingleCert(e);
        });
    });
}

/**
 * Initialize file upload functionality with drag & drop support
 */
function initializeFileUpload() {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('csv_file');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    
    if (!uploadArea || !fileInput) return;
    
    // File selection handler
    fileInput.addEventListener('change', function(e) {
        handleFileSelection(e.target.files[0]);
    });
    
    // Drag and drop handlers
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const file = files[0];
            
            // Set the file on the input element
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
            
            handleFileSelection(file);
        }
    });
    
    function handleFileSelection(file) {
        if (!file) {
            if (fileInfo) fileInfo.style.display = 'none';
            return;
        }
        
        // Validate file type
        if (!file.name.toLowerCase().endsWith('.csv')) {
            showError('Please select a CSV file.');
            // Clear the file input
            fileInput.value = '';
            if (fileInfo) fileInfo.style.display = 'none';
            return;
        }
        
        // Validate file size (10MB limit)
        const maxSize = 10 * 1024 * 1024; // 10MB in bytes
        if (file.size > maxSize) {
            showError('File size exceeds 10MB limit. Please select a smaller file.');
            // Clear the file input
            fileInput.value = '';
            if (fileInfo) fileInfo.style.display = 'none';
            return;
        }
        
        // Show file info
        if (fileName) fileName.textContent = file.name;
        if (fileSize) fileSize.textContent = formatFileSize(file.size);
        if (fileInfo) fileInfo.style.display = 'block';
        
        // Clear any previous errors
        clearErrors();
        
        console.log('File selected successfully:', file.name);
    }
}

/**
 * Initialize form validation
 */
function initializeFormValidation() {
    const form = document.getElementById('upload-form');
    const specJsonField = document.getElementById('spec_json');
    
    if (!form || !specJsonField) return;
    
    // Initialize form-to-JSON conversion
    initializeSpecFormToJSON();
    
    // Form submission validation
    form.addEventListener('htmx:beforeRequest', function(e) {
        // Convert form to JSON before validation
        updateSpecJSONFromForm();
        
        if (!validateForm()) {
            e.preventDefault();
            return false;
        }
        
        // Log form submission for debugging
        console.log('Form submission started with file:', 
            document.getElementById('csv_file')?.files?.[0]?.name || 'No file');
    });
}

/**
 * Initialize the form-to-JSON conversion system
 */
function initializeSpecFormToJSON() {
    // Update JSON whenever form fields change
    const formFields = [
        'job_id', 'target_temp', 'hold_time', 'sensor_uncertainty',
        'max_ramp_rate', 'max_time_to_threshold'
    ];
    
    formFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', updateSpecJSONFromForm);
            field.addEventListener('change', updateSpecJSONFromForm);
        }
    });
    
    // Handle radio buttons
    const radioButtons = document.querySelectorAll('input[type="radio"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', updateSpecJSONFromForm);
    });
    
    // Initialize with current values
    updateSpecJSONFromForm();
}

/**
 * Convert form values to JSON specification
 */
function updateSpecJSONFromForm() {
    const jobId = document.getElementById('job_id')?.value || 'batch_001';
    const targetTemp = parseFloat(document.getElementById('target_temp')?.value) || 180.0;
    const holdTime = parseInt(document.getElementById('hold_time')?.value) || 600;
    const sensorUncertainty = parseFloat(document.getElementById('sensor_uncertainty')?.value) || 2.0;
    const maxRampRate = parseFloat(document.getElementById('max_ramp_rate')?.value) || 15.0;
    const maxTimeToThreshold = parseInt(document.getElementById('max_time_to_threshold')?.value) || 900;
    
    // Get selected radio button values
    const holdLogic = document.querySelector('input[name="hold_logic"]:checked')?.value || 'continuous';
    const sensorMode = document.querySelector('input[name="sensor_mode"]:checked')?.value || 'min_of_set';
    
    const spec = {
        "version": "1.0",
        "job": {
            "job_id": jobId
        },
        "spec": {
            "method": "PMT",
            "target_temp_C": targetTemp,
            "hold_time_s": holdTime,
            "sensor_uncertainty_C": sensorUncertainty
        },
        "data_requirements": {
            "max_sample_period_s": 30.0,
            "allowed_gaps_s": 60.0
        },
        "sensor_selection": {
            "mode": sensorMode,
            "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
            "require_at_least": 1
        },
        "logic": {
            "continuous": holdLogic === 'continuous',
            "max_total_dips_s": holdLogic === 'cumulative' ? 60 : 0
        },
        "preconditions": {
            "max_ramp_rate_C_per_min": maxRampRate,
            "max_time_to_threshold_s": maxTimeToThreshold
        },
        "reporting": {
            "units": "C",
            "language": "en",
            "timezone": "UTC"
        }
    };
    
    const specJsonField = document.getElementById('spec_json');
    if (specJsonField) {
        specJsonField.value = JSON.stringify(spec, null, 2);
    }
}

/**
 * Initialize progress indicator for HTMX requests
 */
function initializeProgressIndicator() {
    const progressDiv = document.getElementById('progress');
    const form = document.getElementById('upload-form');
    let fileState = null; // Store file state
    
    // Store file state before request
    document.body.addEventListener('htmx:beforeRequest', function(e) {
        if (progressDiv) {
            progressDiv.style.display = 'block';
        }
        
        // Store current file state
        const fileInput = document.getElementById('csv_file');
        if (fileInput && fileInput.files && fileInput.files.length > 0) {
            fileState = {
                file: fileInput.files[0],
                name: fileInput.files[0].name,
                size: fileInput.files[0].size
            };
            console.log('Stored file state:', fileState.name);
        }
    });
    
    // Restore file state after request
    document.body.addEventListener('htmx:afterRequest', function(e) {
        if (progressDiv) {
            progressDiv.style.display = 'none';
        }
        
        // Restore file state regardless of success/failure
        if (fileState) {
            restoreFileState(fileState);
        }
    });
    
    // Handle HTMX afterSwap to set up event handlers for dynamically loaded content
    document.body.addEventListener('htmx:afterSwap', function(e) {
        // Set up reload button handler
        var reloadBtn = document.getElementById('reload-btn');
        if (reloadBtn && !reloadBtn.hasAttribute('data-handler-attached')) {
            reloadBtn.setAttribute('data-handler-attached', 'true');
            reloadBtn.addEventListener('click', function() {
                location.reload();
            });
        }
        
        // Set up copy QA link button handler
        var copyQABtn = document.getElementById('copy-qa-link-btn');
        if (copyQABtn && !copyQABtn.hasAttribute('data-handler-attached')) {
            copyQABtn.setAttribute('data-handler-attached', 'true');
            copyQABtn.addEventListener('click', function() {
                var qaLinkInput = document.getElementById('qa-approval-link');
                if (qaLinkInput) {
                    navigator.clipboard.writeText(qaLinkInput.value);
                    this.textContent = 'Copied!';
                    var btn = this;
                    setTimeout(function() {
                        btn.textContent = 'Copy Link';
                    }, 1500);
                }
            });
        }
    });
    
    // Handle HTMX errors
    document.body.addEventListener('htmx:responseError', function(e) {
        if (progressDiv) {
            progressDiv.style.display = 'none';
        }
        
        // Restore file state on error
        if (fileState) {
            restoreFileState(fileState);
        }
        
        let errorMessage = 'An error occurred while processing your request.';
        
        try {
            const response = JSON.parse(e.detail.xhr.responseText);
            if (response.detail) {
                errorMessage = response.detail;
            }
        } catch (err) {
            // Use default error message
        }
        
        showError(errorMessage);
    });
}

/**
 * Validate the entire form before submission
 */
function validateForm() {
    const fileInput = document.getElementById('csv_file');
    
    // Check file is selected
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        showError('📁 Please select a CSV file before generating the validation report. Click or drag a file to the upload area above.');
        // Highlight the upload area
        const uploadArea = document.getElementById('upload-area');
        if (uploadArea) {
            uploadArea.style.border = '2px dashed #dc2626';
            uploadArea.style.background = '#fef2f2';
            setTimeout(() => {
                uploadArea.style.border = '2px dashed #cbd5e0';
                uploadArea.style.background = '#f7fafc';
            }, 3000);
        }
        return false;
    }
    
    // Validate file type and size again
    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showError('⚠️ Invalid file type. Please select a CSV file (*.csv format).');
        return false;
    }
    
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
        showError('File size exceeds 10MB limit.');
        return false;
    }
    
    // Validate form fields
    if (!validateSpecForm()) {
        return false;
    }
    
    return true;
}

/**
 * Validate the specification form fields
 */
function validateSpecForm() {
    const jobId = document.getElementById('job_id')?.value?.trim();
    const targetTemp = parseFloat(document.getElementById('target_temp')?.value);
    const holdTime = parseInt(document.getElementById('hold_time')?.value);
    const sensorUncertainty = parseFloat(document.getElementById('sensor_uncertainty')?.value);
    
    if (!jobId) {
        showError('Job ID is required.');
        return false;
    }
    
    if (isNaN(targetTemp) || targetTemp < 100 || targetTemp > 300) {
        showError('Target temperature must be between 100°C and 300°C.');
        return false;
    }
    
    if (isNaN(holdTime) || holdTime < 60 || holdTime > 3600) {
        showError('Hold time must be between 60 and 3600 seconds.');
        return false;
    }
    
    if (isNaN(sensorUncertainty) || sensorUncertainty < 0.5 || sensorUncertainty > 10) {
        showError('Sensor uncertainty must be between 0.5°C and 10°C.');
        return false;
    }
    
    clearErrors();
    return true;
}


/**
 * Preserve file info after successful form submission
 */
function preserveFileInfo() {
    const fileInput = document.getElementById('csv_file');
    const fileInfo = document.getElementById('file-info');
    
    // Keep file info visible if file was selected
    if (fileInput && fileInput.files && fileInput.files.length > 0 && fileInfo) {
        fileInfo.style.display = 'block';
    }
}

/**
 * Restore file state after HTMX request
 */
function restoreFileState(fileState) {
    if (!fileState) return;
    
    const fileInput = document.getElementById('csv_file');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    
    // Try to restore file to input (may not work due to security restrictions)
    try {
        const dt = new DataTransfer();
        dt.items.add(fileState.file);
        if (fileInput) fileInput.files = dt.files;
    } catch (e) {
        console.log('Cannot restore file to input (security restriction)');
    }
    
    // Always restore the UI display
    if (fileName) fileName.textContent = fileState.name;
    if (fileSize) fileSize.textContent = formatFileSize(fileState.size);
    if (fileInfo) fileInfo.style.display = 'block';
    
    console.log('Restored file state UI:', fileState.name);
}

/**
 * Reset the form to initial state
 */
function resetForm() {
    const form = document.getElementById('upload-form');
    const fileInfo = document.getElementById('file-info');
    const results = document.getElementById('results');
    
    if (form) {
        form.reset();
    }
    
    if (fileInfo) {
        fileInfo.style.display = 'none';
    }
    
    if (results) {
        results.innerHTML = '';
    }
    
    clearErrors();
    
    // Reset form fields to defaults
    const defaults = {
        'job_id': 'batch_001',
        'target_temp': '180',
        'hold_time': '600',
        'sensor_uncertainty': '2.0',
        'max_ramp_rate': '15',
        'max_time_to_threshold': '900'
    };
    
    Object.entries(defaults).forEach(([fieldId, value]) => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.value = value;
        }
    });
    
    // Reset radio buttons to defaults
    const continuousRadio = document.querySelector('input[name="hold_logic"][value="continuous"]');
    if (continuousRadio) continuousRadio.checked = true;
    
    const minSensorRadio = document.querySelector('input[name="sensor_mode"][value="min_of_set"]');
    if (minSensorRadio) minSensorRadio.checked = true;
    
    // Update the JSON field
    updateSpecJSONFromForm();
}

/**
 * Show error message to user
 */
function showError(message) {
    clearErrors();
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.innerHTML = `
        <div style="display: flex; align-items: start; gap: 0.75rem;">
            <span style="font-size: 1.25rem; margin-top: -2px;">⚠️</span>
            <div>
                <strong style="display: block; margin-bottom: 0.25rem;">Action Required</strong>
                ${message}
            </div>
        </div>
    `;
    errorDiv.id = 'error-display';
    errorDiv.style.cssText = `
        background: #fef2f2;
        border: 2px solid #dc2626;
        color: #991b1b;
        padding: 1rem 1.25rem;
        border-radius: 0.75rem;
        margin: 1.5rem auto;
        max-width: 600px;
        box-shadow: 0 4px 6px -1px rgba(220, 38, 38, 0.1);
        animation: slideDown 0.3s ease-out;
    `;
    
    // Add animation style if not already present
    if (!document.getElementById('error-animation-style')) {
        const style = document.createElement('style');
        style.id = 'error-animation-style';
        style.textContent = `
            @keyframes slideDown {
                from {
                    opacity: 0;
                    transform: translateY(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    // Insert at the top of the form section
    const section = document.querySelector('.section-container');
    if (section) {
        section.insertBefore(errorDiv, section.firstChild);
        // Scroll to error message
        errorDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
        // Fallback to form insertion
        const form = document.getElementById('upload-form');
        if (form && form.parentNode) {
            form.parentNode.insertBefore(errorDiv, form);
        }
    }
    
    // Auto-hide after 10 seconds
    setTimeout(clearErrors, 10000);
}

/**
 * Clear any displayed error messages
 */
function clearErrors() {
    const errorDiv = document.getElementById('error-display');
    if (errorDiv) {
        errorDiv.remove();
    }
}

/**
 * Format file size in human-readable format
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Initialize cookie consent functionality
 */
function initializeCookieConsent() {
    // Check if user has already made a choice
    const consentChoice = localStorage.getItem('cookie_consent');
    
    if (!consentChoice) {
        // Show banner after a short delay
        setTimeout(showCookieConsent, 1500);
    } else {
        // Apply user's previous choice
        if (consentChoice === 'analytics') {
            enableAnalytics();
        }
        // Essential cookies are always enabled
    }
}

/**
 * Show the cookie consent banner
 */
function showCookieConsent() {
    const banner = document.getElementById('cookie-consent');
    if (banner) {
        banner.style.transform = 'translateY(0)';
    }
}

/**
 * Hide the cookie consent banner
 */
function hideCookieConsent() {
    const banner = document.getElementById('cookie-consent');
    if (banner) {
        banner.style.transform = 'translateY(100%)';
    }
}

/**
 * Accept all cookies including analytics
 */
function acceptAllCookies() {
    localStorage.setItem('cookie_consent', 'analytics');
    enableAnalytics();
    hideCookieConsent();
    
    // Show confirmation
    showCookieMessage('Analytics cookies enabled. Thank you for helping us improve ProofKit!', 'success');
}

/**
 * Accept only essential cookies
 */
function acceptEssentialOnly() {
    localStorage.setItem('cookie_consent', 'essential');
    disableAnalytics();
    hideCookieConsent();
    
    // Show confirmation
    showCookieMessage('Only essential cookies enabled. You can change this anytime.', 'info');
}

/**
 * Enable Google Analytics 4 tracking (delegated to analytics partial)
 */
function enableAnalytics() {
    // Analytics implementation moved to partials/analytics.html
    // This function is kept for backward compatibility
    console.log('Analytics enablement delegated to analytics partial');
    
    // Trigger analytics consent update if analytics partial is loaded
    if (window.updateAnalyticsConsent) {
        window.updateAnalyticsConsent(true);
    }
}

/**
 * Disable analytics tracking (delegated to analytics partial)
 */
function disableAnalytics() {
    // Analytics implementation moved to partials/analytics.html
    // This function is kept for backward compatibility
    console.log('Analytics disabling delegated to analytics partial');
    
    // Trigger analytics consent update if analytics partial is loaded
    if (window.updateAnalyticsConsent) {
        window.updateAnalyticsConsent(false);
    }
    
    // Fallback: Clear analytics cookies if analytics partial not loaded
    if (!window.updateAnalyticsConsent) {
        const analyticsCookies = ['_ga', '_ga_*', '_gid', '_gat'];
        analyticsCookies.forEach(cookieName => {
            if (cookieName.includes('*')) {
                document.cookie.split(';').forEach(cookie => {
                    const name = cookie.split('=')[0].trim();
                    if (name.startsWith(cookieName.replace('*', ''))) {
                        document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
                    }
                });
            } else {
                document.cookie = cookieName + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
            }
        });
        console.log('Fallback: Analytics cookies cleared directly');
    }
}

/**
 * Show a temporary message about cookie settings
 */
function showCookieMessage(message, type = 'info') {
    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
        position: fixed;
        top: 1rem;
        right: 1rem;
        background: ${type === 'success' ? '#22c55e' : '#3b82f6'};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 10001;
        font-size: 0.9rem;
        max-width: 350px;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    `;
    messageDiv.textContent = message;
    
    document.body.appendChild(messageDiv);
    
    // Animate in
    setTimeout(() => {
        messageDiv.style.transform = 'translateX(0)';
    }, 100);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        messageDiv.style.transform = 'translateX(100%)';
        setTimeout(() => {
            document.body.removeChild(messageDiv);
        }, 300);
    }, 4000);
}

/**
 * Get current cookie consent status
 */
function getCookieConsent() {
    return localStorage.getItem('cookie_consent') || null;
}

/**
 * Reset cookie consent (for testing or user-requested reset)
 */
function resetCookieConsent() {
    localStorage.removeItem('cookie_consent');
    disableAnalytics();
    showCookieConsent();
}

// Make functions available globally for onclick handlers
window.resetForm = resetForm;
window.showCookieConsent = showCookieConsent;
window.hideCookieConsent = hideCookieConsent;
window.acceptAllCookies = acceptAllCookies;
window.acceptEssentialOnly = acceptEssentialOnly;
window.resetCookieConsent = resetCookieConsent;