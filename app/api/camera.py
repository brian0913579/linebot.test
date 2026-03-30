import secrets as py_secrets
import urllib.parse

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

    # Dynamically resolve the current live stream from the channel ID
    channel_id = current_app.config.get("YOUTUBE_CHANNEL_ID", "")
    api_key = current_app.config.get("YOUTUBE_API_KEY", "")

    if channel_id and api_key:
        from app.services.youtube_service import get_live_embed_url

        youtube_url = get_live_embed_url(channel_id, api_key)
        if not youtube_url:
            logger.warning("Channel %s has no active live stream", channel_id)
            return render_template("camera_error.html", message="直播尚未開始，請稍後再試"), 503
    else:
        # Fallback: use the static YOUTUBE_LIVE_URL if channel config is missing
        youtube_url = current_app.config.get("YOUTUBE_LIVE_URL", "")
        if not youtube_url:
            logger.error("No YouTube source configured (channel ID or static URL)")
            return render_template("camera_error.html", message="監控系統暫時無法使用"), 503

    # Add URL parameters to restrict UI and enforce CCTV-like autoplay
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
