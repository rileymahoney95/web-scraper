"""
Advanced database query operations for web scraper analytics and reporting.

This module provides comprehensive analytics, reporting, and bulk operation
capabilities for the web scraper database. It includes content statistics,
trend analysis, advanced search, and efficient bulk operations.
"""

import logging
import json
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

from utils import get_logger, log_performance


@dataclass
class ContentStatistics:
    """Data class for content statistics."""
    total_content: int
    unique_urls: int
    status_distribution: Dict[int, int]
    avg_response_time_ms: float
    avg_content_length: int
    content_by_day: Dict[str, int]
    most_scraped_urls: List[Dict[str, Any]]
    least_scraped_urls: List[Dict[str, Any]]
    error_rate: float
    success_rate: float


@dataclass
class TrendAnalysis:
    """Data class for trend analysis results."""
    period_days: int
    success_rate_trend: List[Dict[str, Any]]
    response_time_trend: List[Dict[str, Any]]
    content_change_frequency: Dict[str, int]
    error_patterns: List[Dict[str, Any]]
    volume_trend: List[Dict[str, Any]]


@dataclass
class SearchResult:
    """Data class for search results."""
    total_matches: int
    results: List[Dict[str, Any]]
    facets: Dict[str, Dict[str, int]]
    query_time_ms: float


