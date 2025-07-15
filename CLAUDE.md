# Web Scraper - CLAUDE.md

This file provides comprehensive information about the Web Scraper project to help Claude Code assist with development, debugging, and maintenance tasks.

## Project Overview

**Name**: Web Scraper - Daily HTML Collection System  
**Phase**: Phase 1 (Core Infrastructure) - COMPLETED  
**Language**: Python 3.8+  
**Database**: PostgreSQL  
**Architecture**: Standalone executable suitable for cron job scheduling  

### Purpose

A Python-based web scraper that automatically collects HTML content from specified websites on a scheduled basis and stores the data in a local PostgreSQL database. The application is designed to run as a standalone process with comprehensive logging, error handling, and configuration management.

### Success Criteria

- ✅ Executable Python script that can be scheduled via cron
- ✅ Reliable data collection and storage infrastructure
- ✅ Graceful error handling and logging
- ✅ Clean shutdown after each execution
- ✅ Configurable target websites and scraping settings

## Project Structure

```
idea-scraper/
├── src/
│   ├── main.py              # Application entry point
│   ├── config.py            # Configuration management
│   ├── config.yaml          # Configuration file
│   ├── database.py          # Database operations
│   ├── scraper.py           # Web scraping logic (Phase 2)
│   └── utils.py             # Helper functions and logging
├── db/
│   └── setup.sql           # Database schema and setup
├── test/
│   ├── test_database_integration.py
│   └── test_utils.py
├── logs/                   # Log files directory
├── docs/                   # Documentation
│   ├── PRD.md              # Product Requirements Document
│   └── PHASE1.md          # Phase 1 implementation details
├── requirements.txt        # Python dependencies
├── README.md              # Project documentation
└── CLAUDE.md              # This file
```

## Technology Stack

### Core Dependencies
- **psycopg2-binary==2.9.10** - PostgreSQL adapter with binary dependencies
- **PyYAML==6.0.2** - YAML configuration file parsing
- **requests==2.32.4** - HTTP library for web requests (Phase 2)
- **beautifulsoup4==4.13.4** - HTML parsing library (Phase 2)
- **lxml==6.0.0** - XML/HTML processing with XPath support (Phase 2)

### Database Schema
```sql
-- Main content storage
CREATE TABLE scraped_content (
    id SERIAL PRIMARY KEY,
    url VARCHAR(2048) NOT NULL,
    title VARCHAR(1024),
    content TEXT,
    content_hash VARCHAR(64),
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    response_status INTEGER,
    response_time_ms INTEGER,
    content_length INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Session statistics tracking
CREATE TABLE scraping_stats (
    id SERIAL PRIMARY KEY,
    scrape_session_id VARCHAR(64),
    total_urls INTEGER,
    successful_scrapes INTEGER,
    failed_scrapes INTEGER,
    total_execution_time_ms INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
```

## Configuration Management

### Environment Variables
- **DB_PASSWORD** (Required) - PostgreSQL database password
- **TEST_DB_HOST** (Optional) - Test database host for testing
- **TEST_DB_PORT** (Optional) - Test database port for testing
- **TEST_DB_NAME** (Optional) - Test database name for testing
- **TEST_DB_USER** (Optional) - Test database user for testing
- **TEST_DB_PASSWORD** (Optional) - Test database password for testing

### Configuration File: src/config.yaml
```yaml
database:
  host: localhost
  port: 5432
  database: web_scraper
  username: scraper_user
  password: ${DB_PASSWORD}  # Environment variable substitution
  max_connections: 20
  min_connections: 5
  connection_timeout: 30

scraping:
  urls:
    - url: 'https://example.com'
      name: 'Example Site'
      enabled: true
  settings:
    timeout: 30
    retry_attempts: 3
    retry_delay: 5
    user_agent: 'WebScraper/1.0'
    delay_between_requests: 1

logging:
  level: INFO
  file: 'logs/scraper.log'
  max_size_mb: 10
  backup_count: 5
  format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
```

## Build and Development Commands

### Installation and Setup
```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up database (requires PostgreSQL running)
export DB_PASSWORD="your_secure_password"
psql -U postgres -f db/setup.sql

# Alternative: Initialize tables without running setup.sql
python src/main.py --setup-db
```

