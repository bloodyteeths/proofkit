#!/bin/bash

# ProofKit AWS Infrastructure Setup Script
# Creates free-tier RDS PostgreSQL, DynamoDB table, and S3 bucket
# Generates IAM credentials for application access

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="${AWS_REGION:-eu-central-1}"
S3_BUCKET="${S3_BUCKET:-proofkit-backups-$(openssl rand -hex 4)}"
DDB_TABLE="${DDB_TABLE:-proofkit_cache}"
RDS_DB="${RDS_DB:-proofkitdb}"
RDS_INSTANCE="proofkit-postgres"
RDS_USERNAME="proofkitadmin"
RDS_PASSWORD=$(openssl rand -base64 32 | tr -d "/@\"'+=\n" | cut -c1-25)
IAM_USER="proofkit-app"

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     ProofKit AWS Infrastructure Setup      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}✗ AWS CLI not found. Please install: https://aws.amazon.com/cli/${NC}"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}✗ jq not found. Please install: brew install jq (macOS) or apt-get install jq (Linux)${NC}"
    exit 1
fi

if ! command -v openssl &> /dev/null; then
    echo -e "${RED}✗ openssl not found. Please install openssl${NC}"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}✗ AWS credentials not configured. Run: aws configure${NC}"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✓ Prerequisites met. AWS Account: $ACCOUNT_ID${NC}"
echo ""

# Create S3 bucket
echo -e "${BLUE}[1/5] Creating S3 bucket...${NC}"
if aws s3 ls "s3://$S3_BUCKET" 2>&1 | grep -q 'NoSuchBucket'; then
    aws s3api create-bucket \
        --bucket "$S3_BUCKET" \
        --region "$AWS_REGION" \
        --create-bucket-configuration LocationConstraint="$AWS_REGION" \
        --no-cli-pager 2>/dev/null || true
    
    # Add lifecycle policy (14-day expiration)
    aws s3api put-bucket-lifecycle-configuration \
        --bucket "$S3_BUCKET" \
        --lifecycle-configuration '{
            "Rules": [{
                "Id": "expire-old-backups",
                "Status": "Enabled",
                "Expiration": {"Days": 14},
                "NoncurrentVersionExpiration": {"NoncurrentDays": 1}
            }]
        }' --no-cli-pager
    
    # Enable versioning
    aws s3api put-bucket-versioning \
        --bucket "$S3_BUCKET" \
        --versioning-configuration Status=Enabled \
        --no-cli-pager
    
    echo -e "${GREEN}✓ S3 bucket created: $S3_BUCKET${NC}"
else
    echo -e "${YELLOW}⚠ S3 bucket already exists: $S3_BUCKET${NC}"
fi
echo ""

# Create DynamoDB table
echo -e "${BLUE}[2/5] Creating DynamoDB table...${NC}"
if ! aws dynamodb describe-table --table-name "$DDB_TABLE" --region "$AWS_REGION" &> /dev/null; then
    aws dynamodb create-table \
        --table-name "$DDB_TABLE" \
        --attribute-definitions \
            AttributeName=pk,AttributeType=S \
            AttributeName=sk,AttributeType=S \
        --key-schema \
            AttributeName=pk,KeyType=HASH \
            AttributeName=sk,KeyType=RANGE \
        --billing-mode PAY_PER_REQUEST \
        --region "$AWS_REGION" \
        --no-cli-pager
    
    # Wait for table to be active
    echo -e "${YELLOW}  Waiting for table to be active...${NC}"
    aws dynamodb wait table-exists --table-name "$DDB_TABLE" --region "$AWS_REGION"
    
    # Enable TTL
    aws dynamodb update-time-to-live \
        --table-name "$DDB_TABLE" \
        --time-to-live-specification "Enabled=true,AttributeName=ttl" \
        --region "$AWS_REGION" \
        --no-cli-pager
    
    echo -e "${GREEN}✓ DynamoDB table created: $DDB_TABLE${NC}"
else
    echo -e "${YELLOW}⚠ DynamoDB table already exists: $DDB_TABLE${NC}"
fi
echo ""

# Create RDS PostgreSQL instance
echo -e "${BLUE}[3/5] Creating RDS PostgreSQL instance...${NC}"
if ! aws rds describe-db-instances --db-instance-identifier "$RDS_INSTANCE" --region "$AWS_REGION" &> /dev/null; then
    # Create DB subnet group if needed (uses default VPC)
    aws rds create-db-subnet-group \
        --db-subnet-group-name proofkit-subnet-group \
        --db-subnet-group-description "ProofKit DB subnet group" \
        --subnet-ids $(aws ec2 describe-subnets \
            --filters "Name=default-for-az,Values=true" \
            --query "Subnets[*].SubnetId" \
            --output text) \
        --region "$AWS_REGION" \
        --no-cli-pager 2>/dev/null || true
    
    # Create security group for RDS
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
    SG_ID=$(aws ec2 create-security-group \
        --group-name proofkit-rds-sg \
        --description "ProofKit RDS security group" \
        --vpc-id "$VPC_ID" \
        --region "$AWS_REGION" \
        --output text 2>/dev/null || \
        aws ec2 describe-security-groups \
            --filters "Name=group-name,Values=proofkit-rds-sg" \
            --query "SecurityGroups[0].GroupId" \
            --output text)
    
    # Allow PostgreSQL from anywhere (for Fly.io access)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 5432 \
        --cidr 0.0.0.0/0 \
        --region "$AWS_REGION" \
        --no-cli-pager 2>/dev/null || true
    
    # Create RDS instance
    aws rds create-db-instance \
        --db-instance-identifier "$RDS_INSTANCE" \
        --db-instance-class db.t3.micro \
        --engine postgres \
        --engine-version "15.4" \
        --allocated-storage 20 \
        --storage-type gp2 \
        --db-name "$RDS_DB" \
        --master-username "$RDS_USERNAME" \
        --master-user-password "$RDS_PASSWORD" \
        --vpc-security-group-ids "$SG_ID" \
        --db-subnet-group-name proofkit-subnet-group \
        --backup-retention-period 7 \
        --preferred-backup-window "03:00-04:00" \
        --preferred-maintenance-window "sun:04:00-sun:05:00" \
        --publicly-accessible \
        --no-multi-az \
        --no-auto-minor-version-upgrade \
        --region "$AWS_REGION" \
        --no-cli-pager
    
    echo -e "${YELLOW}  Creating RDS instance (this takes 5-10 minutes)...${NC}"
    aws rds wait db-instance-available \
        --db-instance-identifier "$RDS_INSTANCE" \
        --region "$AWS_REGION"
    
    echo -e "${GREEN}✓ RDS PostgreSQL instance created: $RDS_INSTANCE${NC}"
