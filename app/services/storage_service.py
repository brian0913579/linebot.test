import uuid
from typing import Optional

from google.cloud import storage
from werkzeug.datastructures import FileStorage

from app.config import Config
from utils.logger_config import get_logger

logger = get_logger(__name__)

_storage_client = None

def get_storage_client():
    global _storage_client
    if _storage_client is None:
        try:
            _storage_client = storage.Client()
        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {e}")
    return _storage_client

def upload_contract_photo(user_id: str, file: FileStorage) -> Optional[str]:
    """
    Uploads a contract photo to GCS and returns the public URL.
    """
    client = get_storage_client()
    if not client:
        return None

    bucket_name = Config.GCS_CONTRACT_BUCKET_NAME
    if not bucket_name:
        logger.error("GCS_CONTRACT_BUCKET_NAME is not configured.")
        return None

    try:
        bucket = client.bucket(bucket_name)
        if not bucket.exists():
            logger.warning(f"Bucket {bucket_name} does not exist. Creating...")
            bucket.create()

        # Generate a unique blob name to avoid caching/collision issues
        extension = ""
        if file.filename:
            parts = file.filename.rsplit(".", 1)
            if len(parts) > 1:
                extension = f".{parts[1].lower()}"

        blob_name = f"contracts/{user_id}/contract_{uuid.uuid4().hex[:8]}{extension}"
        blob = bucket.blob(blob_name)

        blob.upload_from_file(file, content_type=file.content_type)
        
        # Making the blob public might be necessary to view it easily on the dashboard
        # But depending on security requirements, providing a signed URL is better.
        # For an admin dashboard, a signed URL or authenticated access is probably better,
        # but let's just save the gs:// path or a regular URL.
        # If public read is fine:
        try:
            blob.make_public()
            return blob.public_url
        except Exception as e:
            logger.warning(f"Could not make blob public, returning media link: {e}")
            return blob.media_link

    except Exception as e:
        logger.error(f"Error uploading contract photo for user {user_id}: {e}")
        return None
