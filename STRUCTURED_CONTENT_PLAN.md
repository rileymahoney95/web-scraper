# Structured Content Extraction Enhancement Plan

## Overview

This document outlines a comprehensive plan to enhance the web scraper with structured content extraction capabilities while maintaining 100% backward compatibility and ensuring that basic scraping never fails due to structure extraction errors.

## Core Principles

### 1. **Fail-Safe Design**

- Basic content extraction must **NEVER** fail due to structured extraction errors
- All structured extraction happens as an additional layer on top of existing functionality
- Graceful degradation when structured extraction fails

### 2. **Backward Compatibility**

- Existing `ScrapedContent` dataclass remains unchanged for core functionality
- Database schema changes are additive-only
- All existing APIs continue to work without modification

### 3. **Progressive Enhancement**

- Structured extraction is an optional enhancement
- Can be enabled/disabled per URL or globally
- Granular control over what structured data to extract

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Enhanced Content Extractor              │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │   Core Extract  │    │    Structured Extract          │ │
│  │   (Required)    │    │    (Optional, Fail-Safe)       │ │
│  │                 │    │                                 │ │
│  │ • Plain Text    │    │ • Metadata Extraction          │ │
│  │ • Title         │    │ • Section Identification       │ │
│  │ • Basic Hash    │    │ • JSON-LD Processing           │ │
│  │ • Always Works  │    │ • Site-Specific Patterns       │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
│           │                           │                     │
│           ▼                           ▼                     │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │ Core Database   │    │ Enhanced Database Storage       │ │
│  │ (Existing)      │    │ (New JSONB Columns)            │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Foundation Setup (Week 1)

**Goal**: Establish infrastructure without changing existing behavior

#### 1.1 Database Schema Enhancement

```sql
-- Add new columns for structured data (non-breaking)
ALTER TABLE scraped_content
ADD COLUMN IF NOT EXISTS structured_content JSONB DEFAULT NULL,
ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT NULL,
ADD COLUMN IF NOT EXISTS sections JSONB DEFAULT NULL,
ADD COLUMN IF NOT EXISTS extraction_version INTEGER DEFAULT 1;

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_scraped_content_structured
    ON scraped_content USING GIN (structured_content);
CREATE INDEX IF NOT EXISTS idx_scraped_content_metadata
    ON scraped_content USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_scraped_content_sections
    ON scraped_content USING GIN (sections);
```

#### 1.2 Enhanced ScrapedContent Class

```python
@dataclass
class ScrapedContent:
    """Enhanced data class - backward compatible."""
    # Existing fields (unchanged)
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    content_hash: Optional[str] = None
    response_status: Optional[int] = None
    response_time_ms: Optional[int] = None
    content_length: Optional[int] = None
    last_modified: Optional[str] = None

    # New optional fields
    structured_content: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    sections: Optional[List[Dict[str, Any]]] = None
    extraction_version: Optional[int] = 1
    extraction_errors: Optional[List[str]] = None  # Track any issues
```

#### 1.3 Configuration Options

```yaml
scraping:
  settings:
    # Existing settings remain unchanged
    timeout: 30
    retry_attempts: 3

    # New structured extraction settings
    structured_extraction:
      enabled: true
      fail_silently: true # CRITICAL: Never fail core scraping

      # What to extract
      extract_metadata: true
      extract_sections: true
      extract_json_ld: true

      # Site-specific patterns
      site_patterns:
        - domain: 'ideabrowser.com'
          type: 'idea_page'
          extractors:
            - 'idea_metrics'
            - 'pricing_info'
            - 'business_analysis'
        - domain: 'example.com'
          type: 'article'
          extractors:
            - 'article_metadata'
            - 'author_info'

      # Error handling
      max_extraction_time_ms: 5000 # Timeout for structured extraction
      log_extraction_errors: true
```

### Phase 2: Core Structured Extraction (Week 2)

#### 2.1 Enhanced ContentExtractor with Fail-Safe Design

