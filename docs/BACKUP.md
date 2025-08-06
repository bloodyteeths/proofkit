# ProofKit S3 Backup Documentation

Simple S3 backup system for ProofKit production launch. This backup system creates daily tar.gz archives of the storage directory and uploads them to AWS S3.

## Overview

The backup system consists of:
- Daily automated backups via cron job (2:00 AM UTC)
- Simple tar.gz compression of storage directory
- SHA-256 hash verification
- AWS S3 upload using AWS CLI

## Quick Start with AWS CLI

Create S3 bucket and lifecycle policy in eu-central-1 region:

```bash
# Create bucket
aws s3api create-bucket --bucket proofkit-backups --region eu-central-1 --create-bucket-configuration LocationConstraint=eu-central-1

# Add 14-day lifecycle policy
cat > lifecycle_14d.json <<EOF
{
  "Rules": [
    {
      "ID": "exp",
      "Status": "Enabled", 
      "Expiration": {"Days": 14},
      "Filter": {"Prefix": ""}
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration --bucket proofkit-backups --lifecycle-configuration file://lifecycle_14d.json
```

## Environment Variables

Set these environment variables in your production environment:

```bash
export S3_BUCKET="proofkit-backups"
export AWS_ACCESS_KEY_ID="your_aws_access_key_id"
export AWS_SECRET_ACCESS_KEY="your_aws_secret_access_key"
export S3_REGION="eu-central-1"  # Optional, defaults to us-east-1
# export S3_ENDPOINT="https://alt-provider"  # Optional, for non-AWS S3-compatible services
```

## IAM Policy

Create an IAM user for ProofKit backups with this policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ProofKitBucketManagement",
            "Effect": "Allow",
            "Action": [
                "s3:CreateBucket",
                "s3:ListBucket",
                "s3:PutLifecycleConfiguration",
                "s3:GetBucketLifecycleConfiguration"
            ],
            "Resource": "arn:aws:s3:::proofkit-backups"
        },
        {
            "Sid": "ProofKitObjectOperations", 
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:GetObjectAcl",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::proofkit-backups/*"
        }
    ]
}
```

## S3 Bucket Policy

Configure your S3 bucket with this policy for additional security:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ProofKitBackupBucketAccess",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:user/proofkit-backup"
            },
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::proofkit-backups/*"
        },
        {
            "Sid": "ProofKitBackupBucketList",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:user/proofkit-backup"
            },
            "Action": "s3:ListBucket",
            "Resource": "arn:aws:s3:::proofkit-backups"
        },
        {
            "Sid": "DenyPublicAccess",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": [
                "arn:aws:s3:::proofkit-backups",
                "arn:aws:s3:::proofkit-backups/*"
            ],
            "Condition": {
                "Bool": {
                    "aws:SecureTransport": "false"
                }
            }
        }
    ]
}
```

## S3 Bucket Configuration

1. **Create S3 Bucket**:
```bash
aws s3 mb s3://proofkit-backups --region us-east-1
```

2. **Enable Versioning** (recommended):
```bash
aws s3api put-bucket-versioning \
    --bucket proofkit-backups \
    --versioning-configuration Status=Enabled
```

3. **Enable Server-Side Encryption**:
```bash
aws s3api put-bucket-encryption \
    --bucket proofkit-backups \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            }
        }]
    }'
```

4. **Set Lifecycle Policy** (optional - for automatic cleanup):
```bash
aws s3api put-bucket-lifecycle-configuration \
    --bucket proofkit-backups \
    --lifecycle-configuration '{
        "Rules": [{
            "ID": "DeleteOldBackups",
            "Status": "Enabled",
            "Filter": {"Prefix": "backup-"},
            "Expiration": {"Days": 30}
        }]
    }'
```

## Manual Backup

To run a backup manually:

```bash
cd /app  # or your ProofKit directory

# Test configuration without uploading (dry-run mode)
./scripts/backup_to_s3.sh --dry-run

# Actual backup
./scripts/backup_to_s3.sh
```

