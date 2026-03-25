import time
from math import atan2, cos, radians, sin, sqrt

from flask import Blueprint, current_app, jsonify, request

from app.services.mqtt_service import send_garage_command
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

    user_id, expiry, action = token_service.get_verify_token(token)
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

        if not action:
            logger.info(f"Location verified for user {user_id} but no action was stored in token; skipping MQTT")
            return jsonify(ok=True)

        success, error = send_garage_command(action)
        if not success:
            logger.error(f"MQTT command failed after location verification: {error}")
            return jsonify(ok=False, message="⚠️ 無法連接車庫控制器，請稍後再試。"), 200

        result_message = (
            "✅ 門已開啟，請小心進出。" if action == "open" else "✅ 門已關閉，感謝您的使用。"
        )
        return jsonify(ok=True, message=result_message)
    else:
        return jsonify(ok=False, message="不在車場範圍內"), 200
