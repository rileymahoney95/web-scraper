#!/usr/bin/env python3
"""
Web scraping engine implementation for the web scraper application.

This module provides the core scraping functionality including HTTP client,
content extraction, robots.txt compliance, and scraping orchestration.
"""

import time
import random
import re
import hashlib
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse, urljoin
import threading

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import (
    RequestException, Timeout, ConnectionError,
    TooManyRedirects, SSLError, ChunkedEncodingError
)
from bs4 import BeautifulSoup, NavigableString
import chardet

from utils import get_logger, log_performance, calculate_content_hash
from database import ScrapedContent


# Custom exception classes for scraping errors
class ScrapingError(Exception):
    """Base exception for scraping-related errors."""
    
    def __init__(self, message: str, url: str = None, retry_after: int = None):
        super().__init__(message)
        self.url = url
        self.retry_after = retry_after
        self.timestamp = datetime.now()


class NetworkError(ScrapingError):
    """Network-related errors (timeouts, connection failures)."""
    
    def __init__(self, message: str, url: str = None, status_code: int = None):
        super().__init__(message, url)
        self.status_code = status_code


class ParseError(ScrapingError):
    """Content parsing and extraction errors."""
    
    def __init__(self, message: str, url: str = None, content_length: int = None):
        super().__init__(message, url)
        self.content_length = content_length


class RobotsError(ScrapingError):
    """Robots.txt compliance violations."""
    
    def __init__(self, message: str, url: str = None, robots_url: str = None):
        super().__init__(message, url)
        self.robots_url = robots_url


class ConfigurationError(ScrapingError):
    """Scraping configuration errors."""
    pass


@dataclass
class RequestMetrics:
    """Metrics collected for HTTP requests."""
    url: str
    status_code: int
    response_time_ms: int
    content_length: int
    attempt_number: int
    final_url: str = None  # After redirects
    error: str = None


@dataclass
class ErrorDecision:
    """Decision for how to handle a specific error."""
    should_retry: bool
    should_continue: bool
    log_level: str  # 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    count_as_failure: bool
    recovery_action: str = None  # Optional recovery action


class ErrorDecisionEngine:
    """
    Centralized error decision engine implementing the Task 6 error decision matrix.
    
    Provides intelligent decisions for error handling based on error type, context,
    and configured policies. Implements the complete decision matrix:
    
    | Error Type | Retry | Continue | Log Level | Count as Failure |
    |------------|--------|----------|-----------|------------------|
    | Network timeout | Yes | Yes | WARNING | No (until max retries) |
    | HTTP 5xx | Yes | Yes | WARNING | No (until max retries) |
    | HTTP 4xx | No | Yes | ERROR | Yes |
    | Parse error | No | Yes | ERROR | No |
    | Robots.txt violation | No | Yes | WARNING | No |
    | Database error | Yes | No | CRITICAL | Yes |
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize error decision engine with configuration.
        
        Args:
            config: Configuration dictionary containing error handling settings
        """
        self.config = config
        self.logger = get_logger(__name__)
        
        # Error rate tracking for monitoring
        self.error_counts = {
            'NetworkError': 0,
            'ParseError': 0,
            'RobotsError': 0,
            'ConfigurationError': 0,
            'DatabaseError': 0,
            'Unknown': 0
        }
        self.total_requests = 0
    
    def get_error_decision(self, error: Exception, context: Dict[str, Any] = None) -> ErrorDecision:
        """
        Get error handling decision based on error type and context.
        
        Args:
            error: Exception that occurred
            context: Additional context information (attempt number, previous errors, etc.)
            
        Returns:
            ErrorDecision with handling instructions
        """
        context = context or {}
        attempt_number = context.get('attempt_number', 1)
        max_retries = context.get('max_retries', 3)
        
        # Update error tracking
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        self.total_requests += 1
        
        # Apply decision matrix based on error type
        if isinstance(error, NetworkError):
            return self._handle_network_error(error, attempt_number, max_retries, context)
        elif isinstance(error, ParseError):
            return self._handle_parse_error(error, context)
        elif isinstance(error, RobotsError):
            return self._handle_robots_error(error, context)
        elif isinstance(error, ConfigurationError):
            return self._handle_configuration_error(error, context)
        elif 'database' in str(error).lower() or 'psycopg2' in str(error).lower():
            return self._handle_database_error(error, attempt_number, max_retries, context)
        else:
            return self._handle_unknown_error(error, context)
    
    def _handle_network_error(self, error: NetworkError, attempt_number: int, max_retries: int, context: Dict[str, Any]) -> ErrorDecision:
        """Handle network errors (timeouts, connection failures, HTTP 5xx)."""
        
        # Check if this is a client error (4xx) or server error (5xx)
        status_code = getattr(error, 'status_code', None)
        
        if status_code and 400 <= status_code < 500:
            # HTTP 4xx - No retry, Continue, ERROR, Count as failure
            return ErrorDecision(
                should_retry=False,
                should_continue=True,
                log_level='ERROR',
                count_as_failure=True,
                recovery_action='skip_url'
            )
        else:
            # Network timeout or HTTP 5xx - Retry until max, Continue, WARNING, No failure until max retries
            should_retry = attempt_number < max_retries
            count_as_failure = not should_retry  # Only count as failure if we've exhausted retries
            
            return ErrorDecision(
                should_retry=should_retry,
                should_continue=True,
                log_level='WARNING',
                count_as_failure=count_as_failure,
                recovery_action='retry_with_backoff' if should_retry else 'skip_url'
            )
    
    def _handle_parse_error(self, error: ParseError, context: Dict[str, Any]) -> ErrorDecision:
        """Handle content parsing and extraction errors."""
        return ErrorDecision(
            should_retry=False,
            should_continue=True,
            log_level='ERROR',
            count_as_failure=False,  # Parse errors don't count as failures
            recovery_action='save_partial_content'
        )
    
    def _handle_robots_error(self, error: RobotsError, context: Dict[str, Any]) -> ErrorDecision:
        """Handle robots.txt compliance violations."""
        return ErrorDecision(
            should_retry=False,
            should_continue=True,
            log_level='WARNING',
            count_as_failure=False,  # Robots.txt violations are skips, not failures
            recovery_action='skip_url'
        )
    
    def _handle_configuration_error(self, error: ConfigurationError, context: Dict[str, Any]) -> ErrorDecision:
        """Handle scraping configuration errors."""
        return ErrorDecision(
            should_retry=False,
            should_continue=False,  # Configuration errors require manual intervention
            log_level='CRITICAL',
            count_as_failure=True,
            recovery_action='stop_execution'
        )
    
    def _handle_database_error(self, error: Exception, attempt_number: int, max_retries: int, context: Dict[str, Any]) -> ErrorDecision:
        """Handle database-related errors."""
        should_retry = attempt_number < max_retries
        
        return ErrorDecision(
            should_retry=should_retry,
            should_continue=not should_retry,  # Stop if we can't retry
            log_level='CRITICAL',
            count_as_failure=True,
            recovery_action='retry_database_operation' if should_retry else 'stop_execution'
        )
    
    def _handle_unknown_error(self, error: Exception, context: Dict[str, Any]) -> ErrorDecision:
        """Handle unexpected/unknown errors."""
        return ErrorDecision(
            should_retry=False,
            should_continue=True,
            log_level='ERROR',
            count_as_failure=True,
            recovery_action='skip_url'
        )
    
    def get_error_rates(self) -> Dict[str, float]:
        """
        Get error rates by type for monitoring.
        
        Returns:
            Dictionary with error rates (0.0-1.0) by error type
        """
        if self.total_requests == 0:
            return {error_type: 0.0 for error_type in self.error_counts.keys()}
        
        return {
            error_type: count / self.total_requests 
            for error_type, count in self.error_counts.items()
        }
    
    def log_error_with_context(self, error: Exception, context: Dict[str, Any], decision: ErrorDecision) -> None:
        """
        Log error with comprehensive context information as specified in Task 6.
        
        Args:
            error: Exception that occurred
            context: Context information
            decision: Error handling decision
        """
        # Build comprehensive error data structure
        error_data = {
            'error_type': type(error).__name__,
            'message': str(error),
            'url': getattr(error, 'url', context.get('url', 'unknown')),
            'timestamp': getattr(error, 'timestamp', datetime.now()).isoformat(),
            'decision': {
                'should_retry': decision.should_retry,
                'should_continue': decision.should_continue,
                'count_as_failure': decision.count_as_failure,
                'recovery_action': decision.recovery_action
            },
            'context': context,
            'error_rates': self.get_error_rates()
        }
        
        # Add error-specific attributes
        if hasattr(error, 'status_code'):
            error_data['status_code'] = error.status_code
        if hasattr(error, 'content_length'):
            error_data['content_length'] = error.content_length
        if hasattr(error, 'robots_url'):
            error_data['robots_url'] = error.robots_url
        if hasattr(error, 'retry_after'):
            error_data['retry_after'] = error.retry_after
        
        # Log at appropriate level based on decision
        log_message = f"Scraping error: {error_data}"
        
        if decision.log_level == 'DEBUG':
            self.logger.debug(log_message)
        elif decision.log_level == 'INFO':
            self.logger.info(log_message)
        elif decision.log_level == 'WARNING':
            self.logger.warning(log_message)
        elif decision.log_level == 'ERROR':
            self.logger.error(log_message)
        elif decision.log_level == 'CRITICAL':
            self.logger.critical(log_message)
        else:
            # Fallback to error level
            self.logger.error(log_message)


