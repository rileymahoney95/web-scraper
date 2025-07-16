#!/bin/bash
# notify_errors.sh - Error notification script for macOS

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
NOTIFICATION_ENABLED=${NOTIFICATION_ENABLED:-1}
EMAIL_ENABLED=${EMAIL_ENABLED:-0}
SLACK_ENABLED=${SLACK_ENABLED:-0}
DESKTOP_NOTIFICATIONS=${DESKTOP_NOTIFICATIONS:-1}

# Email configuration (set these as environment variables if using email)
EMAIL_TO=${EMAIL_TO:-""}
EMAIL_FROM=${EMAIL_FROM:-"webscraper@localhost"}
EMAIL_SUBJECT_PREFIX=${EMAIL_SUBJECT_PREFIX:-"[Web Scraper]"}

# Slack configuration (set these as environment variables if using Slack)
SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL:-""}
SLACK_CHANNEL=${SLACK_CHANNEL:-"#alerts"}

# Function to display usage
show_usage() {
    echo "Usage: $0 ERROR_MESSAGE [EXIT_CODE]"
    echo ""
    echo "Send error notifications via various channels (desktop, email, Slack)"
    echo ""
    echo "Arguments:"
    echo "  ERROR_MESSAGE    The error message to send"
    echo "  EXIT_CODE        Optional exit code (default: 1)"
    echo ""
    echo "Options:"
    echo "  -h, --help       Show this help message"
    echo "  -t, --test       Send test notifications"
    echo "  -c, --config     Show current configuration"
    echo ""
    echo "Environment variables:"
    echo "  NOTIFICATION_ENABLED     Enable/disable all notifications (default: 1)"
    echo "  EMAIL_ENABLED           Enable email notifications (default: 0)"
    echo "  EMAIL_TO                Email recipient address"
    echo "  EMAIL_FROM              Email sender address"
    echo "  SLACK_ENABLED           Enable Slack notifications (default: 0)"
    echo "  SLACK_WEBHOOK_URL       Slack webhook URL"
    echo "  SLACK_CHANNEL           Slack channel (default: #alerts)"
    echo "  DESKTOP_NOTIFICATIONS   Enable macOS desktop notifications (default: 1)"
}

# Function to show current configuration
show_config() {
    echo -e "${GREEN}Notification Configuration${NC}"
    echo "==========================="
    echo "Notifications enabled: $NOTIFICATION_ENABLED"
    echo "Desktop notifications: $DESKTOP_NOTIFICATIONS"
    echo "Email notifications: $EMAIL_ENABLED"
    echo "Email to: ${EMAIL_TO:-<not set>}"
    echo "Email from: $EMAIL_FROM"
    echo "Slack notifications: $SLACK_ENABLED"
    echo "Slack webhook: ${SLACK_WEBHOOK_URL:+<set>}${SLACK_WEBHOOK_URL:-<not set>}"
    echo "Slack channel: $SLACK_CHANNEL"
}

# Function to send macOS desktop notification
send_desktop_notification() {
    local title="$1"
    local message="$2"
    local urgency="$3"
    
    if [ "$DESKTOP_NOTIFICATIONS" -eq 0 ]; then
        return 0
    fi
    
    # Use osascript to send notification
    local sound=""
    case "$urgency" in
        "critical")
            sound="sound name \"Basso\""
            ;;
        "error")
            sound="sound name \"Sosumi\""
            ;;
        *)
            sound=""
            ;;
    esac
    
    osascript -e "display notification \"$message\" with title \"$title\" $sound" 2>/dev/null || {
        echo -e "${YELLOW}[WARN]${NC} Failed to send desktop notification"
        return 1
    }
    
    echo -e "${GREEN}[INFO]${NC} Desktop notification sent"
    return 0
}

