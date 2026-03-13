import time
from math import atan2, cos, radians, sin, sqrt

from flask import Blueprint, current_app, jsonify, request

from app.services.line_service import line_service
from app.services.token_service import token_service
from utils.logger_config import get_logger

logger = get_logger(__name__)
location_bp = Blueprint("location", __name__)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


@location_bp.route("/verify-location", methods=["GET", "POST"])
def verify_location_handler():
    token = request.args.get("token")
    data = request.get_json(silent=True)
    token_preview = token[:8] if token else "None"
    logger.info(f"Received location verification request for token: {token_preview}...")

    user_id, expiry = token_service.get_verify_token(token)
    if not token or not user_id:
        return jsonify(ok=False, message="無效或已過期的驗證"), 400

    if expiry and time.time() > expiry:
        return jsonify(ok=False, message="驗證已過期，請重新驗證"), 400

    if (
        not data
        or not isinstance(data.get("lat"), (int, float))
        or not isinstance(data.get("lng"), (int, float))
    ):
        return jsonify(ok=False, message="無效的經緯度格式"), 400

    lat, lng, acc = data["lat"], data["lng"], data.get("acc", 999)
    dist = haversine(
        lat, lng, current_app.config["PARK_LAT"], current_app.config["PARK_LNG"]
    )

    is_debug_user = (
        current_app.config["DEBUG_MODE"]
        and user_id in current_app.config["DEBUG_USER_IDS"]
    )
    if is_debug_user:
        logger.info(f"Debug mode: Bypassing location verification for user {user_id}")

    if is_debug_user or (
        dist <= current_app.config["MAX_DIST_KM"]
        and acc <= current_app.config["MAX_ACCURACY_METERS"]
    ):
        token_service.authorize_user(user_id)
        template = line_service.build_open_close_template(user_id)

        # We need to import PushMessageRequest inside or make it available
        from linebot.v3.messaging import PushMessageRequest

        line_service._retry_api_call(
            lambda: line_service.line_bot_api.push_message(
                PushMessageRequest(to=user_id, messages=[template])
            )
        )
        return jsonify(ok=True)
    else:
        return jsonify(ok=False, message="不在車場範圍內"), 200
