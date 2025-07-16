#!/bin/bash
# setup_macos_permissions.sh - Handle macOS security permissions for the web scraper

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${GREEN}macOS Permissions Setup for Web Scraper${NC}"
echo "==========================================="
echo "Project directory: $PROJECT_DIR"
echo

# Function to check if cron has permission to run
check_cron_permissions() {
    echo -e "${YELLOW}Checking cron permissions...${NC}"
    
    # Try to list cron jobs
    if crontab -l >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Cron access is working${NC}"
        return 0
    else
        echo -e "${RED}✗ Cron access may be restricted${NC}"
        return 1
    fi
}

# Function to check Terminal's Full Disk Access
check_terminal_permissions() {
    echo -e "${YELLOW}Checking Terminal permissions...${NC}"
    
    # Try to access a typically restricted directory
    if [ -r "$HOME/Library/Application Support" ] 2>/dev/null; then
        echo -e "${GREEN}✓ Terminal has sufficient permissions${NC}"
        return 0
    else
        echo -e "${RED}✗ Terminal may need Full Disk Access${NC}"
        return 1
    fi
}

# Function to check database connectivity
check_database_access() {
    echo -e "${YELLOW}Checking database access...${NC}"
    
    if [ -z "$DB_PASSWORD" ]; then
        echo -e "${RED}✗ DB_PASSWORD environment variable not set${NC}"
        return 1
    fi
    
    # Try to connect to database using the scraper
    cd "$PROJECT_DIR"
    if [ -d "venv" ]; then
        source venv/bin/activate
        if python src/main.py --setup-db --dry-run 2>/dev/null; then
            echo -e "${GREEN}✓ Database connection successful${NC}"
            return 0
        else
            echo -e "${RED}✗ Database connection failed${NC}"
            return 1
        fi
    else
        echo -e "${RED}✗ Virtual environment not found${NC}"
        return 1
    fi
}

# Function to check file permissions
check_file_permissions() {
    echo -e "${YELLOW}Checking file permissions...${NC}"
    
    local issues=0
    
    # Check if project directory is writable
    if [ -w "$PROJECT_DIR" ]; then
        echo -e "${GREEN}✓ Project directory is writable${NC}"
    else
        echo -e "${RED}✗ Project directory is not writable${NC}"
        issues=$((issues + 1))
    fi
    
    # Check if logs directory exists and is writable
    if [ -d "$PROJECT_DIR/logs" ] && [ -w "$PROJECT_DIR/logs" ]; then
        echo -e "${GREEN}✓ Logs directory is writable${NC}"
    else
        echo -e "${YELLOW}! Creating logs directory${NC}"
        mkdir -p "$PROJECT_DIR/logs"
        if [ -w "$PROJECT_DIR/logs" ]; then
            echo -e "${GREEN}✓ Logs directory created and writable${NC}"
        else
            echo -e "${RED}✗ Cannot create or write to logs directory${NC}"
            issues=$((issues + 1))
        fi
    fi
    
    # Check if scripts are executable
    for script in setup_cron.sh cron_wrapper.sh; do
        script_path="$PROJECT_DIR/scripts/$script"
        if [ -f "$script_path" ]; then
            if [ -x "$script_path" ]; then
                echo -e "${GREEN}✓ $script is executable${NC}"
            else
                echo -e "${YELLOW}! Making $script executable${NC}"
                chmod +x "$script_path"
                echo -e "${GREEN}✓ $script is now executable${NC}"
            fi
        else
            echo -e "${RED}✗ $script not found${NC}"
            issues=$((issues + 1))
        fi
    done
    
    return $issues
}

# Function to provide instructions for macOS permissions
show_macos_instructions() {
    echo
    echo -e "${BLUE}macOS Permission Instructions:${NC}"
    echo "================================"
    echo
    echo -e "${YELLOW}1. Full Disk Access for Terminal:${NC}"
    echo "   • Open System Preferences > Security & Privacy > Privacy"
    echo "   • Click the lock icon and enter your password"
    echo "   • Select 'Full Disk Access' from the left sidebar"
    echo "   • Click the '+' button and add Terminal.app"
    echo "   • Path: /Applications/Utilities/Terminal.app"
    echo
    echo -e "${YELLOW}2. Cron Access:${NC}"
    echo "   • Open System Preferences > Security & Privacy > Privacy"
    echo "   • Select 'Automation' from the left sidebar"
    echo "   • Allow Terminal to control cron if prompted"
    echo
    echo -e "${YELLOW}3. For iTerm2 users:${NC}"
    echo "   • Also add iTerm.app to Full Disk Access"
    echo "   • Path: /Applications/iTerm.app"
    echo
    echo -e "${YELLOW}4. After granting permissions:${NC}"
    echo "   • Restart Terminal completely"
    echo "   • Run this script again to verify permissions"
    echo
}

# Function to create a simple test cron job
test_cron_job() {
    echo -e "${YELLOW}Testing cron job creation...${NC}"
    
    # Create a simple test entry
    local test_entry="*/5 * * * * echo 'Test cron job' >> /tmp/cron_test.log"
    
    # Add test cron job
    if (crontab -l 2>/dev/null; echo "$test_entry") | crontab -; then
        echo -e "${GREEN}✓ Test cron job created successfully${NC}"
        
        # Wait a moment then remove it
        sleep 1
        crontab -l 2>/dev/null | grep -v "Test cron job" | crontab -
        rm -f /tmp/cron_test.log
        echo -e "${GREEN}✓ Test cron job removed${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to create test cron job${NC}"
        return 1
    fi
}

# Main execution
echo -e "${YELLOW}Running permission checks...${NC}"
echo

# Run all checks
cron_ok=0
terminal_ok=0
database_ok=0
files_ok=0

if check_cron_permissions; then
    cron_ok=1
fi

if check_terminal_permissions; then
    terminal_ok=1
fi

if check_database_access; then
    database_ok=1
fi

if check_file_permissions; then
    files_ok=1
fi

echo
echo -e "${YELLOW}Testing cron functionality...${NC}"
if test_cron_job; then
    cron_test_ok=1
else
    cron_test_ok=0
fi

echo
echo -e "${YELLOW}Permission Summary:${NC}"
echo "==================="
echo -e "Cron permissions:      $([ $cron_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo -e "Terminal permissions:  $([ $terminal_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo -e "Database access:       $([ $database_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo -e "File permissions:      $([ $files_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo -e "Cron test:             $([ $cron_test_ok -eq 1 ] && echo -e "${GREEN}✓ OK${NC}" || echo -e "${RED}✗ FAIL${NC}")"

total_issues=$((5 - cron_ok - terminal_ok - database_ok - files_ok - cron_test_ok))

if [ $total_issues -eq 0 ]; then
    echo
    echo -e "${GREEN}🎉 All permissions are correctly configured!${NC}"
    echo -e "${GREEN}You can now run the cron setup script.${NC}"
    echo
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Run: $PROJECT_DIR/scripts/setup_cron.sh"
    echo "2. Monitor logs: tail -f $PROJECT_DIR/logs/scraper.log"
else
    echo
    echo -e "${RED}❌ $total_issues permission issue(s) found${NC}"
    show_macos_instructions
fi

exit $total_issues