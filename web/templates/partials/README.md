# ProofKit Analytics Integration

## Overview

This directory contains HTML partials for ProofKit's analytics and advertising conversion tracking system. The implementation provides privacy-compliant GA4 analytics with cookie consent integration and Google Ads conversion tracking.

## Files

### `analytics.html`
Main analytics integration partial that includes:
- Google Analytics 4 (GA4) configuration with privacy settings
- Cookie consent integration with existing consent system
- Event tracking for key conversion actions
- Google Ads conversion tracking integration
- Automatic event detection for user interactions

### `analytics_test.html` 
Test page for validating analytics implementation:
- Cookie consent testing interface
- Manual event trigger buttons  
- Real-time status monitoring
- Console output display for debugging

## Setup Instructions

### 1. Configure Measurement IDs

Replace placeholder IDs in `analytics.html`:

```javascript
// Update GA4 Measurement ID
const GA4_MEASUREMENT_ID = 'G-YOUR-ACTUAL-ID';

// Update Google Ads Conversion IDs
const GOOGLE_ADS_CONFIG = {
    conversion_id: 'AW-YOUR-CONVERSION-ID',
    conversions: {
        signup: 'AW-XXXXXXXX/SIGNUP-LABEL',
        compile_ok: 'AW-XXXXXXXX/VALIDATION-LABEL', 
        purchase: 'AW-XXXXXXXX/PURCHASE-LABEL'
    }
};
```

### 2. Verify Integration

1. The partial is automatically included in `base.html`
2. Cookie consent system is already configured
3. Test using `/partials/analytics_test.html` (development only)

### 3. Key Events Tracked

- **File Upload**: `file_upload` - User uploads CSV file
- **Successful Validation**: `compile_ok` - CSV validation succeeds (PRIMARY CONVERSION)
- **User Signup**: `sign_up` - User registers/subscribes (LEAD CONVERSION)  
- **Purchase**: `purchase` - User upgrades to paid plan (REVENUE CONVERSION)
- **Engagement**: `engagement` - Navigation, downloads, CTA clicks
- **Errors**: `exception` - JavaScript and HTMX errors for debugging

## Privacy & Compliance

### Cookie Consent Integration
- Analytics only load when user grants consent via cookie banner
- Respects "Essential Only" choice by disabling tracking
- Users can change consent via footer "Cookie Settings" link

### GDPR Compliance
- IP anonymization enabled (`anonymize_ip: true`)
- Google Signals disabled (`allow_google_signals: false`)
- Ad personalization disabled (`allow_ad_personalization_signals: false`)
- No data processing without explicit consent

### Data Retention
- GA4: 14 months (configurable)
- Google Ads: 540 days
- Local storage: Cookie consent choice only

## Event Tracking Usage

### Manual Event Tracking

```javascript
// Track file upload
trackUploadEvent('text/csv', 1048576, 'powder_coat');

// Track successful validation (primary conversion)
trackCompileOkEvent('powder_coat', 'pass', 2500);

// Track user signup (lead conversion)  
trackSignupEvent('organic', 'email_campaign');

// Track purchase (revenue conversion)
trackPurchaseEvent('professional', 99, 'USD');

// Track page view with context
trackPageView('Powder Coat Validation', 'powder_coat');

// Track engagement events
trackEngagement('cta_click', 'Get Started Button', 3);

// Track errors for debugging
trackError('validation_error', 'CSV format invalid', '/app');
```

### Automatic Event Tracking

The following events are tracked automatically:
- File uploads via `#csv_file` input
- Form submissions via `#upload-form` HTMX requests
- Navigation clicks on nav links
- File downloads (PDF, ZIP)
- CTA button clicks
- JavaScript and HTMX errors

## Testing & Validation

### Development Testing

1. **Open Test Page**: `/partials/analytics_test.html`
2. **Grant Analytics Consent**: Click "Accept Analytics"
3. **Test Events**: Use test buttons to trigger events
4. **Monitor Console**: Check for event firing confirmations
5. **Verify GA4**: Check GA4 Real-time reports

### Production Validation

1. **GA4 Real-time Reports**: Verify events appear within minutes
2. **Google Ads Conversions**: Check conversion import after 24 hours
3. **Attribution Testing**: Test conversion attribution across devices
4. **Privacy Compliance**: Verify tracking respects consent choices

## Troubleshooting

### Common Issues

**Analytics Not Loading**
- Check browser console for JavaScript errors
- Verify GA4 Measurement ID is correct
- Ensure user has granted analytics consent

**Events Not Firing**
- Test with browser developer tools
- Check if ad blockers are interfering
- Verify element IDs match event listeners

**Conversion Tracking Issues**
- Confirm Google Ads conversion IDs are correct
- Check GA4-Google Ads account linking
- Verify conversion import settings

**Privacy Consent Issues**
- Test consent banner functionality
- Check localStorage for consent state
- Verify consent is properly propagated to analytics

### Debug Commands

```javascript
// Check consent status
localStorage.getItem('cookie_consent');

// Check GA4 status
window.gtag && window.ga4Loaded;

// Check dataLayer
window.dataLayer;

// Manual consent update
updateAnalyticsConsent(true);

// Test event tracking
trackEngagement('debug_test', 'manual_trigger', 1);
```

## Business Impact

### Conversion Optimization
- Track user journey from upload to successful validation
- Identify drop-off points in validation process
- Optimize for highest-value conversion events

### Marketing Attribution  
- Measure effectiveness of different traffic sources
- Optimize Google Ads campaigns with conversion data
- Track ROI across marketing channels

### Product Analytics
- Monitor usage patterns by industry type
- Track feature adoption and user engagement
- Identify opportunities for product improvement

## Maintenance

### Regular Tasks
- Monitor conversion tracking accuracy monthly
- Review privacy compliance quarterly  
- Update measurement IDs when accounts change
- Test analytics functionality after major releases

### Performance Monitoring
- Track script load times and impact on page speed
- Monitor analytics data quality and completeness
- Review consent rates and user privacy preferences

---

**Implementation Date**: August 2025  
**Last Updated**: August 2025  
**Next Review**: September 2025