import unittest
import tempfile
import os
import logging
import time
from unittest.mock import patch, MagicMock, call
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils import (
    calculate_content_hash,
    validate_url,
    format_bytes,
    get_current_timestamp,
    sanitize_filename,
    retry_with_backoff,
    setup_logging,
    get_logger,
    log_performance,
    log_system_info
)


class TestCalculateContentHash(unittest.TestCase):
    """Test the calculate_content_hash function."""
    
    def test_empty_content(self):
        """Test hashing empty content."""
        result = calculate_content_hash("")
        self.assertEqual(result, "")
    
    def test_simple_content(self):
        """Test hashing simple content."""
        content = "Hello, World!"
        result = calculate_content_hash(content)
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        self.assertEqual(result, expected)
    
    def test_unicode_content(self):
        """Test hashing Unicode content."""
        content = "Hello, 世界! 🌍"
        result = calculate_content_hash(content)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)  # SHA-256 produces 64 character hex string
    
    def test_large_content(self):
        """Test hashing large content."""
        content = "x" * 100000  # Large content
        result = calculate_content_hash(content)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)
    
    def test_identical_content_same_hash(self):
        """Test that identical content produces identical hash."""
        content = "Test content for consistency"
        hash1 = calculate_content_hash(content)
        hash2 = calculate_content_hash(content)
        self.assertEqual(hash1, hash2)
    
    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        content1 = "Content 1"
        content2 = "Content 2"
        hash1 = calculate_content_hash(content1)
        hash2 = calculate_content_hash(content2)
        self.assertNotEqual(hash1, hash2)


class TestValidateUrl(unittest.TestCase):
    """Test the validate_url function."""
    
    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        url = "http://example.com"
        self.assertTrue(validate_url(url))
    
    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        url = "https://example.com"
        self.assertTrue(validate_url(url))
    
    def test_valid_url_with_path(self):
        """Test valid URL with path."""
        url = "https://example.com/path/to/resource"
        self.assertTrue(validate_url(url))
    
    def test_valid_url_with_query_params(self):
        """Test valid URL with query parameters."""
        url = "https://example.com/search?q=test&page=1"
        self.assertTrue(validate_url(url))
    
    def test_valid_url_with_port(self):
        """Test valid URL with port."""
        url = "https://example.com:8080/path"
        self.assertTrue(validate_url(url))
    
    def test_invalid_url_no_scheme(self):
        """Test invalid URL without scheme."""
        url = "example.com"
        self.assertFalse(validate_url(url))
    
    def test_invalid_url_no_netloc(self):
        """Test invalid URL without netloc."""
        url = "https://"
        self.assertFalse(validate_url(url))
    
    def test_invalid_url_wrong_scheme(self):
        """Test invalid URL with wrong scheme."""
        url = "ftp://example.com"
        self.assertFalse(validate_url(url))
    
    def test_invalid_url_malformed(self):
        """Test malformed URL."""
        url = "not-a-url"
        self.assertFalse(validate_url(url))
    
    def test_empty_url(self):
        """Test empty URL."""
        url = ""
        self.assertFalse(validate_url(url))
    
    def test_none_url(self):
        """Test None URL."""
        url = None
        self.assertFalse(validate_url(url))


class TestFormatBytes(unittest.TestCase):
    """Test the format_bytes function."""
    
    def test_zero_bytes(self):
        """Test formatting zero bytes."""
        result = format_bytes(0)
        self.assertEqual(result, "0 B")
    
    def test_bytes(self):
        """Test formatting bytes."""
        result = format_bytes(512)
        self.assertEqual(result, "512.0 B")
    
    def test_kilobytes(self):
        """Test formatting kilobytes."""
        result = format_bytes(1024)
        self.assertEqual(result, "1.0 KB")
    
    def test_megabytes(self):
        """Test formatting megabytes."""
        result = format_bytes(1024 * 1024)
        self.assertEqual(result, "1.0 MB")
    
    def test_gigabytes(self):
        """Test formatting gigabytes."""
        result = format_bytes(1024 * 1024 * 1024)
        self.assertEqual(result, "1.0 GB")
    
    def test_terabytes(self):
        """Test formatting terabytes."""
        result = format_bytes(1024 * 1024 * 1024 * 1024)
        self.assertEqual(result, "1.0 TB")
    
    def test_petabytes(self):
        """Test formatting petabytes."""
        result = format_bytes(1024 * 1024 * 1024 * 1024 * 1024)
        self.assertEqual(result, "1.0 PB")
    
    def test_fractional_values(self):
        """Test formatting fractional values."""
        result = format_bytes(1536)  # 1.5 KB
        self.assertEqual(result, "1.5 KB")
    
    def test_large_values(self):
        """Test formatting very large values."""
        result = format_bytes(1024 * 1024 * 1024 * 1024 * 1024 * 1024)
        self.assertEqual(result, "1024.0 PB")


