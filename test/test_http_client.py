#!/usr/bin/env python3
"""
Unit tests for HTTPClient class.

This module contains comprehensive tests for the HTTPClient implementation
including retry logic, error handling, session management, and metrics collection.
"""

import unittest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
import requests
from requests.exceptions import Timeout, ConnectionError, HTTPError, SSLError, ChunkedEncodingError
import sys
import os

# Add src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scraper import HTTPClient, NetworkError, ScrapingError, RequestMetrics


class TestHTTPClient(unittest.TestCase):
    """Test cases for HTTPClient class."""
    
    def setUp(self):
        """Set up test environment."""
        # Test configuration
        self.test_config = {
            'timeout': 10,
            'retry_attempts': 2,
            'retry_delay': 0.1,  # Short delay for testing
            'user_agent': 'TestScraper/1.0',
            'delay_between_requests': 0  # No delay for testing
        }
        
        self.client = HTTPClient(self.test_config)
    
    def tearDown(self):
        """Clean up after tests."""
        self.client.close()
    
    def test_client_initialization(self):
        """Test HTTPClient initialization with configuration."""
        self.assertEqual(self.client.timeout, 10)
        self.assertEqual(self.client.max_retries, 2)
        self.assertEqual(self.client.base_retry_delay, 0.1)
        self.assertEqual(self.client.user_agent, 'TestScraper/1.0')
        self.assertEqual(self.client.request_delay, 0)
        
        # Test statistics
        stats = self.client.get_statistics()
        self.assertEqual(stats['total_requests'], 0)
        self.assertEqual(stats['successful_requests'], 0)
        self.assertEqual(stats['failed_requests'], 0)
        self.assertEqual(stats['success_rate_percent'], 0)
    
    @patch('requests.Session.get')
    def test_successful_request(self, mock_get):
        """Test successful HTTP request handling."""
        # Add a small delay to ensure response time > 0
        def slow_response(*args, **kwargs):
            time.sleep(0.001)  # 1ms delay
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'Test content'
            mock_response.url = 'https://example.com'
            return mock_response
        
        mock_get.side_effect = slow_response
        
        # Make request
        response, metrics = self.client.fetch_url('https://example.com')
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'Test content')
        
        # Verify metrics
        self.assertEqual(metrics.url, 'https://example.com')
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.content_length, 12)
        self.assertEqual(metrics.attempt_number, 1)
        self.assertEqual(metrics.final_url, 'https://example.com')
        self.assertIsNone(metrics.error)
        self.assertGreaterEqual(metrics.response_time_ms, 1)
        
        # Verify statistics
        stats = self.client.get_statistics()
        self.assertEqual(stats['total_requests'], 1)
        self.assertEqual(stats['successful_requests'], 1)
        self.assertEqual(stats['failed_requests'], 0)
        self.assertEqual(stats['success_rate_percent'], 100.0)
        
        # Verify session.get was called with correct parameters
        mock_get.assert_called_once_with('https://example.com', timeout=10)
    
    @patch('requests.Session.get')
    def test_http_error_no_retry(self, mock_get):
        """Test HTTP 4xx errors that should not be retried."""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.content = b'Not Found'
        mock_response.url = 'https://example.com/missing'
        mock_get.return_value = mock_response
        
        # Request should fail with NetworkError
        with self.assertRaises(NetworkError) as context:
            self.client.fetch_url('https://example.com/missing')
        
        # Verify error details
        error = context.exception
        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.url, 'https://example.com/missing')
        self.assertIn('HTTP 404 error', str(error))
        
        # Verify only one attempt was made (no retries for 4xx)
        self.assertEqual(mock_get.call_count, 1)
        
        # Verify statistics
        stats = self.client.get_statistics()
        self.assertEqual(stats['total_requests'], 1)
        self.assertEqual(stats['successful_requests'], 0)
        self.assertEqual(stats['failed_requests'], 1)
    
    @patch('requests.Session.get')
    def test_http_error_with_retry(self, mock_get):
        """Test HTTP 5xx errors that should be retried."""
        # Mock 500 response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.content = b'Internal Server Error'
        mock_response.url = 'https://example.com/error'
        mock_get.return_value = mock_response
        
        # Request should fail after retries
        with self.assertRaises(NetworkError) as context:
            self.client.fetch_url('https://example.com/error')
        
        # Verify error details
        error = context.exception
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.url, 'https://example.com/error')
        
        # Verify all attempts were made (initial + retries)
        self.assertEqual(mock_get.call_count, 3)  # 1 initial + 2 retries
    
    @patch('requests.Session.get')
    def test_rate_limit_retry(self, mock_get):
        """Test HTTP 429 (rate limit) errors are retried."""
        # Mock 429 response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.content = b'Too Many Requests'
        mock_response.url = 'https://example.com/rate-limited'
        mock_get.return_value = mock_response
        
        # Request should fail after retries
        with self.assertRaises(NetworkError):
            self.client.fetch_url('https://example.com/rate-limited')
        
        # Verify all attempts were made (429 should be retried)
        self.assertEqual(mock_get.call_count, 3)  # 1 initial + 2 retries
    
    @patch('requests.Session.get')
    def test_network_timeout_retry(self, mock_get):
        """Test network timeout errors are retried."""
        # Mock timeout exception
        mock_get.side_effect = [
            Timeout('Request timed out'),
            Timeout('Request timed out'),
            Timeout('Request timed out')
        ]
        
        # Request should fail after retries
        with self.assertRaises(NetworkError) as context:
            self.client.fetch_url('https://example.com/timeout')
        
        # Verify error details
        error = context.exception
        self.assertEqual(error.url, 'https://example.com/timeout')
        self.assertIn('Failed to fetch', str(error))
        
        # Verify all attempts were made
        self.assertEqual(mock_get.call_count, 3)  # 1 initial + 2 retries
    
    @patch('requests.Session.get')
    def test_connection_error_retry(self, mock_get):
        """Test connection errors are retried."""
        # Mock connection error
        mock_get.side_effect = [
            ConnectionError('Connection failed'),
            ConnectionError('Connection failed'),
            ConnectionError('Connection failed')
        ]
        
        # Request should fail after retries
        with self.assertRaises(NetworkError):
            self.client.fetch_url('https://example.com/connection-error')
        
        # Verify all attempts were made
        self.assertEqual(mock_get.call_count, 3)
    
    @patch('requests.Session.get')
    def test_ssl_error_retry(self, mock_get):
        """Test SSL errors are retried."""
        # Mock SSL error
        mock_get.side_effect = [
            SSLError('SSL certificate verification failed'),
            SSLError('SSL certificate verification failed'),
            SSLError('SSL certificate verification failed')
        ]
        
        # Request should fail after retries
        with self.assertRaises(NetworkError):
            self.client.fetch_url('https://example.com/ssl-error')
        
        # Verify all attempts were made
        self.assertEqual(mock_get.call_count, 3)
    
    @patch('requests.Session.get')
    def test_successful_retry_after_failure(self, mock_get):
        """Test successful request after initial failures."""
        # Mock response: first two fail, third succeeds
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'Success after retry'
        mock_response.url = 'https://example.com/retry-success'
        
        mock_get.side_effect = [
            Timeout('First attempt timeout'),
            ConnectionError('Second attempt connection error'),
            mock_response  # Third attempt succeeds
        ]
        
        # Request should succeed on third attempt
        response, metrics = self.client.fetch_url('https://example.com/retry-success')
        
        # Verify successful response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'Success after retry')
        
        # Verify metrics show it took 3 attempts
        self.assertEqual(metrics.attempt_number, 3)
        
        # Verify all attempts were made
        self.assertEqual(mock_get.call_count, 3)
    
    def test_retry_delay_calculation(self):
        """Test exponential backoff calculation."""
        # Test exponential backoff with jitter
        delay0 = self.client._calculate_retry_delay(0)
        delay1 = self.client._calculate_retry_delay(1)
        delay2 = self.client._calculate_retry_delay(2)
        
        # Base delay is 0.1s, so expected delays are around 0.1, 0.2, 0.4
        # With jitter, they should be within range
        self.assertGreater(delay0, 0.05)  # At least 50% of base
        self.assertLess(delay0, 0.15)     # At most 150% of base
        
        self.assertGreater(delay1, 0.1)   # At least 50% of 0.2
        self.assertLess(delay1, 0.3)      # At most 150% of 0.2
        
        self.assertGreater(delay2, 0.2)   # At least 50% of 0.4
        self.assertLess(delay2, 0.6)      # At most 150% of 0.4
        
        # Test maximum delay cap (60 seconds)
        large_delay = self.client._calculate_retry_delay(10)
        self.assertLessEqual(large_delay, 60.0)
    
    def test_should_retry_logic(self):
        """Test retry decision logic for different exception types."""
        # Should retry these exceptions
        self.assertTrue(self.client._should_retry(Timeout('timeout')))
        self.assertTrue(self.client._should_retry(ConnectionError('connection failed')))
        self.assertTrue(self.client._should_retry(SSLError('ssl error')))
        self.assertTrue(self.client._should_retry(ChunkedEncodingError('chunked encoding')))
        
        # Should not retry these
        from requests.exceptions import TooManyRedirects, RequestException
        self.assertFalse(self.client._should_retry(TooManyRedirects('too many redirects')))
        self.assertFalse(self.client._should_retry(RequestException('generic request error')))
        self.assertFalse(self.client._should_retry(ValueError('unexpected error')))
    
    def test_should_retry_status_code(self):
        """Test retry decision logic for HTTP status codes."""
        # Should retry server errors and rate limiting
        self.assertTrue(self.client._should_retry_status_code(500))
        self.assertTrue(self.client._should_retry_status_code(502))
        self.assertTrue(self.client._should_retry_status_code(503))
        self.assertTrue(self.client._should_retry_status_code(504))
        self.assertTrue(self.client._should_retry_status_code(429))
        
        # Should not retry client errors
        self.assertFalse(self.client._should_retry_status_code(400))
        self.assertFalse(self.client._should_retry_status_code(401))
        self.assertFalse(self.client._should_retry_status_code(403))
        self.assertFalse(self.client._should_retry_status_code(404))
        
        # Should not retry success codes
        self.assertFalse(self.client._should_retry_status_code(200))
        self.assertFalse(self.client._should_retry_status_code(201))
    
    def test_session_creation(self):
        """Test HTTP session creation and configuration."""
        session = self.client._create_session()
        
        # Verify headers
        self.assertEqual(session.headers['User-Agent'], 'TestScraper/1.0')
        self.assertIn('Accept', session.headers)
        self.assertIn('Accept-Language', session.headers)
        self.assertIn('Accept-Encoding', session.headers)
        
        # Verify adapters are mounted
        self.assertIn('http://', session.adapters)
        self.assertIn('https://', session.adapters)
        
        session.close()
    
    def test_request_delay(self):
        """Test delay between requests."""
        # Configure client with request delay
        config_with_delay = self.test_config.copy()
        config_with_delay['delay_between_requests'] = 0.1
        client_with_delay = HTTPClient(config_with_delay)
        
        try:
            # Record timing
            start_time = time.time()
            
            # Simulate two consecutive requests
            client_with_delay._apply_request_delay()
            first_request_time = time.time()
            
            client_with_delay._apply_request_delay()
            second_request_time = time.time()
            
            # Second request should be delayed
            delay_between = second_request_time - first_request_time
            self.assertGreaterEqual(delay_between, 0.1)
            self.assertLess(delay_between, 0.2)  # Should not be much longer
            
        finally:
            client_with_delay.close()
    
    def test_concurrent_requests(self):
        """Test thread safety of HTTP client."""
        results = []
        errors = []
        
        def make_request(url_suffix):
            try:
                with patch('requests.Session.get') as mock_get:
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.content = f'Content {url_suffix}'.encode()
                    mock_response.url = f'https://example.com/{url_suffix}'
                    mock_get.return_value = mock_response
                    
                    response, metrics = self.client.fetch_url(f'https://example.com/{url_suffix}')
                    results.append((url_suffix, response.status_code))
            except Exception as e:
                errors.append((url_suffix, str(e)))
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request, args=(f'thread{i}',))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify all requests completed successfully
        self.assertEqual(len(results), 5)
        self.assertEqual(len(errors), 0)
        
        # Verify all got 200 status
        for url_suffix, status_code in results:
            self.assertEqual(status_code, 200)
    
    def test_context_manager(self):
        """Test HTTPClient as context manager."""
        config = self.test_config.copy()
        
        with HTTPClient(config) as client:
            # Client should be usable
            self.assertIsNotNone(client.session)
            
            # Mock a successful request
            with patch('requests.Session.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = b'Test content'
                mock_response.url = 'https://example.com'
                mock_get.return_value = mock_response
                
                response, metrics = client.fetch_url('https://example.com')
                self.assertEqual(response.status_code, 200)
        
        # Session should be closed after context exit
        # Note: We can't easily test this since session.close() doesn't change
        # the session object, but the __exit__ method should have been called
    
    def test_metrics_collection(self):
        """Test comprehensive metrics collection."""
        with patch('requests.Session.get') as mock_get:
            # Add a small delay to ensure response time > 0
            def slow_response(*args, **kwargs):
                time.sleep(0.001)  # 1ms delay
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = b'A' * 1000  # 1000 bytes
                mock_response.url = 'https://example.com/metrics'
                return mock_response
            
            mock_get.side_effect = slow_response
            
            response, metrics = self.client.fetch_url('https://example.com/metrics')
            
            # Verify detailed metrics
            self.assertEqual(metrics.url, 'https://example.com/metrics')
            self.assertEqual(metrics.status_code, 200)
            self.assertEqual(metrics.content_length, 1000)
            self.assertEqual(metrics.attempt_number, 1)
            self.assertEqual(metrics.final_url, 'https://example.com/metrics')
            self.assertIsNone(metrics.error)
            self.assertGreaterEqual(metrics.response_time_ms, 1)  # At least 1ms due to max(1, ...)
            self.assertLess(metrics.response_time_ms, 10000)  # Should be under 10 seconds
    
    def test_error_metrics_collection(self):
        """Test metrics collection for failed requests."""
        with patch('requests.Session.get') as mock_get:
            # Mock timeout error
            mock_get.side_effect = Timeout('Request timed out')
            
            try:
                self.client.fetch_url('https://example.com/timeout')
            except NetworkError:
                pass  # Expected
            
            # Verify statistics show failure
            stats = self.client.get_statistics()
            self.assertEqual(stats['total_requests'], 1)
            self.assertEqual(stats['successful_requests'], 0)
            self.assertEqual(stats['failed_requests'], 1)
            self.assertEqual(stats['success_rate_percent'], 0.0)


class TestRequestMetrics(unittest.TestCase):
    """Test cases for RequestMetrics dataclass."""
    
    def test_metrics_creation(self):
        """Test RequestMetrics creation and attributes."""
        metrics = RequestMetrics(
            url='https://example.com',
            status_code=200,
            response_time_ms=150,
            content_length=1024,
            attempt_number=1,
            final_url='https://example.com/redirected',
            error=None
        )
        
        self.assertEqual(metrics.url, 'https://example.com')
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.response_time_ms, 150)
        self.assertEqual(metrics.content_length, 1024)
        self.assertEqual(metrics.attempt_number, 1)
        self.assertEqual(metrics.final_url, 'https://example.com/redirected')
        self.assertIsNone(metrics.error)
    
    def test_error_metrics(self):
        """Test RequestMetrics for failed requests."""
        metrics = RequestMetrics(
            url='https://example.com/error',
            status_code=0,
            response_time_ms=5000,
            content_length=0,
            attempt_number=3,
            error='Network timeout after 3 attempts'
        )
        
        self.assertEqual(metrics.url, 'https://example.com/error')
        self.assertEqual(metrics.status_code, 0)
        self.assertEqual(metrics.response_time_ms, 5000)
        self.assertEqual(metrics.content_length, 0)
        self.assertEqual(metrics.attempt_number, 3)
        self.assertIsNone(metrics.final_url)
        self.assertEqual(metrics.error, 'Network timeout after 3 attempts')
    
    @patch('requests.Session.get')
    def test_conditional_request_if_modified_since(self, mock_get):
        """Test conditional request with If-Modified-Since header."""
        client = HTTPClient(self.test_config)
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'Test content'
        mock_response.url = 'https://example.com/conditional'
        mock_response.headers = {'Last-Modified': 'Wed, 21 Oct 2015 07:28:00 GMT'}
        mock_get.return_value = mock_response
        
        last_modified = 'Tue, 20 Oct 2015 07:28:00 GMT'
        
        # Make request with If-Modified-Since header
        response, metrics = client.fetch_url(
            'https://example.com/conditional', 
            if_modified_since=last_modified
        )
        
        # Verify the request was made with the correct header
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        headers = call_args[1]['headers']
        self.assertIn('If-Modified-Since', headers)
        self.assertEqual(headers['If-Modified-Since'], last_modified)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(metrics.status_code, 200)
    
    @patch('requests.Session.get')
    def test_conditional_request_304_not_modified(self, mock_get):
        """Test conditional request returning 304 Not Modified."""
        client = HTTPClient(self.test_config)
        
        # Mock 304 Not Modified response
        mock_response = Mock()
        mock_response.status_code = 304
        mock_response.content = b''
        mock_response.url = 'https://example.com/not-modified'
        mock_response.headers = {}
        mock_get.return_value = mock_response
        
        last_modified = 'Wed, 21 Oct 2015 07:28:00 GMT'
        
        # Make request with If-Modified-Since header
        response, metrics = client.fetch_url(
            'https://example.com/not-modified', 
            if_modified_since=last_modified
        )
        
        # Verify 304 response is handled correctly
        self.assertEqual(response.status_code, 304)
        self.assertEqual(metrics.status_code, 304)
        self.assertEqual(metrics.content_length, 0)
        
        # Verify the request was made with the correct header
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        headers = call_args[1]['headers']
        self.assertIn('If-Modified-Since', headers)
        self.assertEqual(headers['If-Modified-Since'], last_modified)


if __name__ == '__main__':
    # Set up test environment
    print("Starting HTTPClient unit tests...")
    print("Testing retry logic, session management, error handling, and metrics collection...")
    print()
    
    # Run tests with verbose output
    unittest.main(verbosity=2)