import logging
from logging.config import dictConfig
from flask import Flask, request, abort
import hashlib
import hmac
import os
from dotenv import load_dotenv
from pathlib import Path
# Load .env if present for local development
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
from google.cloud import secretmanager
from linebot.v3.messaging import ApiClient, MessagingApi, Configuration, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction, LocationAction, PostbackAction
from linebot.v3 import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent, PostbackEvent
from linebot.v3.exceptions import InvalidSignatureError
import time
from models import get_allowed_users
from token_manager import generate_token, clean_expired_tokens, TOKENS
from location_manager import check_location

app = Flask(__name__)

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

# Verify signature function with enhanced logging
def verify_signature(signature, body):
    # Debugging log to check the received signature and body
    app.logger.debug(f"Received Signature: {signature}")
    app.logger.debug(f"Request Body: {body}")
    
    # Calculate expected signature
    expected_signature = hmac.new(
        key=LINE_CHANNEL_SECRET.encode(),
        msg=body.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

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
    except Exception as e:
        app.logger.error(f"Unexpected error occurred while handling the webhook: {e}")
        abort(500)  # Return 500 for other errors
    return 'OK', 200  # Explicitly return 200 OK response

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

        # If the user sends "開關門", proceed with the parking lot logic
        if user_id not in ALLOWED_USERS:
            reply = TextMessage(text="❌ 您尚未註冊為停車場用戶，請聯絡管理員。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
            return

        else:
            reply = TextMessage(
                text="請傳送您的位置訊息，以便確認您是否在停車場範圍內：",
                quick_reply=QuickReply(items=[
                    QuickReplyItem(action=LocationAction(label="傳送位置"))
                ])
            )
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

    except Exception as e:
        app.logger.error(f"Error while processing text message: {e}")
        reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location(event):
    try:
        user_id = event.source.user_id

        if user_id not in ALLOWED_USERS:
            reply = TextMessage(text="❌ 未授權使用者，請勿嘗試操作。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
            return

        user_loc = (event.message.latitude, event.message.longitude)

        if check_location(user_loc):
            app.logger.info(f"User {user_id} is accessing the parking lot.")
            print("✅ GPS OK，可進行操作")
            token_open, token_close = generate_token(user_id)
            reply = TextMessage(
                text="您目前在停車場範圍內，請選擇動作：",
                quick_reply=QuickReply(items=[
                    QuickReplyItem(action=PostbackAction(label="開門", data=token_open)),
                    QuickReplyItem(action=PostbackAction(label="關門", data=token_close))
                ])
            )
        else:
            app.logger.info(f"User {user_id} is outside the parking lot range.")
            print("❌ GPS 不在範圍內")
            reply = TextMessage(text="您目前不在停車場範圍內，請靠近後再試。")

        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

    except Exception as e:
        app.logger.error(f"Error while processing location message: {e}")
        reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

@handler.add(PostbackEvent)
def handle_postback(event):
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
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)