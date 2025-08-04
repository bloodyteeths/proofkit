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
});

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
    
    // Click to upload
    uploadArea.addEventListener('click', function(e) {
        if (e.target !== fileInput) {
            fileInput.click();
        }
    });
    
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
            fileInfo.style.display = 'none';
            return;
        }
        
        // Validate file type
        if (!file.name.toLowerCase().endsWith('.csv')) {
            showError('Please select a CSV file.');
            return;
        }
        
        // Validate file size (10MB limit)
        const maxSize = 10 * 1024 * 1024; // 10MB in bytes
        if (file.size > maxSize) {
            showError('File size exceeds 10MB limit. Please select a smaller file.');
            return;
        }
        
        // Show file info
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        fileInfo.style.display = 'block';
        
        // Clear any previous errors
        clearErrors();
    }
}

/**
 * Initialize form validation
 */
function initializeFormValidation() {
    const form = document.getElementById('upload-form');
    const specTextarea = document.getElementById('spec_json');
    
    if (!form || !specTextarea) return;
    
    // Validate JSON on blur
    specTextarea.addEventListener('blur', function() {
        validateSpecJSON();
    });
    
    // Form submission validation
    form.addEventListener('htmx:beforeRequest', function(e) {
        if (!validateForm()) {
            e.preventDefault();
            return false;
        }
    });
}

/**
 * Initialize progress indicator for HTMX requests
 */
function initializeProgressIndicator() {
    const progressDiv = document.getElementById('progress');
    
    // Show progress on HTMX request start
    document.body.addEventListener('htmx:beforeRequest', function() {
        if (progressDiv) {
            progressDiv.style.display = 'block';
        }
    });
    
    // Hide progress on HTMX request complete
    document.body.addEventListener('htmx:afterRequest', function() {
        if (progressDiv) {
            progressDiv.style.display = 'none';
        }
    });
    
    // Handle HTMX errors
    document.body.addEventListener('htmx:responseError', function(e) {
        if (progressDiv) {
            progressDiv.style.display = 'none';
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
    const specTextarea = document.getElementById('spec_json');
    
    // Check file is selected
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        showError('Please select a CSV file.');
        return false;
    }
    
    // Validate file type and size again
    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showError('Please select a CSV file.');
        return false;
    }
    
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
        showError('File size exceeds 10MB limit.');
        return false;
    }
    
    // Validate JSON spec
    if (!validateSpecJSON()) {
        return false;
    }
    
    return true;
}

/**
 * Validate the specification JSON
 */
function validateSpecJSON() {
    const specTextarea = document.getElementById('spec_json');
    if (!specTextarea) return true;
    
    const jsonText = specTextarea.value.trim();
    if (!jsonText) {
        showError('Specification JSON is required.');
        return false;
    }
    
    try {
        const spec = JSON.parse(jsonText);
        
        // Basic validation for required fields
        if (!spec.version) {
            showError('Specification must include a version field.');
            return false;
        }
        
        if (!spec.spec || typeof spec.spec.target_temp_C !== 'number' || spec.spec.target_temp_C <= 0) {
            showError('Specification must include a valid target_temp_C (positive number).');
            return false;
        }
        
        if (!spec.spec || typeof spec.spec.hold_time_s !== 'number' || spec.spec.hold_time_s < 1) {
            showError('Specification must include a valid hold_time_s (>= 1 second).');
            return false;
        }
        
        clearErrors();
        return true;
        
    } catch (e) {
        showError('Invalid JSON format in specification. Please check your syntax.');
        return false;
    }
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
    
    // Reset spec JSON to default
    const specTextarea = document.getElementById('spec_json');
    if (specTextarea && window.defaultSpec) {
        specTextarea.value = window.defaultSpec;
    }
}

/**
 * Show error message to user
 */
function showError(message) {
    clearErrors();
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = message;
    errorDiv.id = 'error-display';
    
    // Insert after the form
    const form = document.getElementById('upload-form');
    if (form && form.parentNode) {
        form.parentNode.insertBefore(errorDiv, form.nextSibling);
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
 * Utility function to pretty-print JSON in textarea
 */
function formatSpecJSON() {
    const specTextarea = document.getElementById('spec_json');
    if (!specTextarea) return;
    
    try {
        const spec = JSON.parse(specTextarea.value);
        specTextarea.value = JSON.stringify(spec, null, 2);
    } catch (e) {
        // If JSON is invalid, don't format
        showError('Cannot format invalid JSON. Please fix syntax errors first.');
    }
}

// Make functions available globally for onclick handlers
window.resetForm = resetForm;
window.formatSpecJSON = formatSpecJSON;