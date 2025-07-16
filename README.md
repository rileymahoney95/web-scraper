# Web Scraper

A Python-based web scraper that automatically collects HTML content from specified websites and stores the data in a PostgreSQL database. Designed for scheduled execution with comprehensive logging and error handling.

## Quick Start

### Prerequisites

- Python 3.8+
- PostgreSQL database

### Setup

1. **Install dependencies**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set up database**:
   ```bash
   # Create database and tables
   psql -U postgres -f db/setup.sql
   ```

3. **Configure environment**:
   ```bash
   export DB_PASSWORD=your_secure_password
   ```

4. **Run the scraper**:
   ```bash
   python src/main.py
   ```

## Configuration

Edit `src/config.yaml` to customize:

- **URLs to scrape**: Add/remove target websites
- **Database connection**: Host, port, database name
- **Scraping settings**: Timeouts, delays, retry attempts
- **Logging**: Log level, file rotation settings

Example:
```yaml
scraping:
  urls:
    - url: 'https://example.com'
      name: 'Example Site'
      enabled: true
  settings:
    timeout: 30
    retry_attempts: 3
    delay_between_requests: 1
    respect_robots_txt: true
```

## Usage

### Basic Commands

```bash
# Run scraper with default settings
python src/main.py

# Test configuration without scraping
python src/main.py --dry-run

# Initialize database tables
python src/main.py --setup-db

# Enable verbose logging
python src/main.py --verbose

# Use custom configuration file
python src/main.py --config /path/to/config.yaml
```

### Environment Variables

Required:
- `DB_PASSWORD` - PostgreSQL database password

Optional:
- `DB_HOST` - Database host (default: localhost)
- `DB_PORT` - Database port (default: 5432)
- `DB_NAME` - Database name (default: web_scraper)
- `DB_USER` - Database user (default: scraper_user)

## Features

- **Robust HTML extraction**: Multi-strategy title and content extraction
- **Robots.txt compliance**: Respects website crawling policies and delays
- **Error handling**: Automatic retries with exponential backoff
- **Smart duplicate detection**: Content change tracking with conditional HTTP requests
- **Performance monitoring**: Request timing and session statistics
- **Scheduled execution**: Designed for cron job automation
- **Comprehensive logging**: Rotating log files with configurable levels

## Database Schema

The scraper stores data in two main tables:

- `scraped_content` - HTML content, titles, URLs, metadata, and Last-Modified headers
- `scraping_stats` - Session statistics and performance metrics

## Monitoring

View logs to monitor scraper activity:
```bash
# Real-time log monitoring
tail -f logs/scraper.log

# Check for errors
grep "ERROR\|WARNING" logs/scraper.log
```

## Automation & Scheduling

### Quick Setup (macOS)

1. **Check permissions**:
   ```bash
   ./scripts/setup_macos_permissions.sh
   ```

2. **Set up cron job**:
   ```bash
   ./scripts/setup_cron.sh
   ```

3. **Monitor scraper**:
   ```bash
   ./scripts/monitor_scraper.sh
   ```

### Available Scripts

- `setup_cron.sh` - Interactive cron job setup with scheduling options
- `cron_wrapper.sh` - Robust cron execution wrapper with error handling
- `monitor_scraper.sh` - Health monitoring and status reports
- `cleanup_logs.sh` - Automated log cleanup and rotation
- `notify_errors.sh` - Error notifications (desktop, email, Slack)
- `test_cron_setup.sh` - Validate your cron configuration
- `validate_permissions.sh` - Check and fix file permissions

### Manual Cron Setup

**⚠️ Important**: Cron needs environment variables and output redirection:

```bash
# Edit crontab
crontab -e

# CORRECT format (loads DB_PASSWORD and captures logs):
0 9,21 * * * /bin/zsh -c "source ~/.zshrc && /path/to/idea-scraper/scripts/cron_wrapper.sh" >> /path/to/idea-scraper/logs/cron.log 2>&1

# Other schedules:
# Every 6 hours
0 */6 * * * /bin/zsh -c "source ~/.zshrc && /path/to/idea-scraper/scripts/cron_wrapper.sh" >> /path/to/idea-scraper/logs/cron.log 2>&1

# Daily at 2 AM
0 2 * * * /bin/zsh -c "source ~/.zshrc && /path/to/idea-scraper/scripts/cron_wrapper.sh" >> /path/to/idea-scraper/logs/cron.log 2>&1
```

### Monitoring Commands

```bash
# Check scraper health
./scripts/monitor_scraper.sh

# View recent logs
tail -f logs/scraper.log
tail -f logs/cron.log

# Clean up old logs
./scripts/cleanup_logs.sh

# Test notifications
./scripts/notify_errors.sh --test
```

## Exit Codes

- `0` - Success
- `1` - Configuration error
- `2` - Database connection error
- `3` - Logging setup error
- `4` - Runtime error
- `5` - Keyboard interrupt

## Troubleshooting

**Database connection fails**:
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Test connection manually
psql -h localhost -U scraper_user -d web_scraper
```

**Configuration errors**:
```bash
# Validate settings
python src/main.py --dry-run --verbose

# Check environment variables
echo $DB_PASSWORD
```

**Permission issues**:
```bash
# Ensure log directory exists
mkdir -p logs
chmod 755 logs
```

## Documentation

- **`docs/DEPLOYMENT.md`** - Complete macOS deployment guide
- **`docs/PRD.md`** - Product requirements and specifications
- **`CLAUDE.md`** - Detailed project information and development guide

## Need Help?

**Common Issues:**
- Permission errors → Run `./scripts/setup_macos_permissions.sh`
- Database connection → Check PostgreSQL is running and DB_PASSWORD is set
- Cron not working → Run `./scripts/test_cron_setup.sh -v` for diagnostics

**Quick Commands:**
```bash
# Full system check
./scripts/test_cron_setup.sh -v

# Fix permissions
./scripts/validate_permissions.sh --fix

# Monitor health
./scripts/monitor_scraper.sh --stats
```