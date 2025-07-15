import logging
import logging.handlers
import os
import hashlib
import time
import re
from functools import wraps
from typing import Dict, Any, Optional, Callable
from urllib.parse import urlparse


# Global logger registry to avoid duplicate logger creation
_logger_registry = {}


def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """
    Configure logging based on configuration settings.
    
    Sets up rotating file handlers, structured formatting, and console output.
    
    Args:
        config: Dictionary containing logging configuration with keys:
            - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            - file: Log file path
            - max_size_mb: Maximum log file size in MB
            - backup_count: Number of backup log files to keep
            - format: Log message format string
    
    Returns:
        Configured root logger instance
        
    Raises:
        ValueError: If configuration is invalid
        OSError: If log directory cannot be created
    """
    try:
        # Extract configuration values
        log_level = config.get('level', 'INFO')
        log_file = config.get('file', 'logs/scraper.log')
        max_size_mb = config.get('max_size_mb', 10)
        backup_count = config.get('backup_count', 5)
        log_format = config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # Convert log level string to logging constant
        numeric_level = getattr(logging, log_level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError(f'Invalid log level: {log_level}')
        
        # Create root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        
        # Clear existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(
            fmt=log_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Set up rotating file handler
        max_bytes = max_size_mb * 1024 * 1024  # Convert MB to bytes
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Set up console handler for INFO and above
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Log the successful setup
        root_logger.info("Logging system initialized successfully")
        root_logger.info(f"Log level: {log_level}")
        root_logger.info(f"Log file: {log_file}")
        root_logger.info(f"Max file size: {max_size_mb} MB")
        root_logger.info(f"Backup count: {backup_count}")
        
        return root_logger
        
    except Exception as e:
        # If logging setup fails, create a basic console logger
        fallback_logger = logging.getLogger()
        fallback_logger.setLevel(logging.ERROR)
        if not fallback_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
            fallback_logger.addHandler(handler)
        
        fallback_logger.error(f"Failed to set up logging: {e}")
        raise


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Creates a logger with the specified name and ensures it uses the
    parent logger's configuration. Maintains a registry to avoid
    duplicate logger creation.
    
    Args:
        name: Name of the logger (typically __name__ of the module)
        
    Returns:
        Logger instance for the specified module
    """
    # Check if logger already exists in registry
    if name in _logger_registry:
        return _logger_registry[name]
    
    # Create new logger
    logger = logging.getLogger(f"WebScraper.{name}")
    
    # Store in registry
    _logger_registry[name] = logger
    
    return logger


def log_performance(func: Callable) -> Callable:
    """
    Decorator to log function execution time and performance metrics.
    
    Logs the function name, execution time, and any exceptions that occur.
    Uses DEBUG level for performance logs to avoid cluttering INFO logs.
    
    Args:
        func: Function to be decorated
        
    Returns:
        Decorated function with performance logging
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get logger for the function's module
        logger = get_logger(func.__module__)
        
        # Record start time
        start_time = time.time()
        function_name = f"{func.__module__}.{func.__name__}"
        
        logger.debug(f"Starting execution of {function_name}")
        
        try:
            # Execute the function
            result = func(*args, **kwargs)
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Log successful execution
            logger.debug(f"Completed {function_name} in {execution_time:.3f} seconds")
            
            return result
            
        except Exception as e:
            # Calculate execution time even for failed executions
            execution_time = time.time() - start_time
            
            # Log failed execution
            logger.error(f"Failed {function_name} after {execution_time:.3f} seconds: {e}")
            
            # Re-raise the exception
            raise
    
    return wrapper


def calculate_content_hash(content: str) -> str:
    """
    Calculate SHA-256 hash of content for duplicate detection.
    
    Args:
        content: Content string to hash
        
    Returns:
        Hexadecimal hash string
    """
    if not content:
        return ""
    
    # Convert to bytes and calculate hash
    content_bytes = content.encode('utf-8')
    hash_object = hashlib.sha256(content_bytes)
    return hash_object.hexdigest()


def validate_url(url: str) -> bool:
    """
    Validate URL format.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if URL is valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc]) and result.scheme in ['http', 'https']
    except Exception:
        return False


def format_bytes(bytes_count: int) -> str:
    """
    Format bytes as human-readable string.
    
    Args:
        bytes_count: Number of bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB", "2.3 KB")
    """
    if bytes_count == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    
    return f"{bytes_count:.1f} PB"


def get_current_timestamp() -> str:
    """
    Get current timestamp in ISO format.
    
    Returns:
        ISO formatted timestamp string
    """
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime())


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file operations.
    
    Removes or replaces characters that could be problematic in filenames.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove or replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip('. ')
    
    # Ensure filename is not empty
    if not sanitized:
        sanitized = 'unnamed'
    
    # Limit length to 255 characters (common filesystem limit)
    if len(sanitized) > 255:
        sanitized = sanitized[:255]
    
    return sanitized


def retry_with_backoff(func: Callable, max_retries: int = 3, delay: float = 1.0, 
                      backoff_factor: float = 2.0) -> Callable:
    """
    Retry function with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each retry
        
    Returns:
        Decorated function with retry logic
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                    raise
                
                retry_delay = delay * (backoff_factor ** attempt)
                logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                time.sleep(retry_delay)
        
        return None  # Should never reach here
    
    return wrapper


def log_system_info():
    """
    Log system information for debugging purposes.
    
    Logs Python version, platform, and other relevant system information.
    """
    import sys
    import platform
    
    logger = get_logger(__name__)
    
    logger.info("System Information:")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {platform.platform()}")
    logger.info(f"Architecture: {platform.architecture()[0]}")
    logger.info(f"Working directory: {os.getcwd()}")


def create_performance_logger(name: str) -> logging.Logger:
    """
    Create a specialized logger for performance metrics.
    
    Args:
        name: Name of the performance logger
        
    Returns:
        Logger configured for performance monitoring
    """
    perf_logger = logging.getLogger(f"WebScraper.Performance.{name}")
    
    # Set up a separate file handler for performance logs if needed
    # This could be configured to write to a separate performance log file
    
    return perf_logger


