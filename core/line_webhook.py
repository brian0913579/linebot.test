"""
line_webhook.py

Defines the webhook handlers and supporting functions for LINE Platform integration,
including token verification, user authorization, and message handling.
"""

import secrets as py_secrets
import time
from math import atan2, cos, radians, sin, sqrt

from flask import abort, jsonify, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    ButtonsTemplate,
    Configuration,
    MessagingApi,
    PostbackAction,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TemplateMessage,
    TextMessage,
    URIAction,
)
from linebot.v3.webhooks import MessageEvent, PostbackEvent, TextMessageContent

from config.config_module import (
    DEBUG_MODE,
    DEBUG_USER_IDS,
    MAX_ACCURACY_METERS,
    MAX_DIST_KM,
    PARK_LAT,
    PARK_LNG,
    VERIFY_URL_BASE,
)
from core.models import get_allowed_users
from core.mqtt_handler import send_garage_command
from middleware.cache_manager import (
    authorize_user,
    generate_token,
    get_action_token,
    get_verify_token,
    invalidate_user_tokens,
    is_user_authorized,
    store_action_token,
    store_verify_token,
)
from utils.logger_config import get_logger

# Configure logger
logger = get_logger(__name__)

# Global variables for LINE API clients (will be initialized lazily)
line_bot_api = None
handler = None
_api_clients_initialized = False


def _initialize_line_clients():
    """Initialize LINE API clients lazily when first needed."""
    global line_bot_api, handler, _api_clients_initialized

    if _api_clients_initialized:
        return

    from config.secret_manager import get_secret

    # Get secrets directly from secret manager
    access_token = get_secret("LINE_CHANNEL_ACCESS_TOKEN")
    channel_secret = get_secret("LINE_CHANNEL_SECRET")

    if not access_token or not channel_secret:
        raise RuntimeError("LINE credentials not available in secret manager")

    # Initialize LINE API clients
    configuration = Configuration(access_token=access_token)
    api_client = ApiClient(configuration)
    line_bot_api = MessagingApi(api_client)
    handler = WebhookHandler(channel_secret)

    # Register event handlers
    _register_handlers()

    _api_clients_initialized = True


def _register_handlers():
    """Register LINE webhook event handlers."""
    handler.add(MessageEvent, message=TextMessageContent)(handle_text)
    handler.add(PostbackEvent)(handle_postback)


def get_line_bot_api():
    """Get the LINE Bot API client, initializing if needed."""
    _initialize_line_clients()
    return line_bot_api


def get_webhook_handler():
    """Get the webhook handler, initializing if needed."""
    _initialize_line_clients()
    return handler


# Haversine formula
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


def build_open_close_template(user_id):
    open_token, close_token = generate_token(user_id)
    store_action_token(open_token, user_id, "open")
    store_action_token(close_token, user_id, "close")

    # Use Quick Reply for better button spacing and UX
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=PostbackAction(label="🟢 開門", data=open_token)),
            QuickReplyItem(action=PostbackAction(label="🔴 關門", data=close_token)),
        ]
    )

    return TextMessage(text="請選擇車庫門操作：", quick_reply=quick_reply)


def send_verification_message(user_id, reply_token):
    verify_token = py_secrets.token_urlsafe(24)
    store_verify_token(verify_token, user_id)
    verify_url = f"{VERIFY_URL_BASE}?token={verify_token}"
    reply = TemplateMessage(
        altText="請先驗證定位",
        template=ButtonsTemplate(
            text="請先在車場範圍內進行位置驗證",
            actions=[URIAction(label="📍 驗證我的位置", uri=verify_url)],
        ),
    )
    return retry_api_call(
        lambda: get_line_bot_api().reply_message(
            ReplyMessageRequest(replyToken=reply_token, messages=[reply])
        )
    )


def handle_system_error(user_id, reply_token, error, context):
    logger.error(f"Error in {context}: {error}")
    try:
        reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
        retry_api_call(
            lambda: get_line_bot_api().reply_message(
                ReplyMessageRequest(replyToken=reply_token, messages=[reply])
            )
        )
    except Exception as reply_error:
        logger.error(f"Unable to send error reply: {reply_error}")
        try:
            retry_api_call(
                lambda: get_line_bot_api().push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text="❌ 系統錯誤，請稍後再試。")],
                    )
                )
            )
            logger.info(f"Sent push message instead of reply to user {user_id}")
        except Exception as push_error:
            logger.error(f"Failed to send push message: {push_error}")


# Simple retry mechanism
def retry_api_call(func, max_attempts=3, delay=1):
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            logger.warning(
                f"API call failed (attempt {attempt + 1}/{max_attempts}): {e}"
            )
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay)
    return None


def webhook_handler():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    try:
        get_webhook_handler().handle(body, signature)
        logger.info("Webhook processed successfully")
    except InvalidSignatureError:
        logger.error("Invalid signature from LINE Platform")
        abort(400, description="Invalid signature")
    except Exception as e:
        logger.error(f"Error while handling webhook: {e}")
        logger.error(f"Request body: {body[:200]}...")
    return "OK", 200


