"""
Tests for advanced database query operations.

This module contains comprehensive tests for the DatabaseAnalytics and
DatabaseBulkOps classes, covering analytics, reporting, search functionality,
and bulk operations.
"""

import unittest
import logging
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import psycopg2
from typing import Dict, Any

# Add src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import DatabaseManager, ScrapedContent, calculate_content_hash
from database_queries import (
    DatabaseAnalytics, DatabaseBulkOps, ContentStatistics, 
    TrendAnalysis, SearchResult
)


class TestDatabaseAnalytics(unittest.TestCase):
    """Test analytics and reporting functionality."""
    
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
    
    def setUp(self):
        """Set up each test."""
        # Initialize database manager
        self.db_manager = DatabaseManager(self.test_config)
        
        # Try to connect - if this fails, skip the test
        try:
            self.db_manager.connect()
            self.db_manager.create_tables()  # Ensure tables exist
            self.analytics = DatabaseAnalytics(self.db_manager)
            self.bulk_ops = DatabaseBulkOps(self.db_manager)
        except psycopg2.Error as e:
            self.skipTest(f"Cannot connect to test database: {e}")
        
        # Insert test data
        self._insert_test_data()
    
    def tearDown(self):
        """Clean up after each test."""
        if self.db_manager:
            try:
                # Clean up test data
                self.db_manager.execute_query("DELETE FROM scraped_content WHERE url LIKE 'https://test-analytics-%'")
                self.db_manager.execute_query("DELETE FROM scraping_stats WHERE scrape_session_id LIKE 'test-analytics-%'")
                self.db_manager.disconnect()
            except Exception as e:
                print(f"Error during cleanup: {e}")
    
    def _insert_test_data(self):
        """Insert test data for analytics tests."""
        # Create test content with various scenarios
        test_content = [
            # Successful scrapes
            ScrapedContent(
                url="https://test-analytics-success-1.com",
                title="Success Test 1",
                content="Content for successful test 1",
                content_hash=calculate_content_hash("Content for successful test 1"),
                response_status=200,
                response_time_ms=100,
                content_length=30
            ),
            ScrapedContent(
                url="https://test-analytics-success-2.com",
                title="Success Test 2",
                content="Content for successful test 2",
                content_hash=calculate_content_hash("Content for successful test 2"),
                response_status=200,
                response_time_ms=150,
                content_length=40
            ),
            # Error cases
            ScrapedContent(
                url="https://test-analytics-error-1.com",
                title=None,
                content=None,
                content_hash=None,
                response_status=404,
                response_time_ms=50,
                content_length=0
            ),
            ScrapedContent(
                url="https://test-analytics-error-2.com",
                title=None,
                content=None,
                content_hash=None,
                response_status=500,
                response_time_ms=75,
                content_length=0
            ),
            # Content changes (same URL, different content)
            ScrapedContent(
                url="https://test-analytics-change.com",
                title="Changed Content V1",
                content="Original content",
                content_hash=calculate_content_hash("Original content"),
                response_status=200,
                response_time_ms=120,
                content_length=20
            )
        ]
        
        # Insert test content
        for content in test_content:
            self.db_manager.insert_content(content)
        
        # Insert a changed version of the last URL (simulating content change)
        import time
        time.sleep(0.1)  # Ensure different timestamp
        changed_content = ScrapedContent(
            url="https://test-analytics-change.com",
            title="Changed Content V2",
            content="Updated content",
            content_hash=calculate_content_hash("Updated content"),
            response_status=200,
            response_time_ms=130,
            content_length=25
        )
        self.db_manager.insert_content(changed_content)
        
        # Insert test scraping stats
        self.db_manager.insert_scraping_stats(
            session_id="test-analytics-session-1",
            total_urls=6,
            successful_scrapes=4,
            failed_scrapes=2,
            total_execution_time_ms=5000
        )
    
    def test_content_statistics(self):
        """Test content statistics generation."""
        stats = self.analytics.get_content_statistics()
        
        # Verify stats object structure
        self.assertIsInstance(stats, ContentStatistics)
        self.assertIsInstance(stats.total_content, int)
        self.assertIsInstance(stats.unique_urls, int)
        self.assertIsInstance(stats.status_distribution, dict)
        self.assertIsInstance(stats.avg_response_time_ms, float)
        self.assertIsInstance(stats.success_rate, float)
        self.assertIsInstance(stats.error_rate, float)
        
        # Verify we have test data
        self.assertGreater(stats.total_content, 0)
        self.assertGreater(stats.unique_urls, 0)
        
        # Verify status distribution includes our test statuses
        self.assertIn(200, stats.status_distribution)
        self.assertIn(404, stats.status_distribution)
        self.assertIn(500, stats.status_distribution)
        
        # Verify success/error rates are calculated
        self.assertGreaterEqual(stats.success_rate, 0)
        self.assertLessEqual(stats.success_rate, 100)
        self.assertGreaterEqual(stats.error_rate, 0)
        self.assertLessEqual(stats.error_rate, 100)
        
        # Verify lists are populated
        self.assertIsInstance(stats.most_scraped_urls, list)
        self.assertIsInstance(stats.content_by_day, dict)
    
    def test_content_statistics_with_date_range(self):
        """Test content statistics with specific date range."""
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=1)
        
        stats = self.analytics.get_content_statistics(start_date=start_date, end_date=end_date)
        
        # Should have our test data since it was just inserted
        self.assertGreater(stats.total_content, 0)
        
        # Test with date range that should exclude our data
        old_end_date = datetime.now() - timedelta(days=2)
        old_start_date = old_end_date - timedelta(hours=1)
        
        old_stats = self.analytics.get_content_statistics(start_date=old_start_date, end_date=old_end_date)
        self.assertEqual(old_stats.total_content, 0)
    
    def test_scraping_trends(self):
        """Test trend analysis over time."""
        trends = self.analytics.get_scraping_trends(days=1)
        
        # Verify trends object structure
        self.assertIsInstance(trends, TrendAnalysis)
        self.assertEqual(trends.period_days, 1)
        self.assertIsInstance(trends.success_rate_trend, list)
        self.assertIsInstance(trends.response_time_trend, list)
        self.assertIsInstance(trends.content_change_frequency, dict)
        self.assertIsInstance(trends.error_patterns, list)
        self.assertIsInstance(trends.volume_trend, list)
        
        # Verify trend data is populated (should have today's data)
        if trends.success_rate_trend:
            trend_day = trends.success_rate_trend[0]
            self.assertIn('date', trend_day)
            self.assertIn('total_requests', trend_day)
            self.assertIn('successful_requests', trend_day)
            self.assertIn('success_rate', trend_day)
        
        # Verify content change frequency has expected categories
        expected_categories = ['No Changes', 'Rarely Changes', 'Sometimes Changes', 'Frequently Changes']
        for category in trends.content_change_frequency.keys():
            self.assertIn(category, expected_categories)
    
    def test_advanced_search(self):
        """Test advanced content search functionality."""
        # Test basic text search
        search_results = self.analytics.search_content(query="success", limit=10)
        
        self.assertIsInstance(search_results, SearchResult)
        self.assertIsInstance(search_results.total_matches, int)
        self.assertIsInstance(search_results.results, list)
        self.assertIsInstance(search_results.facets, dict)
        self.assertIsInstance(search_results.query_time_ms, float)
        
        # Should find our test content with "success" in the title
        self.assertGreater(search_results.total_matches, 0)
        
        # Verify result structure
        if search_results.results:
            result = search_results.results[0]
            required_fields = ['id', 'url', 'title', 'response_status', 'scraped_at']
            for field in required_fields:
                self.assertIn(field, result)
        
        # Verify facets are populated
        self.assertIn('status_codes', search_results.facets)
        self.assertIn('months', search_results.facets)
        self.assertIn('content_sizes', search_results.facets)
    
    def test_search_with_filters(self):
        """Test search with various filters."""
        # Test status code filter
        filters = {
            'status_codes': [200]
        }
        search_results = self.analytics.search_content(filters=filters, limit=10)
        
        # All results should have status 200
        for result in search_results.results:
            self.assertEqual(result['response_status'], 200)
        
        # Test URL pattern filter
        filters = {
            'urls': ['test-analytics-success']
        }
        search_results = self.analytics.search_content(filters=filters, limit=10)
        
        # All results should match the URL pattern
        for result in search_results.results:
            self.assertIn('test-analytics-success', result['url'])
        
        # Test date range filter
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=1)
        filters = {
            'start_date': start_date,
            'end_date': end_date
        }
        search_results = self.analytics.search_content(filters=filters, limit=10)
        
        # Should have results from our recent test data
        self.assertGreater(search_results.total_matches, 0)
    
    def test_search_pagination(self):
        """Test search pagination."""
        # Get first page
        page1 = self.analytics.search_content(limit=2, offset=0)
        
        # Get second page
        page2 = self.analytics.search_content(limit=2, offset=2)
        
        # Pages should have different results
        if page1.results and page2.results:
            page1_ids = {result['id'] for result in page1.results}
            page2_ids = {result['id'] for result in page2.results}
            self.assertNotEqual(page1_ids, page2_ids)
    
    def test_scraping_report_generation(self):
        """Test report generation in different formats."""
        # Test dict format (default)
        report = self.analytics.generate_scraping_report(
            session_id="test-analytics-session-1",
            format='dict'
        )
        
        self.assertIsInstance(report, dict)
        
        # Verify report structure
        required_sections = ['session_info', 'summary', 'performance_metrics', 'status_breakdown', 'url_details']
        for section in required_sections:
            self.assertIn(section, report)
        
        # Verify summary data
        summary = report['summary']
        self.assertEqual(summary['session_id'], 'test-analytics-session-1')
        self.assertEqual(summary['total_urls'], 6)
        self.assertEqual(summary['successful_scrapes'], 4)
        self.assertEqual(summary['failed_scrapes'], 2)
        
        # Test JSON format
        json_report = self.analytics.generate_scraping_report(
            session_id="test-analytics-session-1",
            format='json'
        )
        self.assertIsInstance(json_report, str)
        
        # Should be valid JSON
        import json
        parsed_json = json.loads(json_report)
        self.assertIsInstance(parsed_json, dict)
        
        # Test CSV format
        csv_report = self.analytics.generate_scraping_report(
            session_id="test-analytics-session-1",
            format='csv'
        )
        self.assertIsInstance(csv_report, str)
        self.assertIn('Session ID', csv_report)
        self.assertIn('URL Details', csv_report)
        
        # Test HTML format
        html_report = self.analytics.generate_scraping_report(
            session_id="test-analytics-session-1",
            format='html'
        )
        self.assertIsInstance(html_report, str)
        self.assertIn('<html>', html_report)
        self.assertIn('Session Summary', html_report)
    
    def test_report_latest_session(self):
        """Test report generation for latest session (no session_id specified)."""
        report = self.analytics.generate_scraping_report()
        
        self.assertIsInstance(report, dict)
        self.assertIn('session_info', report)
        self.assertIn('summary', report)
        
        # Should use the latest session we created
        self.assertEqual(report['summary']['session_id'], 'test-analytics-session-1')


