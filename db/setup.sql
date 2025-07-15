-- Database Setup Script for Web Scraper Application
-- This script creates the database, user, schema, and necessary permissions

-- Create database
CREATE DATABASE web_scraper;

-- Connect to the new database
\c web_scraper;

-- Create scraper user with secure password
CREATE USER scraper_user WITH PASSWORD 'secure_password';

-- Main table for storing scraped content
CREATE TABLE scraped_content (
    id SERIAL PRIMARY KEY,
    url VARCHAR(2048) NOT NULL,
    title VARCHAR(1024),
    content TEXT,
    content_hash VARCHAR(64),
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    response_status INTEGER,
    response_time_ms INTEGER,
    content_length INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX idx_scraped_content_url_date ON scraped_content(url, scraped_at);
CREATE INDEX idx_scraped_content_hash ON scraped_content(content_hash);
CREATE INDEX idx_scraped_content_created_at ON scraped_content(created_at);

-- Grant all necessary permissions to scraper_user
GRANT ALL PRIVILEGES ON DATABASE web_scraper TO scraper_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO scraper_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO scraper_user;

-- Create additional table for scraping statistics (optional for monitoring)
CREATE TABLE scraping_stats (
    id SERIAL PRIMARY KEY,
    scrape_session_id VARCHAR(64),
    total_urls INTEGER,
    successful_scrapes INTEGER,
    failed_scrapes INTEGER,
    total_execution_time_ms INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Index for scraping stats
CREATE INDEX idx_scraping_stats_session ON scraping_stats(scrape_session_id);
CREATE INDEX idx_scraping_stats_date ON scraping_stats(started_at);

-- Grant permissions for the stats table
GRANT ALL PRIVILEGES ON scraping_stats TO scraper_user;

-- Create view for recent scraping activity
CREATE VIEW recent_scrapes AS
SELECT 
    url,
    title,
    response_status,
    response_time_ms,
    content_length,
    scraped_at
FROM scraped_content
WHERE scraped_at >= NOW() - INTERVAL '7 days'
ORDER BY scraped_at DESC;

-- Grant permission to view
GRANT SELECT ON recent_scrapes TO scraper_user;
