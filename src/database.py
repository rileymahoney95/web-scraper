"""
Database management module for web scraper application.

This module provides the DatabaseManager class for handling PostgreSQL database
operations with connection pooling, transaction management, and error recovery.
"""

import logging
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Any, Optional, Tuple
import time
import hashlib
from contextlib import contextmanager
import threading
from dataclasses import dataclass


@dataclass
class ScrapedContent:
    """Data class for scraped content."""
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    content_hash: Optional[str] = None
    response_status: Optional[int] = None
    response_time_ms: Optional[int] = None
    content_length: Optional[int] = None
    last_modified: Optional[str] = None


class DatabaseManager:
    """
    Database manager with connection pooling and transaction management.
    
    This class provides robust database operations with:
    - Connection pooling for efficient resource usage
    - Transaction management with automatic rollback
    - Error recovery and reconnection handling
    - Health checks and monitoring
    - Thread-safe operations
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize DatabaseManager with configuration.
        
        Args:
            config: Database configuration dictionary containing:
                - host: Database host
                - port: Database port
                - database: Database name
                - username: Database username
                - password: Database password
                - max_connections: Maximum pool connections (default: 20)
                - min_connections: Minimum pool connections (default: 5)
                - connection_timeout: Connection timeout in seconds (default: 30)
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.connection_pool = None
        self._lock = threading.Lock()
        
        # Connection pool configuration
        self.min_connections = config.get('min_connections', 5)
        self.max_connections = config.get('max_connections', 20)
        self.connection_timeout = config.get('connection_timeout', 30)
        
        # Database connection parameters
        self.db_params = {
            'host': config['host'],
            'port': config['port'],
            'database': config['database'],
            'user': config['username'],
            'password': config['password'],
            'connect_timeout': self.connection_timeout
        }
        
        self.logger.info(f"DatabaseManager initialized for {config['host']}:{config['port']}/{config['database']}")
    
    def connect(self) -> None:
        """
        Establish database connection pool.
        
        Raises:
            psycopg2.Error: If connection cannot be established
        """
        try:
            self.logger.info("Creating database connection pool...")
            self._create_connection_pool()
            
            # Test the connection
            if self.health_check():
                self.logger.info(f"Database connection pool created successfully "
                               f"({self.min_connections}-{self.max_connections} connections)")
            else:
                raise psycopg2.Error("Database health check failed after connection")
                
        except psycopg2.Error as e:
            self.logger.error(f"Failed to create database connection pool: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during database connection: {e}")
            raise psycopg2.Error(f"Database connection failed: {e}")
    
    def disconnect(self) -> None:
        """Close all database connections and cleanup resources."""
        if self.connection_pool:
            try:
                self.logger.info("Closing database connection pool...")
                self.connection_pool.closeall()
                self.connection_pool = None
                self.logger.info("Database connection pool closed successfully")
            except Exception as e:
                self.logger.error(f"Error closing database connection pool: {e}")
        else:
            self.logger.debug("No database connection pool to close")
    
    def insert_content(self, content: ScrapedContent) -> int:
        """
        Insert scraped content into the database.
        
        Args:
            content: ScrapedContent object with the scraped data
            
        Returns:
            int: The ID of the inserted record
            
        Raises:
            psycopg2.Error: If insertion fails
        """
        query = """
        INSERT INTO scraped_content (
            url, title, content, content_hash, response_status, 
            response_time_ms, content_length, last_modified
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
        """
        
        params = (
            content.url,
            content.title,
            content.content,
            content.content_hash,
            content.response_status,
            content.response_time_ms,
            content.content_length,
            content.last_modified
        )
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    record_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    self.logger.debug(f"Inserted content for URL: {content.url}, ID: {record_id}")
                    return record_id
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to insert content for URL {content.url}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error inserting content: {e}")
            raise psycopg2.Error(f"Content insertion failed: {e}")
    
    def get_content_by_url(self, url: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve scraped content by URL.
        
        Args:
            url: The URL to search for
            limit: Maximum number of records to return
            
        Returns:
            List of dictionaries containing the scraped content
        """
        query = """
        SELECT id, url, title, content_hash, response_status, 
               response_time_ms, content_length, scraped_at, created_at
        FROM scraped_content 
        WHERE url = %s 
        ORDER BY scraped_at DESC 
        LIMIT %s
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, (url, limit))
                    results = cursor.fetchall()
                    
                    self.logger.debug(f"Retrieved {len(results)} records for URL: {url}")
                    return [dict(row) for row in results]
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to retrieve content for URL {url}: {e}")
            raise
    
    def content_exists(self, url: str, content_hash: str) -> bool:
        """
        Check if content with specific hash already exists for URL.
        
        Args:
            url: The URL to check
            content_hash: SHA-256 hash of the content
            
        Returns:
            bool: True if content exists, False otherwise
        """
        query = """
        SELECT 1 FROM scraped_content 
        WHERE url = %s AND content_hash = %s 
        LIMIT 1
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (url, content_hash))
                    result = cursor.fetchone()
                    exists = result is not None
                    
                    self.logger.debug(f"Content exists check for {url}: {exists}")
                    return exists
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to check content existence for {url}: {e}")
            raise
    
    def get_latest_content_hash(self, url: str) -> Optional[str]:
        """
        Get the most recent content hash for a URL.
        
        Args:
            url: The URL to check
            
        Returns:
            The latest content hash for the URL, or None if no content exists
        """
        query = """
        SELECT content_hash FROM scraped_content 
        WHERE url = %s 
        ORDER BY scraped_at DESC 
        LIMIT 1
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (url,))
                    result = cursor.fetchone()
                    
                    if result:
                        content_hash = result[0]
                        self.logger.debug(f"Latest content hash for {url}: {content_hash}")
                        return content_hash
                    else:
                        self.logger.debug(f"No existing content found for {url}")
                        return None
                        
        except psycopg2.Error as e:
            self.logger.error(f"Failed to get latest content hash for {url}: {e}")
            raise
    
    def insert_scraping_stats(self, session_id: str, total_urls: int, 
                            successful_scrapes: int, failed_scrapes: int,
                            total_execution_time_ms: int) -> int:
        """
        Insert scraping session statistics.
        
        Args:
            session_id: Unique identifier for the scraping session
            total_urls: Total number of URLs attempted
            successful_scrapes: Number of successful scrapes
            failed_scrapes: Number of failed scrapes
            total_execution_time_ms: Total execution time in milliseconds
            
        Returns:
            int: The ID of the inserted stats record
        """
        query = """
        INSERT INTO scraping_stats (
            scrape_session_id, total_urls, successful_scrapes, 
            failed_scrapes, total_execution_time_ms, completed_at
        ) VALUES (
            %s, %s, %s, %s, %s, NOW()
        ) RETURNING id
        """
        
        params = (session_id, total_urls, successful_scrapes, failed_scrapes, total_execution_time_ms)
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    stats_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    self.logger.info(f"Inserted scraping stats for session {session_id}, ID: {stats_id}")
                    return stats_id
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to insert scraping stats for session {session_id}: {e}")
            raise
    
    def execute_query(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute a custom SQL query.
        
        Args:
            query: SQL query string
            params: Query parameters tuple
            
        Returns:
            List of dictionaries containing query results
            
        Raises:
            psycopg2.Error: If query execution fails
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    
                    # Handle both SELECT and non-SELECT queries
                    if cursor.description:
                        results = cursor.fetchall()
                        return [dict(row) for row in results]
                    else:
                        conn.commit()
                        return []
                        
        except psycopg2.Error as e:
            self.logger.error(f"Failed to execute query: {e}")
            raise
    
    def health_check(self) -> bool:
        """
        Perform database health check.
        
        Returns:
            bool: True if database is healthy, False otherwise
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    
                    if result and result[0] == 1:
                        self.logger.debug("Database health check passed")
                        return True
                    else:
                        self.logger.warning("Database health check failed: unexpected result")
                        return False
                        
        except psycopg2.Error as e:
            self.logger.error(f"Database health check failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Database health check failed with unexpected error: {e}")
            return False
    
    def create_tables(self) -> None:
        """
        Create database tables if they don't exist.
        This method can be used for initialization without running setup.sql.
        """
        create_content_table = """
        CREATE TABLE IF NOT EXISTS scraped_content (
            id SERIAL PRIMARY KEY,
            url VARCHAR(2048) NOT NULL,
            title VARCHAR(1024),
            content TEXT,
            content_hash VARCHAR(64),
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            response_status INTEGER,
            response_time_ms INTEGER,
            content_length INTEGER,
            last_modified VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        create_stats_table = """
        CREATE TABLE IF NOT EXISTS scraping_stats (
            id SERIAL PRIMARY KEY,
            scrape_session_id VARCHAR(64),
            total_urls INTEGER,
            successful_scrapes INTEGER,
            failed_scrapes INTEGER,
            total_execution_time_ms INTEGER,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """
        
        create_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_scraped_content_url_date ON scraped_content(url, scraped_at)",
            "CREATE INDEX IF NOT EXISTS idx_scraped_content_hash ON scraped_content(content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_scraped_content_created_at ON scraped_content(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_scraping_stats_session ON scraping_stats(scrape_session_id)",
            "CREATE INDEX IF NOT EXISTS idx_scraping_stats_date ON scraping_stats(started_at)"
        ]
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Create tables
                    cursor.execute(create_content_table)
                    cursor.execute(create_stats_table)
                    
                    # Create indexes
                    for index_query in create_indexes:
                        cursor.execute(index_query)
                    
                    conn.commit()
                    self.logger.info("Database tables and indexes created successfully")
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to create database tables: {e}")
            raise
    
    def migrate_add_last_modified_column(self) -> None:
        """
        Add last_modified column to scraped_content table if it doesn't exist.
        This migration is safe to run multiple times.
        """
        migration_query = """
        ALTER TABLE scraped_content 
        ADD COLUMN IF NOT EXISTS last_modified VARCHAR(255)
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(migration_query)
                    conn.commit()
                    self.logger.info("Migration: Added last_modified column to scraped_content table")
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to run migration for last_modified column: {e}")
            raise
    
    def get_connection_pool_stats(self) -> Dict[str, Any]:
        """
        Get connection pool statistics.
        
        Returns:
            Dictionary containing pool statistics
        """
        if not self.connection_pool:
            return {"status": "disconnected", "active_connections": 0}
        
        try:
            # psycopg2.pool doesn't provide direct access to pool stats
            # so we'll provide basic information
            return {
                "status": "connected",
                "min_connections": self.min_connections,
                "max_connections": self.max_connections,
                "pool_class": self.connection_pool.__class__.__name__
            }
        except Exception as e:
            self.logger.error(f"Failed to get connection pool stats: {e}")
            return {"status": "error", "error": str(e)}
    
    def _create_connection_pool(self) -> None:
        """Create database connection pool."""
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=self.min_connections,
                maxconn=self.max_connections,
                **self.db_params
            )
            
            self.logger.debug(f"Created connection pool with {self.min_connections}-{self.max_connections} connections")
            
        except psycopg2.Error as e:
            self.logger.error(f"Failed to create connection pool: {e}")
            raise
    
    @contextmanager
    def _get_connection(self):
        """
        Context manager for getting database connections from the pool.
        
        Yields:
            psycopg2.connection: Database connection
            
        Raises:
            psycopg2.Error: If connection cannot be obtained
        """
        if not self.connection_pool:
            raise psycopg2.Error("Database connection pool not initialized")
        
        connection = None
        try:
            # Get connection from pool with timeout
            connection = self.connection_pool.getconn()
            if connection is None:
                raise psycopg2.Error("Could not get connection from pool")
            
            # Test connection is still valid
            if connection.closed:
                raise psycopg2.Error("Database connection is closed")
            yield connection
            
        except psycopg2.Error as e:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass  # Ignore rollback errors
            raise
        except Exception as e:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass  # Ignore rollback errors
            raise psycopg2.Error(f"Database operation failed: {e}")
        finally:
            if connection:
                try:
                    self.connection_pool.putconn(connection)
                except Exception as e:
                    self.logger.error(f"Failed to return connection to pool: {e}")


