from flask import Flask, request, abort
from linebot.v3.messaging import ApiClient, MessagingApi, Configuration, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction, LocationAction, PostbackAction
from linebot.v3 import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent, PostbackEvent
from linebot.v3.exceptions import InvalidSignatureError
import time
from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET
from models import get_allowed_users
from token_manager import generate_token, clean_expired_tokens
from location_manager import check_location
from logging_config import setup_logging

app = Flask(__name__)

ALLOWED_USERS = get_allowed_users()

# Set up logging
setup_logging(app)

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Could not verify the signature.")
        abort(400)
    except Exception as e:
        app.logger.error(f"Unexpected error occurred while handling the webhook: {e}")
        abort(500)
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
            token_open, token_close = generate_token()
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
        record = TOKENS.get(token)
        if not record:
            reply = TextMessage(text="❌ 無效操作")
            return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))
        action, expiry = record
        if event.source.user_id not in ALLOWED_USERS or time.time() > expiry:
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
    except Exception as e:
        app.logger.error(f"Unexpected error during postback handling: {e}")
        reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))

if __name__ == "__main__":
    app.run(host='localhost', port=5000)