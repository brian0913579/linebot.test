"""
line_webhook.py

Defines the webhook handlers and supporting functions for LINE Platform integration,
including token verification, user authorization, and message handling.
"""

import base64
import hashlib
import hmac
import secrets as py_secrets
import threading
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
    TemplateMessage,
    TextMessage,
    URIAction,
)
from linebot.v3.webhooks import MessageEvent, PostbackEvent, TextMessageContent

from config.config_module import (
    CACHE_ENABLED,
    DEBUG_MODE,
    DEBUG_USER_IDS,
    LOCATION_TTL,
    MAX_DIST_KM,
    PARK_LAT,
    PARK_LNG,
    VERIFY_TTL,
    VERIFY_URL_BASE,
)
from core.models import get_allowed_users
from core.mqtt_handler import send_garage_command
from core.token_manager import (
    TOKENS,
    clean_expired_tokens,
    generate_token,
    store_action_token,
)
from utils.logger_config import get_logger

# Thread locks for in-memory storage (used only if CACHE_ENABLED is False)
verify_tokens_lock = threading.Lock()
authorized_users_lock = threading.Lock()

# In-memory rate limiter for verify_location_handler
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX = 5  # 5 requests per minute per user
GLOBAL_RATE_LIMIT_MAX = 100  # 100 requests per minute globally
rate_limit_store = {}  # {user_id: [(timestamp, count)]}
global_rate_limit_store = []  # [(timestamp, count)]
rate_limit_lock = threading.Lock()

# Configure logger
logger = get_logger(__name__)

# In-memory stores (fallback, discouraged in production)
VERIFY_TOKENS = {}
authorized_users = {}

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

    # Schedule background cleanup
    ensure_cleanup_scheduled()

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


# Startup validation
if not CACHE_ENABLED:
    logger.warning("In-memory storage is enabled. Set CACHE_ENABLED=True.")
    # In production, consider raising an error:
    # raise RuntimeError("Redis cache is required for production.")


# Background token cleanup
_cleanup_scheduled = False


def schedule_token_cleanup():
    """Schedule background token cleanup (called lazily)."""
    global _cleanup_scheduled
    if _cleanup_scheduled:
        return

    def cleanup_loop():
        if not CACHE_ENABLED:
            clean_expired_tokens()
        threading.Timer(300, cleanup_loop).start()

    cleanup_loop()
    _cleanup_scheduled = True


def ensure_cleanup_scheduled():
    """Ensure cleanup is scheduled when LINE clients are used."""
    schedule_token_cleanup()


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


# Enhanced rate limiting
def is_rate_limited(user_id):
    with rate_limit_lock:
        current_time = time.time()

        # Clean old entries
        global_rate_limit_store[:] = [
            (timestamp, count)
            for timestamp, count in global_rate_limit_store
            if current_time - timestamp < RATE_LIMIT_WINDOW
        ]

        # Global rate limiting
        total_global_requests = sum(count for _, count in global_rate_limit_store)
        if total_global_requests >= GLOBAL_RATE_LIMIT_MAX:
            return True

        # User-specific rate limiting
        if user_id not in rate_limit_store:
            rate_limit_store[user_id] = []

        rate_limit_store[user_id] = [
            (timestamp, count)
            for timestamp, count in rate_limit_store[user_id]
            if current_time - timestamp < RATE_LIMIT_WINDOW
        ]

        total_user_requests = sum(count for _, count in rate_limit_store[user_id])
        if total_user_requests >= RATE_LIMIT_MAX:
            return True

        # Log the request
        rate_limit_store[user_id].append((current_time, 1))
        global_rate_limit_store.append((current_time, 1))

        return False


def store_verify_token(token, user_id):
    expiry = time.time() + VERIFY_TTL
    if CACHE_ENABLED:
        store_action_token(f"verify:{token}", user_id, "verify", expiry=LOCATION_TTL)
    else:
        with verify_tokens_lock:
            VERIFY_TOKENS[token] = (user_id, expiry)


def get_verify_token(token):
    if CACHE_ENABLED:
        record = TOKENS.get(f"verify:{token}")
        if record and len(record) >= 3:
            return record[0], record[2]  # user_id, expiry
        return None, None
    else:
        with verify_tokens_lock:
            return VERIFY_TOKENS.get(token, (None, None))


def authorize_user(user_id):
    if CACHE_ENABLED:
        store_action_token(f"auth:{user_id}", user_id, "authorize", expiry=LOCATION_TTL)


def is_user_authorized(user_id):
    if CACHE_ENABLED:
        record = TOKENS.get(f"auth:{user_id}")
        if record and len(record) >= 3:
            expiry = record[2]
            return time.time() < expiry
        return False
    else:
        with authorized_users_lock:
            expiry = authorized_users.get(user_id)
            return expiry and time.time() < expiry


def build_open_close_template(user_id):
    open_token, close_token = generate_token(user_id)
    if CACHE_ENABLED:
        store_action_token(open_token, user_id, "open")
        store_action_token(close_token, user_id, "close")
    
    # Use Quick Reply for better button spacing and UX
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(
                action=PostbackAction(label="🟢 開門", data=open_token)
            ),
            QuickReplyItem(
                action=PostbackAction(label="🔴 關門", data=close_token)
            ),
        ]
    )
    
    return TextMessage(text="請選擇車庫門操作：", quick_reply=quick_reply)


def verify_signature(signature, body):
    logger.debug(f"Received Signature: {signature}")
    logger.debug(f"Request Body: {body}")

    from config.secret_manager import get_secret

    channel_secret = get_secret("LINE_CHANNEL_SECRET")
    if not channel_secret:
        logger.error("LINE_CHANNEL_SECRET not available")
        return False

    expected_signature = base64.b64encode(
        hmac.new(
            key=channel_secret.encode(),
            msg=body.encode(),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode()
    logger.debug(f"Expected Signature: {expected_signature}")
    return signature == expected_signature


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

    if is_rate_limited(user_id):
        return jsonify(ok=False, message="請求過於頻繁，請稍後再試"), 429

    lat, lng, acc = data["lat"], data["lng"], data.get("acc", 999)
    dist = haversine(lat, lng, PARK_LAT, PARK_LNG)
    acc_threshold = 50

    # Check if user is in debug mode (bypasses location check)
    is_debug_user = DEBUG_MODE and user_id in DEBUG_USER_IDS

    if is_debug_user:
        logger.info(
            f"Debug mode: Bypassing location verification for user "
            f"{user_id}"
        )

    if is_debug_user or (dist <= MAX_DIST_KM and acc <= acc_threshold):
        if CACHE_ENABLED:
            authorize_user(user_id)
        else:
            with authorized_users_lock:
                authorized_users[user_id] = time.time() + LOCATION_TTL
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
            reply = TextMessage(text="❌ 您尚未註冊為停車場用戶，請聯絡管理員。")
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
    if not is_user_authorized(user_id):
        return send_verification_message(user_id, event.reply_token)

    try:
        token = event.postback.data
        record = TOKENS.get(token)
        if not record or len(record) != 3:
            logger.warning(f"Invalid token in postback: {token[:8]}...")
            reply = TextMessage(text="❌ 無效操作")
            return retry_api_call(
                lambda: get_line_bot_api().reply_message(
                    ReplyMessageRequest(replyToken=event.reply_token, messages=[reply])
                )
            )

        token_user_id, action, expiry = record
        TOKENS.pop(token, None)
        logger.info(f"Found and used token for action: {action}")

        if event.source.user_id != token_user_id or time.time() > expiry:
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
