#!/usr/bin/env python3
"""
Test suite for RobotChecker class and robots.txt compliance functionality.

This module provides comprehensive testing for robots.txt parsing, caching,
compliance checking, and integration with the web scraping workflow.
"""

import unittest
import time
import threading
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

# Add src directory to path for importing modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scraper import RobotChecker, RobotsError, HTTPClient, NetworkError


class TestRobotChecker(unittest.TestCase):
    """Test cases for RobotChecker class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.config = {
            'respect_robots_txt': True,
            'user_agent': 'TestBot/1.0',
            'timeout': 30,
            'retry_attempts': 3,
            'retry_delay': 1,
            'delay_between_requests': 1
        }
        
        # Create mock HTTP client
        self.mock_http_client = Mock(spec=HTTPClient)
        
        # Initialize RobotChecker
        self.robot_checker = RobotChecker(self.config, self.mock_http_client)
    
    def tearDown(self):
        """Clean up after each test method."""
        # Clear cache to avoid test interference
        self.robot_checker.clear_cache()
    
    def test_initialization(self):
        """Test RobotChecker initialization."""
        self.assertTrue(self.robot_checker.respect_robots)
        self.assertEqual(self.robot_checker.user_agent, 'TestBot/1.0')
        self.assertEqual(self.robot_checker.cache_ttl, 86400)
        self.assertEqual(len(self.robot_checker._robots_cache), 0)
    
    def test_initialization_disabled(self):
        """Test RobotChecker initialization with robots.txt disabled."""
        config = self.config.copy()
        config['respect_robots_txt'] = False
        
        robot_checker = RobotChecker(config, self.mock_http_client)
        self.assertFalse(robot_checker.respect_robots)
    
    def test_can_fetch_disabled(self):
        """Test can_fetch when robots.txt checking is disabled."""
        config = self.config.copy()
        config['respect_robots_txt'] = False
        
        robot_checker = RobotChecker(config, self.mock_http_client)
        
        # Should always return True when disabled
        self.assertTrue(robot_checker.can_fetch('https://example.com/any/path'))
    
    def test_get_crawl_delay_disabled(self):
        """Test get_crawl_delay when robots.txt checking is disabled."""
        config = self.config.copy()
        config['respect_robots_txt'] = False
        
        robot_checker = RobotChecker(config, self.mock_http_client)
        
        # Should always return 0 when disabled
        self.assertEqual(robot_checker.get_crawl_delay('https://example.com/any/path'), 0.0)
    
    def test_robots_txt_parsing_basic(self):
        """Test basic robots.txt parsing."""
        robots_content = """
User-agent: *
Disallow: /private/
Allow: /public/
Crawl-delay: 10

User-agent: GoogleBot
Disallow: /admin/
Crawl-delay: 5

Sitemap: https://example.com/sitemap.xml
"""
        
        rules = self.robot_checker._parse_robots_txt(robots_content)
        
        # Check user agents
        self.assertIn('*', rules['user_agents'])
        self.assertIn('googlebot', rules['user_agents'])
        
        # Check wildcard rules
        wildcard_rules = rules['user_agents']['*']
        self.assertIn('/private/', wildcard_rules['disallow'])
        self.assertIn('/public/', wildcard_rules['allow'])
        self.assertEqual(wildcard_rules['crawl_delay'], 10.0)
        
        # Check GoogleBot rules
        googlebot_rules = rules['user_agents']['googlebot']
        self.assertIn('/admin/', googlebot_rules['disallow'])
        self.assertEqual(googlebot_rules['crawl_delay'], 5.0)
        
        # Check sitemaps
        self.assertIn('https://example.com/sitemap.xml', rules['sitemaps'])
    
    def test_robots_txt_parsing_comments(self):
        """Test robots.txt parsing with comments."""
        robots_content = """
# This is a comment
User-agent: * # Another comment
Disallow: /private/ # Disallow private area
# More comments
Allow: /public/
"""
        
        rules = self.robot_checker._parse_robots_txt(robots_content)
        
        wildcard_rules = rules['user_agents']['*']
        self.assertIn('/private/', wildcard_rules['disallow'])
        self.assertIn('/public/', wildcard_rules['allow'])
    
    def test_robots_txt_parsing_malformed(self):
        """Test robots.txt parsing with malformed content."""
        robots_content = """
