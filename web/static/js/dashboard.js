/**
 * ProofKit Dashboard JavaScript
 * Handles dashboard interactions, data fetching, and upgrade modals
 */

class ProofKitDashboard {
    constructor() {
        this.apiEndpoints = {
            quota: '/api/quota',
            recentJobs: '/api/my-jobs?limit=5',
            buySingle: '/api/buy-single',
            upgrade: '/api/upgrade',
            billingPortal: '/api/billing/portal',
            usageStats: '/api/usage-stats'
        };
        
        this.updateIntervals = {
            quota: 30000,        // 30 seconds
            recentJobs: 60000,   // 1 minute
            usageStats: 300000   // 5 minutes
        };
        
        this.cache = {
            quota: null,
            recentJobs: null,
            usageStats: null
        };
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadInitialData();
        this.setupPeriodicUpdates();
        this.setupUpgradeModals();
        this.initializeCharts();
    }
    
    setupEventListeners() {
        // Upgrade buttons
        document.querySelectorAll('[data-action="upgrade"]').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleUpgrade(e));
        });
        
        // Buy single certificate buttons
        document.querySelectorAll('[data-action="buy-single"]').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleBuySingle(e));
        });
        
        // Billing management
        document.querySelectorAll('[data-action="billing"]').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleBilling(e));
        });
        
        // Refresh buttons
        document.querySelectorAll('[data-action="refresh"]').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleRefresh(e));
        });
        
        // Modal close buttons
        document.querySelectorAll('[data-dismiss="modal"]').forEach(btn => {
            btn.addEventListener('click', (e) => this.closeModal(e.target.closest('.modal')));
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
        
        // Visibility change for data refresh
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.refreshQuickStats();
            }
        });
    }
    
    async loadInitialData() {
        const loadingIndicator = this.showLoadingIndicator('Loading dashboard data...');
        
        try {
            await Promise.all([
                this.fetchQuotaData(),
                this.fetchRecentJobs(),
                this.fetchUsageStats()
            ]);
            
            this.updateDashboardUI();
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.showErrorMessage('Failed to load dashboard data. Please refresh the page.');
        } finally {
            this.hideLoadingIndicator(loadingIndicator);
        }
    }
    
    async fetchQuotaData() {
        try {
            const response = await fetch(this.apiEndpoints.quota);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            this.cache.quota = await response.json();
            this.updateQuotaDisplay();
            return this.cache.quota;
        } catch (error) {
            console.error('Failed to fetch quota data:', error);
            throw error;
        }
    }
    
    async fetchRecentJobs() {
        try {
            const response = await fetch(this.apiEndpoints.recentJobs);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            this.cache.recentJobs = await response.json();
            this.updateRecentJobsTable();
            return this.cache.recentJobs;
        } catch (error) {
            console.error('Failed to fetch recent jobs:', error);
            throw error;
        }
    }
    
    async fetchUsageStats() {
        try {
            const response = await fetch(this.apiEndpoints.usageStats);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            this.cache.usageStats = await response.json();
            this.updateUsageChart();
            return this.cache.usageStats;
        } catch (error) {
            console.error('Failed to fetch usage stats:', error);
            throw error;
        }
    }
    
    updateDashboardUI() {
        this.updateQuotaDisplay();
        this.updateRecentJobsTable();
        this.updateUsageChart();
        this.updatePlanBadge();
        this.updateActionButtons();
    }
    
    updateQuotaDisplay() {
        const quota = this.cache.quota;
        if (!quota) return;
        
        // Update plan badge
        const planBadge = document.querySelector('.plan-badge');
        if (planBadge) {
            planBadge.textContent = quota.plan_name;
            planBadge.className = `plan-badge ${quota.plan}`;
        }
        
        // Update usage display
        const usageDisplay = document.querySelector('.usage-display');
        if (usageDisplay) {
            const current = usageDisplay.querySelector('.usage-current');
            const limit = usageDisplay.querySelector('.usage-limit');
            
            if (current) current.textContent = quota.monthly_used || 0;
            if (limit) limit.textContent = quota.monthly_limit || '∞';
        }
        
        // Update usage bar
        this.updateUsageBar(quota);
        
        // Update billing status
        this.updateBillingStatus(quota);
    }
    
    updateUsageBar(quota) {
        const usageBar = document.querySelector('.usage-bar-fill');
        if (!usageBar) return;
        
        const percentage = quota.monthly_limit 
            ? (quota.monthly_used / quota.monthly_limit * 100)
            : 0;
        
        usageBar.style.width = `${Math.min(percentage, 100)}%`;
        usageBar.setAttribute('data-percentage', percentage.toFixed(1));
        
        // Update status classes
        usageBar.className = 'usage-bar-fill';
        if (percentage >= 100) {
            usageBar.classList.add('over-limit');
        } else if (percentage >= 80) {
            usageBar.classList.add('near-limit');
        } else {
            usageBar.classList.add('normal');
        }
        
        // Show/hide warning messages
        this.updateUsageWarnings(quota, percentage);
    }
    
    updateUsageWarnings(quota, percentage) {
        const warningContainer = document.querySelector('.usage-warnings');
        if (!warningContainer) return;
        
        let warningHTML = '';
        
        if (percentage >= 100) {
            if (quota.plan === 'free') {
                warningHTML = `
                    <div class="usage-warning error">
                        <strong>Limit reached:</strong> 
                        <a href="/pricing" class="upgrade-link">Upgrade your plan</a> 
                        or <button onclick="dashboard.showBuySingleModal()" class="buy-single-btn">buy single certificates</button>.
                    </div>
                `;
            } else {
                warningHTML = `
                    <div class="usage-warning caution">
                        <strong>Usage exceeded:</strong> Additional charges may apply to your next invoice.
                    </div>
                `;
            }
        } else if (percentage >= 80) {
            warningHTML = `
                <div class="usage-warning warning">
                    You're approaching your monthly limit (${percentage.toFixed(0)}% used).
                </div>
            `;
        }
        
        warningContainer.innerHTML = warningHTML;
    }
    
    updateBillingStatus(quota) {
        const statusBadge = document.querySelector('.billing-status .status-badge');
        const statusText = document.querySelector('.billing-status .stat-description');
        
        if (statusBadge && statusText) {
            if (quota.subscription && quota.subscription.active) {
                statusBadge.textContent = 'Active';
                statusBadge.className = 'status-badge active';
                statusText.textContent = `Next billing: ${quota.next_billing_date}`;
            } else {
                statusBadge.textContent = 'No Subscription';
                statusBadge.className = 'status-badge inactive';
                statusText.textContent = quota.plan === 'free' ? 'Using free tier' : 'Pay-as-you-go';
            }
        }
    }
    
    updateRecentJobsTable() {
        const tableBody = document.querySelector('.jobs-table tbody');
        if (!tableBody || !this.cache.recentJobs) return;
        
        const jobs = this.cache.recentJobs.jobs || [];
        
        if (jobs.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-state">
                        No compilations yet. <a href="/app">Start your first validation</a>
                    </td>
                </tr>
            `;
            return;
        }
        
        tableBody.innerHTML = jobs.slice(0, 5).map(job => `
            <tr class="job-row" data-job-id="${job.job_id}">
                <td class="job-id">
                    <code>${job.job_id.substring(0, 8)}...</code>
                </td>
                <td class="job-date">
                    ${this.formatDate(job.created_at)}
                </td>
                <td class="job-status">
                    ${job.approved 
                        ? '<span class="badge approved">Approved</span>'
                        : '<span class="badge pending">Pending</span>'
                    }
                </td>
                <td class="job-result">
                    ${job.pass 
                        ? '<span class="result pass">✓ PASS</span>'
                        : '<span class="result fail">✗ FAIL</span>'
                    }
                </td>
                <td class="job-actions">
                    <a href="/verify/${job.job_id}" class="action-link">View</a>
                    <a href="/download/${job.job_id}/pdf" class="action-link">PDF</a>
                    ${job.evidence_zip 
                        ? `<a href="/download/${job.job_id}/evidence" class="action-link">Evidence</a>`
                        : ''
                    }
                </td>
            </tr>
        `).join('');
        
        // Add click handlers for job rows
        this.setupJobRowHandlers();
    }
    
    setupJobRowHandlers() {
        document.querySelectorAll('.job-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (!e.target.closest('.action-link')) {
                    const jobId = row.dataset.jobId;
                    window.location.href = `/verify/${jobId}`;
                }
            });
        });
    }
    
    updateUsageChart() {
        const canvas = document.getElementById('usage-canvas');
        if (!canvas || !this.cache.usageStats) return;
        
        this.drawUsageChart(canvas, this.cache.usageStats);
    }
    
    drawUsageChart(canvas, data) {
        const ctx = canvas.getContext('2d');
        const containerWidth = canvas.parentElement.offsetWidth;
        const height = 280;
        
        // Set canvas size
        canvas.width = containerWidth;
        canvas.height = height;
        
        if (!data.daily_usage || data.daily_usage.length === 0) {
            // Show "No data" message
            ctx.fillStyle = '#6b7280';
            ctx.font = '14px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('No usage data available', containerWidth / 2, height / 2);
            return;
        }
        
        // Chart parameters
        const padding = { top: 20, right: 20, bottom: 40, left: 40 };
        const chartWidth = containerWidth - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        
        const maxValue = Math.max(...data.daily_usage.map(d => d.count), 1);
        const barWidth = chartWidth / data.daily_usage.length * 0.7;
        const barSpacing = chartWidth / data.daily_usage.length * 0.3;
        
        // Clear canvas
        ctx.clearRect(0, 0, containerWidth, height);
        
        // Draw bars
        data.daily_usage.forEach((item, index) => {
            const barHeight = (item.count / maxValue) * chartHeight;
            const x = padding.left + index * (barWidth + barSpacing) + barSpacing / 2;
            const y = padding.top + chartHeight - barHeight;
            
            // Draw bar
            const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
            gradient.addColorStop(0, '#667eea');
            gradient.addColorStop(1, '#764ba2');
            
            ctx.fillStyle = gradient;
            ctx.fillRect(x, y, barWidth, barHeight);
            
            // Draw value on top of bar
            if (item.count > 0) {
                ctx.fillStyle = '#374151';
                ctx.font = '12px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(item.count, x + barWidth / 2, y - 5);
            }
            
            // Draw date label
            ctx.fillStyle = '#6b7280';
            ctx.font = '10px Inter, sans-serif';
            ctx.textAlign = 'center';
            const date = new Date(item.date).toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric' 
            });
            ctx.fillText(date, x + barWidth / 2, height - 10);
        });
        
        // Draw axis lines
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        
        // Y-axis
        ctx.beginPath();
        ctx.moveTo(padding.left, padding.top);
        ctx.lineTo(padding.left, height - padding.bottom);
        ctx.stroke();
        
        // X-axis
        ctx.beginPath();
        ctx.moveTo(padding.left, height - padding.bottom);
        ctx.lineTo(containerWidth - padding.right, height - padding.bottom);
        ctx.stroke();
    }
    
    setupPeriodicUpdates() {
        // Update quota every 30 seconds
        setInterval(() => this.fetchQuotaData(), this.updateIntervals.quota);
        
        // Update recent jobs every minute
        setInterval(() => this.fetchRecentJobs(), this.updateIntervals.recentJobs);
        
        // Update usage stats every 5 minutes
        setInterval(() => this.fetchUsageStats(), this.updateIntervals.usageStats);
    }
    
    async refreshQuickStats() {
        try {
            await Promise.all([
                this.fetchQuotaData(),
                this.fetchRecentJobs()
            ]);
        } catch (error) {
            console.error('Failed to refresh quick stats:', error);
        }
    }
    
    setupUpgradeModals() {
        // This will integrate with the existing upgrade modal system
        window.showUpgradeModal = (errorData) => {
            const modal = document.getElementById('upgrade-modal');
            if (modal && typeof showUpgradeModal === 'function') {
                showUpgradeModal(errorData);
            } else {
                // Fallback to pricing page
                window.location.href = '/pricing';
            }
        };
        
        window.showBuySingleModal = () => {
            this.handleBuySingle();
        };
    }
    
    async handleUpgrade(event) {
        event.preventDefault();
        const button = event.target;
        const plan = button.dataset.plan || 'starter';
        
        button.classList.add('loading');
        button.disabled = true;
        
        try {
            const response = await fetch(`${this.apiEndpoints.upgrade}/${plan}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    success_url: `${window.location.origin}/dashboard?upgrade=success&plan=${plan}`,
                    cancel_url: window.location.href
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                
                // Track upgrade attempt
                this.trackEvent('plan_upgrade_attempt', {
                    target_plan: plan,
                    source: 'dashboard'
                });
                
                window.location.href = data.checkout_url;
            } else if (response.status === 401) {
                window.location.href = `/auth/login?redirect=${encodeURIComponent(window.location.href)}`;
            } else {
                const error = await response.json();
                this.showErrorMessage(`Upgrade failed: ${error.detail}`);
            }
        } catch (error) {
            console.error('Upgrade error:', error);
            this.showErrorMessage('Upgrade failed. Please try again.');
        } finally {
            button.classList.remove('loading');
            button.disabled = false;
        }
    }
    
    async handleBuySingle(event) {
        if (event) event.preventDefault();
        
        try {
            const response = await fetch(this.apiEndpoints.buySingle, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    certificate_count: 1,
                    success_url: `${window.location.origin}/dashboard?purchase=success`,
                    cancel_url: window.location.href
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                
                this.trackEvent('single_cert_purchase_attempt', {
                    price: data.price,
                    source: 'dashboard'
                });
                
                window.location.href = data.checkout_url;
            } else {
                const error = await response.json();
                this.showErrorMessage(`Purchase failed: ${error.detail}`);
            }
        } catch (error) {
            console.error('Purchase error:', error);
            this.showErrorMessage('Purchase failed. Please try again.');
        }
    }
    
    async handleBilling(event) {
        event.preventDefault();
        
        try {
            const response = await fetch(this.apiEndpoints.billingPortal, {
                method: 'POST'
            });
            
            if (response.ok) {
                const data = await response.json();
                window.location.href = data.portal_url;
            } else {
                this.showErrorMessage('Unable to access billing portal. Please try again.');
            }
        } catch (error) {
            console.error('Billing portal error:', error);
            this.showErrorMessage('Unable to access billing portal. Please try again.');
        }
    }
    
    handleRefresh(event) {
        event.preventDefault();
        const section = event.target.closest('[data-section]');
        const sectionName = section?.dataset.section || 'all';
        
        switch (sectionName) {
            case 'quota':
                this.fetchQuotaData();
                break;
            case 'jobs':
                this.fetchRecentJobs();
                break;
            case 'stats':
                this.fetchUsageStats();
                break;
            default:
                this.loadInitialData();
        }
    }
    
    handleKeyboardShortcuts(event) {
        if (event.ctrlKey || event.metaKey) {
            switch (event.key) {
                case 'r':
                    event.preventDefault();
                    this.refreshQuickStats();
                    break;
                case 'n':
                    event.preventDefault();
                    window.location.href = '/app';
                    break;
            }
        }
        
        if (event.key === 'Escape') {
            // Close any open modals
            document.querySelectorAll('.modal[style*="flex"]').forEach(modal => {
                this.closeModal(modal);
            });
        }
    }
    
    initializeCharts() {
        // Initialize usage chart
        this.updateUsageChart();
        
        // Handle window resize
        window.addEventListener('resize', () => {
            setTimeout(() => this.updateUsageChart(), 100);
        });
    }
    
    // Utility methods
    showLoadingIndicator(message = 'Loading...') {
        const indicator = document.createElement('div');
        indicator.className = 'dashboard-loading';
        indicator.innerHTML = `
            <div class="loading-spinner"></div>
            <span>${message}</span>
        `;
        document.body.appendChild(indicator);
        return indicator;
    }
    
    hideLoadingIndicator(indicator) {
        if (indicator && indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
        }
    }
    
    showErrorMessage(message) {
        const toast = document.createElement('div');
        toast.className = 'error-toast';
        toast.textContent = message;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('show');
        }, 100);
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 5000);
    }
    
    closeModal(modal) {
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    formatDate(dateString) {
        return new Date(dateString).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
    
    trackEvent(eventName, parameters = {}) {
        if (typeof gtag !== 'undefined') {
            gtag('event', eventName, parameters);
        }
        
        // Also track in console for development
        console.log('Dashboard Event:', eventName, parameters);
    }
}

// Global dashboard instance
let dashboard;

// Initialize dashboard when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        dashboard = new ProofKitDashboard();
    });
} else {
    dashboard = new ProofKitDashboard();
}

// Export for external use
window.ProofKitDashboard = ProofKitDashboard;