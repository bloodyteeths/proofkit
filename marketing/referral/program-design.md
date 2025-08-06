# ProofKit Referral Program Design

## Program Overview
Customer-driven growth program leveraging verification links to acquire new users with €5 credit incentives and viral loop mechanics.

## Core Mechanics

### Referral Trigger Point
- **Activation:** Customer completes successful PDF generation
- **Referral Link:** Added to certificate verification page footer
- **Incentive Structure:** €5 credit for referrer when new user signs up
- **New User Benefit:** €5 welcome credit (equivalent to 1 logo-free PDF)

### Referral Flow
1. **Customer generates certificate** → receives verification link
2. **Verification page displays** → "Shared by [Company Name] - Get your own certificates"
3. **New visitor clicks referral CTA** → lands on homepage with UTM tracking
4. **New user signs up** → both parties receive €5 credit
5. **Credits auto-apply** → next purchase or subscription

## Technical Implementation

### Verification Page Footer Addition
```html
<!-- Add to certificate verification page -->
<div class="referral-footer">
  <hr class="my-4">
  <div class="text-center">
    <p class="text-sm text-gray-600 mb-2">
      This certificate was generated using ProofKit
    </p>
    <a href="https://proofkit.dev/?utm_source=referral&utm_medium=referral&utm_campaign=verify_link&utm_content={{referrer_id}}" 
       class="btn btn-outline btn-sm">
      Create Your Own Certificates →
    </a>
    <p class="text-xs text-gray-500 mt-2">
      Get €5 credit when you sign up • Professional compliance reports in 30 seconds
    </p>
  </div>
</div>
```

### Credit System Integration
```python
# Referral credit model
class ReferralCredit:
    referrer_email: str
    referee_email: str  
    credit_amount: float = 5.00
    status: str  # pending, credited, expired
    created_at: datetime
    credited_at: Optional[datetime]
    
# Credit application logic
def apply_referral_credit(user_email: str, purchase_amount: float):
    available_credit = get_user_credit_balance(user_email)
    credit_used = min(available_credit, purchase_amount)
    final_amount = purchase_amount - credit_used
    return final_amount, credit_used
```

### UTM Tracking for Referrals
- **Source:** `referral`
- **Medium:** `referral` 
- **Campaign:** `verify_link`
- **Content:** `{referrer_user_id}` for attribution tracking

## Referral Incentive Structure

### Credit Values
- **Referrer Reward:** €5 credit per successful signup
- **Referee Welcome:** €5 credit on account creation
- **Credit Expiry:** 12 months from issue date
- **Minimum Purchase:** €1 to use credits (prevents gaming)

### Credit Usage Rules
- **Logo-free PDF:** €7 (€5 credit + €2 payment)
- **Subscription:** Credits apply to first month
- **Bulk Purchases:** Credits apply to total order
- **No Cash Value:** Credits cannot be withdrawn or transferred

### Anti-Fraud Measures
- **Email Verification:** Both parties must verify email addresses
- **Unique Referrals:** Same email cannot be referred multiple times
- **Activity Requirement:** Referee must complete at least 1 successful upload
- **Time Window:** 30 days for referee to complete qualifying action

## Email Automation Sequences

### Referrer Notification (Immediate)
**Subject:** "Good news! You've earned €5 credit"

```
Hi [Name],

Great news! Someone used your ProofKit referral link and signed up.

You've earned: €5 credit
Available balance: €[total_balance]

Your credit will automatically apply to your next purchase or subscription.

Keep sharing: [Your Referral Link]

Thanks for spreading the word!
The ProofKit Team
```

### Referee Welcome (Immediate)
**Subject:** "Welcome to ProofKit + €5 credit inside"

```
Hi [Name],

Welcome to ProofKit! Thanks to [Referrer Company], you're starting with €5 credit.

Your account:
• €5 welcome credit (expires in 12 months)
• Free uploads forever
• Logo-free PDFs for just €2 (after credit)

Ready to create your first certificate?
[Upload CSV] [Browse Templates]

Questions? Just reply to this email.

Best regards,
The ProofKit Team
```

### Credit Reminder (7 days unused)
**Subject:** "Don't forget your €5 ProofKit credit"

