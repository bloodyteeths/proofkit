# UTM Tracking Strategy for ProofKit

## Overview
Comprehensive UTM parameter strategy to track campaign attribution across all marketing channels with €10/day total Google Ads budget distributed across 5 industry-specific campaigns.

## Budget Allocation
- **Total Daily Budget:** €10
- **Per Industry Campaign:** €2/day
- **Industries:** Powder Coat, HACCP, Autoclave, Concrete, Vaccine
- **Expected Monthly Spend:** €300 total

## UTM Parameter Structure

### Standard UTM Parameters
```
utm_source: Traffic source identifier
utm_medium: Marketing medium category  
utm_campaign: Specific campaign identifier
utm_content: Ad variation or content piece
utm_term: Paid search keywords (for Google Ads)
```

### UTM Source Values
- `google` - Google Ads campaigns
- `linkedin` - LinkedIn organic and paid
- `reddit` - Reddit community posts
- `email` - Email marketing campaigns
- `webinar` - Webinar follow-up traffic
- `referral` - Partner and customer referrals
- `organic` - Direct organic traffic with UTM

### UTM Medium Values
- `cpc` - Cost-per-click advertising (Google Ads)
- `social` - Social media posts
- `organic` - Organic social and search
- `referral` - Referral program traffic
- `email` - Email campaigns
- `webinar` - Webinar-generated traffic

### UTM Campaign Structure
**Format:** `industry_[vertical]` or `type_[category]`

**Industry Campaigns:**
- `industry_powder` - Powder coat cure validation
- `industry_haccp` - HACCP cooling curve compliance
- `industry_autoclave` - Autoclave sterilization validation
- `industry_concrete` - Concrete curing compliance
- `industry_vaccine` - Vaccine cold chain monitoring

**Email Campaigns:**
- `welcome_series` - New user onboarding
- `upsell_logo` - Logo-free PDF upsell
- `nurture_post` - Post-upload nurture sequence

**Content Campaigns:**
- `webinar_powder` - Powder coat webinar
- `webinar_autoclave` - Autoclave webinar
- `case_study` - Industry case studies

### UTM Content Values
**Ad Variations:**
- `headline1` - Primary headline variant
- `headline2` - Secondary headline variant
- `compliance` - Compliance-focused messaging
- `quick` - Speed-focused messaging
- `professional` - Professional-grade messaging

**Email Content:**
- `cta_upgrade` - Upgrade call-to-action
- `cta_download` - Download template CTA
- `cta_verify` - Verification link click

## Campaign-Specific UTM Examples

### Google Ads - Powder Coat Campaign
```
https://proofkit.dev/?utm_source=google&utm_medium=cpc&utm_campaign=industry_powder&utm_content=headline1&utm_term=powder+coat+cure+certificate
```

### LinkedIn - HACCP Content
```
https://proofkit.dev/?utm_source=linkedin&utm_medium=social&utm_campaign=industry_haccp&utm_content=cooling_curve_post
```

### Email - Upsell Campaign
```
https://proofkit.dev/upgrade?utm_source=email&utm_medium=email&utm_campaign=upsell_logo&utm_content=cta_upgrade
```

### Referral Program
```
https://proofkit.dev/?utm_source=referral&utm_medium=referral&utm_campaign=customer_referral&utm_content=verify_link
```

## Tracking Implementation

### Google Analytics 4 Custom Events
```javascript
// Track campaign attribution
gtag('event', 'campaign_attribution', {
  utm_source: getUTMParam('utm_source'),
  utm_medium: getUTMParam('utm_medium'),
  utm_campaign: getUTMParam('utm_campaign'),
  utm_content: getUTMParam('utm_content')
});

// Track upload with attribution
gtag('event', 'upload_csv', {
  campaign_source: sessionStorage.getItem('utm_source'),
  campaign_medium: sessionStorage.getItem('utm_medium'),
  campaign_name: sessionStorage.getItem('utm_campaign'),
  file_size: fileSize,
  industry: detectedIndustry
});
```

### URL Parameter Capture
Store UTM parameters in sessionStorage on landing:
```javascript
// Capture and store UTM parameters
const urlParams = new URLSearchParams(window.location.search);
const utmParams = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];

utmParams.forEach(param => {
  const value = urlParams.get(param);
  if (value) {
    sessionStorage.setItem(param, value);
  }
});
```

## Attribution Reporting

### Daily Metrics Dashboard
Track these metrics by UTM parameters:
- **Traffic:** Visitors, sessions, bounce rate
- **Engagement:** Page views, time on site, upload initiation
- **Conversion:** CSV uploads, successful compilations, PDF downloads
- **Revenue:** One-off purchases, subscription signups, MRR attribution

### Weekly Campaign Performance Report
```
Campaign | Spend | Clicks | CTR | Uploads | CVR | CPA | Revenue | ROAS
industry_powder | €14 | 87 | 2.3% | 12 | 13.8% | €1.17 | €84 | 6.0x
industry_haccp | €14 | 93 | 2.8% | 15 | 16.1% | €0.93 | €105 | 7.5x
industry_autoclave | €14 | 76 | 2.1% | 9 | 11.8% | €1.56 | €63 | 4.5x
industry_concrete | €14 | 82 | 2.4% | 11 | 13.4% | €1.27 | €77 | 5.5x
industry_vaccine | €14 | 89 | 2.6% | 13 | 14.6% | €1.08 | €91 | 6.5x
```

### Key Performance Indicators
- **Target CPA (Cost Per Acquisition):** ≤ €12 per upload
- **Target CVR (Conversion Rate):** ≥ 12% uploads from clicks
- **Target ROAS (Return on Ad Spend):** ≥ 5.0x revenue/spend
- **Upload → Paid Conversion:** ≥ 5% overall target

## Campaign Optimization Strategy

### A/B Testing Schedule
- **Week 1-2:** Test headline variations (headline1 vs headline2)
- **Week 3-4:** Test description messaging (speed vs compliance focus)
- **Week 5-6:** Test landing page variations by industry
- **Week 7-8:** Test call-to-action positioning and wording

### Budget Reallocation Rules
- **High Performance:** Campaign with CVR >15% gets +€1/day budget
- **Low Performance:** Campaign with CVR <8% gets -€0.50/day budget
- **Industry Seasonality:** Adjust based on compliance audit seasons
- **Geographic Performance:** Focus spend on highest-converting regions

### Quality Score Optimization
- **Keyword Relevance:** Align ad copy with target search terms
- **Landing Page Experience:** Industry-specific landing pages
- **Expected CTR:** Rotate ad variations to maintain freshness
- **Ad Relevance:** Use dynamic keyword insertion where appropriate

## Attribution Model

### Multi-Touch Attribution
- **First Touch:** 40% credit to initial campaign
- **Last Touch:** 40% credit to final campaign before conversion
- **Middle Touch:** 20% distributed across journey touchpoints

### Customer Journey Mapping
1. **Awareness:** Industry-specific Google Ad click
2. **Consideration:** Template download or spec exploration
3. **Trial:** First CSV upload and compilation
4. **Conversion:** Purchase of logo-free PDF or subscription
5. **Advocacy:** Referral program participation

This UTM strategy ensures comprehensive tracking of our €10/day Google Ads investment across all five industry verticals while enabling data-driven optimization decisions.