# Function to send email notification
send_email_notification() {
    local subject="$1"
    local body="$2"
    
    if [ "$EMAIL_ENABLED" -eq 0 ]; then
        return 0
    fi
    
    if [ -z "$EMAIL_TO" ]; then
        echo -e "${YELLOW}[WARN]${NC} EMAIL_TO not set, skipping email notification"
        return 1
    fi
    
    # Create email body with additional context
    local full_body="$body

Project: $PROJECT_DIR
Time: $(date)
Host: $(hostname)

Recent log entries:
$(tail -n 10 "$LOG_DIR/scraper.log" 2>/dev/null || echo "No recent log entries available")
"
    
    # Try to send email using mail command
    if command -v mail >/dev/null 2>&1; then
        echo "$full_body" | mail -s "$subject" "$EMAIL_TO" 2>/dev/null || {
            echo -e "${YELLOW}[WARN]${NC} Failed to send email notification"
            return 1
        }
        echo -e "${GREEN}[INFO]${NC} Email notification sent to $EMAIL_TO"
        return 0
    else
        echo -e "${YELLOW}[WARN]${NC} mail command not available, skipping email notification"
        return 1
    fi
}

# Function to send Slack notification
send_slack_notification() {
    local message="$1"
    local urgency="$2"
    
    if [ "$SLACK_ENABLED" -eq 0 ]; then
        return 0
    fi
    
    if [ -z "$SLACK_WEBHOOK_URL" ]; then
        echo -e "${YELLOW}[WARN]${NC} SLACK_WEBHOOK_URL not set, skipping Slack notification"
        return 1
    fi
    
    # Set color based on urgency
    local color=""
    case "$urgency" in
        "critical")
            color="#FF0000"  # Red
            ;;
        "error")
            color="#FF6600"  # Orange
            ;;
        "warning")
            color="#FFFF00"  # Yellow
            ;;
        *)
            color="#36A64F"  # Green
            ;;
    esac
    
    # Create Slack payload
    local payload=$(cat <<EOF
{
    "channel": "$SLACK_CHANNEL",
    "attachments": [
        {
            "color": "$color",
            "title": "Web Scraper Alert",
            "text": "$message",
            "fields": [
                {
                    "title": "Project",
                    "value": "$PROJECT_DIR",
                    "short": true
                },
                {
                    "title": "Host",
                    "value": "$(hostname)",
                    "short": true
                },
                {
                    "title": "Time",
                    "value": "$(date)",
                    "short": false
                }
            ],
            "footer": "Web Scraper Monitor",
            "ts": $(date +%s)
        }
    ]
}
EOF
)
    
    # Send to Slack
    if command -v curl >/dev/null 2>&1; then
        local response=$(curl -s -X POST \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "$SLACK_WEBHOOK_URL")
        
        if [ "$response" = "ok" ]; then
            echo -e "${GREEN}[INFO]${NC} Slack notification sent"
            return 0
        else
            echo -e "${YELLOW}[WARN]${NC} Failed to send Slack notification: $response"
            return 1
        fi
    else
        echo -e "${YELLOW}[WARN]${NC} curl command not available, skipping Slack notification"
        return 1
    fi
}

# Function to determine urgency level
determine_urgency() {
    local error_message="$1"
    local exit_code="$2"
    
    # Check for critical errors
    if echo "$error_message" | grep -qi -E "(critical|fatal|database.*connection|permission.*denied)"; then
        echo "critical"
        return
    fi
    
    # Check for high exit codes
    if [ "$exit_code" -gt 10 ]; then
        echo "critical"
        return
    fi
    
    # Check for specific error patterns
    if echo "$error_message" | grep -qi -E "(timeout|failed|error)"; then
        echo "error"
        return
    fi
    
    # Default to warning
    echo "warning"
}

