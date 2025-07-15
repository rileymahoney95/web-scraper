#!/usr/bin/env python3
"""
Main application entry point for the web scraper.

This module provides the WebScraperApp class that orchestrates all infrastructure
components including configuration loading, database initialization, logging setup,
and graceful shutdown handling.
"""

import argparse
import signal
import sys
import os
import time
import uuid
from typing import Optional

# Add the src directory to Python path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, ConfigError
from database import DatabaseManager
from utils import setup_logging, get_logger, log_system_info


class WebScraperApp:
    """
    Main application class that orchestrates all infrastructure components.
    
    This class handles:
    - Command-line argument parsing
    - Configuration loading and validation
    - Database initialization
    - Logging system setup
    - Graceful shutdown procedures
    - Resource cleanup
    """
    
    def __init__(self):
        """Initialize the web scraper application."""
        self.config = None
        self.database_manager = None
        self.logger = None
        self.shutdown_requested = False
        self.session_id = str(uuid.uuid4())[:8]  # Short session ID for tracking
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def parse_arguments(self) -> argparse.Namespace:
        """
        Parse command-line arguments.
        
        Returns:
            Parsed arguments namespace
        """
        parser = argparse.ArgumentParser(
            description="Web Scraper - Automated HTML content collection system",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s                           # Run with default src/config.yaml
  %(prog)s --config /path/to/config  # Run with custom configuration
  %(prog)s --setup-db                # Initialize database tables
  %(prog)s --migrate                 # Run database migrations
  %(prog)s --dry-run                 # Run in dry-run mode (Phase 2+)
  %(prog)s --verbose                 # Enable verbose logging

Analytics and Reporting:
  %(prog)s --db-stats                # Show database statistics
  %(prog)s --trends --days 7         # Show 7-day trends analysis
  %(prog)s --report --format json    # Generate JSON report for latest session
  %(prog)s --report --session-id abc # Generate report for specific session
  %(prog)s --search "example.com"    # Search content with query
            """
        )
        
        parser.add_argument(
            '--config', '-c',
            type=str,
            default='src/config.yaml',
            help='Path to configuration file (default: src/config.yaml)'
        )
        
        parser.add_argument(
            '--setup-db',
            action='store_true',
            help='Initialize database tables and exit'
        )
        
        parser.add_argument(
            '--migrate',
            action='store_true',
            help='Run database migrations and exit'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode without making changes (Phase 2+)'
        )
        
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Enable verbose logging (DEBUG level)'
        )
        
        parser.add_argument(
            '--version',
            action='version',
            version='WebScraper 1.0.0'
        )
        
        # Analytics and reporting arguments
        parser.add_argument(
            '--db-stats',
            action='store_true',
            help='Show database statistics and exit'
        )
        
        parser.add_argument(
            '--trends',
            action='store_true',
            help='Show scraping trends analysis and exit'
        )
        
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days for trends analysis (default: 30)'
        )
        
        parser.add_argument(
            '--report',
            action='store_true',
            help='Generate scraping session report and exit'
        )
        
        parser.add_argument(
            '--session-id',
            type=str,
            help='Specific session ID for report generation (default: latest)'
        )
        
        parser.add_argument(
            '--format',
            choices=['dict', 'json', 'csv', 'html'],
            default='dict',
            help='Output format for reports (default: dict)'
        )
        
        parser.add_argument(
            '--search',
            type=str,
            help='Search content with query and exit'
        )
        
        parser.add_argument(
            '--search-limit',
            type=int,
            default=10,
            help='Maximum number of search results (default: 10)'
        )
        
        return parser.parse_args()
    
    def load_configuration(self, config_path: str) -> Config:
        """
        Load and validate configuration.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Loaded and validated Config object
            
        Raises:
            ConfigError: If configuration loading or validation fails
        """
        try:
            config = Config(config_path)
            config.load()
            return config
        except ConfigError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Unexpected error loading configuration: {e}", file=sys.stderr)
            raise ConfigError(f"Failed to load configuration: {e}")
    
    def setup_logging(self, config: Config, verbose: bool = False) -> None:
        """
        Set up logging system.
        
        Args:
            config: Configuration object
            verbose: Enable verbose (DEBUG) logging
        """
        logging_config = config.get_logging_config()
        
        # Override log level if verbose mode is enabled
        if verbose:
            logging_config['level'] = 'DEBUG'
        
        # Set up logging
        setup_logging(logging_config)
        
        # Get logger for this module
        self.logger = get_logger(__name__)
        
        # Log system information
        log_system_info()
        
        self.logger.info(f"Web Scraper starting - Session ID: {self.session_id}")
    
    def initialize_database(self, config: Config) -> DatabaseManager:
        """
        Initialize database connection.
        
        Args:
            config: Configuration object
            
        Returns:
            Initialized DatabaseManager instance
            
        Raises:
            Exception: If database initialization fails
        """
        try:
            database_config = config.get_database_config()
            db_manager = DatabaseManager(database_config)
            db_manager.connect()
            
            self.logger.info("Database connection established successfully")
            return db_manager
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    def setup_database_tables(self, db_manager: DatabaseManager) -> None:
        """
        Set up database tables and run migrations.
        
        Args:
            db_manager: DatabaseManager instance
        """
        try:
            self.logger.info("Creating database tables...")
            db_manager.create_tables()
            self.logger.info("Database tables created successfully")
            
            # Run migrations for existing installations
            self.logger.info("Running database migrations...")
            db_manager.migrate_add_last_modified_column()
            self.logger.info("Database migrations completed successfully")
        except Exception as e:
            self.logger.error(f"Failed to create database tables: {e}")
            raise
    
    def run(self) -> int:
        """
        Main application execution method.
        
        Returns:
            Exit code (0 for success, non-zero for various error conditions)
        """
        start_time = time.time()
        
        try:
            # Parse command-line arguments
            args = self.parse_arguments()
            
            # Load configuration
            try:
                self.config = self.load_configuration(args.config)
            except ConfigError:
                return 1  # Configuration error
            
            # Set up logging
            try:
                self.setup_logging(self.config, args.verbose)
            except Exception as e:
                print(f"Failed to set up logging: {e}", file=sys.stderr)
                return 3  # Logging setup error
            
            # Initialize database
            try:
                self.database_manager = self.initialize_database(self.config)
            except Exception as e:
                self.logger.error(f"Database initialization failed: {e}")
                return 2  # Database connection error
            
            # Handle database setup mode
            if args.setup_db:
                try:
                    self.setup_database_tables(self.database_manager)
                    self.logger.info("Database setup completed successfully")
                    return 0  # Success
                except Exception as e:
                    self.logger.error(f"Database setup failed: {e}")
                    return 2  # Database error
            
            # Handle database migration mode
            if args.migrate:
                try:
                    self.logger.info("Running database migrations...")
                    self.database_manager.migrate_add_last_modified_column()
                    self.logger.info("Database migrations completed successfully")
                    return 0  # Success
                except Exception as e:
                    self.logger.error(f"Database migration failed: {e}")
                    return 2  # Database error
            
            # Handle analytics and reporting commands
            if args.db_stats or args.trends or args.report or args.search:
                return self._handle_analytics_commands(args)
            
            # Main application logic (Phase 1 - Infrastructure only)
            self.logger.info("Starting main application logic...")
            
            # Check if shutdown was requested
            if self.shutdown_requested:
                self.logger.info("Shutdown requested, exiting gracefully")
                return 5  # Keyboard interrupt
            
            # Perform database health check
            if not self.database_manager.health_check():
                self.logger.error("Database health check failed")
                return 2  # Database error
            
            # Log configuration summary
            self._log_configuration_summary()
            
            # Phase 2: Web scraping logic
            from scraper import WebScraper
            
            try:
                with WebScraper(self.config, self.database_manager) as scraper:
                    if args.dry_run:
                        self.logger.info("Dry-run mode enabled - simulating scraping process")
                        session = scraper.scrape_urls(dry_run=True)
                    else:
                        self.logger.info("Starting web scraping process...")
                        session = scraper.scrape_urls(dry_run=False)
                    
                    # Store session statistics in database
                    if not args.dry_run:
                        self.database_manager.insert_scraping_stats(
                            session.session_id,
                            session.total_urls,
                            session.successful_scrapes,
                            session.failed_scrapes,
                            int((session.end_time - session.start_time).total_seconds() * 1000)
                        )
                    
                    # Log session summary
                    self.logger.info(f"Scraping session completed: {session.successful_scrapes}/{session.total_urls} successful, "
                                   f"{session.failed_scrapes} failed, {session.skipped_urls} skipped")
                    
                    if session.errors:
                        self.logger.warning(f"Encountered {len(session.errors)} errors during scraping")
                        for error in session.errors[:3]:  # Log first 3 errors
                            self.logger.warning(f"  - {error['url']}: {error['error_type']} - {error['error_message']}")
                        if len(session.errors) > 3:
                            self.logger.warning(f"  ... and {len(session.errors) - 3} more errors")
                    
            except Exception as e:
                self.logger.error(f"Web scraping failed: {type(e).__name__} - {str(e)}")
                return 4  # Runtime error
            
            # Calculate execution time
            execution_time = time.time() - start_time
            self.logger.info(f"Application completed successfully in {execution_time:.2f} seconds")
            
            return 0  # Success
            
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, shutting down gracefully")
            return 5  # Keyboard interrupt
        except Exception as e:
            if self.logger:
                self.logger.error(f"Unexpected error during execution: {e}")
            else:
                print(f"Unexpected error: {e}", file=sys.stderr)
            return 4  # Runtime error
        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """Perform cleanup operations before shutdown."""
        if self.logger:
            self.logger.info("Performing cleanup operations...")
        
        # Close database connections
        if self.database_manager:
            try:
                self.database_manager.disconnect()
                if self.logger:
                    self.logger.info("Database connections closed")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error closing database connections: {e}")
        
        # Additional cleanup operations can be added here
        
        if self.logger:
            self.logger.info(f"Cleanup completed for session {self.session_id}")
    
    def signal_handler(self, signum, frame) -> None:
        """
        Handle system signals for graceful shutdown.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_names = {
            signal.SIGINT: 'SIGINT',
            signal.SIGTERM: 'SIGTERM'
        }
        
        signal_name = signal_names.get(signum, f'Signal {signum}')
        
        if self.logger:
            self.logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        else:
            print(f"Received {signal_name}, shutting down...", file=sys.stderr)
        
        self.shutdown_requested = True
        
        # If this is the second signal, force exit
        if hasattr(self, '_shutdown_signal_received'):
            if self.logger:
                self.logger.warning("Second shutdown signal received, forcing exit")
            else:
                print("Forcing exit...", file=sys.stderr)
            sys.exit(5)
        
        self._shutdown_signal_received = True
    
    def _handle_analytics_commands(self, args) -> int:
        """
        Handle analytics and reporting commands.
        
        Args:
            args: Parsed command-line arguments
            
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            from database_queries import DatabaseAnalytics, DatabaseBulkOps
            
            analytics = DatabaseAnalytics(self.database_manager)
            
            # Handle database statistics
            if args.db_stats:
                self.logger.info("Generating database statistics...")
                try:
                    stats = analytics.get_content_statistics()
                    
                    print("\n=== Database Statistics ===")
                    print(f"Total Content Records: {stats.total_content:,}")
                    print(f"Unique URLs: {stats.unique_urls:,}")
                    print(f"Success Rate: {stats.success_rate:.2f}%")
                    print(f"Error Rate: {stats.error_rate:.2f}%")
                    print(f"Average Response Time: {stats.avg_response_time_ms:.2f}ms")
                    print(f"Average Content Length: {stats.avg_content_length:,} bytes")
                    
                    print("\nStatus Code Distribution:")
                    for status, count in sorted(stats.status_distribution.items()):
                        print(f"  {status}: {count:,} requests")
                    
                    print("\nMost Scraped URLs:")
                    for i, url_info in enumerate(stats.most_scraped_urls[:5], 1):
                        print(f"  {i}. {url_info['url']} ({url_info['scrape_count']} times)")
                    
                    print("\nContent by Day (last 7 days):")
                    for date, count in list(stats.content_by_day.items())[-7:]:
                        print(f"  {date}: {count:,} requests")
                    
                except Exception as e:
                    self.logger.error(f"Failed to generate statistics: {e}")
                    return 4
            
            # Handle trends analysis
            if args.trends:
                self.logger.info(f"Generating {args.days}-day trends analysis...")
                try:
                    trends = analytics.get_scraping_trends(days=args.days)
                    
                    print(f"\n=== {args.days}-Day Trends Analysis ===")
                    
                    print("\nContent Change Frequency:")
                    for category, count in trends.content_change_frequency.items():
                        print(f"  {category}: {count:,} URLs")
                    
                    print("\nSuccess Rate Trend (last 7 days):")
                    for day_data in trends.success_rate_trend[-7:]:
                        print(f"  {day_data['date']}: {day_data['success_rate']}% "
                              f"({day_data['successful_requests']}/{day_data['total_requests']})")
                    
                    print("\nVolume Trend (last 7 days):")
                    for day_data in trends.volume_trend[-7:]:
                        content_size_mb = (day_data['total_content_size'] or 0) / (1024 * 1024)
                        print(f"  {day_data['date']}: {day_data['request_count']:,} requests, "
                              f"{content_size_mb:.2f}MB content")
                    
                    if trends.error_patterns:
                        print("\nRecent Error Patterns:")
                        for error in trends.error_patterns[-5:]:
                            print(f"  {error['date']}: Status {error['response_status']} "
                                  f"({error['error_count']} times)")
                    
                except Exception as e:
                    self.logger.error(f"Failed to generate trends: {e}")
                    return 4
            
            # Handle search
            if args.search:
                self.logger.info(f"Searching content for '{args.search}'...")
                try:
                    search_results = analytics.search_content(
                        query=args.search, 
                        limit=args.search_limit
                    )
                    
                    print(f"\n=== Search Results for '{args.search}' ===")
                    print(f"Found {search_results.total_matches:,} matches in {search_results.query_time_ms:.2f}ms")
                    
                    if search_results.results:
                        print(f"\nShowing top {len(search_results.results)} results:")
                        for i, result in enumerate(search_results.results, 1):
                            print(f"\n{i}. {result['url']}")
                            print(f"   Title: {result['title'] or 'N/A'}")
                            print(f"   Status: {result['response_status']}")
                            print(f"   Scraped: {result['scraped_at']}")
                            if result.get('content_preview'):
                                print(f"   Preview: {result['content_preview']}")
                    
                    print("\nFacets:")
                    for facet_name, facet_data in search_results.facets.items():
                        print(f"  {facet_name.replace('_', ' ').title()}:")
                        for value, count in list(facet_data.items())[:5]:
                            print(f"    {value}: {count:,}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to search content: {e}")
                    return 4
            
            # Handle report generation
            if args.report:
                self.logger.info("Generating scraping session report...")
                try:
                    report = analytics.generate_scraping_report(
                        session_id=args.session_id,
                        format=args.format
                    )
                    
                    if args.format == 'dict':
                        print("\n=== Scraping Session Report ===")
                        summary = report['summary']
                        print(f"Session ID: {summary['session_id']}")
                        print(f"Start Time: {summary['start_time']}")
                        print(f"End Time: {summary['end_time']}")
                        print(f"Duration: {summary.get('duration_seconds', 0):.2f} seconds")
                        print(f"Total URLs: {summary['total_urls']}")
                        print(f"Successful: {summary['successful_scrapes']}")
                        print(f"Failed: {summary['failed_scrapes']}")
                        print(f"Success Rate: {summary['success_rate']:.2f}%")
                        
                        perf = report['performance_metrics']
                        print(f"\nPerformance:")
                        print(f"  Average Response Time: {perf['avg_response_time_ms']:.2f}ms")
                        print(f"  Total Content Size: {perf['total_content_size']:,} bytes")
                        print(f"  Requests/Second: {perf['requests_per_second']:.2f}")
                        
                        print(f"\nStatus Breakdown:")
                        for status, count in sorted(report['status_breakdown'].items()):
                            print(f"  {status}: {count:,}")
                        
                        if report['errors']:
                            print(f"\nErrors ({len(report['errors'])}):")
                            for error in report['errors'][:5]:
                                print(f"  {error['url']}: Status {error['response_status']}")
                    else:
                        # For other formats, just print the raw output
                        print(report)
                    
                except Exception as e:
                    self.logger.error(f"Failed to generate report: {e}")
                    return 4
            
            return 0  # Success
            
        except ImportError as e:
            self.logger.error(f"Analytics module not available: {e}")
            return 4  # Runtime error
        except Exception as e:
            self.logger.error(f"Analytics command failed: {e}")
            return 4  # Runtime error
    
    def _log_configuration_summary(self) -> None:
        """Log a summary of the loaded configuration."""
        if not self.config or not self.logger:
            return
        
        try:
            db_config = self.config.get_database_config()
            scraping_config = self.config.get_scraping_config()
            
            self.logger.info("Configuration Summary:")
            self.logger.info(f"  Database: {db_config['host']}:{db_config['port']}/{db_config['database']}")
            self.logger.info(f"  URLs configured: {len(scraping_config.get('urls', []))}")
            
            enabled_urls = [url for url in scraping_config.get('urls', []) if url.get('enabled', False)]
            self.logger.info(f"  URLs enabled: {len(enabled_urls)}")
            
            settings = scraping_config.get('settings', {})
            self.logger.info(f"  Request timeout: {settings.get('timeout', 30)}s")
            self.logger.info(f"  Retry attempts: {settings.get('retry_attempts', 3)}")
            
        except Exception as e:
            self.logger.error(f"Error logging configuration summary: {e}")


def main() -> int:
    """
    Main entry point for the web scraper application.
    
    Returns:
        Exit code indicating success (0) or failure (non-zero)
    """
    try:
        app = WebScraperApp()
        return app.run()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        return 4  # Runtime error


if __name__ == "__main__":
    sys.exit(main())
