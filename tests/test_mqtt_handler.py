from unittest.mock import MagicMock, patch

import pytest

from core.mqtt_handler import (
    create_mqtt_client,
    on_connect,
    on_disconnect,
    on_publish,
    send_garage_command,
)


# Fixture for mocking the MQTT client
@pytest.fixture
def mock_mqtt():
    with patch("core.mqtt_handler.mqtt.Client") as mock_client:
        # Create a mock instance
        instance = mock_client.return_value

        # Configure the instance to report successful connection
        instance.is_connected.return_value = True

        # Mock publish result
        publish_result = MagicMock()
        publish_result.is_published.return_value = True
        publish_result.wait_for_publish.return_value = None
        instance.publish.return_value = publish_result

        # Return the mock
        yield instance


# Fixture for mocking SSL context
@pytest.fixture
def mock_ssl():
    with patch("core.mqtt_handler.ssl.create_default_context") as mock_ssl:
        ssl_context = MagicMock()
        mock_ssl.return_value = ssl_context
        yield ssl_context


# Test client creation
def test_create_mqtt_client(mock_mqtt, mock_ssl):
    """Test MQTT client creation and configuration."""
    with patch("core.mqtt_handler.MQTT_USERNAME", "test_user"):
        with patch("core.mqtt_handler.MQTT_PASSWORD", "test_pass"):
            client, ssl_ctx = create_mqtt_client()

            # Verify the client was created
            assert client is mock_mqtt

            # Verify SSL was configured
            assert ssl_ctx is mock_ssl

            # Verify credentials were set
            mock_mqtt.username_pw_set.assert_called_with("test_user", "test_pass")

            # Verify SSL was set
            mock_mqtt.tls_set_context.assert_called_with(mock_ssl)

            # Verify callbacks were set
            assert mock_mqtt.on_connect == on_connect
            assert mock_mqtt.on_publish == on_publish
            assert mock_mqtt.on_disconnect == on_disconnect


# Test successful command sending
@patch("core.mqtt_handler.create_mqtt_client")
def test_send_garage_command_success(mock_create_client, mock_mqtt):
    """Test successful sending of garage command."""
    # Setup the mock
    mock_create_client.return_value = (mock_mqtt, None)

    # Test open command
    with patch("core.mqtt_handler.MQTT_TOPIC", "test/topic"):
        success, error = send_garage_command("open")

        # Verify connection was established
        mock_mqtt.connect_async.assert_called()
        mock_mqtt.loop_start.assert_called()

        # Verify command was published correctly
        mock_mqtt.publish.assert_called_with("test/topic", "up", qos=1)

        # Verify cleanup
        mock_mqtt.loop_stop.assert_called()
        mock_mqtt.disconnect.assert_called()

        # Verify result
        assert success is True
        assert error is None


# Test connection failure
@patch("core.mqtt_handler.create_mqtt_client")
def test_send_garage_command_connection_failure(mock_create_client):
    """Test handling of connection failure."""
    # Create a mock client that will fail to connect
    mock_client = MagicMock()
    mock_client.is_connected.return_value = False
    mock_create_client.return_value = (mock_client, None)

    # Patch retry settings for faster test
    with patch("core.mqtt_handler.MAX_RETRIES", 2):
        with patch("core.mqtt_handler.RETRY_DELAY", 0.01):
            with patch("core.mqtt_handler.CONNECT_TIMEOUT", 0.1):
                # Test command
                success, error = send_garage_command("close")

                # Verify connection was attempted multiple times
                assert mock_client.connect_async.call_count == 2

                # Verify result indicates failure
                assert success is False
                assert error is not None
                assert "timed out" in error.lower() or "failed" in error.lower()


# Test publish failure
@patch("core.mqtt_handler.create_mqtt_client")
def test_send_garage_command_publish_failure(mock_create_client, mock_mqtt):
    """Test handling of publish failure."""
    # Setup the mock with publish failure
    mock_create_client.return_value = (mock_mqtt, None)

    # Configure the publish result to indicate failure
    publish_result = MagicMock()
    publish_result.is_published.return_value = False
    mock_mqtt.publish.return_value = publish_result

    # Patch retry settings for faster test
    with patch("core.mqtt_handler.MAX_RETRIES", 2):
        with patch("core.mqtt_handler.RETRY_DELAY", 0.01):
            # Test command
            success, error = send_garage_command("open")

            # Verify publish was attempted
            assert mock_mqtt.publish.call_count > 0

            # Verify result indicates failure
            assert success is False
            assert error is not None
            assert "failed to publish" in error.lower()


# Test callback functions
def test_on_connect_success(caplog):
    """Test on_connect callback with successful connection."""
    client = MagicMock()
    userdata = None
    flags = {}
    rc = 0  # success code

    on_connect(client, userdata, flags, rc)

    # Verify successful connection was logged
    assert any(
        "Connected to MQTT broker successfully" in record.message
        for record in caplog.records
    )
    # Verify no errors or warnings were logged
    assert not any(
        record.levelname in ["ERROR", "WARNING"] for record in caplog.records
    )


def test_on_connect_failure(caplog):
    """Test on_connect callback with connection failure."""
    client = MagicMock()
    userdata = None
    flags = {}
    rc = 4  # bad username/password code

    on_connect(client, userdata, flags, rc)

    # Verify error was logged
    assert any(
        "Failed to connect to MQTT broker" in record.message
        for record in caplog.records
    )
    assert any(
        "bad username or password" in record.message for record in caplog.records
    )


def test_on_disconnect_unexpected(caplog):
    """Test on_disconnect callback with unexpected disconnection."""
    client = MagicMock()
    userdata = None
    rc = 1  # unexpected disconnect code

    on_disconnect(client, userdata, rc)

    # Verify warning was logged
    assert any(
        "Unexpected disconnection" in record.message for record in caplog.records
    )
