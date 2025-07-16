#!/bin/bash
# validate_permissions.sh - Check required permissions for the web scraper

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
SCRIPTS_DIR="$PROJECT_DIR/scripts"

# Function to display usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -h, --help       Show this help message"
    echo "  -v, --verbose    Enable verbose output"
    echo "  -q, --quiet      Quiet mode (errors only)"
    echo "  --fix            Attempt to fix permission issues"
    echo "  --json           Output results in JSON format"
}

# Function to log messages
log_message() {
    local level="$1"
    local message="$2"
    
    if [ "$QUIET" -eq 1 ] && [ "$level" != "ERROR" ]; then
        return
    fi
    
    if [ "$JSON_OUTPUT" -eq 1 ]; then
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

# Function to check file permissions
check_file_permissions() {
    local file="$1"
    local required_perms="$2"
    local file_type="$3"
    
    if [ ! -e "$file" ]; then
        return 1
    fi
    
    case "$required_perms" in
        "read")
            [ -r "$file" ]
            ;;
        "write")
            [ -w "$file" ]
            ;;
        "execute")
            [ -x "$file" ]
            ;;
        "read_write")
            [ -r "$file" ] && [ -w "$file" ]
            ;;
        "all")
            [ -r "$file" ] && [ -w "$file" ] && [ -x "$file" ]
            ;;
        *)
            return 1
            ;;
    esac
}

# Function to check directory permissions
check_directory_permissions() {
    log_message "INFO" "Checking directory permissions..."
    
    local issues=0
    local directories=(
        "$PROJECT_DIR:read_write:Project root"
        "$LOG_DIR:read_write:Logs directory"
        "$SCRIPTS_DIR:read:Scripts directory"
    )
    
    for dir_info in "${directories[@]}"; do
        local dir_path="${dir_info%%:*}"
        local remainder="${dir_info#*:}"
        local required_perms="${remainder%%:*}"
        local description="${remainder#*:}"
        
        if [ -d "$dir_path" ]; then
            if check_file_permissions "$dir_path" "$required_perms" "directory"; then
                log_message "SUCCESS" "$description permissions OK"
            else
                log_message "ERROR" "$description permissions insufficient"
                issues=$((issues + 1))
                
                if [ "$FIX_ISSUES" -eq 1 ]; then
                    log_message "FIX" "Attempting to fix $description permissions"
                    case "$required_perms" in
                        "read_write")
                            chmod u+rw "$dir_path" 2>/dev/null || log_message "ERROR" "Failed to fix $description permissions"
                            ;;
                        "read")
                            chmod u+r "$dir_path" 2>/dev/null || log_message "ERROR" "Failed to fix $description permissions"
                            ;;
                    esac
                fi
            fi
        else
            log_message "ERROR" "$description does not exist"
            issues=$((issues + 1))
            
            if [ "$FIX_ISSUES" -eq 1 ]; then
                log_message "FIX" "Creating $description"
                mkdir -p "$dir_path" 2>/dev/null || log_message "ERROR" "Failed to create $description"
            fi
        fi
    done
    
    return $issues
}

# Function to check script permissions
check_script_permissions() {
    log_message "INFO" "Checking script permissions..."
    
    local issues=0
    local scripts=(
        "$SCRIPTS_DIR/setup_cron.sh:execute:Cron setup script"
        "$SCRIPTS_DIR/cron_wrapper.sh:execute:Cron wrapper script"
        "$SCRIPTS_DIR/setup_macos_permissions.sh:execute:macOS permissions script"
        "$SCRIPTS_DIR/monitor_scraper.sh:execute:Monitor script"
        "$SCRIPTS_DIR/cleanup_logs.sh:execute:Log cleanup script"
        "$SCRIPTS_DIR/notify_errors.sh:execute:Error notification script"
        "$SCRIPTS_DIR/test_cron_setup.sh:execute:Cron test script"
        "$SCRIPTS_DIR/validate_permissions.sh:execute:Permission validation script"
    )
    
    for script_info in "${scripts[@]}"; do
        local script_path="${script_info%%:*}"
        local remainder="${script_info#*:}"
        local required_perms="${remainder%%:*}"
        local description="${remainder#*:}"
        
        if [ -f "$script_path" ]; then
            if check_file_permissions "$script_path" "$required_perms" "file"; then
                log_message "SUCCESS" "$description permissions OK"
            else
                log_message "ERROR" "$description is not executable"
                issues=$((issues + 1))
                
                if [ "$FIX_ISSUES" -eq 1 ]; then
                    log_message "FIX" "Making $description executable"
                    chmod +x "$script_path" 2>/dev/null || log_message "ERROR" "Failed to make $description executable"
                fi
            fi
        else
            log_message "ERROR" "$description does not exist"
            issues=$((issues + 1))
        fi
    done
    
    return $issues
}

