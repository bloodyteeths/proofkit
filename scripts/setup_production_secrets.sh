#!/bin/bash

# ProofKit Production Secrets Setup Script
# Run this script to configure all required environment variables for production

echo "ProofKit Production Secrets Configuration"
echo "========================================="
echo ""
echo "This script will help you set up the required secrets for ProofKit production."
echo "You'll need the following information ready:"
echo "  - Stripe API keys (from https://dashboard.stripe.com/apikeys)"
echo "  - Stripe webhook secret (from https://dashboard.stripe.com/webhooks)"
echo "  - Stripe price IDs (from your Stripe products)"
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read

# JWT Secret (already configured, but verify)
echo "Setting JWT secret..."
JWT_SECRET=$(openssl rand -base64 32)
flyctl secrets set JWT_SECRET="$JWT_SECRET" --app proofkit-prod

# Stripe Configuration
echo ""
echo "STRIPE CONFIGURATION"
echo "===================="
echo "Go to https://dashboard.stripe.com/apikeys"
echo ""
read -p "Enter your Stripe Secret Key (starts with sk_): " STRIPE_SECRET_KEY
read -p "Enter your Stripe Publishable Key (starts with pk_): " STRIPE_PUBLISHABLE_KEY

echo ""
echo "WEBHOOK CONFIGURATION"
echo "===================="
echo "1. Go to https://dashboard.stripe.com/webhooks"
echo "2. Create a new endpoint with URL: https://www.proofkit.net/api/pay/webhook"
echo "3. Select events: checkout.session.completed, invoice.payment_succeeded"
echo ""
read -p "Enter your Stripe Webhook Secret (starts with whsec_): " STRIPE_WEBHOOK_SECRET

echo ""
echo "PRICE IDs CONFIGURATION"
echo "======================="
echo "Create products in Stripe Dashboard if not already done:"
echo "  - Starter Plan: €14/month"
echo "  - Pro Plan: €59/month"
echo "  - Business Plan: €199/month"
echo ""
read -p "Enter Starter Plan Price ID: " STRIPE_PRICE_ID_STARTER
read -p "Enter Pro Plan Price ID: " STRIPE_PRICE_ID_PRO
read -p "Enter Business Plan Price ID: " STRIPE_PRICE_ID_BUSINESS

echo ""
echo "Setting secrets in production..."
flyctl secrets set \
  STRIPE_SECRET_KEY="$STRIPE_SECRET_KEY" \
  STRIPE_PUBLISHABLE_KEY="$STRIPE_PUBLISHABLE_KEY" \
  STRIPE_WEBHOOK_SECRET="$STRIPE_WEBHOOK_SECRET" \
  STRIPE_PRICE_ID_STARTER="$STRIPE_PRICE_ID_STARTER" \
  STRIPE_PRICE_ID_PRO="$STRIPE_PRICE_ID_PRO" \
  STRIPE_PRICE_ID_BUSINESS="$STRIPE_PRICE_ID_BUSINESS" \
  --app proofkit-prod

echo ""
echo "✅ Secrets configured successfully!"
echo ""
echo "Next steps:"
echo "1. The app will automatically restart with the new configuration"
echo "2. Test the payment flow at https://www.proofkit.net/pricing"
echo "3. Monitor webhook events at https://dashboard.stripe.com/webhooks"
echo ""
echo "For testing, use Stripe test cards:"
echo "  - Success: 4242 4242 4242 4242"
echo "  - Decline: 4000 0000 0000 0002"