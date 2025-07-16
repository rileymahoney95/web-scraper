#!/bin/bash
# monitor_scraper.sh - Health check script for database and recent runs

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
MAIN_SCRIPT="$PROJECT_DIR/src/main.py"
LOG_DIR="$PROJECT_DIR/logs"
SCRAPER_LOG="$LOG_DIR/scraper.log"
CRON_LOG="$LOG_DIR/cron.log"

# Configuration
MAX_LOG_AGE_HOURS=24
MAX_ERROR_COUNT=10
MIN_SUCCESS_RATE=80

# Function to display usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -v, --verbose  Enable verbose output"
    echo "  -q, --quiet    Quiet mode (errors only)"
    echo "  --json         Output results in JSON format"
    echo "  --status       Show brief status only"
    echo "  --last-run     Show last run information"
    echo "  --errors       Show recent errors"
    echo "  --stats        Show statistics"
}

# Parse command line arguments
VERBOSE=0
QUIET=0
JSON_OUTPUT=0
STATUS_ONLY=0
LAST_RUN_ONLY=0
ERRORS_ONLY=0
STATS_ONLY=0

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -q|--quiet)
            QUIET=1
            shift
            ;;
        --json)
            JSON_OUTPUT=1
            shift
            ;;
        --status)
            STATUS_ONLY=1
            shift
            ;;
        --last-run)
            LAST_RUN_ONLY=1
            shift
            ;;
        --errors)
            ERRORS_ONLY=1
            shift
            ;;
        --stats)
            STATS_ONLY=1
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Function to log messages based on verbosity
log_message() {
    local level="$1"
    local message="$2"
    
    if [ "$QUIET" -eq 1 ] && [ "$level" != "ERROR" ]; then
        return
    fi
    
    case "$level" in
        "INFO")
            [ "$VERBOSE" -eq 1 ] && echo -e "${BLUE}[INFO]${NC} $message"
            ;;
        "WARN")
            echo -e "${YELLOW}[WARN]${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        "SUCCESS")
            echo -e "${GREEN}[SUCCESS]${NC} $message"
            ;;
    esac
}

# Function to check if database is accessible
check_database_connection() {
    log_message "INFO" "Checking database connection..."
    
    if [ -z "$DB_PASSWORD" ]; then
        log_message "ERROR" "DB_PASSWORD environment variable not set"
        return 1
    fi
    
    cd "$PROJECT_DIR"
    
    if [ ! -d "$VENV_DIR" ]; then
        log_message "ERROR" "Virtual environment not found at $VENV_DIR"
        return 1
    fi
    
    if ! source "$VENV_DIR/bin/activate"; then
        log_message "ERROR" "Failed to activate virtual environment"
        return 1
    fi
    
    # Use a timeout to prevent hanging
    if timeout 30 python "$MAIN_SCRIPT" --setup-db --dry-run >/dev/null 2>&1; then
        log_message "SUCCESS" "Database connection successful"
        return 0
    else
        log_message "ERROR" "Database connection failed"
        return 1
    fi
}

# Function to check last run information
check_last_run() {
    log_message "INFO" "Checking last run information..."
    
    local last_run_info=""
    local last_run_time=""
    local last_run_status=""
    
    if [ -f "$CRON_LOG" ]; then
        # Get last completed run from cron log
        last_run_info=$(grep -E "(completed successfully|failed|timed out)" "$CRON_LOG" | tail -1)
        if [ -n "$last_run_info" ]; then
            last_run_time=$(echo "$last_run_info" | grep -o '^\[[^]]*\]' | tr -d '[]')
            if echo "$last_run_info" | grep -q "completed successfully"; then
                last_run_status="SUCCESS"
            else
                last_run_status="FAILED"
            fi
        fi
    fi
    
    if [ -z "$last_run_info" ] && [ -f "$SCRAPER_LOG" ]; then
        # Fallback to scraper log
        last_run_info=$(grep -E "(Web Scraper starting|Scraper completed|ERROR|CRITICAL)" "$SCRAPER_LOG" | tail -1)
        if [ -n "$last_run_info" ]; then
            last_run_time=$(echo "$last_run_info" | grep -o '^[^-]*' | tr -d ' ')
            if echo "$last_run_info" | grep -q -E "(completed|success)"; then
                last_run_status="SUCCESS"
            else
                last_run_status="UNKNOWN"
            fi
        fi
    fi
    
    if [ -n "$last_run_info" ]; then
        log_message "INFO" "Last run: $last_run_time ($last_run_status)"
        echo "$last_run_info"
        
        # Check if last run was too long ago
        if [ -n "$last_run_time" ]; then
            local current_time=$(date +%s)
            local last_run_seconds
            
            # Try to parse the timestamp
            if last_run_seconds=$(date -j -f "%Y-%m-%d %H:%M:%S" "$last_run_time" +%s 2>/dev/null); then
                local time_diff=$((current_time - last_run_seconds))
                local hours_since=$((time_diff / 3600))
                
                if [ $hours_since -gt $MAX_LOG_AGE_HOURS ]; then
                    log_message "WARN" "Last run was $hours_since hours ago (threshold: $MAX_LOG_AGE_HOURS hours)"
                    return 1
                else
                    log_message "SUCCESS" "Last run was $hours_since hours ago"
                fi
            fi
        fi
        
        return 0
    else
        log_message "WARN" "No previous run information found"
        return 1
    fi
}