else
    echo -e "${YELLOW}⚠ RDS instance already exists: $RDS_INSTANCE${NC}"
fi

# Get RDS endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
    --db-instance-identifier "$RDS_INSTANCE" \
    --query "DBInstances[0].Endpoint.Address" \
    --output text \
    --region "$AWS_REGION")

DATABASE_URL="postgresql://$RDS_USERNAME:$RDS_PASSWORD@$RDS_ENDPOINT:5432/$RDS_DB"
echo ""

# Create IAM user and access keys
echo -e "${BLUE}[4/5] Creating IAM user and access keys...${NC}"
if ! aws iam get-user --user-name "$IAM_USER" &> /dev/null; then
    aws iam create-user --user-name "$IAM_USER" --no-cli-pager
    echo -e "${GREEN}✓ IAM user created: $IAM_USER${NC}"
else
    echo -e "${YELLOW}⚠ IAM user already exists: $IAM_USER${NC}"
fi

# Create/update IAM policy
POLICY_JSON=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation"
            ],
            "Resource": "arn:aws:s3:::$S3_BUCKET"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::$S3_BUCKET/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:BatchGetItem",
                "dynamodb:BatchWriteItem",
                "dynamodb:DeleteItem",
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:UpdateItem"
            ],
            "Resource": "arn:aws:dynamodb:$AWS_REGION:$ACCOUNT_ID:table/$DDB_TABLE"
        },
        {
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDBInstances"
            ],
            "Resource": "arn:aws:rds:$AWS_REGION:$ACCOUNT_ID:db:$RDS_INSTANCE"
        }
    ]
}
EOF
)

aws iam put-user-policy \
    --user-name "$IAM_USER" \
    --policy-name ProofKitAppPolicy \
    --policy-document "$POLICY_JSON" \
    --no-cli-pager

# Delete old access keys if any
OLD_KEYS=$(aws iam list-access-keys --user-name "$IAM_USER" --query "AccessKeyMetadata[].AccessKeyId" --output text)
for KEY in $OLD_KEYS; do
    aws iam delete-access-key --user-name "$IAM_USER" --access-key-id "$KEY" --no-cli-pager
done

# Create new access key
KEY_OUTPUT=$(aws iam create-access-key --user-name "$IAM_USER" --output json)
ACCESS_KEY_ID=$(echo "$KEY_OUTPUT" | jq -r '.AccessKey.AccessKeyId')
SECRET_ACCESS_KEY=$(echo "$KEY_OUTPUT" | jq -r '.AccessKey.SecretAccessKey')
echo ""

# Output results
echo -e "${BLUE}[5/5] Setup complete!${NC}"
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           SAVE THESE VALUES                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}DATABASE_URL:${NC}"
echo "$DATABASE_URL"
echo ""
echo -e "${YELLOW}AWS_ACCESS_KEY_ID:${NC}"
echo "$ACCESS_KEY_ID"
echo ""
echo -e "${YELLOW}AWS_SECRET_ACCESS_KEY:${NC}"
echo "$SECRET_ACCESS_KEY"
echo ""
echo -e "${YELLOW}AWS_REGION:${NC}"
echo "$AWS_REGION"
echo ""
echo -e "${YELLOW}DDB_TABLE:${NC}"
echo "$DDB_TABLE"
echo ""
echo -e "${YELLOW}S3_BUCKET:${NC}"
echo "$S3_BUCKET"
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              NEXT STEPS                    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo "1. Save these values to .env or add to Fly.io:"
echo ""
echo "   flyctl secrets set \\"
echo "     DATABASE_URL=\"$DATABASE_URL\" \\"
echo "     AWS_ACCESS_KEY_ID=\"$ACCESS_KEY_ID\" \\"
echo "     AWS_SECRET_ACCESS_KEY=\"$SECRET_ACCESS_KEY\" \\"
echo "     AWS_REGION=\"$AWS_REGION\" \\"
echo "     DDB_TABLE=\"$DDB_TABLE\" \\"
echo "     S3_BUCKET=\"$S3_BUCKET\""
echo ""
echo "2. Deploy your application:"
echo "   fly deploy"
echo ""
echo -e "${BLUE}Monthly costs after 12-month free tier:${NC}"
echo "  • RDS: ~€13/month (db.t3.micro)"
echo "  • DynamoDB: <€1/month (on-demand)"
echo "  • S3: <€1/month (with lifecycle)"
echo ""
echo -e "${GREEN}✓ Infrastructure setup complete!${NC}"