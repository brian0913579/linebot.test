"""
Tests for the webhook handler (app/api/webhooks.py).

Covers: signature validation, message routing, auth checks, door commands,
camera commands, and unrecognised messages.
"""

import json
import hashlib
import hmac
import base64
from unittest.mock import MagicMock, patch, call

import pytest


def _sign(body: str, secret: str) -> str:
    """Compute the X-Line-Signature for *body* using *secret*."""
    return base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()


# ------------------------------------------------------------------
# Webhook endpoint
# ------------------------------------------------------------------


class TestWebhookEndpoint:
    """POST /webhook — signature validation."""

    def test_valid_signature_returns_200(self, client, app):
        """A correctly signed body is accepted."""
        body = json.dumps({"events": []})
        sig = _sign(body, app.config["LINE_CHANNEL_SECRET"])
        resp = client.post(
            "/webhook",
            data=body,
            content_type="application/json",
            headers={"X-Line-Signature": sig},
        )
        assert resp.status_code == 200

    def test_invalid_signature_returns_400(self, client):
        """A bad signature triggers a 400."""
        from linebot.v3.exceptions import InvalidSignatureError

        with patch(
            "app.api.webhooks.line_service.handler.handle",
            side_effect=InvalidSignatureError("bad"),
        ):
            resp = client.post(
                "/webhook",
                data="{}",
                content_type="application/json",
                headers={"X-Line-Signature": "invalidsig"},
            )
        assert resp.status_code == 400

    def test_missing_signature_still_calls_handler(self, client):
        """Missing header sends empty string to the SDK (SDK decides)."""
        resp = client.post(
            "/webhook", data="{}", content_type="application/json"
        )
        # The handler is a mock, so it won't raise — returns 200
        assert resp.status_code == 200

    def test_unexpected_exception_returns_500(self, client):
        with patch("app.api.webhooks.line_service.handler.handle", side_effect=Exception("mocked error")):
            resp = client.post(
                "/webhook",
                data="{}",
                content_type="application/json",
                headers={"X-Line-Signature": "invalidsig"}
            )
        assert resp.status_code == 500


# ------------------------------------------------------------------
# Text message handler — exercise the real logic extracted from webhooks.py
# ------------------------------------------------------------------

def _make_event(user_id="Utest123", text="開門"):
    """Build a minimal mock MessageEvent."""
    event = MagicMock()
    event.source.user_id = user_id
    event.message.text = text
    event.reply_token = "test-reply-token"
    return event


def _run_handle_text(app, event):
    """Execute the core handle_text logic directly, bypassing the decorator.

    We replicate the logic flow from webhooks.py without going through the
    LINE SDK handler.add() decorator, which doesn't work in test context
    because line_service.handler is a mock at import time.
    """
    from app.api.webhooks import DOOR_COMMANDS
    from app.models.datastore_client import add_pending_user, get_allowed_users
    from app.services.line_service import line_service
    from app.services.mqtt_service import send_garage_command
    from app.services.token_service import token_service

    user_id = event.source.user_id
    user_msg = event.message.text

    camera_commands = ("監控", "監控畫面")
    if user_msg not in DOOR_COMMANDS and user_msg not in camera_commands:
        return

    ALLOWED_USERS = get_allowed_users()
    if user_id not in ALLOWED_USERS:
        add_pending_user(user_id)
        line_service.reply_text(
            event.reply_token,
            "🔒 您尚未開通權限。\n\n已自動將您的申請送出給管理員，請耐心等候審核。",
        )
        return

    if user_msg in camera_commands:
        return line_service.send_camera_link(user_id, event.reply_token)

    action = DOOR_COMMANDS[user_msg]
    if not token_service.is_user_authorized(user_id):
        return line_service.send_verification_message(user_id, event.reply_token, action)

    # In the real code the MQTT call is offloaded to a thread.
    # For testing we just call it synchronously.
    success, error = send_garage_command(action)
    action_label = "開啟" if action == "open" else "關閉"
    if success:
        line_service.reply_text(event.reply_token, f"✅ 車庫門已{action_label}，請小心進出。")
    else:
        line_service.reply_text(event.reply_token, "⚠️ 無法連接車庫控制器，請稍後再試。")