The script will:
1. Create a tar.gz file of the storage directory
2. Calculate SHA-256 hash
3. Upload to S3 with hash metadata (or simulate if --dry-run)
4. Log success/failure
5. Emit success metric (`backup_success:1|c`) only on successful completion

**Note**: The success metric is logged in StatsD format for monitoring purposes.

## Manual Restore

To restore from a backup:

1. **List available backups**:
```bash
aws s3 ls s3://proofkit-backups/ | grep backup-
```

2. **Download specific backup**:
```bash
# Replace YYYYMMDD-HHMMSS with actual timestamp
aws s3 cp s3://proofkit-backups/backup-YYYYMMDD-HHMMSS.tar.gz ./
```

3. **Verify backup integrity**:
```bash
# Get stored hash from S3 metadata
aws s3api head-object \
    --bucket proofkit-backups \
    --key backup-YYYYMMDD-HHMMSS.tar.gz \
    --query 'Metadata.sha256' --output text

# Calculate hash of downloaded file
sha256sum backup-YYYYMMDD-HHMMSS.tar.gz

# Compare the two hashes - they should match
```

4. **Extract and restore**:
```bash
# Backup current storage (if exists)
mv storage storage.backup.$(date +%Y%m%d-%H%M%S)

# Extract backup
tar -xzf backup-YYYYMMDD-HHMMSS.tar.gz

# Verify extraction
ls -la storage/
```

## Monitoring

Check backup logs:
```bash
tail -f /app/logs/s3_backup.log
```

Check cron logs:
```bash
tail -f /app/logs/cron.log
```

Verify recent backups:
```bash
aws s3 ls s3://proofkit-backups/ --recursive | tail -10
```

## Troubleshooting

### Common Issues

**AWS CLI not found**:
- Install AWS CLI: `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && unzip awscliv2.zip && ./aws/install`

**Permission denied errors**:
- Check IAM policy and user permissions
- Verify S3_BUCKET environment variable is correct
- Test AWS credentials: `aws sts get-caller-identity`

**Storage directory not found**:
- Verify ProofKit installation path
- Check STORAGE_DIR variable in backup script
- Ensure storage directory exists: `ls -la storage/`

**Upload failures**:
- Check network connectivity
- Verify S3 bucket exists: `aws s3 ls s3://proofkit-backups/`
- Check AWS region settings

### Emergency Recovery

If complete system failure occurs:

1. **Set up new instance**:
```bash
# Install ProofKit
git clone https://github.com/yourorg/proofkit.git
cd proofkit
pip install -r requirements.txt

# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && ./aws/install

# Set environment variables
export S3_BUCKET="proofkit-backups"
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
```

2. **Restore latest backup**:
```bash
# Get latest backup
LATEST_BACKUP=$(aws s3 ls s3://proofkit-backups/ | grep backup- | sort | tail -n1 | awk '{print $4}')

# Download and restore
aws s3 cp "s3://proofkit-backups/$LATEST_BACKUP" ./
tar -xzf "$LATEST_BACKUP"
```

3. **Verify and start**:
```bash
# Check storage contents
ls -la storage/

# Start ProofKit
python app.py
```

## Security Best Practices

1. **Rotate AWS credentials** regularly (quarterly)
2. **Use IAM roles** instead of access keys when possible (for EC2/ECS)
3. **Enable CloudTrail** for S3 API logging
4. **Monitor S3 access** via CloudWatch
5. **Use VPC endpoints** for S3 access when possible
6. **Enable MFA** for S3 bucket deletion
7. **Regularly test restore procedures**

## Cost Optimization

- Use S3 Intelligent Tiering for automatic cost optimization
- Set lifecycle policies to transition old backups to cheaper storage classes
- Monitor storage usage: `aws s3api list-objects --bucket proofkit-backups --query 'sum(Contents[].Size)'`

---

**Version**: 1.0  
**Last Updated**: August 2025  
**Compatible with**: ProofKit v0.5+