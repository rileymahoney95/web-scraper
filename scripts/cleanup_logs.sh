#!/bin/bash
# cleanup_logs.sh - Automated log cleanup script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

# Configuration (can be overridden by environment variables)
MAX_LOG_AGE_DAYS=${MAX_LOG_AGE_DAYS:-30}
MAX_LOG_SIZE_MB=${MAX_LOG_SIZE_MB:-100}
KEEP_LOG_COUNT=${KEEP_LOG_COUNT:-10}
DRY_RUN=${DRY_RUN:-0}

# Function to display usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -h, --help                Show this help message"
    echo "  -n, --dry-run             Show what would be done without actually doing it"
    echo "  -d, --days DAYS           Keep logs newer than DAYS (default: $MAX_LOG_AGE_DAYS)"
    echo "  -s, --size SIZE_MB        Clean up if logs exceed SIZE_MB (default: $MAX_LOG_SIZE_MB)"
    echo "  -k, --keep COUNT          Keep at least COUNT recent log files (default: $KEEP_LOG_COUNT)"
    echo "  -v, --verbose             Enable verbose output"
    echo "  -f, --force               Force cleanup even if logs are recent"
}

# Function to log messages
log_message() {
    local level="$1"
    local message="$2"
    
    case "$level" in
        "INFO")
            [ "$VERBOSE" -eq 1 ] && echo -e "${GREEN}[INFO]${NC} $message"
            ;;
        "WARN")
            echo -e "${YELLOW}[WARN]${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        "DRY_RUN")
            echo -e "${YELLOW}[DRY RUN]${NC} $message"
            ;;
    esac
}

# Function to get file size in MB
get_file_size_mb() {
    local file="$1"
    if [ -f "$file" ]; then
        local size_bytes=$(stat -f%z "$file" 2>/dev/null || echo 0)
        echo $((size_bytes / 1024 / 1024))
    else
        echo 0
    fi
}

# Function to get directory size in MB
get_dir_size_mb() {
    local dir="$1"
    if [ -d "$dir" ]; then
        local size_bytes=$(du -sk "$dir" 2>/dev/null | cut -f1)
        echo $((size_bytes / 1024))
    else
        echo 0
    fi
}

# Function to compress old log files
compress_old_logs() {
    local log_file="$1"
    local base_name=$(basename "$log_file" .log)
    local log_dir=$(dirname "$log_file")
    
    log_message "INFO" "Compressing old log files for $base_name"
    
    # Find old log files (rotated logs usually have .1, .2, etc.)
    local old_logs=$(find "$log_dir" -name "${base_name}.log.[0-9]*" -type f ! -name "*.gz" 2>/dev/null || true)
    
    if [ -n "$old_logs" ]; then
        for old_log in $old_logs; do
            if [ -f "$old_log" ]; then
                local size_mb=$(get_file_size_mb "$old_log")
                if [ "$DRY_RUN" -eq 1 ]; then
                    log_message "DRY_RUN" "Would compress $old_log (${size_mb}MB)"
                else
                    log_message "INFO" "Compressing $old_log (${size_mb}MB)"
                    if gzip "$old_log"; then
                        log_message "INFO" "Successfully compressed $old_log"
                    else
                        log_message "ERROR" "Failed to compress $old_log"
                    fi
                fi
            fi
        done
    else
        log_message "INFO" "No old log files found for compression"
    fi
}

# Function to clean up old compressed logs
cleanup_old_compressed_logs() {
    local log_file="$1"
    local base_name=$(basename "$log_file" .log)
    local log_dir=$(dirname "$log_file")
    
    log_message "INFO" "Cleaning up old compressed logs for $base_name"
    
    # Find compressed log files older than specified days
    local old_compressed_logs=$(find "$log_dir" -name "${base_name}.log.[0-9]*.gz" -type f -mtime +$MAX_LOG_AGE_DAYS 2>/dev/null || true)
    
    if [ -n "$old_compressed_logs" ]; then
        for old_log in $old_compressed_logs; do
            if [ -f "$old_log" ]; then
                local size_mb=$(get_file_size_mb "$old_log")
                if [ "$DRY_RUN" -eq 1 ]; then
                    log_message "DRY_RUN" "Would delete $old_log (${size_mb}MB, older than $MAX_LOG_AGE_DAYS days)"
                else
                    log_message "INFO" "Deleting $old_log (${size_mb}MB, older than $MAX_LOG_AGE_DAYS days)"
                    if rm "$old_log"; then
                        log_message "INFO" "Successfully deleted $old_log"
                    else
                        log_message "ERROR" "Failed to delete $old_log"
                    fi
                fi
            fi
        done
    else
        log_message "INFO" "No old compressed logs found for cleanup"
    fi
}

# Function to enforce keep count
enforce_keep_count() {
    local log_file="$1"
    local base_name=$(basename "$log_file" .log)
    local log_dir=$(dirname "$log_file")
    
    log_message "INFO" "Enforcing keep count for $base_name (keeping $KEEP_LOG_COUNT files)"
    
    # Find all log files (including compressed) and sort by modification time
    local all_logs=$(find "$log_dir" -name "${base_name}.log*" -type f | sort -t. -k3 -n -r 2>/dev/null || true)
    
    if [ -n "$all_logs" ]; then
        local count=0
        for log in $all_logs; do
            count=$((count + 1))
            if [ $count -gt $KEEP_LOG_COUNT ]; then
                local size_mb=$(get_file_size_mb "$log")
                if [ "$DRY_RUN" -eq 1 ]; then
                    log_message "DRY_RUN" "Would delete $log (${size_mb}MB, exceeds keep count)"
                else
                    log_message "INFO" "Deleting $log (${size_mb}MB, exceeds keep count)"
                    if rm "$log"; then
                        log_message "INFO" "Successfully deleted $log"
                    else
                        log_message "ERROR" "Failed to delete $log"
                    fi
                fi
            fi
        done
    fi
}

