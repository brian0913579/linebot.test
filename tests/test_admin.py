"""
Tests for the admin dashboard (app/api/admin.py).

Covers: login/logout, session auth, approve/reject/delete users, audit logging.
"""

from unittest.mock import patch, MagicMock

import pytest


class TestAdminLogin:
    def test_login_page_renders(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200

    def test_login_success(self, client, app):
        resp = client.post(
            "/admin/login",
            data={
                "username": app.config["ADMIN_USERNAME"],
                "password": app.config["ADMIN_PASSWORD"],
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302  # redirect to dashboard

    def test_login_invalid_creds(self, client):
        resp = client.post(
            "/admin/login",
            data={"username": "wrong", "password": "wrong"},
            follow_redirects=True,
        )
        assert b"Invalid credentials" in resp.data

    def test_logout_clears_session(self, client, app):
        # Login first
        client.post(
            "/admin/login",
            data={
                "username": app.config["ADMIN_USERNAME"],
                "password": app.config["ADMIN_PASSWORD"],
            },
        )
        resp = client.get("/admin/logout", follow_redirects=True)
        assert resp.status_code == 200


class TestAdminDashboard:
    def test_requires_auth(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302  # redirect to login

    @patch("app.api.admin.get_allowed_users", return_value={"U1": "Alice"})
    @patch("app.api.admin.get_pending_users", return_value={})
    def test_dashboard_renders_when_logged_in(self, mock_pu, mock_au, client, app):
        # Login
        client.post(
            "/admin/login",
            data={
                "username": app.config["ADMIN_USERNAME"],
                "password": app.config["ADMIN_PASSWORD"],
            },
        )
        resp = client.get("/admin/")
        assert resp.status_code == 200


class TestAdminActions:
    @pytest.fixture(autouse=True)
    def _login(self, client, app):
        client.post(
            "/admin/login",
            data={
                "username": app.config["ADMIN_USERNAME"],
                "password": app.config["ADMIN_PASSWORD"],
            },
        )

    @patch("app.api.admin.log_admin_action")
    @patch("app.api.admin.remove_pending_user", return_value=True)
    @patch("app.api.admin.add_user", return_value=True)
    def test_approve_user(self, mock_add, mock_rm, mock_log, client):
        resp = client.post(
            "/admin/approve",
            data={"user_id": "U1", "user_name": "Alice"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        mock_add.assert_called_once_with("U1", "Alice")
        mock_rm.assert_called_once_with("U1")
        mock_log.assert_called_once()

    @patch("app.api.admin.log_admin_action")
    @patch("app.api.admin.remove_pending_user", return_value=True)
    def test_reject_user(self, mock_rm, mock_log, client):
        resp = client.post(
            "/admin/reject",
            data={"user_id": "U2"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        mock_rm.assert_called_once_with("U2")

    @patch("app.api.admin.log_admin_action")
    @patch("app.api.admin.remove_user", return_value=True)
    def test_delete_user(self, mock_rm, mock_log, client):
        resp = client.post(
            "/admin/delete",
            data={"user_id": "U3"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        mock_rm.assert_called_once_with("U3")

    @patch("app.api.admin.log_admin_action")
    @patch("app.api.admin.update_user", return_value=True)
    def test_edit_user(self, mock_update, mock_log, client):
        resp = client.post(
            "/admin/edit_user",
            data={
                "user_id": "U1",
                "nickname": "Ally",
                "parking_space": "B1",
                "is_admin": "on",
                "is_moderator": "off",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        mock_update.assert_called_once_with("U1", {
            "nickname": "Ally",
            "start_date": "",
            "end_date": "",
            "parking_space": "B1",
            "is_admin": True,
            "is_moderator": False,
        })
        mock_log.assert_called_once()

    def test_edit_user_missing_id(self, client):
        resp = client.post("/admin/edit_user", data={}, follow_redirects=True)
        assert b"Missing user ID" in resp.data

    @patch("app.api.admin.update_user", return_value=False)
    def test_edit_user_fail(self, mock_update, client):
        resp = client.post(
            "/admin/edit_user",
            data={"user_id": "U1"},
            follow_redirects=True,
        )
        assert b"Failed to update user" in resp.data

    @patch("app.services.storage_service.upload_contract_photo", return_value="http://fake")
    @patch("app.api.admin.update_user", return_value=True)
    def test_edit_user_with_photo(self, mock_update, mock_upload, client):
        import io
        resp = client.post(
            "/admin/edit_user",
            data={
                "user_id": "U2",
                "contract_photo": (io.BytesIO(b"abc"), "contract.pdf")
            },
            content_type="multipart/form-data",
            follow_redirects=False
        )
        assert resp.status_code == 302
        mock_upload.assert_called_once()
        mock_update.assert_called_once()
        updates = mock_update.call_args[0][1]
        assert updates["contract_url"] == "http://fake"

    @patch("app.services.storage_service.upload_contract_photo", return_value=None)
    @patch("app.api.admin.update_user", return_value=True)
    def test_edit_user_with_photo_fail(self, mock_update, mock_upload, client):
        import io
        resp = client.post(
            "/admin/edit_user",
            data={
                "user_id": "U2",
                "contract_photo": (io.BytesIO(b"abc"), "contract.pdf")
            },
            content_type="multipart/form-data",
            follow_redirects=False
        )
        assert resp.status_code == 302
        mock_upload.assert_called_once()
        mock_update.assert_called_once()
        updates = mock_update.call_args[0][1]
        assert "contract_url" not in updates

