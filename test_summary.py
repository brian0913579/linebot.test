#!/usr/bin/env python3
"""Test summary script."""

import os
import subprocess
import sys


def run_test_module(module_name):
    """Run a single test module and return results."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        f"tests/test_{module_name}.py",
        "-v",
        "--tb=no",
        "-q",
    ]

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = "/workspaces/linebot.test"
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd="/workspaces/linebot.test", env=env
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def main():
    """Generate test summary."""
    modules = [
        "app_endpoints",
        "cache_manager",
        "token_manager",
        "models",
        "mqtt_handler",
        "rate_limiter",
        "secret_manager",
        "line_webhook",
    ]

    results = {}

    print("=== Test Module Summary ===")
    for module in modules:
        success, stdout, stderr = run_test_module(module)
        status = "PASS" if success else "FAIL"
        print(f"{module:20} {status}")

        if not success and stderr:
            print(f"  Error: {stderr.strip()}")

        results[module] = success

    print("\n=== Overall Results ===")
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    print(f"Passed: {passed}/{total} modules")

    if passed < total:
        print("\nFailed modules:")
        for module, success in results.items():
            if not success:
                print(f"  - {module}")


if __name__ == "__main__":
    main()