class TestDatabaseBulkOps(unittest.TestCase):
    """Test bulk database operations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
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
    
    def setUp(self):
        """Set up each test."""
        # Initialize database manager
        self.db_manager = DatabaseManager(self.test_config)
        
        # Try to connect - if this fails, skip the test
        try:
            self.db_manager.connect()
            self.db_manager.create_tables()  # Ensure tables exist
            self.bulk_ops = DatabaseBulkOps(self.db_manager)
        except psycopg2.Error as e:
            self.skipTest(f"Cannot connect to test database: {e}")
    
    def tearDown(self):
        """Clean up after each test."""
        if self.db_manager:
            try:
                # Clean up test data
                self.db_manager.execute_query("DELETE FROM scraped_content WHERE url LIKE 'https://test-bulk-%'")
                self.db_manager.disconnect()
            except Exception as e:
                print(f"Error during cleanup: {e}")
    
    def test_bulk_insert_content(self):
        """Test bulk insertion of content."""
        # Prepare test data
        test_content = []
        for i in range(10):
            content_text = f"Bulk test content {i}"
            test_content.append({
                'url': f'https://test-bulk-insert-{i}.com',
                'title': f'Bulk Test {i}',
                'content': content_text,
                'content_hash': calculate_content_hash(content_text),
                'response_status': 200,
                'response_time_ms': 100 + i * 10,
                'content_length': len(content_text),
                'last_modified': 'Wed, 21 Oct 2015 07:28:00 GMT'
            })
        
        # Test bulk insert
        inserted_count = self.bulk_ops.bulk_insert_content(test_content, batch_size=5)
        
        self.assertEqual(inserted_count, 10)
        
        # Verify data was inserted
        for i in range(10):
            results = self.db_manager.get_content_by_url(f'https://test-bulk-insert-{i}.com')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['title'], f'Bulk Test {i}')
    
    def test_bulk_insert_empty_list(self):
        """Test bulk insert with empty list."""
        inserted_count = self.bulk_ops.bulk_insert_content([])
        self.assertEqual(inserted_count, 0)
    
    def test_bulk_insert_large_batch(self):
        """Test bulk insert with larger dataset."""
        # Create larger test dataset
        test_content = []
        for i in range(1500):  # Larger than default batch size
            content_text = f"Large bulk test content {i}"
            test_content.append({
                'url': f'https://test-bulk-large-{i}.com',
                'title': f'Large Bulk Test {i}',
                'content': content_text,
                'content_hash': calculate_content_hash(content_text),
                'response_status': 200,
                'response_time_ms': 100,
                'content_length': len(content_text)
            })
        
        # Test with custom batch size
        inserted_count = self.bulk_ops.bulk_insert_content(test_content, batch_size=500)
        
        self.assertEqual(inserted_count, 1500)
        
        # Verify a few random records
        test_indices = [0, 500, 1000, 1499]
        for i in test_indices:
            results = self.db_manager.get_content_by_url(f'https://test-bulk-large-{i}.com')
            self.assertEqual(len(results), 1)
    
    def test_bulk_update_status(self):
        """Test bulk status updates."""
        # First, insert some test data
        test_urls = []
        for i in range(5):
            content = ScrapedContent(
                url=f"https://test-bulk-update-{i}.com",
                title=f"Update Test {i}",
                content=f"Content {i}",
                content_hash=calculate_content_hash(f"Content {i}"),
                response_status=200,
                response_time_ms=100,
                content_length=20
            )
            self.db_manager.insert_content(content)
            test_urls.append(content.url)
        
        # Prepare status updates
        url_status_map = {}
        for i, url in enumerate(test_urls):
            url_status_map[url] = 404 if i % 2 == 0 else 500
        
        # Test bulk update
        updated_count = self.bulk_ops.bulk_update_status(url_status_map)
        
        self.assertEqual(updated_count, 5)
        
        # Verify updates
        for url, expected_status in url_status_map.items():
            results = self.db_manager.get_content_by_url(url)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['response_status'], expected_status)
    
    def test_bulk_update_empty_map(self):
        """Test bulk update with empty map."""
        updated_count = self.bulk_ops.bulk_update_status({})
        self.assertEqual(updated_count, 0)
    
    def test_bulk_delete_by_criteria(self):
        """Test bulk deletion by various criteria."""
        # Insert test data with different scenarios
        now = datetime.now()
        old_date = now - timedelta(days=2)
        
        # Insert old content
        old_content = ScrapedContent(
            url="https://test-bulk-delete-old.com",
            title="Old Content",
            content="Old content to delete",
            content_hash=calculate_content_hash("Old content to delete"),
            response_status=200,
            response_time_ms=100,
            content_length=20
        )
        self.db_manager.insert_content(old_content)
        
        # Manually update the timestamp to make it old
        self.db_manager.execute_query(
            "UPDATE scraped_content SET scraped_at = %s WHERE url = %s",
            (old_date, old_content.url)
        )
        
        # Insert content with error status
        error_content = ScrapedContent(
            url="https://test-bulk-delete-error.com",
            title="Error Content",
            content=None,
            content_hash=None,
            response_status=404,
            response_time_ms=50,
            content_length=0
        )
        self.db_manager.insert_content(error_content)
        
        # Insert recent good content (should not be deleted)
        good_content = ScrapedContent(
            url="https://test-bulk-delete-keep.com",
            title="Good Content",
            content="Good content to keep",
            content_hash=calculate_content_hash("Good content to keep"),
            response_status=200,
            response_time_ms=100,
            content_length=20
        )
        self.db_manager.insert_content(good_content)
        
        # Test age-based deletion
        deleted_count = self.bulk_ops.bulk_delete_by_criteria({
            'older_than_days': 1
        })
        
        self.assertGreater(deleted_count, 0)
        
        # Verify old content was deleted
        old_results = self.db_manager.get_content_by_url(old_content.url)
        self.assertEqual(len(old_results), 0)
        
        # Verify good content was kept
        good_results = self.db_manager.get_content_by_url(good_content.url)
        self.assertEqual(len(good_results), 1)
        
        # Test status-based deletion
        deleted_count = self.bulk_ops.bulk_delete_by_criteria({
            'status_codes': [404, 500]
        })
        
        self.assertGreater(deleted_count, 0)
        
        # Verify error content was deleted
        error_results = self.db_manager.get_content_by_url(error_content.url)
        self.assertEqual(len(error_results), 0)
        
        # Test URL pattern deletion
        pattern_content = ScrapedContent(
            url="https://test-bulk-delete-pattern-match.com",
            title="Pattern Content",
            content="Pattern content",
            content_hash=calculate_content_hash("Pattern content"),
            response_status=200,
            response_time_ms=100,
            content_length=20
        )
        self.db_manager.insert_content(pattern_content)
        
        deleted_count = self.bulk_ops.bulk_delete_by_criteria({
            'url_patterns': ['pattern-match']
        })
        
        self.assertGreater(deleted_count, 0)
        
        # Verify pattern content was deleted
        pattern_results = self.db_manager.get_content_by_url(pattern_content.url)
        self.assertEqual(len(pattern_results), 0)
    
    def test_bulk_delete_no_criteria(self):
        """Test bulk delete with no criteria raises error."""
        with self.assertRaises(ValueError):
            self.bulk_ops.bulk_delete_by_criteria({})


class TestDataClasses(unittest.TestCase):
    """Test data classes used in analytics."""
    
    def test_content_statistics_dataclass(self):
        """Test ContentStatistics dataclass."""
        stats = ContentStatistics(
            total_content=100,
            unique_urls=50,
            status_distribution={200: 80, 404: 15, 500: 5},
            avg_response_time_ms=150.5,
            avg_content_length=1024,
            content_by_day={'2023-01-01': 20, '2023-01-02': 30},
            most_scraped_urls=[],
            least_scraped_urls=[],
            error_rate=20.0,
            success_rate=80.0
        )
        
        self.assertEqual(stats.total_content, 100)
        self.assertEqual(stats.unique_urls, 50)
        self.assertEqual(stats.success_rate, 80.0)
        self.assertEqual(stats.error_rate, 20.0)
        
        # Test conversion to dict
        stats_dict = asdict(stats)
        self.assertIsInstance(stats_dict, dict)
        self.assertEqual(stats_dict['total_content'], 100)
    
    def test_trend_analysis_dataclass(self):
        """Test TrendAnalysis dataclass."""
        trends = TrendAnalysis(
            period_days=30,
            success_rate_trend=[],
            response_time_trend=[],
            content_change_frequency={},
            error_patterns=[],
            volume_trend=[]
        )
        
        self.assertEqual(trends.period_days, 30)
        self.assertIsInstance(trends.success_rate_trend, list)
    
    def test_search_result_dataclass(self):
        """Test SearchResult dataclass."""
        search_result = SearchResult(
            total_matches=42,
            results=[],
            facets={},
            query_time_ms=123.45
        )
        
        self.assertEqual(search_result.total_matches, 42)
        self.assertEqual(search_result.query_time_ms, 123.45)


if __name__ == '__main__':
    # Set up test environment
    print("Starting database query operations tests...")
    print("Note: These tests require a PostgreSQL database to be running")
    print("Database configuration can be set via environment variables:")
    print("  TEST_DB_HOST, TEST_DB_PORT, TEST_DB_NAME, TEST_DB_USER, TEST_DB_PASSWORD")
    print()
    
    # Run tests
    unittest.main(verbosity=2)