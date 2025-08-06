# ProofKit Analytics & Conversion Tracking Setup

## Overview
Comprehensive tracking system for €10/day Google Ads campaigns, referral attribution, email conversions, and revenue analytics across all five industry verticals.

## Google Analytics 4 Configuration

### Enhanced Ecommerce Setup
```javascript
// Configure GA4 with enhanced ecommerce
gtag('config', 'GA_MEASUREMENT_ID', {
  custom_map: {
    'custom_parameter_1': 'industry',
    'custom_parameter_2': 'spec_type', 
    'custom_parameter_3': 'utm_campaign',
    'custom_parameter_4': 'referral_source'
  }
});

// Purchase event for logo-free PDF
gtag('event', 'purchase', {
  transaction_id: transactionId,
  value: 7.00,
  currency: 'EUR',
  items: [{
    item_id: 'logo_free_pdf',
    item_name: 'Logo-Free PDF Certificate',
    item_category: 'Digital Product',
    item_variant: industryType,
    price: 7.00,
    quantity: 1
  }],
  industry: industryType,
  spec_type: specType,
  utm_campaign: sessionStorage.getItem('utm_campaign'),
  referral_source: sessionStorage.getItem('referral_source')
});
```

### Custom Events Tracking
```javascript
// CSV Upload Event
gtag('event', 'upload_csv', {
  event_category: 'Engagement',
  event_label: industryType,
  custom_parameter_1: industryType,
  custom_parameter_2: specType,
  custom_parameter_3: sessionStorage.getItem('utm_campaign'),
  file_size: fileSizeKB,
  processing_time: processingTimeMs
});

// Compilation Success Event  
gtag('event', 'compile_success', {
  event_category: 'Conversion',
  event_label: industryType,
  custom_parameter_1: industryType,
  custom_parameter_2: specType,
  validation_result: 'PASS' | 'FAIL',
  processing_time: processingTimeMs
});

// PDF Download Event
gtag('event', 'download_pdf', {
  event_category: 'Engagement', 
  event_label: industryType,
  custom_parameter_1: industryType,
  custom_parameter_2: specType,
  pdf_type: 'watermarked' | 'logo_free',
  file_size: fileSizeKB
});

// Email Link Click
gtag('event', 'email_click', {
  event_category: 'Email',
  event_label: emailCampaign,
  custom_parameter_3: emailCampaign,
  email_type: 'upsell' | 'welcome' | 'nurture',
  cta_position: 'header' | 'body' | 'footer'
});

// Referral Conversion
gtag('event', 'referral_conversion', {
  event_category: 'Referral',
  event_label: 'signup',
  custom_parameter_4: referralSource,
  conversion_type: 'signup' | 'purchase',
  credit_amount: 5.00
});
```

## Conversion Tracking Implementation

### Google Ads Conversion Actions
```javascript
// Google Ads conversion tracking
function trackGoogleAdsConversion(conversionLabel, value = null) {
  gtag('event', 'conversion', {
    'send_to': 'AW-CONVERSION_ID/' + conversionLabel,
    'value': value,
    'currency': 'EUR'
  });
}

// Upload conversion (primary goal)
trackGoogleAdsConversion('UPLOAD_CONVERSION_LABEL');

// Purchase conversion (revenue goal)  
trackGoogleAdsConversion('PURCHASE_CONVERSION_LABEL', 7.00);

// Subscription conversion
trackGoogleAdsConversion('SUBSCRIPTION_CONVERSION_LABEL', 15.00);
```

### Facebook Pixel Integration
```javascript
// Facebook Pixel for retargeting
fbq('init', 'FACEBOOK_PIXEL_ID');
fbq('track', 'PageView');

// Custom events
fbq('track', 'Lead', {
  content_category: industryType,
  content_name: 'CSV Upload',
  value: 0,
  currency: 'EUR'
});

fbq('track', 'Purchase', {
  content_type: 'product',
  content_ids: ['logo_free_pdf'],
  content_category: industryType,
  value: 7.00,
  currency: 'EUR'
});
```

## UTM Parameter Capture & Attribution

### Client-Side UTM Tracking
```javascript
// Capture and persist UTM parameters
function captureUTMParameters() {
  const urlParams = new URLSearchParams(window.location.search);
  const utmParams = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  
  utmParams.forEach(param => {
    const value = urlParams.get(param);
    if (value) {
      sessionStorage.setItem(param, value);
      
      // Set GA4 user property for attribution
      gtag('config', 'GA_MEASUREMENT_ID', {
        custom_map: { [param]: value }
      });
    }
  });
  
  // Capture referral parameter
  const referralId = urlParams.get('ref') || urlParams.get('utm_content');
  if (referralId && urlParams.get('utm_source') === 'referral') {
    sessionStorage.setItem('referral_source', referralId);
  }
}

// Call on page load
document.addEventListener('DOMContentLoaded', captureUTMParameters);
```