class DatabaseAnalytics:
    """
    Advanced analytics and reporting for scraped content.
    
    Provides comprehensive analytics capabilities including:
    - Content statistics and metrics
    - Scraping performance trends
    - Advanced search and filtering
    - Report generation in multiple formats
    """
    
    def __init__(self, database_manager):
        """
        Initialize DatabaseAnalytics.
        
        Args:
            database_manager: DatabaseManager instance
        """
        self.db_manager = database_manager
        self.logger = get_logger(__name__)
    
    @log_performance
    def get_content_statistics(self, start_date: Optional[datetime] = None, 
                             end_date: Optional[datetime] = None) -> ContentStatistics:
        """
        Get comprehensive content statistics.
        
        Args:
            start_date: Start date for analysis (default: 30 days ago)
            end_date: End date for analysis (default: now)
            
        Returns:
            ContentStatistics object with comprehensive metrics
        """
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        try:
            with self.db_manager._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Total content count
                    cursor.execute("""
                        SELECT COUNT(*) as total_content,
                               COUNT(DISTINCT url) as unique_urls
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                    """, (start_date, end_date))
                    basic_stats = cursor.fetchone()
                    
                    # Status distribution
                    cursor.execute("""
                        SELECT response_status, COUNT(*) as count
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                        GROUP BY response_status
                        ORDER BY count DESC
                    """, (start_date, end_date))
                    status_dist = {row['response_status']: row['count'] for row in cursor.fetchall()}
                    
                    # Average response time and content length
                    cursor.execute("""
                        SELECT AVG(response_time_ms) as avg_response_time,
                               AVG(content_length) as avg_content_length
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                          AND response_time_ms IS NOT NULL
                          AND content_length IS NOT NULL
                    """, (start_date, end_date))
                    avg_stats = cursor.fetchone()
                    
                    # Content by day
                    cursor.execute("""
                        SELECT DATE(scraped_at) as date, COUNT(*) as count
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                        GROUP BY DATE(scraped_at)
                        ORDER BY date
                    """, (start_date, end_date))
                    content_by_day = {str(row['date']): row['count'] for row in cursor.fetchall()}
                    
                    # Most scraped URLs
                    cursor.execute("""
                        SELECT url, COUNT(*) as scrape_count,
                               MAX(scraped_at) as last_scraped,
                               AVG(response_time_ms) as avg_response_time
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                        GROUP BY url
                        ORDER BY scrape_count DESC
                        LIMIT 10
                    """, (start_date, end_date))
                    most_scraped = [dict(row) for row in cursor.fetchall()]
                    
                    # Least scraped URLs (URLs that appear only once)
                    cursor.execute("""
                        SELECT url, COUNT(*) as scrape_count,
                               MAX(scraped_at) as last_scraped,
                               AVG(response_time_ms) as avg_response_time
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                        GROUP BY url
                        HAVING COUNT(*) = 1
                        ORDER BY last_scraped DESC
                        LIMIT 10
                    """, (start_date, end_date))
                    least_scraped = [dict(row) for row in cursor.fetchall()]
                    
                    # Calculate rates
                    total_requests = basic_stats['total_content'] or 0
                    successful_requests = status_dist.get(200, 0)
                    error_requests = sum(count for status, count in status_dist.items() 
                                       if status and status >= 400)
                    
                    success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
                    error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0
                    
                    return ContentStatistics(
                        total_content=basic_stats['total_content'] or 0,
                        unique_urls=basic_stats['unique_urls'] or 0,
                        status_distribution=status_dist,
                        avg_response_time_ms=float(avg_stats['avg_response_time'] or 0),
                        avg_content_length=int(avg_stats['avg_content_length'] or 0),
                        content_by_day=content_by_day,
                        most_scraped_urls=most_scraped,
                        least_scraped_urls=least_scraped,
                        error_rate=error_rate,
                        success_rate=success_rate
                    )
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to get content statistics: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error getting content statistics: {e}")
            raise
    
    @log_performance
    def get_scraping_trends(self, days: int = 30) -> TrendAnalysis:
        """
        Analyze scraping trends over time.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            TrendAnalysis object with trend data
        """
        start_date = datetime.now() - timedelta(days=days)
        end_date = datetime.now()
        
        try:
            with self.db_manager._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Success rate trend by day
                    cursor.execute("""
                        SELECT DATE(scraped_at) as date,
                               COUNT(*) as total_requests,
                               COUNT(CASE WHEN response_status = 200 THEN 1 END) as successful_requests,
                               ROUND(
                                   COUNT(CASE WHEN response_status = 200 THEN 1 END) * 100.0 / COUNT(*), 2
                               ) as success_rate
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                        GROUP BY DATE(scraped_at)
                        ORDER BY date
                    """, (start_date, end_date))
                    success_rate_trend = [dict(row) for row in cursor.fetchall()]
                    
                    # Response time trend by day
                    cursor.execute("""
                        SELECT DATE(scraped_at) as date,
                               AVG(response_time_ms) as avg_response_time,
                               MIN(response_time_ms) as min_response_time,
                               MAX(response_time_ms) as max_response_time,
                               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms) as median_response_time
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                          AND response_time_ms IS NOT NULL
                        GROUP BY DATE(scraped_at)
                        ORDER BY date
                    """, (start_date, end_date))
                    response_time_trend = [dict(row) for row in cursor.fetchall()]
                    
                    # Content change frequency (based on content hash changes)
                    cursor.execute("""
                        WITH url_changes AS (
                            SELECT url,
                                   COUNT(DISTINCT content_hash) as unique_versions,
                                   COUNT(*) as total_scrapes
                            FROM scraped_content 
                            WHERE scraped_at BETWEEN %s AND %s
                            GROUP BY url
                        )
                        SELECT 
                            CASE 
                                WHEN unique_versions = 1 THEN 'No Changes'
                                WHEN unique_versions::float / total_scrapes < 0.1 THEN 'Rarely Changes'
                                WHEN unique_versions::float / total_scrapes < 0.3 THEN 'Sometimes Changes'
                                ELSE 'Frequently Changes'
                            END as change_frequency,
                            COUNT(*) as url_count
                        FROM url_changes
                        GROUP BY 1
                        ORDER BY url_count DESC
                    """, (start_date, end_date))
                    change_freq = {row['change_frequency']: row['url_count'] for row in cursor.fetchall()}
                    
                    # Error patterns by status code over time
                    cursor.execute("""
                        SELECT DATE(scraped_at) as date,
                               response_status,
                               COUNT(*) as error_count
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                          AND response_status >= 400
                        GROUP BY DATE(scraped_at), response_status
                        ORDER BY date, error_count DESC
                    """, (start_date, end_date))
                    error_patterns = [dict(row) for row in cursor.fetchall()]
                    
                    # Volume trend by day
                    cursor.execute("""
                        SELECT DATE(scraped_at) as date,
                               COUNT(*) as request_count,
                               COUNT(DISTINCT url) as unique_urls,
                               SUM(content_length) as total_content_size
                        FROM scraped_content 
                        WHERE scraped_at BETWEEN %s AND %s
                        GROUP BY DATE(scraped_at)
                        ORDER BY date
                    """, (start_date, end_date))
                    volume_trend = [dict(row) for row in cursor.fetchall()]
                    
                    return TrendAnalysis(
                        period_days=days,
                        success_rate_trend=success_rate_trend,
                        response_time_trend=response_time_trend,
                        content_change_frequency=change_freq,
                        error_patterns=error_patterns,
                        volume_trend=volume_trend
                    )
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to get scraping trends: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error getting scraping trends: {e}")
            raise
    
    @log_performance
    def search_content(self, query: str = "", filters: Optional[Dict[str, Any]] = None,
                      limit: int = 100, offset: int = 0) -> SearchResult:
        """
        Advanced content search with filtering.
        
        Args:
            query: Search query for title and content (case-insensitive)
            filters: Dictionary of filters:
                - start_date: Start date for search
                - end_date: End date for search
                - status_codes: List of status codes to include
                - urls: List of URL patterns to match
                - min_content_length: Minimum content length
                - max_content_length: Maximum content length
            limit: Maximum number of results to return
            offset: Number of results to skip
            
        Returns:
            SearchResult object with matches and facets
        """
        if filters is None:
            filters = {}
        
        search_start = datetime.now()
        
        try:
            with self.db_manager._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Build WHERE clause dynamically
                    where_conditions = []
                    params = []
                    
                    # Text search
                    if query:
                        where_conditions.append("""
                            (LOWER(title) LIKE LOWER(%s) OR LOWER(content) LIKE LOWER(%s) OR LOWER(url) LIKE LOWER(%s))
                        """)
                        search_pattern = f"%{query}%"
                        params.extend([search_pattern, search_pattern, search_pattern])
                    
                    # Date filters
                    if filters.get('start_date'):
                        where_conditions.append("scraped_at >= %s")
                        params.append(filters['start_date'])
                    
                    if filters.get('end_date'):
                        where_conditions.append("scraped_at <= %s")
                        params.append(filters['end_date'])
                    
                    # Status code filter
                    if filters.get('status_codes'):
                        status_codes = filters['status_codes']
                        placeholders = ','.join(['%s'] * len(status_codes))
                        where_conditions.append(f"response_status IN ({placeholders})")
                        params.extend(status_codes)
                    
                    # URL pattern filter
                    if filters.get('urls'):
                        url_conditions = []
                        for url_pattern in filters['urls']:
                            url_conditions.append("url LIKE %s")
                            params.append(f"%{url_pattern}%")
                        where_conditions.append(f"({' OR '.join(url_conditions)})")
                    
                    # Content length filters
                    if filters.get('min_content_length'):
                        where_conditions.append("content_length >= %s")
                        params.append(filters['min_content_length'])
                    
                    if filters.get('max_content_length'):
                        where_conditions.append("content_length <= %s")
                        params.append(filters['max_content_length'])
                    
                    # Build final WHERE clause
                    where_clause = ""
                    if where_conditions:
                        where_clause = "WHERE " + " AND ".join(where_conditions)
                    
                    # Get total count
                    count_query = f"""
                        SELECT COUNT(*) as total
                        FROM scraped_content
                        {where_clause}
                    """
                    cursor.execute(count_query, params)
                    total_matches = cursor.fetchone()['total']
                    
                    # Get search results
                    search_query = f"""
                        SELECT id, url, title, content_hash, response_status,
                               response_time_ms, content_length, scraped_at,
                               CASE 
                                   WHEN content IS NOT NULL 
                                   THEN LEFT(content, 200) || '...'
                                   ELSE NULL
                               END as content_preview
                        FROM scraped_content
                        {where_clause}
                        ORDER BY scraped_at DESC
                        LIMIT %s OFFSET %s
                    """
                    cursor.execute(search_query, params + [limit, offset])
                    results = [dict(row) for row in cursor.fetchall()]
                    
                    # Get facets (aggregations)
                    facets = {}
                    
                    # Status code facets
                    facet_query = f"""
                        SELECT response_status, COUNT(*) as count
                        FROM scraped_content
                        {where_clause}
                        GROUP BY response_status
                        ORDER BY count DESC
                    """
                    cursor.execute(facet_query, params)
                    facets['status_codes'] = {str(row['response_status']): row['count'] 
                                            for row in cursor.fetchall()}
                    
                    # Date facets (by month)
                    facet_query = f"""
                        SELECT DATE_TRUNC('month', scraped_at) as month, COUNT(*) as count
                        FROM scraped_content
                        {where_clause}
                        GROUP BY DATE_TRUNC('month', scraped_at)
                        ORDER BY month DESC
                        LIMIT 12
                    """
                    cursor.execute(facet_query, params)
                    facets['months'] = {str(row['month'].date()): row['count'] 
                                      for row in cursor.fetchall()}
                    
                    # Content length facets
                    facet_query = f"""
                        SELECT 
                            CASE 
                                WHEN content_length < 1000 THEN 'Small (<1KB)'
                                WHEN content_length < 10000 THEN 'Medium (1-10KB)'
                                WHEN content_length < 100000 THEN 'Large (10-100KB)'
                                ELSE 'Very Large (>100KB)'
                            END as size_category,
                            COUNT(*) as count
                        FROM scraped_content
                        {where_clause}
                        AND content_length IS NOT NULL
                        GROUP BY 1
                        ORDER BY count DESC
                    """
                    cursor.execute(facet_query, params)
                    facets['content_sizes'] = {row['size_category']: row['count'] 
                                             for row in cursor.fetchall()}
                    
                    query_time = (datetime.now() - search_start).total_seconds() * 1000
                    
                    return SearchResult(
                        total_matches=total_matches,
                        results=results,
                        facets=facets,
                        query_time_ms=query_time
                    )
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to search content: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error searching content: {e}")
            raise
    
    @log_performance
    def generate_scraping_report(self, session_id: Optional[str] = None, 
                               format: str = 'dict') -> Union[Dict[str, Any], str]:
        """
        Generate comprehensive scraping session reports.
        
        Args:
            session_id: Specific session ID to report on (default: latest session)
            format: Output format ('dict', 'json', 'csv', 'html')
            
        Returns:
            Report in requested format
        """
        try:
            with self.db_manager._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Get session info
                    if session_id:
                        session_condition = "WHERE scrape_session_id = %s"
                        session_params = [session_id]
                    else:
                        session_condition = "ORDER BY started_at DESC LIMIT 1"
                        session_params = []
                    
                    cursor.execute(f"""
                        SELECT *
                        FROM scraping_stats
                        {session_condition}
                    """, session_params)
                    session_info = cursor.fetchone()
                    
                    if not session_info:
                        raise ValueError("No session found matching criteria")
                    
                    actual_session_id = session_info['scrape_session_id']
                    
                    # Get detailed content info for this session
                    # Note: This requires adding session tracking to scraped_content table
                    # For now, we'll use time-based approximation
                    session_start = session_info['started_at']
                    session_end = session_info['completed_at'] or datetime.now()
                    
                    cursor.execute("""
                        SELECT 
                            url,
                            response_status,
                            response_time_ms,
                            content_length,
                            scraped_at,
                            CASE 
                                WHEN response_status = 200 THEN 'Success'
                                WHEN response_status >= 400 THEN 'Error'
                                ELSE 'Other'
                            END as result_category
                        FROM scraped_content
                        WHERE scraped_at BETWEEN %s AND %s
                        ORDER BY scraped_at
                    """, (session_start, session_end))
                    content_details = [dict(row) for row in cursor.fetchall()]
                    
                    # Build comprehensive report
                    report = {
                        'session_info': dict(session_info),
                        'summary': {
                            'session_id': actual_session_id,
                            'start_time': session_start.isoformat(),
                            'end_time': session_end.isoformat() if session_end else None,
                            'duration_seconds': (session_end - session_start).total_seconds() if session_end else None,
                            'total_urls': session_info['total_urls'],
                            'successful_scrapes': session_info['successful_scrapes'],
                            'failed_scrapes': session_info['failed_scrapes'],
                            'success_rate': (session_info['successful_scrapes'] / session_info['total_urls'] * 100) 
                                          if session_info['total_urls'] > 0 else 0
                        },
                        'performance_metrics': {
                            'avg_response_time_ms': sum(row['response_time_ms'] or 0 for row in content_details) / len(content_details) if content_details else 0,
                            'total_content_size': sum(row['content_length'] or 0 for row in content_details),
                            'requests_per_second': len(content_details) / ((session_end - session_start).total_seconds()) if session_end and (session_end - session_start).total_seconds() > 0 else 0
                        },
                        'status_breakdown': {},
                        'url_details': content_details,
                        'errors': [row for row in content_details if row['response_status'] >= 400],
                        'generated_at': datetime.now().isoformat()
                    }
                    
                    # Calculate status breakdown
                    status_counts = {}
                    for detail in content_details:
                        status = detail['response_status']
                        status_counts[status] = status_counts.get(status, 0) + 1
                    report['status_breakdown'] = status_counts
                    
                    # Format according to requested format
                    if format.lower() == 'json':
                        return json.dumps(report, indent=2, default=str)
                    elif format.lower() == 'csv':
                        return self._format_report_as_csv(report)
                    elif format.lower() == 'html':
                        return self._format_report_as_html(report)
                    else:
                        return report
                        
        except psycopg2.Error as e:
            self.logger.error(f"Failed to generate scraping report: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error generating scraping report: {e}")
            raise
    
    def _format_report_as_csv(self, report: Dict[str, Any]) -> str:
        """Format report as CSV string."""
        output = io.StringIO()
        
        # Summary section
        writer = csv.writer(output)
        writer.writerow(['Section', 'Metric', 'Value'])
        writer.writerow(['Summary', 'Session ID', report['summary']['session_id']])
        writer.writerow(['Summary', 'Start Time', report['summary']['start_time']])
        writer.writerow(['Summary', 'End Time', report['summary']['end_time']])
        writer.writerow(['Summary', 'Total URLs', report['summary']['total_urls']])
        writer.writerow(['Summary', 'Successful Scrapes', report['summary']['successful_scrapes']])
        writer.writerow(['Summary', 'Failed Scrapes', report['summary']['failed_scrapes']])
        writer.writerow(['Summary', 'Success Rate %', f"{report['summary']['success_rate']:.2f}"])
        
        writer.writerow([])  # Empty row
        writer.writerow(['URL Details'])
        writer.writerow(['URL', 'Status', 'Response Time (ms)', 'Content Length', 'Scraped At', 'Result'])
        
        for detail in report['url_details']:
            writer.writerow([
                detail['url'],
                detail['response_status'],
                detail['response_time_ms'],
                detail['content_length'],
                detail['scraped_at'],
                detail['result_category']
            ])
        
        return output.getvalue()
    
    def _format_report_as_html(self, report: Dict[str, Any]) -> str:
        """Format report as HTML string."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Scraping Report - {report['summary']['session_id']}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .success {{ color: green; }}
                .error {{ color: red; }}
                .summary {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Web Scraper Report</h1>
            
            <div class="summary">
                <h2>Session Summary</h2>
                <p><strong>Session ID:</strong> {report['summary']['session_id']}</p>
                <p><strong>Start Time:</strong> {report['summary']['start_time']}</p>
                <p><strong>End Time:</strong> {report['summary']['end_time']}</p>
                <p><strong>Total URLs:</strong> {report['summary']['total_urls']}</p>
                <p><strong>Successful Scrapes:</strong> {report['summary']['successful_scrapes']}</p>
                <p><strong>Failed Scrapes:</strong> {report['summary']['failed_scrapes']}</p>
                <p><strong>Success Rate:</strong> {report['summary']['success_rate']:.2f}%</p>
            </div>
            
            <h2>URL Details</h2>
            <table>
                <tr>
                    <th>URL</th>
                    <th>Status</th>
                    <th>Response Time (ms)</th>
                    <th>Content Length</th>
                    <th>Result</th>
                </tr>
        """
        
        for detail in report['url_details']:
            css_class = 'success' if detail['response_status'] == 200 else 'error' if detail['response_status'] >= 400 else ''
            html += f"""
                <tr class="{css_class}">
                    <td>{detail['url']}</td>
                    <td>{detail['response_status']}</td>
                    <td>{detail['response_time_ms']}</td>
                    <td>{detail['content_length']}</td>
                    <td>{detail['result_category']}</td>
                </tr>
            """
        
        html += """
            </table>
            
            <p><em>Report generated at: """ + report['generated_at'] + """</em></p>
        </body>
        </html>
        """
        
        return html


