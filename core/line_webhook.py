import hashlib
import hmac
import base64
import time
import secrets as py_secrets
from math import radians, sin, cos, sqrt, atan2
import importlib.util
from flask import request, abort, jsonify
from utils.logger_config import get_logger

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, 
    ReplyMessageRequest, TextMessage, 
    TemplateMessage, ButtonsTemplate, 
    PostbackAction, URIAction, PushMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
from linebot.v3.exceptions import InvalidSignatureError

from config.config_module import (
    LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET,
    PARK_LAT, PARK_LNG, MAX_DIST_KM, 
    VERIFY_TTL, LOCATION_TTL, VERIFY_URL_BASE, CACHE_ENABLED
)
from core.mqtt_handler import send_garage_command
from core.token_manager import generate_token, clean_expired_tokens, TOKENS
from core.models import get_allowed_users

# Define cache-related functions (using in-memory storage)
def store_verify_token(token, user_id): 
    logger.info(f"Storing verification token in memory: {token[:8]}...")
    VERIFY_TOKENS[token] = (user_id, time.time() + VERIFY_TTL)
    return True

def get_verify_token(token):
    record = VERIFY_TOKENS.get(token)
    logger.info(f"Looking up token in memory: {token[:8] if token else 'None'}... Found: {record is not None}")
    
    if not record:
        return None, None
    
    user_id, expiry = record
    # Remove token so it cannot be reused
    VERIFY_TOKENS.pop(token, None)
    logger.info(f"Found and removed token for user_id: {user_id}")
    
    return user_id, expiry

def authorize_user(user_id):
    authorized_users[user_id] = time.time() + LOCATION_TTL
    logger.info(f"Authorized user {user_id} for {LOCATION_TTL} seconds")
    return True

def is_user_authorized(user_id):
    expiry = authorized_users.get(user_id)
    is_valid = expiry and expiry >= time.time()
    
    # Remove expired entry if present
    if expiry and expiry < time.time():
        authorized_users.pop(user_id, None)
        
    return is_valid

# Configure logger
logger = get_logger(__name__)

# In-memory store of one-time verification tokens: token -> (user_id, expiry_timestamp)
# Used as fallback when Redis is unavailable
VERIFY_TOKENS = {}

# In-memory store of users who passed browser-based location check with expiry
# Maps user_id to expiry timestamp
# Used as fallback when Redis is unavailable
authorized_users = {}

# Set up LINE API clients
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Haversine formula: returns distance in kilometers between two lat/lon points
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def build_open_close_template(user_id):
    open_token, close_token = generate_token(user_id)
    if CACHE_ENABLED:
        store_action_token(open_token, user_id, 'open')
        store_action_token(close_token, user_id, 'close')
    buttons = ButtonsTemplate(
        text='請選擇操作',
        actions=[
            PostbackAction(label='開門', data=open_token),
            PostbackAction(label='關門', data=close_token)
        ]
    )
    return TemplateMessage(alt_text='開關門選單', template=buttons)

# Verify signature function
def verify_signature(signature, body):
    logger.debug(f"Received Signature: {signature}")
    logger.debug(f"Request Body: {body}")
    
    # Calculate expected signature
    expected_signature = base64.b64encode(
        hmac.new(
            key=LINE_CHANNEL_SECRET.encode(),
            msg=body.encode(),
            digestmod=hashlib.sha256
        ).digest()
    ).decode()

    logger.debug(f"Expected Signature: {expected_signature}")
    return signature == expected_signature

# Handler for webhook endpoint
def webhook_handler():
    """
    Handle incoming webhook events from LINE Platform.
    Signature validation is now performed by middleware.
    """
    body = request.get_data(as_text=True)
    signature = request.headers.get('X-Line-Signature', '')

    try:
        # Process the webhook content
        handler.handle(body, signature)
        logger.info("Webhook processed successfully")
    except InvalidSignatureError:
        logger.error("Invalid signature from LINE Platform")
        abort(400, description="Invalid signature")
    except Exception as e:
        # Log the error but still return 200 OK to LINE Platform
        # This prevents unnecessary retries for transient errors
        logger.error(f"Error while handling webhook: {e}")
        logger.error(f"Request body: {body[:200]}...")  # Log partial body for debugging
    
    # Always return 200 OK to LINE Platform
    # This is recommended by LINE to acknowledge receipt of the webhook
    return 'OK', 200

# Handler for location verification
def verify_location_handler():
    # Query param contains the one-time verification token
    token = request.args.get('token')
    data = request.get_json(silent=True)
    
    logger.info(f"Received location verification request for token: {token[:8] if token else 'None'}...")
    
    # Get and validate token (using our in-memory function)
    user_id, expiry = get_verify_token(token)
    
    # Debug check all tokens in memory
    logger.info(f"Current tokens in memory: {len(VERIFY_TOKENS)}")
    
    # Validate token
    if not token or not user_id:
        logger.warning(f"Invalid token: token_provided={token is not None}, user_id_found={user_id is not None}")
        return jsonify(ok=False, message='無效或已過期的驗證'), 400
    
    # Check expiry
    if expiry and time.time() > expiry:
        return jsonify(ok=False, message='驗證已過期，請重新驗證'), 400

    if not data or 'lat' not in data or 'lng' not in data:
        return jsonify(ok=False, message='缺少參數'), 400
    
    lat, lng, acc = data['lat'], data['lng'], data.get('acc', 999)
    dist = haversine(lat, lng, PARK_LAT, PARK_LNG)
    
    if dist <= MAX_DIST_KM and acc <= 50:
        # Store authorization in Redis if enabled, otherwise in memory
        if CACHE_ENABLED:
            authorize_user(user_id)
        else:
            authorized_users[user_id] = time.time() + LOCATION_TTL
            
        # Immediately push the open/close buttons to the user
        template = build_open_close_template(user_id)
        line_bot_api.push_message(PushMessageRequest(
            to=user_id,
            messages=[template]
        ))
        return jsonify(ok=True)
    else:
        return jsonify(ok=False, message='不在車場範圍內'), 200

