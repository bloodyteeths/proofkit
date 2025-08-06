# DNS Setup for ProofKit Production Domain

## Overview
This guide covers DNS configuration for ProofKit's custom domain on Fly.io, including domain verification, SSL certificates, and proper DNS records.

## Prerequisites
- Custom domain registered (e.g., `proofkit.com`)
- Access to domain registrar's DNS management
- Fly.io CLI installed and authenticated

## 1. Add Domain to Fly.io

```bash
# Add your custom domain
fly certs create proofkit.com

# Add www subdomain (optional)
fly certs create www.proofkit.com

# Check certificate status
fly certs show proofkit.com
```

## 2. DNS Records Configuration

### Required DNS Records at Your Registrar

#### For Root Domain (proofkit.com)
```
Type: A
Name: @
Value: [Fly.io IPv4 - check fly certs show output]
TTL: 300

Type: AAAA  
Name: @
Value: [Fly.io IPv6 - check fly certs show output]
TTL: 300
```

#### For WWW Subdomain (www.proofkit.com)
```
Type: CNAME
Name: www
Value: proofkit.com
TTL: 300
```

#### Alternative: CNAME for Root (if registrar supports)
```
Type: CNAME
Name: @
Value: proofkit-prod.fly.dev
TTL: 300
```

## 3. SSL Certificate Verification

After adding DNS records, Fly.io will automatically provision Let's Encrypt certificates:

```bash
# Monitor certificate status
fly certs show proofkit.com

# Expected output when ready:
# Certificate Status: Ready
# DNS Provider: lets-encrypt
# Certificate Authority: Let's Encrypt
```

## 4. Fly.io Configuration

Update `fly.toml` to handle custom domain:

```toml
[[services.http_checks]]
  interval = "10s"
  method = "GET"
  path = "/health"
  protocol = "http"
  restart_limit = 0
  timeout = "2s"

[[services]]
  protocol = "tcp"
  internal_port = 8000

  [[services.ports]]
    port = 80
    handlers = ["http"]
    force_https = true

  [[services.ports]]
    port = 443
    handlers = ["http", "tls"]

  [services.concurrency]
    type = "connections"
    hard_limit = 25
    soft_limit = 20
```

## 5. Domain Verification Steps

1. **Add DNS Records**: Configure A/AAAA or CNAME records as shown above
2. **Wait for Propagation**: DNS changes can take up to 48 hours (usually 5-30 minutes)
3. **Verify SSL**: Check certificate status with `fly certs show`
4. **Test HTTPS**: Visit https://proofkit.com and verify secure connection

## 6. Troubleshooting

### Certificate Pending
```bash
# Check DNS propagation
nslookup proofkit.com
dig proofkit.com

# Force certificate refresh
fly certs create proofkit.com --force
```

### DNS Propagation Check
```bash
# Check from multiple locations
dig @8.8.8.8 proofkit.com
dig @1.1.1.1 proofkit.com
```

### Common Issues
- **DNS TTL too high**: Reduce TTL to 300 seconds during setup
- **CAA records**: Ensure no CAA records block Let's Encrypt
- **Proxy services**: Disable Cloudflare proxy during initial setup

## 7. Production Checklist

- [ ] Domain added to Fly.io: `fly certs create proofkit.com`
- [ ] DNS A/AAAA records configured
- [ ] DNS propagation verified: `nslookup proofkit.com`
- [ ] SSL certificate issued: `fly certs show proofkit.com`
- [ ] HTTPS redirect working: `curl -I http://proofkit.com`
- [ ] Custom domain accessible: `curl -I https://proofkit.com`
- [ ] Health check passing: `curl https://proofkit.com/health`

## 8. Monitoring

Set up monitoring for:
- Certificate expiration (auto-renewed by Fly.io)
- DNS resolution health
- HTTPS accessibility

```bash
# Add to monitoring script
curl -f -s https://proofkit.com/health > /dev/null || echo "Health check failed"
```

## Security Notes

- Fly.io automatically handles HTTPS redirect
- Let's Encrypt certificates auto-renew
- HSTS headers should be configured in application (see BATCH L2)
- Consider adding domain to HSTS preload list after stable operation

## Support

- Fly.io Documentation: https://fly.io/docs/app-guides/custom-domains-with-fly/
- Let's Encrypt Status: https://letsencrypt.status.io/
- DNS Propagation Checker: https://dnschecker.org/