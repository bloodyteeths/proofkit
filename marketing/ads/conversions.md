# Google Ads Conversion Tracking & Import Guide

## Overview

This guide explains how to set up and import GA4 conversion data into Google Ads for ProofKit's advertising campaigns. The integration enables automated bidding strategies (tCPA) once sufficient conversion data is collected.

## Prerequisites

- Google Analytics 4 (GA4) property configured
- Google Ads account with admin access  
- GA4 and Google Ads accounts linked
- ProofKit analytics partial implemented (`/web/templates/partials/analytics.html`)

## Conversion Events Setup

### 1. GA4 Conversion Events

ProofKit tracks these key conversion events in GA4:

| Event Name | Description | Value | Business Impact |
|------------|-------------|-------|-----------------|
| `compile_ok` | Successful CSV validation | 10 | Primary conversion - validates product value |
| `sign_up` | User registration/signup | 5 | Lead generation - builds email list |
| `purchase` | Plan upgrade/purchase | Variable | Revenue generation |
| `file_upload` | CSV file uploaded | 1 | Engagement indicator |

### 2. Google Ads Conversion Actions

Set up corresponding conversion actions in Google Ads:

1. **Successful Validation** (`compile_ok`)
   - **Type**: Website action
   - **Value**: 10 USD
   - **Count**: One per conversion
   - **Window**: 30 days view, 1 day click
   - **Attribution**: Last click

2. **Lead Signup** (`sign_up`) 
   - **Type**: Website action
   - **Value**: 5 USD
   - **Count**: One per conversion
   - **Window**: 30 days view, 7 days click
   - **Attribution**: Last click

3. **Purchase** (`purchase`)
   - **Type**: Purchase/Sale
   - **Value**: Use transaction value
   - **Count**: Every conversion
   - **Window**: 30 days view, 30 days click
   - **Attribution**: Last click

## Implementation Steps

### Step 1: Configure GA4 Measurement ID

1. Update `/web/templates/partials/analytics.html`:
   ```javascript
   // Replace placeholder with actual GA4 Measurement ID
   const GA4_MEASUREMENT_ID = 'G-YOUR-ACTUAL-ID';
   ```

2. Verify GA4 property is receiving events in real-time reports

### Step 2: Mark GA4 Events as Conversions

1. In GA4 Admin → Events
2. Find each conversion event (`compile_ok`, `sign_up`, `purchase`)
3. Toggle "Mark as conversion" to ON
4. Verify conversion counting method matches business goals

### Step 3: Link GA4 to Google Ads

1. In GA4 Admin → Product Links → Google Ads Links
2. Click "Link" and select your Google Ads account
3. Configure link settings:
   - **Export**: Enable "Web conversions"
   - **Import**: Enable "Google Ads clicks data"
   - **Personalized advertising**: Based on privacy policy

### Step 4: Import Conversions to Google Ads

1. In Google Ads → Tools & Settings → Conversions
2. Click the "+" button → "Import" 
3. Select "Google Analytics 4 properties"
4. Choose your linked GA4 property
5. Select conversions to import:
   - ✅ `compile_ok` → "Successful Validation"
   - ✅ `sign_up` → "Lead Signup" 
   - ✅ `purchase` → "Purchase/Upgrade"

### Step 5: Configure Google Ads Conversion IDs

1. Get conversion IDs from Google Ads → Conversions
2. Update `/web/templates/partials/analytics.html`:
   ```javascript
   const GOOGLE_ADS_CONFIG = {
       conversion_id: 'AW-YOUR-CONVERSION-ID',
       conversions: {
           signup: 'AW-XXXXXXXX/SIGNUP-LABEL',
           compile_ok: 'AW-XXXXXXXX/VALIDATION-LABEL', 
           purchase: 'AW-XXXXXXXX/PURCHASE-LABEL'
       }
   };
   ```

## Automated Bidding Strategy (tCPA)

### Prerequisites for tCPA

- **Minimum 30 conversions** in the last 30 days per campaign
- **Consistent conversion volume** for at least 2 weeks
- **Stable conversion rates** (avoid during major site changes)

### Recommended tCPA Values

Based on ProofKit's business model:

| Campaign Type | Target CPA | Conversion Event | Rationale |
|---------------|------------|------------------|-----------|
| **Brand Search** | $8-12 | `compile_ok` | High-intent users, lower competition |
| **Industry Keywords** | $15-25 | `compile_ok` | Medium competition, qualified traffic |
| **Competitor Terms** | $20-35 | `compile_ok` | Higher competition, acquisition focus |
| **Lead Generation** | $3-7 | `sign_up` | Lower barrier, volume focus |
| **Remarketing** | $5-10 | `compile_ok` | Warm audience, higher conversion rate |

### Implementation Timeline

**Week 1-2: Data Collection**
- Monitor conversion volume and quality
- Ensure GA4-Google Ads data sync is working
- Verify conversion attribution accuracy

**Week 3-4: Optimization Preparation**
- Analyze conversion patterns by keyword/ad group
- Identify top-performing traffic sources
- Set baseline CPA benchmarks

**Week 5+: tCPA Implementation**
- Start with conservative tCPA targets (20% above current CPA)
- Implement gradually across 1-2 campaigns first
- Monitor performance for 2 weeks before expanding

## Monitoring & Optimization

### Key Metrics to Track

1. **Conversion Tracking Health**
   - GA4 vs Google Ads conversion discrepancies
   - Attribution model impact on conversion counts
   - Cross-device conversion patterns

2. **Campaign Performance** 
   - Cost per conversion by campaign/ad group
   - Conversion rate trends over time
   - Quality score impact on conversion costs

3. **Business Impact**
   - Customer lifetime value by acquisition channel
   - Conversion to paid customer rate
   - Industry-specific conversion performance

### Troubleshooting Common Issues

**Low Conversion Volume (<30/month)**
- Expand keyword targeting to include broader terms
- Test different ad copy focused on free validation
- Consider lowering conversion event value (track micro-conversions)

**High CPA After tCPA Implementation**
- Reduce tCPA target by 10-15%
- Review Search Terms report for irrelevant queries
- Adjust audience targeting to exclude non-relevant users

**GA4-Google Ads Data Discrepancies**
- Check attribution windows match between platforms
- Verify GA4 conversions are properly marked as conversions
- Review cross-domain tracking implementation

**Conversion Tracking Not Firing**
- Test analytics implementation with browser dev tools
- Verify cookie consent is properly granted for test users
- Check for JavaScript errors blocking conversion tracking

## Privacy & Compliance

### GDPR Compliance
- Conversions only tracked with explicit user consent
- Analytics cookies clearly disclosed in privacy policy
- Users can withdraw consent and opt-out at any time

### Data Retention
- GA4: 14 months for user-level data (configurable)
- Google Ads: 540 days for conversion data
- ProofKit logs: 30 days for analytics events

### Cookie Configuration
```javascript
// Privacy-focused GA4 configuration
gtag('config', GA4_MEASUREMENT_ID, {
    anonymize_ip: true,
    allow_google_signals: false,
    allow_ad_personalization_signals: false
});
```

## Testing & Validation

### Testing Conversion Tracking

1. **Local Testing**
   ```bash
   # Enable analytics consent in browser console
   localStorage.setItem('cookie_consent', 'analytics');
   
   # Trigger test events
   trackCompileOkEvent('powder_coat', 'pass', 5000);
   trackSignupEvent('organic', 'test_campaign');
   ```

2. **GA4 Real-Time Validation**
   - Upload test CSV file
   - Check GA4 Real-time → Events for `file_upload` and `compile_ok`
   - Verify event parameters are populated correctly

3. **Google Ads Conversion Validation**
   - Use Google Ads Preview & Diagnosis tool
   - Check conversions appear in Google Ads within 24 hours
   - Verify conversion values match GA4 configuration

### Performance Benchmarks

**Industry Averages for B2B SaaS:**
- Search ads CTR: 2-5%
- Landing page conversion rate: 2-5%
- Cost per lead: $50-200
- Lead to customer rate: 5-15%

**ProofKit Target Benchmarks:**
- File upload rate: >8% (from ad clicks)
- Successful validation rate: >60% (from uploads)
- Signup conversion rate: >3% (from successful validations)
- Trial to paid conversion: >10%

## Conclusion

This conversion tracking setup enables data-driven optimization of ProofKit's Google Ads campaigns. Once 50+ conversions are achieved per campaign, automated bidding strategies (tCPA) can be implemented to scale efficiently while maintaining target cost-per-acquisition goals.

The integration respects user privacy through consent-gated tracking while providing detailed conversion attribution for marketing optimization.

---

**Last Updated:** August 2025  
**Version:** 1.0  
**Next Review:** September 2025