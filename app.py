# -*- coding: utf-8 -*-
import json
import os
import re
import threading
from datetime import datetime, timedelta

import dotenv
import pythainlp.util.date
import speech_recognition as sr
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, abort, Blueprint, jsonify, render_template
from flask_socketio import SocketIO
from google import genai
from google.genai.errors import ClientError
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage, ShowLoadingAnimationRequest, TemplateMessage, ButtonsTemplate, DatetimePickerAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
from pydantic import StrictStr

from constants import ReminderState
from database_manager import SingleConnection

# need to do this so that the code can be run from any current working directory
# otherwise the CLI may use current working directory instead of using
# the relative project path
script_dir = os.path.dirname(os.path.abspath(__file__))

bp = Blueprint('llm', __name__, template_folder='templates', static_folder='static', root_path="llm")
env = dotenv.load_dotenv()

gemini_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
configuration = Configuration(access_token=os.getenv("LINE_BOT_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_BOT_CHANNEL_SECRET"))

app = Flask(__name__)
scheduler = BackgroundScheduler()

MODEL_LIST = ['gemini-flash-latest',
              'gemini-3-flash-preview',
              'gemini-flash-lite-latest',
              'gemini-3.1-flash-lite-preview',
              'gemini-2.5-flash',
              'gemini-2.5-flash-lite']
CURRENT_MODEL_INDEX = 0

memory = "Nothing."
recognizer = sr.Recognizer()
stop_listening = False

socketio = SocketIO(app)

SOCKET_NAMESPACE = "/llm"

system_prompt = ""
with open(os.path.join(script_dir, "text/system_prompt.txt"), "r", encoding="utf8") as f:
    for line in f:
        system_prompt += line

context = ""
with open(os.path.join(script_dir, "text/context.txt"), "r", encoding="utf8") as f:
    for line in f:
        context += line


def test_shit(prompt):
    for _model in MODEL_LIST:
        print("\ntesting", _model)
        try:
            result = gemini_client.models.generate_content_stream(
                model=_model, contents=prompt)  # xxx here

            final_text = ""
            for r in result:
                r = r.text
                # print(r, end=" ")
                final_text += r
                socketio.emit('new_word', r, namespace=SOCKET_NAMESPACE)
                socketio.sleep(0)  # force the server to flush the socketio. DO NOT REMOVE
                # print()
                # Assuming the result is a list of dictionaries
            print("model=", _model, final_text)
        except ClientError as e:
            print(e.code, e.message)


def process_prompt(prompt):
    global CURRENT_MODEL_INDEX
    while CURRENT_MODEL_INDEX < len(MODEL_LIST):
        try:
            result = gemini_client.models.generate_content_stream(
                model=MODEL_LIST[CURRENT_MODEL_INDEX], contents=prompt)  # xxx here
            final_text = ""
            for r in result:
                r = r.text
                # print(r, end=" ")
                final_text += r
                socketio.emit('new_word', r, namespace=SOCKET_NAMESPACE)
                socketio.sleep(0)  # force the server to flush the socketio. DO NOT REMOVE
            # print()
            # Assuming the result is a list of dictionaries
            # print
            return final_text
        except ClientError as e:
            print(datetime.now(), e.message)
            CURRENT_MODEL_INDEX += 1
    return "ขออภัยค่ะ ระบบหนูกำลังได้รับการปรับปรุงอยู่นะคะ เดี๋ยวหนูจะกลับมาใหม่นะ ไม่เกิน 1 วันหนูสัญญา <3"


def generate_text(user_prompt):
    prompt = {
        "system_prompt": system_prompt,
        "context": context,
        "user_prompt": user_prompt
    }
    prompt = json.dumps(prompt, ensure_ascii=False)
    return process_prompt(prompt)


@bp.route("/callback", methods=['GET'])
def callback_get():
    res = generate_text("Hello. Are you ready to help?")
    return f"callback ready for webhook: {res}"


