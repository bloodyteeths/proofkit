#!/bin/bash
#
# ProofKit S3 Backup Script
# Simple backup script for ProofKit production launch
# 
# Creates tar.gz of ./storage directory and uploads to S3
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STORAGE_DIR="$PROJECT_DIR/storage"
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
BACKUP_NAME="backup-${TIMESTAMP}.tar.gz"
LOG_FILE="$PROJECT_DIR/logs/s3_backup.log"

# Ensure logs directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

# Validate required environment variables
validate_config() {
    log "Validating configuration..."
    
    if [[ -z "${S3_BUCKET:-}" ]]; then
        error "S3_BUCKET environment variable is required"
        exit 1
    fi
    
    if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
        error "AWS_ACCESS_KEY_ID environment variable is required"
        exit 1
    fi
    
    if [[ -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
        error "AWS_SECRET_ACCESS_KEY environment variable is required"
        exit 1
    fi
    
    if [[ ! -d "$STORAGE_DIR" ]]; then
        error "Storage directory not found: $STORAGE_DIR"
        exit 1
    fi
    
    if ! command -v aws &> /dev/null; then
        error "AWS CLI is not installed. Please install aws cli first."
        exit 1
    fi
    
    log "Configuration validation passed"
}

# Create tar.gz backup of storage directory
create_backup_archive() {
    log "Creating backup archive: $BACKUP_NAME"
    
    local temp_dir=$(mktemp -d)
    local archive_path="$temp_dir/$BACKUP_NAME"
    
    # Change to project directory and create tar.gz
    cd "$PROJECT_DIR"
    
    if tar -czf "$archive_path" -C . storage/; then
        log "Archive created successfully: $archive_path"
        echo "$archive_path"
    else
        error "Failed to create backup archive"
        rm -rf "$temp_dir"
        exit 1
    fi
}

# Calculate SHA-256 hash of the backup file
calculate_hash() {
    local archive_path="$1"
    
    log "Calculating SHA-256 hash..."
    
    if command -v sha256sum &> /dev/null; then
        sha256sum "$archive_path" | awk '{print $1}'
    elif command -v shasum &> /dev/null; then
        shasum -a 256 "$archive_path" | awk '{print $1}'
    else
        error "No SHA-256 utility found (sha256sum or shasum)"
        exit 1
    fi
}

# Upload backup to S3
upload_to_s3() {
    local archive_path="$1"
    local hash_value="$2"
    
    log "Uploading backup to S3 bucket: $S3_BUCKET"
    
    # Set AWS region if not already set
    export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
    
    # Upload archive to S3
    if aws s3 cp "$archive_path" "s3://$S3_BUCKET/$BACKUP_NAME" --metadata "sha256=$hash_value"; then
        log "Upload successful: s3://$S3_BUCKET/$BACKUP_NAME"
        log "SHA-256: $hash_value"
    else
        error "Failed to upload backup to S3"
        exit 1
    fi
}

# Main backup process
main() {
    log "Starting ProofKit S3 backup process"
    
    # Validate configuration
    validate_config
    
    # Create backup archive
    local archive_path=$(create_backup_archive)
    
    # Calculate hash
    local hash_value=$(calculate_hash "$archive_path")
    log "Backup SHA-256 hash: $hash_value"
    
    # Upload to S3
    upload_to_s3 "$archive_path" "$hash_value"
    
    # Cleanup temporary files
    rm -rf "$(dirname "$archive_path")"
    
    log "Backup process completed successfully"
    log "Backup file: $BACKUP_NAME"
    log "S3 location: s3://$S3_BUCKET/$BACKUP_NAME"
    log "SHA-256: $hash_value"
    
    return 0
}

# Error handling
trap 'error "Backup script interrupted"; exit 130' INT TERM

# Run main function
main "$@"