### Running the Application
```bash
# Basic execution
python src/main.py

# With custom configuration
python src/main.py --config /path/to/config.yaml

# Initialize database tables
python src/main.py --setup-db

# Verbose logging (DEBUG level)
python src/main.py --verbose

# Dry run mode (Phase 2+)
python src/main.py --dry-run

# Show version
python src/main.py --version
```

### Testing
```bash
# Run all tests using virtual environment
source venv/bin/activate && python -m pytest test/ -v

# Run specific test modules
python test/test_database_integration.py    # Database tests (requires PostgreSQL)
python test/test_http_client.py             # HTTP client tests
python test/test_utils.py                   # Utility function tests

# Run tests with coverage (if pytest-cov installed)
python -m pytest test/ --cov=src --cov-report=html
```

### Deployment with Cron
```bash
# Example cron job entries
# Run every 6 hours
0 */6 * * * cd /path/to/idea-scraper && source venv/bin/activate && python src/main.py

# Run twice daily at 9 AM and 9 PM
0 9,21 * * * cd /path/to/idea-scraper && source venv/bin/activate && python src/main.py
```

## Key Classes and Components

### 1. WebScraperApp (src/main.py)
**Purpose**: Main application orchestrator  
**Key Methods**:
- `run()` - Main execution loop with exit codes
- `parse_arguments()` - Command-line argument parsing
- `load_configuration()` - Configuration loading and validation
- `initialize_database()` - Database connection setup
- `cleanup()` - Resource cleanup on shutdown

**Exit Codes**:
- 0: Success
- 1: Configuration error
- 2: Database connection error
- 3: Logging setup error
- 4: Runtime error
- 5: Keyboard interrupt

### 2. Config (src/config.py)
**Purpose**: Configuration management with YAML loading and validation  
**Key Methods**:
- `load()` - Load and validate configuration from YAML
- `get_database_config()` - Get database configuration section
- `get_scraping_config()` - Get scraping configuration section
- `get_logging_config()` - Get logging configuration section
- `_substitute_env_vars()` - Environment variable substitution

**Features**:
- Environment variable substitution: `${VAR_NAME}` or `${VAR_NAME:-default}`
- Comprehensive validation for all configuration sections
- Clear error messages for configuration issues

### 3. DatabaseManager (src/database.py)
**Purpose**: Database operations with connection pooling and transaction management  
**Key Methods**:
- `connect()` / `disconnect()` - Connection pool management
- `insert_content()` - Store scraped content with metadata
- `get_content_by_url()` - Retrieve content by URL
- `content_exists()` - Check for duplicate content via hash
- `health_check()` - Database connectivity verification
- `create_tables()` - Initialize database schema

**Features**:
- ThreadedConnectionPool for concurrent operations
- Automatic transaction rollback on errors
- Content deduplication via SHA-256 hashing
- Connection health monitoring

### 4. Utility Functions (src/utils.py)
**Purpose**: Logging system and helper functions  
**Key Functions**:
- `setup_logging()` - Configure rotating file logs and console output
- `get_logger()` - Get module-specific logger instances
- `@log_performance` - Decorator for execution time logging
- `calculate_content_hash()` - SHA-256 content hashing
- `validate_url()` - URL format validation
- `@retry_with_backoff` - Automatic retry with exponential backoff
- `format_bytes()` - Human-readable byte formatting

### 5. HTTP Client (src/scraper.py) ✅ NEW IN PHASE 2
**Purpose**: Robust HTTP requests with retry logic and error handling  
**Key Classes**:
- `HTTPClient` - Main HTTP client with session management and retry logic
- `NetworkError`, `ScrapingError` - Custom exception hierarchy for error handling
- `RequestMetrics` - Data structure for request performance metrics

**Key Features**:
- Exponential backoff with jitter for retry logic
- Connection pooling for performance
- Intelligent retry decisions (5xx and 429 errors)
- Request/response metrics collection
- Thread-safe concurrent operations
- Context manager support for resource cleanup

**Usage Example**:
```python
from scraper import HTTPClient, NetworkError

config = scraping_config['settings']
with HTTPClient(config) as client:
    try:
        response, metrics = client.fetch_url('https://example.com')
        print(f"Status: {response.status_code}, Time: {metrics.response_time_ms}ms")
    except NetworkError as e:
        print(f"Request failed: {e}")
```