```python
class EnhancedContentExtractor(ContentExtractor):
    """
    Enhanced content extractor with fail-safe structured extraction.
    """

    def extract_content(self, response: requests.Response, url: str) -> ScrapedContent:
        """
        Extract content with optional structured enhancement.
        GUARANTEE: This method will never fail due to structured extraction errors.
        """
        extraction_errors = []

        # STEP 1: Core extraction (existing, proven code) - MUST succeed
        try:
            core_content = super().extract_content(response, url)
        except Exception as e:
            # If core extraction fails, it should fail (existing behavior)
            raise

        # STEP 2: Enhanced extraction (new, optional) - CAN fail safely
        structured_data = None
        metadata = None
        sections = None

        if self._should_extract_structure(url):
            try:
                # Timeout protection for structured extraction
                with timeout_context(self.config.get('max_extraction_time_ms', 5000)):
                    soup = self._create_soup(response.text)

                    # Extract each component separately with individual error handling
                    metadata = self._safe_extract_metadata(soup, extraction_errors)
                    sections = self._safe_extract_sections(soup, extraction_errors)
                    structured_data = self._safe_extract_structured_content(soup, url, extraction_errors)

            except TimeoutError:
                extraction_errors.append("Structured extraction timed out")
                self.logger.warning(f"Structured extraction timed out for {url}")
            except Exception as e:
                extraction_errors.append(f"Structured extraction failed: {str(e)}")
                self.logger.warning(f"Structured extraction failed for {url}: {e}")

        # STEP 3: Combine results (core content + optional enhancements)
        enhanced_content = ScrapedContent(
            # Core fields (guaranteed to exist)
            url=core_content.url,
            title=core_content.title,
            content=core_content.content,
            content_hash=core_content.content_hash,
            response_status=core_content.response_status,
            response_time_ms=core_content.response_time_ms,
            content_length=core_content.content_length,
            last_modified=core_content.last_modified,

            # Enhanced fields (may be None if extraction failed)
            structured_content=structured_data,
            metadata=metadata,
            sections=sections,
            extraction_version=2,
            extraction_errors=extraction_errors if extraction_errors else None
        )

        return enhanced_content

    def _safe_extract_metadata(self, soup: BeautifulSoup, errors: List[str]) -> Optional[Dict[str, Any]]:
        """Extract metadata with error isolation."""
        try:
            return self._extract_metadata(soup)
        except Exception as e:
            errors.append(f"Metadata extraction failed: {str(e)}")
            return None

    def _safe_extract_sections(self, soup: BeautifulSoup, errors: List[str]) -> Optional[List[Dict[str, Any]]]:
        """Extract sections with error isolation."""
        try:
            return self._extract_sections(soup)
        except Exception as e:
            errors.append(f"Section extraction failed: {str(e)}")
            return None

    def _safe_extract_structured_content(self, soup: BeautifulSoup, url: str, errors: List[str]) -> Optional[Dict[str, Any]]:
        """Extract structured content with error isolation."""
        try:
            return self._extract_structured_content(soup, url)
        except Exception as e:
            errors.append(f"Structured content extraction failed: {str(e)}")
            return None
```

#### 2.2 Site-Specific Extractors

```python
class SiteSpecificExtractors:
    """Registry of site-specific extraction patterns."""

    @staticmethod
    def extract_idea_page_data(soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract data specific to idea browser pages."""
        try:
            data = {}
            text_content = soup.get_text()

            # Extract metrics safely
            metrics = {}
            metric_patterns = {
                'opportunity': r'Opportunity\s*(\d+)',
                'problem': r'Problem\s*(\d+)',
                'feasibility': r'Feasibility\s*(\d+)',
                'timing': r'Why Now\s*(\d+)'
            }

            for key, pattern in metric_patterns.items():
                match = re.search(pattern, text_content)
                if match:
                    metrics[key] = int(match.group(1))

            if metrics:
                data['metrics'] = metrics

            # Extract pricing
            prices = re.findall(r'\$(\d+)(?:/month)?', text_content)
            if prices:
                data['pricing'] = [int(p) for p in prices]

            return data

        except Exception as e:
            # Log but don't fail
            logging.warning(f"Idea page extraction failed: {e}")
            return {}
```

