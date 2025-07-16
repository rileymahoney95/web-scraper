#!/bin/bash
# test_cron_setup.sh - Validate cron job configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
VENV_DIR="$PROJECT_DIR/venv"
MAIN_SCRIPT="$PROJECT_DIR/src/main.py"
LOG_DIR="$PROJECT_DIR/logs"

# Function to display usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -h, --help       Show this help message"
    echo "  -v, --verbose    Enable verbose output"
    echo "  -q, --quiet      Quiet mode (errors only)"
    echo "  --fix            Attempt to fix issues automatically"
    echo "  --dry-run        Show what would be fixed without making changes"
}

# Function to log messages
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
        "FIX")
            echo -e "${YELLOW}[FIX]${NC} $message"
            ;;
    esac
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check cron service
check_cron_service() {
    log_message "INFO" "Checking cron service..."
    
    local issues=0
    
    # Check if cron is available
    if ! command_exists crontab; then
        log_message "ERROR" "crontab command not found"
        issues=$((issues + 1))
    else
        log_message "SUCCESS" "crontab command available"
    fi
    
    # Try to list cron jobs
    if crontab -l >/dev/null 2>&1; then
        log_message "SUCCESS" "Cron access is working"
    else
        log_message "ERROR" "Cannot access cron jobs (permission denied or no crontab)"
        issues=$((issues + 1))
    fi
    
    # Check if cron daemon is running on macOS
    if launchctl list | grep -q com.vix.cron; then
        log_message "SUCCESS" "Cron daemon is running"
    else
        log_message "WARN" "Cron daemon may not be running"
        if [ "$FIX_ISSUES" -eq 1 ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                log_message "FIX" "Would attempt to start cron daemon"
            else
                log_message "FIX" "Attempting to start cron daemon"
                sudo launchctl load -w /System/Library/LaunchDaemons/com.vix.cron.plist 2>/dev/null || true
            fi
        fi
    fi
    
    return $issues
}

# Function to check project structure
check_project_structure() {
    log_message "INFO" "Checking project structure..."
    
    local issues=0
    local required_files=(
        "$MAIN_SCRIPT"
        "$SCRIPTS_DIR/setup_cron.sh"
        "$SCRIPTS_DIR/cron_wrapper.sh"
        "$SCRIPTS_DIR/setup_macos_permissions.sh"
        "$SCRIPTS_DIR/monitor_scraper.sh"
        "$PROJECT_DIR/requirements.txt"
        "$PROJECT_DIR/src/config.yaml"
    )
    
    for file in "${required_files[@]}"; do
        if [ -f "$file" ]; then
            log_message "SUCCESS" "Found: $(basename "$file")"
            
            # Check if script files are executable
            if [[ "$file" == *.sh ]]; then
                if [ -x "$file" ]; then
                    log_message "SUCCESS" "$(basename "$file") is executable"
                else
                    log_message "ERROR" "$(basename "$file") is not executable"
                    issues=$((issues + 1))
                    if [ "$FIX_ISSUES" -eq 1 ]; then
                        if [ "$DRY_RUN" -eq 1 ]; then
                            log_message "FIX" "Would make $(basename "$file") executable"
                        else
                            log_message "FIX" "Making $(basename "$file") executable"
                            chmod +x "$file"
                        fi
                    fi
                fi
            fi
        else
            log_message "ERROR" "Missing: $(basename "$file")"
            issues=$((issues + 1))
        fi
    done
    
    # Check if log directory exists
    if [ -d "$LOG_DIR" ]; then
        log_message "SUCCESS" "Log directory exists"
        if [ -w "$LOG_DIR" ]; then
            log_message "SUCCESS" "Log directory is writable"
        else
            log_message "ERROR" "Log directory is not writable"
            issues=$((issues + 1))
        fi
    else
        log_message "ERROR" "Log directory does not exist"
        issues=$((issues + 1))
        if [ "$FIX_ISSUES" -eq 1 ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                log_message "FIX" "Would create log directory"
            else
                log_message "FIX" "Creating log directory"
                mkdir -p "$LOG_DIR"
            fi
        fi
    fi
    
    return $issues
}

# Function to check virtual environment
check_virtual_environment() {
    log_message "INFO" "Checking virtual environment..."
    
    local issues=0
    
    if [ -d "$VENV_DIR" ]; then
        log_message "SUCCESS" "Virtual environment directory exists"
        
        # Check if virtual environment is valid
        if [ -f "$VENV_DIR/bin/activate" ]; then
            log_message "SUCCESS" "Virtual environment activation script found"
            
            # Test activation
            if source "$VENV_DIR/bin/activate" 2>/dev/null; then
                log_message "SUCCESS" "Virtual environment can be activated"
                
                # Check if required packages are installed
                local required_packages=("psycopg2-binary" "PyYAML" "requests" "beautifulsoup4")
                for package in "${required_packages[@]}"; do
                    if python -c "import $package" 2>/dev/null; then
                        log_message "SUCCESS" "Package $package is available"
                    else
                        log_message "ERROR" "Package $package is not installed"
                        issues=$((issues + 1))
                    fi
                done
                
                deactivate 2>/dev/null || true
            else
                log_message "ERROR" "Cannot activate virtual environment"
                issues=$((issues + 1))
            fi
        else
            log_message "ERROR" "Virtual environment activation script not found"
            issues=$((issues + 1))
        fi
    else
        log_message "ERROR" "Virtual environment directory does not exist"
        issues=$((issues + 1))
        if [ "$FIX_ISSUES" -eq 1 ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                log_message "FIX" "Would create virtual environment"
            else
                log_message "FIX" "Creating virtual environment"
                python3 -m venv "$VENV_DIR"
                source "$VENV_DIR/bin/activate"
                pip install -r "$PROJECT_DIR/requirements.txt"
                deactivate
            fi
        fi
    fi
    
    return $issues
}

# Function to check environment variables
check_environment_variables() {
    log_message "INFO" "Checking environment variables..."
    
    local issues=0
    
    # Check DB_PASSWORD
    if [ -n "$DB_PASSWORD" ]; then
        log_message "SUCCESS" "DB_PASSWORD is set"
    else
        log_message "ERROR" "DB_PASSWORD environment variable is not set"
        issues=$((issues + 1))
    fi
    
    # Check PATH
    if echo "$PATH" | grep -q "/usr/local/bin"; then
        log_message "SUCCESS" "PATH includes /usr/local/bin"
    else
        log_message "WARN" "PATH may not include /usr/local/bin"
    fi
    
    return $issues
}

# Function to check database connectivity
check_database_connectivity() {
    log_message "INFO" "Checking database connectivity..."
    
    local issues=0
    
    if [ -z "$DB_PASSWORD" ]; then
        log_message "ERROR" "Cannot test database - DB_PASSWORD not set"
        return 1
    fi
    
    cd "$PROJECT_DIR"
    
    if [ -d "$VENV_DIR" ]; then
        source "$VENV_DIR/bin/activate"
        
        # Test database connection
        if timeout 30 python "$MAIN_SCRIPT" --setup-db --dry-run >/dev/null 2>&1; then
            log_message "SUCCESS" "Database connection test passed"
        else
            log_message "ERROR" "Database connection test failed"
            issues=$((issues + 1))
        fi
        
        deactivate 2>/dev/null || true
    else
        log_message "ERROR" "Cannot test database - virtual environment not found"
        issues=$((issues + 1))
    fi
    
    return $issues
}

# Function to check existing cron jobs
check_existing_cron_jobs() {
    log_message "INFO" "Checking existing cron jobs..."
    
    local issues=0
    local wrapper_script="$SCRIPTS_DIR/cron_wrapper.sh"
    
    if crontab -l 2>/dev/null | grep -q "$wrapper_script"; then
        log_message "SUCCESS" "Web scraper cron job found"
        
        # Show the cron job
        local cron_line=$(crontab -l 2>/dev/null | grep "$wrapper_script")
        log_message "INFO" "Cron job: $cron_line"
        
        # Validate cron job syntax
        if echo "$cron_line" | grep -E '^[0-9*,-/]+ [0-9*,-/]+ [0-9*,-/]+ [0-9*,-/]+ [0-9*,-/]+ ' >/dev/null; then
            log_message "SUCCESS" "Cron job syntax appears valid"
        else
            log_message "ERROR" "Cron job syntax may be invalid"
            issues=$((issues + 1))
        fi
    else
        log_message "WARN" "No web scraper cron job found"
        if [ "$FIX_ISSUES" -eq 1 ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                log_message "FIX" "Would suggest running setup_cron.sh"
            else
                log_message "FIX" "Please run: $SCRIPTS_DIR/setup_cron.sh"
            fi
        fi
    fi
    
    return $issues
}

# Function to test cron job execution
test_cron_job_execution() {
    log_message "INFO" "Testing cron job execution..."
    
    local issues=0
    local wrapper_script="$SCRIPTS_DIR/cron_wrapper.sh"
    
    if [ ! -f "$wrapper_script" ]; then
        log_message "ERROR" "Cron wrapper script not found"
        return 1
    fi
    
    # Test wrapper script in test mode
    if "$wrapper_script" --test; then
        log_message "SUCCESS" "Cron wrapper test passed"
    else
        log_message "ERROR" "Cron wrapper test failed"
        issues=$((issues + 1))
    fi
    
    return $issues
}

# Function to check log files
check_log_files() {
    log_message "INFO" "Checking log files..."
    
    local issues=0
    local log_files=("$LOG_DIR/scraper.log" "$LOG_DIR/cron.log")
    
    for log_file in "${log_files[@]}"; do
        local log_name=$(basename "$log_file")
        
        if [ -f "$log_file" ]; then
            log_message "SUCCESS" "Log file $log_name exists"
            
            # Check if log file is writable
            if [ -w "$log_file" ]; then
                log_message "SUCCESS" "Log file $log_name is writable"
            else
                log_message "ERROR" "Log file $log_name is not writable"
                issues=$((issues + 1))
            fi
            
            # Check log file size
            local size_mb=$(stat -f%z "$log_file" 2>/dev/null | awk '{print int($1/1024/1024)}')
            if [ "$size_mb" -gt 100 ]; then
                log_message "WARN" "Log file $log_name is large (${size_mb}MB)"
            fi
        else
            log_message "INFO" "Log file $log_name does not exist yet (will be created on first run)"
        fi
    done
    
    return $issues
}

# Function to run comprehensive test
run_comprehensive_test() {
    echo -e "${GREEN}Comprehensive Cron Setup Test${NC}"
    echo "==============================="
    echo "Project: $PROJECT_DIR"
    echo "Time: $(date)"
    echo
    
    local total_issues=0
    local test_results=()
    
    # Run all checks
    local checks=(
        "check_cron_service:Cron Service"
        "check_project_structure:Project Structure"
        "check_virtual_environment:Virtual Environment"
        "check_environment_variables:Environment Variables"
        "check_database_connectivity:Database Connectivity"
        "check_existing_cron_jobs:Existing Cron Jobs"
        "test_cron_job_execution:Cron Job Execution"
        "check_log_files:Log Files"
    )
    
    for check in "${checks[@]}"; do
        local func_name="${check%%:*}"
        local check_name="${check##*:}"
        
        echo -e "${YELLOW}Testing: $check_name${NC}"
        local issues=0
        
        if $func_name; then
            issues=0
        else
            issues=$?
        fi
        
        total_issues=$((total_issues + issues))
        
        if [ $issues -eq 0 ]; then
            test_results+=("$check_name: ✓ PASS")
        else
            test_results+=("$check_name: ✗ FAIL ($issues issues)")
        fi
        
        echo
    done
    
    # Summary
    echo -e "${YELLOW}Test Summary:${NC}"
    echo "============="
    
    for result in "${test_results[@]}"; do
        if [[ "$result" == *"PASS"* ]]; then
            echo -e "${GREEN}$result${NC}"
        else
            echo -e "${RED}$result${NC}"
        fi
    done
    
    echo
    echo -e "${YELLOW}Total Issues Found: $total_issues${NC}"
    
    if [ $total_issues -eq 0 ]; then
        echo -e "${GREEN}🎉 All tests passed! Your cron setup is ready.${NC}"
        echo
        echo -e "${YELLOW}Next steps:${NC}"
        echo "1. Run: $SCRIPTS_DIR/setup_cron.sh (if not already done)"
        echo "2. Monitor: $SCRIPTS_DIR/monitor_scraper.sh"
        echo "3. Check logs: tail -f $LOG_DIR/scraper.log"
    else
        echo -e "${RED}❌ Issues found that need attention.${NC}"
        echo
        if [ "$FIX_ISSUES" -eq 0 ]; then
            echo -e "${YELLOW}Run with --fix to attempt automatic fixes.${NC}"
        fi
    fi
    
    return $total_issues
}

# Parse command line arguments
VERBOSE=0
QUIET=0
FIX_ISSUES=0
DRY_RUN=0

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
        --fix)
            FIX_ISSUES=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
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
run_comprehensive_test
exit $?