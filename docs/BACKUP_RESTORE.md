# ProofKit Backup & Restore Guide

Complete disaster recovery procedures and operational backup management for ProofKit v0.5.

## Overview

ProofKit uses automated daily backups to Backblaze B2 cloud storage with 14-day retention. All temperature validation data, certificates, and evidence files are automatically preserved with cryptographic integrity verification.

## Backup System Architecture

- **Storage Target**: Backblaze B2 cloud storage
- **Backup Tool**: rclone with versioning support
- **Schedule**: Daily automated backups via cron
- **Retention**: 14 days of versioned backups
- **Security**: TLS encryption in transit, server-side encryption at rest

## Prerequisites

### Required Environment Variables
```bash
export B2_BUCKET="proofkit-backups-prod"
export B2_KEY="your_b2_application_key_id"
export B2_SECRET="your_b2_application_key_secret"
```

### Required Tools
- rclone (v1.60+)
- jq (for JSON processing)
- bash (v4.0+)

## Backup Operations

### Manual Backup
```bash
# Run immediate backup
./scripts/backup.sh

# Test backup without uploading
./scripts/backup.sh --dry-run

# Verify latest backup integrity
./scripts/backup.sh --verify
```

### List Available Backups
```bash
./scripts/backup.sh --list
```

Expected output:
```
Date/Time           | Files | Size  | Age
-------------------|-------|-------|----
2025-08-05 14:30:25 |  1247 | 245MB | 0d
2025-08-04 14:30:18 |  1198 | 238MB | 1d
2025-08-03 14:30:11 |  1156 | 231MB | 2d
```

## Restore Procedures

### Interactive Restore
```bash
./scripts/backup.sh --restore
```

This will:
1. List all available backups
2. Prompt for backup selection
3. Create safety backup of current data
4. Execute restore with progress tracking
5. Verify restore integrity

### Critical Recovery Steps

#### 1. Emergency Restore (Complete Data Loss)
```bash
# If storage directory is completely lost
cd /path/to/proofkit
./scripts/backup.sh --restore

# Select most recent backup
# Follow prompts to confirm restore operation
```

#### 2. Partial Data Recovery
```bash
# For specific file recovery, use rclone directly
export RCLONE_CONFIG="/tmp/b2_config"

# Configure rclone
cat > "$RCLONE_CONFIG" << EOF
[b2_proofkit]
type = b2
account = $B2_KEY
key = $B2_SECRET
hard_delete = false
EOF

# List backup contents
rclone ls b2_proofkit:$B2_BUCKET/proofkit_backups/20250805_143025

# Restore specific files
rclone copy "b2_proofkit:$B2_BUCKET/proofkit_backups/20250805_143025/specific_file.pdf" ./recovery/
```

#### 3. Database Recovery (if applicable)
ProofKit is stateless and file-based, but if database features are added:
```bash
# Restore database from backup
pg_restore -h localhost -U proofkit -d proofkit_prod /path/to/db_backup.sql

# Verify database integrity
psql -U proofkit -d proofkit_prod -c "SELECT COUNT(*) FROM validations;"
```

## Disaster Recovery Scenarios

### Scenario 1: Server Hardware Failure
1. **Immediate Actions** (RTO: 4 hours)
   - Provision new server with identical specifications
   - Install ProofKit dependencies and application
   - Configure environment variables
   - Execute full restore

```bash
# On new server
git clone https://github.com/yourorg/proofkit.git
cd proofkit
pip install -r requirements.txt

# Set environment variables
export B2_BUCKET="proofkit-backups-prod"
export B2_KEY="your_key"
export B2_SECRET="your_secret"

# Restore latest backup
./scripts/backup.sh --restore
```

2. **Verification Steps**
   - Run application health check
   - Verify file counts match backup metadata
   - Test certificate generation with sample data
   - Update DNS if necessary

