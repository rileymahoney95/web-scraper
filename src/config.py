import os
import yaml
import re
from typing import Dict, Any, List
from urllib.parse import urlparse
import logging


class ConfigError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class Config:
    """
    Configuration management class that handles YAML configuration files,
    environment variable substitution, and comprehensive validation.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to the configuration file
        """
        self.config_path = config_path
        self.config_data = {}
        self.logger = logging.getLogger(__name__)
    
    def load(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file with environment variable substitution.
        
        Returns:
            Dictionary containing the loaded configuration
            
        Raises:
            ConfigError: If configuration file cannot be loaded or is invalid
        """
        try:
            if not os.path.exists(self.config_path):
                raise ConfigError(f"Configuration file not found: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.config_data = yaml.safe_load(file)
            
            if not self.config_data:
                raise ConfigError("Configuration file is empty or invalid")
            
            # Substitute environment variables
            self.config_data = self._substitute_env_vars(self.config_data)
            
            # Validate configuration
            if not self.validate():
                raise ConfigError("Configuration validation failed")
            
            self.logger.info("Configuration loaded successfully from %s", self.config_path)
            return self.config_data
            
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise ConfigError(f"Error loading configuration: {e}")
    
    def validate(self) -> bool:
        """
        Validate the entire configuration.
        
        Returns:
            True if configuration is valid
            
        Raises:
            ConfigError: If validation fails
        """
        if not self.config_data:
            raise ConfigError("No configuration data loaded")
        
        # Check required top-level sections
        required_sections = ['database', 'scraping', 'logging']
        for section in required_sections:
            if section not in self.config_data:
                raise ConfigError(f"Required configuration section '{section}' not found")
        
        # Validate each section
        self._validate_database_config(self.config_data['database'])
        self._validate_scraping_config(self.config_data['scraping'])
        self._validate_logging_config(self.config_data['logging'])
        
        return True
    
    def get_database_config(self) -> Dict[str, Any]:
        """
        Get database configuration section.
        
        Returns:
            Dictionary containing database configuration
        """
        if 'database' not in self.config_data:
            raise ConfigError("Database configuration not found")
        return self.config_data['database']
    
    def get_scraping_config(self) -> Dict[str, Any]:
        """
        Get scraping configuration section.
        
        Returns:
            Dictionary containing scraping configuration
        """
        if 'scraping' not in self.config_data:
            raise ConfigError("Scraping configuration not found")
        return self.config_data['scraping']
    
    def get_logging_config(self) -> Dict[str, Any]:
        """
        Get logging configuration section.
        
        Returns:
            Dictionary containing logging configuration
        """
        if 'logging' not in self.config_data:
            raise ConfigError("Logging configuration not found")
        return self.config_data['logging']
    
    def _substitute_env_vars(self, config: Dict) -> Dict:
        """
        Recursively substitute environment variables in configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Configuration dictionary with environment variables substituted
        """
        if isinstance(config, dict):
            return {key: self._substitute_env_vars(value) for key, value in config.items()}
        elif isinstance(config, list):
            return [self._substitute_env_vars(item) for item in config]
        elif isinstance(config, str):
            # Pattern to match ${VAR_NAME} or ${VAR_NAME:-default_value}
            pattern = r'\$\{([^}]+)\}'
            
            def replace_var(match):
                var_expr = match.group(1)
                if ':-' in var_expr:
                    var_name, default_value = var_expr.split(':-', 1)
                    return os.getenv(var_name.strip(), default_value.strip())
                else:
                    var_name = var_expr.strip()
                    env_value = os.getenv(var_name)
                    if env_value is None:
                        raise ConfigError(f"Environment variable '{var_name}' not found")
                    return env_value
            
            return re.sub(pattern, replace_var, config)
        else:
            return config
    
    def _validate_database_config(self, config: Dict) -> bool:
        """
        Validate database configuration.
        
        Args:
            config: Database configuration dictionary
            
        Returns:
            True if valid
            
        Raises:
            ConfigError: If validation fails
        """
        required_fields = ['host', 'port', 'database', 'username', 'password']
        
        for field in required_fields:
            if field not in config:
                raise ConfigError(f"Database configuration missing required field: {field}")
            if not config[field]:
                raise ConfigError(f"Database configuration field '{field}' cannot be empty")
        
        # Validate port is a valid integer
        try:
            port = int(config['port'])
            if port < 1 or port > 65535:
                raise ConfigError("Database port must be between 1 and 65535")
        except (ValueError, TypeError):
            raise ConfigError("Database port must be a valid integer")
        
        # Validate optional fields
        if 'max_connections' in config:
            try:
                max_conn = int(config['max_connections'])
                if max_conn < 1:
                    raise ConfigError("Database max_connections must be greater than 0")
            except (ValueError, TypeError):
                raise ConfigError("Database max_connections must be a valid integer")
        
        if 'connection_timeout' in config:
            try:
                timeout = int(config['connection_timeout'])
                if timeout < 1:
                    raise ConfigError("Database connection_timeout must be greater than 0")
            except (ValueError, TypeError):
                raise ConfigError("Database connection_timeout must be a valid integer")
        
        return True
    
    def _validate_scraping_config(self, config: Dict) -> bool:
        """
        Validate scraping configuration.
        
        Args:
            config: Scraping configuration dictionary
            
        Returns:
            True if valid
            
        Raises:
            ConfigError: If validation fails
        """
        # Check required sections
        if 'urls' not in config:
            raise ConfigError("Scraping configuration missing 'urls' section")
        if 'settings' not in config:
            raise ConfigError("Scraping configuration missing 'settings' section")
        
        # Validate URLs
        urls = config['urls']
        if not isinstance(urls, list):
            raise ConfigError("Scraping 'urls' must be a list")
        
        if not urls:
            raise ConfigError("Scraping 'urls' list cannot be empty")
        
        for i, url_config in enumerate(urls):
            if not isinstance(url_config, dict):
                raise ConfigError(f"URL configuration {i} must be a dictionary")
            
            required_url_fields = ['url', 'name', 'enabled']
            for field in required_url_fields:
                if field not in url_config:
                    raise ConfigError(f"URL configuration {i} missing required field: {field}")
            
            # Validate URL format
            url = url_config['url']
            if not self._is_valid_url(url):
                raise ConfigError(f"Invalid URL in configuration {i}: {url}")
            
            # Validate enabled is boolean
            if not isinstance(url_config['enabled'], bool):
                raise ConfigError(f"URL configuration {i} 'enabled' must be a boolean")
        
        # Validate settings
        settings = config['settings']
        if not isinstance(settings, dict):
            raise ConfigError("Scraping 'settings' must be a dictionary")
        
        # Validate numeric settings
        numeric_settings = {
            'timeout': (1, 300),  # 1 second to 5 minutes
            'retry_attempts': (0, 10),
            'retry_delay': (0, 60),
            'delay_between_requests': (0, 60)
        }
        
        for setting, (min_val, max_val) in numeric_settings.items():
            if setting in settings:
                try:
                    value = int(settings[setting])
                    if value < min_val or value > max_val:
                        raise ConfigError(f"Scraping setting '{setting}' must be between {min_val} and {max_val}")
                except (ValueError, TypeError):
                    raise ConfigError(f"Scraping setting '{setting}' must be a valid integer")
        
        # Validate boolean settings
        if 'respect_robots_txt' in settings:
            if not isinstance(settings['respect_robots_txt'], bool):
                raise ConfigError("Scraping setting 'respect_robots_txt' must be a boolean")
        
        return True
    
    def _validate_logging_config(self, config: Dict) -> bool:
        """
        Validate logging configuration.
        
        Args:
            config: Logging configuration dictionary
            
        Returns:
            True if valid
            
        Raises:
            ConfigError: If validation fails
        """
        # Check required fields
        required_fields = ['level', 'file', 'max_size_mb', 'backup_count']
        
        for field in required_fields:
            if field not in config:
                raise ConfigError(f"Logging configuration missing required field: {field}")
        
        # Validate log level
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if config['level'] not in valid_levels:
            raise ConfigError(f"Logging level must be one of: {', '.join(valid_levels)}")
        
        # Validate log file path
        log_file = config['file']
        if not isinstance(log_file, str) or not log_file:
            raise ConfigError("Logging file path must be a non-empty string")
        
        # Check if log directory exists or can be created
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError as e:
                raise ConfigError(f"Cannot create log directory '{log_dir}': {e}")
        
        # Validate numeric settings
        try:
            max_size = int(config['max_size_mb'])
            if max_size < 1:
                raise ConfigError("Logging max_size_mb must be greater than 0")
        except (ValueError, TypeError):
            raise ConfigError("Logging max_size_mb must be a valid integer")
        
        try:
            backup_count = int(config['backup_count'])
            if backup_count < 0:
                raise ConfigError("Logging backup_count must be greater than or equal to 0")
        except (ValueError, TypeError):
            raise ConfigError("Logging backup_count must be a valid integer")
        
        return True
    
    def _is_valid_url(self, url: str) -> bool:
        """
        Validate URL format.
        
        Args:
            url: URL string to validate
            
        Returns:
            True if URL is valid
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc]) and result.scheme in ['http', 'https']
        except Exception:
            return False
