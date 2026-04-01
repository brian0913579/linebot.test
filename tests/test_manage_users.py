"""
Tests for the CLI script utils/manage_users.py.
"""

import sys
from unittest.mock import patch, MagicMock

import pytest


class TestManageUsersCLI:

    @patch("utils.manage_users.get_client")
    def test_list_users(self, mock_get_client, capsys):
        client = MagicMock()
        mock_get_client.return_value = client

        entity1 = MagicMock()
        entity1.get.side_effect = lambda k, default=None: "Alice" if k == "user_name" else "U1"
        entity1.key.name = "U1"
        
        entity2 = MagicMock()
        entity2.get.side_effect = lambda k, default=None: "Bob" if k == "user_name" else None
        entity2.key.name = "U2"
        
        query_mock = MagicMock()
        query_mock.fetch.return_value = [entity1, entity2]
        client.query.return_value = query_mock

        from utils.manage_users import list_users
        list_users()

        out, _ = capsys.readouterr()
        assert "Found 2 users" in out

    @patch("utils.manage_users.get_client")
    def test_add_user(self, mock_get_client, capsys):
        client = MagicMock()
        mock_get_client.return_value = client

        from utils.manage_users import add_user
        add_user("U3", "Charlie")

        client.put.assert_called_once()
        out, _ = capsys.readouterr()
        assert "Added user: Charlie" in out

    @patch("utils.manage_users.get_client")
    def test_remove_user(self, mock_get_client, capsys):
        client = MagicMock()
        mock_get_client.return_value = client

        from utils.manage_users import remove_user
        remove_user("U4")

        client.delete.assert_called_once()
        out, _ = capsys.readouterr()
        assert "Removed user: U4" in out

    @patch("sys.argv", ["manage_users.py", "list"])
    @patch("utils.manage_users.list_users")
    def test_main_list(self, mock_lu, capsys):
        from utils.manage_users import main
        main()
        mock_lu.assert_called_once()

    @patch("sys.argv", ["manage_users.py", "add", "U5", "Eve"])
    @patch("utils.manage_users.add_user")
    def test_main_add(self, mock_add, capsys):
        from utils.manage_users import main
        main()
        mock_add.assert_called_once_with("U5", "Eve")

    @patch("sys.argv", ["manage_users.py", "remove", "U6"])
    @patch("utils.manage_users.remove_user")
    def test_main_remove(self, mock_rm, capsys):
        from utils.manage_users import main
        main()
        mock_rm.assert_called_once_with("U6")

    @patch("sys.argv", ["manage_users.py"])
    def test_main_help(self, capsys):
        from utils.manage_users import main
        with pytest.raises(SystemExit):
            main()

    @patch("sys.argv", ["manage_users.py", "list"])
    @patch("utils.manage_users.list_users")
    def test_main_exception(self, mock_lu, capsys):
        mock_lu.side_effect = Exception("DB Error")
        from utils.manage_users import main
        main()
        out, _ = capsys.readouterr()
        assert "Error: DB Error" in out
        assert "Tip:" in out

    @patch("utils.manage_users.datastore.Client")
    def test_module_execution(self, mock_client):
        from utils.manage_users import get_client
        get_client()
        mock_client.assert_called_once()
        
        # Test __main__
        import runpy
        # Avoid running actual list output during test by patching list_users at the builtins/globals level, 
        # but since runpy is clean, we just patch sys.argv to trigger 'list' and let the mock client handle it silently.
        with patch("sys.argv", ["manage_users.py", "list"]), patch("utils.manage_users.list_users"):
            runpy.run_module("utils.manage_users", run_name="__main__")
