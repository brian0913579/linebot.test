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

        # Execute the garage command directly — no push_message needed.
        # The result is shown on this web page; the user is already watching it.
        result_label = "開啟" if action == "open" else "關閉"
        success, error = send_garage_command(action)
        if success:
            return jsonify(ok=True, message=f"✅ 車庫門已{result_label}，請回到 LINE。")
        else:
            logger.error(f"MQTT command failed after location verify: {error}")
            return jsonify(
                ok=False, message="⚠️ 位置驗證通過，但無法連接車庫控制器，請稍後再試。"
            ), 500
    else:
        return jsonify(ok=False, message="不在車場範圍內"), 200
