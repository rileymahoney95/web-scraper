"""
Integration tests for database infrastructure.

This module contains integration tests for the DatabaseManager class and 
related database operations. These tests require a PostgreSQL database
to be running and accessible.
"""

import unittest
import logging
import os
import sys
from unittest.mock import patch, MagicMock
import psycopg2
from typing import Dict, Any

# Add src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import DatabaseManager, ScrapedContent, calculate_content_hash


class TestDatabaseIntegration(unittest.TestCase):
    """Integration tests for DatabaseManager class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        # Configure logging for tests
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Test database configuration
        cls.test_config = {
            'host': os.getenv('TEST_DB_HOST', 'localhost'),
            'port': int(os.getenv('TEST_DB_PORT', '5432')),
            'database': os.getenv('TEST_DB_NAME', 'web_scraper_test'),
            'username': os.getenv('TEST_DB_USER', 'scraper_user'),
            'password': os.getenv('TEST_DB_PASSWORD', 'secure_password'),
            'max_connections': 5,
            'min_connections': 2,
            'connection_timeout': 10
        }
        
        cls.db_manager = None
    
    def setUp(self):
        """Set up each test."""
        # Initialize database manager
        self.db_manager = DatabaseManager(self.test_config)
        
        # Try to connect - if this fails, skip the test
        try:
            self.db_manager.connect()
            self.db_manager.create_tables()  # Ensure tables exist
        except psycopg2.Error as e:
            self.skipTest(f"Cannot connect to test database: {e}")
    
    def tearDown(self):
        """Clean up after each test."""
        if self.db_manager:
            try:
                # Clean up test data
                self.db_manager.execute_query("DELETE FROM scraped_content WHERE url LIKE 'https://test-%'")
                self.db_manager.execute_query("DELETE FROM scraping_stats WHERE scrape_session_id LIKE 'test-%'")
                self.db_manager.disconnect()
            except Exception as e:
                print(f"Error during cleanup: {e}")
    
    def test_database_connection(self):
        """Test database connection and health check."""
        # Test connection is established
        self.assertIsNotNone(self.db_manager.connection_pool)
        
        # Test health check
        self.assertTrue(self.db_manager.health_check())
        
        # Test connection pool stats
        stats = self.db_manager.get_connection_pool_stats()
        self.assertEqual(stats['status'], 'connected')
        self.assertEqual(stats['min_connections'], 2)
        self.assertEqual(stats['max_connections'], 5)
    
    def test_content_insertion_and_retrieval(self):
        """Test inserting and retrieving scraped content."""
        # Create test content
        test_content = ScrapedContent(
            url="https://test-example.com",
            title="Test Example Title",
            content="This is test content for insertion",
            content_hash=calculate_content_hash("This is test content for insertion"),
            response_status=200,
            response_time_ms=150,
            content_length=34
        )
        
        # Insert content
        content_id = self.db_manager.insert_content(test_content)
        self.assertIsInstance(content_id, int)
        self.assertGreater(content_id, 0)
        
        # Retrieve content
        retrieved_content = self.db_manager.get_content_by_url("https://test-example.com")
        self.assertEqual(len(retrieved_content), 1)
        
        # Verify content details
        content = retrieved_content[0]
        self.assertEqual(content['url'], "https://test-example.com")
        self.assertEqual(content['title'], "Test Example Title")
        self.assertEqual(content['response_status'], 200)
        self.assertEqual(content['response_time_ms'], 150)
        self.assertEqual(content['content_length'], 34)
        self.assertIsNotNone(content['scraped_at'])
        self.assertIsNotNone(content['created_at'])
    
    def test_content_hash_and_duplicate_detection(self):
        """Test content hashing and duplicate detection."""
        test_content = "This is test content for hashing"
        content_hash = calculate_content_hash(test_content)
        
        # Verify hash format
        self.assertIsInstance(content_hash, str)
        self.assertEqual(len(content_hash), 64)  # SHA-256 hash length
        
        # Test duplicate detection
        test_url = "https://test-duplicate.com"
        
        # Initially, content should not exist
        self.assertFalse(self.db_manager.content_exists(test_url, content_hash))
        
        # Insert content
        content = ScrapedContent(
            url=test_url,
            title="Duplicate Test",
            content=test_content,
            content_hash=content_hash,
            response_status=200
        )
        
        self.db_manager.insert_content(content)
        
        # Now content should exist
        self.assertTrue(self.db_manager.content_exists(test_url, content_hash))
        
        # Different hash should not exist
        different_hash = calculate_content_hash("Different content")
        self.assertFalse(self.db_manager.content_exists(test_url, different_hash))
    
    def test_get_latest_content_hash(self):
        """Test getting the latest content hash for a URL."""
        test_url = "https://test-latest-hash.com"
        
        # Initially, no content should exist
        latest_hash = self.db_manager.get_latest_content_hash(test_url)
        self.assertIsNone(latest_hash)
        
        # Insert first content
        first_content = "First version of content"
        first_hash = calculate_content_hash(first_content)
        content1 = ScrapedContent(
            url=test_url,
            title="Test Content V1",
            content=first_content,
            content_hash=first_hash,
            response_status=200
        )
        self.db_manager.insert_content(content1)
        
        # Should return the first hash
        latest_hash = self.db_manager.get_latest_content_hash(test_url)
        self.assertEqual(latest_hash, first_hash)
        
        # Insert second content (simulating content change)
        import time
        time.sleep(0.1)  # Ensure different timestamps
        second_content = "Second version of content - updated"
        second_hash = calculate_content_hash(second_content)
        content2 = ScrapedContent(
            url=test_url,
            title="Test Content V2",
            content=second_content,
            content_hash=second_hash,
            response_status=200
        )
        self.db_manager.insert_content(content2)
        
        # Should return the latest (second) hash
        latest_hash = self.db_manager.get_latest_content_hash(test_url)
        self.assertEqual(latest_hash, second_hash)
        self.assertNotEqual(latest_hash, first_hash)
    
    def test_last_modified_storage(self):
        """Test storage and retrieval of Last-Modified headers."""
        test_url = "https://test-last-modified.com"
        test_content = "Content with Last-Modified header"
        content_hash = calculate_content_hash(test_content)
        last_modified = "Wed, 21 Oct 2015 07:28:00 GMT"
        
        # Insert content with Last-Modified header
        content = ScrapedContent(
            url=test_url,
            title="Test Last-Modified",
            content=test_content,
            content_hash=content_hash,
            response_status=200,
            last_modified=last_modified
        )
        
        content_id = self.db_manager.insert_content(content)
        self.assertIsInstance(content_id, int)
        
        # Retrieve content and verify Last-Modified header
        retrieved_content = self.db_manager.get_content_by_url(test_url, limit=1)
        self.assertEqual(len(retrieved_content), 1)
        
        # Note: get_content_by_url doesn't include last_modified in the SELECT
        # We'll test it by checking the database directly
        query = "SELECT last_modified FROM scraped_content WHERE url = %s ORDER BY scraped_at DESC LIMIT 1"
        import psycopg2.extras
        
        with self.db_manager._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (test_url,))
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                self.assertEqual(result[0], last_modified)
    
    def test_scraping_statistics(self):
        """Test scraping statistics insertion."""
        session_id = "test-session-123"
        total_urls = 10
        successful_scrapes = 8
        failed_scrapes = 2
        execution_time = 5000  # 5 seconds
        
        # Insert stats
        stats_id = self.db_manager.insert_scraping_stats(
            session_id=session_id,
            total_urls=total_urls,
            successful_scrapes=successful_scrapes,
            failed_scrapes=failed_scrapes,
            total_execution_time_ms=execution_time
        )
        
        self.assertIsInstance(stats_id, int)
        self.assertGreater(stats_id, 0)
        
        # Verify stats were inserted
        query = "SELECT * FROM scraping_stats WHERE scrape_session_id = %s"
        results = self.db_manager.execute_query(query, (session_id,))
        
        self.assertEqual(len(results), 1)
        stats = results[0]
        self.assertEqual(stats['scrape_session_id'], session_id)
        self.assertEqual(stats['total_urls'], total_urls)
        self.assertEqual(stats['successful_scrapes'], successful_scrapes)
        self.assertEqual(stats['failed_scrapes'], failed_scrapes)
        self.assertEqual(stats['total_execution_time_ms'], execution_time)
        self.assertIsNotNone(stats['started_at'])
        self.assertIsNotNone(stats['completed_at'])
    
    def test_custom_query_execution(self):
        """Test custom query execution."""
        # Test SELECT query
        results = self.db_manager.execute_query("SELECT 1 as test_value")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['test_value'], 1)
        
        # Test INSERT query with parameters
        query = """
        INSERT INTO scraped_content (url, title, content_hash, response_status)
        VALUES (%s, %s, %s, %s)
        """
        params = ("https://test-custom.com", "Custom Test", "test_hash", 200)
        
        # Should return empty list for non-SELECT queries
        results = self.db_manager.execute_query(query, params)
        self.assertEqual(len(results), 0)
        
        # Verify insertion worked
        verify_results = self.db_manager.get_content_by_url("https://test-custom.com")
        self.assertEqual(len(verify_results), 1)
        self.assertEqual(verify_results[0]['title'], "Custom Test")
    
    def test_table_creation(self):
        """Test table creation functionality."""
        # Drop and recreate tables to test creation
        try:
            self.db_manager.execute_query("DROP TABLE IF EXISTS scraped_content CASCADE")
            self.db_manager.execute_query("DROP TABLE IF EXISTS scraping_stats CASCADE")
            
            # Recreate tables
            self.db_manager.create_tables()
            
            # Test that tables exist by inserting test data
            test_content = ScrapedContent(
                url="https://test-creation.com",
                title="Table Creation Test",
                content="Test content",
                content_hash="test_hash_123",
                response_status=200
            )
            
            content_id = self.db_manager.insert_content(test_content)
            self.assertIsInstance(content_id, int)
            
        except Exception as e:
            self.fail(f"Table creation test failed: {e}")
    
    def test_error_handling(self):
        """Test error handling scenarios."""
        # Test invalid content insertion
        invalid_content = ScrapedContent(
            url="x" * 3000,  # URL too long
            title="Test",
            content="Test content"
        )
        
        with self.assertRaises(psycopg2.Error):
            self.db_manager.insert_content(invalid_content)
        
        # Test invalid query
        with self.assertRaises(psycopg2.Error):
            self.db_manager.execute_query("INVALID SQL QUERY")
    
    def test_connection_pool_management(self):
        """Test connection pool management."""
        # Test multiple concurrent operations
        import threading
        import time
        
        def concurrent_operation(thread_id):
            """Perform database operation in separate thread."""
            content = ScrapedContent(
                url=f"https://test-concurrent-{thread_id}.com",
                title=f"Concurrent Test {thread_id}",
                content=f"Content from thread {thread_id}",
                content_hash=calculate_content_hash(f"Content from thread {thread_id}"),
                response_status=200
            )
            
            self.db_manager.insert_content(content)
            
            # Verify insertion
            results = self.db_manager.get_content_by_url(f"https://test-concurrent-{thread_id}.com")
            self.assertEqual(len(results), 1)
        
        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=concurrent_operation, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all operations completed successfully
        for i in range(3):
            results = self.db_manager.get_content_by_url(f"https://test-concurrent-{i}.com")
            self.assertEqual(len(results), 1)
    
    def test_transaction_rollback(self):
        """Test transaction rollback on errors."""
        # This test simulates a transaction that should rollback
        # We'll test this by attempting an operation that will fail
        
        # Insert valid content first
        valid_content = ScrapedContent(
            url="https://test-transaction.com",
            title="Transaction Test",
            content="Valid content",
            content_hash="valid_hash",
            response_status=200
        )
        
        content_id = self.db_manager.insert_content(valid_content)
        self.assertIsInstance(content_id, int)
        
        # Verify the transaction committed properly
        results = self.db_manager.get_content_by_url("https://test-transaction.com")
        self.assertEqual(len(results), 1)
        
        # Test that failed operations don't affect database state
        with self.assertRaises(psycopg2.Error):
            invalid_content = ScrapedContent(
                url="x" * 3000,  # This should fail
                title="Should Fail",
                content="This should not be inserted"
            )
            self.db_manager.insert_content(invalid_content)
        
        # Verify original content is still there
        results = self.db_manager.get_content_by_url("https://test-transaction.com")
        self.assertEqual(len(results), 1)


class TestDatabaseUtilities(unittest.TestCase):
    """Test utility functions."""
    
    def test_content_hash_calculation(self):
        """Test content hash calculation."""
        # Test normal content
        content = "This is test content"
        hash_value = calculate_content_hash(content)
        
        self.assertIsInstance(hash_value, str)
        self.assertEqual(len(hash_value), 64)  # SHA-256 hash length
        
        # Test same content produces same hash
        hash_value2 = calculate_content_hash(content)
        self.assertEqual(hash_value, hash_value2)
        
        # Test different content produces different hash
        different_content = "This is different content"
        different_hash = calculate_content_hash(different_content)
        self.assertNotEqual(hash_value, different_hash)
        
        # Test empty content
        empty_hash = calculate_content_hash("")
        self.assertEqual(empty_hash, "")
        
        # Test None content
        none_hash = calculate_content_hash(None)
        self.assertEqual(none_hash, "")


class TestDatabaseMocking(unittest.TestCase):
    """Test database manager with mocked connections."""
    
    def test_database_manager_initialization(self):
        """Test DatabaseManager initialization without real database."""
        config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'test_db',
            'username': 'test_user',
            'password': 'test_pass'
        }
        
        db_manager = DatabaseManager(config)
        
        # Test configuration is stored correctly
        self.assertEqual(db_manager.config, config)
        self.assertEqual(db_manager.min_connections, 5)  # default
        self.assertEqual(db_manager.max_connections, 20)  # default
        self.assertEqual(db_manager.connection_timeout, 30)  # default
        
        # Test custom connection pool settings
        custom_config = config.copy()
        custom_config.update({
            'min_connections': 3,
            'max_connections': 15,
            'connection_timeout': 60
        })
        
        custom_db_manager = DatabaseManager(custom_config)
        self.assertEqual(custom_db_manager.min_connections, 3)
        self.assertEqual(custom_db_manager.max_connections, 15)
        self.assertEqual(custom_db_manager.connection_timeout, 60)


if __name__ == '__main__':
    # Set up test environment
    print("Starting database integration tests...")
    print("Note: These tests require a PostgreSQL database to be running")
    print("Database configuration can be set via environment variables:")
    print("  TEST_DB_HOST, TEST_DB_PORT, TEST_DB_NAME, TEST_DB_USER, TEST_DB_PASSWORD")
    print()
    
    # Run tests
    unittest.main(verbosity=2) 