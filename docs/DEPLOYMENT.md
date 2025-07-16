# Web Scraper Deployment Guide for macOS

This guide provides step-by-step instructions for deploying and scheduling the web scraper on macOS systems using cron jobs.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Permission Configuration](#permission-configuration)
4. [Cron Job Setup](#cron-job-setup)
5. [Monitoring and Maintenance](#monitoring-and-maintenance)
6. [Troubleshooting](#troubleshooting)
7. [Advanced Configuration](#advanced-configuration)

## Prerequisites

### System Requirements

- macOS 10.14 (Mojave) or later
- Python 3.8 or later
- PostgreSQL 12 or later
- Terminal access with administrative privileges

### Required Software

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3 (if not already installed)
brew install python3

# Install PostgreSQL (if not already installed)
brew install postgresql
brew services start postgresql
```

### Database Setup

Create the database and user:

```bash
# Start PostgreSQL service
brew services start postgresql

# Create database and user
psql postgres -c "CREATE DATABASE web_scraper;"
psql postgres -c "CREATE USER scraper_user WITH PASSWORD 'your_secure_password';"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE web_scraper TO scraper_user;"

# Initialize database schema
psql -U scraper_user -d web_scraper -f db/setup.sql
```

## Initial Setup

### 1. Project Installation

```bash
# Clone or navigate to project directory
cd /path/to/idea-scraper

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python src/main.py --help
```

### 2. Configuration

```bash
# Set up environment variables
export DB_PASSWORD="your_secure_password"

# Add to your shell profile for persistence
echo 'export DB_PASSWORD="your_secure_password"' >> ~/.zshrc
source ~/.zshrc

# Test configuration
python src/main.py --setup-db --dry-run
```

## Permission Configuration

### 1. Check Current Permissions

```bash
# Run permission validation
./scripts/validate_permissions.sh -v

# Check macOS-specific permissions
./scripts/setup_macos_permissions.sh
```

### 2. Grant macOS Permissions

The web scraper requires specific macOS permissions to function correctly:

#### Full Disk Access for Terminal

1. Open **System Preferences** → **Security & Privacy** → **Privacy**
2. Click the lock icon and enter your password
3. Select **Full Disk Access** from the left sidebar
4. Click the **+** button and navigate to `/Applications/Utilities/Terminal.app`
5. Add Terminal to the list and ensure it's checked

#### Automation Permissions

1. In **System Preferences** → **Security & Privacy** → **Privacy**
2. Select **Automation** from the left sidebar
3. Allow Terminal to control system events if prompted

### 3. Fix Permission Issues

```bash
# Automatically fix common permission issues
./scripts/validate_permissions.sh --fix

# Make all scripts executable
chmod +x scripts/*.sh
```

## Cron Job Setup

### 1. Run Setup Script

The interactive setup script will guide you through cron job configuration:

```bash
# Run the cron setup script
./scripts/setup_cron.sh
```

This script will:
- Check all prerequisites
- Set up environment variables
- Create appropriate cron job entries
- Test the configuration

### 2. Available Scheduling Options

The setup script offers several predefined schedules:

1. **Every 6 hours** (`0 */6 * * *`) - Good for regular content monitoring
2. **Twice daily** (`0 9,21 * * *`) - 9 AM and 9 PM execution
3. **Daily at 2 AM** (`0 2 * * *`) - Once per day during low-traffic hours
4. **Business hours** (`0 8-18/2 * * *`) - Every 2 hours from 8 AM to 6 PM
5. **Custom schedule** - Define your own cron expression

### 3. Manual Cron Setup

If you prefer manual configuration:

```bash
# Edit crontab
crontab -e

# Add one of these lines (adjust path as needed):
# Every 6 hours
0 */6 * * * /Users/yourusername/Documents/Workspace/idea-scraper/scripts/cron_wrapper.sh

# Twice daily
0 9,21 * * * /Users/yourusername/Documents/Workspace/idea-scraper/scripts/cron_wrapper.sh

# Verify cron job
crontab -l
```

### 4. Test Cron Configuration

```bash
# Test the complete cron setup
./scripts/test_cron_setup.sh -v

# Test just the wrapper script
./scripts/cron_wrapper.sh --test
```

## Monitoring and Maintenance

### 1. Health Monitoring

```bash
# Check scraper health
./scripts/monitor_scraper.sh

# Monitor with verbose output
./scripts/monitor_scraper.sh -v

# Check specific aspects
./scripts/monitor_scraper.sh --status
./scripts/monitor_scraper.sh --errors
./scripts/monitor_scraper.sh --stats
```

### 2. Log Management

```bash
# View recent logs
tail -f logs/scraper.log
tail -f logs/cron.log

# Clean up old logs
./scripts/cleanup_logs.sh

# Clean up with dry run (see what would be deleted)
./scripts/cleanup_logs.sh --dry-run
```

### 3. Error Notifications

Configure error notifications for proactive monitoring:

```bash
# Test notification system
./scripts/notify_errors.sh --test

# Configure notifications (set environment variables)
export NOTIFICATION_ENABLED=1
export DESKTOP_NOTIFICATIONS=1
export EMAIL_ENABLED=1
export EMAIL_TO="your-email@example.com"

# Test with actual error
./scripts/notify_errors.sh "Test error message" 1
```

### 4. Regular Maintenance Tasks

Create a weekly maintenance routine:

```bash
# Weekly maintenance script (you can add this to cron)
#!/bin/bash
cd /path/to/idea-scraper

# Clean up logs
./scripts/cleanup_logs.sh

# Check health
./scripts/monitor_scraper.sh --stats

# Validate permissions
./scripts/validate_permissions.sh --json
```

## Troubleshooting

### Common Issues

#### 1. Permission Denied Errors

**Problem**: Cron jobs fail with permission errors

**Solution**:
```bash
# Check and fix permissions
./scripts/validate_permissions.sh --fix

# Ensure Terminal has Full Disk Access
./scripts/setup_macos_permissions.sh
```

#### 2. Database Connection Failures

**Problem**: Cannot connect to PostgreSQL database

**Solution**:
```bash
# Check if PostgreSQL is running
brew services list | grep postgresql

# Start PostgreSQL if needed
brew services start postgresql

# Test connection manually
psql -U scraper_user -d web_scraper -c "SELECT 1;"

# Check environment variables
echo $DB_PASSWORD
```

#### 3. Virtual Environment Issues

**Problem**: Python packages not found or virtual environment errors

**Solution**:
```bash
# Recreate virtual environment
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test virtual environment
./scripts/cron_wrapper.sh --test
```

#### 4. Cron Job Not Running

**Problem**: Cron job is scheduled but not executing

**Solution**:
```bash
# Check cron service
launchctl list | grep cron

# Check cron jobs
crontab -l

# Check cron logs
tail -f /var/log/cron.log  # System cron log
tail -f logs/cron.log      # Application cron log

# Test cron job manually
./scripts/cron_wrapper.sh
```

### Debug Mode

Enable debug mode for detailed troubleshooting:

```bash
# Run with verbose logging
python src/main.py --verbose

# Check wrapper script with test mode
./scripts/cron_wrapper.sh --test

# Test complete setup
./scripts/test_cron_setup.sh -v
```

## Advanced Configuration

### 1. Custom Scheduling

For complex scheduling needs, you can create custom cron expressions:

```bash
# Examples of custom schedules:
# Every 15 minutes during business hours
*/15 9-17 * * 1-5 /path/to/cron_wrapper.sh

# Every hour except during maintenance window (2-4 AM)
0 0-1,5-23 * * * /path/to/cron_wrapper.sh

# Weekdays only at specific times
0 8,12,16,20 * * 1-5 /path/to/cron_wrapper.sh
```

### 2. Environment-Specific Configuration

Create different configurations for different environments:

```bash
# Development environment
export DB_PASSWORD="dev_password"
export LOG_LEVEL="DEBUG"

# Production environment
export DB_PASSWORD="prod_password"
export LOG_LEVEL="INFO"
export EMAIL_ENABLED=1
export EMAIL_TO="admin@company.com"
```

### 3. Load Balancing and Scaling

For high-volume scraping:

```bash
# Multiple instances with different schedules
# Instance 1: Even hours
0 */2 * * * /path/to/cron_wrapper.sh

# Instance 2: Odd hours
0 1-23/2 * * * /path/to/cron_wrapper.sh
```

### 4. Backup and Recovery

Set up automated backups:

```bash
# Daily database backup
0 3 * * * pg_dump -U scraper_user web_scraper > /backups/web_scraper_$(date +\%Y\%m\%d).sql

# Weekly log archive
0 4 * * 0 tar -czf /backups/logs_$(date +\%Y\%m\%d).tar.gz logs/
```

## Security Considerations

### 1. Credential Management

- Store sensitive credentials in environment variables
- Use macOS Keychain for additional security
- Never commit passwords to version control

### 2. Network Security

- Configure firewalls appropriately
- Use SSL/TLS for database connections
- Implement rate limiting in scraper configuration

### 3. File Permissions

- Ensure log files are not world-readable
- Set appropriate permissions on configuration files
- Use umask to control default file permissions

## Performance Optimization

### 1. Resource Monitoring

```bash
# Monitor system resources during scraping
top -pid $(pgrep -f "python.*main.py")

# Check disk usage
df -h
du -sh logs/
```

### 2. Database Optimization

```bash
# Regular database maintenance
psql -U scraper_user -d web_scraper -c "VACUUM ANALYZE;"

# Check database size
psql -U scraper_user -d web_scraper -c "SELECT pg_size_pretty(pg_database_size('web_scraper'));"
```

### 3. Log Rotation

Configure automatic log rotation:

```bash
# Add to cron for daily log cleanup
0 1 * * * /path/to/scripts/cleanup_logs.sh
```

## Deployment Checklist

Use this checklist to ensure proper deployment:

- [ ] PostgreSQL installed and running
- [ ] Database and user created
- [ ] Database schema initialized
- [ ] Python virtual environment created
- [ ] Dependencies installed
- [ ] Environment variables set
- [ ] Configuration file updated
- [ ] macOS permissions granted
- [ ] File permissions correct
- [ ] Scripts executable
- [ ] Cron job configured
- [ ] Health monitoring tested
- [ ] Error notifications configured
- [ ] Log rotation configured
- [ ] Backup strategy implemented
- [ ] Documentation updated

## Support and Maintenance

### Regular Tasks

**Daily**:
- Monitor application logs
- Check for error notifications
- Verify database connectivity

**Weekly**:
- Review scraping statistics
- Clean up old logs
- Check system resources

**Monthly**:
- Update dependencies
- Review and rotate credentials
- Backup configuration files

### Getting Help

If you encounter issues:

1. Check the logs: `tail -f logs/scraper.log`
2. Run diagnostics: `./scripts/monitor_scraper.sh -v`
3. Validate setup: `./scripts/test_cron_setup.sh`
4. Review this documentation
5. Check the project's GitHub issues

---

**Last Updated**: July 2025  
**Version**: 1.0.0

This deployment guide should be updated as the project evolves and new features are added.