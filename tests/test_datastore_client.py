"""
Tests for the Datastore client (app/models/datastore_client.py).

Covers: allowed user CRUD, pending user lifecycle, audit logging.
All tests use a FakeDatastoreClient from conftest.
"""

from unittest.mock import patch

import pytest


class TestAllowedUsers:
    @patch("app.models.datastore_client.get_datastore_client")
    def test_get_allowed_users_empty(self, mock_client):
        from tests.conftest import FakeDatastoreClient
        ds = FakeDatastoreClient()
        mock_client.return_value = ds

        from app.models.datastore_client import get_allowed_users
        assert get_allowed_users() == {}

    @patch("app.models.datastore_client.get_datastore_client")
    @patch("app.models.datastore_client.datastore")
    def test_add_and_get_user(self, mock_ds_mod, mock_client):
        from tests.conftest import FakeDatastoreClient, FakeEntity, FakeKey
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        mock_ds_mod.Entity = lambda key: FakeEntity(key)

        from app.models.datastore_client import add_user, get_allowed_users

        result = add_user("U1", "Alice")
        assert result is True

        users = get_allowed_users()
        assert "U1" in users

    @patch("app.models.datastore_client.get_datastore_client")
    @patch("app.models.datastore_client.datastore")
    def test_remove_user(self, mock_ds_mod, mock_client):
        from tests.conftest import FakeDatastoreClient, FakeEntity
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        mock_ds_mod.Entity = lambda key: FakeEntity(key)

        from app.models.datastore_client import add_user, remove_user, get_allowed_users

        add_user("U1", "Alice")
        remove_user("U1")
        assert "U1" not in get_allowed_users()

    @patch("app.models.datastore_client.get_datastore_client")
    def test_update_user(self, mock_client):
        from tests.conftest import FakeDatastoreClient, FakeEntity
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        
        from app.models.datastore_client import update_user, add_user, datastore
        with patch("app.models.datastore_client.datastore") as mds:
            mds.Entity = lambda key: FakeEntity(key)
            add_user("U1", "Alice")
        
        result = update_user("U1", {"nickname": "Ally"})
        assert result is True
        
        entity = ds.get(ds.key("allowed_users", "U1"))
        assert entity["nickname"] == "Ally"

    @patch("app.models.datastore_client.get_datastore_client")
    def test_update_user_nonexistent(self, mock_client):
        from tests.conftest import FakeDatastoreClient
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        
        from app.models.datastore_client import update_user
        result = update_user("U_NOPE", {"nickname": "Ghost"})
        assert result is False


class TestPendingUsers:
    @patch("app.models.datastore_client.get_datastore_client")
    @patch("app.models.datastore_client.datastore")
    def test_full_lifecycle(self, mock_ds_mod, mock_client):
        from tests.conftest import FakeDatastoreClient, FakeEntity
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        mock_ds_mod.Entity = lambda key: FakeEntity(key)

        from app.models.datastore_client import (
            add_pending_user,
            get_pending_users,
            remove_pending_user,
        )

        add_pending_user("U2", "Bob")
        pending = get_pending_users()
        assert "U2" in pending

        remove_pending_user("U2")
        assert "U2" not in get_pending_users()

    @patch("app.models.datastore_client.get_datastore_client")
    @patch("app.models.datastore_client.datastore")
    def test_duplicate_pending_ignored(self, mock_ds_mod, mock_client):
        from tests.conftest import FakeDatastoreClient, FakeEntity
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        mock_ds_mod.Entity = lambda key: FakeEntity(key)

        from app.models.datastore_client import add_pending_user
        add_pending_user("U3")
        assert add_pending_user("U3") is True  # idempotent


class TestAuditLog:
    @patch("app.models.datastore_client.get_datastore_client")
    @patch("app.models.datastore_client.datastore")
    def test_log_admin_action(self, mock_ds_mod, mock_client):
        from tests.conftest import FakeDatastoreClient, FakeEntity
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        mock_ds_mod.Entity = lambda key: FakeEntity(key)

        from app.models.datastore_client import log_admin_action
        result = log_admin_action(
            admin_username="admin",
            action="APPROVE_USER",
            target_user_id="U1",
            metadata={"name": "Alice"},
        )
        assert result is True
        # Verify it was persisted
        assert "AuditLog" in ds._store

class TestDatastoreExceptions:
    @patch("app.models.datastore_client.get_datastore_client")
    def test_add_user_exception(self, mock_client):
        mock_client.return_value.put.side_effect = Exception("DB error")
        from app.models.datastore_client import add_user
        assert add_user("U1", "Alice") is False

    @patch("app.models.datastore_client.get_datastore_client")
    def test_remove_user_exception(self, mock_client):
        mock_client.return_value.delete.side_effect = Exception("DB error")
        from app.models.datastore_client import remove_user
        assert remove_user("U1") is False

    @patch("app.models.datastore_client.get_datastore_client")
    def test_add_pending_user_exception(self, mock_client):
        mock_client.return_value.get.return_value = None
        mock_client.return_value.put.side_effect = Exception("DB error")
        from app.models.datastore_client import add_pending_user
        assert add_pending_user("U1", "Alice") is False

    @patch("app.models.datastore_client.get_datastore_client")
    def test_remove_pending_user_exception(self, mock_client):
        mock_client.return_value.delete.side_effect = Exception("DB error")
        from app.models.datastore_client import remove_pending_user
        assert remove_pending_user("U1") is False

    @patch("app.models.datastore_client.get_datastore_client")
    def test_log_admin_action_exception(self, mock_client):
        mock_client.return_value.put.side_effect = Exception("DB error")
        from app.models.datastore_client import log_admin_action
        assert log_admin_action("admin", "ACTION", "U1") is False

    @patch("app.models.datastore_client.get_datastore_client")
    def test_get_allowed_users_exception(self, mock_client):
        mock_client.return_value.query.side_effect = Exception("DB error")
        from app.models.datastore_client import get_allowed_users
        assert get_allowed_users() == {}
        
    @patch("app.models.datastore_client.get_datastore_client")
    def test_update_user_exception(self, mock_client):
        mock_client.return_value.get.side_effect = Exception("DB error")
        from app.models.datastore_client import update_user
        assert update_user("U1", {}) is False

    @patch("app.models.datastore_client.get_datastore_client")
    def test_get_pending_users_exception(self, mock_client):
        mock_client.return_value.query.side_effect = Exception("DB error")
        from app.models.datastore_client import get_pending_users
        assert get_pending_users() == {}

    @patch("app.models.datastore_client.get_datastore_client", return_value=None)
    def test_remove_user_no_db(self, mock_client):
        from app.models.datastore_client import remove_user
        assert remove_user("U1") is False

    @patch("app.models.datastore_client.get_datastore_client", return_value=None)
    def test_log_admin_action_no_db(self, mock_client):
        from app.models.datastore_client import log_admin_action
        assert log_admin_action("admin", "ACTION", "U1") is False