class TestHandleText:
    """Unit tests for the message processing logic in webhooks.py."""

    @patch("app.api.webhooks.line_service")
    @patch("app.models.datastore_client.get_datastore_client")
    @patch("app.models.datastore_client.datastore")
    def test_unauthorized_user_gets_pending(self, mock_ds_mod, mock_client, mock_ls, app):
        from tests.conftest import FakeDatastoreClient, FakeEntity
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        mock_ds_mod.Entity = lambda key: FakeEntity(key)

        with app.app_context():
            from app.api.webhooks import handle_text
            event = _make_event(user_id="Unew", text="開門")
            handle_text(event)

        mock_ls.reply_text.assert_called_once()
        assert "Unew" in ds._store.get("pending_users", {})

    @patch("app.api.webhooks.send_garage_command", return_value=(True, None))
    @patch("app.api.webhooks.token_service")
    @patch("app.api.webhooks.line_service")
    @patch("app.models.datastore_client.get_datastore_client")
    def test_authorized_user_open_door(self, mock_client, mock_ls, mock_ts, mock_mqtt, app):
        from tests.conftest import FakeDatastoreClient, FakeEntity, FakeKey
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        # Seed allowed user
        entity = FakeEntity(FakeKey("allowed_users", "Uauth"), {"user_id": "Uauth", "user_name": "Alice"})
        ds._store.setdefault("allowed_users", {})["Uauth"] = entity

        mock_ts.is_user_authorized.return_value = True

        with app.app_context():
            from app.api.webhooks import handle_text
            event = _make_event(user_id="Uauth", text="開門")
            handle_text(event)

        mock_ts.is_user_authorized.assert_called_once_with("Uauth")
        mock_mqtt.assert_called_once_with("open")
        mock_ls.reply_text.assert_called_once()
        assert "開啟" in mock_ls.reply_text.call_args[0][1]

    @patch("app.api.webhooks.token_service")
    @patch("app.api.webhooks.line_service")
    @patch("app.models.datastore_client.get_datastore_client")
    def test_unverified_user_gets_verification_link(self, mock_client, mock_ls, mock_ts, app):
        from tests.conftest import FakeDatastoreClient, FakeEntity, FakeKey
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        entity = FakeEntity(FakeKey("allowed_users", "Uauth"), {"user_id": "Uauth", "user_name": "Alice"})
        ds._store.setdefault("allowed_users", {})["Uauth"] = entity

        mock_ts.is_user_authorized.return_value = False

        with app.app_context():
            from app.api.webhooks import handle_text
            event = _make_event(user_id="Uauth", text="關門")
            handle_text(event)

        mock_ls.send_verification_message.assert_called_once_with(
            "Uauth", "test-reply-token", "close"
        )

    @patch("app.api.webhooks.line_service")
    @patch("app.models.datastore_client.get_datastore_client")
    def test_camera_command(self, mock_client, mock_ls, app):
        from tests.conftest import FakeDatastoreClient, FakeEntity, FakeKey
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        entity = FakeEntity(FakeKey("allowed_users", "Ucam"), {"user_id": "Ucam", "user_name": "Bob"})
        ds._store.setdefault("allowed_users", {})["Ucam"] = entity

        with app.app_context():
            from app.api.webhooks import handle_text
            event = _make_event(user_id="Ucam", text="監控")
            handle_text(event)

        mock_ls.send_camera_link.assert_called_once_with("Ucam", "test-reply-token")

    @patch("app.api.webhooks.line_service")
    @patch("app.models.datastore_client.get_datastore_client")
    def test_unrecognized_message_ignored(self, mock_client, mock_ls, app):
        from tests.conftest import FakeDatastoreClient
        ds = FakeDatastoreClient()
        mock_client.return_value = ds

        with app.app_context():
            from app.api.webhooks import handle_text
            event = _make_event(user_id="U1", text="你好")
            handle_text(event)

        mock_ls.reply_text.assert_not_called()

    @patch("app.api.webhooks.send_garage_command", return_value=(False, "broker down"))
    @patch("app.api.webhooks.token_service")
    @patch("app.api.webhooks.line_service")
    @patch("app.models.datastore_client.get_datastore_client")
    def test_authorized_user_open_door_fails(self, mock_client, mock_ls, mock_ts, mock_mqtt, app):
        from tests.conftest import FakeDatastoreClient, FakeEntity, FakeKey
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        entity = FakeEntity(FakeKey("allowed_users", "Uauth"), {"user_id": "Uauth", "user_name": "Alice"})
        ds._store.setdefault("allowed_users", {})["Uauth"] = entity

        mock_ts.is_user_authorized.return_value = True

        with app.app_context():
            from app.api.webhooks import handle_text
            event = _make_event(user_id="Uauth", text="開門")
            handle_text(event)

        mock_mqtt.assert_called_once_with("open")
        mock_ls.reply_text.assert_called_once()
        assert "無法連接車庫控制器" in mock_ls.reply_text.call_args[0][1]

    @patch("app.api.webhooks.token_service")
    @patch("app.api.webhooks.line_service")
    @patch("app.models.datastore_client.get_datastore_client")
    def test_handle_text_exception(self, mock_client, mock_ls, mock_ts, app):
        from tests.conftest import FakeDatastoreClient, FakeEntity, FakeKey
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        entity = FakeEntity(FakeKey("allowed_users", "Uauth"), {"user_id": "Uauth", "user_name": "Alice"})
        ds._store.setdefault("allowed_users", {})["Uauth"] = entity

        mock_ts.is_user_authorized.side_effect = Exception("System Failure")

        with app.app_context():
            from app.api.webhooks import handle_text
            event = _make_event(user_id="Uauth", text="開門")
            handle_text(event)

        mock_ls.handle_system_error.assert_called_once()
        mock_ls.send_verification_message.assert_not_called()
        mock_ls.send_camera_link.assert_not_called()
