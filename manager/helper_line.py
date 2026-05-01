import os
from datetime import datetime, timedelta

from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage, ShowLoadingAnimationRequest,
    ReplyMessageRequest, TemplateMessage, ButtonsTemplate, DatetimePickerAction, Message
)
from pydantic import StrictStr

from manager.database_manager import SingleConnection, log_chat
from manager.util import to_date_str

_configuration = Configuration(access_token=os.getenv("LINE_BOT_ACCESS_TOKEN"))


def fetch_line_config():
    global _configuration
    if _configuration:
        return _configuration
    else:
        _configuration = Configuration(access_token=os.getenv("LINE_BOT_ACCESS_TOKEN"))
        return _configuration


# take user_id and return user_id, display_name, picture_url, and status_message
def fetch_line_profile(user_id):
    with SingleConnection() as con:
        user = con.execute("SELECT * FROM users WHERE user_id = %s", (user_id,)).fetchone()
        return dict(user) if user else None

# take user_id and return user_id, display_name, picture_url, and status_message
def upsert_line_profile(user_id):
    with ApiClient(fetch_line_config()) as api_client:
        line_bot_api = MessagingApi(api_client)
        profile = line_bot_api.get_profile(user_id)
        next_week = to_date_str((datetime.today() + timedelta(days=7)).date())
        with SingleConnection() as con:
            con.execute("INSERT INTO users (user_id, display_name, picture_url, status_message, end_date) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT(user_id) "
                        "DO UPDATE SET display_name=%s, picture_url=%s, status_message=%s;",
                        (profile.user_id, profile.display_name, profile.picture_url, profile.status_message, next_week,
                         profile.display_name, profile.picture_url, profile.status_message))
            con.commit()
            # then return the updated one. Need to fetch for the end date

            user = con.execute("SELECT * FROM users WHERE user_id = %s", (profile.user_id,)).fetchone()
            return dict(user)


def fetch_all_users():
    with SingleConnection() as con:
        return [dict(_) for _ in con.execute("SELECT * FROM users ORDER BY display_name").fetchall()]


def push_message(user_id, message):
    with ApiClient(fetch_line_config()) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.push_message_with_http_info(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=message)]))


def show_loading(chat_id, loading_seconds=5):
    with ApiClient(fetch_line_config()) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=chat_id, loadingSeconds=loading_seconds))


def reply_message(reply_token, content):
    with ApiClient(fetch_line_config()) as api_client:
        line_bot_api = MessagingApi(api_client)
        if isinstance(content, str):
            print("replying:", content)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(replyToken=reply_token, messages=[TextMessage(text=content)]))
        # if it's already a message, just send it
        elif isinstance(content, Message):
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(replyToken=reply_token, messages=[content]))


def datetime_message(reply_token, text):
    print("datetime:", text)
    date_picker = TemplateMessage(
        altText=text,
        template=ButtonsTemplate(
            text=text,
            actions=[
                DatetimePickerAction(
                    label=StrictStr("วันที่และเวลานัดหมาย"),
                    data="action=set_datetime",  # Identify this specific picker
                    mode=StrictStr("datetime"))]))

    reply_message(reply_token=reply_token, content=date_picker)



def plain_text_reply_and_log(response_message, model_name, user_id, original_text, reply_token):
    log_chat(user_id, message=original_text, response=response_message, model_name=model_name)
    reply_message(reply_token=reply_token, content=response_message)


def plain_text_push_and_log(push_text, model_name, user_id, original_text):
    log_chat(user_id, message=original_text, response=push_text, model_name=model_name)
    push_message(user_id=user_id, message=push_text)
