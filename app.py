from flask import Flask, request, abort
from linebot.v3.messaging import ApiClient, MessagingApi, Configuration, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction, LocationAction, PostbackAction
from linebot.v3 import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent, PostbackEvent
from linebot.v3.exceptions import InvalidSignatureError
import time
import secrets
import os
from geopy.distance import geodesic

app = Flask(__name__)

ALLOWED_USERS = {
    "Uea6813ef8ec77e7446090621ebcf472a": "admin_Brian",
    "U1d640cea545510e631396b5306ade151": "cyn.18"
}
PENDING_USERS = set()
# Single-use tokens: token -> (user_id, action, expiry_timestamp)
TOKENS = {}

# 用你的 channel access token 跟 secret 替換
LINE_CHANNEL_ACCESS_TOKEN = 'I6l46sYem5H4kuRx/J14iT64aNNTxSvOaSQzD3Wsp5U+tN/yjMM/mbq2H74zn6Jjo/cpiPfIaUAnV8sMsO4UnhNetrUZxLpC9SK8fIR4hSRomSJ3H4wr+y0GXcr+uBIiKjdnzi0jKE7+K4gzXYvIRQdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '2eeb33ec876a3a3ad7cba129de6d3207'

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
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    user_id = event.source.user_id
    user_msg = event.message.text
    print("使用者 ID：", user_id)

    if user_id not in ALLOWED_USERS:
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="❌ 您尚未註冊為停車場用戶，請聯絡管理員。")]))
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

@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location(event):
    user_id = event.source.user_id

    if user_id not in ALLOWED_USERS:
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="❌ 未授權使用者，請勿嘗試操作。")]))
        return

    user_loc = (event.message.latitude, event.message.longitude)
    distance = geodesic(user_loc, GATE_LOCATION).meters

    if distance <= GATE_RADIUS_METERS:
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
        print("❌ GPS 不在範圍內")
        reply = TextMessage(text="您目前不在停車場範圍內，請靠近後再試。")

    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))



# Postback handler for one-time token actions
@handler.add(PostbackEvent)
def handle_postback(event):
    token = event.postback.data
    record = TOKENS.get(token)
    # clean expired tokens
    TOKENS.clear()
    TOKENS.update({k: v for k, v in TOKENS.items() if v[2] > time.time()})
    if not record:
        return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="❌ 無效操作")]))
    user_id, action, expiry = record
    if event.source.user_id != user_id or time.time() > expiry:
        TOKENS.pop(token, None)
        return line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="❌ 此操作已失效，請重新傳送位置")]))
    # valid, consume token
    TOKENS.pop(token, None)
    if action == 'open':
        # TODO: insert GPIO open logic
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="✅ 門已開啟，請小心進出。")]))
    else:
        # TODO: insert GPIO close logic
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="✅ 門已關閉，感謝您的使用。")]))

if __name__ == "__main__":
    app.run(host='localhost', port=5000)