def extract_datetime_components(s):
    # Match pattern: yyyy-MM-dd hh-mm
    pattern = r'(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})'
    match = re.search(pattern, s)

    if match:
        year, month, day, hour, minute = match.groups()
        return int(year), int(month), int(day), int(hour), int(minute)
    else:
        raise ValueError("No valid datetime substring found in the input.")


def schedule_notification(user_id, date_text, time_text, message):
    with SingleConnection() as con:
        con.execute("INSERT INTO notifications (user_id, date, time, message) "
                    "VALUES (?, ?, ?, ?)",
                    (str(user_id), date_text, time_text, message))
        con.commit()


@bp.route("/callback", methods=['POST'])
def callback_post():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    app.logger.info("Signature: " + signature)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


def push_message(user_id, message):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.push_message_with_http_info(
            PushMessageRequest(to=user_id,
                               messages=[TextMessage(text=message)])
        )


def check_for_notification():
    with SingleConnection() as con:
        now = datetime.now()
        date = now.strftime("%Y-%m-%d")
        ytd = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        notifications = con.execute("SELECT * FROM notifications WHERE sent = 0 and (date == ? or date == ?)",
                                    (date, ytd)).fetchall()
        sent_count = 0
        for n in notifications:
            n = dict(n)  # to prevent sqlite3 different thread problem
            scheduled_dt = datetime.strptime(f"{n['date']} {n['time']}", "%Y-%m-%d %H:%M")
            if scheduled_dt < now:
                push_message(user_id=n['user_id'], message=f"อย่าลืม: {n['message']}")
                sent_count += 1

        if sent_count > 0:
            print(
                f"checking for notifications to be sent... now {now}: {sent_count} messages sent.")


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    if event.message.type == "text":
        event_text = event.message.text
        if event_text == "สวัสดี คุณช่วยอะไรฉันได้บ้าง":
            response_message = "สวัสดีค่ะ/ครับ หนูเป็นผู้ช่วยพยาบาลผู้เชี่ยวชาญด้านการดูแลผู้ป่วยมะเร็งเด็กนะคะ ยินดีให้คำแนะนำและข้อมูลเกี่ยวกับการดูแลเด็กป่วยมะเร็งเม็ดเลือดขาวค่ะ มีเรื่องอะไรอยากปรึกษาได้เลยนะคะ"
            log_chat(event.source.user_id, message=event.message.text, response=response_message,
                     model_name="default response")
            reply_message(reply_token=event.reply_token, text=response_message)
        elif event_text.startswith("reminder"):
            create_reminder(event.source.user_id, event.reply_token)
        elif event_text.startswith("cancel"):
            set_session(event.source.user_id, ReminderState.IDLE)
        elif get_session(event.source.user_id)["state"] != ReminderState.IDLE:
            create_reminder(user_id=event.source.user_id,
                            reply_token=event.reply_token,
                            action="continue",
                            text=event_text)
        else:
            show_loading(event.source.user_id, 10)
            response_message = generate_text(event.message.text)
            log_chat(event.source.user_id, message=event.message.text, response=response_message,
                     model_name=MODEL_LIST[CURRENT_MODEL_INDEX])
            reply_message(reply_token=event.reply_token, text=response_message)
    else:
        print("cannot understand:", event.message.type, event.message)
        reply_message(reply_token=event.reply_token,
                      text="ขออภัย ฉันเข้าใจแค่ข้อความ")


@handler.add(PostbackEvent)
def handle_postback_message(event):
    if event.postback.data == "action=set_datetime":
        create_reminder(user_id=event.source.user_id,
                        reply_token=event.reply_token,
                        action="continue",
                        text=event.postback.params['datetime'])
    else:
        print(event.message.type, event.message)
        reply_message(reply_token=event.reply_token,
                      text="ขออภัย ฉันเข้าใจแค่ข้อความ")


def show_loading(chat_id, loading_seconds=5):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=chat_id,
                                                                        loadingSeconds=loading_seconds))


def reply_message(reply_token, text):
    print("replying:", text)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


