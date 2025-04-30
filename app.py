from flask import Flask, request, abort
from linebot.v3.messaging import ApiClient, MessagingApi, Configuration, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction, LocationAction, PostbackAction
from linebot.v3 import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent, PostbackEvent
from linebot.v3.exceptions import InvalidSignatureError
import time
import secrets
import os
from geopy.distance import geodesic
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from sortedcontainers import SortedDict

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

import sqlite3

# Fetch the allowed users from SQLite database
def get_allowed_users():
    connection = sqlite3.connect('users.db')
    cursor = connection.cursor()
    cursor.execute("SELECT user_id, user_name FROM allowed_users")
    users = cursor.fetchall()
    connection.close()
    return {user[0]: user[1] for user in users}

ALLOWED_USERS = get_allowed_users()
PENDING_USERS = set()
# Initialize a SortedDict to store tokens, ordered by expiry time
TOKENS = SortedDict()

# Set up logging configuration
log_handler = RotatingFileHandler('app.log', maxBytes=10 * 1024 * 1024, backupCount=3)  # Log rotation
log_handler.setLevel(logging.INFO)  # Log level can be adjusted
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)

# Add log handler to Flask's logger
app.logger.addHandler(log_handler)

# Optionally, you can log to the console as well
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
app.logger.addHandler(console_handler)

# 用你的 channel access token 跟 secret 替換
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 你的停車場座標（舉例：台北車站）
GATE_LOCATION = (24.79155, 120.99442)
GATE_RADIUS_METERS = 50

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Could not verify the signature.")
        abort(400)  # Return a 400 Bad Request status
    except Exception as e:
        app.logger.error(f"Unexpected error occurred while handling the webhook: {e}")
        abort(500)  # Internal server error
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    try:
        user_id = event.source.user_id
        user_msg = event.message.text
        print("使用者 ID：", user_id)
        app.logger.info(f"User {user_id} sent a text message.")

        if user_id not in ALLOWED_USERS:
            reply = TextMessage(text="❌ 您尚未註冊為停車場用戶，請聯絡管理員。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
            return

        else:
            # 清除任何舊的待驗證狀態
            PENDING_USERS.discard(user_id)
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
        distance = geodesic(user_loc, GATE_LOCATION).meters

        if distance <= GATE_RADIUS_METERS:
            app.logger.info(f"User {user_id} is accessing the parking lot.")
            print("✅ GPS OK，可進行操作")
            # Generate one-time tokens valid for 5 minutes
            token_open = secrets.token_urlsafe(16)
            token_close = secrets.token_urlsafe(16)
            TOKENS[token_open] = (user_id, 'open', time.time() + 300)
            TOKENS[token_close] = (user_id, 'close', time.time() + 300)
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

# Function to clean expired tokens (can be called periodically or with each operation)
def clean_expired_tokens():
    current_time = time.time()
    # Remove tokens that have expired
    expired_tokens = list(TOKENS.keys())  # Get all token keys
    for token in expired_tokens:
        _, _, expiry = TOKENS[token]
        if expiry <= current_time:  # Check if expired
            del TOKENS[token]

# Postback handler for one-time token actions
@handler.add(PostbackEvent)
def handle_postback(event):
    try:
        clean_expired_tokens()  # Clean expired tokens before processing

        token = event.postback.data
        record = TOKENS.get(token)
        if not record:
            reply = TextMessage(text="❌ 無效操作")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        user_id, action, expiry = record
        if event.source.user_id != user_id or time.time() > expiry:
            TOKENS.pop(token, None)
            reply = TextMessage(text="❌ 此操作已失效，請重新傳送位置")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        
        # valid, consume token
        TOKENS.pop(token, None)
        if action == 'open':
            # TODO: insert GPIO open logic
            reply = TextMessage(text="✅ 門已開啟，請小心進出。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        else:
            # TODO: insert GPIO close logic
            reply = TextMessage(text="✅ 門已關閉，感謝您的使用。")
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

    except KeyError:
        app.logger.error("Token not found or invalid token provided.")
        reply = TextMessage(text="❌ 無效操作")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
    except Exception as e:
        app.logger.error(f"Unexpected error during postback handling: {e}")
        reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

if __name__ == "__main__":
    app.run(host='localhost', port=5000)
