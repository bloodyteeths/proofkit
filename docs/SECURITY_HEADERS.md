# Security Headers Configuration

This document describes ProofKit's HTTP security headers implementation, designed to protect against common web vulnerabilities and ensure compliance with security best practices.

## Overview

ProofKit implements comprehensive security headers through a custom Starlette middleware (`SecurityHeadersMiddleware`) that automatically applies security headers to all HTTP responses. This provides defense-in-depth protection for web-based attacks.

## Implemented Security Headers

### 1. Strict-Transport-Security (HSTS)

**Configuration:** `max-age=31536000; includeSubDomains; preload`

**Purpose:** Forces browsers to use HTTPS connections only, preventing protocol downgrade attacks and cookie hijacking.

**Details:**
- `max-age=31536000`: Policy valid for 1 year (365 days)
- `includeSubDomains`: Applies to all subdomains
- `preload`: Eligible for browser HSTS preload lists

**Security Benefits:**
- Prevents man-in-the-middle attacks
- Blocks mixed content vulnerabilities
- Protects authentication cookies from interception

### 2. X-Content-Type-Options

**Configuration:** `nosniff`

**Purpose:** Prevents browsers from MIME-type sniffing, which can lead to content-type confusion attacks.

**Security Benefits:**
- Blocks execution of non-JavaScript files as JavaScript
- Prevents CSS injection attacks via MIME confusion
- Enforces proper content-type handling

### 3. Referrer-Policy

**Configuration:** `strict-origin-when-cross-origin`

**Purpose:** Controls how much referrer information is included when navigating to external sites.

**Behavior:**
- Same-origin requests: Full URL sent as referrer
- Cross-origin HTTPS→HTTPS: Origin only
- Cross-origin HTTPS→HTTP: No referrer
- Cross-origin HTTP→HTTP: Origin only

**Security Benefits:**
- Prevents sensitive URL parameters from leaking
- Protects user privacy
- Reduces information disclosure to third parties

### 4. Permissions-Policy

**Configuration:** `geolocation=(), camera=(), microphone=()`

**Purpose:** Restricts access to sensitive browser APIs that could be misused by malicious scripts.

**Restricted APIs:**
- `geolocation=()`: Blocks location access
- `camera=()`: Blocks camera access  
- `microphone=()`: Blocks microphone access

**Security Benefits:**
- Prevents unauthorized device access
- Protects user privacy
- Reduces attack surface for malicious scripts

### 5. Content-Security-Policy (CSP)

**Configuration:**
```
default-src 'self'; 
img-src 'self' data:; 
font-src 'self' data:; 
style-src 'self' 'unsafe-inline'; 
script-src 'self'; 
connect-src 'self';
```

**Purpose:** Controls which resources browsers are allowed to load, providing strong XSS protection.

**Policy Breakdown:**
- `default-src 'self'`: Default restriction to same-origin resources
- `img-src 'self' data:`: Images from same-origin and data URIs (for base64 images)
- `font-src 'self' data:`: Fonts from same-origin and data URIs
- `style-src 'self' 'unsafe-inline'`: Styles from same-origin and inline CSS (required for UI framework)
- `script-src 'self'`: JavaScript only from same-origin
- `connect-src 'self'`: AJAX/fetch requests only to same-origin

**Security Benefits:**
- Prevents XSS attacks
- Blocks unauthorized resource loading
- Limits impact of compromised third-party resources

## DocuSign Integration Considerations

If DocuSign integration is enabled in future versions, the CSP policy will need updates:

### Additional CSP Directives for DocuSign

```
script-src 'self' https://account.docusign.com https://demo.docusign.net;
frame-src 'self' https://account.docusign.com https://demo.docusign.net;
connect-src 'self' https://account.docusign.com https://demo.docusign.net;
```

### Environment-Based CSP Configuration

For DocuSign environments:

**Production:**
```
script-src 'self' https://account.docusign.com;
frame-src 'self' https://account.docusign.com;
connect-src 'self' https://account.docusign.com;
```

**Demo/Sandbox:**
```
script-src 'self' https://demo.docusign.net;
frame-src 'self' https://demo.docusign.net;
connect-src 'self' https://demo.docusign.net;
```

### Implementation Note

To support DocuSign, modify the `SecurityHeadersMiddleware` to use environment-specific CSP policies:

```python
# Check if DocuSign is enabled
docusign_enabled = os.environ.get("DOCUSIGN_ENABLED", "false").lower() == "true"
docusign_env = os.environ.get("DOCUSIGN_ENVIRONMENT", "production")

if docusign_enabled:
    if docusign_env == "demo":
        csp_docusign = "https://demo.docusign.net"
    else:
        csp_docusign = "https://account.docusign.com"
    
    csp_policy = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        f"script-src 'self' {csp_docusign}; "
        f"frame-src 'self' {csp_docusign}; "
        f"connect-src 'self' {csp_docusign}; "
        "style-src 'self' 'unsafe-inline';"
    )
```

## Testing and Validation

### 1. Header Verification

Test security headers are properly applied:

```bash
# Check headers on any endpoint
curl -I https://your-domain.com/health

# Expected headers should include:
# Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
# X-Content-Type-Options: nosniff
# Referrer-Policy: strict-origin-when-cross-origin
# Permissions-Policy: geolocation=(), camera=(), microphone=()
# Content-Security-Policy: default-src 'self'; img-src 'self' data:; ...
```

### 2. CSP Validation

Verify CSP is working by checking browser developer console:

1. Open browser developer tools (F12)
2. Navigate to any ProofKit page
3. Check Console tab for CSP violations
4. Verify no CSP errors are reported for legitimate resources

### 3. HSTS Testing

Test HSTS enforcement:

```bash
# Check HSTS header presence
curl -I https://your-domain.com/

# Verify HSTS preload eligibility
# Visit: https://hstspreload.org/
# Enter your domain to check preload status
```

### 4. Security Scanner Tools

Use online security scanners:

- **Mozilla Observatory**: https://observatory.mozilla.org/
- **Security Headers**: https://securityheaders.com/
- **SSL Labs**: https://www.ssllabs.com/ssltest/

Expected security grades:
- Mozilla Observatory: A+ or A
- Security Headers: A
- SSL Labs: A or A+

### 5. Manual Testing

Test specific security features:

1. **XSS Protection**: Attempt to inject `<script>alert('xss')</script>` in form fields
2. **MIME Sniffing**: Try accessing `.txt` files as scripts
3. **Mixed Content**: Verify HTTP resources are blocked on HTTPS pages
4. **API Access**: Confirm geolocation/camera prompts are blocked

## Security Compliance Benefits

### Industry Standards

- **OWASP Top 10**: Addresses A2 (Broken Authentication), A6 (Security Misconfiguration), A7 (XSS)
- **NIST Cybersecurity Framework**: Implements protective controls (PR.AC, PR.DS)
- **ISO 27001**: Supports access control and cryptography requirements

### Regulatory Compliance

- **FDA 21 CFR Part 11**: Enhances electronic record security
- **EU GDPR**: Provides technical safeguards for personal data
- **HIPAA**: Supports administrative and technical safeguards
- **SOX**: Strengthens internal controls for IT systems

### Audit Trail

Security headers implementation provides:
- Verifiable security controls
- Consistent policy enforcement
- Documented security posture
- Compliance evidence for auditors

## Monitoring and Maintenance

### 1. Regular Security Reviews

- Monthly: Review CSP violation reports
- Quarterly: Update security scanner assessments  
- Annually: Review and update security policies

### 2. Header Updates

Stay current with evolving standards:
- Monitor OWASP security header recommendations
- Review browser support for new security features
- Update CSP policies as application features change

### 3. Performance Impact

Security headers have minimal performance impact:
- Headers add ~1KB to each response
- No client-side processing overhead
- Caching policies remain effective

### 4. Troubleshooting

Common issues and solutions:

**CSP Violations:**
- Check browser console for blocked resources
- Update CSP to allow legitimate third-party resources
- Use CSP reporting for violation monitoring

**HSTS Issues:**
- Clear browser HSTS cache for testing: `chrome://net-internals/#hsts`
- Verify certificate validity for HSTS preload
- Test subdomain coverage

**Mixed Content:**
- Ensure all resources use HTTPS URLs
- Update hardcoded HTTP links in templates
- Configure CDN/proxy to force HTTPS

## Implementation History

- **v0.5**: Initial security headers implementation
- **Security Headers Middleware**: Custom Starlette middleware for consistent application
- **CSP Policy**: Tailored for ProofKit's resource requirements
- **Future**: DocuSign CSP integration planned for digital signatures

---

**Security Contact**: For security-related questions or vulnerability reports, please contact the development team.

**Last Updated**: August 2025 - ProofKit v0.5 Production Launch