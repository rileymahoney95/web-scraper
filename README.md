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

## Automation

Schedule regular scraping with cron:
```bash
# Run every 6 hours
0 */6 * * * cd /path/to/idea-scraper && source venv/bin/activate && python src/main.py

# Run twice daily
0 9,21 * * * cd /path/to/idea-scraper && source venv/bin/activate && python src/main.py
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

For detailed documentation, see `docs/` directory and `CLAUDE.md`.