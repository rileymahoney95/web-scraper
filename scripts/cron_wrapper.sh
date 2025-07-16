#!/bin/bash
# cron_wrapper.sh - Wrapper script for cron execution with environment handling

set -e

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
VENV_DIR="$PROJECT_DIR/venv"
MAIN_SCRIPT="$PROJECT_DIR/src/main.py"
LOG_DIR="$PROJECT_DIR/logs"
CRON_LOG="$LOG_DIR/cron.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Function to log messages with timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$CRON_LOG"
}

# Function to send error notification
send_error_notification() {
    local error_msg="$1"
    local exit_code="$2"
    
    log_message "ERROR: $error_msg (exit code: $exit_code)"
    
    # Try to send notification if notify script exists
    if [ -f "$SCRIPTS_DIR/notify_errors.sh" ]; then
        "$SCRIPTS_DIR/notify_errors.sh" "$error_msg" "$exit_code" || true
    fi
}

# Function to test the setup
test_setup() {
    log_message "Testing scraper setup..."
    
    # Check virtual environment
    if [ ! -d "$VENV_DIR" ]; then
        echo "ERROR: Virtual environment not found at $VENV_DIR"
        return 1
    fi
    
    # Check main script
    if [ ! -f "$MAIN_SCRIPT" ]; then
        echo "ERROR: Main script not found at $MAIN_SCRIPT"
        return 1
    fi
    
    # Check DB_PASSWORD
    if [ -z "$DB_PASSWORD" ]; then
        echo "ERROR: DB_PASSWORD environment variable not set"
        return 1
    fi
    
    # Try to activate virtual environment and run a quick test
    source "$VENV_DIR/bin/activate"
    
    # Test database connection
    if ! python "$MAIN_SCRIPT" --setup-db --dry-run 2>/dev/null; then
        echo "ERROR: Database connection test failed"
        return 1
    fi
    
    echo "Setup test passed!"
    return 0
}

# Handle test mode
if [ "$1" == "--test" ]; then
    test_setup
    exit $?
fi

# Set up environment for cron execution
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Load environment variables from shell profile if available
if [ -f "$HOME/.zshrc" ]; then
    source "$HOME/.zshrc" 2>/dev/null || true
elif [ -f "$HOME/.bash_profile" ]; then
    source "$HOME/.bash_profile" 2>/dev/null || true
elif [ -f "$HOME/.bashrc" ]; then
    source "$HOME/.bashrc" 2>/dev/null || true
fi

# Ensure DB_PASSWORD is set
if [ -z "$DB_PASSWORD" ]; then
    send_error_notification "DB_PASSWORD environment variable not set" 1
    exit 1
fi

# Change to project directory
cd "$PROJECT_DIR"

# Create lock file to prevent concurrent runs
LOCK_FILE="/tmp/webscraper.lock"
if [ -f "$LOCK_FILE" ]; then
    # Check if process is still running
    if kill -0 "$(cat "$LOCK_FILE")" 2>/dev/null; then
        log_message "Another scraper instance is already running (PID: $(cat "$LOCK_FILE"))"
        exit 0
    else
        log_message "Removing stale lock file"
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file with current PID
echo $$ > "$LOCK_FILE"

# Cleanup function
cleanup() {
    rm -f "$LOCK_FILE"
    log_message "Cleanup completed"
}

# Set up trap for cleanup on exit
trap cleanup EXIT INT TERM

log_message "Starting web scraper (PID: $$)"

# Activate virtual environment
if ! source "$VENV_DIR/bin/activate"; then
    send_error_notification "Failed to activate virtual environment" 1
    exit 1
fi

# Run the scraper with timeout to prevent hanging
TIMEOUT_SECONDS=3600  # 1 hour timeout
START_TIME=$(date +%s)

if timeout "$TIMEOUT_SECONDS" python "$MAIN_SCRIPT" "$@"; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log_message "Scraper completed successfully in ${DURATION}s"
    
    # Run cleanup if script exists
    if [ -f "$SCRIPTS_DIR/cleanup_logs.sh" ]; then
        "$SCRIPTS_DIR/cleanup_logs.sh" || true
    fi
    
    exit 0
else
    EXIT_CODE=$?
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    if [ $EXIT_CODE -eq 124 ]; then
        send_error_notification "Scraper timed out after ${TIMEOUT_SECONDS}s" $EXIT_CODE
    else
        send_error_notification "Scraper failed after ${DURATION}s" $EXIT_CODE
    fi
    
    exit $EXIT_CODE
fi