# Handle text messages
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    try:
        user_id = event.source.user_id
        user_msg = event.message.text
        logger.info(f"User {user_id} sent a text message: {user_msg}")

        # Respond only to the specific message "開關門"
        if user_msg != "開關門":
            return  # Do nothing if the message is not "開關門"

        # Registration check
        ALLOWED_USERS = get_allowed_users()
        if user_id not in ALLOWED_USERS:
            # Not a parking customer
            reply = TextMessage(text="❌ 您尚未註冊為停車場用戶，請聯絡管理員。")
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        # Location verification check with expiry handling
        is_authorized = is_user_authorized(user_id)
        
        # If not authorized, require verification
        if not is_authorized:
            # Generate one-time token for verification
            verify_token = py_secrets.token_urlsafe(24)
            
            # Store token in memory
            store_verify_token(verify_token, user_id)
                
            verify_url = f"{VERIFY_URL_BASE}?token={verify_token}"
            reply = TemplateMessage(
                alt_text='請先驗證定位',
                template=ButtonsTemplate(
                    text='請先在車場範圍內進行位置驗證',
                    actions=[URIAction(label='📍 驗證我的位置', uri=verify_url)]
                )
            )
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        # User is registered and verified -> show open/close buttons
        open_token, close_token = generate_token(user_id)
        template = TemplateMessage(
            alt_text='開關門選單',
            template=ButtonsTemplate(
                text='請選擇動作',
                actions=[
                    PostbackAction(label='開門', data=open_token),
                    PostbackAction(label='關門', data=close_token)
                ]
            )
        )
        return line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[template])
        )

    except Exception as e:
        logger.error(f"Error while processing text message: {e}")
        try:
            reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        except Exception as reply_error:
            logger.error(f"Unable to send error reply: {reply_error}")
            # If we can't reply, try to push a message instead
            try:
                line_bot_api.push_message(PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text="❌ 系統錯誤，請稍後再試。")]
                ))
                logger.info(f"Sent push message instead of reply to user {user_id}")
            except Exception as push_error:
                logger.error(f"Failed to send push message: {push_error}")

# Handle postback events
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    
    # Check if user is authorized
    is_authorized = is_user_authorized(user_id)
    
    if not is_authorized:
        # User hasn't passed verify step yet
        verify_token = py_secrets.token_urlsafe(24)
        
        # Store token in memory
        store_verify_token(verify_token, user_id)
            
        verify_url = f"{VERIFY_URL_BASE}?token={verify_token}"
        reply = TemplateMessage(
            alt_text='請先驗證定位',
            template=ButtonsTemplate(
                text='請先在車場範圍內進行位置驗證',
                actions=[URIAction(label='📍 驗證我的位置', uri=verify_url)]
            )
        )
        return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

    try:
        # Clean expired tokens from in-memory storage if not using Redis
        if not CACHE_ENABLED:
            clean_expired_tokens()

        token = event.postback.data
        
        # Get token from in-memory TOKENS
        record = TOKENS.get(token)  # Get the token data from TOKENS
        if not record or len(record) != 3:
            valid_token = False
            logger.warning(f"Invalid token in postback: {token[:8]}...")
        else:
            user_id, action, expiry = record
            TOKENS.pop(token, None)  # Remove token to prevent reuse
            logger.info(f"Found and used token for action: {action}")
            valid_token = True

        if not valid_token:
            reply = TextMessage(text="❌ 無效操作")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

        if event.source.user_id != user_id or time.time() > expiry:
            reply = TextMessage(text="❌ 此操作已失效，請重新傳送位置")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

        # Send command to MQTT broker
        success, error = send_garage_command(action)
        
        if not success:
            logger.error(f"Failed to send garage command: {error}")
            reply = TextMessage(text="⚠️ 無法連接車庫控制器，請稍後再試。")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

        if action == 'open':
            reply = TextMessage(text="✅ 門已開啟，請小心進出。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        else:
            reply = TextMessage(text="✅ 門已關閉，感謝您的使用。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

    except Exception as e:
        logger.error(f"Unexpected error during postback handling: {e}")
        try:
            reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        except Exception as reply_error:
            logger.error(f"Unable to send error reply: {reply_error}")
            # If we can't reply, try to push a message instead
            try:
                line_bot_api.push_message(PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text="❌ 系統錯誤，請稍後再試。")]
                ))
                logger.info(f"Sent push message instead of reply to user {user_id}")
            except Exception as push_error:
                logger.error(f"Failed to send push message: {push_error}")