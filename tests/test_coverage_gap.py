from unittest.mock import patch, MagicMock
from app.api.admin import check_auth
from app.services.line_service import LineService
from app.services.mqtt_service import send_garage_command

def test_admin_check_auth_warning(app):
    with app.app_context():
        app.config["ADMIN_PASSWORD"] = "password"
        with patch("app.api.admin.logger") as mock_log:
            check_auth("admin", "password")
            mock_log.warning.assert_called_with("Using default admin password! Please set ADMIN_PASSWORD.")

def test_admin_approve_user_fails(client):
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    with patch("app.api.admin.add_user", return_value=False):
        client.post("/admin/approve", data={"user_id": "U1", "user_name": "Alice"})

def test_admin_approve_missing_data(client):
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    client.post("/admin/approve", data={})

def test_admin_reject_fails(client):
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    with patch("app.api.admin.remove_pending_user", return_value=False):
        client.post("/admin/reject", data={"user_id": "U1"})
        
def test_admin_delete_fails(client):
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    with patch("app.api.admin.remove_user", return_value=False):
        client.post("/admin/delete", data={"user_id": "U1"})

def test_line_service_system_error_return_none(app):
    with app.app_context():
        svc = LineService(app)
        svc.line_bot_api = MagicMock()
        svc.line_bot_api.reply_message.side_effect = Exception("err")
        assert svc.handle_system_error("U1", "token", "err", "ctx") is None

def test_line_service_zero_retries(app):
    with app.app_context():
        svc = LineService(app)
        assert svc._retry_api_call(lambda: True, max_attempts=0) is None

def test_token_service_get_camera_expired(app):
    with app.app_context():
        from app.services.token_service import token_service
        with patch.object(token_service, "_db") as mock_db:
            import time
            fake_entity = {"user_id": "U1", "expiry": time.time() - 100}
            mock_db.return_value.get.return_value = fake_entity
            user, exp = token_service.get_camera_token("expired")
            assert user is None
            assert exp is None

def test_token_service_get_camera_not_found(app):
    with app.app_context():
        from app.services.token_service import token_service
        with patch.object(token_service, "_db") as mock_db:
            mock_db.return_value.get.return_value = None
            user, exp = token_service.get_camera_token("missing")
            assert user is None
            assert exp is None

