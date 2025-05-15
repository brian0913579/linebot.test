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
    ReplyMessageRequest,
    TemplateMessage,
    TextMessage,
    URIAction,
)
from linebot.v3.webhooks import MessageEvent, PostbackEvent, TextMessageContent

from config.config_module import (
    ACC_THRESHOLD,
    CACHE_ENABLED,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CHANNEL_SECRET,
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

# Thread locks for in-memory storage
verify_tokens_lock = threading.Lock()
authorized_users_lock = threading.Lock()

# In-memory rate limiter for verify_location_handler
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX = 5  # 5 requests per minute per user
rate_limit_store = {}  # {user_id: [(timestamp, count)]}
rate_limit_lock = threading.Lock()

# Configure logger
logger = get_logger(__name__)

# In-memory store of one-time verification tokens: token -> (user_id, expiry_timestamp)
VERIFY_TOKENS = {}

# In-memory store of authorized users: user_id -> expiry_timestamp
authorized_users = {}

# Set up LINE API clients
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


# Background token cleanup
def schedule_token_cleanup():
    if not CACHE_ENABLED:
        clean_expired_tokens()
    threading.Timer(300, schedule_token_cleanup).start()  # Run every 5 minutes


# Start cleanup thread
schedule_token_cleanup()


# Haversine formula: returns distance in kilometers between two lat/lon points
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


# Rate limiting for verification requests
def is_rate_limited(user_id):
    with rate_limit_lock:
        now = time.time()
        # Clean old entries
        rate_limit_store[user_id] = [
            (ts, count)
            for ts, count in rate_limit_store.get(user_id, [])
            if now - ts < RATE_LIMIT_WINDOW
        ]
        # Count requests in window
        total = sum(count for _, count in rate_limit_store.get(user_id, []))
        if total >= RATE_LIMIT_MAX:
            return True
        # Add new request
        rate_limit_store[user_id] = rate_limit_store.get(user_id, []) + [(now, 1)]
        return False


def store_verify_token(token, user_id):
    logger.info(f"Storing verification token: {token[:8]}...")
    with verify_tokens_lock:
        VERIFY_TOKENS[token] = (user_id, time.time() + VERIFY_TTL)
    return True


def get_verify_token(token):
    logger.info(f"Looking up token: {token[:8] if token else 'None'}...")
    with verify_tokens_lock:
        record = VERIFY_TOKENS.pop(token, None)
    if not record:
        logger.info("Token not found")
        return None, None
    user_id, expiry = record
    logger.info(f"Found token for user_id: {user_id}")
    return user_id, expiry


def authorize_user(user_id):
    logger.info(f"Authorizing user {user_id} for {LOCATION_TTL} seconds")
    with authorized_users_lock:
        authorized_users[user_id] = time.time() + LOCATION_TTL
    return True


def is_user_authorized(user_id):
    with authorized_users_lock:
        expiry = authorized_users.get(user_id)
        if expiry and expiry < time.time():
            authorized_users.pop(user_id, None)
        return expiry and expiry >= time.time()


def build_open_close_template(user_id):
    open_token, close_token = generate_token(user_id)
    if CACHE_ENABLED:
        store_action_token(open_token, user_id, "open")
        store_action_token(close_token, user_id, "close")
    buttons = ButtonsTemplate(
        text="請選擇操作",
        actions=[
            PostbackAction(label="開門", data=open_token),
            PostbackAction(label="關門", data=close_token),
        ],
    )
    return TemplateMessage(alt_text="開關門選單", template=buttons)


def verify_signature(signature, body):
    logger.debug(f"Received Signature: {signature}")
    logger.debug(f"Request Body: {body}")
    expected_signature = base64.b64encode(
        hmac.new(
            key=LINE_CHANNEL_SECRET.encode(),
            msg=body.encode(),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode()
    logger.debug(f"Expected Signature: {expected_signature}")
    return signature == expected_signature


def webhook_handler():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    try:
        handler.handle(body, signature)
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

    # Rate limiting check
    if is_rate_limited(user_id):
        return jsonify(ok=False, message="請求過於頻繁，請稍後再試"), 429

    lat, lng, acc = data["lat"], data["lng"], data.get("acc", 999)
    dist = haversine(lat, lng, PARK_LAT, PARK_LNG)
    acc_threshold = ACC_THRESHOLD if "ACC_THRESHOLD" in globals() else 50

    if dist <= MAX_DIST_KM and acc <= acc_threshold:
        if CACHE_ENABLED:
            authorize_user(user_id)
        else:
            with authorized_users_lock:
                authorized_users[user_id] = time.time() + LOCATION_TTL
        template = build_open_close_template(user_id)
        line_bot_api.push_message(PushMessageRequest(to=user_id, messages=[template]))
        return jsonify(ok=True)
    else:
        return jsonify(ok=False, message="不在車場範圍內"), 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    try:
        user_id = event.source.user_id
        user_msg = event.message.text
        logger.info(f"User {user_id} sent a text message: {user_msg}")

        if user_msg != "開關門":
            return

        ALLOWED_USERS = get_allowed_users()
        if user_id not in ALLOWED_USERS:
            reply = TextMessage(text="❌ 您尚未註冊為停車場用戶，請聯絡管理員。")
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        is_authorized = is_user_authorized(user_id)
        if not is_authorized:
            verify_token = py_secrets.token_urlsafe(24)
            store_verify_token(verify_token, user_id)
            verify_url = f"{VERIFY_URL_BASE}?token={verify_token}"
            reply = TemplateMessage(
                alt_text="請先驗證定位",
                template=ButtonsTemplate(
                    text="請先在車場範圍內進行位置驗證",
                    actions=[URIAction(label="📍 驗證我的位置", uri=verify_url)],
                ),
            )
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        # Generate and store tokens consistently
        open_token, close_token = generate_token(user_id)
        if CACHE_ENABLED:
            store_action_token(open_token, user_id, "open")
            store_action_token(close_token, user_id, "close")
        template = TemplateMessage(
            alt_text="開關門選單",
            template=ButtonsTemplate(
                text="請選擇動作",
                actions=[
                    PostbackAction(label="開門", data=open_token),
                    PostbackAction(label="關門", data=close_token),
                ],
            ),
        )
        return line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[template])
        )

    except Exception as e:
        logger.error(f"Error while processing text message: {e}")
        try:
            reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )
        except Exception as reply_error:
            logger.error(f"Unable to send error reply: {reply_error}")
            try:
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text="❌ 系統錯誤，請稍後再試。")],
                    )
                )
                logger.info(f"Sent push message instead of reply to user {user_id}")
            except Exception as push_error:
                logger.error(f"Failed to send push message: {push_error}")


