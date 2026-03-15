import secrets as py_secrets

from flask import Blueprint, current_app, render_template, request

from app.models.datastore_client import get_allowed_users
from app.services.token_service import token_service
from utils.logger_config import get_logger

logger = get_logger(__name__)
camera_bp = Blueprint("camera", __name__)


def generate_camera_token(user_id: str) -> str:
    """Generate and persist a signed camera token for the given user."""
    token = py_secrets.token_urlsafe(24)
    token_service.store_camera_token(token, user_id)
    return token


@camera_bp.route("/camera", methods=["GET"])
def camera_view():
    token = request.args.get("token")
    if not token:
        logger.warning("Camera access attempt without token")
        return render_template("camera_error.html", message="缺少訪問憑證"), 403

    user_id, expiry = token_service.get_camera_token(token)
    if not user_id:
        logger.warning(f"Invalid or expired camera token: {token[:8]}...")
        return render_template("camera_error.html", message="無效或已過期的連結"), 403

    # Double-check user is still on the whitelist
    allowed_users = get_allowed_users()
    if user_id not in allowed_users:
        logger.warning(f"Revoked user {user_id} attempted camera access")
        return render_template("camera_error.html", message="您的訪問權限已被撤銷"), 403

    youtube_url = current_app.config.get("YOUTUBE_LIVE_URL", "")
    if not youtube_url:
        logger.error("YOUTUBE_LIVE_URL not configured")
        return render_template("camera_error.html", message="監控系統暫時無法使用"), 503

    # Add URL parameters to restrict UI and enforce CCTV-like autoplay
    import urllib.parse

    parsed = urllib.parse.urlparse(youtube_url)
    query = dict(urllib.parse.parse_qsl(parsed.query))

    # Force strict YouTube embed settings
    query.update(
        {
            "autoplay": "1",
            "mute": "1",  # Required for autoplay in modern browsers
            "controls": "0",  # Hide player controls
            "modestbranding": "1",
            "rel": "0",  # Don't show random related videos
            "disablekb": "1",
            "fs": "0",
            "playsinline": "1",
        }
    )

    # Strip tracking parameters
    if "si" in query:
        del query["si"]

    youtube_url = urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query))
    )

    logger.info(f"Camera access granted for user {user_id}")
    return render_template("camera.html", youtube_url=youtube_url)
