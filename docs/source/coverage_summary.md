# Test Coverage

Current test coverage for the Thoth project.

## Coverage Summary

The project maintains high test coverage across all modules. View the detailed coverage report:

<a href="coverage/index.html" target="_blank">📊 View Full Coverage Report</a>

## Coverage by Module

- **Overall Coverage**: 93.91%
- **Total Statements**: 434
- **Covered**: 409
- **Missing**: 25

### Module Breakdown

| Module | Coverage |
|--------|----------|
| thoth.mcp_server.server | 74.51% |
| thoth.utils.logger | 84.29% |
| tests (all modules) | 98.33% |

## Running Coverage Locally

Generate the latest coverage report:

```bash
# Generate HTML coverage report
hatch test --cov --cov-report=html:docs/build/coverage --cov-report=term

# View the report
open docs/build/coverage/index.html
```

Or use the hatch script:

```bash
hatch run cov-html
```

## Coverage Configuration

Coverage settings are configured in `pyproject.toml`:

```toml
[tool.coverage.run]
source_pkgs = ["thoth", "tests"]
branch = true
parallel = true

[tool.coverage.html]
directory = "docs/build/coverage"
title = "Thoth Test Coverage Report"
```

## CI/CD Integration

Coverage reports are generated automatically:
- On every test run
- In the documentation build
- HTML reports available at `docs/build/coverage/`

## Coverage Goals

- Target: ≥90% overall coverage
- Critical modules: ≥85% coverage
- New code: ≥95% coverage

## Interpreting the Report

The full HTML coverage report shows:
- **Green lines**: Executed during tests
- **Red lines**: Not executed
- **Yellow lines**: Partially covered (branches)

Click on any file in the coverage report to see line-by-line coverage details.
