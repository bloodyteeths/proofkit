#!/bin/bash
"""
ProofKit Backup Script

Automated backup system using rclone to Backblaze B2 cloud storage.
Backs up /storage directory nightly with 14-day version retention.

Usage:
    ./scripts/backup.sh                 # Run full backup
    ./scripts/backup.sh --dry-run       # Test run without uploading
    ./scripts/backup.sh --restore       # Interactive restore mode
    ./scripts/backup.sh --verify        # Verify latest backup

Environment Variables Required:
    B2_BUCKET    - Backblaze B2 bucket name
    B2_KEY       - B2 application key ID  
    B2_SECRET    - B2 application key secret
"""

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STORAGE_DIR="$PROJECT_DIR/storage"
LOG_FILE="$PROJECT_DIR/logs/backup.log"
LOCK_FILE="/tmp/proofkit_backup.lock"
RETENTION_DAYS=14
MAX_RETRIES=3
RETRY_DELAY=30

# Ensure logs directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

# Check dependencies
check_dependencies() {
    log "Checking dependencies..."
    
    if ! command -v rclone &> /dev/null; then
        error "rclone is not installed. Please install rclone first."
        echo "Install instructions: https://rclone.org/install/"
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        error "jq is not installed. Installing via package manager recommended."
        echo "On Ubuntu/Debian: sudo apt-get install jq"
        echo "On macOS: brew install jq"
        exit 1
    fi
    
    log "✅ Dependencies check passed"
}

# Validate configuration
validate_config() {
    log "Validating configuration..."
    
    if [[ -z "${B2_BUCKET:-}" ]]; then
        error "B2_BUCKET environment variable is required"
        exit 1
    fi
    
    if [[ -z "${B2_KEY:-}" ]]; then
        error "B2_KEY environment variable is required"
        exit 1
    fi
    
    if [[ -z "${B2_SECRET:-}" ]]; then
        error "B2_SECRET environment variable is required"
        exit 1
    fi
    
    if [[ ! -d "$STORAGE_DIR" ]]; then
        error "Storage directory not found: $STORAGE_DIR"
        exit 1
    fi
    
    log "✅ Configuration validation passed"
}

# Configure rclone for Backblaze B2
configure_rclone() {
    log "Configuring rclone for Backblaze B2..."
    
    # Create rclone config for B2
    local config_content="[b2_proofkit]
type = b2
account = $B2_KEY
key = $B2_SECRET
hard_delete = false
"
    
    # Write config to temporary file
    local temp_config=$(mktemp)
    echo "$config_content" > "$temp_config"
    
    # Set rclone config file
    export RCLONE_CONFIG="$temp_config"
    
    # Test connection
    if ! rclone lsd "b2_proofkit:$B2_BUCKET" &>/dev/null; then
        error "Failed to connect to B2 bucket: $B2_BUCKET"
        error "Check your B2_BUCKET, B2_KEY, and B2_SECRET environment variables"
        rm -f "$temp_config"
        exit 1
    fi
    
    log "✅ rclone configured successfully"
}

# Calculate storage statistics
calculate_stats() {
    local dir="$1"
    
    if [[ ! -d "$dir" ]]; then
        echo "0 0 0"
        return
    fi
    
    local file_count=$(find "$dir" -type f | wc -l)
    local total_size=$(du -sb "$dir" 2>/dev/null | cut -f1 || echo "0")
    local size_mb=$((total_size / 1024 / 1024))
    
    echo "$file_count $size_mb $total_size"
}

# Create backup with versioning
create_backup() {
    local dry_run="$1"
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_path="proofkit_backups/$timestamp"
    
    log "Starting backup to B2: $B2_BUCKET/$backup_path"
    
    # Calculate pre-backup statistics
    read -r file_count size_mb total_size <<< "$(calculate_stats "$STORAGE_DIR")"
    log "Source statistics: $file_count files, ${size_mb}MB total"
    
    if [[ $file_count -eq 0 ]]; then
        log "⚠️  No files to backup in storage directory"
        return 0
    fi
    
    # Prepare rclone command
    local rclone_cmd=(
        rclone sync
        "$STORAGE_DIR"
        "b2_proofkit:$B2_BUCKET/$backup_path"
        --progress
        --stats=1m
        --log-level=INFO
        --transfers=4
        --checkers=8
        --retries=$MAX_RETRIES
        --retries-sleep="${RETRY_DELAY}s"
        --exclude="*.tmp"
        --exclude="*.lock"
        --exclude=".DS_Store"
    )
    
    if [[ "$dry_run" == "true" ]]; then
        rclone_cmd+=(--dry-run)
        log "🧪 DRY RUN MODE - No files will be uploaded"
    fi
    
    # Execute backup with retry logic
    local attempt=1
    while [[ $attempt -le $MAX_RETRIES ]]; do
        log "Backup attempt $attempt/$MAX_RETRIES"
        
        if "${rclone_cmd[@]}" 2>&1 | tee -a "$LOG_FILE"; then
            if [[ "$dry_run" != "true" ]]; then
                log "✅ Backup completed successfully: $backup_path"
                
                # Create backup metadata
                create_backup_metadata "$backup_path" "$file_count" "$size_mb"
                
                # Clean up old backups
                cleanup_old_backups
            else
                log "✅ Dry run completed successfully"
            fi
            return 0
        else
            log "❌ Backup attempt $attempt failed"
            if [[ $attempt -lt $MAX_RETRIES ]]; then
                log "Retrying in ${RETRY_DELAY} seconds..."
                sleep $RETRY_DELAY
            fi
            ((attempt++))
        fi
    done
    
    error "Backup failed after $MAX_RETRIES attempts"
    return 1
}