def datetime_message(reply_token, text):
    print("datetime:", text)
    with ApiClient(configuration) as api_client:
        date_picker = TemplateMessage(
            altText=text,
            template=ButtonsTemplate(
                text=text,
                actions=[
                    DatetimePickerAction(
                        label=StrictStr("วันที่และเวลานัดหมาย"),
                        data="action=set_datetime",  # Identify this specific picker
                        mode=StrictStr("datetime")
                    )
                ]
            )
        )

        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=reply_token,
                messages=[date_picker]
            )
        )


@app.before_request
def log_request():
    print("Incoming request:", request.method, request.path)


@bp.route('/')
def chatbot():
    return render_template('chatbot.html')


@socketio.on('test_connection', namespace=SOCKET_NAMESPACE)
def handle_connect_test():
    print("test_connection")


@socketio.on('connect', namespace=SOCKET_NAMESPACE)
def handle_connect():
    print("Client connected")


@bp.route('/summarize', methods=['POST'])
def summarize_text():
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "Invalid input, 'prompt' is required"}), 400

    prompt = {
        "system_prompt": system_prompt,
        "context": context,
        "user_prompt": data['prompt']
    }
    prompt = json.dumps(prompt, ensure_ascii=False)
    return process_prompt(prompt)


@bp.route('/generate', methods=['POST'])
def generate_text_api():
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "Invalid input, 'prompt' is required"}), 400
    if 'passcode' not in data or data['passcode'] != "Aj.Nune<3":
        print(data['passcode'])
        return jsonify({"error": "Invalid passcode"}), 400

    prompt = {
        "system_prompt": system_prompt,
        "context": context,
        "user_prompt": data['prompt']
    }
    prompt = json.dumps(prompt, ensure_ascii=False)
    return process_prompt(prompt)


@bp.route('/transcribe')
def transcribe():
    return render_template('transcribe.html')


def background_recognition():
    global stop_listening
    mic = sr.Microphone()

    with mic as source:
        recognizer.adjust_for_ambient_noise(source)

    def callback(_recognizer, audio):
        try:
            text = _recognizer.recognize_google(audio)
            socketio.emit('transcription', {'text': text}, namespace=SOCKET_NAMESPACE)
        except sr.UnknownValueError:
            socketio.emit('transcription', {'text': '[Unintelligible]'}, namespace=SOCKET_NAMESPACE)

    with mic as source:
        stop_listening = recognizer.listen_in_background(source, callback)


@socketio.on('start_transcribing', namespace=SOCKET_NAMESPACE)
def start_transcribing():
    global stop_listening
    threading.Thread(target=background_recognition).start()


@socketio.on('stop_transcribing', namespace=SOCKET_NAMESPACE)
def stop_transcribing():
    global stop_listening
    if stop_listening:
        stop_listening()


# ----------------- for a legit reminder logic ---------------
# Simple in-memory storage (Use Redis/Database for production)
# Format: { 'user_id': {'state': '...', 'data': {'title': '...', 'datetime': '...', 'detail': '...'}} }
def formatted_thai_dt(dt):
    return pythainlp.util.thai_strftime(dt_obj=dt, fmt="%Aที่ %d %B %Y เวลา %H:%M น.")


user_sessions = {}


def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {'state': ReminderState.IDLE, 'data': {}}
    return user_sessions[user_id]


def set_session(user_id, state, title=None, target_datetime=None, detail=None):
    if user_id not in user_sessions:
        user_sessions[user_id] = {'state': ReminderState.IDLE, 'data': {}}

    user_sessions[user_id]['state'] = state
    if title is not None:
        user_sessions[user_id]['data']['title'] = title
    if target_datetime is not None:
        user_sessions[user_id]['data']['datetime'] = target_datetime
    if detail is not None:
        user_sessions[user_id]['data']['detail'] = detail
    return user_sessions[user_id]