def calculate_content_hash(content: str) -> str:
    """
    Calculate SHA-256 hash of content for duplicate detection.
    
    Args:
        content: Content string to hash
        
    Returns:
        str: SHA-256 hash in hexadecimal format
    """
    if not content:
        return ""
    
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


# Example usage and testing functions
if __name__ == "__main__":
    # This section is for testing purposes
    import sys
    
    # Example configuration for testing
    test_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'web_scraper',
        'username': 'scraper_user',
        'password': 'secure_password',
        'max_connections': 10,
        'min_connections': 2
    }
    
    # Basic logging setup for testing
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Initialize database manager
        db_manager = DatabaseManager(test_config)
        
        # Test connection
        db_manager.connect()
        
        # Test health check
        if db_manager.health_check():
            print("Database connection successful!")
        else:
            print("Database health check failed!")
            
        # Test content insertion
        test_content = ScrapedContent(
            url="https://example.com",
            title="Example Title",
            content="Example content for testing",
            content_hash=calculate_content_hash("Example content for testing"),
            response_status=200,
            response_time_ms=150,
            content_length=25
        )
        
        content_id = db_manager.insert_content(test_content)
        print(f"Inserted test content with ID: {content_id}")
        
        # Test content retrieval
        retrieved_content = db_manager.get_content_by_url("https://example.com")
        print(f"Retrieved {len(retrieved_content)} records for test URL")
        
        # Test connection pool stats
        stats = db_manager.get_connection_pool_stats()
        print(f"Connection pool stats: {stats}")
        
        # Cleanup
        db_manager.disconnect()
        print("Database manager testing completed successfully!")
        
    except Exception as e:
        print(f"Database manager testing failed: {e}")
        sys.exit(1)
