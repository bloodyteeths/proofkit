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

# Emit success metric (StatsD format)
emit_success_metric() {
    # Send StatsD metric for backup success
    log "Emitting success metric: backup_success:1|c"
    # This would typically go to a metrics endpoint, but for now just log it
    echo "backup_success:1|c" | logger -t proofkit-backup || true
}

# Parse command line arguments (after logging functions are defined)
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    log "Running in DRY-RUN mode - no actual uploads will be performed"
fi

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
    # Don't log inside this function to avoid output contamination
    local temp_dir=$(mktemp -d)
    local archive_path="$temp_dir/$BACKUP_NAME"
    
    # Change to project directory and create tar.gz
    cd "$PROJECT_DIR"
    
    if tar -czf "$archive_path" -C . storage/ 2>/dev/null; then
        # Return only the path, no log messages
        printf "%s" "$archive_path"
    else
        echo "ERROR: Failed to create backup archive" >&2
        rm -rf "$temp_dir"
        return 1
    fi
}

# Calculate SHA-256 hash of the backup file
calculate_hash() {
    local archive_path="$1"
    
    # Don't log inside this function to avoid output contamination
    local hash_result=""
    if command -v sha256sum &> /dev/null; then
        hash_result=$(sha256sum "$archive_path" 2>/dev/null | awk '{print $1}')
    elif command -v shasum &> /dev/null; then
        hash_result=$(shasum -a 256 "$archive_path" 2>/dev/null | awk '{print $1}')
    else
        # Log error to stderr, not stdout
        echo "ERROR: No SHA-256 utility found (sha256sum or shasum)" >&2
        return 1
    fi
    
    # Return only the hash value, no additional output
    printf "%s" "$hash_result"
}

# Upload backup to S3
upload_to_s3() {
    local archive_path="$1"
    local hash_value="$2"
    
    log "Uploading backup to S3 bucket: $S3_BUCKET"
    
    # Set AWS region if not already set
    export AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}"
    
    # Build AWS CLI command with optional endpoint
    local aws_cmd="aws s3 cp \"$archive_path\" \"s3://$S3_BUCKET/$BACKUP_NAME\" --metadata \"sha256=$hash_value\""
    
    # Add S3_ENDPOINT if provided (for non-AWS S3-compatible services)
    if [[ -n "${S3_ENDPOINT:-}" ]]; then
        aws_cmd="$aws_cmd --endpoint-url=\"$S3_ENDPOINT\""
        log "Using custom S3 endpoint: $S3_ENDPOINT"
    fi
    
    # Execute upload command (or simulate in dry-run mode)
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY-RUN: Would execute: $aws_cmd"
        log "DRY-RUN: Upload simulated successfully: s3://$S3_BUCKET/$BACKUP_NAME"
        log "DRY-RUN: SHA-256: $hash_value"
    else
        if eval "$aws_cmd"; then
            log "Upload successful: s3://$S3_BUCKET/$BACKUP_NAME"
            log "SHA-256: $hash_value"
        else
            error "Failed to upload backup to S3"
            exit 1
        fi
    fi
}

# Main backup process
main() {
    log "Starting ProofKit S3 backup process"
    
    # Validate configuration
    validate_config
    
    # Create backup archive
    log "Creating backup archive: $BACKUP_NAME"
    local archive_path=$(create_backup_archive)
    log "Archive created successfully: $archive_path"
    
    # Calculate hash
    log "Calculating SHA-256 hash..."
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
    
    # Emit success metric only on successful completion
    emit_success_metric
    
    return 0
}

# Error handling
trap 'error "Backup script interrupted"; exit 130' INT TERM

# Run main function
main "$@"