### Phase 3: Database Integration (Week 3)

#### 3.1 Enhanced DatabaseManager Methods

```python
class DatabaseManager:
    """Enhanced database manager with structured content support."""

    def insert_content(self, content: ScrapedContent) -> int:
        """
        Insert content with optional structured data.
        GUARANTEE: Will not fail if structured data is malformed.
        """
        # Prepare core data (existing logic)
        core_params = (
            content.url, content.title, content.content, content.content_hash,
            content.response_status, content.response_time_ms,
            content.content_length, content.last_modified
        )

        # Prepare structured data safely
        structured_content_json = None
        metadata_json = None
        sections_json = None

        try:
            if content.structured_content:
                structured_content_json = json.dumps(content.structured_content)
        except Exception as e:
            self.logger.warning(f"Failed to serialize structured_content: {e}")

        try:
            if content.metadata:
                metadata_json = json.dumps(content.metadata)
        except Exception as e:
            self.logger.warning(f"Failed to serialize metadata: {e}")

        try:
            if content.sections:
                sections_json = json.dumps(content.sections)
        except Exception as e:
            self.logger.warning(f"Failed to serialize sections: {e}")

        # Enhanced query with fallback handling
        query = """
        INSERT INTO scraped_content (
            url, title, content, content_hash, response_status,
            response_time_ms, content_length, last_modified,
            structured_content, metadata, sections, extraction_version
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
        """

        all_params = core_params + (
            structured_content_json, metadata_json, sections_json,
            getattr(content, 'extraction_version', 1)
        )

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, all_params)
                    record_id = cursor.fetchone()[0]
                    conn.commit()
                    return record_id

        except psycopg2.Error as e:
            # If enhanced insert fails, try basic insert as fallback
            self.logger.warning(f"Enhanced insert failed, falling back to basic insert: {e}")
            return self._insert_content_basic(content)

    def _insert_content_basic(self, content: ScrapedContent) -> int:
        """Fallback to basic content insertion if enhanced insert fails."""
        query = """
        INSERT INTO scraped_content (
            url, title, content, content_hash, response_status,
            response_time_ms, content_length, last_modified
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
        """

        params = (
            content.url, content.title, content.content, content.content_hash,
            content.response_status, content.response_time_ms,
            content.content_length, content.last_modified
        )

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                record_id = cursor.fetchone()[0]
                conn.commit()
                return record_id
```

#### 3.2 Query Enhancement Methods

```python
    def search_structured_content(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search using structured content fields."""
        conditions = []
        params = []

        # Build dynamic query based on available structured data
        if 'idea_metrics' in query_params:
            conditions.append("structured_content->'idea_data'->'metrics' IS NOT NULL")

        if 'min_opportunity' in query_params:
            conditions.append("(structured_content->'idea_data'->'metrics'->>'opportunity')::int >= %s")
            params.append(query_params['min_opportunity'])

        if 'max_price' in query_params:
            conditions.append("structured_content->'idea_data'->>'pricing' IS NOT NULL")

        base_query = """
        SELECT url, title, content, structured_content, metadata, sections
        FROM scraped_content
        WHERE 1=1
        """

        if conditions:
            base_query += " AND " + " AND ".join(conditions)

        base_query += " ORDER BY scraped_at DESC"

        return self.execute_query(base_query, tuple(params))

    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about structured extraction success rates."""
        query = """
        SELECT
            COUNT(*) as total_records,
            COUNT(structured_content) as structured_count,
            COUNT(metadata) as metadata_count,
            COUNT(sections) as sections_count,
            AVG(CASE WHEN extraction_errors IS NOT NULL THEN 1 ELSE 0 END) as error_rate
        FROM scraped_content
        WHERE created_at >= NOW() - INTERVAL '7 days'
        """

        results = self.execute_query(query)
        return results[0] if results else {}
```

