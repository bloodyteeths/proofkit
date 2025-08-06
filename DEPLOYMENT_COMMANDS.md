# ProofKit Fly.io Deployment Commands

## Account Verification Required
Your Fly.io account needs verification. Please visit: https://fly.io/high-risk-unlock

## After Account Verification, run these commands:

```bash
cd "/Users/tamsar/Downloads/csv SaaS"

# 1. Create the Fly.io app
flyctl apps create proofkit-prod

# 2. Create persistent volume (2GB in Frankfurt region)
flyctl volumes create proofkit_storage --region fra --size 2

# 3. Set environment secrets
flyctl secrets set RETENTION_DAYS=14 MAX_UPLOAD_MB=10 RATE_LIMIT_PER_MIN=30

# 4. Update fly.toml with correct app name
sed -i '' 's/app = "proofkit"/app = "proofkit-prod"/' fly.toml

# 5. Deploy the application
flyctl deploy

# 6. Set the BASE_URL secret after deployment
flyctl secrets set BASE_URL=https://proofkit-prod.fly.dev

# 7. Check deployment status
flyctl status

# 8. View logs
flyctl logs

# 9. Open the application
flyctl open
```

## Alternative: Render Deployment

If Fly.io continues to have issues, you can deploy to Render instead:

1. Go to https://dashboard.render.com
2. Connect your GitHub repository: https://github.com/bloodyteeths/proofkit
3. Render will automatically detect the `render.yaml` configuration
4. Set environment variables in the Render dashboard
5. Deploy will happen automatically

## Verification Commands

After deployment, test the endpoints:

```bash
# Health check
curl https://proofkit-prod.fly.dev/health

# Upload test (replace with your domain)
curl -X POST https://proofkit-prod.fly.dev/api/compile \
  -F "csv=@examples/ok_run.csv" \
  -F "spec=$(cat examples/spec_example.json)"
```

## Environment Variables for Production

The following environment variables will be set:
- `RETENTION_DAYS=14` - Keep artifacts for 14 days
- `MAX_UPLOAD_MB=10` - Maximum 10MB file uploads
- `RATE_LIMIT_PER_MIN=30` - 30 requests per minute per IP
- `BASE_URL=https://proofkit-prod.fly.dev` - Base URL for links

## Storage Volume

A 2GB persistent volume named `proofkit_storage` will be created and mounted to `/app/storage` for evidence bundle storage.