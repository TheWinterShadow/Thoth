# Testing & Coverage

This document describes the testing strategy and coverage requirements for Thoth.

## Test Structure

```
tests/
├── test_thoth.py                    # Package import test
├── ingestion/                       # Ingestion pipeline tests
│   ├── test_pipeline.py             # IngestionPipeline orchestration
│   ├── test_chunker.py              # MarkdownChunker behavior
│   ├── test_repo_manager.py         # Repository management
│   ├── test_gitlab_api.py           # GitLab API client
│   ├── test_worker.py               # Worker HTTP endpoints
│   └── test_gcs_*.py                # GCS integration tests
├── mcp/                             # MCP server tests
│   ├── test_mcp_server.py           # Tool execution, search, caching
│   └── test_http_wrapper.py         # HTTP transport tests
└── shared/                          # Shared utility tests
    ├── test_vector_store.py         # ChromaDB operations
    ├── test_embedder.py             # Embedding generation
    ├── test_cli.py                  # CLI commands
    └── utils/                       # Utility tests
        ├── test_logger.py
        └── test_secrets.py
```

## Running Tests

### Full Test Suite

```bash
# Run all tests
hatch test

# Run with coverage
hatch run default:test-cov

# Run specific test file
hatch test tests/ingestion/test_chunker.py

# Run with verbose output
hatch test -v
```

### Test by Component

```bash
# Ingestion tests only
hatch test tests/ingestion/

# MCP server tests only
hatch test tests/mcp/

# Shared utilities tests only
hatch test tests/shared/
```

## Coverage Requirements

### Minimum Coverage Targets

| Component | Target | Description |
|-----------|--------|-------------|
| Overall | 80% | Minimum total coverage |
| Ingestion | 85% | Core business logic |
| MCP Server | 85% | Query handling |
| Shared | 75% | Utility functions |

### Generating Coverage Reports

```bash
# Terminal report
hatch run default:cov-report

# HTML report
hatch run default:cov-html
# Open docs/build/coverage/index.html
```

### Coverage Configuration

From `pyproject.toml`:

```toml
[tool.coverage.run]
source_pkgs = ["thoth", "tests"]
branch = true
parallel = true
omit = ["thoth/__about__.py"]

[tool.coverage.report]
exclude_lines = [
    "no cov",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
precision = 2
show_missing = true
```

## Test Categories

### Unit Tests

Test individual functions and classes in isolation.

```python
# Example: test_chunker.py
def test_chunk_document_respects_max_size():
    chunker = MarkdownChunker(max_tokens=100)
    chunks = chunker.chunk_document(long_document)
    for chunk in chunks:
        assert len(chunk.tokens) <= 100
```

### Integration Tests

Test component interactions with mocked external services.

```python
# Example: test_pipeline.py
@pytest.fixture
def mock_gitlab(mocker):
    return mocker.patch("thoth.ingestion.gitlab_api.GitLabAPIClient")

def test_pipeline_processes_changed_files(mock_gitlab, tmp_path):
    pipeline = IngestionPipeline(config)
    pipeline.run()
    assert pipeline.state.processed_files > 0
```

### End-to-End Tests

Test complete workflows (run in CI with real services).

```python
# Example: test_gcs_integration.py
@pytest.mark.integration
def test_full_sync_to_gcs(gcs_bucket):
    sync = GCSRepoSync(bucket=gcs_bucket)
    sync.clone_to_gcs(repo_url)
    assert sync.list_files() > 0
```

## Test Fixtures

### Common Fixtures

```python
# conftest.py
@pytest.fixture
def sample_markdown():
    return """
    # Heading

    Some content here.

    ## Subheading

    More content.
    """

@pytest.fixture
def temp_vector_store(tmp_path):
    return VectorStore(path=tmp_path / "chroma")

@pytest.fixture
def mock_embedder(mocker):
    embedder = mocker.Mock()
    embedder.embed.return_value = [0.1] * 384
    return embedder
```

## CI Integration

Tests run automatically in GitHub Actions:

```yaml
# .github/workflows/ci.yml
test:
  strategy:
    matrix:
      python-version: ["3.10", "3.11", "3.12", "3.13"]
  steps:
    - name: Run tests
      run: hatch test
```

### Test Environment Variables

```yaml
env:
  GITLAB_TOKEN: "test-token-for-ci"
  GITLAB_BASE_URL: "https://gitlab.com"
  GCP_PROJECT_ID: "test-project"
```

## Writing New Tests

### Guidelines

1. **One assertion per test** when practical
2. **Descriptive names**: `test_chunker_splits_at_header_boundaries`
3. **Arrange-Act-Assert** pattern
4. **Mock external services** (GitLab, GCS, Secret Manager)
5. **Use fixtures** for repeated setup

### Example Test Structure

```python
class TestMarkdownChunker:
    """Tests for MarkdownChunker class."""

    def test_creates_chunks_from_document(self, sample_markdown):
        """Verify chunker produces non-empty chunks."""
        # Arrange
        chunker = MarkdownChunker()

        # Act
        chunks = chunker.chunk_document(sample_markdown)

        # Assert
        assert len(chunks) > 0
        assert all(chunk.content for chunk in chunks)

    def test_preserves_header_hierarchy(self, sample_markdown):
        """Verify chunk metadata includes header path."""
        chunker = MarkdownChunker()
        chunks = chunker.chunk_document(sample_markdown)

        assert any("Heading" in c.metadata.get("headers", []) for c in chunks)
```

## Debugging Tests

### Running with Debug Output

```bash
# Print statements visible
hatch test -s

# Verbose pytest output
hatch test -vvv

# Stop on first failure
hatch test -x

# Run last failed tests
hatch test --lf
```

### Using pytest-asyncio

For async tests:

```python
import pytest

@pytest.mark.asyncio
async def test_async_search():
    server = ThothMCPServer()
    result = await server.search("query")
    assert result is not None
```