### Phase 4: Testing & Validation (Week 4)

#### 4.1 Comprehensive Test Suite

```python
import pytest
from unittest.mock import Mock, patch

class TestStructuredExtraction:
    """Test suite ensuring fail-safe behavior."""

    def test_core_extraction_never_fails_due_to_structured_errors(self):
        """CRITICAL: Core extraction must work even if structured extraction explodes."""
        # Simulate structured extraction throwing every possible error
        with patch('enhanced_scraper.EnhancedContentExtractor._extract_metadata') as mock_meta:
            mock_meta.side_effect = Exception("Metadata extraction exploded")

            with patch('enhanced_scraper.EnhancedContentExtractor._extract_sections') as mock_sections:
                mock_sections.side_effect = RuntimeError("Sections exploded")

                # Core extraction should still work
                extractor = EnhancedContentExtractor(config)
                result = extractor.extract_content(mock_response, "http://example.com")

                # Core fields must be present
                assert result.url == "http://example.com"
                assert result.content is not None
                assert result.title is not None

                # Structured fields should be None due to errors
                assert result.structured_content is None
                assert result.metadata is None
                assert result.sections is None

                # Errors should be logged
                assert result.extraction_errors is not None
                assert len(result.extraction_errors) > 0

    def test_database_insertion_graceful_degradation(self):
        """Database insertion should work even with malformed structured data."""
        # Create content with malformed structured data
        content = ScrapedContent(
            url="http://test.com",
            title="Test",
            content="Basic content",
            structured_content={"invalid": datetime.now()},  # Non-serializable
            metadata={"circular": None}
        )
        # Set up circular reference
        content.metadata["circular"] = content.metadata

        db_manager = DatabaseManager(config)

        # Should not raise exception
        record_id = db_manager.insert_content(content)
        assert record_id is not None

        # Should fall back to basic insertion
        retrieved = db_manager.get_content_by_url("http://test.com")
        assert len(retrieved) == 1
        assert retrieved[0]['title'] == "Test"

    def test_structured_extraction_timeout(self):
        """Structured extraction should timeout gracefully."""
        with patch('enhanced_scraper.EnhancedContentExtractor._extract_metadata') as mock_meta:
            # Simulate slow extraction
            mock_meta.side_effect = lambda soup: time.sleep(10)

            extractor = EnhancedContentExtractor({
                'max_extraction_time_ms': 1000  # 1 second timeout
            })

            start_time = time.time()
            result = extractor.extract_content(mock_response, "http://example.com")
            elapsed = time.time() - start_time

            # Should complete quickly due to timeout
            assert elapsed < 2.0

            # Core content should be present
            assert result.content is not None

            # Should have timeout error logged
            assert any("timed out" in error for error in result.extraction_errors)
```

#### 4.2 Performance Testing

```python
class TestPerformanceImpact:
    """Ensure structured extraction doesn't significantly impact performance."""

    def test_extraction_time_overhead(self):
        """Structured extraction should add minimal overhead."""
        extractor_basic = ContentExtractor(config)
        extractor_enhanced = EnhancedContentExtractor(config)

        # Test with same content
        basic_times = []
        enhanced_times = []

        for _ in range(10):
            start = time.time()
            extractor_basic.extract_content(mock_response, "http://test.com")
            basic_times.append(time.time() - start)

            start = time.time()
            extractor_enhanced.extract_content(mock_response, "http://test.com")
            enhanced_times.append(time.time() - start)

        avg_basic = sum(basic_times) / len(basic_times)
        avg_enhanced = sum(enhanced_times) / len(enhanced_times)

        # Enhanced should not be more than 2x slower
        assert avg_enhanced / avg_basic < 2.0
```