### 6. Robots.txt Checker (src/scraper.py) ✅ NEW IN PHASE 2
**Purpose**: Robots.txt compliance checking and crawl-delay enforcement  
**Key Classes**:
- `RobotChecker` - Main robots.txt compliance checker with caching
- `RobotsError` - Exception for robots.txt compliance violations

**Key Features**:
- Automatic robots.txt fetching and parsing for each domain
- In-memory caching with 24-hour TTL to avoid repeated requests
- Support for User-agent specific rules and wildcards (*)
- Crawl-delay directive parsing and enforcement
- Allow/Disallow directive processing with pattern matching
- Thread-safe caching for concurrent operations
- Graceful error handling (missing/invalid robots.txt allows all)

**Usage Example**:
```python
from scraper import RobotChecker, HTTPClient, RobotsError

config = scraping_config['settings']
http_client = HTTPClient(config)
robot_checker = RobotChecker(config, http_client)

try:
    if robot_checker.can_fetch('https://example.com/admin/'):
        # Check for crawl delay
        delay = robot_checker.get_crawl_delay('https://example.com/admin/')
        if delay > 0:
            time.sleep(delay)
        
        # Proceed with scraping
        response, metrics = http_client.fetch_url('https://example.com/admin/')
    else:
        print("Robots.txt disallows access to this URL")
except RobotsError as e:
    print(f"Robots.txt compliance error: {e}")
```

### 7. Enhanced Duplicate Detection (Task 4) ✅ NEW IN PHASE 3
**Purpose**: Advanced duplicate detection with content change tracking and conditional requests  
**Key Features**:
- **Content change detection**: Distinguishes between duplicate content and content changes
- **Conditional HTTP requests**: Uses If-Modified-Since headers to avoid unnecessary downloads  
- **Last-Modified tracking**: Stores and retrieves Last-Modified headers for optimization
- **Enhanced logging**: Structured logging for content changes, duplicates, and new URLs
- **Database migration**: Safe migration to add `last_modified` column to existing tables

**Database Enhancements**:
- **New column**: `last_modified VARCHAR(255)` in `scraped_content` table
- **New method**: `get_latest_content_hash()` for change detection
- **Migration support**: `migrate_add_last_modified_column()` for existing installations

**HTTP Optimization**:
- **Conditional requests**: `fetch_url(url, if_modified_since=header)` support
- **304 handling**: Proper handling of "304 Not Modified" responses
- **Bandwidth savings**: Skip downloads when content hasn't changed

**Usage Example**:
```python
from scraper import WebScraper
from database import DatabaseManager

# Enhanced duplicate detection in action
scraper = WebScraper(config, db_manager)
session = scraper.scrape_urls()

# Automatic behavior:
# 1. Check for previous Last-Modified header
# 2. Send conditional request if available  
# 3. Handle 304 Not Modified (skip processing)
# 4. Detect content changes vs. true duplicates
# 5. Log structured change/duplicate events
```

**Benefits**:
- **Reduced bandwidth**: 304 responses skip unnecessary downloads
- **Faster processing**: Skip content extraction for unchanged pages
- **Change monitoring**: Track and log content changes over time
- **Intelligent scheduling**: Future enhancement foundation for adaptive scraping

## Current Implementation Status

### Phase 1: Core Infrastructure ✅ COMPLETED
- [x] Project structure and dependencies
- [x] Configuration management with YAML and environment variables
- [x] PostgreSQL database schema and connection pooling
- [x] Comprehensive logging system with rotation
- [x] Main application entry point with CLI
- [x] Utility functions and error handling
- [x] Integration tests for database operations

### Phase 2: Web Scraping Engine ✅ COMPLETED
- [x] **HTTP client implementation with retry logic** ✅ COMPLETED
- [x] **HTML parsing and content extraction** ✅ COMPLETED  
- [x] **Robots.txt compliance checking** ✅ COMPLETED
- [x] **Main scraper orchestration and integration** ✅ COMPLETED
- [x] **Enhanced error handling for scraping scenarios** ✅ COMPLETED
- [x] **Duplicate detection enhancements** ✅ COMPLETED (Task 4)