# Function to check application file permissions
check_application_permissions() {
    log_message "INFO" "Checking application file permissions..."
    
    local issues=0
    local app_files=(
        "$PROJECT_DIR/src/main.py:read:Main application script"
        "$PROJECT_DIR/src/config.yaml:read_write:Configuration file"
        "$PROJECT_DIR/requirements.txt:read:Requirements file"
    )
    
    for file_info in "${app_files[@]}"; do
        local file_path="${file_info%%:*}"
        local remainder="${file_info#*:}"
        local required_perms="${remainder%%:*}"
        local description="${remainder#*:}"
        
        if [ -f "$file_path" ]; then
            if check_file_permissions "$file_path" "$required_perms" "file"; then
                log_message "SUCCESS" "$description permissions OK"
            else
                log_message "ERROR" "$description permissions insufficient"
                issues=$((issues + 1))
                
                if [ "$FIX_ISSUES" -eq 1 ]; then
                    log_message "FIX" "Fixing $description permissions"
                    case "$required_perms" in
                        "read_write")
                            chmod u+rw "$file_path" 2>/dev/null || log_message "ERROR" "Failed to fix $description permissions"
                            ;;
                        "read")
                            chmod u+r "$file_path" 2>/dev/null || log_message "ERROR" "Failed to fix $description permissions"
                            ;;
                    esac
                fi
            fi
        else
            log_message "ERROR" "$description does not exist"
            issues=$((issues + 1))
        fi
    done
    
    return $issues
}

# Function to check log file permissions
check_log_permissions() {
    log_message "INFO" "Checking log file permissions..."
    
    local issues=0
    local log_files=(
        "$LOG_DIR/scraper.log:read_write:Main scraper log"
        "$LOG_DIR/cron.log:read_write:Cron execution log"
        "$LOG_DIR/notifications.log:read_write:Notifications log"
    )
    
    for log_info in "${log_files[@]}"; do
        local log_path="${log_info%%:*}"
        local remainder="${log_info#*:}"
        local required_perms="${remainder%%:*}"
        local description="${remainder#*:}"
        
        if [ -f "$log_path" ]; then
            if check_file_permissions "$log_path" "$required_perms" "file"; then
                log_message "SUCCESS" "$description permissions OK"
            else
                log_message "ERROR" "$description permissions insufficient"
                issues=$((issues + 1))
                
                if [ "$FIX_ISSUES" -eq 1 ]; then
                    log_message "FIX" "Fixing $description permissions"
                    chmod u+rw "$log_path" 2>/dev/null || log_message "ERROR" "Failed to fix $description permissions"
                fi
            fi
        else
            log_message "INFO" "$description does not exist yet (will be created on first run)"
        fi
    done
    
    return $issues
}

# Function to check cron permissions
check_cron_permissions() {
    log_message "INFO" "Checking cron permissions..."
    
    local issues=0
    
    # Check if we can list cron jobs
    if crontab -l >/dev/null 2>&1; then
        log_message "SUCCESS" "Can access cron jobs"
    else
        log_message "ERROR" "Cannot access cron jobs"
        issues=$((issues + 1))
    fi
    
    # Check if we can edit cron jobs
    if (crontab -l 2>/dev/null; echo "# Test entry") | crontab - 2>/dev/null; then
        log_message "SUCCESS" "Can edit cron jobs"
        # Remove the test entry
        crontab -l 2>/dev/null | grep -v "# Test entry" | crontab - 2>/dev/null
    else
        log_message "ERROR" "Cannot edit cron jobs"
        issues=$((issues + 1))
    fi
    
    return $issues
}

# Function to check system-level permissions
check_system_permissions() {
    log_message "INFO" "Checking system-level permissions..."
    
    local issues=0
    
    # Check if we can write to /tmp (needed for lock files)
    if [ -w "/tmp" ]; then
        log_message "SUCCESS" "Can write to /tmp directory"
    else
        log_message "ERROR" "Cannot write to /tmp directory"
        issues=$((issues + 1))
    fi
    
    # Check if we can create and remove lock files
    local test_lock="/tmp/webscraper_test.lock"
    if echo "$$" > "$test_lock" 2>/dev/null; then
        log_message "SUCCESS" "Can create lock files"
        rm -f "$test_lock"
    else
        log_message "ERROR" "Cannot create lock files"
        issues=$((issues + 1))
    fi
    
    # Check if we can send desktop notifications
    if command -v osascript >/dev/null 2>&1; then
        log_message "SUCCESS" "osascript available for notifications"
    else
        log_message "WARN" "osascript not available (notifications may not work)"
    fi
    
    return $issues
}