### Scenario 2: Ransomware/Malware Attack
1. **Immediate Actions** (RTO: 2 hours)
   - Isolate infected systems
   - Assess backup integrity (ransomware shouldn't reach B2)
   - Select clean backup from before infection

```bash
# Check backup dates to find clean restore point
./scripts/backup.sh --list

# Restore from known-good backup
./scripts/backup.sh --restore
# Select backup from before infection date
```

### Scenario 3: Data Corruption
1. **Assessment**
   - Identify scope of corruption
   - Check backup verification logs
   - Determine recovery point objective

```bash
# Verify current backup integrity
./scripts/backup.sh --verify

# Compare file counts
find ./storage -type f | wc -l
```

2. **Selective Recovery**
   - Restore specific affected files
   - Maintain unaffected data
   - Verify certificate integrity

### Scenario 4: Cloud Storage Failure (B2 Outage)
1. **Immediate Actions**
   - Confirm B2 service status
   - Switch to secondary backup location if configured
   - Implement temporary local backup retention

```bash
# Check B2 service status
curl -s https://status.backblaze.com/api/v2/status.json | jq '.status.indicator'

# Create local backup copy
rsync -av ./storage/ ./storage_emergency_backup/
```

## Monitoring & Alerting

### Backup Health Monitoring
```bash
# Check last backup success
tail -n 50 /path/to/proofkit/logs/backup.log | grep -E "(✅|❌)"

# Verify backup age (should be < 25 hours)
find /path/to/proofkit/logs/backup.log -mtime +1 -exec echo "WARNING: Backup older than 24 hours" \;
```

### Automated Monitoring Script
```bash
#!/bin/bash
# /etc/cron.daily/backup_monitor.sh

LOG_FILE="/var/log/proofkit/backup_monitor.log"
BACKUP_LOG="/path/to/proofkit/logs/backup.log"

# Check if backup ran in last 25 hours
if [[ $(find "$BACKUP_LOG" -mtime -1 2>/dev/null) ]]; then
    # Check if backup was successful
    if tail -n 20 "$BACKUP_LOG" | grep -q "✅ Backup completed successfully"; then
        echo "$(date): Backup check PASS" >> "$LOG_FILE"
        exit 0
    else
        echo "$(date): Backup check FAIL - unsuccessful backup" >> "$LOG_FILE"
        # Send alert email
        echo "ProofKit backup failed" | mail -s "ALERT: Backup Failure" admin@yourorg.com
        exit 1
    fi
else
    echo "$(date): Backup check FAIL - no recent backup" >> "$LOG_FILE"
    # Send alert email
    echo "ProofKit backup missing" | mail -s "ALERT: Backup Missing" admin@yourorg.com
    exit 1
fi
```

## Testing & Drill Procedures

### Monthly Restore Drill
Perform complete restore testing monthly to ensure RTO compliance:

```bash
#!/bin/bash
# Monthly drill script

DRILL_DIR="/tmp/proofkit_drill_$(date +%Y%m%d)"
mkdir -p "$DRILL_DIR"
cd "$DRILL_DIR"

echo "=== ProofKit Restore Drill $(date) ===" | tee drill.log

# 1. Clone application
git clone https://github.com/yourorg/proofkit.git >> drill.log 2>&1

# 2. Install dependencies
cd proofkit
pip install -r requirements.txt >> ../drill.log 2>&1

# 3. Restore data
./scripts/backup.sh --restore >> ../drill.log 2>&1

# 4. Verify application starts
timeout 30s python app.py >> ../drill.log 2>&1 &
sleep 10

# 5. Test certificate generation
curl -f "http://localhost:5000/health" >> ../drill.log 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Restore drill PASSED" | tee -a ../drill.log
else
    echo "❌ Restore drill FAILED" | tee -a ../drill.log
fi

# 6. Cleanup
cd /
rm -rf "$DRILL_DIR"
```

### Quarterly Full Recovery Test
Complete disaster recovery simulation:

1. **Preparation** (T-1 week)
   - Schedule maintenance window
   - Notify stakeholders
   - Prepare test environment

2. **Execution** (4-hour window)
   - Simulate complete system failure
   - Execute recovery procedures
   - Measure RTO and RPO metrics
   - Document issues and improvements

3. **Validation**
   - Generate test certificates
   - Verify all functionality
   - Compare against production metrics

### Backup Integrity Verification
```bash
#!/bin/bash
# Weekly backup integrity check

# Get latest backup
LATEST_BACKUP=$(./scripts/backup.sh --list | grep -E '20[0-9]{2}-[0-9]{2}-[0-9]{2}' | head -n1 | awk '{print $1" "$2}')

if [[ -z "$LATEST_BACKUP" ]]; then
    echo "❌ No backups found"
    exit 1
fi

# Convert to backup format
BACKUP_NAME=$(echo "$LATEST_BACKUP" | sed 's/[-: ]//g')

# Verify backup
if ./scripts/backup.sh --verify "$BACKUP_NAME"; then
    echo "✅ Backup integrity verified"
else
    echo "❌ Backup integrity check failed"
    exit 1
fi
```

## Recovery Time & Point Objectives

| Scenario | RTO (Recovery Time) | RPO (Data Loss) | Priority |
|----------|-------------------|-----------------|----------|
| Hardware failure | 4 hours | 24 hours | P1 |
| Ransomware | 2 hours | 24 hours | P0 |
| Data corruption | 1 hour | 24 hours | P1 |
| Cloud outage | 8 hours | 24 hours | P2 |

## Troubleshooting

### Common Issues

#### "Failed to connect to B2 bucket"
```bash
# Check credentials
env | grep B2_

# Test rclone connectivity
rclone lsd "b2_proofkit:$B2_BUCKET"

# Verify B2 service status
curl -s https://status.backblaze.com/api/v2/status.json
```

#### "Backup directory not found"
```bash
# Check storage directory exists
ls -la /path/to/proofkit/storage

# Check backup script configuration
grep STORAGE_DIR scripts/backup.sh
```

#### "Restore failed - insufficient space"
```bash
# Check available disk space
df -h /path/to/proofkit

# Check backup size
rclone size "b2_proofkit:$B2_BUCKET/proofkit_backups/BACKUP_NAME"
```

### Emergency Contacts

- **Primary SysAdmin**: admin@yourorg.com
- **Backup Admin**: backup@yourorg.com  
- **Backblaze Support**: https://help.backblaze.com
- **Emergency Escalation**: +1-555-EMERGENCY

## Best Practices

1. **Test restores regularly** - Monthly drills minimum
2. **Monitor backup logs** - Automated alerting for failures
3. **Verify backup integrity** - Weekly verification checks
4. **Document all procedures** - Keep runbooks updated
5. **Train multiple staff** - Avoid single points of failure
6. **Security first** - Protect backup credentials carefully
7. **Monitor storage costs** - Review retention policies quarterly

## Compliance Notes

- Backups comply with SOC 2 Type II requirements
- 14-day retention meets regulatory minimum for temperature validation data
- All backups encrypted in transit (TLS) and at rest (AES-256)
- Access logs maintained for audit compliance
- Disaster recovery tested and documented quarterly

---

**Last Updated**: August 2025  
**Version**: 1.0  
**Next Review**: November 2025