## Migration Strategy

### 1. Gradual Rollout

```yaml
# Phase 1: Enable for specific URLs only
structured_extraction:
  enabled: true
  url_patterns:
    - "ideabrowser.com/ideas/*"

# Phase 2: Enable for specific domains
structured_extraction:
  enabled: true
  domain_whitelist:
    - "ideabrowser.com"
    - "example.com"

# Phase 3: Enable globally with blacklist
structured_extraction:
  enabled: true
  domain_blacklist:
    - "problematic-site.com"
```

### 2. Monitoring & Rollback

```python
# Monitor extraction success rates
def monitor_extraction_health():
    stats = db_manager.get_extraction_stats()

    if stats['error_rate'] > 0.1:  # More than 10% errors
        logger.warning("High structured extraction error rate, consider disabling")

    if stats['structured_count'] / stats['total_records'] < 0.5:
        logger.info("Low structured extraction success rate")
```

## Error Handling & Monitoring

### 1. Error Categories

- **Timeout Errors**: Extraction takes too long
- **Parsing Errors**: Malformed HTML/JSON
- **Serialization Errors**: Non-JSON-serializable data
- **Database Errors**: JSON storage issues

### 2. Monitoring Dashboard Metrics

- Extraction success rate by site
- Average extraction time overhead
- Error types and frequencies
- Structured data quality scores

### 3. Alerting Thresholds

- Error rate > 10% for any site
- Extraction time > 5 seconds consistently
- Database insertion failures > 1%

## Configuration Reference

### Complete Configuration Example

```yaml
scraping:
  settings:
    # Core settings (unchanged)
    timeout: 30
    retry_attempts: 3

    # Structured extraction settings
    structured_extraction:
      enabled: true
      fail_silently: true
      max_extraction_time_ms: 5000

      # Feature toggles
      extract_metadata: true
      extract_sections: true
      extract_json_ld: true
      preserve_html_structure: false

      # Site-specific configurations
      site_patterns:
        - domain: 'ideabrowser.com'
          type: 'idea_page'
          enabled: true
          extractors:
            - name: 'idea_metrics'
              selectors:
                opportunity: "text-containing('Opportunity')"
                problem: "text-containing('Problem')"
            - name: 'pricing_info'
              patterns:
                - r'\$(\d+)/month'

        - domain: 'news.ycombinator.com'
          type: 'discussion'
          enabled: true
          extractors:
            - name: 'hn_metadata'
              selectors:
                points: '.score'
                comments: '.comments a'

      # Performance settings
      timeout_ms: 5000
      max_sections: 50
      max_metadata_size: 10240 # 10KB

      # Error handling
      log_extraction_errors: true
      store_extraction_errors: true
      fallback_to_basic_on_error: true
```

## Success Metrics

### 1. Reliability Metrics

- **Zero Breaking Changes**: 0% regression in existing functionality
- **Extraction Success Rate**: >90% successful structured extractions
- **Error Isolation**: 100% of extraction errors contained (don't break core scraping)

### 2. Performance Metrics

- **Time Overhead**: <50% increase in total extraction time
- **Memory Overhead**: <25% increase in memory usage
- **Database Performance**: Query times remain within 10% of baseline

### 3. Data Quality Metrics

- **Structured Data Coverage**: >80% of pages have some structured data
- **Metadata Completeness**: >95% of pages have title and basic metadata
- **Section Identification**: >70% of content pages have identified sections

## Conclusion

This plan ensures that structured content extraction enhances your scraper without compromising its reliability. The fail-safe design guarantees that:

1. **Existing functionality never breaks** due to structured extraction issues
2. **Graceful degradation** occurs when structured extraction fails
3. **Progressive enhancement** allows gradual adoption of new features
4. **Comprehensive monitoring** ensures early detection of issues

The implementation prioritizes safety and backward compatibility while providing powerful new capabilities for content analysis and search.