# Function to clean up temporary files
cleanup_temp_files() {
    log_message "INFO" "Cleaning up temporary files"
    
    # Clean up lock files older than 1 day
    local lock_files="/tmp/webscraper.lock"
    if [ -f "$lock_files" ]; then
        local lock_age=$(find "$lock_files" -mtime +1 2>/dev/null || true)
        if [ -n "$lock_age" ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                log_message "DRY_RUN" "Would remove stale lock file $lock_files"
            else
                log_message "INFO" "Removing stale lock file $lock_files"
                rm -f "$lock_files"
            fi
        fi
    fi
    
    # Clean up any core dumps or temp files in project directory
    local temp_files=$(find "$PROJECT_DIR" -name "core.*" -o -name "*.tmp" -o -name "*.temp" -mtime +1 2>/dev/null || true)
    if [ -n "$temp_files" ]; then
        for temp_file in $temp_files; do
            if [ -f "$temp_file" ]; then
                local size_mb=$(get_file_size_mb "$temp_file")
                if [ "$DRY_RUN" -eq 1 ]; then
                    log_message "DRY_RUN" "Would delete temp file $temp_file (${size_mb}MB)"
                else
                    log_message "INFO" "Deleting temp file $temp_file (${size_mb}MB)"
                    rm -f "$temp_file"
                fi
            fi
        done
    fi
}

# Function to process a single log file
process_log_file() {
    local log_file="$1"
    local base_name=$(basename "$log_file")
    
    if [ ! -f "$log_file" ]; then
        log_message "WARN" "Log file $log_file does not exist"
        return 1
    fi
    
    local current_size_mb=$(get_file_size_mb "$log_file")
    log_message "INFO" "Processing $base_name (current size: ${current_size_mb}MB)"
    
    # Check if log file is too large
    if [ "$current_size_mb" -gt "$MAX_LOG_SIZE_MB" ]; then
        log_message "WARN" "$base_name is ${current_size_mb}MB (exceeds ${MAX_LOG_SIZE_MB}MB limit)"
        
        # Force rotation if file is too large
        if [ "$DRY_RUN" -eq 1 ]; then
            log_message "DRY_RUN" "Would force rotate $base_name"
        else
            log_message "INFO" "Force rotating $base_name"
            # Create a backup and truncate
            local backup_file="${log_file}.$(date +%Y%m%d_%H%M%S)"
            if cp "$log_file" "$backup_file"; then
                > "$log_file"  # Truncate the file
                log_message "INFO" "Rotated $base_name to $(basename "$backup_file")"
            else
                log_message "ERROR" "Failed to rotate $base_name"
            fi
        fi
    fi
    
    # Compress old logs
    compress_old_logs "$log_file"
    
    # Clean up old compressed logs
    cleanup_old_compressed_logs "$log_file"
    
    # Enforce keep count
    enforce_keep_count "$log_file"
}

# Parse command line arguments
VERBOSE=0
FORCE=0

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -n|--dry-run)
            DRY_RUN=1
            shift
            ;;
        -d|--days)
            MAX_LOG_AGE_DAYS="$2"
            shift 2
            ;;
        -s|--size)
            MAX_LOG_SIZE_MB="$2"
            shift 2
            ;;
        -k|--keep)
            KEEP_LOG_COUNT="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -f|--force)
            FORCE=1
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    echo -e "${GREEN}Web Scraper Log Cleanup${NC}"
    echo "========================="
    echo "Log directory: $LOG_DIR"
    echo "Max age: $MAX_LOG_AGE_DAYS days"
    echo "Max size: $MAX_LOG_SIZE_MB MB"
    echo "Keep count: $KEEP_LOG_COUNT files"
    if [ "$DRY_RUN" -eq 1 ]; then
        echo -e "${YELLOW}DRY RUN MODE - No changes will be made${NC}"
    fi
    echo
    
    # Check if log directory exists
    if [ ! -d "$LOG_DIR" ]; then
        log_message "ERROR" "Log directory $LOG_DIR does not exist"
        exit 1
    fi
    
    # Get current log directory size
    local initial_size_mb=$(get_dir_size_mb "$LOG_DIR")
    log_message "INFO" "Initial log directory size: ${initial_size_mb}MB"
    
    # Process main log files
    local log_files=("$LOG_DIR/scraper.log" "$LOG_DIR/cron.log")
    
    for log_file in "${log_files[@]}"; do
        if [ -f "$log_file" ]; then
            process_log_file "$log_file"
        else
            log_message "INFO" "Log file $(basename "$log_file") does not exist, skipping"
        fi
    done
    
    # Clean up temporary files
    cleanup_temp_files
    
    # Calculate space saved
    local final_size_mb=$(get_dir_size_mb "$LOG_DIR")
    local space_saved_mb=$((initial_size_mb - final_size_mb))
    
    echo
    log_message "INFO" "Cleanup completed"
    log_message "INFO" "Final log directory size: ${final_size_mb}MB"
    if [ "$space_saved_mb" -gt 0 ]; then
        log_message "INFO" "Space saved: ${space_saved_mb}MB"
    fi
    
    # Show remaining log files
    if [ "$VERBOSE" -eq 1 ]; then
        echo
        log_message "INFO" "Remaining log files:"
        find "$LOG_DIR" -type f -name "*.log*" -exec ls -lh {} \; 2>/dev/null | sort
    fi
}

# Run main function
main "$@"