# Function to check for recent errors
check_recent_errors() {
    log_message "INFO" "Checking for recent errors..."
    
    local error_count=0
    local error_files=()
    
    # Check scraper log
    if [ -f "$SCRAPER_LOG" ]; then
        error_count=$(grep -c -E "(ERROR|CRITICAL)" "$SCRAPER_LOG" 2>/dev/null || echo 0)
        if [ $error_count -gt 0 ]; then
            error_files+=("$SCRAPER_LOG")
        fi
    fi
    
    # Check cron log
    if [ -f "$CRON_LOG" ]; then
        local cron_errors=$(grep -c "ERROR:" "$CRON_LOG" 2>/dev/null || echo 0)
        error_count=$((error_count + cron_errors))
        if [ $cron_errors -gt 0 ]; then
            error_files+=("$CRON_LOG")
        fi
    fi
    
    if [ $error_count -gt $MAX_ERROR_COUNT ]; then
        log_message "ERROR" "Found $error_count errors (threshold: $MAX_ERROR_COUNT)"
        
        if [ "$VERBOSE" -eq 1 ]; then
            for file in "${error_files[@]}"; do
                log_message "INFO" "Recent errors from $file:"
                grep -E "(ERROR|CRITICAL)" "$file" | tail -5
            done
        fi
        
        return 1
    elif [ $error_count -gt 0 ]; then
        log_message "WARN" "Found $error_count errors"
        return 0
    else
        log_message "SUCCESS" "No recent errors found"
        return 0
    fi
}

# Function to check running processes
check_running_processes() {
    log_message "INFO" "Checking for running scraper processes..."
    
    local lock_file="/tmp/webscraper.lock"
    local running_processes
    
    # Check lock file
    if [ -f "$lock_file" ]; then
        local pid=$(cat "$lock_file")
        if kill -0 "$pid" 2>/dev/null; then
            log_message "INFO" "Scraper process is running (PID: $pid)"
            return 0
        else
            log_message "WARN" "Stale lock file found, process $pid not running"
            rm -f "$lock_file"
        fi
    fi
    
    # Check for any python processes running the scraper
    running_processes=$(ps aux | grep "[p]ython.*main.py" | grep -v grep | wc -l)
    
    if [ "$running_processes" -gt 0 ]; then
        log_message "INFO" "Found $running_processes running scraper process(es)"
        if [ "$VERBOSE" -eq 1 ]; then
            ps aux | grep "[p]ython.*main.py" | grep -v grep
        fi
        return 0
    else
        log_message "INFO" "No scraper processes currently running"
        return 0
    fi
}

