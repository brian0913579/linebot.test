import logging
from logging.config import dictConfig
from flask import Flask, request, abort, jsonify
import hashlib
import hmac
import os
from dotenv import load_dotenv
from pathlib import Path
import base64
from werkzeug.exceptions import HTTPException
from math import radians, sin, cos, sqrt, atan2
from paho.mqtt import client as mqtt
import ssl
import time
import secrets

# TTL for one-time verification tokens (seconds)
VERIFY_TTL = 300  # 5 minutes
# In-memory store of one-time tokens: token -> (user_id, expiry_timestamp)
VERIFY_TOKENS = {}
# How long a location verification remains valid (seconds)
LOCATION_TTL = 10  # 1 hour, adjust as needed
# Load .env if present for local development
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
from google.cloud import secretmanager
from linebot.v3.messaging import ApiClient, MessagingApi, Configuration, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction, PostbackAction
from linebot.v3.messaging.models import TemplateMessage, ButtonsTemplate, URIAction, PushMessageRequest
from linebot.v3 import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
from linebot.v3.exceptions import InvalidSignatureError
from models import get_allowed_users
from token_manager import generate_token, clean_expired_tokens, TOKENS

app = Flask(__name__)

# In-memory store of users who passed browser-based location check with expiry
# Maps user_id to expiry timestamp
authorized_users = {}

# ——— Location verification helpers ———

# Haversine formula: returns distance in kilometers between two lat/lon points
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# Coordinates and allowed radius for your parking lot
PARK_LAT    = 24.79155    # set to your actual gate latitude
PARK_LNG    = 120.99442   # set to your actual gate longitude
MAX_DIST_KM = 0.5       # 0.5 km = 500 meters

@app.route("/healthz", methods=["GET"])
def healthz():
    return "OK", 200

# Set up logging
dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        '': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    }
})

# Function to access secrets from Google Cloud Secret Manager
def get_secret(secret_name):
    client = secretmanager.SecretManagerServiceClient()
    secret_path = f"projects/{os.getenv('GOOGLE_CLOUD_PROJECT')}/secrets/{secret_name}/versions/latest"  # Access latest version
    response = client.access_secret_version(name=secret_path)
    secret_data = response.payload.data.decode("UTF-8")
    return secret_data

# Support local .env overrides or fall back to Secret Manager
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or get_secret("line-channel-token2")
LINE_CHANNEL_SECRET       = os.getenv("LINE_CHANNEL_SECRET")       or get_secret("line-channel-secret2")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET must be set via .env or Secret Manager")

ALLOWED_USERS = get_allowed_users()

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# MQTT Broker settings for Pi garage controller
MQTT_BROKER   = os.getenv('MQTT_BROKER', 'bri4nting.duckdns.org')
MQTT_PORT     = int(os.getenv('MQTT_PORT', '8883'))
MQTT_USERNAME = os.getenv('MQTT_USERNAME', 'piuser')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', 'cool.com')
MQTT_CAFILE   = os.getenv('MQTT_CAFILE', '/etc/mosquitto/certs/ca.crt')

# Prepare an SSL context that uses our CA but skips hostname verification
_ssl_context = ssl.create_default_context(cafile=MQTT_CAFILE)
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_REQUIRED

# Verify signature function with enhanced logging
def verify_signature(signature, body):
    # Debugging log to check the received signature and body
    app.logger.debug(f"Received Signature: {signature}")
    app.logger.debug(f"Request Body: {body}")
    
    # Calculate expected signature
    expected_signature = base64.b64encode(
        hmac.new(
            key=LINE_CHANNEL_SECRET.encode(),
            msg=body.encode(),
            digestmod=hashlib.sha256
        ).digest()
    ).decode()

    # Debugging log to compare the expected signature with the received signature
    app.logger.debug(f"Expected Signature: {expected_signature}")
    
    # Return whether the received signature matches the expected signature
    return signature == expected_signature

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        # Verify the signature
        if not verify_signature(signature, body):
            app.logger.error("Invalid signature. Could not verify the signature.")
            abort(400)  # Return 400 if signature is invalid
        handler.handle(body, signature)
    except HTTPException:
        # Propagate HTTP errors (like abort(400))
        raise
    except Exception as e:
        app.logger.error(f"Unexpected error occurred while handling the webhook: {e}")
        abort(500)  # Return 500 for other errors
    return 'OK', 200  # Explicitly return 200 OK response