# Function to send test notifications
send_test_notifications() {
    local test_message="Test notification from Web Scraper"
    local test_subject="$EMAIL_SUBJECT_PREFIX Test Notification"
    
    echo -e "${GREEN}Sending test notifications...${NC}"
    
    local success_count=0
    local total_count=0
    
    # Test desktop notification
    if [ "$DESKTOP_NOTIFICATIONS" -eq 1 ]; then
        total_count=$((total_count + 1))
        if send_desktop_notification "Web Scraper Test" "$test_message" "info"; then
            success_count=$((success_count + 1))
        fi
    fi
    
    # Test email notification
    if [ "$EMAIL_ENABLED" -eq 1 ]; then
        total_count=$((total_count + 1))
        if send_email_notification "$test_subject" "$test_message"; then
            success_count=$((success_count + 1))
        fi
    fi
    
    # Test Slack notification
    if [ "$SLACK_ENABLED" -eq 1 ]; then
        total_count=$((total_count + 1))
        if send_slack_notification "$test_message" "info"; then
            success_count=$((success_count + 1))
        fi
    fi
    
    echo
    echo -e "${GREEN}Test results: $success_count/$total_count notifications sent successfully${NC}"
    
    if [ "$success_count" -eq "$total_count" ] && [ "$total_count" -gt 0 ]; then
        echo -e "${GREEN}All enabled notification channels are working correctly${NC}"
        return 0
    else
        echo -e "${YELLOW}Some notification channels failed or are disabled${NC}"
        return 1
    fi
}

# Function to log notification attempt
log_notification() {
    local message="$1"
    local status="$2"
    
    local log_file="$LOG_DIR/notifications.log"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo "[$timestamp] $status: $message" >> "$log_file"
}

# Main notification function
send_error_notification() {
    local error_message="$1"
    local exit_code="${2:-1}"
    
    if [ "$NOTIFICATION_ENABLED" -eq 0 ]; then
        echo -e "${YELLOW}[INFO]${NC} Notifications disabled"
        return 0
    fi
    
    local urgency=$(determine_urgency "$error_message" "$exit_code")
    local subject="$EMAIL_SUBJECT_PREFIX Error Alert"
    
    case "$urgency" in
        "critical")
            subject="$EMAIL_SUBJECT_PREFIX CRITICAL ERROR"
            ;;
        "error")
            subject="$EMAIL_SUBJECT_PREFIX Error"
            ;;
        "warning")
            subject="$EMAIL_SUBJECT_PREFIX Warning"
            ;;
    esac
    
    echo -e "${RED}[ERROR]${NC} Sending error notification: $error_message"
    
    local success_count=0
    local total_attempts=0
    
    # Send desktop notification
    if [ "$DESKTOP_NOTIFICATIONS" -eq 1 ]; then
        total_attempts=$((total_attempts + 1))
        if send_desktop_notification "Web Scraper Error" "$error_message" "$urgency"; then
            success_count=$((success_count + 1))
        fi
    fi
    
    # Send email notification
    if [ "$EMAIL_ENABLED" -eq 1 ]; then
        total_attempts=$((total_attempts + 1))
        if send_email_notification "$subject" "$error_message"; then
            success_count=$((success_count + 1))
        fi
    fi
    
    # Send Slack notification
    if [ "$SLACK_ENABLED" -eq 1 ]; then
        total_attempts=$((total_attempts + 1))
        if send_slack_notification "$error_message" "$urgency"; then
            success_count=$((success_count + 1))
        fi
    fi
    
    # Log the notification attempt
    log_notification "$error_message" "Sent $success_count/$total_attempts notifications"
    
    if [ "$total_attempts" -eq 0 ]; then
        echo -e "${YELLOW}[WARN]${NC} No notification channels enabled"
        return 1
    elif [ "$success_count" -eq 0 ]; then
        echo -e "${RED}[ERROR]${NC} All notification attempts failed"
        return 1
    elif [ "$success_count" -lt "$total_attempts" ]; then
        echo -e "${YELLOW}[WARN]${NC} Some notification attempts failed ($success_count/$total_attempts succeeded)"
        return 1
    else
        echo -e "${GREEN}[INFO]${NC} All notifications sent successfully"
        return 0
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -t|--test)
            send_test_notifications
            exit $?
            ;;
        -c|--config)
            show_config
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

# Main execution
if [ $# -eq 0 ]; then
    echo -e "${RED}[ERROR]${NC} Error message is required"
    show_usage
    exit 1
fi

ERROR_MESSAGE="$1"
EXIT_CODE="${2:-1}"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Send the notification
send_error_notification "$ERROR_MESSAGE" "$EXIT_CODE"
exit $?