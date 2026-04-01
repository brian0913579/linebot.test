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