### Phase 3: Database Integration Enhancement (IN PROGRESS)
- [x] **Duplicate detection enhancement** ✅ COMPLETED
- [ ] Advanced query operations  
- [ ] Data archival and cleanup
- [ ] Performance optimization
- [ ] Migration scripts

## Logging and Monitoring

### Log Format
```
2025-07-13 10:30:45 - WebScraper.main - INFO - Web Scraper starting - Session ID: abc12345
2025-07-13 10:30:45 - WebScraper.database - INFO - Database connection established successfully
2025-07-13 10:30:45 - WebScraper.config - INFO - Configuration loaded successfully
```

### Log Files
- **Location**: `logs/scraper.log`
- **Rotation**: 10MB max size, 5 backup files
- **Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Console Output**: INFO level and above

### Performance Monitoring
- Function execution timing via `@log_performance` decorator
- Database operation metrics
- Session tracking with unique session IDs
- Memory usage and connection pool statistics

## Error Handling and Recovery

### Database Errors
- Automatic connection retry with exponential backoff
- Transaction rollback on failures
- Connection pool health monitoring
- Graceful degradation on partial failures

### Configuration Errors
- Comprehensive validation with clear error messages
- Environment variable substitution with defaults
- File path validation and directory creation

### Network Errors (Phase 2)
- HTTP timeout handling with retries
- Rate limiting and delay between requests
- User agent configuration
- SSL certificate validation

## Security Considerations

### Credential Management
- Environment variable storage for sensitive data
- No hardcoded passwords in configuration files
- Database user with minimal required privileges

### Input Validation
- URL format validation
- Configuration parameter validation
- SQL injection prevention with parameterized queries

### Logging Security
- No sensitive data in log files
- Sanitized error messages
- Secure log file permissions

## Development Guidelines

### Code Style
- Follow PEP 8 Python style guidelines
- Type hints for better code documentation
- Comprehensive docstrings for all classes and methods
- Meaningful variable and function names

### Testing Strategy
- Unit tests for individual components
- Integration tests for database operations
- Mocked tests for external dependencies
- Performance and load testing

### Error Handling
- Proper exception handling with specific error types
- Graceful degradation when possible
- Clear error messages for debugging
- Proper resource cleanup in all exit paths

## Common Issues and Solutions

### Database Connection Issues
```bash
# Check PostgreSQL service
sudo systemctl status postgresql

# Verify database exists
psql -U postgres -c "\l" | grep web_scraper

# Test connection
python -c "from src.database import DatabaseManager; dm = DatabaseManager({'host': 'localhost', 'port': 5432, 'database': 'web_scraper', 'username': 'scraper_user', 'password': 'your_password'}); dm.connect(); print('Success')"
```

### Configuration Issues
```bash
# Validate configuration
python -c "from src.config import Config; c = Config(); c.load(); print('Config valid')"

# Check environment variables
echo $DB_PASSWORD

# Test with custom config
python src/main.py --config custom_config.yaml --verbose
```

### Log File Issues
```bash
# Check log directory permissions
ls -la logs/

# Create log directory if missing
mkdir -p logs

# Check disk space for log files
df -h logs/
```

## Future Enhancements

### Planned Features
- Web dashboard for monitoring
- Email notifications for failures
- Support for JavaScript-heavy sites (Selenium)
- Content change detection and alerting
- API endpoint for querying scraped data
- Multi-threading for parallel scraping

### Scalability Considerations
- Docker containerization
- Cloud deployment options
- Distributed scraping architecture
- Message queue integration
- Horizontal scaling capabilities

## API Reference

### Command Line Interface
```bash
python src/main.py [OPTIONS]

Options:
  -c, --config PATH     Configuration file path (default: config.yaml)
  --setup-db           Initialize database tables and exit
  --dry-run            Run in dry-run mode without making changes
  -v, --verbose        Enable verbose logging (DEBUG level)
  --version            Show version information
  -h, --help           Show help message
```

### Configuration Schema
Refer to `src/config.yaml` for the complete configuration schema with all available options and their descriptions.

## Contact and Support

For development questions, bug reports, or feature requests, refer to the project documentation in the `docs/` directory or examine the test files for usage examples.

**Last Updated**: July 2025  
**Version**: 1.3.0 (Phase 1 Complete, Phase 2 Complete, Task 4 Duplicate Detection Enhancement Complete)