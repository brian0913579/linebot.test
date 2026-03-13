import secrets as py_secrets
import time

from flask import current_app
from linebot.v3 import WebhookHandler
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

from app.services.token_service import token_service
from utils.logger_config import get_logger

logger = get_logger(__name__)


class LineService:
    def __init__(self, app=None):
        self.line_bot_api = None
        self.handler = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize LINE API clients."""
        access_token = app.config["LINE_CHANNEL_ACCESS_TOKEN"]
        channel_secret = app.config["LINE_CHANNEL_SECRET"]

        if not access_token or not channel_secret:
            raise RuntimeError("LINE credentials not available in environment")

        configuration = Configuration(access_token=access_token)
        api_client = ApiClient(configuration)
        self.line_bot_api = MessagingApi(api_client)
        self.handler = WebhookHandler(channel_secret)

    def build_open_close_template(self, user_id):
        open_token, close_token = token_service.generate_token(user_id)
        token_service.store_action_token(open_token, user_id, "open")
        token_service.store_action_token(close_token, user_id, "close")

        quick_reply = QuickReply(
            items=[
                QuickReplyItem(action=PostbackAction(label="🟢 開門", data=open_token)),
                QuickReplyItem(
                    action=PostbackAction(label="🔴 關門", data=close_token)
                ),
            ]
        )
        return TextMessage(text="請選擇車庫門操作：", quick_reply=quick_reply)

    def send_open_close_message(self, user_id, reply_token):
        template = self.build_open_close_template(user_id)
        return self._retry_api_call(
            lambda: self.line_bot_api.reply_message(
                ReplyMessageRequest(replyToken=reply_token, messages=[template])
            )
        )

    def send_camera_link(self, user_id, reply_token):
        """Generate a signed camera link and reply to the user."""
        from app.api.camera import generate_camera_token

        token = generate_camera_token(user_id)
        base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
        camera_url = f"{base_url}/camera?token={token}"
        ttl_hours = current_app.config.get("CAMERA_TOKEN_TTL", 3600) // 3600
        reply = TemplateMessage(
            altText="📹 即時監控畫面",
            template=ButtonsTemplate(
                text=f"您的監控連結（有效 {ttl_hours} 小時）：\n請勿將此連結分享給他人",
                actions=[URIAction(label="📹 查看監控畫面", uri=camera_url)],
            ),
        )
        return self._retry_api_call(
            lambda: self.line_bot_api.reply_message(
                ReplyMessageRequest(replyToken=reply_token, messages=[reply])
            )
        )

    def send_verification_message(self, user_id, reply_token):
        verify_token = py_secrets.token_urlsafe(24)
        token_service.store_verify_token(verify_token, user_id)
        verify_url = f"{current_app.config['VERIFY_URL_BASE']}?token={verify_token}"
        reply = TemplateMessage(
            altText="請先驗證定位",
            template=ButtonsTemplate(
                text="請先在車場範圍內進行位置驗證",
                actions=[URIAction(label="📍 驗證我的位置", uri=verify_url)],
            ),
        )
        return self._retry_api_call(
            lambda: self.line_bot_api.reply_message(
                ReplyMessageRequest(replyToken=reply_token, messages=[reply])
            )
        )

    def handle_system_error(self, user_id, reply_token, error, context):
        logger.error(f"Error in {context}: {error}")
        try:
            reply = TextMessage(text="❌ 系統錯誤，請稍後再試。")
            self._retry_api_call(
                lambda: self.line_bot_api.reply_message(
                    ReplyMessageRequest(replyToken=reply_token, messages=[reply])
                )
            )
        except Exception as reply_error:
            logger.error(f"Unable to send error reply: {reply_error}")
            try:
                self._retry_api_call(
                    lambda: self.line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=[TextMessage(text="❌ 系統錯誤，請稍後再試。")],
                        )
                    )
                )
            except Exception as push_error:
                logger.error(f"Failed to send push message: {push_error}")

    def reply_text(self, reply_token, text):
        return self._retry_api_call(
            lambda: self.line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=reply_token, messages=[TextMessage(text=text)]
                )
            )
        )

    def push_text(self, user_id, text):
        return self._retry_api_call(
            lambda: self.line_bot_api.push_message(
                PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
            )
        )

    def _retry_api_call(self, func, max_attempts=3, delay=1):
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


# Create a singleton instance
line_service = LineService()
