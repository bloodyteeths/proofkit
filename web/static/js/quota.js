/**
 * ProofKit Quota Management JavaScript
 * 
 * Handles quota enforcement, 402 error interception, and upgrade flow UX.
 * Works with the upgrade modal and billing system to provide seamless
 * user experience when quota limits are exceeded.
 * 
 * Features:
 * - Intercepts 402 Payment Required responses
 * - Shows appropriate upgrade modal based on user plan
 * - Handles single certificate purchases
 * - Tracks quota events for analytics
 * 
 * Usage:
 *   Include this script after HTMX and before any compilation forms
 *   The script automatically attaches to form submissions and API calls
 */

(function() {
    'use strict';
    
    // Configuration
    const CONFIG = {
        modalElementId: 'upgrade-modal',
        quotaEndpoint: '/api/usage',
        upgradeEndpoint: '/api/upgrade',
        singlePurchaseEndpoint: '/api/buy-single',
        retryDelay: 1000, // ms
        maxRetries: 3
    };
    
    // State management
    let currentQuotaStatus = null;
    let isProcessingRequest = false;
    let retryCount = 0;
    
    /**
     * Initialize quota management system
     */
    function initializeQuotaManagement() {
        console.log('ProofKit Quota Management initialized');
        
        // Intercept form submissions
        interceptFormSubmissions();
        
        // Intercept HTMX requests
        interceptHtmxRequests();
        
        // Intercept fetch requests
        interceptFetchRequests();
        
        // Load current quota status
        loadQuotaStatus();
        
        // Set up periodic quota checks (every 5 minutes)
        setInterval(loadQuotaStatus, 5 * 60 * 1000);
    }
    
    /**
     * Intercept form submissions to compilation endpoints
     */
    function interceptFormSubmissions() {
        document.addEventListener('submit', function(event) {
            const form = event.target;
            
            // Only intercept compilation forms
            if (!isCompilationForm(form)) {
                return;
            }
            
            // Check quota before submission
            event.preventDefault();
            checkQuotaAndSubmit(form);
        });
    }
    
    /**
     * Intercept HTMX requests for quota checking
     */
    function interceptHtmxRequests() {
        document.body.addEventListener('htmx:beforeRequest', function(event) {
            const url = event.detail.requestConfig.path;
            
            if (isCompilationUrl(url)) {
                // Check quota before HTMX request
                event.preventDefault();
                checkQuotaAndMakeHtmxRequest(event.detail);
            }
        });
        
        // Handle HTMX responses
        document.body.addEventListener('htmx:responseError', function(event) {
            if (event.detail.xhr.status === 402) {
                try {
                    const errorData = JSON.parse(event.detail.xhr.responseText);
                    handleQuotaExceeded(errorData);
                } catch (e) {
                    console.error('Failed to parse 402 error response:', e);
                    showGenericQuotaError();
                }
            }
        });
    }
    
    /**
     * Intercept fetch requests to compilation endpoints
     */
    function interceptFetchRequests() {
        const originalFetch = window.fetch;
        
        window.fetch = function(url, options = {}) {
            // Check if this is a compilation request
            if (typeof url === 'string' && isCompilationUrl(url)) {
                return checkQuotaAndFetch(url, options, originalFetch);
            }
            
            return originalFetch(url, options);
        };
    }
    
    /**
     * Check if form is a compilation form
     */
    function isCompilationForm(form) {
        const action = form.action || '';
        return isCompilationUrl(action);
    }
    
    /**
     * Check if URL is a compilation endpoint
     */
    function isCompilationUrl(url) {
        const compilationEndpoints = ['/api/compile', '/api/compile/json'];
        return compilationEndpoints.some(endpoint => url.includes(endpoint));
    }
    
    /**
     * Load current quota status from API
     */
    async function loadQuotaStatus() {
        try {
            const response = await fetch(CONFIG.quotaEndpoint, {
                credentials: 'same-origin'
            });
            
            if (response.ok) {
                currentQuotaStatus = await response.json();
                updateQuotaDisplay();
            } else if (response.status !== 401) {
                console.warn('Failed to load quota status:', response.status);
            }
        } catch (error) {
            console.warn('Quota status check failed:', error);
        }
    }
    
    /**
     * Update quota display in UI
     */
    function updateQuotaDisplay() {
        if (!currentQuotaStatus) return;
        
        // Update quota indicators in the UI
        const quotaDisplays = document.querySelectorAll('[data-quota-display]');
        quotaDisplays.forEach(display => {
            updateSingleQuotaDisplay(display, currentQuotaStatus);
        });
    }
    
    /**
     * Update a single quota display element
     */
    function updateSingleQuotaDisplay(element, quota) {
        const type = element.getAttribute('data-quota-display');
        
        switch (type) {
            case 'remaining':
                if (quota.plan === 'free') {
                    element.textContent = quota.total_remaining || 0;
                } else {
                    element.textContent = quota.monthly_remaining || 0;
                }
                break;
                
            case 'used':
                if (quota.plan === 'free') {
                    element.textContent = quota.total_used || 0;
                } else {
                    element.textContent = quota.monthly_used || 0;
                }
                break;
                
            case 'limit':
                if (quota.plan === 'free') {
                    element.textContent = quota.total_limit || 2;
                } else {
                    element.textContent = quota.monthly_limit || 0;
                }
                break;
                
            case 'plan':
                element.textContent = (quota.plan_name || quota.plan || 'Free').charAt(0).toUpperCase() + 
                                    (quota.plan_name || quota.plan || 'Free').slice(1);
                break;
        }
    }
    
    /**
     * Check quota and submit form if allowed
     */
    async function checkQuotaAndSubmit(form) {
        if (isProcessingRequest) return;
        
        try {
            isProcessingRequest = true;
            showLoadingState(form);
            
            // Pre-check quota
            await loadQuotaStatus();
            
            if (currentQuotaStatus && isQuotaExceeded(currentQuotaStatus)) {
                hideLoadingState(form);
                handleQuotaExceeded({
                    code: currentQuotaStatus.plan === 'free' ? 'FREE_TIER_EXCEEDED' : 'MONTHLY_QUOTA_EXCEEDED',
                    plan: currentQuotaStatus.plan,
                    ...currentQuotaStatus
                });
                return;
            }
            
            // Proceed with form submission
            const formData = new FormData(form);
            const response = await fetch(form.action, {
                method: form.method || 'POST',
                body: formData,
                credentials: 'same-origin'
            });
            
            if (response.status === 402) {
                const errorData = await response.json();
                hideLoadingState(form);
                handleQuotaExceeded(errorData);
            } else if (response.ok) {
                // Handle successful submission
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('text/html')) {
                    // Replace content for HTMX-style response
                    const html = await response.text();
                    const targetSelector = form.getAttribute('hx-target') || '#result';
                    const targetElement = document.querySelector(targetSelector);
                    if (targetElement) {
                        targetElement.innerHTML = html;
                    }
                } else {
                    // Handle JSON response
                    const result = await response.json();
                    handleSuccessfulCompilation(result);
                }
                
                // Refresh quota status
                await loadQuotaStatus();
            } else {
                // Handle other errors
                hideLoadingState(form);
                handleFormError(response);
            }
            
        } catch (error) {
            hideLoadingState(form);
            console.error('Form submission error:', error);
            showErrorMessage('An error occurred. Please try again.');
        } finally {
            isProcessingRequest = false;
        }
    }
    
    /**
     * Check quota and make HTMX request if allowed
     */
    async function checkQuotaAndMakeHtmxRequest(requestConfig) {
        // Similar logic to form submission but for HTMX
        // For simplicity, let HTMX handle the request and catch 402 in response handler
        // This could be enhanced to pre-check quota like form submissions
        
        // Re-trigger the HTMX request
        const element = requestConfig.elt;
        if (element && element.dispatchEvent) {
            const event = new Event('htmx:afterRequest');
            setTimeout(() => element.dispatchEvent(event), 10);
        }
    }
    
    /**
     * Check quota and make fetch request if allowed
     */
    async function checkQuotaAndFetch(url, options, originalFetch) {
        try {
            // Pre-check quota
            await loadQuotaStatus();
            
            if (currentQuotaStatus && isQuotaExceeded(currentQuotaStatus)) {
                // Return a mock 402 response
                return new Response(JSON.stringify({
                    code: currentQuotaStatus.plan === 'free' ? 'FREE_TIER_EXCEEDED' : 'MONTHLY_QUOTA_EXCEEDED',
                    plan: currentQuotaStatus.plan,
                    ...currentQuotaStatus
                }), {
                    status: 402,
                    headers: { 'Content-Type': 'application/json' }
                });
            }
            
            // Proceed with original fetch
            const response = await originalFetch(url, options);
            
            // Refresh quota status on successful compilation
            if (response.ok) {
                setTimeout(loadQuotaStatus, 500);
            }
            
            return response;
            
        } catch (error) {
            console.error('Fetch interception error:', error);
            return originalFetch(url, options);
        }
    }
    
    /**
     * Check if quota is exceeded based on current status
     */
    function isQuotaExceeded(quotaStatus) {
        if (quotaStatus.plan === 'free') {
            return quotaStatus.total_used >= quotaStatus.total_limit;
        } else {
            // For paid plans, overage is allowed so don't pre-block
            return false;
        }
    }
    
    /**
     * Handle quota exceeded error
     */
    function handleQuotaExceeded(errorData) {
        console.log('Quota exceeded:', errorData);
        
        // Track quota exceeded event
        trackQuotaEvent('quota_exceeded', {
            code: errorData.code,
            plan: errorData.plan || 'free',
            used: errorData.total_used || errorData.monthly_used,
            limit: errorData.total_limit || errorData.monthly_limit
        });
        
        // Show upgrade modal
        if (typeof showUpgradeModal === 'function') {
            showUpgradeModal(errorData);
        } else {
            // Fallback to built-in modal or redirect
            showFallbackUpgradePrompt(errorData);
        }
    }
    
    /**
     * Show fallback upgrade prompt if modal is not available
     */
    function showFallbackUpgradePrompt(errorData) {
        const message = errorData.code === 'FREE_TIER_EXCEEDED' 
            ? `You've used all ${errorData.limit} free certificates. Upgrade to continue.`
            : `You've exceeded your monthly quota. Upgrade or purchase additional certificates.`;
        
        const upgrade = confirm(message + '\n\nWould you like to view upgrade options?');
        if (upgrade) {
            window.location.href = '/pricing#upgrade';
        }
    }
    
    /**
     * Handle successful compilation
     */
    function handleSuccessfulCompilation(result) {
        // Update UI or redirect as needed
        console.log('Compilation successful:', result);
        
        // Track successful compilation
        trackQuotaEvent('compilation_success', {
            job_id: result.id,
            pass: result.pass
        });
    }
    
    /**
     * Handle form submission errors
     */
    function handleFormError(response) {
        console.error('Form error:', response.status, response.statusText);
        
        if (response.status === 400) {
            showErrorMessage('Invalid input data. Please check your CSV file and specification.');
        } else if (response.status === 413) {
            showErrorMessage('File too large. Maximum size is 10MB.');
        } else if (response.status >= 500) {
            showErrorMessage('Server error. Please try again in a few moments.');
        } else {
            showErrorMessage('An error occurred. Please try again.');
        }
    }
    
    /**
     * Show loading state on form
     */
    function showLoadingState(form) {
        const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.setAttribute('data-original-text', submitButton.textContent);
            submitButton.textContent = 'Processing...';
            submitButton.classList.add('loading');
        }
    }
    
    /**
     * Hide loading state on form
     */
    function hideLoadingState(form) {
        const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
        if (submitButton) {
            submitButton.disabled = false;
            const originalText = submitButton.getAttribute('data-original-text');
            if (originalText) {
                submitButton.textContent = originalText;
                submitButton.removeAttribute('data-original-text');
            }
            submitButton.classList.remove('loading');
        }
    }
    
    /**
     * Show error message to user
     */
    function showErrorMessage(message) {
        // Try to use existing error display elements
        const errorElements = document.querySelectorAll('[data-error-display]');
        if (errorElements.length > 0) {
            errorElements.forEach(el => {
                el.textContent = message;
                el.style.display = 'block';
            });
            return;
        }
        
        // Fallback to alert
        alert(message);
    }
    
    /**
     * Show generic quota error
     */
    function showGenericQuotaError() {
        handleQuotaExceeded({
            code: 'QUOTA_EXCEEDED',
            plan: 'unknown',
            message: 'You have exceeded your quota limit. Please upgrade to continue.'
        });
    }
    
    /**
     * Track quota-related events for analytics
     */
    function trackQuotaEvent(eventName, properties = {}) {
        // Google Analytics 4
        if (typeof gtag !== 'undefined') {
            gtag('event', eventName, {
                event_category: 'quota',
                ...properties
            });
        }
        
        // Console logging for development
        console.log('Quota event:', eventName, properties);
    }
    
    /**
     * Utility: Retry failed requests
     */
    async function retryRequest(requestFn, maxRetries = CONFIG.maxRetries) {
        for (let i = 0; i < maxRetries; i++) {
            try {
                return await requestFn();
            } catch (error) {
                if (i === maxRetries - 1) throw error;
                await new Promise(resolve => setTimeout(resolve, CONFIG.retryDelay * (i + 1)));
            }
        }
    }
    
    /**
     * Public API for external access
     */
    window.ProofKitQuota = {
        loadQuotaStatus: loadQuotaStatus,
        getCurrentQuota: () => currentQuotaStatus,
        handleQuotaExceeded: handleQuotaExceeded,
        trackQuotaEvent: trackQuotaEvent,
        isQuotaExceeded: isQuotaExceeded
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeQuotaManagement);
    } else {
        initializeQuotaManagement();
    }
    
})();