# Create backup metadata
create_backup_metadata() {
    local backup_path="$1"
    local file_count="$2"
    local size_mb="$3"
    local metadata_file=$(mktemp)
    
    # Create metadata JSON
    cat > "$metadata_file" << EOF
{
    "backup_date": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
    "backup_path": "$backup_path",
    "source_directory": "$STORAGE_DIR",
    "file_count": $file_count,
    "size_mb": $size_mb,
    "proofkit_version": "0.5",
    "backup_script_version": "1.0",
    "retention_days": $RETENTION_DAYS
}
EOF
    
    # Upload metadata
    if rclone copyto "$metadata_file" "b2_proofkit:$B2_BUCKET/${backup_path}_metadata.json" &>/dev/null; then
        log "📄 Backup metadata created"
    else
        log "⚠️  Failed to create backup metadata"
    fi
    
    rm -f "$metadata_file"
}

# Clean up old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."
    
    local cutoff_date=$(date -d "$RETENTION_DAYS days ago" '+%Y%m%d' 2>/dev/null || date -v-${RETENTION_DAYS}d '+%Y%m%d')
    
    # List all backup directories
    local backup_list=$(rclone lsf "b2_proofkit:$B2_BUCKET/proofkit_backups/" --dirs-only 2>/dev/null || true)
    
    if [[ -z "$backup_list" ]]; then
        log "No existing backups found"
        return 0
    fi
    
    local deleted_count=0
    while IFS= read -r backup_dir; do
        # Extract date from backup directory name (format: YYYYMMDD_HHMMSS/)
        local backup_date=$(echo "$backup_dir" | cut -d'_' -f1)
        
        if [[ ${#backup_date} -eq 8 && "$backup_date" -lt "$cutoff_date" ]]; then
            log "Deleting old backup: $backup_dir"
            
            if rclone purge "b2_proofkit:$B2_BUCKET/proofkit_backups/$backup_dir" &>/dev/null; then
                # Also delete metadata file
                rclone delete "b2_proofkit:$B2_BUCKET/proofkit_backups/${backup_dir%/}_metadata.json" &>/dev/null || true
                ((deleted_count++))
            else
                log "⚠️  Failed to delete backup: $backup_dir"
            fi
        fi
    done <<< "$backup_list"
    
    log "🧹 Deleted $deleted_count old backups"
}

# List available backups
list_backups() {
    log "Listing available backups..."
    
    echo "Available ProofKit backups:"
    echo "=========================="
    
    # Get backup list with metadata
    local backup_list=$(rclone lsf "b2_proofkit:$B2_BUCKET/proofkit_backups/" --dirs-only 2>/dev/null || true)
    
    if [[ -z "$backup_list" ]]; then
        echo "No backups found"
        return 0
    fi
    
    echo "Date/Time           | Files | Size  | Age"
    echo "-------------------|-------|-------|----"
    
    while IFS= read -r backup_dir; do
        local backup_name="${backup_dir%/}"
        local backup_date="${backup_name:0:8}"
        local backup_time="${backup_name:9:6}"
        
        # Format date and time
        local formatted_date="${backup_date:0:4}-${backup_date:4:2}-${backup_date:6:2}"
        local formatted_time="${backup_time:0:2}:${backup_time:2:2}:${backup_time:4:2}"
        
        # Calculate age
        local backup_timestamp=$(date -d "$formatted_date $formatted_time" '+%s' 2>/dev/null || echo "0")
        local current_timestamp=$(date '+%s')
        local age_days=$(( (current_timestamp - backup_timestamp) / 86400 ))
        
        # Try to get metadata
        local file_count="?"
        local size_mb="?"
        
        local metadata_file=$(mktemp)
        if rclone copyto "b2_proofkit:$B2_BUCKET/proofkit_backups/${backup_name}_metadata.json" "$metadata_file" &>/dev/null; then
            file_count=$(jq -r '.file_count // "?"' "$metadata_file" 2>/dev/null || echo "?")
            size_mb=$(jq -r '.size_mb // "?"' "$metadata_file" 2>/dev/null || echo "?")
        fi
        rm -f "$metadata_file"
        
        printf "%-18s | %-5s | %-5s | %dd\n" "$formatted_date $formatted_time" "$file_count" "${size_mb}MB" "$age_days"
        
    done <<< "$backup_list" | sort -r
}

# Verify backup integrity
verify_backup() {
    local backup_name="$1"
    
    if [[ -z "$backup_name" ]]; then
        # Get latest backup
        backup_name=$(rclone lsf "b2_proofkit:$B2_BUCKET/proofkit_backups/" --dirs-only 2>/dev/null | sort -r | head -n1 | tr -d '/')
    fi
    
    if [[ -z "$backup_name" ]]; then
        error "No backups found to verify"
        return 1
    fi
    
    log "Verifying backup: $backup_name"
    
    # Check backup exists and get file count
    local remote_files=$(rclone size "b2_proofkit:$B2_BUCKET/proofkit_backups/$backup_name" --json 2>/dev/null)
    
    if [[ -z "$remote_files" ]]; then
        error "Backup not found or inaccessible: $backup_name"
        return 1
    fi
    
    local remote_count=$(echo "$remote_files" | jq -r '.count // 0')
    local remote_size=$(echo "$remote_files" | jq -r '.bytes // 0')
    local remote_size_mb=$((remote_size / 1024 / 1024))
    
    log "✅ Backup verified: $backup_name"
    log "   Files: $remote_count"
    log "   Size: ${remote_size_mb}MB"
    
    return 0
}

# Interactive restore function
interactive_restore() {
    log "Starting interactive restore process..."
    
    # List available backups
    list_backups
    echo
    
    # Prompt for backup selection
    echo "Enter backup name to restore (YYYYMMDD_HHMMSS format):"
    read -r backup_name
    
    if [[ -z "$backup_name" ]]; then
        error "No backup name provided"
        return 1
    fi
    
    # Verify backup exists
    if ! verify_backup "$backup_name"; then
        error "Selected backup is not valid"
        return 1
    fi
    
    # Confirm restore
    echo
    echo "⚠️  WARNING: This will overwrite the current storage directory!"
    echo "Current storage: $STORAGE_DIR"
    echo "Backup to restore: $backup_name"
    echo
    echo "Continue? (yes/no):"
    read -r confirmation
    
    if [[ "$confirmation" != "yes" ]]; then
        log "Restore cancelled by user"
        return 0
    fi
    
    # Create backup of current storage
    local current_backup="$STORAGE_DIR.backup.$(date '+%Y%m%d_%H%M%S')"
    if [[ -d "$STORAGE_DIR" ]]; then
        log "Creating backup of current storage: $current_backup"
        cp -r "$STORAGE_DIR" "$current_backup"
    fi
    
    # Perform restore
    log "Restoring backup: $backup_name"
    
    # Create storage directory if it doesn't exist
    mkdir -p "$STORAGE_DIR"
    
    if rclone sync "b2_proofkit:$B2_BUCKET/proofkit_backups/$backup_name" "$STORAGE_DIR" --progress; then
        log "✅ Restore completed successfully"
        log "Previous storage backed up to: $current_backup"
        return 0
    else
        error "Restore failed"
        
        # Attempt to restore previous version
        if [[ -d "$current_backup" ]]; then
            log "Attempting to restore previous storage..."
            rm -rf "$STORAGE_DIR"
            mv "$current_backup" "$STORAGE_DIR"
            log "Previous storage restored"
        fi
        
        return 1
    fi
}

# Acquire lock to prevent concurrent backups
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
            error "Another backup process is already running (PID: $lock_pid)"
            exit 1
        else
            log "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi
    
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
}

# Main execution
main() {
    local dry_run=false
    local restore=false
    local verify=false
    local list_only=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                dry_run=true
                shift
                ;;
            --restore)
                restore=true
                shift
                ;;
            --verify)
                verify=true
                shift
                ;;
            --list)
                list_only=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [--dry-run] [--restore] [--verify] [--list]"
                echo "  --dry-run   Test backup without uploading"
                echo "  --restore   Interactive restore mode"
                echo "  --verify    Verify latest backup"
                echo "  --list      List available backups"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Always check dependencies and configuration
    check_dependencies
    validate_config
    configure_rclone
    
    if [[ "$list_only" == "true" ]]; then
        list_backups
        exit 0
    fi
    
    if [[ "$verify" == "true" ]]; then
        verify_backup ""
        exit $?
    fi
    
    if [[ "$restore" == "true" ]]; then
        interactive_restore
        exit $?
    fi
    
    # Regular backup flow
    acquire_lock
    
    log "ProofKit backup started (dry_run: $dry_run)"
    
    if create_backup "$dry_run"; then
        log "🎉 Backup process completed successfully"
        exit 0
    else
        error "Backup process failed"
        exit 1
    fi
}

# Handle script termination
cleanup() {
    log "Backup script interrupted or terminated"
    rm -f "$LOCK_FILE"
    exit 130
}

trap cleanup INT TERM

# Run main function
main "$@"