@app.route('/api/verify-location', methods=['POST'])
def verify_location():
    # query param contains the one-time verification token
    token = request.args.get('token')
    record = VERIFY_TOKENS.get(token)
    data = request.get_json(silent=True)
    # validate token
    if not token or not record:
        return jsonify(ok=False, message='無效或已過期的驗證'), 400
    user_id, expiry = record
    # remove token so it cannot be reused
    VERIFY_TOKENS.pop(token, None)
    # check expiry
    if time.time() > expiry:
        return jsonify(ok=False, message='驗證已過期，請重新驗證'), 400

    if not data or 'lat' not in data or 'lng' not in data:
        return jsonify(ok=False, message='缺少參數'), 400
    lat, lng, acc = data['lat'], data['lng'], data.get('acc', 999)
    dist = haversine(lat, lng, PARK_LAT, PARK_LNG)
    if dist <= MAX_DIST_KM and acc <= 50:
        authorized_users[user_id] = time.time() + LOCATION_TTL
        # immediately push the open/close buttons to the user
        open_token, close_token = generate_token(user_id)
        buttons = ButtonsTemplate(
            text='請選擇操作',
            actions=[
                PostbackAction(label='開門', data=open_token),
                PostbackAction(label='關門', data=close_token)
            ]
        )
        template = TemplateMessage(alt_text='開關門選單', template=buttons)
        line_bot_api.push_message(PushMessageRequest(
            to=user_id,
            messages=[template]
        ))
        return jsonify(ok=True)
    else:
        return jsonify(ok=False, message='不在車場範圍內'), 200

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    try:
        user_id = event.source.user_id
        user_msg = event.message.text
        print("使用者 ID：", user_id)
        app.logger.info(f"User {user_id} sent a text message.")

        # Respond only to the specific message "開關門"
        if user_msg != "開關門":
            return  # Do nothing if the message is not "開關門"

        # registration check
        if user_id not in ALLOWED_USERS:
            # not a parking customer
            reply = TextMessage(text="❌ 您尚未註冊為停車場用戶，請聯絡管理員。")
            return line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
            )

        # location verification check with expiry handling
        expiry = authorized_users.get(user_id)
        # if no entry or expired, treat as unverified
        if not expiry or expiry < time.time():
            # remove expired entry if present
            authorized_users.pop(user_id, None)
            # not yet verified -> send verify link
            # generate one-time token for verification
            verify_token = secrets.token_urlsafe(24)
            # store mapping to user_id
            VERIFY_TOKENS[verify_token] = (user_id, time.time() + VERIFY_TTL)
            verify_url = f"https://bri4nting.duckdns.org/verify-location?token={verify_token}"
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

        # user is registered and verified -> show open/close buttons
        # generate a unique pair of tokens for open and close
        open_token, close_token = generate_token(user_id)
        buttons = ButtonsTemplate(
            text='請選擇操作',
            actions=[
                PostbackAction(label='開門', data=open_token),
                PostbackAction(label='關門', data=close_token)
            ]
        )
        reply = TemplateMessage(alt_text='開關門選單', template=buttons)
        return line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[reply])
        )

    except Exception as e:
        app.logger.error(f"Error while processing text message: {e}")
        reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if user_id not in authorized_users:
        # user hasn’t passed verify step yet
        verify_url = f"https://bri4nting.duckdns.org/verify-location?user_id={user_id}"
        reply = TemplateMessage(
            alt_text='請先驗證定位',
            template=ButtonsTemplate(
                text='請先在車場範圍內進行位置驗證',
                actions=[URIAction(label='📍 驗證我的位置', uri=verify_url)]
            )
        )
        return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

    try:
        clean_expired_tokens()

        token = event.postback.data
        record = TOKENS.get(token)  # Get the token data from TOKENS

        if not record:
            reply = TextMessage(text="❌ 無效操作")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

        # Now check if there are exactly 3 elements to unpack
        if len(record) == 3:
            user_id, action, expiry = record
        else:
            raise ValueError("Token record does not have 3 values.")

        if event.source.user_id != user_id or time.time() > expiry:
            TOKENS.pop(token, None)
            reply = TextMessage(text="❌ 此操作已失效，請重新傳送位置")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

        TOKENS.pop(token, None)

        # Send command to Raspberry Pi via MQTT
        mqtt_cmd = 'up' if action == 'open' else 'down'
        try:
            # Explicit MQTT client to allow ssl_context
            client = mqtt.Client()
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
            client.tls_set_context(_ssl_context)
            client.connect(MQTT_BROKER, MQTT_PORT)
            client.publish('garage/command', mqtt_cmd)
            client.disconnect()
            app.logger.info(f"Published MQTT command: {mqtt_cmd}")
        except Exception as e:
            app.logger.error(f"Failed to publish MQTT command: {e}")

        if action == 'open':
            reply = TextMessage(text="✅ 門已開啟，請小心進出。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        else:
            reply = TextMessage(text="✅ 門已關閉，感謝您的使用。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

    except KeyError:
        app.logger.error("Token not found or invalid token provided.")
        reply = TextMessage(text="❌ 無效操作")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
    except ValueError as e:
        app.logger.error(f"Error in token unpacking: {e}")
        reply = TextMessage(text="❌ 無效操作")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
    except Exception as e:
        app.logger.error(f"Unexpected error during postback handling: {e}")
        reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