# Function to generate statistics
generate_statistics() {
    log_message "INFO" "Generating statistics..."
    
    local total_runs=0
    local successful_runs=0
    local failed_runs=0
    local avg_runtime=0
    
    if [ -f "$CRON_LOG" ]; then
        total_runs=$(grep -c "Starting web scraper" "$CRON_LOG" 2>/dev/null || echo 0)
        successful_runs=$(grep -c "completed successfully" "$CRON_LOG" 2>/dev/null || echo 0)
        failed_runs=$(grep -c -E "(failed|timed out)" "$CRON_LOG" 2>/dev/null || echo 0)
        
        # Calculate success rate
        if [ $total_runs -gt 0 ]; then
            local success_rate=$((successful_runs * 100 / total_runs))
            log_message "INFO" "Success rate: $success_rate% ($successful_runs/$total_runs)"
            
            if [ $success_rate -lt $MIN_SUCCESS_RATE ]; then
                log_message "WARN" "Success rate below threshold ($MIN_SUCCESS_RATE%)"
            else
                log_message "SUCCESS" "Success rate meets threshold"
            fi
        fi
        
        # Extract runtime information
        if [ "$VERBOSE" -eq 1 ]; then
            local runtime_info=$(grep "completed successfully" "$CRON_LOG" | grep -o '[0-9]\+s' | sed 's/s//' | tail -10)
            if [ -n "$runtime_info" ]; then
                avg_runtime=$(echo "$runtime_info" | awk '{sum+=$1} END {print int(sum/NR)}')
                log_message "INFO" "Average runtime (last 10 runs): ${avg_runtime}s"
            fi
        fi
    fi
    
    echo "Statistics:"
    echo "  Total runs: $total_runs"
    echo "  Successful: $successful_runs"
    echo "  Failed: $failed_runs"
    [ $avg_runtime -gt 0 ] && echo "  Avg runtime: ${avg_runtime}s"
}

# Function to output JSON results
output_json() {
    local db_status="$1"
    local last_run_status="$2"
    local error_status="$3"
    local overall_status="$4"
    
    cat << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "overall_status": "$overall_status",
    "checks": {
        "database_connection": "$db_status",
        "last_run": "$last_run_status",
        "error_check": "$error_status"
    },
    "project_dir": "$PROJECT_DIR",
    "logs": {
        "scraper_log": "$SCRAPER_LOG",
        "cron_log": "$CRON_LOG"
    }
}
EOF
}

# Main execution
main() {
    if [ "$JSON_OUTPUT" -eq 0 ] && [ "$STATUS_ONLY" -eq 0 ]; then
        echo -e "${GREEN}Web Scraper Health Monitor${NC}"
        echo "=============================="
        echo "Project: $PROJECT_DIR"
        echo "Time: $(date)"
        echo
    fi
    
    # Run specific checks based on flags
    if [ "$LAST_RUN_ONLY" -eq 1 ]; then
        check_last_run
        exit $?
    fi
    
    if [ "$ERRORS_ONLY" -eq 1 ]; then
        check_recent_errors
        exit $?
    fi
    
    if [ "$STATS_ONLY" -eq 1 ]; then
        generate_statistics
        exit 0
    fi
    
    # Run all checks
    local db_ok=0
    local last_run_ok=0
    local error_ok=0
    local overall_ok=0
    
    if check_database_connection; then
        db_ok=1
    fi
    
    if check_last_run; then
        last_run_ok=1
    fi
    
    if check_recent_errors; then
        error_ok=1
    fi
    
    check_running_processes
    
    # Determine overall status
    if [ $db_ok -eq 1 ] && [ $last_run_ok -eq 1 ] && [ $error_ok -eq 1 ]; then
        overall_ok=1
    fi
    
    if [ "$JSON_OUTPUT" -eq 1 ]; then
        output_json \
            "$([ $db_ok -eq 1 ] && echo "OK" || echo "FAIL")" \
            "$([ $last_run_ok -eq 1 ] && echo "OK" || echo "FAIL")" \
            "$([ $error_ok -eq 1 ] && echo "OK" || echo "FAIL")" \
            "$([ $overall_ok -eq 1 ] && echo "HEALTHY" || echo "UNHEALTHY")"
    elif [ "$STATUS_ONLY" -eq 1 ]; then
        if [ $overall_ok -eq 1 ]; then
            echo -e "${GREEN}HEALTHY${NC}"
        else
            echo -e "${RED}UNHEALTHY${NC}"
        fi
    else
        echo
        echo -e "${YELLOW}Health Summary:${NC}"
        echo "================"
        echo -e "Database:     $([ $db_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"
        echo -e "Last run:     $([ $last_run_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"
        echo -e "Error check:  $([ $error_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"
        echo -e "Overall:      $([ $overall_ok -eq 1 ] && echo -e "${GREEN}✓ HEALTHY${NC}" || echo -e "${RED}✗ UNHEALTHY${NC}")"
        
        if [ "$VERBOSE" -eq 1 ]; then
            echo
            generate_statistics
        fi
    fi
    
    exit $((1 - overall_ok))
}

# Run main function
main "$@"