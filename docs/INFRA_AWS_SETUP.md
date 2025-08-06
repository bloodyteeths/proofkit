# AWS Infrastructure Setup Guide

This guide walks you through setting up ProofKit's AWS infrastructure using the free tier, including RDS PostgreSQL, DynamoDB, and S3.

## Prerequisites

Before running the setup script, ensure you have:

1. **AWS CLI installed and configured**
   ```bash
   # Install AWS CLI (macOS)
   brew install awscli
   
   # Install AWS CLI (Linux)
   curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
   unzip awscliv2.zip
   sudo ./aws/install
   
   # Configure with your AWS credentials
   aws configure
   ```

2. **Required tools installed**
   ```bash
   # macOS
   brew install jq openssl
   
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install jq openssl postgresql-client
   ```

3. **AWS Account with free tier eligibility**
   - New AWS accounts get 12 months of free tier
   - Includes: t3.micro RDS, DynamoDB, S3 (5GB)

## Running the Setup Script

1. **Make the script executable**
   ```bash
   chmod +x infra/aws/setup.sh
   ```

2. **Run the setup script**
   ```bash
   ./infra/aws/setup.sh
   ```
   
   The script will:
   - Create an S3 bucket with 14-day lifecycle policy
   - Create a DynamoDB table with TTL enabled
   - Create an RDS PostgreSQL instance (db.t3.micro, 20GB)
   - Create an IAM user with necessary permissions
   - Output all credentials and connection strings

3. **Save the output values**
   The script will display:
   - `DATABASE_URL`: PostgreSQL connection string
   - `AWS_ACCESS_KEY_ID`: IAM access key
   - `AWS_SECRET_ACCESS_KEY`: IAM secret key
   - `AWS_REGION`: Region (eu-central-1)
   - `DDB_TABLE`: DynamoDB table name
   - `S3_BUCKET`: S3 bucket name

## Deploying to Fly.io

1. **Set secrets in Fly.io**
   Copy the command from the script output or use:
   ```bash
   flyctl secrets set \
     DATABASE_URL="postgresql://..." \
     AWS_ACCESS_KEY_ID="AKIA..." \
     AWS_SECRET_ACCESS_KEY="..." \
     AWS_REGION="eu-central-1" \
     DDB_TABLE="proofkit_cache" \
     S3_BUCKET="proofkit-backups-..."
   ```

2. **Deploy the application**
   ```bash
   fly deploy
   ```

## Testing the Setup

### Test Database Connection
```bash
# Using psql (replace with your DATABASE_URL)
psql "postgresql://proofkitadmin:password@endpoint.rds.amazonaws.com:5432/proofkitdb"

# Run a test query
\dt  # List tables
\q   # Quit
```

### Test DynamoDB
```bash
# List items (should be empty initially)
aws dynamodb scan --table-name proofkit_cache --region eu-central-1
```

### Test S3 Bucket
```bash
# Upload a test file
echo "test" > test.txt
aws s3 cp test.txt s3://your-bucket-name/test.txt

# List files
aws s3 ls s3://your-bucket-name/

# Clean up
aws s3 rm s3://your-bucket-name/test.txt
rm test.txt
```

## Backup and Restore

### Database Backup
```bash
# Create backup
pg_dump $DATABASE_URL > backup.sql

# Upload to S3
aws s3 cp backup.sql s3://$S3_BUCKET/backups/$(date +%Y%m%d)/backup.sql
```

### Database Restore
```bash
# Download backup
aws s3 cp s3://$S3_BUCKET/backups/20240101/backup.sql ./

# Restore
psql $DATABASE_URL < backup.sql
```

## Cost Breakdown

### During Free Tier (First 12 Months)
- **RDS PostgreSQL**: FREE (750 hours/month of db.t3.micro)
- **DynamoDB**: FREE (25GB storage, 25 read/write units)
- **S3**: FREE (5GB storage, 20k GET, 2k PUT requests)
- **Total**: €0/month

### After Free Tier
- **RDS PostgreSQL**: ~€13/month (db.t3.micro, 20GB)
- **DynamoDB**: <€1/month (pay-per-request mode)
- **S3**: <€1/month (with 14-day lifecycle)
- **Total**: ~€15/month

## Monitoring

### CloudWatch Metrics
```bash
# RDS CPU utilization
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=proofkit-postgres \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average \
  --region eu-central-1
```

### Check RDS Status
```bash
aws rds describe-db-instances \
  --db-instance-identifier proofkit-postgres \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address]' \
  --output table
```

## Troubleshooting

### RDS Connection Issues
1. Check security group allows port 5432 from your IP
2. Ensure RDS is publicly accessible
3. Verify DATABASE_URL format

### DynamoDB Throttling
- Switch to provisioned capacity if consistent high traffic
- Implement exponential backoff in application

### S3 Access Denied
- Verify IAM policy includes bucket and objects
- Check bucket policy and ACLs

## Cleanup (Optional)

To remove all created resources:
```bash
# Delete RDS instance (no final snapshot)
aws rds delete-db-instance \
  --db-instance-identifier proofkit-postgres \
  --skip-final-snapshot \
  --delete-automated-backups

# Delete DynamoDB table
aws dynamodb delete-table --table-name proofkit_cache

# Empty and delete S3 bucket
aws s3 rm s3://your-bucket-name --recursive
aws s3api delete-bucket --bucket your-bucket-name

# Delete IAM user
aws iam delete-user-policy --user-name proofkit-app --policy-name ProofKitAppPolicy
aws iam delete-user --user-name proofkit-app
```

## Security Considerations

1. **RDS Password**: Generated randomly, store securely
2. **IAM Keys**: Rotate regularly, never commit to git
3. **Network Security**: Consider VPC peering with Fly.io for production
4. **Backups**: Enable automated RDS backups (7-day retention configured)
5. **Encryption**: Enable encryption at rest for production use

## Support

For issues or questions:
- Check AWS service health: https://status.aws.amazon.com/
- Review CloudWatch logs in AWS Console
- Contact support@proofkit.net