class DatabaseBulkOps:
    """
    Bulk database operations for efficiency.
    
    Provides efficient batch operations for large-scale data management,
    including bulk inserts, updates, and batch processing.
    """
    
    def __init__(self, database_manager):
        """
        Initialize DatabaseBulkOps.
        
        Args:
            database_manager: DatabaseManager instance
        """
        self.db_manager = database_manager
        self.logger = get_logger(__name__)
    
    @log_performance
    def bulk_insert_content(self, content_list: List[Dict[str, Any]], 
                          batch_size: int = 1000) -> int:
        """
        Efficient batch insertion of content.
        
        Args:
            content_list: List of content dictionaries to insert
            batch_size: Number of records to insert per batch
            
        Returns:
            Number of records successfully inserted
        """
        if not content_list:
            return 0
        
        total_inserted = 0
        
        try:
            with self.db_manager._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Process in batches
                    for i in range(0, len(content_list), batch_size):
                        batch = content_list[i:i + batch_size]
                        
                        # Prepare batch insert query
                        values_template = "(%s, %s, %s, %s, %s, %s, %s, %s)"
                        values_list = []
                        params = []
                        
                        for content in batch:
                            values_list.append(values_template)
                            params.extend([
                                content.get('url'),
                                content.get('title'),
                                content.get('content'),
                                content.get('content_hash'),
                                content.get('response_status'),
                                content.get('response_time_ms'),
                                content.get('content_length'),
                                content.get('last_modified')
                            ])
                        
                        insert_query = f"""
                            INSERT INTO scraped_content 
                            (url, title, content, content_hash, response_status, 
                             response_time_ms, content_length, last_modified)
                            VALUES {', '.join(values_list)}
                        """
                        
                        cursor.execute(insert_query, params)
                        batch_inserted = cursor.rowcount
                        total_inserted += batch_inserted
                        
                        self.logger.debug(f"Inserted batch {i//batch_size + 1}: {batch_inserted} records")
                    
                    conn.commit()
                    self.logger.info(f"Bulk insert completed: {total_inserted} records inserted")
                    return total_inserted
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to bulk insert content: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during bulk insert: {e}")
            raise
    
    @log_performance
    def bulk_update_status(self, url_status_map: Dict[str, int]) -> int:
        """
        Batch update status for multiple URLs.
        
        Args:
            url_status_map: Dictionary mapping URLs to new status codes
            
        Returns:
            Number of records updated
        """
        if not url_status_map:
            return 0
        
        try:
            with self.db_manager._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Use CASE statement for efficient bulk update
                    case_conditions = []
                    url_list = list(url_status_map.keys())
                    
                    for url, status in url_status_map.items():
                        case_conditions.append(f"WHEN %s THEN %s")
                    
                    update_query = f"""
                        UPDATE scraped_content 
                        SET response_status = CASE url
                            {' '.join(case_conditions)}
                        END
                        WHERE url = ANY(%s)
                    """
                    
                    # Flatten parameters for CASE conditions and add URL list
                    params = []
                    for url, status in url_status_map.items():
                        params.extend([url, status])
                    params.append(url_list)
                    
                    cursor.execute(update_query, params)
                    updated_count = cursor.rowcount
                    conn.commit()
                    
                    self.logger.info(f"Bulk status update completed: {updated_count} records updated")
                    return updated_count
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to bulk update status: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during bulk update: {e}")
            raise
    
    @log_performance
    def bulk_delete_by_criteria(self, criteria: Dict[str, Any]) -> int:
        """
        Bulk delete records based on criteria.
        
        Args:
            criteria: Dictionary of deletion criteria:
                - older_than_days: Delete records older than specified days
                - status_codes: List of status codes to delete
                - url_patterns: List of URL patterns to match for deletion
                
        Returns:
            Number of records deleted
        """
        where_conditions = []
        params = []
        
        # Age-based deletion
        if criteria.get('older_than_days'):
            cutoff_date = datetime.now() - timedelta(days=criteria['older_than_days'])
            where_conditions.append("scraped_at < %s")
            params.append(cutoff_date)
        
        # Status code based deletion
        if criteria.get('status_codes'):
            status_codes = criteria['status_codes']
            placeholders = ','.join(['%s'] * len(status_codes))
            where_conditions.append(f"response_status IN ({placeholders})")
            params.extend(status_codes)
        
        # URL pattern based deletion
        if criteria.get('url_patterns'):
            url_conditions = []
            for pattern in criteria['url_patterns']:
                url_conditions.append("url LIKE %s")
                params.append(f"%{pattern}%")
            where_conditions.append(f"({' OR '.join(url_conditions)})")
        
        if not where_conditions:
            raise ValueError("No deletion criteria specified")
        
        try:
            with self.db_manager._get_connection() as conn:
                with conn.cursor() as cursor:
                    delete_query = f"""
                        DELETE FROM scraped_content 
                        WHERE {' AND '.join(where_conditions)}
                    """
                    
                    cursor.execute(delete_query, params)
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    self.logger.info(f"Bulk delete completed: {deleted_count} records deleted")
                    return deleted_count
                    
        except psycopg2.Error as e:
            self.logger.error(f"Failed to bulk delete: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during bulk delete: {e}")
            raise