class HTTPClient:
    """
    HTTP client with retry logic, session management, and comprehensive error handling.
    
    This class provides robust HTTP request capabilities including:
    - Persistent session with connection pooling
    - Intelligent retry logic with exponential backoff
    - Request/response metrics collection
    - Configurable timeouts and delays
    - Comprehensive error categorization
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize HTTP client with configuration.
        
        Args:
            config: Scraping configuration dictionary containing:
                - timeout: Request timeout in seconds
                - retry_attempts: Maximum number of retry attempts
                - retry_delay: Base delay between retries in seconds
                - user_agent: User agent string for requests
                - delay_between_requests: Delay between consecutive requests
        """
        self.config = config
        self.logger = get_logger(__name__)
        
        # Extract configuration values with defaults
        self.timeout = config.get('timeout', 30)
        self.max_retries = config.get('retry_attempts', 3)
        self.base_retry_delay = config.get('retry_delay', 5)
        self.user_agent = config.get('user_agent', 'WebScraper/1.0')
        self.request_delay = config.get('delay_between_requests', 1)
        
        # Session management
        self.session = None
        self._session_lock = threading.Lock()
        self._last_request_time = 0
        
        # Request metrics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        self.logger.info(f"HTTPClient initialized with timeout={self.timeout}s, "
                        f"max_retries={self.max_retries}, user_agent='{self.user_agent}'")
    
    @log_performance
    def fetch_url(self, url: str, if_modified_since: str = None) -> Tuple[requests.Response, RequestMetrics]:
        """
        Fetch URL with retry logic and comprehensive error handling.
        
        Args:
            url: URL to fetch
            if_modified_since: Optional If-Modified-Since header value for conditional requests
            
        Returns:
            Tuple of (response, metrics) for successful requests
            
        Raises:
            NetworkError: For network-related failures
            ScrapingError: For other scraping-related failures
        """
        self.total_requests += 1
        start_time = time.time()
        
        # Ensure minimum delay between requests
        self._apply_request_delay()
        
        # Get or create session
        session = self._get_session()
        
        last_exception = None
        last_status_code = None
        
        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(f"Attempting to fetch {url} (attempt {attempt + 1}/{self.max_retries + 1})")
                
                # Record request start time for this attempt
                request_start = time.time()
                
                # Prepare headers for conditional requests
                headers = {}
                if if_modified_since:
                    headers['If-Modified-Since'] = if_modified_since
                    self.logger.debug(f"Adding If-Modified-Since header: {if_modified_since}")
                
                # Make the request
                response = session.get(url, timeout=self.timeout, headers=headers)
                
                # Calculate metrics
                response_time_ms = max(1, int((time.time() - request_start) * 1000))
                content_length = len(response.content) if response.content else 0
                
                metrics = RequestMetrics(
                    url=url,
                    status_code=response.status_code,
                    response_time_ms=response_time_ms,
                    content_length=content_length,
                    attempt_number=attempt + 1,
                    final_url=response.url
                )
                
                # Handle 304 Not Modified response (success for conditional requests)
                if response.status_code == 304:
                    self._log_request_metrics(metrics)
                    self.successful_requests += 1
                    self.logger.debug(f"Content not modified for {url} (304 response)")
                    return response, metrics
                
                # Check for HTTP errors
                if response.status_code >= 400:
                    error_msg = f"HTTP {response.status_code} error for {url}"
                    last_status_code = response.status_code
                    
                    # Decide whether to retry based on status code
                    if self._should_retry_status_code(response.status_code) and attempt < self.max_retries:
                        self.logger.warning(f"{error_msg}, retrying in {self._calculate_retry_delay(attempt)}s")
                        self._wait_for_retry(attempt)
                        continue
                    else:
                        # Don't retry 4xx errors (except 429) - fail immediately
                        metrics.error = error_msg
                        self._log_request_metrics(metrics)
                        self.failed_requests += 1
                        raise NetworkError(error_msg, url, response.status_code)
                
                # Success!
                self._log_request_metrics(metrics)
                self.successful_requests += 1
                self.logger.debug(f"Successfully fetched {url} ({content_length} bytes, {response_time_ms}ms)")
                
                return response, metrics
                
            except (Timeout, ConnectionError, SSLError, ChunkedEncodingError, TooManyRedirects) as e:
                last_exception = e
                error_msg = f"Network error for {url}: {type(e).__name__} - {str(e)}"
                
                if attempt < self.max_retries and self._should_retry(e):
                    retry_delay = self._calculate_retry_delay(attempt)
                    self.logger.warning(f"{error_msg}, retrying in {retry_delay}s")
                    self._wait_for_retry(attempt)
                    continue
                else:
                    # Max retries reached or non-retryable error
                    break
                    
            except NetworkError:
                # Re-raise NetworkError exceptions (from immediate 4xx failures)
                raise
                
            except RequestException as e:
                last_exception = e
                error_msg = f"Request error for {url}: {type(e).__name__} - {str(e)}"
                self.logger.error(error_msg)
                break
                
            except Exception as e:
                last_exception = e
                error_msg = f"Unexpected error for {url}: {type(e).__name__} - {str(e)}"
                self.logger.error(error_msg)
                break
        
        # All retries exhausted or non-retryable error
        response_time_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Failed to fetch {url} after {self.max_retries + 1} attempts: {str(last_exception)}"
        
        metrics = RequestMetrics(
            url=url,
            status_code=0,
            response_time_ms=response_time_ms,
            content_length=0,
            attempt_number=self.max_retries + 1,
            error=error_msg
        )
        
        self._log_request_metrics(metrics)
        self.failed_requests += 1
        
        # Raise NetworkError with status code if we have it
        raise NetworkError(error_msg, url, last_status_code)
    
    def _get_session(self) -> requests.Session:
        """
        Get or create a requests session with proper configuration.
        
        Returns:
            Configured requests session
        """
        with self._session_lock:
            if self.session is None:
                self.session = self._create_session()
            return self.session
    
    def _create_session(self) -> requests.Session:
        """
        Create a new requests session with optimized configuration.
        
        Returns:
            Configured requests session
        """
        session = requests.Session()
        
        # Set headers
        session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Configure adapters for connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,  # Number of connection pools
            pool_maxsize=20,      # Number of connections per pool
            max_retries=0,        # We handle retries manually
            pool_block=False      # Don't block when pool is full
        )
        
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        self.logger.debug("Created new HTTP session with connection pooling")
        return session
    
    def _should_retry(self, exception: Exception) -> bool:
        """
        Determine if request should be retried based on exception type.
        
        Args:
            exception: Exception that occurred during request
            
        Returns:
            True if request should be retried
        """
        # Always retry network-related errors
        retryable_exceptions = (
            Timeout,
            ConnectionError,
            SSLError,
            ChunkedEncodingError
        )
        
        if isinstance(exception, retryable_exceptions):
            return True
        
        # Don't retry too many redirects
        if isinstance(exception, TooManyRedirects):
            return False
        
        # For other RequestExceptions, don't retry
        if isinstance(exception, RequestException):
            return False
        
        # For unexpected exceptions, don't retry
        return False
    
    def _should_retry_status_code(self, status_code: int) -> bool:
        """
        Determine if request should be retried based on HTTP status code.
        
        Args:
            status_code: HTTP status code
            
        Returns:
            True if request should be retried
        """
        # Retry server errors (5xx)
        if status_code >= 500:
            return True
        
        # Retry rate limiting (429)
        if status_code == 429:
            return True
        
        # Don't retry client errors (4xx) except 429
        return False
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """
        Calculate delay for retry attempt with exponential backoff and jitter.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff: base_delay * (2 ^ attempt)
        exponential_delay = self.base_retry_delay * (2 ** attempt)
        
        # Add jitter to prevent thundering herd (�25% of delay)
        jitter_range = exponential_delay * 0.25
        jitter = random.uniform(-jitter_range, jitter_range)
        
        # Calculate final delay with jitter
        delay = exponential_delay + jitter
        
        # Cap maximum delay at 60 seconds
        return min(delay, 60.0)
    
    def _wait_for_retry(self, attempt: int) -> None:
        """
        Wait for the calculated retry delay.
        
        Args:
            attempt: Current attempt number (0-based)
        """
        delay = self._calculate_retry_delay(attempt)
        time.sleep(delay)
    
    def _apply_request_delay(self) -> None:
        """
        Apply configured delay between requests to be respectful to servers.
        """
        if self.request_delay <= 0:
            return
        
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        
        if time_since_last_request < self.request_delay:
            sleep_time = self.request_delay - time_since_last_request
            self.logger.debug(f"Applying request delay: {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def _log_request_metrics(self, metrics: RequestMetrics) -> None:
        """
        Log request performance metrics.
        
        Args:
            metrics: Request metrics to log
        """
        if metrics.error:
            self.logger.error(
                f"Request failed: {metrics.url} - {metrics.error} "
                f"(attempt {metrics.attempt_number}, {metrics.response_time_ms}ms)"
            )
        else:
            self.logger.info(
                f"Request successful: {metrics.url} - {metrics.status_code} "
                f"({metrics.content_length} bytes, {metrics.response_time_ms}ms, "
                f"attempt {metrics.attempt_number})"
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get HTTP client statistics.
        
        Returns:
            Dictionary containing client statistics
        """
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate_percent': round(success_rate, 2),
            'configuration': {
                'timeout': self.timeout,
                'max_retries': self.max_retries,
                'base_retry_delay': self.base_retry_delay,
                'request_delay': self.request_delay,
                'user_agent': self.user_agent
            }
        }
    
    def close(self) -> None:
        """
        Close the HTTP session and cleanup resources.
        """
        with self._session_lock:
            if self.session:
                self.session.close()
                self.session = None
                self.logger.debug("HTTP session closed")
    
    def __enter__(self):
        """Context manager entry."""
        # Initialize session on entry
        self._get_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # Close the session and cleanup resources
        self.close()
        # Don't suppress any exceptions
        return False


