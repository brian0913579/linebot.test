# LineBot Test Suite

This directory contains unit tests for the LineBot garage door control system.

## Test Organization

- `conftest.py`: Shared fixtures and test utilities
- `test_app.py`: Tests for Flask application endpoints
- `test_line_webhook.py`: Tests for LINE webhook handlers
- `test_mqtt_handler.py`: Tests for MQTT connection and messaging
- `test_token_manager.py`: Tests for token generation and management

## Running Tests

To run the tests, use:

```bash
# Run all tests
python -m pytest

# Run with verbose output
python -m pytest -v

# Run specific test file
python -m pytest tests/test_app.py

# Run with coverage report
python -m pytest --cov=.

# Run with xUnit report
python -m pytest --junitxml=test-reports/junit.xml
```

## Test Dependencies

Make sure to install the test dependencies:

```bash
pip install pytest pytest-cov pytest-mock
```

## Mocked Services

The tests mock the following external services:
- LINE Messaging API
- MQTT broker connection
- SQLite database interactions