class TestGetCurrentTimestamp(unittest.TestCase):
    """Test the get_current_timestamp function."""
    
    def test_timestamp_format(self):
        """Test timestamp format."""
        timestamp = get_current_timestamp()
        # Check format: YYYY-MM-DDTHH:MM:SS
        self.assertRegex(timestamp, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')
    
    def test_timestamp_consistency(self):
        """Test timestamp consistency within short time window."""
        timestamp1 = get_current_timestamp()
        timestamp2 = get_current_timestamp()
        # Should be the same or very close
        self.assertIsInstance(timestamp1, str)
        self.assertIsInstance(timestamp2, str)
    
    @patch('time.strftime')
    def test_timestamp_mocked(self, mock_strftime):
        """Test timestamp with mocked time."""
        mock_strftime.return_value = "2024-01-15T10:30:45"
        result = get_current_timestamp()
        self.assertEqual(result, "2024-01-15T10:30:45")
        mock_strftime.assert_called_once_with('%Y-%m-%dT%H:%M:%S', time.localtime())


class TestSanitizeFilename(unittest.TestCase):
    """Test the sanitize_filename function."""
    
    def test_clean_filename(self):
        """Test clean filename."""
        filename = "clean_filename.txt"
        result = sanitize_filename(filename)
        self.assertEqual(result, "clean_filename.txt")
    
    def test_problematic_characters(self):
        """Test filename with problematic characters."""
        filename = "file<>:\"/\\|?*name.txt"
        result = sanitize_filename(filename)
        self.assertEqual(result, "file_________name.txt")
    
    def test_leading_trailing_spaces(self):
        """Test filename with leading/trailing spaces."""
        filename = "   filename.txt   "
        result = sanitize_filename(filename)
        self.assertEqual(result, "filename.txt")
    
    def test_leading_trailing_dots(self):
        """Test filename with leading/trailing dots."""
        filename = "...filename.txt..."
        result = sanitize_filename(filename)
        self.assertEqual(result, "filename.txt")
    
    def test_empty_filename(self):
        """Test empty filename."""
        filename = ""
        result = sanitize_filename(filename)
        self.assertEqual(result, "unnamed")
    
    def test_whitespace_only_filename(self):
        """Test filename with only whitespace."""
        filename = "   "
        result = sanitize_filename(filename)
        self.assertEqual(result, "unnamed")
    
    def test_long_filename(self):
        """Test very long filename."""
        filename = "a" * 300
        result = sanitize_filename(filename)
        self.assertEqual(len(result), 255)
        self.assertEqual(result, "a" * 255)
    
    def test_unicode_filename(self):
        """Test filename with Unicode characters."""
        filename = "文件名.txt"
        result = sanitize_filename(filename)
        self.assertEqual(result, "文件名.txt")


class TestRetryWithBackoff(unittest.TestCase):
    """Test the retry_with_backoff decorator."""
    
    def test_successful_function(self):
        """Test successful function execution."""
        @retry_with_backoff
        def success_func():
            return "success"
        
        result = success_func()
        self.assertEqual(result, "success")
    
    def test_function_succeeds_after_retries(self):
        """Test function that succeeds after retries."""
        call_count = 0
        
        @retry_with_backoff
        def retry_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary error")
            return "success"
        
        result = retry_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)
    
    def test_function_fails_after_max_retries(self):
        """Test function that fails after max retries."""
        call_count = 0
        
        @retry_with_backoff
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Persistent error")
        
        with self.assertRaises(Exception) as context:
            failing_func()
        
        self.assertEqual(str(context.exception), "Persistent error")
        self.assertEqual(call_count, 4)  # Initial + 3 retries
    
    def test_custom_max_retries(self):
        """Test custom max retries."""
        call_count = 0
        
        def custom_retry_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Error")
        
        # Apply the decorator with custom parameters
        decorated_func = retry_with_backoff(custom_retry_func, max_retries=1)
        
        with self.assertRaises(Exception):
            decorated_func()
        
        self.assertEqual(call_count, 2)  # Initial + 1 retry
    
    @patch('utils.time.sleep')
    def test_backoff_delay(self, mock_sleep):
        """Test backoff delay calculation."""
        call_count = 0
        
        def delay_func():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Error")
            return "success"
        
        # Apply the decorator with custom parameters
        decorated_func = retry_with_backoff(delay_func, max_retries=2, delay=1.0, backoff_factor=2.0)
        
        result = decorated_func()
        self.assertEqual(result, "success")
        
        # Check sleep was called with correct delays
        expected_calls = [call(1.0), call(2.0)]
        mock_sleep.assert_has_calls(expected_calls)


