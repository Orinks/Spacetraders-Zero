---
name: Failing Tests Report
about: Track and fix failing tests in the test suite
title: 'Fix failing API client tests'
labels: 'bug, testing'
assignees: ''
---

## Failed Tests Summary

Seven tests are failing in the test suite, all related to API client testing. The main issue is that these tests are making actual API calls instead of using proper mocks.

### Failed Tests List

1. Client Logging Tests:
   - `test_cache_logging`
   - `test_error_request_logging`
   - `test_rate_limit_logging`
   - `test_successful_request_logging`

2. Client Optimizations Tests:
   - `test_cache_hit`
   - `test_cache_ttl`
   - `test_etag_handling`

### Error Details

All tests are failing with a 401 Unauthorized error:
```
Failed to parse token. Token is missing or empty.
```

### Required Fixes

1. Update test files to properly mock API responses:
   - Use `@patch` decorators to mock `requests.get` calls
   - Create proper mock responses with appropriate status codes and headers
   - Ensure no actual API calls are made during testing

2. Specific fixes needed:
   - `test_client_logging.py`: Mock responses for logging tests
   - `test_client_optimizations.py`: Mock responses for caching and ETag tests

3. Additional improvements:
   - Add test fixtures for common mock responses
   - Add test cases for error scenarios
   - Ensure tests run in isolation

### Success Criteria

- [ ] All tests pass locally
- [ ] No actual API calls made during testing
- [ ] Test coverage maintained or improved
- [ ] CI/CD pipeline passes

### Notes

- Current test success rate: 36/43 tests passing
- Core functionality tests (gameplay, mining, persistence) are all passing
- Only API client-related tests are failing
