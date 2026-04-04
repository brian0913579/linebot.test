"""
Tests for storage_service (app/services/storage_service.py).
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
sys.modules['google.cloud.storage'] = MagicMock()
import app.services.storage_service

@pytest.fixture(autouse=True)
def reset_storage_client():
    app.services.storage_service._storage_client = None
    yield
    app.services.storage_service._storage_client = None

@patch("app.services.storage_service.storage")
def test_upload_contract_photo_success(mock_storage, app):
    mock_client = MagicMock()
    mock_storage.Client.return_value = mock_client
    mock_bucket = MagicMock()
    mock_bucket.exists.return_value = False
    mock_client.bucket.return_value = mock_bucket
    
    mock_blob = MagicMock()
    mock_blob.public_url = "http://fake-url/photo.jpg"
    mock_bucket.blob.return_value = mock_blob

    from app.services.storage_service import upload_contract_photo
    from werkzeug.datastructures import FileStorage
    
    import io
    file_storage = FileStorage(stream=io.BytesIO(b"abc"), filename="test.jpg", content_type="image/jpeg", name="contract_photo")
    
    with app.app_context():
        # Override config
        from app.config import Config
        Config.GCS_CONTRACT_BUCKET_NAME = "test-bucket"
        
        url = upload_contract_photo("U1", file_storage)
        assert url == "http://fake-url/photo.jpg"
        mock_bucket.create.assert_called_once()
        mock_blob.upload_from_file.assert_called_once()
        mock_blob.make_public.assert_called_once()


@patch("app.services.storage_service.storage")
def test_upload_contract_photo_make_public_fail(mock_storage, app):
    mock_client = MagicMock()
    mock_storage.Client.return_value = mock_client
    mock_bucket = MagicMock()
    mock_bucket.exists.return_value = True
    mock_client.bucket.return_value = mock_bucket
    
    mock_blob = MagicMock()
    mock_blob.make_public.side_effect = Exception("Not allowed")
    mock_blob.media_link = "http://fake-url/media.jpg"
    mock_bucket.blob.return_value = mock_blob

    from app.services.storage_service import upload_contract_photo
    from werkzeug.datastructures import FileStorage
    
    import io
    file_storage = FileStorage(stream=io.BytesIO(b"abc"), filename="test.jpg", content_type="image/jpeg", name="contract_photo")
    
    with app.app_context():
        url = upload_contract_photo("U1", file_storage)
        assert url == "http://fake-url/media.jpg"


@patch("app.services.storage_service.storage")
def test_upload_contract_photo_no_bucket_name(mock_storage, app):
    from app.services.storage_service import upload_contract_photo
    from werkzeug.datastructures import FileStorage
    
    with patch("app.services.storage_service.Config") as mock_config:
        mock_config.GCS_CONTRACT_BUCKET_NAME = None
        url = upload_contract_photo("U1", MagicMock(spec=FileStorage))
        assert url is None

@patch("app.services.storage_service.storage")
def test_upload_contract_photo_client_fail(mock_storage, app):
    mock_storage.Client.side_effect = Exception("Init error")
    from app.services.storage_service import upload_contract_photo
    url = upload_contract_photo("U1", MagicMock())
    assert url is None

@patch("app.services.storage_service.storage")
def test_upload_contract_photo_upload_fail(mock_storage, app):
    mock_client = MagicMock()
    mock_storage.Client.return_value = mock_client
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.side_effect = Exception("Blob error")

    from app.services.storage_service import upload_contract_photo
    from werkzeug.datastructures import FileStorage
    
    with app.app_context():
        url = upload_contract_photo("U1", MagicMock(spec=FileStorage))
        assert url is None
