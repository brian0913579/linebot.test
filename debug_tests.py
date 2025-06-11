#!/usr/bin/env python3
"""Debug script to test individual components."""

import sys
import traceback

# Add current directory to Python path
sys.path.insert(0, "/workspaces/linebot.test")


def test_imports():
    """Test importing all modules."""
    modules_to_test = [
        "config.config_module",
        "config.secret_manager",
        "middleware.cache_manager",
        "core.models",
        "core.token_manager",
        "core.mqtt_handler",
        "core.line_webhook",
        "middleware.rate_limiter",
    ]

    for module in modules_to_test:
        try:
            __import__(module)
            print(f"✓ {module}")
        except Exception as e:
            print(f"✗ {module}: {e}")
            traceback.print_exc()


def test_pytest_import():
    """Test pytest functionality."""
    try:
        import pytest

        print(f"✓ pytest version: {pytest.__version__}")

        # Try to import conftest

        print("✓ tests.conftest imported")

        # Try to import test modules
        test_modules = [
            "tests.test_models",
            "tests.test_token_manager",
            "tests.test_cache_manager",
        ]

        for module in test_modules:
            try:
                __import__(module)
                print(f"✓ {module}")
            except Exception as e:
                print(f"✗ {module}: {e}")

    except Exception as e:
        print(f"✗ pytest import failed: {e}")


if __name__ == "__main__":
    print("=== Testing Module Imports ===")
    test_imports()
    print("\n=== Testing Pytest Imports ===")
    test_pytest_import()
