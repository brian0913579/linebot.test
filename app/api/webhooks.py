import threading

from flask import Blueprint, abort, current_app, request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from app.models.datastore_client import add_pending_user, get_allowed_users
from app.services.line_service import line_service
from app.services.mqtt_service import send_garage_command
from app.services.token_service import token_service
from utils.logger_config import get_logger

logger = get_logger(__name__)
webhooks_bp = Blueprint("webhooks", __name__)

DOOR_COMMANDS = {
    "開門": "open",
    "關門": "close",
}


@webhooks_bp.route("/webhook", methods=["POST"])
def webhook_handler():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    try:
        line_service.handler.handle(body, signature)
        logger.info("Webhook processed successfully")
        return "OK", 200
    except InvalidSignatureError:
        logger.error("Invalid signature from LINE Platform")
        abort(400, description="Invalid signature")
    except Exception as e:
        logger.error(f"Error while handling webhook: {e}")
        # Allow LINE to see the 500 internal server error so it can retry
        abort(500, description="Internal Server Error")


@line_service.handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    user_id = None
    try:
        user_id = event.source.user_id
        user_msg = event.message.text
        logger.info(f"User {user_id} sent: {user_msg}")

        camera_commands = ("監控", "監控畫面")
        if user_msg not in DOOR_COMMANDS and user_msg not in camera_commands:
            return

        ALLOWED_USERS = get_allowed_users()
        if user_id not in ALLOWED_USERS:
            add_pending_user(user_id)
            line_service.reply_text(
                event.reply_token,
                "🔒 您尚未開通權限。\n\n已自動將您的申請送出給管理員，請耐心等候審核。",
            )
            return

        # Camera access
        if user_msg in camera_commands:
            return line_service.send_camera_link(user_id, event.reply_token)

        # Door command
        action = DOOR_COMMANDS[user_msg]
        action_label = "開啟" if action == "open" else "關閉"

        if not token_service.is_user_authorized(user_id):
            return line_service.send_verification_message(user_id, event.reply_token, action)

        reply_token = event.reply_token

        # Execute MQTT command synchronously.
        # This will block for ~0.5s to ~3s depending on EMQX broker latency.
        # This easily fits well within LINE's webhook timeout (1-3s).
        # We drop the background threading.Thread because GAE limits
        # background execution outside of active requests.
        success, error = send_garage_command(action)
        if success:
            line_service.reply_text(
                reply_token, f"✅ 車庫門已{action_label}，請小心進出。"
            )
        else:
            logger.error(f"MQTT command failed: {error}")
            line_service.reply_text(
                reply_token, "⚠️ 無法連接車庫控制器，請稍後再試。"
            )

    except Exception as e:
        if user_id:
            line_service.handle_system_error(
                user_id, event.reply_token, e, "text message processing"
            )