class ContentExtractor:
    """
    Extract and process content from HTTP responses.
    
    This class provides robust HTML parsing and content extraction including:
    - Multi-strategy title extraction with fallbacks
    - Content cleaning and normalization
    - Character encoding detection and handling
    - Content validation and error recovery
    - Integration with ScrapedContent dataclass
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize content extractor with configuration.
        
        Args:
            config: Scraping configuration dictionary containing:
                - min_content_length: Minimum content length threshold
                - preserve_html: Whether to preserve HTML structure
                - max_content_size: Maximum content size to process
        """
        self.config = config
        self.logger = get_logger(__name__)
        
        # Extract configuration values with defaults
        self.min_content_length = config.get('min_content_length', 100)
        self.preserve_html = config.get('preserve_html', False)
        self.max_content_size = config.get('max_content_size', 10 * 1024 * 1024)  # 10MB
        
        # Elements to remove during content cleaning
        self.remove_selectors = [
            'script', 'style', 'nav', 'footer', 'header',
            '.navigation', '.navbar', '.sidebar', '.footer',
            '.advertisement', '.ads', '#comments', '.comment-section'
        ]
        
        # Content area selectors (in order of preference)
        self.content_selectors = [
            'main', 'article', '.content', '.main-content',
            '.post-content', '.entry-content', '#content',
            '.article-body', '.story-body'
        ]
        
        self.logger.info(f"ContentExtractor initialized with min_length={self.min_content_length}, "
                        f"preserve_html={self.preserve_html}")
    
    @log_performance
    def extract_content(self, response: requests.Response, url: str) -> ScrapedContent:
        """
        Extract structured content from HTTP response.
        
        Args:
            response: HTTP response object
            url: Original URL (may differ from response.url due to redirects)
            
        Returns:
            ScrapedContent object with extracted information
            
        Raises:
            ParseError: For content parsing failures
        """
        start_time = time.time()
        extraction_error = None
        
        try:
            # Detect and handle character encoding
            encoding = self._detect_encoding(response)
            
            # Get content with proper encoding
            if response.encoding != encoding:
                response.encoding = encoding
                content_text = response.text
            else:
                content_text = response.text
            
            # Validate content size
            if len(content_text) > self.max_content_size:
                self.logger.warning(f"Content size ({len(content_text)} bytes) exceeds maximum, truncating")
                content_text = content_text[:self.max_content_size]
            
            # Parse HTML with error recovery
            soup = self._create_soup(content_text)
            
            # Extract title using multiple strategies
            title = self._extract_title(soup, url)
            
            # Extract and clean main content
            content = self._extract_main_content(soup)
            
            # Validate content
            if len(content.strip()) < self.min_content_length:
                self.logger.warning(f"Extracted content is too short ({len(content)} chars) for {url}")
                # Don't fail entirely, but flag it
            
            # Calculate content hash
            content_hash = calculate_content_hash(content)
            
            # Extract Last-Modified header if present
            last_modified = self._extract_last_modified(response)
            
            # Calculate metrics
            response_time_ms = getattr(response, '_response_time_ms', 
                                     int((time.time() - start_time) * 1000))
            
            scraped_content = ScrapedContent(
                url=url,
                title=title,
                content=content,
                content_hash=content_hash,
                response_status=response.status_code,
                response_time_ms=response_time_ms,
                content_length=len(response.content) if response.content else 0,
                last_modified=last_modified
            )
            
            self.logger.info(f"Content extracted successfully from {url}: "
                           f"title='{title[:50]}...' content_length={len(content)}")
            
            return scraped_content
            
        except Exception as e:
            extraction_error = f"Content extraction failed: {type(e).__name__} - {str(e)}"
            self.logger.error(f"{extraction_error} for {url}")
            
            # Create partial content object even on failure
            response_time_ms = getattr(response, '_response_time_ms', 
                                     int((time.time() - start_time) * 1000))
            
            scraped_content = ScrapedContent(
                url=url,
                title=self._generate_fallback_title(url),
                content="",  # Empty content on extraction failure
                content_hash=calculate_content_hash(""),
                response_status=response.status_code,
                response_time_ms=response_time_ms,
                content_length=len(response.content) if response.content else 0,
                last_modified=self._extract_last_modified(response)
            )
            
            return scraped_content
    
    def _detect_encoding(self, response: requests.Response) -> str:
        """
        Detect character encoding from response headers and content.
        
        Args:
            response: HTTP response object
            
        Returns:
            Detected encoding string
        """
        # Try encoding from HTTP headers first
        if response.encoding and response.encoding.lower() != 'iso-8859-1':
            return response.encoding
        
        # Try encoding from content meta tags
        if response.content:
            # Look for charset in meta tags
            content_sample = response.content[:1024]  # First 1KB should contain meta tags
            
            # Check for charset in meta http-equiv
            charset_match = re.search(rb'<meta[^>]+charset[=\s]*["\']?([^"\'>\s]+)', content_sample, re.IGNORECASE)
            if charset_match:
                charset = charset_match.group(1).decode('ascii', errors='ignore')
                return charset
            
            # Use chardet for automatic detection as last resort
            try:
                detected = chardet.detect(content_sample)
                if detected and detected['confidence'] > 0.7:
                    return detected['encoding']
            except Exception:
                pass
        
        # Default fallback
        return 'utf-8'
    
    def _create_soup(self, content: str) -> BeautifulSoup:
        """
        Create BeautifulSoup object with error recovery.
        
        Args:
            content: HTML content string
            
        Returns:
            BeautifulSoup object
        """
        try:
            # Try with lxml parser first (fastest and most lenient)
            return BeautifulSoup(content, 'lxml')
        except Exception:
            try:
                # Fall back to html.parser (built-in, more forgiving)
                return BeautifulSoup(content, 'html.parser')
            except Exception:
                # Last resort: very lenient parsing
                return BeautifulSoup(content, 'html.parser', from_encoding='utf-8')
    
    def _extract_title(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        """
        Extract page title using multiple strategies.
        
        Args:
            soup: BeautifulSoup object
            url: Page URL for fallback title generation
            
        Returns:
            Extracted title string or None
        """
        # Strategy 1: <title> tag
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
            if title:
                return self._clean_title(title)
        
        # Strategy 2: First <h1> tag
        h1_tag = soup.find('h1')
        if h1_tag:
            title = h1_tag.get_text(strip=True)
            if title:
                return self._clean_title(title)
        
        # Strategy 3: Open Graph title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
            if title:
                return self._clean_title(title)
        
        # Strategy 4: Meta title
        meta_title = soup.find('meta', attrs={'name': 'title'})
        if meta_title and meta_title.get('content'):
            title = meta_title['content'].strip()
            if title:
                return self._clean_title(title)
        
        # Strategy 5: Generate from URL
        return self._generate_fallback_title(url)
    
    def _clean_title(self, title: str) -> str:
        """
        Clean and normalize title text.
        
        Args:
            title: Raw title string
            
        Returns:
            Cleaned title string
        """
        # Remove excessive whitespace
        title = re.sub(r'\s+', ' ', title.strip())
        
        # Remove common title suffixes (site names, etc.)
        # This could be made configurable in the future
        title = re.sub(r'\s*[-|–—]\s*[^-|–—]*$', '', title)
        
        # Truncate if too long
        if len(title) > 200:
            title = title[:197] + '...'
        
        return title
    
    def _generate_fallback_title(self, url: str) -> str:
        """
        Generate fallback title from URL.
        
        Args:
            url: Page URL
            
        Returns:
            Generated title string
        """
        try:
            parsed = urlparse(url)
            
            # Use path for title if available
            if parsed.path and parsed.path != '/':
                # Extract meaningful part from path
                path_parts = [part for part in parsed.path.split('/') if part]
                if path_parts:
                    title = path_parts[-1].replace('-', ' ').replace('_', ' ')
                    # Capitalize words
                    title = ' '.join(word.capitalize() for word in title.split())
                    return f"{title} - {parsed.netloc}"
            
            # Just use domain name
            return parsed.netloc or url
            
        except Exception:
            return url
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """
        Extract main content from HTML, removing navigation and boilerplate.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Extracted content string
        """
        # Create a copy to avoid modifying the original
        content_soup = BeautifulSoup(str(soup), soup.original_encoding or 'html.parser')
        
        # Remove unwanted elements
        for selector in self.remove_selectors:
            for element in content_soup.select(selector):
                element.decompose()
        
        # Try to find main content area
        content_element = None
        for selector in self.content_selectors:
            content_element = content_soup.select_one(selector)
            if content_element:
                break
        
        # If no specific content area found, use body
        if not content_element:
            content_element = content_soup.find('body')
        
        # Last resort: use the entire document
        if not content_element:
            content_element = content_soup
        
        # Extract text or HTML based on configuration
        if self.preserve_html:
            content = str(content_element)
        else:
            content = content_element.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        content = re.sub(r'\s+', ' ', content.strip())
        
        return content
    
    def _extract_last_modified(self, response: requests.Response) -> Optional[str]:
        """
        Extract Last-Modified header from HTTP response.
        
        Args:
            response: HTTP response object
            
        Returns:
            Last-Modified header value or None if not present
        """
        try:
            last_modified = response.headers.get('Last-Modified')
            if last_modified:
                self.logger.debug(f"Found Last-Modified header: {last_modified}")
                return last_modified
            else:
                self.logger.debug("No Last-Modified header found")
                return None
        except Exception as e:
            self.logger.warning(f"Error extracting Last-Modified header: {e}")
            return None


class RobotChecker:
    """
    Check robots.txt compliance for URLs.
    
    This class provides robots.txt fetching, parsing, and compliance checking including:
    - Fetching and caching robots.txt files per domain
    - Parsing robots.txt rules for specific user agents
    - Crawl-delay directive support
    - Graceful error handling for missing/invalid robots.txt
    - TTL-based cache management
    """
    
    def __init__(self, config: Dict[str, Any], http_client: HTTPClient):
        """
        Initialize robot checker with configuration.
        
        Args:
            config: Scraping configuration dictionary containing:
                - respect_robots_txt: Whether to check robots.txt compliance
                - user_agent: User agent string for robots.txt rules
        """
        self.config = config
        self.http_client = http_client
        self.logger = get_logger(__name__)
        
        # Configuration
        self.respect_robots = config.get('respect_robots_txt', True)
        self.user_agent = config.get('user_agent', 'WebScraper/1.0')
        self.cache_ttl = 86400  # 24 hours in seconds
        
        # Cache for robots.txt data
        self._robots_cache = {}
        self._cache_lock = threading.Lock()
        
        self.logger.info(f"RobotChecker initialized: respect_robots={self.respect_robots}, "
                        f"user_agent='{self.user_agent}', cache_ttl={self.cache_ttl}s")
    
    def can_fetch(self, url: str, user_agent: str = None) -> bool:
        """
        Check if URL can be fetched according to robots.txt.
        
        Args:
            url: URL to check for compliance
            user_agent: User agent string (defaults to configured user agent)
            
        Returns:
            True if URL can be fetched, False otherwise
        """
        if not self.respect_robots:
            return True
        
        user_agent = user_agent or self.user_agent
        
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Get robots.txt rules for this domain
            robots_rules = self._get_robots_rules(base_url)
            if not robots_rules:
                # No robots.txt found or parsing failed - allow all
                return True
            
            # Check rules for this user agent
            path = parsed_url.path or '/'
            return self._check_path_allowed(path, user_agent, robots_rules)
            
        except Exception as e:
            self.logger.warning(f"Error checking robots.txt for {url}: {e}")
            # On error, allow access
            return True
    
    def get_crawl_delay(self, url: str, user_agent: str = None) -> float:
        """
        Get crawl delay for URL and user agent.
        
        Args:
            url: URL to check
            user_agent: User agent string (defaults to configured user agent)
            
        Returns:
            Crawl delay in seconds, or 0 if no delay specified
        """
        if not self.respect_robots:
            return 0.0
        
        user_agent = user_agent or self.user_agent
        
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            robots_rules = self._get_robots_rules(base_url)
            if not robots_rules:
                return 0.0
            
            # Look for crawl-delay directive
            return self._get_crawl_delay_for_agent(user_agent, robots_rules)
            
        except Exception as e:
            self.logger.warning(f"Error getting crawl delay for {url}: {e}")
            return 0.0
    
    def _get_robots_rules(self, base_url: str) -> Optional[Dict[str, Any]]:
        """
        Get robots.txt rules for domain, using cache when available.
        
        Args:
            base_url: Base URL of the domain (e.g., https://example.com)
            
        Returns:
            Parsed robots.txt rules or None if unavailable
        """
        cache_key = self._get_cache_key(base_url)
        
        with self._cache_lock:
            # Check cache first
            if cache_key in self._robots_cache:
                cache_entry = self._robots_cache[cache_key]
                if self._is_cache_valid(cache_entry):
                    self.logger.debug(f"Using cached robots.txt for {base_url}")
                    return cache_entry['rules']
                else:
                    # Cache expired, remove entry
                    del self._robots_cache[cache_key]
        
        # Fetch fresh robots.txt
        robots_content = self._fetch_robots_txt(base_url)
        if robots_content is None:
            return None
        
        # Parse robots.txt
        robots_rules = self._parse_robots_txt(robots_content)
        
        # Cache the result
        with self._cache_lock:
            self._robots_cache[cache_key] = {
                'rules': robots_rules,
                'timestamp': time.time(),
                'url': base_url
            }
        
        return robots_rules
    
    def _fetch_robots_txt(self, base_url: str) -> Optional[str]:
        """
        Fetch robots.txt for domain.
        
        Args:
            base_url: Base URL of the domain
            
        Returns:
            robots.txt content or None if unavailable
        """
        robots_url = urljoin(base_url, '/robots.txt')
        
        try:
            self.logger.debug(f"Fetching robots.txt from {robots_url}")
            response, metrics = self.http_client.fetch_url(robots_url)
            
            if response.status_code == 200:
                content = response.text
                self.logger.debug(f"Successfully fetched robots.txt from {robots_url} "
                                f"({len(content)} chars)")
                return content
            else:
                self.logger.debug(f"robots.txt not found at {robots_url} (status: {response.status_code})")
                return None
                
        except NetworkError as e:
            # 4xx errors mean no robots.txt - that's normal
            if e.status_code and 400 <= e.status_code < 500:
                self.logger.debug(f"No robots.txt found at {robots_url} (404)")
            else:
                self.logger.warning(f"Failed to fetch robots.txt from {robots_url}: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"Unexpected error fetching robots.txt from {robots_url}: {e}")
            return None
    
    def _parse_robots_txt(self, content: str) -> Dict[str, Any]:
        """
        Parse robots.txt content into rules.
        
        Args:
            content: Raw robots.txt content
            
        Returns:
            Dictionary with parsed rules
        """
        rules = {
            'user_agents': {},  # user-agent -> {'disallow': [], 'allow': [], 'crawl_delay': None}
            'sitemaps': []      # List of sitemap URLs
        }
        
        current_user_agent = None
        
        for line_num, line in enumerate(content.split('\n'), 1):
            # Remove comments and whitespace
            line = line.split('#')[0].strip()
            if not line:
                continue
            
            # Parse directive
            if ':' not in line:
                continue
            
            directive, value = line.split(':', 1)
            directive = directive.strip().lower()
            value = value.strip()
            
            if directive == 'user-agent':
                current_user_agent = value.lower()
                if current_user_agent not in rules['user_agents']:
                    rules['user_agents'][current_user_agent] = {
                        'disallow': [],
                        'allow': [],
                        'crawl_delay': None
                    }
            
            elif directive == 'disallow' and current_user_agent:
                if value:  # Empty disallow means allow all
                    rules['user_agents'][current_user_agent]['disallow'].append(value)
            
            elif directive == 'allow' and current_user_agent:
                if value:
                    rules['user_agents'][current_user_agent]['allow'].append(value)
            
            elif directive == 'crawl-delay' and current_user_agent:
                try:
                    crawl_delay = float(value)
                    rules['user_agents'][current_user_agent]['crawl_delay'] = crawl_delay
                except ValueError:
                    self.logger.warning(f"Invalid crawl-delay value: {value}")
            
            elif directive == 'sitemap':
                rules['sitemaps'].append(value)
        
        return rules
    
    def _check_path_allowed(self, path: str, user_agent: str, robots_rules: Dict[str, Any]) -> bool:
        """
        Check if path is allowed for user agent according to robots.txt rules.
        
        Args:
            path: URL path to check
            user_agent: User agent string
            robots_rules: Parsed robots.txt rules
            
        Returns:
            True if path is allowed
        """
        user_agents = robots_rules.get('user_agents', {})
        
        # Find applicable rules (check specific user agent first, then *)
        applicable_rules = None
        user_agent_lower = user_agent.lower()
        
        # First, try exact match
        if user_agent_lower in user_agents:
            applicable_rules = user_agents[user_agent_lower]
        else:
            # Try prefix matching (e.g., "googlebot" matches "googlebot/1.2")
            for ua in user_agents:
                if user_agent_lower.startswith(ua + '/') or user_agent_lower.startswith(ua + ' ') or user_agent_lower == ua:
                    applicable_rules = user_agents[ua]
                    break
        
        # Fall back to wildcard rules
        if applicable_rules is None and '*' in user_agents:
            applicable_rules = user_agents['*']
        
        # If no applicable rules found, allow by default
        if applicable_rules is None:
            return True
        
        # Check Allow rules first (they take precedence)
        for allow_pattern in applicable_rules.get('allow', []):
            if self._path_matches_pattern(path, allow_pattern):
                return True
        
        # Check Disallow rules
        for disallow_pattern in applicable_rules.get('disallow', []):
            if self._path_matches_pattern(path, disallow_pattern):
                return False
        
        # No matching rules - allow by default
        return True
    
    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """
        Check if path matches robots.txt pattern.
        
        Args:
            path: URL path to check
            pattern: robots.txt pattern (may contain wildcards)
            
        Returns:
            True if path matches pattern
        """
        # robots.txt patterns are simple prefix matches with optional wildcards
        # Convert to regex for proper matching
        
        # Escape special regex characters except * and $
        escaped_pattern = re.escape(pattern)
        
        # Replace escaped wildcards with regex equivalents
        escaped_pattern = escaped_pattern.replace(r'\*', '.*')
        
        # Handle end-of-line anchor
        if escaped_pattern.endswith('$'):
            escaped_pattern = escaped_pattern[:-1] + '$'
        else:
            # If no $ at end, pattern matches prefix
            escaped_pattern = '^' + escaped_pattern
        
        # Add start anchor if not present
        if not escaped_pattern.startswith('^'):
            escaped_pattern = '^' + escaped_pattern
        
        try:
            return bool(re.match(escaped_pattern, path))
        except re.error:
            # Invalid regex - fall back to simple prefix matching
            return path.startswith(pattern.rstrip('*'))
    
    def _get_crawl_delay_for_agent(self, user_agent: str, robots_rules: Dict[str, Any]) -> float:
        """
        Get crawl delay for specific user agent.
        
        Args:
            user_agent: User agent string
            robots_rules: Parsed robots.txt rules
            
        Returns:
            Crawl delay in seconds
        """
        user_agents = robots_rules.get('user_agents', {})
        user_agent_lower = user_agent.lower()
        
        # Check specific user agent first
        if user_agent_lower in user_agents:
            delay = user_agents[user_agent_lower].get('crawl_delay')
            if delay is not None:
                return float(delay)
        
        # Try prefix matching for user agent
        for ua in user_agents:
            if user_agent_lower.startswith(ua + '/') or user_agent_lower.startswith(ua + ' ') or user_agent_lower == ua:
                delay = user_agents[ua].get('crawl_delay')
                if delay is not None:
                    return float(delay)
        
        # Check wildcard rules
        if '*' in user_agents:
            delay = user_agents['*'].get('crawl_delay')
            if delay is not None:
                return float(delay)
        
        return 0.0
    
    def _get_cache_key(self, url: str) -> str:
        """
        Generate cache key for robots.txt data.
        
        Args:
            url: Base URL
            
        Returns:
            Cache key string
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """
        Check if cached robots.txt is still valid.
        
        Args:
            cache_entry: Cache entry dictionary
            
        Returns:
            True if cache is still valid
        """
        timestamp = cache_entry.get('timestamp', 0)
        age = time.time() - timestamp
        return age < self.cache_ttl
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get robots.txt cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._cache_lock:
            valid_entries = 0
            expired_entries = 0
            
            for entry in self._robots_cache.values():
                if self._is_cache_valid(entry):
                    valid_entries += 1
                else:
                    expired_entries += 1
            
            return {
                'total_entries': len(self._robots_cache),
                'valid_entries': valid_entries,
                'expired_entries': expired_entries,
                'cache_ttl_seconds': self.cache_ttl
            }
    
    def clear_cache(self) -> None:
        """Clear robots.txt cache."""
        with self._cache_lock:
            cleared_count = len(self._robots_cache)
            self._robots_cache.clear()
            self.logger.debug(f"Cleared robots.txt cache ({cleared_count} entries)")


@dataclass
class ScrapingSession:
    """Results of a scraping session."""
    session_id: str
    start_time: datetime
    end_time: datetime
    total_urls: int
    successful_scrapes: int
    failed_scrapes: int
    skipped_urls: int
    errors: list  # List of error dictionaries
    total_content_size: int
    average_response_time: float


class WebScraper:
    """
    Main web scraper orchestrator that coordinates all scraping components.
    
    This class provides the main scraping workflow including:
    - Coordination of HTTPClient and ContentExtractor
    - URL processing with error handling
    - Session statistics and progress tracking
    - Integration with database storage
    - Dry-run mode support
    """
    
    def __init__(self, config, db_manager):
        """
        Initialize scraper with dependencies.
        
        Args:
            config: Configuration object with scraping settings
            db_manager: DatabaseManager instance for data storage
        """
        self.config = config
        self.db_manager = db_manager
        self.logger = get_logger(__name__)
        
        # Get scraping configuration
        scraping_config = config.get_scraping_config()
        self.urls_config = scraping_config.get('urls', [])
        self.settings = scraping_config.get('settings', {})
        
        # Initialize components
        self.http_client = HTTPClient(self.settings)
        self.content_extractor = ContentExtractor(self.settings)
        self.robot_checker = RobotChecker(self.settings, self.http_client)
        self.error_engine = ErrorDecisionEngine(self.settings)
        
        # Session tracking
        self.session_id = f"scrape_{int(time.time())}_{random.randint(1000, 9999)}"
        self.session_stats = {
            'total_urls': 0,
            'successful_scrapes': 0,
            'failed_scrapes': 0,
            'skipped_urls': 0,
            'errors': [],
            'total_content_size': 0,
            'total_response_time': 0,
            'start_time': None,
            'end_time': None
        }
        
        self.logger.info(f"WebScraper initialized with session_id={self.session_id}, "
                        f"{len(self.urls_config)} URLs configured")
    
    @log_performance
    def scrape_urls(self, dry_run: bool = False) -> ScrapingSession:
        """
        Execute scraping for all configured URLs.
        
        Args:
            dry_run: If True, simulate scraping without making actual requests
            
        Returns:
            ScrapingSession object with results and statistics
        """
        self.session_stats['start_time'] = datetime.now()
        
        if dry_run:
            return self._simulate_scraping()
        
        self.logger.info(f"Starting scraping session {self.session_id}")
        
        # Filter enabled URLs
        enabled_urls = [url_config for url_config in self.urls_config 
                       if url_config.get('enabled', True)]
        
        self.session_stats['total_urls'] = len(enabled_urls)
        
        if not enabled_urls:
            self.logger.warning("No enabled URLs found in configuration")
            return self._create_session_result()
        
        # Process each URL
        for i, url_config in enumerate(enabled_urls):
            url = url_config.get('url')
            name = url_config.get('name', url)
            
            self.logger.info(f"Processing {i+1}/{len(enabled_urls)}: {name} ({url})")
            
            try:
                scraped_content = self.scrape_single_url(url_config)
                if scraped_content:
                    # Store in database
                    self._store_content(scraped_content)
                    self.session_stats['successful_scrapes'] += 1
                    self.session_stats['total_content_size'] += len(scraped_content.content)
                    self.session_stats['total_response_time'] += scraped_content.response_time_ms
                else:
                    self.session_stats['skipped_urls'] += 1
                    
            except RobotsError as e:
                decision = self._handle_scraping_error(url, e)
                if decision.count_as_failure:
                    self.session_stats['failed_scrapes'] += 1
                else:
                    self.session_stats['skipped_urls'] += 1
            except Exception as e:
                decision = self._handle_scraping_error(url, e)
                if decision.count_as_failure:
                    self.session_stats['failed_scrapes'] += 1
                else:
                    self.session_stats['skipped_urls'] += 1
            
            # Apply delay between requests (except for last URL)
            if i < len(enabled_urls) - 1:
                self._apply_request_delay()
        
        self.session_stats['end_time'] = datetime.now()
        
        session_result = self._create_session_result()
        self.logger.info(f"Scraping session completed: {session_result.successful_scrapes}/"
                        f"{session_result.total_urls} successful")
        
        return session_result
    
    def scrape_single_url(self, url_config: Dict[str, Any]) -> Optional[ScrapedContent]:
        """
        Scrape a single URL with full error handling.
        
        Args:
            url_config: URL configuration dictionary containing 'url' and optional metadata
            
        Returns:
            ScrapedContent object or None if scraping failed/skipped
        """
        url = url_config.get('url')
        if not url:
            self.logger.error("URL configuration missing 'url' field")
            return None
        
        try:
            # Check robots.txt compliance before fetching
            if not self.robot_checker.can_fetch(url):
                self.logger.warning(f"Robots.txt disallows scraping {url}, skipping")
                raise RobotsError(f"Robots.txt disallows access to {url}", url)
            
            # Apply crawl delay if specified in robots.txt
            robots_delay = self.robot_checker.get_crawl_delay(url)
            configured_delay = self.settings.get('delay_between_requests', 1)
            
            # Use the longer delay (robots.txt takes precedence if higher)
            if robots_delay > configured_delay:
                extra_delay = robots_delay - configured_delay
                self.logger.debug(f"Applying additional robots.txt crawl delay: {extra_delay}s")
                time.sleep(extra_delay)
            
            # Check for conditional request opportunity
            last_modified_header = self._get_last_modified_for_url(url)
            
            # Fetch URL using HTTP client with conditional request if available
            response, metrics = self.http_client.fetch_url(url, if_modified_since=last_modified_header)
            
            # Handle 304 Not Modified response
            if response.status_code == 304:
                self.logger.info(f"Content not modified for {url} (304 response), skipping")
                return None
            
            # Add response time to response object for ContentExtractor
            response._response_time_ms = metrics.response_time_ms
            
            # Extract content
            scraped_content = self.content_extractor.extract_content(response, url)
            
            # Check if content already exists (duplicate detection)
            if self._check_for_duplicates(url, scraped_content.content_hash):
                self.logger.info(f"Content already exists for {url}, skipping")
                return None
            
            return scraped_content
            
        except RobotsError as e:
            self.logger.warning(f"Robots.txt violation for {url}: {e}")
            raise
        except NetworkError as e:
            self.logger.error(f"Network error for {url}: {e}")
            raise
        except ParseError as e:
            self.logger.error(f"Parse error for {url}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error for {url}: {type(e).__name__} - {str(e)}")
            raise
    
    def _simulate_scraping(self) -> ScrapingSession:
        """
        Simulate scraping process for dry-run mode.
        
        Returns:
            ScrapingSession with simulated results
        """
        self.logger.info("Simulating scraping process (dry-run mode)")
        
        enabled_urls = [url_config for url_config in self.urls_config 
                       if url_config.get('enabled', True)]
        
        self.session_stats['total_urls'] = len(enabled_urls)
        self.session_stats['successful_scrapes'] = len(enabled_urls)  # Assume all would succeed
        
        for url_config in enabled_urls:
            url = url_config.get('url')
            name = url_config.get('name', url)
            self.logger.info(f"Would scrape: {name} ({url})")
        
        return self._create_session_result()
    
    def _store_content(self, scraped_content: ScrapedContent) -> None:
        """
        Store scraped content in the database.
        
        Args:
            scraped_content: ScrapedContent object to store
        """
        try:
            record_id = self.db_manager.insert_content(scraped_content)
            self.logger.debug(f"Content stored successfully for {scraped_content.url} with ID {record_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to store content for {scraped_content.url}: {e}")
            raise
    
    def _check_for_duplicates(self, url: str, content_hash: str) -> bool:
        """
        Check if content hash already exists for URL and log content changes.
        
        Args:
            url: URL to check
            content_hash: Content hash to check
            
        Returns:
            True if content is a duplicate
        """
        try:
            # Check if exact content already exists
            if self.db_manager.content_exists(url, content_hash):
                self.logger.info(f"Duplicate content detected for {url} (hash: {content_hash[:12]}...)")
                return True
            
            # Check if we have any previous content for this URL
            latest_hash = self.db_manager.get_latest_content_hash(url)
            if latest_hash:
                if latest_hash != content_hash:
                    self.logger.info(f"Content change detected for {url}: "
                                   f"old_hash={latest_hash[:12]}... new_hash={content_hash[:12]}...")
                    # Content has changed - not a duplicate, should scrape
                    return False
                else:
                    # This case should already be caught above, but just in case
                    self.logger.debug(f"Content unchanged for {url}")
                    return True
            else:
                # First time scraping this URL
                self.logger.info(f"New URL detected for scraping: {url}")
                return False
                
        except Exception as e:
            self.logger.warning(f"Error checking for duplicates: {e}")
            return False  # Assume not duplicate if check fails
    
    def _get_last_modified_for_url(self, url: str) -> Optional[str]:
        """
        Get the Last-Modified header from the most recent scrape of a URL.
        
        Args:
            url: URL to check
            
        Returns:
            Last-Modified header value or None if not available
        """
        try:
            # Get the most recent content for this URL
            recent_content = self.db_manager.get_content_by_url(url, limit=1)
            if recent_content and len(recent_content) > 0:
                last_modified = recent_content[0].get('last_modified')
                if last_modified:
                    self.logger.debug(f"Found previous Last-Modified for {url}: {last_modified}")
                    return last_modified
            
            self.logger.debug(f"No previous Last-Modified found for {url}")
            return None
            
        except Exception as e:
            self.logger.warning(f"Error getting Last-Modified for {url}: {e}")
            return None
    
    def _handle_scraping_error(self, url: str, error: Exception, context: Dict[str, Any] = None) -> ErrorDecision:
        """
        Handle and log scraping errors using the enhanced ErrorDecisionEngine.
        
        Args:
            url: URL that failed
            error: Exception that occurred
            context: Additional context information for error handling
            
        Returns:
            ErrorDecision with handling instructions
        """
        # Build comprehensive context
        context = context or {}
        context.update({
            'url': url,
            'session_id': self.session_id,
            'session_stats': self.session_stats.copy(),
            'user_agent': self.settings.get('user_agent', 'WebScraper/1.0'),
            'timeout': self.settings.get('timeout', 30),
            'max_retries': self.settings.get('retry_attempts', 3)
        })
        
        # Get error handling decision from the engine
        decision = self.error_engine.get_error_decision(error, context)
        
        # Use enhanced structured logging
        self.error_engine.log_error_with_context(error, context, decision)
        
        # Build error info for session stats (backward compatibility)
        error_info = {
            'url': url,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': datetime.now().isoformat(),
            'decision': {
                'should_retry': decision.should_retry,
                'should_continue': decision.should_continue,
                'count_as_failure': decision.count_as_failure,
                'recovery_action': decision.recovery_action
            }
        }
        
        self.session_stats['errors'].append(error_info)
        
        # Execute recovery actions based on decision
        self._execute_recovery_action(decision, url, error, context)
        
        return decision
    
    def _execute_recovery_action(self, decision: ErrorDecision, url: str, error: Exception, context: Dict[str, Any]) -> None:
        """
        Execute recovery actions based on error decision with enhanced recovery strategies.
        
        Args:
            decision: Error handling decision
            url: URL that failed
            error: Exception that occurred
            context: Error context
        """
        if decision.recovery_action == 'save_partial_content':
            self._attempt_partial_content_recovery(url, error, context)
            
        elif decision.recovery_action == 'skip_url':
            self.logger.info(f"Skipping URL {url} due to {type(error).__name__}")
            
        elif decision.recovery_action == 'retry_with_backoff':
            self.logger.info(f"URL {url} will be retried with backoff")
            # Retry logic is handled at the HTTP client level
            
        elif decision.recovery_action == 'retry_database_operation':
            self._attempt_database_recovery(url, error, context)
            
        elif decision.recovery_action == 'stop_execution':
            self.logger.critical(f"Critical error for {url}, execution should be stopped")
            # This would typically raise an exception to stop the scraping process
            
        else:
            self.logger.debug(f"No specific recovery action for {url}")
    
    def _attempt_partial_content_recovery(self, url: str, error: Exception, context: Dict[str, Any]) -> None:
        """
        Attempt to save partial content when parsing fails.
        
        This implements graceful degradation by saving whatever content can be extracted
        even when full parsing fails.
        
        Args:
            url: URL that failed
            error: Parse error that occurred
            context: Error context
        """
        try:
            self.logger.info(f"Attempting partial content recovery for {url}")
            
            # Try to get raw HTML content from context if available
            raw_content = context.get('raw_content')
            response = context.get('response')
            
            if response and hasattr(response, 'text'):
                raw_content = response.text
            
            if raw_content:
                # Create minimal scraped content with just the raw HTML
                partial_content = ScrapedContent(
                    url=url,
                    title=f"[PARTIAL] Content from {url}",  # Indicate partial recovery
                    content=raw_content[:10000],  # Limit to first 10KB
                    content_hash=calculate_content_hash(raw_content),
                    scraped_at=datetime.now(),
                    response_status=getattr(response, 'status_code', 0) if response else 0,
                    response_time_ms=context.get('response_time_ms', 0),
                    content_length=len(raw_content)
                )
                
                # Try to save partial content
                try:
                    self.db_manager.insert_content(partial_content)
                    self.logger.info(f"Successfully saved partial content for {url}")
                    
                    # Update session stats for successful partial recovery
                    self.session_stats['successful_scrapes'] += 1
                    self.session_stats['total_content_size'] += len(raw_content)
                    
                except Exception as db_error:
                    self.logger.error(f"Failed to save partial content for {url}: {db_error}")
            else:
                self.logger.warning(f"No raw content available for partial recovery of {url}")
                
        except Exception as recovery_error:
            self.logger.error(f"Partial content recovery failed for {url}: {recovery_error}")
    
    def _attempt_database_recovery(self, url: str, error: Exception, context: Dict[str, Any]) -> None:
        """
        Attempt to recover from database errors with retry logic.
        
        Args:
            url: URL that had database error
            error: Database error that occurred
            context: Error context
        """
        try:
            self.logger.info(f"Attempting database recovery for {url}")
            
            # Check if we have content to retry saving
            scraped_content = context.get('scraped_content')
            if not scraped_content:
                self.logger.warning(f"No scraped content available for database recovery of {url}")
                return
            
            # Try database health check first
            if hasattr(self.db_manager, 'health_check'):
                try:
                    self.db_manager.health_check()
                    self.logger.info("Database health check passed, retrying content save")
                    
                    # Retry saving the content
                    self.db_manager.insert_content(scraped_content)
                    self.logger.info(f"Successfully recovered database operation for {url}")
                    
                    # Update session stats for successful recovery
                    self.session_stats['successful_scrapes'] += 1
                    if hasattr(scraped_content, 'content') and scraped_content.content:
                        self.session_stats['total_content_size'] += len(scraped_content.content)
                    
                except Exception as retry_error:
                    self.logger.error(f"Database recovery retry failed for {url}: {retry_error}")
                    
                except Exception as health_error:
                    self.logger.error(f"Database health check failed during recovery for {url}: {health_error}")
            
        except Exception as recovery_error:
            self.logger.error(f"Database recovery attempt failed for {url}: {recovery_error}")
    
    def _analyze_error_patterns(self) -> Dict[str, Any]:
        """
        Analyze error patterns for adaptive recovery strategies.
        
        Returns:
            Dictionary with error pattern analysis
        """
        error_rates = self.error_engine.get_error_rates()
        total_errors = len(self.session_stats['errors'])
        
        # Calculate error trend (recent vs overall)
        recent_errors = self.session_stats['errors'][-10:] if total_errors > 10 else self.session_stats['errors']
        recent_error_types = [e['error_type'] for e in recent_errors]
        
        analysis = {
            'total_errors': total_errors,
            'error_rates': error_rates,
            'recent_error_types': recent_error_types,
            'high_error_rate_threshold': 0.1,  # 10% error rate
            'recommendations': []
        }
        
        # Generate recommendations based on patterns
        for error_type, rate in error_rates.items():
            if rate > 0.1:  # High error rate
                if error_type == 'NetworkError':
                    analysis['recommendations'].append(
                        'Consider increasing timeout or reducing request rate due to high network error rate'
                    )
                elif error_type == 'ParseError':
                    analysis['recommendations'].append(
                        'Consider reviewing content extraction logic due to high parse error rate'
                    )
                elif error_type == 'RobotsError':
                    analysis['recommendations'].append(
                        'Consider reviewing robots.txt compliance settings due to high robots error rate'
                    )
        
        return analysis
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive error statistics including rates, trends, and analysis.
        
        Returns:
            Dictionary with error statistics, rates, and recommendations
        """
        pattern_analysis = self._analyze_error_patterns()
        
        return {
            'error_counts': self.error_engine.error_counts.copy(),
            'error_rates': self.error_engine.get_error_rates(),
            'total_requests': self.error_engine.total_requests,
            'session_errors': len(self.session_stats['errors']),
            'session_id': self.session_id,
            'pattern_analysis': pattern_analysis,
            'recovery_statistics': {
                'total_recovery_attempts': sum(1 for e in self.session_stats['errors'] 
                                             if e.get('decision', {}).get('recovery_action')),
                'partial_content_recoveries': sum(1 for e in self.session_stats['errors'] 
                                                if e.get('decision', {}).get('recovery_action') == 'save_partial_content'),
                'database_recoveries': sum(1 for e in self.session_stats['errors'] 
                                         if e.get('decision', {}).get('recovery_action') == 'retry_database_operation')
            }
        }
    
    def _apply_request_delay(self) -> None:
        """
        Apply configured delay between requests to be respectful to servers.
        """
        delay = self.settings.get('delay_between_requests', 1)
        if delay > 0:
            self.logger.debug(f"Applying request delay: {delay}s")
            time.sleep(delay)
    
    def _create_session_result(self) -> ScrapingSession:
        """
        Create ScrapingSession result object from current statistics.
        
        Returns:
            ScrapingSession object with complete results
        """
        start_time = self.session_stats['start_time'] or datetime.now()
        end_time = self.session_stats['end_time'] or datetime.now()
        
        # Calculate average response time
        successful_scrapes = self.session_stats['successful_scrapes']
        total_response_time = self.session_stats['total_response_time']
        average_response_time = (total_response_time / successful_scrapes) if successful_scrapes > 0 else 0.0
        
        return ScrapingSession(
            session_id=self.session_id,
            start_time=start_time,
            end_time=end_time,
            total_urls=self.session_stats['total_urls'],
            successful_scrapes=successful_scrapes,
            failed_scrapes=self.session_stats['failed_scrapes'],
            skipped_urls=self.session_stats['skipped_urls'],
            errors=self.session_stats['errors'],
            total_content_size=self.session_stats['total_content_size'],
            average_response_time=average_response_time
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed scraping statistics.
        
        Returns:
            Dictionary containing comprehensive statistics
        """
        return {
            'session_id': self.session_id,
            'current_stats': self.session_stats.copy(),
            'http_client_stats': self.http_client.get_statistics(),
            'configuration': {
                'total_configured_urls': len(self.urls_config),
                'enabled_urls': len([u for u in self.urls_config if u.get('enabled', True)]),
                'settings': self.settings
            }
        }
    
    def close(self) -> None:
        """
        Close scraper and cleanup resources.
        """
        if hasattr(self.http_client, 'close'):
            self.http_client.close()
        self.logger.debug("WebScraper resources cleaned up")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
