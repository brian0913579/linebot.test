"""
Tests for app/config.py edge cases, particularly missing secrets.
"""

import sys
import importlib
from unittest.mock import patch, MagicMock

import pytest


class TestConfigLoading:
    @pytest.fixture(autouse=True)
    def clean_env(self):
        import os, importlib
        original = dict(os.environ)
        
        # Store original sys.modules items we might touch
        gc_orig = sys.modules.get("google.cloud")
        gcsm_orig = sys.modules.get("google.cloud.secretmanager")
        
        yield
        
        os.environ.clear()
        os.environ.update(original)
        
        # Restore sys.modules
        if gc_orig:
            sys.modules["google.cloud"] = gc_orig
        elif "google.cloud" in sys.modules:
            del sys.modules["google.cloud"]
            
        if gcsm_orig:
            sys.modules["google.cloud.secretmanager"] = gcsm_orig
        elif "google.cloud.secretmanager" in sys.modules:
            del sys.modules["google.cloud.secretmanager"]
            
        import app.config as config_mod
        importlib.reload(config_mod)

    def test_get_secret_returns_default(self):
        """When GCP is used but the project ID is missing, it uses default."""
        import app.config as config_mod
        
        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.side_effect = Exception("No project ID")
        
        import os
        env = dict(os.environ)
        env["SECRETS_BACKEND"] = "gcp"
        if "GOOGLE_CLOUD_PROJECT" in env:
            del env["GOOGLE_CLOUD_PROJECT"]
            
        with patch.dict("sys.modules", {"google.cloud.secretmanager": mock_sm, "google.cloud": MagicMock(secretmanager=mock_sm)}):
            with patch.dict("os.environ", env, clear=True):
                importlib.reload(config_mod)
                assert config_mod.USE_GOOGLE_SECRET_MANAGER is True
                val = config_mod.get_secret("TEST_MISSING", default="mydef")
                assert val == "mydef"

    def test_get_secret_no_sm_library(self):
        """When google.cloud.secretmanager is not installed, it falls back to environment."""
        import app.config as config_mod
        import os
        env = dict(os.environ)
        env["SECRETS_BACKEND"] = "gcp"
        env["TEST_ENV"] = "env_val"
        
        with patch.dict("sys.modules", {"google.cloud.secretmanager": None}):
            with patch.dict("os.environ", env, clear=True):
                importlib.reload(config_mod)
                assert config_mod.USE_GOOGLE_SECRET_MANAGER is False
                val = config_mod.get_secret("TEST_ENV")
                assert val == "env_val"

    def test_get_secret_gcp_api_error(self):
        """When GCP API fails (e.g., secret not found), it falls back to environment and default."""
        import app.config as config_mod
        
        mock_sm = MagicMock()
        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = Exception("Not found")
        mock_sm.SecretManagerServiceClient.return_value = mock_client
        
        import os
        env = dict(os.environ)
        env["SECRETS_BACKEND"] = "gcp"
        env["GOOGLE_CLOUD_PROJECT"] = "test-proj"
        
        with patch.dict("sys.modules", {"google.cloud.secretmanager": mock_sm, "google.cloud": MagicMock(secretmanager=mock_sm)}):
            with patch.dict("os.environ", env, clear=True):
                importlib.reload(config_mod)
                assert config_mod.USE_GOOGLE_SECRET_MANAGER is True
                val = config_mod.get_secret("MISSING_SECRET_API", default="fallback")
                assert val == "fallback"

    def test_get_secret_returns_gcp_value(self):
        """When GCP is used and API succeeds, it extracts and returns the secret data."""
        import app.config as config_mod
        
        mock_sm = MagicMock()
        mock_client = MagicMock()
        # Ensure it works correctly to cover decode() line 38, and line 51
        fake_payload = MagicMock()
        fake_payload.data = b"8883"
        mock_client.access_secret_version.return_value = MagicMock(payload=fake_payload)
        mock_sm.SecretManagerServiceClient.return_value = mock_client
        import os
        env = dict(os.environ)
        env["SECRETS_BACKEND"] = "gcp"
        env["GOOGLE_CLOUD_PROJECT"] = "test-proj"
        
        with patch.dict("sys.modules", {"google.cloud.secretmanager": mock_sm, "google.cloud": MagicMock(secretmanager=mock_sm)}):
            with patch.dict("os.environ", env, clear=True):
                importlib.reload(config_mod)
                val = config_mod.get_secret("GCP_SECRET_KEY")
                assert val == "8883"
            
    def test_load_dotenv_called(self):
        """Verify that load_dotenv is called if .env exists."""
        import app.config as config_mod
        import importlib
        
        # Create a real dummy .env file
        did_create = False
        if not config_mod.env_path.exists():
            config_mod.env_path.touch()
            did_create = True
            
        try:
            with patch("dotenv.load_dotenv") as mock_load:
                importlib.reload(config_mod)
                mock_load.assert_called_once()
        finally:
            if did_create and config_mod.env_path.exists():
                config_mod.env_path.unlink()
