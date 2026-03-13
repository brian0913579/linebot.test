import time

from flask import Blueprint, abort, request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import ShowLoadingAnimationRequest
from linebot.v3.webhooks import MessageEvent, PostbackEvent, TextMessageContent

from app.models.datastore_client import add_pending_user, get_allowed_users
from app.services.line_service import line_service
from app.services.mqtt_service import send_garage_command
from app.services.token_service import token_service
from utils.logger_config import get_logger

logger = get_logger(__name__)
webhooks_bp = Blueprint("webhooks", __name__)


@webhooks_bp.route("/webhook", methods=["POST"])
def webhook_handler():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    try:
        line_service.handler.handle(body, signature)
        logger.info("Webhook processed successfully")
    except InvalidSignatureError:
        logger.error("Invalid signature from LINE Platform")
        abort(400, description="Invalid signature")
    except Exception as e:
        logger.error(f"Error while handling webhook: {e}")
    return "OK", 200


@line_service.handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    user_id = None
    try:
        user_id = event.source.user_id
        user_msg = event.message.text
        logger.info(f"User {user_id} sent a text message: {user_msg}")

        if user_msg not in ("開關門", "監控", "監控畫面"):
            return

        ALLOWED_USERS = get_allowed_users()
        if user_id not in ALLOWED_USERS:
            add_pending_user(user_id)
            line_service.reply_text(
                event.reply_token,
                "🔒 您尚未開通權限。\n\n已自動將您的申請送出給管理員，請耐心等候審核。",
            )
            return

        # --- Camera access branch ---
        if user_msg in ("監控", "監控畫面"):
            return line_service.send_camera_link(user_id, event.reply_token)

        if not token_service.is_user_authorized(user_id):
            return line_service.send_verification_message(user_id, event.reply_token)

        return line_service.send_open_close_message(user_id, event.reply_token)

    except Exception as e:
        if user_id:
            line_service.handle_system_error(
                user_id, event.reply_token, e, "text message processing"
            )


@line_service.handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id

    try:
        line_service._retry_api_call(
            lambda: line_service.line_bot_api.show_loading_animation(
                ShowLoadingAnimationRequest(chatId=user_id, loadingSeconds=5)
            )
        )
    except Exception as loading_error:
        logger.warning(f"Failed to show loading animation: {loading_error}")

    if not token_service.is_user_authorized(user_id):
        return line_service.send_verification_message(user_id, event.reply_token)

    try:
        token = event.postback.data
        t_user_id, action, expiry = token_service.get_action_token(token)
        if not t_user_id or not action:
            line_service.reply_text(event.reply_token, "❌ 無效操作")
            return

        token_service.invalidate_user_tokens(t_user_id)

        if event.source.user_id != t_user_id or time.time() > expiry:
            line_service.reply_text(
                event.reply_token, "❌ 此操作已失效，請重新傳送位置"
            )
            return

        # Execute MQTT action
        for attempt in range(3):
            success, error = send_garage_command(action)
            if success:
                break
            logger.warning(f"MQTT command failed (attempt {attempt + 1}/3): {error}")
            if attempt < 2:
                time.sleep(1)
            else:
                line_service.reply_text(
                    event.reply_token, "⚠️ 無法連接車庫控制器，請稍後再試。"
                )
                return

        if action == "open":
            line_service.reply_text(event.reply_token, "✅ 門已開啟，請小心進出。")
        else:
            line_service.reply_text(event.reply_token, "✅ 門已關閉，感謝您的使用。")

    except Exception as e:
        line_service.handle_system_error(
            user_id, event.reply_token, e, "postback handling"
        )