### Server-Side Attribution Storage
```python
# Attribution model for database storage
class UserAttribution:
    user_id: str
    first_touch_source: str
    first_touch_medium: str  
    first_touch_campaign: str
    first_touch_timestamp: datetime
    
    last_touch_source: str
    last_touch_medium: str
    last_touch_campaign: str
    last_touch_timestamp: datetime
    
    referral_source: Optional[str]
    email_attribution: Optional[str]

# Store attribution on user action
def store_attribution(user_id: str, session_data: dict):
    attribution = UserAttribution.get_or_create(user_id)
    
    # First touch attribution (only set once)
    if not attribution.first_touch_source:
        attribution.first_touch_source = session_data.get('utm_source')
        attribution.first_touch_medium = session_data.get('utm_medium')
        attribution.first_touch_campaign = session_data.get('utm_campaign')
        attribution.first_touch_timestamp = datetime.utcnow()
    
    # Last touch attribution (always update)
    attribution.last_touch_source = session_data.get('utm_source')
    attribution.last_touch_medium = session_data.get('utm_medium') 
    attribution.last_touch_campaign = session_data.get('utm_campaign')
    attribution.last_touch_timestamp = datetime.utcnow()
    
    # Referral attribution
    if session_data.get('referral_source'):
        attribution.referral_source = session_data.get('referral_source')
    
    attribution.save()
```

## Revenue Attribution Model

### Multi-Touch Attribution Logic
```python
def calculate_attribution_credit(user_attribution: UserAttribution, revenue: float):
    """
    Attribution Model:
    - First Touch: 40% credit
    - Last Touch: 40% credit  
    - Referral: 20% credit (if applicable)
    """
    
    attribution_credits = {}
    
    # First touch (40%)
    first_touch_key = f"{user_attribution.first_touch_source}_{user_attribution.first_touch_campaign}"
    attribution_credits[first_touch_key] = revenue * 0.4
    
    # Last touch (40%) 
    last_touch_key = f"{user_attribution.last_touch_source}_{user_attribution.last_touch_campaign}"
    if last_touch_key != first_touch_key:
        attribution_credits[last_touch_key] = revenue * 0.4
    else:
        attribution_credits[first_touch_key] = revenue * 0.8  # Same source gets 80%
    
    # Referral bonus (20%)
    if user_attribution.referral_source:
        referral_key = f"referral_{user_attribution.referral_source}"
        attribution_credits[referral_key] = revenue * 0.2
        
        # Adjust other sources proportionally
        for key in list(attribution_credits.keys()):
            if key != referral_key:
                attribution_credits[key] *= 0.8
    
    return attribution_credits
```

## Campaign Performance Dashboard

### Daily Metrics Collection
```sql
-- Daily campaign performance query
CREATE VIEW daily_campaign_metrics AS
SELECT 
    DATE(created_at) as date,
    utm_source,
    utm_medium,
    utm_campaign,
    
    -- Traffic metrics
    COUNT(DISTINCT user_id) as unique_visitors,
    COUNT(*) as total_sessions,
    
    -- Engagement metrics  
    SUM(CASE WHEN action_type = 'upload_csv' THEN 1 ELSE 0 END) as uploads,
    SUM(CASE WHEN action_type = 'compile_success' THEN 1 ELSE 0 END) as successful_compilations,
    SUM(CASE WHEN action_type = 'download_pdf' THEN 1 ELSE 0 END) as pdf_downloads,
    
    -- Revenue metrics
    SUM(CASE WHEN action_type = 'purchase' THEN revenue_amount ELSE 0 END) as revenue,
    COUNT(CASE WHEN action_type = 'purchase' THEN 1 END) as purchases,
    
    -- Conversion rates
    ROUND(COUNT(CASE WHEN action_type = 'upload_csv' THEN 1 END) * 100.0 / COUNT(DISTINCT user_id), 2) as upload_conversion_rate,
    ROUND(COUNT(CASE WHEN action_type = 'purchase' THEN 1 END) * 100.0 / COUNT(CASE WHEN action_type = 'upload_csv' THEN 1 END), 2) as purchase_conversion_rate

FROM user_actions ua
JOIN user_attribution attr ON ua.user_id = attr.user_id  
WHERE ua.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
GROUP BY DATE(ua.created_at), utm_source, utm_medium, utm_campaign;
```

### Weekly Performance Report
```python
def generate_weekly_report():
    """Generate weekly campaign performance report"""
    
    report_data = {
        'campaign_performance': [],
        'top_performers': [],
        'optimization_recommendations': []
    }
    
    # Get campaign data for last 7 days
    campaigns = db.execute("""
        SELECT 
            utm_campaign,
            SUM(ad_spend) as spend,
            SUM(clicks) as clicks, 
            SUM(uploads) as uploads,
            SUM(revenue) as revenue,
            AVG(upload_conversion_rate) as avg_cvr,
            SUM(revenue) / SUM(ad_spend) as roas
        FROM daily_campaign_metrics 
        WHERE date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
          AND utm_source = 'google'
          AND utm_medium = 'cpc'
        GROUP BY utm_campaign
    """)
    
    for campaign in campaigns:
        cpa = campaign['spend'] / campaign['uploads'] if campaign['uploads'] > 0 else 0
        
        report_data['campaign_performance'].append({
            'campaign': campaign['utm_campaign'],
            'spend': f"€{campaign['spend']:.2f}",
            'clicks': campaign['clicks'],
            'uploads': campaign['uploads'],
            'cvr': f"{campaign['avg_cvr']:.1f}%",
            'cpa': f"€{cpa:.2f}",
            'revenue': f"€{campaign['revenue']:.2f}",
            'roas': f"{campaign['roas']:.1f}x"
        })
    
    return report_data
```