# Function to check virtual environment permissions
check_venv_permissions() {
    log_message "INFO" "Checking virtual environment permissions..."
    
    local issues=0
    local venv_dir="$PROJECT_DIR/venv"
    
    if [ -d "$venv_dir" ]; then
        # Check if virtual environment directory is accessible
        if [ -r "$venv_dir" ] && [ -x "$venv_dir" ]; then
            log_message "SUCCESS" "Virtual environment directory accessible"
        else
            log_message "ERROR" "Virtual environment directory not accessible"
            issues=$((issues + 1))
        fi
        
        # Check if activation script is executable
        local activate_script="$venv_dir/bin/activate"
        if [ -f "$activate_script" ] && [ -r "$activate_script" ]; then
            log_message "SUCCESS" "Virtual environment activation script accessible"
        else
            log_message "ERROR" "Virtual environment activation script not accessible"
            issues=$((issues + 1))
        fi
        
        # Check if Python executable is accessible
        local python_exe="$venv_dir/bin/python"
        if [ -f "$python_exe" ] && [ -x "$python_exe" ]; then
            log_message "SUCCESS" "Virtual environment Python executable accessible"
        else
            log_message "ERROR" "Virtual environment Python executable not accessible"
            issues=$((issues + 1))
        fi
    else
        log_message "ERROR" "Virtual environment directory does not exist"
        issues=$((issues + 1))
    fi
    
    return $issues
}

# Function to output JSON results
output_json() {
    local overall_issues="$1"
    local check_results="$2"
    
    cat << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "overall_status": "$([ $overall_issues -eq 0 ] && echo "OK" || echo "ISSUES_FOUND")",
    "total_issues": $overall_issues,
    "project_dir": "$PROJECT_DIR",
    "checks": $check_results
}
EOF
}

# Function to run all permission checks
run_permission_checks() {
    if [ "$JSON_OUTPUT" -eq 0 ]; then
        echo -e "${GREEN}Permission Validation Report${NC}"
        echo "=============================="
        echo "Project: $PROJECT_DIR"
        echo "Time: $(date)"
        echo
    fi
    
    local total_issues=0
    local check_results="{"
    
    # Run all checks
    local checks=(
        "check_directory_permissions:Directory Permissions"
        "check_script_permissions:Script Permissions"
        "check_application_permissions:Application Permissions"
        "check_log_permissions:Log Permissions"
        "check_cron_permissions:Cron Permissions"
        "check_system_permissions:System Permissions"
        "check_venv_permissions:Virtual Environment Permissions"
    )
    
    local first_check=1
    for check in "${checks[@]}"; do
        local func_name="${check%%:*}"
        local check_name="${check##*:}"
        
        if [ "$JSON_OUTPUT" -eq 0 ]; then
            echo -e "${YELLOW}Checking: $check_name${NC}"
        fi
        
        local issues=0
        if $func_name; then
            issues=0
        else
            issues=$?
        fi
        
        total_issues=$((total_issues + issues))
        
        # Build JSON results
        if [ "$first_check" -eq 0 ]; then
            check_results="$check_results,"
        fi
        check_results="$check_results\"$(echo "$check_name" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')\":{\"issues\":$issues,\"status\":\"$([ $issues -eq 0 ] && echo "OK" || echo "ISSUES_FOUND")\"}"
        first_check=0
        
        if [ "$JSON_OUTPUT" -eq 0 ]; then
            echo
        fi
    done
    
    check_results="$check_results}"
    
    if [ "$JSON_OUTPUT" -eq 1 ]; then
        output_json "$total_issues" "$check_results"
    else
        # Summary
        echo -e "${YELLOW}Permission Summary:${NC}"
        echo "==================="
        echo "Total issues found: $total_issues"
        
        if [ $total_issues -eq 0 ]; then
            echo -e "${GREEN}🎉 All permission checks passed!${NC}"
            echo -e "${GREEN}Your web scraper has the necessary permissions to run.${NC}"
        else
            echo -e "${RED}❌ Permission issues found that need attention.${NC}"
            if [ "$FIX_ISSUES" -eq 0 ]; then
                echo -e "${YELLOW}Run with --fix to attempt automatic fixes.${NC}"
            fi
        fi
    fi
    
    return $total_issues
}

# Parse command line arguments
VERBOSE=0
QUIET=0
FIX_ISSUES=0
JSON_OUTPUT=0

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
        --json)
            JSON_OUTPUT=1
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
run_permission_checks
exit $?