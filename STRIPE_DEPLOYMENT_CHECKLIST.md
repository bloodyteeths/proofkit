# 🚀 STRIPE LIVE DEPLOYMENT CHECKLIST

## ⚠️ IMMEDIATE SECURITY ACTIONS

### 1. **ROLL YOUR SECRET KEY NOW!** 
You exposed your secret key in chat. Go to Stripe Dashboard → API Keys → Roll key immediately!

### 2. **Update .env.live with new secret key**
After rolling, update the `STRIPE_SECRET_KEY` in `.env.live`

---

## 📋 DEPLOYMENT STEPS

### Step 1: Prepare Environment
```bash
# Copy live environment file
cp .env.live .env

# Generate secure random strings
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))"
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(16))"

# Update .env with the generated values
```

### Step 2: Update Critical Values in .env
- [ ] `DATABASE_URL` - Your production PostgreSQL connection
- [ ] `BASE_URL` - Your actual domain (https://yourdomain.com)
- [ ] `JWT_SECRET` - Use generated random string
- [ ] `SECRET_KEY` - Use generated random string
- [ ] `POSTMARK_TOKEN` - Your email service token
- [ ] Email addresses (FROM_EMAIL, REPLY_TO_EMAIL, SUPPORT_INBOX)

### Step 3: Set Up Stripe Webhook
1. Go to Stripe Dashboard → Webhooks
2. Add endpoint: `https://yourdomain.com/api/billing/webhook`
3. Select events:
   - checkout.session.completed
   - customer.subscription.created
   - customer.subscription.updated
   - customer.subscription.deleted
   - invoice.payment_succeeded
   - invoice.payment_failed

### Step 4: Deploy Application
```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
python cli/main.py migrate

# Start application (production)
gunicorn app:app --workers 4 --bind 0.0.0.0:8080
```

### Step 5: Test Payment Flow
1. Make a test purchase with card: `4242 4242 4242 4242`
2. Check webhook receives events
3. Verify user plan updates
4. Test customer portal access

---

## 🔍 VERIFICATION CHECKLIST

### Before Going Live:
- [ ] SSL certificate installed and working
- [ ] All environment variables updated
- [ ] Database migrations completed
- [ ] Webhook endpoint responding (check Stripe Dashboard)
- [ ] Test payment completed successfully
- [ ] Email notifications working
- [ ] Customer portal accessible

### Security:
- [ ] Secret key rolled and updated
- [ ] .env file not in git repository
- [ ] HTTPS enforced on all pages
- [ ] Rate limiting enabled
- [ ] CORS properly configured

### Monitoring:
- [ ] Error logging configured
- [ ] Webhook failures alerting set up
- [ ] Database backups scheduled
- [ ] Uptime monitoring active

---

## 🛠️ QUICK COMMANDS

### Test Webhook Locally:
```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Forward webhooks to local
stripe listen --forward-to localhost:8080/api/billing/webhook

# Trigger test event
stripe trigger checkout.session.completed
```

### Check Integration:
```bash
# Test API endpoint
curl https://yourdomain.com/api/stripe-config

# Should return:
# {"publishableKey":"pk_live_...", "testMode":false}
```

### Monitor Logs:
```bash
# Watch application logs
tail -f logs/app.log

# Check webhook events in Stripe Dashboard
# Go to: Developers → Webhooks → Your endpoint → View events
```

---

## 📞 SUPPORT CONTACTS

- **Stripe Support**: https://support.stripe.com
- **Stripe Status**: https://status.stripe.com
- **Documentation**: https://stripe.com/docs

---

## 🚨 EMERGENCY ROLLBACK

If something goes wrong:
1. Switch to test keys in .env
2. Restart application
3. Debug issue
4. Fix and redeploy with live keys

Keep test mode configuration in `.env.test` as backup!