@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    is_authorized = is_user_authorized(user_id)

    if not is_authorized:
        verify_token = py_secrets.token_urlsafe(24)
        store_verify_token(verify_token, user_id)
        verify_url = f"{VERIFY_URL_BASE}?token={verify_token}"
        reply = TemplateMessage(
            alt_text="請先驗證定位",
            template=ButtonsTemplate(
                text="請先在車場範圍內進行位置驗證",
                actions=[URIAction(label="📍 驗證我的位置", uri=verify_url)],
            ),
        )
        return line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
        )

    try:
        token = event.postback.data
        record = TOKENS.get(token)
        if not record or len(record) != 3:
            logger.warning(f"Invalid token in postback: {token[:8]}...")
            reply = TextMessage(text="❌ 無效操作")
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        token_user_id, action, expiry = record
        TOKENS.pop(token, None)
        logger.info(f"Found and used token for action: {action}")

        if event.source.user_id != token_user_id or time.time() > expiry:
            reply = TextMessage(text="❌ 此操作已失效，請重新傳送位置")
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        success, error = send_garage_command(action)
        if not success:
            logger.error(f"Failed to send garage command: {error}")
            reply = TextMessage(text="⚠️ 無法連接車庫控制器，請稍後再試。")
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        if action == "open":
            reply = TextMessage(text="✅ 門已開啟，請小心進出。")
        else:
            reply = TextMessage(text="✅ 門已關閉，感謝您的使用。")
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
        )

    except Exception as e:
        logger.error(f"Unexpected error during postback handling: {e}")
        try:
            reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )
        except Exception as reply_error:
            logger.error(f"Unable to send error reply: {reply_error}")
            try:
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text="❌ 系統錯誤，請稍後再試。")],
                    )
                )
                logger.info(f"Sent push message instead of reply to user {user_id}")
            except Exception as push_error:
                logger.error(f"Failed to send push message: {push_error}")
