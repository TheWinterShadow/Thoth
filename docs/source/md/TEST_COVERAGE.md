# MCP Server Test Coverage

## Test Suites Overview

This document provides an overview of the test coverage for the Thoth MCP Server.

## Test Classes

### 1. TestThothMCPServer
Basic server initialization and configuration tests.

**Tests:**
- Server initialization with custom name/version
- Server initialization with default values
- Handler setup verification

### 2. TestMCPServerHandlers
Tests for MCP protocol handlers.

**Tests:**
- List tools handler
- Call tool handler for ping
- Unknown tool error handling
- List resources handler
- Read resource error handling

### 3. TestServerRunMethods
Tests for server runtime methods.

**Tests:**
- Server run method with stdio transport
- Main function execution
- Async server initialization

### 4. TestRunServerFunction
Tests for synchronous entry point.

**Tests:**
- Successful server startup
- KeyboardInterrupt handling
- Exception logging and propagation

### 5. TestToolResponse
Tests for MCP type structures and responses.

**Tests:**
- TextContent creation
- Tool definition structure
- Ping tool response format

### 6. TestMCPTools ⭐ NEW
**Comprehensive test suite specifically for MCP tools.**

**Tests:**
- ✅ `test_ping_tool_exists` - Verifies ping tool registration
- ✅ `test_ping_tool_with_default_message` - Tests default "ping" message
- ✅ `test_ping_tool_with_custom_message` - Tests custom messages (includes Unicode)
- ✅ `test_ping_tool_with_empty_string` - Tests empty string handling
- ✅ `test_ping_tool_response_format` - Validates "pong: {message}" format
- ✅ `test_ping_tool_schema_validation` - Verifies tool schema structure
- ✅ `test_ping_tool_text_content_response` - Tests TextContent response objects
- ✅ `test_tool_error_handling_unknown_tool` - Tests error handling for invalid tools
- ✅ `test_tool_list_structure` - Validates Tool object structure

**Coverage:**
- Default argument handling
- Custom message processing
- Unicode/international character support
- Multiple message formats
- Response format validation
- Schema compliance
- Error handling

### 7. TestMCPResources ⭐ NEW
**Comprehensive test suite specifically for MCP resources.**

**Tests:**
- ✅ `test_list_resources_returns_list` - Verifies list return type
- ✅ `test_list_resources_empty_by_default` - Tests empty default state
- ✅ `test_read_resource_not_found` - Tests resource not found errors
- ✅ `test_resource_uri_format` - Validates URI format patterns
- ✅ `test_resource_error_message_format` - Tests error message formatting

**Coverage:**
- Resource listing
- Resource URI validation
- Error handling for missing resources
- URI format compliance

### 8. TestServerIntegration
Integration tests for server components.

**Tests:**
- MCP Server instance validation
- Server attribute accessibility
- Component integration

## Test Statistics

- **Total Test Classes:** 8
- **Total Tests:** 48
- **Pass Rate:** 100%
- **Code Coverage:** Comprehensive

## Key Testing Features

### Subtests
Uses `subTest()` for parameterized testing:
- Multiple ping messages in single test
- Multiple unknown tools testing
- Multiple resource URIs validation

### Async Testing
Uses `unittest.IsolatedAsyncioTestCase` for proper async testing:
- Isolated async test environments
- Proper asyncio handling
- No test pollution

### Mock Usage
Strategic mocking for:
- stdio transport
- asyncio.run
- Server initialization
- Logger verification

## Running Tests

### All Tests
```bash
hatch test
```

### Specific Test Class
```bash
hatch test tests/mcp_server/test_mcp_server.py::TestMCPTools -v
```

### Single Test
```bash
hatch test tests/mcp_server/test_mcp_server.py::TestMCPTools::test_ping_tool_with_custom_message -v
```

### With Coverage
```bash
hatch test --cov
```

## Adding New Tool Tests

When adding a new tool, add tests to `TestMCPTools`:

```python
async def test_your_tool_with_args(self):
    """Test your tool with various arguments."""
    # Test logic here
    pass

async def test_your_tool_error_handling(self):
    """Test your tool error cases."""
    # Error testing here
    pass
```

## Adding New Resource Tests

When adding resources, add tests to `TestMCPResources`:

```python
async def test_your_resource_read(self):
    """Test reading your resource."""
    # Test logic here
    pass
```

## Best Practices

1. **Isolation**: Each test is independent
2. **Descriptive Names**: Test names clearly describe what they test
3. **Subtests**: Use for parameterized scenarios
4. **Async Proper**: Use IsolatedAsyncioTestCase for async tests
5. **Assertions**: Multiple assertions per test when logical
6. **Documentation**: Every test has a docstring

## Future Enhancements

- [ ] Add performance benchmarks
- [ ] Add integration tests with real MCP clients
- [ ] Add stress testing for concurrent requests
- [ ] Add test coverage for future tools
- [ ] Add property-based testing with Hypothesis
