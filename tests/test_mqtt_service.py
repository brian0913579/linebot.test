"""
Tests for MQTT garage command service (app/services/mqtt_service.py).

Covers: successful open/close, connection timeout retry, publish failure retry.
"""

from unittest.mock import patch, MagicMock, PropertyMock

import pytest


@pytest.fixture()
def _mock_ssl():
    """Patch ssl so create_mqtt_client doesn't need a real CA cert."""
    with patch("app.services.mqtt_service.ssl.create_default_context") as ctx:
        yield ctx


class TestSendGarageCommand:
    @patch("app.services.mqtt_service.mqtt.Client")
    def test_open_publishes_up(self, MockClient, app, _mock_ssl):
        client = MagicMock()
        client.is_connected.return_value = True
        result = MagicMock()
        result.is_published.return_value = True
        client.publish.return_value = result
        MockClient.return_value = client

        with app.app_context():
            from app.services.mqtt_service import send_garage_command
            ok, err = send_garage_command("open")

        assert ok is True
        assert err is None
        client.publish.assert_called_once()
        args = client.publish.call_args
        assert args[0][1] == "up"

    @patch("app.services.mqtt_service.mqtt.Client")
    def test_close_publishes_down(self, MockClient, app, _mock_ssl):
        client = MagicMock()
        client.is_connected.return_value = True
        result = MagicMock()
        result.is_published.return_value = True
        client.publish.return_value = result
        MockClient.return_value = client

        with app.app_context():
            from app.services.mqtt_service import send_garage_command
            ok, _ = send_garage_command("close")

        assert ok is True
        args = client.publish.call_args
        assert args[0][1] == "down"

    @patch("app.services.mqtt_service.RETRY_DELAY", 0)
    @patch("app.services.mqtt_service.CONNECT_TIMEOUT", 0.01)
    @patch("app.services.mqtt_service.mqtt.Client")
    def test_connection_timeout_retries(self, MockClient, app, _mock_ssl):
        client = MagicMock()
        client.is_connected.return_value = False  # never connects
        MockClient.return_value = client

        with app.app_context():
            from app.services.mqtt_service import send_garage_command
            ok, err = send_garage_command("open")

        assert ok is False
        assert "timed out" in err.lower() or "failed" in err.lower()

    @patch("app.services.mqtt_service.RETRY_DELAY", 0)
    @patch("app.services.mqtt_service.mqtt.Client")
    def test_publish_failure_retries(self, MockClient, app, _mock_ssl):
        client = MagicMock()
        client.is_connected.return_value = True
        result = MagicMock()
        result.is_published.return_value = False
        result.wait_for_publish.side_effect = Exception("publish timeout")
        client.publish.return_value = result
        MockClient.return_value = client

        with app.app_context():
            from app.services.mqtt_service import send_garage_command
            ok, err = send_garage_command("open")

        assert ok is False

    def test_publish_timeout_exception(self, app):
        from app.services.mqtt_service import create_mqtt_client, send_garage_command

        fake_client = MagicMock()
        fake_client.is_connected.return_value = True

        fake_result = MagicMock()
        fake_result.is_published.return_value = False
        fake_client.publish.return_value = fake_result

        with app.app_context():
            with patch("app.services.mqtt_service.create_mqtt_client", return_value=(fake_client, None)):
                # Mock retry logic to fail fast
                with patch("app.services.mqtt_service.MAX_RETRIES", 1), patch("app.services.mqtt_service.RETRY_DELAY", 0):
                    ok, err = send_garage_command("open")
                    
        assert ok is False
        assert "Failed to send MQTT command" in err

    @patch("app.services.mqtt_service.mqtt.Client")
    def test_on_connect_callback(self, MockClient, app, _mock_ssl):
        from app.services.mqtt_service import create_mqtt_client
        with app.app_context():
            with patch.object(MockClient.return_value, "connect"), patch.object(MockClient.return_value, "loop_start"):
                client, _ = create_mqtt_client()
            
            with patch("app.services.mqtt_service.logging") as mock_logging:
                client.on_connect(client, None, None, 0)
                mock_logging.info.assert_called_with("Connected to MQTT broker successfully")
                
                client.on_connect(client, None, None, 4)
                mock_logging.error.assert_called_with("Failed to connect to MQTT broker: bad username or password")
                
                client.on_connect(client, None, None, 1)
                assert "Failed to connect to MQTT broker" in mock_logging.error.call_args[0][0]
                
            with patch("app.services.mqtt_service.logger") as mock_logger:
                client.on_publish(client, None, 123)
                mock_logger.debug.assert_called_with("Message 123 published successfully")

    @patch("app.services.mqtt_service.mqtt.Client")
    def test_on_disconnect_callback(self, MockClient, app, _mock_ssl):
        from app.services.mqtt_service import create_mqtt_client
        with app.app_context():
            # Mock the client instance natively
            MockClient.return_value.connect.return_value = 0
            MockClient.return_value.loop_start.return_value = None
            client, _ = create_mqtt_client()
            
            with patch("app.services.mqtt_service.logging") as mock_logging:
                client.on_disconnect(client, None, 0)
                
                client.on_disconnect(client, None, 1)
                mock_logging.warning.assert_called_with("Unexpected disconnection from MQTT broker")
