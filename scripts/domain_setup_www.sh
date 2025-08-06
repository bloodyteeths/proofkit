#!/bin/bash
set -e

# ProofKit Domain Setup - WWW Certificate and BASE_URL
# This script sets up TLS for www.proofkit.net on Fly.io

echo "======================================"
echo "ProofKit Domain Setup - WWW"
echo "======================================"
echo ""

# Step 1: Create certificate for www.proofkit.net
echo "Step 1: Creating TLS certificate for www.proofkit.net..."
flyctl certs create www.proofkit.net

# Step 2: Wait for certificate to be ready
echo ""
echo "Step 2: Waiting for certificate to be ready..."
echo "This may take 1-5 minutes for DNS validation..."

MAX_ATTEMPTS=30
ATTEMPT=0
CERT_STATUS=""

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    echo -n "Attempt $ATTEMPT/$MAX_ATTEMPTS: "
    
    # Get certificate status
    CERT_OUTPUT=$(flyctl certs show www.proofkit.net 2>/dev/null || echo "")
    
    if echo "$CERT_OUTPUT" | grep -q "Ready"; then
        CERT_STATUS="Ready"
        echo "Certificate is READY!"
        break
    elif echo "$CERT_OUTPUT" | grep -q "Issued"; then
        echo "Certificate issued, waiting for ready state..."
    else
        echo "Certificate pending validation..."
    fi
    
    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        sleep 10
    fi
done

if [ "$CERT_STATUS" != "Ready" ]; then
    echo ""
    echo "WARNING: Certificate not ready after $MAX_ATTEMPTS attempts."
    echo "DNS may still be propagating. Check status with:"
    echo "  flyctl certs show www.proofkit.net"
    echo ""
    echo "Once ready, continue with step 3 manually."
else
    echo ""
    echo "✓ Certificate successfully created and validated!"
fi

# Step 3: Set BASE_URL secret
echo ""
echo "Step 3: Setting BASE_URL secret..."
flyctl secrets set BASE_URL=https://www.proofkit.net --stage

echo ""
echo "✓ BASE_URL set to https://www.proofkit.net"

# Step 4: Show current certificate status
echo ""
echo "Step 4: Current certificate status:"
echo "======================================"
flyctl certs list
echo ""
flyctl certs show www.proofkit.net || true

# Step 5: Provide verification commands
echo ""
echo "======================================"
echo "VERIFICATION COMMANDS"
echo "======================================"
echo ""
echo "Run these commands to verify the setup:"
echo ""
echo "1. Check DNS resolution:"
echo "   dig +short CNAME www.proofkit.net"
echo "   # Expected: proofkit-prod.fly.dev."
echo ""
echo "2. Test HTTPS connection:"
echo "   curl -I https://www.proofkit.net"
echo "   # Expected: HTTP/2 200 or 301"
echo ""
echo "3. Test full page load:"
echo "   curl -s https://www.proofkit.net | head -n 20"
echo "   # Expected: HTML content"
echo ""
echo "4. Check certificate details:"
echo "   echo | openssl s_client -connect www.proofkit.net:443 -servername www.proofkit.net 2>/dev/null | openssl x509 -noout -subject -issuer -dates"
echo "   # Expected: Valid Let's Encrypt certificate"
echo ""
echo "5. Verify BASE_URL is set:"
echo "   flyctl secrets list | grep BASE_URL"
echo "   # Expected: BASE_URL with digest shown"
echo ""
echo "======================================"
echo "Setup complete! Your site should be available at:"
echo "https://www.proofkit.net"
echo "======================================"