def verify_location_handler():
    token = request.args.get("token")
    data = request.get_json(silent=True)
    logger.info(
        f"Received location verification request for token: "
        f"{token[:8] if token else 'None'}..."
    )

    user_id, expiry = get_verify_token(token)
    if not token or not user_id:
        logger.warning(
            f"Invalid token: token_provided={token is not None}, "
            f"user_id_found={user_id is not None}"
        )
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
    dist = haversine(lat, lng, PARK_LAT, PARK_LNG)
    acc_threshold = MAX_ACCURACY_METERS

    # Check if user is in debug mode (bypasses location check)
    is_debug_user = DEBUG_MODE and user_id in DEBUG_USER_IDS

    if is_debug_user:
        logger.info(
            f"Debug mode: Bypassing location verification for user " f"{user_id}"
        )

    if is_debug_user or (dist <= MAX_DIST_KM and acc <= acc_threshold):
        authorize_user(user_id)
        template = build_open_close_template(user_id)
        retry_api_call(
            lambda: get_line_bot_api().push_message(
                PushMessageRequest(to=user_id, messages=[template])
            )
        )
        return jsonify(ok=True)
    else:
        return jsonify(ok=False, message="不在車場範圍內"), 200


def handle_text(event):
    user_id = None
    try:
        user_id = event.source.user_id
        user_msg = event.message.text
        logger.info(f"User {user_id} sent a text message: {user_msg}")

        if user_msg != "開關門":
            return

        ALLOWED_USERS = get_allowed_users()
        if user_id not in ALLOWED_USERS:
            # Auto-register as pending user
            from core.models import add_pending_user

            add_pending_user(user_id)

            reply = TextMessage(
                text="🔒 您尚未開通權限。\n\n已自動將您的申請送出給管理員，請耐心等候審核。"
            )
            return retry_api_call(
                lambda: get_line_bot_api().reply_message(
                    ReplyMessageRequest(replyToken=event.reply_token, messages=[reply])
                )
            )

        if not is_user_authorized(user_id):
            return send_verification_message(user_id, event.reply_token)

        template = build_open_close_template(user_id)
        return retry_api_call(
            lambda: get_line_bot_api().reply_message(
                ReplyMessageRequest(replyToken=event.reply_token, messages=[template])
            )
        )

    except Exception as e:
        if user_id:
            handle_system_error(
                user_id, event.reply_token, e, "text message processing"
            )


def handle_postback(event):
    user_id = event.source.user_id

    # Show loading animation immediately for better UX
    try:
        retry_api_call(
            lambda: get_line_bot_api().show_loading_animation(
                ShowLoadingAnimationRequest(chatId=user_id, loadingSeconds=5)
            )
        )
        logger.info(f"Loading animation started for user {user_id}")
    except Exception as loading_error:
        # Non-critical: continue even if loading animation fails
        logger.warning(f"Failed to show loading animation: {loading_error}")

    if not is_user_authorized(user_id):
        return send_verification_message(user_id, event.reply_token)

    try:
        token = event.postback.data
        user_id, action, expiry = get_action_token(token)
        if not user_id or not action:
            logger.warning(f"Invalid token in postback: {token[:8]}...")
            reply = TextMessage(text="❌ 無效操作")
            return retry_api_call(
                lambda: get_line_bot_api().reply_message(
                    ReplyMessageRequest(replyToken=event.reply_token, messages=[reply])
                )
            )

        # Invalidate all OTHER open/close tokens for this user immediately
        # to prevent double-click malfunction
        invalidate_user_tokens(user_id)

        logger.info(f"Found and used token for action: {action}")

        if event.source.user_id != user_id or time.time() > expiry:
            reply = TextMessage(text="❌ 此操作已失效，請重新傳送位置")
            return retry_api_call(
                lambda: get_line_bot_api().reply_message(
                    ReplyMessageRequest(replyToken=event.reply_token, messages=[reply])
                )
            )

        # Retry MQTT command
        for attempt in range(3):
            success, error = send_garage_command(action)
            if success:
                break
            logger.warning(f"MQTT command failed (attempt {attempt + 1}/3): {error}")
            if attempt < 2:
                time.sleep(1)
            else:
                logger.error(f"Failed to send garage command: {error}")
                reply = TextMessage(text="⚠️ 無法連接車庫控制器，請稍後再試。")
                return retry_api_call(
                    lambda: get_line_bot_api().reply_message(
                        ReplyMessageRequest(
                            replyToken=event.reply_token, messages=[reply]
                        )
                    )
                )

        if action == "open":
            reply = TextMessage(text="✅ 門已開啟，請小心進出。")
        else:
            reply = TextMessage(text="✅ 門已關閉，感謝您的使用。")
        retry_api_call(
            lambda: get_line_bot_api().reply_message(
                ReplyMessageRequest(replyToken=event.reply_token, messages=[reply])
            )
        )

    except Exception as e:
        handle_system_error(user_id, event.reply_token, e, "postback handling")