```
Hi [Name],

Quick reminder - you have €5 credit waiting in your ProofKit account.

Perfect for:
✓ Logo-free PDF certificates (€7 - only €2 after credit)
✓ Bulk certificate generation
✓ Monthly subscription (credit applies to first month)

[Use Credit Now] [View Account Balance]

Credit expires in [days_remaining] days.

The ProofKit Team
```

## Referral Link Generation

### Dynamic Link Creation
```python
def generate_referral_link(user_id: str, base_url: str = "https://proofkit.dev") -> str:
    """Generate unique referral link with UTM tracking"""
    utm_params = {
        'utm_source': 'referral',
        'utm_medium': 'referral', 
        'utm_campaign': 'verify_link',
        'utm_content': user_id,
        'ref': user_id  # Backup parameter
    }
    
    query_string = urllib.parse.urlencode(utm_params)
    return f"{base_url}/?{query_string}"
```

### Referral Attribution Tracking
```javascript
// Capture referral parameters on landing page
const urlParams = new URLSearchParams(window.location.search);
const referralId = urlParams.get('utm_content') || urlParams.get('ref');

if (referralId) {
    sessionStorage.setItem('referral_source', referralId);
    
    // Track referral landing
    gtag('event', 'referral_landing', {
        referrer_id: referralId,
        page_location: window.location.href
    });
}

// Apply referral credit on signup
function processSignup(userEmail) {
    const referralSource = sessionStorage.getItem('referral_source');
    if (referralSource) {
        createReferralCredit(referralSource, userEmail);
    }
}
```

## Program Promotion Strategy

### Launch Announcement (Email to existing users)
**Subject:** "Earn €5 for every ProofKit referral"

```
Hi [Name],

We're launching our referral program and you're invited to be among the first participants.

How it works:
1. Share your ProofKit certificates (they already have referral links)
2. When someone clicks and signs up, you both get €5 credit
3. Use credits for logo-free PDFs, subscriptions, or bulk orders

Your referral stats:
• Certificates shared: [count]
• Potential reach: [estimated_views]
• Earning potential: [estimated_earnings]

No extra work needed - just keep using ProofKit as normal!

[View Referral Dashboard] [Share Template Library]

Happy referring!
The ProofKit Team
```

### Verification Page Messaging Testing
**Variant A (Direct):**
"This certificate was generated using ProofKit - Create your own certificates"

**Variant B (Value-focused):**
"Get professional compliance certificates in 30 seconds - Start free"

**Variant C (Social proof):**
"Join 1,000+ companies using ProofKit for compliance reporting"

## Success Metrics & KPIs

### Primary Metrics
- **Referral Conversion Rate:** % of verification page visitors who click referral link
- **Signup Conversion Rate:** % of referral clicks that result in signups
- **Credit Utilization Rate:** % of issued credits that get used
- **Customer Lifetime Value Impact:** CLV difference for referred vs. organic users

### Target Performance
- **Month 1:** 50 referral signups, 2% verification→click rate
- **Month 2:** 120 referral signups, 3% verification→click rate  
- **Month 3:** 200 referral signups, 4% verification→click rate
- **Ongoing:** 15% of new signups from referral program

### Attribution Tracking
```sql
-- Referral performance query
SELECT 
    DATE(created_at) as date,
    COUNT(*) as referral_signups,
    SUM(credit_amount) as credits_issued,
    COUNT(CASE WHEN status = 'credited' THEN 1 END) as credits_used,
    AVG(DATEDIFF(credited_at, created_at)) as avg_days_to_use
FROM referral_credits 
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(created_at)
ORDER BY date;
```

## Customer Support Guidelines

### Common Questions & Responses

**Q: "When will I receive my referral credit?"**
A: Credits are issued immediately when your referral completes their first successful upload. You'll receive an email confirmation and can view your balance in account settings.

**Q: "Why didn't I get credit for my referral?"**
A: Credits require the new user to: (1) click your referral link, (2) create an account, (3) complete at least one successful upload. Check that they used your specific referral link.

**Q: "Can I refer myself or use multiple accounts?"**
A: No, our system prevents self-referrals and duplicate accounts. Each person can only be referred once per email address.

**Q: "Do my credits expire?"**
A: Yes, credits expire 12 months after they're issued. You'll receive reminder emails at 30, 7, and 1 day before expiration.

This referral program design creates a sustainable growth engine while providing clear value to both referrers and new users, with robust tracking and fraud prevention measures.