## Key Performance Indicators (KPIs)

### Primary KPIs
```python
# Target metrics for €10/day ad spend
TARGET_METRICS = {
    'daily_clicks': 85,  # Avg across 5 campaigns
    'daily_uploads': 12,  # Target 14% CTR to upload
    'daily_revenue': 42,  # €6 ROAS target
    'cpa_upload': 12,     # Cost per upload ≤ €12
    'upload_to_purchase': 5,  # 5% conversion rate
    'monthly_new_customers': 108,  # 12 uploads/day * 30 days * 30% new
    'monthly_attributed_revenue': 1260  # €42/day * 30 days
}
```

### Weekly KPI Tracking
```python
def calculate_weekly_kpis():
    """Calculate and report weekly KPIs"""
    
    current_week = db.execute("""
        SELECT 
            COUNT(DISTINCT user_id) as weekly_visitors,
            SUM(CASE WHEN action_type = 'upload_csv' THEN 1 ELSE 0 END) as weekly_uploads,
            SUM(CASE WHEN action_type = 'purchase' THEN revenue_amount ELSE 0 END) as weekly_revenue,
            SUM(ad_spend) as weekly_spend
        FROM user_actions ua
        JOIN campaign_spend cs ON ua.utm_campaign = cs.campaign_name
        WHERE ua.created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
    """).fetchone()
    
    kpis = {
        'visitors': current_week['weekly_visitors'],
        'uploads': current_week['weekly_uploads'], 
        'revenue': current_week['weekly_revenue'],
        'spend': current_week['weekly_spend'],
        'cpa': current_week['weekly_spend'] / current_week['weekly_uploads'],
        'roas': current_week['weekly_revenue'] / current_week['weekly_spend'],
        'upload_cvr': current_week['weekly_uploads'] / current_week['weekly_visitors'] * 100
    }
    
    return kpis
```

## Alert System

### Performance Alerts
```python
def check_performance_alerts():
    """Monitor campaign performance and send alerts"""
    
    alerts = []
    daily_metrics = get_daily_metrics()
    
    # High CPA alert
    if daily_metrics['cpa'] > 15:
        alerts.append({
            'type': 'HIGH_CPA',
            'message': f"CPA is €{daily_metrics['cpa']:.2f}, above €15 threshold",
            'action': 'Review keyword bids and ad copy performance'
        })
    
    # Low conversion rate alert  
    if daily_metrics['upload_cvr'] < 10:
        alerts.append({
            'type': 'LOW_CVR', 
            'message': f"Upload CVR is {daily_metrics['upload_cvr']:.1f}%, below 10% threshold",
            'action': 'Test new ad copy or landing page variations'
        })
    
    # Budget pacing alert
    if daily_metrics['spend'] < 8:
        alerts.append({
            'type': 'UNDER_SPEND',
            'message': f"Daily spend is €{daily_metrics['spend']:.2f}, below €10 target", 
            'action': 'Increase bids or expand keyword targeting'
        })
    
    return alerts
```

### Automated Reporting
```python
# Daily email report to marketing team
def send_daily_report():
    """Send automated daily performance report"""
    
    metrics = get_daily_metrics()
    alerts = check_performance_alerts()
    
    email_body = f"""
    Daily ProofKit Marketing Report - {datetime.now().strftime('%Y-%m-%d')}
    
    Campaign Performance:
    • Total Spend: €{metrics['spend']:.2f}
    • Clicks: {metrics['clicks']}
    • Uploads: {metrics['uploads']} 
    • Revenue: €{metrics['revenue']:.2f}
    • CPA: €{metrics['cpa']:.2f}
    • ROAS: {metrics['roas']:.1f}x
    
    Top Performing Campaign: {metrics['top_campaign']}
    Conversion Rate: {metrics['upload_cvr']:.1f}%
    
    {len(alerts)} Alerts: {', '.join([alert['type'] for alert in alerts])}
    
    View full dashboard: https://proofkit.dev/admin/analytics
    """
    
    send_email(
        to=['marketing@proofkit.dev'],
        subject=f"Daily Marketing Report - {datetime.now().strftime('%m/%d')}",
        body=email_body
    )
```

This comprehensive analytics setup provides full visibility into campaign performance, attribution accuracy, and ROI measurement across all marketing channels while maintaining GDPR compliance and data accuracy.