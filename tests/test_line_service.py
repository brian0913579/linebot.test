"""
Tests for the LineService wrapper (app/services/line_service.py).

Covers initialization exceptions, message sending wrappers, system error handling,
camera links, and retry logic.
"""

from unittest.mock import patch, MagicMock, ANY

import pytest


class TestLineService:
    @pytest.fixture
    def mock_app(self, app):
        """Returns the flask app fixture."""
        return app

    def test_init_app_missing_credentials(self, mock_app):
        from app.services.line_service import LineService
        
        # Unset credentials
        original_token = mock_app.config["LINE_CHANNEL_ACCESS_TOKEN"]
        original_secret = mock_app.config["LINE_CHANNEL_SECRET"]
        
        try:
            mock_app.config["LINE_CHANNEL_ACCESS_TOKEN"] = ""
            with pytest.raises(RuntimeError, match="LINE credentials not available"):
                LineService(mock_app)
        finally:
            mock_app.config["LINE_CHANNEL_ACCESS_TOKEN"] = original_token
            mock_app.config["LINE_CHANNEL_SECRET"] = original_secret

    @patch("app.services.line_service.time.sleep")
    def test_retry_api_call_success(self, mock_sleep):
        from app.services.line_service import LineService
        svc = LineService()
        
        mock_func = MagicMock()
        mock_func.side_effect = [Exception("fail1"), "success"]
        
        res = svc._retry_api_call(mock_func, max_attempts=3, delay=0.1)
        assert res == "success"
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(0.1)

    @patch("app.services.line_service.time.sleep")
    def test_retry_api_call_exhausted(self, mock_sleep):
        from app.services.line_service import LineService
        svc = LineService()
        
        import linebot.v3.exceptions
        mock_api = MagicMock()
        mock_api.reply_message.side_effect = Exception("always fail")
        
        with pytest.raises(Exception):
            svc._retry_api_call(mock_api.reply_message, delay=0.1)
            
        assert mock_api.reply_message.call_count == 3
        mock_sleep.assert_called_with(0.1)

    @patch("app.services.line_service.token_service")
    def test_send_verification_message(self, mock_ts, mock_app):
        from app.services.line_service import LineService
        svc = LineService(mock_app)
        svc.line_bot_api = MagicMock()
        
        with mock_app.app_context():
            svc.send_verification_message("U1", "token1", "open")
            
        mock_ts.store_verify_token.assert_called_once()
        svc.line_bot_api.reply_message.assert_called_once()
        
        # Check generated message
        req = svc.line_bot_api.reply_message.call_args[0][0]
        assert req.reply_token == "token1"
        assert req.messages[0].template.text.find("開門") != -1

    def test_reply_text(self, mock_app):
        from app.services.line_service import LineService
        svc = LineService(mock_app)
        svc.line_bot_api = MagicMock()
        
        svc.reply_text("token2", "hello")
        
        svc.line_bot_api.reply_message.assert_called_once()
        req = svc.line_bot_api.reply_message.call_args[0][0]
        assert req.messages[0].text == "hello"
        assert req.reply_token == "token2"

    @patch("app.api.camera.generate_camera_token")
    def test_send_camera_link(self, mock_gct, mock_app):
        mock_gct.return_value = "camtoken"
        from app.services.line_service import LineService
        svc = LineService(mock_app)
        svc.line_bot_api = MagicMock()
        
        with mock_app.app_context():
            svc.send_camera_link("U2", "token3")
            
        svc.line_bot_api.reply_message.assert_called_once()
        req = svc.line_bot_api.reply_message.call_args[0][0]
        assert req.reply_token == "token3"
        uri = req.messages[0].template.actions[0].uri
        assert "camtoken" in uri

    def test_handle_system_error_success(self, mock_app):
        from app.services.line_service import LineService
        svc = LineService(mock_app)
        svc.line_bot_api = MagicMock()
        
        svc.handle_system_error("U3", "token4", "some DB error", "DB Sync")
        svc.line_bot_api.reply_message.assert_called_once()
        req = svc.line_bot_api.reply_message.call_args[0][0]
        assert req.messages[0].text.find("系統錯誤") != -1

    @patch("app.services.line_service.logger")
    def test_handle_system_error_reply_fails(self, mock_logger, mock_app):
        from app.services.line_service import LineService
        svc = LineService(mock_app)
        svc.line_bot_api = MagicMock()
        svc.line_bot_api.reply_message.side_effect = Exception("Reply token expired")
        
        # Should catch the error and log a warning instead of raising
        svc.handle_system_error("U4", "token5", "some error", "Context")
        
        mock_logger.warning.assert_called()
        assert mock_logger.warning.call_count == 4
        assert "Reply token expired" in mock_logger.warning.call_args[0][0]