class TestSetupLogging(unittest.TestCase):
    """Test the setup_logging function."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test.log")
    
    def tearDown(self):
        """Clean up test environment."""
        # Clear all handlers
        logging.getLogger().handlers.clear()
        # Remove temp directory and all its contents
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_basic_logging_setup(self):
        """Test basic logging setup."""
        config = {
            'level': 'INFO',
            'file': self.log_file,
            'max_size_mb': 1,
            'backup_count': 3,
            'format': '%(levelname)s - %(message)s'
        }
        
        logger = setup_logging(config)
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.level, logging.INFO)
    
    def test_log_directory_creation(self):
        """Test log directory creation."""
        nested_log_file = os.path.join(self.temp_dir, "nested", "test.log")
        config = {
            'level': 'INFO',
            'file': nested_log_file,
            'max_size_mb': 1,
            'backup_count': 3
        }
        
        logger = setup_logging(config)
        self.assertTrue(os.path.exists(os.path.dirname(nested_log_file)))
    
    def test_invalid_log_level(self):
        """Test invalid log level."""
        config = {
            'level': 'INVALID',
            'file': self.log_file,
            'max_size_mb': 1,
            'backup_count': 3
        }
        
        with self.assertRaises(ValueError):
            setup_logging(config)
    
    def test_default_values(self):
        """Test default configuration values."""
        config = {}
        
        with patch('os.makedirs'), patch('os.path.exists', return_value=True):
            logger = setup_logging(config)
            self.assertIsInstance(logger, logging.Logger)


class TestGetLogger(unittest.TestCase):
    """Test the get_logger function."""
    
    def test_get_logger_basic(self):
        """Test basic logger creation."""
        logger = get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "WebScraper.test_module")
    
    def test_logger_registry(self):
        """Test logger registry functionality."""
        logger1 = get_logger("test_module")
        logger2 = get_logger("test_module")
        self.assertIs(logger1, logger2)  # Should be the same instance


class TestLogPerformance(unittest.TestCase):
    """Test the log_performance decorator."""
    
    def test_performance_logging(self):
        """Test performance logging decorator."""
        @log_performance
        def test_func():
            return "result"
        
        result = test_func()
        self.assertEqual(result, "result")
    
    def test_performance_logging_with_exception(self):
        """Test performance logging with exception."""
        @log_performance
        def failing_func():
            raise ValueError("Test error")
        
        with self.assertRaises(ValueError):
            failing_func()


class TestLogSystemInfo(unittest.TestCase):
    """Test the log_system_info function."""
    
    @patch('utils.get_logger')
    def test_log_system_info(self, mock_get_logger):
        """Test system info logging."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        log_system_info()
        
        # Check that logger was called with system info
        self.assertTrue(mock_logger.info.called)
        # Should have multiple info calls for different system info
        self.assertGreater(mock_logger.info.call_count, 1)


if __name__ == '__main__':
    unittest.main() 