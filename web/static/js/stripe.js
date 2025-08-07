/**
 * Stripe Frontend Integration for ProofKit
 * 
 * This module handles Stripe checkout redirects and payment flows
 * for subscription upgrades and single certificate purchases.
 */

// Initialize Stripe - will be replaced with actual key from backend
let stripe = null;
let stripePublishableKey = null;

/**
 * Initialize Stripe with publishable key from backend
 */
async function initStripe() {
    try {
        const response = await fetch('/api/stripe-config');
        const config = await response.json();
        stripePublishableKey = config.publishableKey;
        
        if (stripePublishableKey) {
            stripe = Stripe(stripePublishableKey);
            console.log('Stripe initialized successfully');
        } else {
            console.error('No Stripe publishable key found');
        }
    } catch (error) {
        console.error('Failed to initialize Stripe:', error);
    }
}

/**
 * Redirect to Stripe checkout for subscription upgrade
 * @param {string} planName - Target plan (starter, pro, business)
 */
async function upgradeToplan(planName) {
    // Initialize Stripe if not already done
    if (!stripe && stripePublishableKey) {
        stripe = Stripe(stripePublishableKey);
    }
    
    if (!stripe) {
        // Fallback: try to get Stripe config first
        try {
            const configResponse = await fetch('/api/stripe-config');
            const config = await configResponse.json();
            if (config.publishableKey) {
                stripe = Stripe(config.publishableKey);
            }
        } catch (e) {
            console.error('Failed to get Stripe config:', e);
        }
    }
    
    if (!stripe) {
        alert('Payment system is not available. Please try again later.');
        return;
    }
    
    let button = null;
    let originalText = '';
    
    try {
        // Get the button that was clicked
        if (typeof event !== 'undefined' && event && event.target) {
            button = event.target;
        } else {
            // Fallback: find button by data-plan attribute
            button = document.querySelector(`button[data-plan="${planName}"]`);
        }
        
        if (button) {
            originalText = button.textContent;
            button.disabled = true;
            button.textContent = 'Loading...';
        }
        
        // Create checkout session
        const response = await fetch(`/api/upgrade/${planName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({
                success_url: window.location.origin + '/billing/success?plan=' + planName,
                cancel_url: window.location.origin + '/pricing'
            })
        });
        
        if (!response.ok) {
            if (response.status === 401 || response.status === 422) {
                // User not authenticated, redirect to login
                window.location.href = '/auth/login?return_url=' + encodeURIComponent('/pricing');
                return;
            }
            if (response.status === 409) {
                // User already has this plan
                let message = 'You already have this plan';
                try {
                    const error = await response.json();
                    message = error.detail || message;
                } catch (e) {
                    // If JSON parsing fails, use default message
                }
                // Show message and optionally open customer portal
                if (confirm(message + '\n\nWould you like to manage your subscription?')) {
                    openCustomerPortal();
                }
                // Reset button state
                if (button) {
                    button.disabled = false;
                    button.textContent = originalText || 'Choose ' + planName.charAt(0).toUpperCase() + planName.slice(1);
                }
                return;
            }
            let errorMessage = 'Failed to create checkout session';
            try {
                const error = await response.json();
                errorMessage = error.detail || errorMessage;
            } catch (e) {
                // If JSON parsing fails, use default message
            }
            throw new Error(errorMessage);
        }
        
        const session = await response.json();
        
        // Redirect to Stripe checkout
        const result = await stripe.redirectToCheckout({
            sessionId: session.session_id
        });
        
        if (result.error) {
            throw new Error(result.error.message);
        }
        
    } catch (error) {
        console.error('Checkout error:', error);
        const errorMessage = error.message || 'Failed to start checkout';
        
        // Don't show alert if we're redirecting to login
        if (!window.location.href.includes('/auth/login')) {
            alert(`Unable to start checkout: ${errorMessage}`);
        }
        
        // Reset button state
        if (button) {
            button.disabled = false;
            button.textContent = originalText || 'Choose ' + planName.charAt(0).toUpperCase() + planName.slice(1);
        }
    }
}

/**
 * Purchase single certificates
 * @param {number} count - Number of certificates to purchase
 */
async function buySingleCertificates(count = 1) {
    if (!stripe) {
        alert('Payment system is not available. Please try again later.');
        return;
    }
    
    try {
        // Show loading state
        const button = event.target;
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = 'Loading...';
        
        // Create checkout session
        const response = await fetch('/api/buy-single', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                certificate_count: count
            }),
            credentials: 'include'
        });
        
        if (!response.ok) {
            let errorMessage = 'Failed to create checkout session';
            try {
                const error = await response.json();
                errorMessage = error.detail || errorMessage;
            } catch (e) {
                // If JSON parsing fails, use default message
            }
            throw new Error(errorMessage);
        }
        
        const session = await response.json();
        
        // Redirect to Stripe checkout
        const result = await stripe.redirectToCheckout({
            sessionId: session.session_id
        });
        
        if (result.error) {
            throw new Error(result.error.message);
        }
        
    } catch (error) {
        console.error('Checkout error:', error);
        alert(`Unable to start checkout: ${error.message}`);
        
        // Reset button state
        if (button) {
            button.disabled = false;
            button.textContent = originalText;
        }
    }
}

/**
 * Open Stripe Customer Portal for subscription management
 */
async function openCustomerPortal() {
    try {
        const response = await fetch('/api/customer-portal', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create portal session');
        }
        
        const { url } = await response.json();
        window.location.href = url;
        
    } catch (error) {
        console.error('Customer portal error:', error);
        alert(`Unable to open customer portal: ${error.message}`);
    }
}

/**
 * Handle successful payment return
 */
function handlePaymentSuccess() {
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session_id');
    
    if (sessionId) {
        // Show success message
        const successMessage = document.getElementById('payment-success-message');
        if (successMessage) {
            successMessage.style.display = 'block';
            successMessage.innerHTML = `
                <div class="alert alert-success">
                    <h4>Payment Successful!</h4>
                    <p>Your plan has been updated. You can now use your new features.</p>
                    <a href="/dashboard" class="btn btn-primary">Go to Dashboard</a>
                </div>
            `;
        }
        
        // Refresh quota display if exists
        if (typeof refreshQuota === 'function') {
            refreshQuota();
        }
    }
}

/**
 * Handle cancelled payment return
 */
function handlePaymentCancel() {
    const cancelMessage = document.getElementById('payment-cancel-message');
    if (cancelMessage) {
        cancelMessage.style.display = 'block';
        cancelMessage.innerHTML = `
            <div class="alert alert-warning">
                <h4>Payment Cancelled</h4>
                <p>No charges were made. You can try again anytime.</p>
                <a href="/pricing" class="btn btn-primary">View Plans</a>
            </div>
        `;
    }
}

/**
 * Update pricing display with live prices from backend
 */
async function updatePricingDisplay() {
    try {
        const response = await fetch('/api/plans');
        const plans = await response.json();
        
        // Update price displays
        Object.keys(plans).forEach(planName => {
            const plan = plans[planName];
            const priceElement = document.getElementById(`price-${planName}`);
            if (priceElement && plan.price_usd !== null) {
                priceElement.textContent = `$${plan.price_usd}`;
            }
            
            // Update features list
            const featuresElement = document.getElementById(`features-${planName}`);
            if (featuresElement && plan.features) {
                featuresElement.innerHTML = plan.features.map(f => `<li>${f}</li>`).join('');
            }
        });
        
    } catch (error) {
        console.error('Failed to update pricing display:', error);
    }
}

/**
 * Show upgrade modal with plan details
 * @param {string} planName - Plan to upgrade to
 */
function showUpgradeModal(planName) {
    const modal = document.getElementById('upgrade-modal');
    if (!modal) return;
    
    // Populate modal with plan details
    const modalBody = modal.querySelector('.modal-body');
    if (modalBody) {
        fetch('/api/plans')
            .then(res => res.json())
            .then(plans => {
                const plan = plans[planName];
                modalBody.innerHTML = `
                    <h4>Upgrade to ${plan.name}</h4>
                    <p class="price-display">$${plan.price_usd}/month</p>
                    <ul class="features-list">
                        ${plan.features.map(f => `<li>${f}</li>`).join('')}
                    </ul>
                    <button class="btn btn-primary btn-lg w-100" onclick="upgradeToplan('${planName}')">
                        Proceed to Checkout
                    </button>
                `;
            });
    }
    
    // Show modal
    modal.style.display = 'block';
}

/**
 * Close upgrade modal
 */
function closeUpgradeModal() {
    const modal = document.getElementById('upgrade-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Stripe
    initStripe();
    
    // Update pricing display if on pricing page
    if (window.location.pathname === '/pricing') {
        updatePricingDisplay();
    }
    
    // Handle payment success/cancel returns
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('session_id')) {
        handlePaymentSuccess();
    } else if (urlParams.has('canceled')) {
        handlePaymentCancel();
    }
    
    // Add click handlers for upgrade buttons
    document.querySelectorAll('[data-upgrade-plan]').forEach(button => {
        button.addEventListener('click', function() {
            const planName = this.dataset.upgradePlan;
            upgradeToplan(planName);
        });
    });
    
    // Add click handlers for single cert purchase
    document.querySelectorAll('[data-buy-certs]').forEach(button => {
        button.addEventListener('click', function() {
            const count = parseInt(this.dataset.buyCerts) || 1;
            buySingleCertificates(count);
        });
    });
});

// Export functions for use in other scripts
window.stripeIntegration = {
    upgradeToplan,
    buySingleCertificates,
    openCustomerPortal,
    showUpgradeModal,
    closeUpgradeModal
};