def log_chat(user_id, message, response, model_name):
    dt_now = datetime.now()
    date_text = dt_now.strftime("%Y-%m-%d")
    time_text = dt_now.strftime("%H:%M")

    with SingleConnection() as con:
        con.execute("INSERT INTO chat_logs (user_id, date, time, message, response, error, model) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(user_id), date_text, time_text, message, response, '', model_name))
        con.commit()


def create_reminder(user_id, reply_token, action="new", text=None):
    if action == "new":
        set_session(user_id, ReminderState.TITLE)
        reply_message(reply_token, "กรุณาใส่การชื่อการนัดหมายที่ต้องการเตือน")
    elif action == "cancel":
        set_session(user_id, ReminderState.IDLE)
    else:
        match get_session(user_id)['state']:
            case ReminderState.TITLE:
                set_session(user_id, ReminderState.DATETIME, title=text)
                datetime_message(reply_token, "กรุณาเลือกวันที่และเวลาของการนัดหมาย")
            case ReminderState.DATETIME:
                target_dt = datetime.fromisoformat(text)
                if target_dt < datetime.now() + timedelta(hours=1):
                    datetime_message(reply_token,
                                     "คุณเลือกเวลาที่ใกล้เกินไป (น้อยกว่า 1 ชั่วโมงจากนี้) กรุณาเลือกวันที่และเวลาของการนัดหมายใหม่")
                else:
                    set_session(user_id, ReminderState.DETAIL, target_datetime=text)
                    reply_message(reply_token, f"คุณใส่เลือกวันเวลา {formatted_thai_dt(datetime.fromisoformat(text))}\n"
                                               f"กรุณาใส่รายละเอียดอื่น ๆ เกี่ยวกับการนัดหมาย เช่น การเตรียมตัว")
            case ReminderState.DETAIL:
                set_session(user_id, ReminderState.IDLE, detail=text)
                print(user_sessions[user_id]['data'])
                print("DONE!")
                reminder_info = user_sessions[user_id]['data']
                target_dt = datetime.fromisoformat(reminder_info['datetime'])
                morning_of = target_dt.replace(hour=6, minute=0, second=0, microsecond=0)
                night_before = morning_of.replace(day=morning_of.day - 1, hour=18)
                seven_days = morning_of.replace(day=morning_of.day - 7)
                reminder_text = (f"การเตือนการนัดหมาย เรื่อง:\n {reminder_info['title']}\n\n"
                                 f"นัดหมายวันเดือนปี เวลา:\n {formatted_thai_dt(target_dt)}\n\n"
                                 f"รายละเอียดอื่น ๆ:\n {reminder_info['detail']}")

                reply_text = (f"สร้างการเตือนการนัดหมายสำเร็จ\n\n"
                              f"{reminder_text}\n\n"
                              f"วันเวลาที่จะเตือน: \n")
                if seven_days > datetime.now():
                    reply_text += f"- {formatted_thai_dt(seven_days)} (7 วันก่อนวันนัด)\n"
                if night_before > datetime.now():
                    reply_text += f"- {formatted_thai_dt(night_before)} (คืนก่อนวันนัด)\n"
                if morning_of > datetime.now():
                    reply_text += f"- {formatted_thai_dt(morning_of)} (เช้าวันนัด)\n"
                reply_text += f"- {formatted_thai_dt(target_dt)} (วันและเวลาที่นัด)"

                for to_remind in [morning_of, night_before, seven_days, target_dt]:
                    if to_remind > datetime.now():
                        date_text = to_remind.strftime("%Y-%m-%d")
                        time_text = to_remind.strftime("%H:%M")
                        schedule_notification(user_id=user_id, date_text=date_text, time_text=time_text,
                                              message=reminder_text)

                reply_message(reply_token, text=reply_text)
            case _:
                pass

    pass


# -------------------------------------------------

# because python debug is wonky and will start scheduler twice
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler.remove_all_jobs()
    scheduler.add_job(check_for_notification, 'cron',
                      id='notification_job', replace_existing=True, second=0)
    scheduler.start()

app.register_blueprint(bp, url_prefix='/llm')
app.config['APPLICATION_ROOT'] = ''
app.config['SECRET_KEY'] = 'secret!'

if __name__ == "__main__":
    app.run(debug=True, port=9004)