# Example usage and testing functions
if __name__ == "__main__":
    # This section is for testing purposes
    import sys
    import os
    
    # Add src directory to path for imports
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from database import DatabaseManager
    from config import Config
    
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
        db_manager.connect()
        
        # Test analytics
        analytics = DatabaseAnalytics(db_manager)
        
        print("Testing content statistics...")
        stats = analytics.get_content_statistics()
        print(f"Total content: {stats.total_content}")
        print(f"Unique URLs: {stats.unique_urls}")
        print(f"Success rate: {stats.success_rate:.2f}%")
        
        print("\nTesting search functionality...")
        search_results = analytics.search_content(query="example", limit=5)
        print(f"Found {search_results.total_matches} matches in {search_results.query_time_ms:.2f}ms")
        
        print("\nTesting bulk operations...")
        bulk_ops = DatabaseBulkOps(db_manager)
        
        # Test with sample data
        sample_content = [
            {
                'url': 'https://test-bulk-1.com',
                'title': 'Bulk Test 1',
                'content': 'Test content 1',
                'content_hash': 'hash1',
                'response_status': 200,
                'response_time_ms': 100,
                'content_length': 100
            },
            {
                'url': 'https://test-bulk-2.com',
                'title': 'Bulk Test 2',
                'content': 'Test content 2',
                'content_hash': 'hash2',
                'response_status': 200,
                'response_time_ms': 150,
                'content_length': 120
            }
        ]
        
        inserted = bulk_ops.bulk_insert_content(sample_content)
        print(f"Bulk inserted {inserted} records")
        
        # Cleanup
        db_manager.disconnect()
        print("Database analytics testing completed successfully!")
        
    except Exception as e:
        print(f"Database analytics testing failed: {e}")
        sys.exit(1)