User-agent: *
Disallow /missing/colon
Invalid line without colon
Crawl-delay: invalid_number
: empty_directive
"""
        
        # Should not raise exception
        rules = self.robot_checker._parse_robots_txt(robots_content)
        
        # Should have basic structure even with malformed content
        self.assertIn('user_agents', rules)
        self.assertIn('sitemaps', rules)
    
    def test_path_matching_basic(self):
        """Test basic path matching against robots.txt patterns."""
        # Exact match
        self.assertTrue(self.robot_checker._path_matches_pattern('/admin/', '/admin/'))
        self.assertFalse(self.robot_checker._path_matches_pattern('/public/', '/admin/'))
        
        # Prefix match
        self.assertTrue(self.robot_checker._path_matches_pattern('/admin/users', '/admin/'))
        self.assertTrue(self.robot_checker._path_matches_pattern('/admin/', '/admin/'))
        
        # Wildcard matching
        self.assertTrue(self.robot_checker._path_matches_pattern('/admin/users.html', '/admin/*.html'))
        self.assertTrue(self.robot_checker._path_matches_pattern('/images/photo.jpg', '/images/*'))
        self.assertFalse(self.robot_checker._path_matches_pattern('/admin/users.txt', '/admin/*.html'))
    
    def test_path_matching_advanced(self):
        """Test advanced path matching scenarios."""
        # End anchor
        self.assertTrue(self.robot_checker._path_matches_pattern('/page$', '/page$'))
        self.assertFalse(self.robot_checker._path_matches_pattern('/page.html', '/page$'))
        
        # Complex patterns
        self.assertTrue(self.robot_checker._path_matches_pattern('/api/v1/users', '/api/*/users'))
        self.assertTrue(self.robot_checker._path_matches_pattern('/search?q=test', '/search'))
    
    def test_check_path_allowed_wildcard(self):
        """Test path checking with wildcard user agent rules."""
        robots_rules = {
            'user_agents': {
                '*': {
                    'disallow': ['/private/', '/admin/'],
                    'allow': ['/admin/public/'],
                    'crawl_delay': None
                }
            },
            'sitemaps': []
        }
        
        # Allow rules take precedence
        self.assertTrue(self.robot_checker._check_path_allowed('/admin/public/page.html', 'TestBot/1.0', robots_rules))
        
        # Disallow rules
        self.assertFalse(self.robot_checker._check_path_allowed('/private/secret.html', 'TestBot/1.0', robots_rules))
        self.assertFalse(self.robot_checker._check_path_allowed('/admin/users.html', 'TestBot/1.0', robots_rules))
        
        # Allowed paths
        self.assertTrue(self.robot_checker._check_path_allowed('/public/page.html', 'TestBot/1.0', robots_rules))
        self.assertTrue(self.robot_checker._check_path_allowed('/', 'TestBot/1.0', robots_rules))
    
    def test_check_path_allowed_specific_user_agent(self):
        """Test path checking with specific user agent rules."""
        robots_rules = {
            'user_agents': {
                '*': {
                    'disallow': ['/'],
                    'allow': [],
                    'crawl_delay': None
                },
                'testbot': {
                    'disallow': ['/private/'],
                    'allow': ['/public/'],
                    'crawl_delay': None
                }
            },
            'sitemaps': []
        }
        
        # Specific user agent rules should override wildcard
        self.assertTrue(self.robot_checker._check_path_allowed('/public/page.html', 'TestBot/1.0', robots_rules))
        self.assertFalse(self.robot_checker._check_path_allowed('/private/secret.html', 'TestBot/1.0', robots_rules))
        
        # Different user agent should use wildcard rules
        self.assertFalse(self.robot_checker._check_path_allowed('/public/page.html', 'OtherBot/1.0', robots_rules))
    
    def test_get_crawl_delay_for_agent(self):
        """Test crawl delay extraction for specific user agents."""
        robots_rules = {
            'user_agents': {
                '*': {
                    'disallow': [],
                    'allow': [],
                    'crawl_delay': 10.0
                },
                'testbot': {
                    'disallow': [],
                    'allow': [],
                    'crawl_delay': 5.0
                }
            },
            'sitemaps': []
        }
        
        # Specific user agent delay
        self.assertEqual(self.robot_checker._get_crawl_delay_for_agent('TestBot/1.0', robots_rules), 5.0)
        
        # Wildcard delay for unknown user agent
        self.assertEqual(self.robot_checker._get_crawl_delay_for_agent('OtherBot/1.0', robots_rules), 10.0)
        
        # No delay specified
        robots_rules['user_agents']['*']['crawl_delay'] = None
        robots_rules['user_agents']['testbot']['crawl_delay'] = None
        self.assertEqual(self.robot_checker._get_crawl_delay_for_agent('TestBot/1.0', robots_rules), 0.0)
    
    def test_cache_functionality(self):
        """Test robots.txt caching functionality."""
        # Mock successful robots.txt fetch
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /private/"
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        
        # First call should fetch from server
        rules1 = self.robot_checker._get_robots_rules('https://example.com')
        self.mock_http_client.fetch_url.assert_called_once_with('https://example.com/robots.txt')
        
        # Second call should use cache
        self.mock_http_client.fetch_url.reset_mock()
        rules2 = self.robot_checker._get_robots_rules('https://example.com')
        self.mock_http_client.fetch_url.assert_not_called()
        
        # Rules should be the same
        self.assertEqual(rules1, rules2)
    
    def test_cache_expiration(self):
        """Test robots.txt cache expiration."""
        # Mock successful robots.txt fetch
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /private/"
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        
        # Set very short TTL for testing
        self.robot_checker.cache_ttl = 0.1  # 100ms
        
        # First call
        self.robot_checker._get_robots_rules('https://example.com')
        
        # Wait for cache to expire
        time.sleep(0.15)
        
        # Second call should fetch again
        self.mock_http_client.fetch_url.reset_mock()
        self.robot_checker._get_robots_rules('https://example.com')
        self.mock_http_client.fetch_url.assert_called_once()
    
    def test_cache_key_generation(self):
        """Test cache key generation for different URLs."""
        # Same domain should have same cache key
        key1 = self.robot_checker._get_cache_key('https://example.com')
        key2 = self.robot_checker._get_cache_key('https://example.com/path')
        key3 = self.robot_checker._get_cache_key('https://example.com:443')
        
        self.assertEqual(key1, 'https://example.com')
        self.assertEqual(key1, key2)
        
        # Different domains should have different cache keys
        key4 = self.robot_checker._get_cache_key('https://other.com')
        self.assertNotEqual(key1, key4)
        
        # Different schemes should have different cache keys
        key5 = self.robot_checker._get_cache_key('http://example.com')
        self.assertNotEqual(key1, key5)
    
    def test_fetch_robots_txt_success(self):
        """Test successful robots.txt fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /private/"
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        
        content = self.robot_checker._fetch_robots_txt('https://example.com')
        self.assertEqual(content, "User-agent: *\nDisallow: /private/")
        self.mock_http_client.fetch_url.assert_called_once_with('https://example.com/robots.txt')
    
    def test_fetch_robots_txt_not_found(self):
        """Test robots.txt fetching when file not found."""
        # Mock 404 response
        self.mock_http_client.fetch_url.side_effect = NetworkError("HTTP 404 error", status_code=404)
        
        content = self.robot_checker._fetch_robots_txt('https://example.com')
        self.assertIsNone(content)
    
    def test_fetch_robots_txt_server_error(self):
        """Test robots.txt fetching with server error."""
        # Mock 500 response
        self.mock_http_client.fetch_url.side_effect = NetworkError("HTTP 500 error", status_code=500)
        
        content = self.robot_checker._fetch_robots_txt('https://example.com')
        self.assertIsNone(content)
    
    def test_fetch_robots_txt_network_error(self):
        """Test robots.txt fetching with network error."""
        # Mock network error
        self.mock_http_client.fetch_url.side_effect = NetworkError("Connection timeout")
        
        content = self.robot_checker._fetch_robots_txt('https://example.com')
        self.assertIsNone(content)
    
    def test_can_fetch_no_robots_txt(self):
        """Test can_fetch when no robots.txt is available."""
        # Mock 404 response
        self.mock_http_client.fetch_url.side_effect = NetworkError("HTTP 404 error", status_code=404)
        
        # Should allow access when no robots.txt found
        self.assertTrue(self.robot_checker.can_fetch('https://example.com/any/path'))
    
    def test_can_fetch_with_robots_txt(self):
        """Test can_fetch with actual robots.txt rules."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
User-agent: *
Disallow: /private/
Allow: /public/

User-agent: TestBot
Disallow: /admin/
"""
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        
        # Test specific user agent rules (TestBot/1.0 matches TestBot)
        # TestBot only disallows /admin/, so /private/ should be allowed
        self.assertTrue(self.robot_checker.can_fetch('https://example.com/private/secret.html'))
        self.assertTrue(self.robot_checker.can_fetch('https://example.com/public/page.html'))
        self.assertFalse(self.robot_checker.can_fetch('https://example.com/admin/users.html'))
        self.assertTrue(self.robot_checker.can_fetch('https://example.com/other/page.html'))
        
        # Test with a different user agent that should use wildcard rules
        self.assertFalse(self.robot_checker.can_fetch('https://example.com/private/secret.html', 'OtherBot/1.0'))
        self.assertTrue(self.robot_checker.can_fetch('https://example.com/public/page.html', 'OtherBot/1.0'))
    
    def test_get_crawl_delay_with_robots_txt(self):
        """Test get_crawl_delay with actual robots.txt rules."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
User-agent: *
Crawl-delay: 10

User-agent: TestBot
Crawl-delay: 5
"""
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        
        # Test specific user agent delay
        delay = self.robot_checker.get_crawl_delay('https://example.com/any/path')
        self.assertEqual(delay, 5.0)
        
        # Test with different user agent
        delay = self.robot_checker.get_crawl_delay('https://example.com/any/path', 'OtherBot/1.0')
        self.assertEqual(delay, 10.0)
    
    def test_error_handling_in_can_fetch(self):
        """Test error handling in can_fetch method."""
        # Mock exception during processing
        self.mock_http_client.fetch_url.side_effect = Exception("Unexpected error")
        
        # Should return True (allow access) on errors
        self.assertTrue(self.robot_checker.can_fetch('https://example.com/any/path'))
    
    def test_error_handling_in_get_crawl_delay(self):
        """Test error handling in get_crawl_delay method."""
        # Mock exception during processing
        self.mock_http_client.fetch_url.side_effect = Exception("Unexpected error")
        
        # Should return 0.0 on errors
        self.assertEqual(self.robot_checker.get_crawl_delay('https://example.com/any/path'), 0.0)
    
    def test_cache_stats(self):
        """Test cache statistics functionality."""
        # Initially empty cache
        stats = self.robot_checker.get_cache_stats()
        self.assertEqual(stats['total_entries'], 0)
        self.assertEqual(stats['valid_entries'], 0)
        self.assertEqual(stats['expired_entries'], 0)
        
        # Add some cache entries
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /"
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        
        # Cache some robots.txt
        self.robot_checker._get_robots_rules('https://example.com')
        self.robot_checker._get_robots_rules('https://other.com')
        
        stats = self.robot_checker.get_cache_stats()
        self.assertEqual(stats['total_entries'], 2)
        self.assertEqual(stats['valid_entries'], 2)
        self.assertEqual(stats['expired_entries'], 0)
    
    def test_clear_cache(self):
        """Test cache clearing functionality."""
        # Add cache entry
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /"
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        self.robot_checker._get_robots_rules('https://example.com')
        
        # Verify cache has content
        self.assertEqual(len(self.robot_checker._robots_cache), 1)
        
        # Clear cache
        self.robot_checker.clear_cache()
        
        # Verify cache is empty
        self.assertEqual(len(self.robot_checker._robots_cache), 0)
    
    def test_thread_safety(self):
        """Test thread safety of cache operations."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /"
        
        self.mock_http_client.fetch_url.return_value = (mock_response, Mock())
        
        def fetch_robots():
            for _ in range(10):
                self.robot_checker._get_robots_rules('https://example.com')
        
        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=fetch_robots)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have only one cache entry despite multiple threads
        self.assertEqual(len(self.robot_checker._robots_cache), 1)


class TestRobotCheckerIntegration(unittest.TestCase):
    """Integration tests for RobotChecker with WebScraper."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'respect_robots_txt': True,
            'user_agent': 'TestBot/1.0',
            'timeout': 30,
            'retry_attempts': 3,
            'retry_delay': 1,
            'delay_between_requests': 1
        }
    
    def test_robots_error_exception(self):
        """Test RobotsError exception functionality."""
        url = 'https://example.com/private/'
        robots_url = 'https://example.com/robots.txt'
        
        error = RobotsError("Access denied", url, robots_url)
        
        self.assertEqual(str(error), "Access denied")
        self.assertEqual(error.url, url)
        self.assertEqual(error.robots_url, robots_url)
        self.assertIsNotNone(error.timestamp)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)