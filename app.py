# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime

import dotenv
import speech_recognition as sr
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, abort, Blueprint, jsonify, render_template, session, redirect, url_for
from flask_socketio import SocketIO
from google import genai
from google.genai.errors import ClientError, ServerError
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
from werkzeug.security import check_password_hash

from constants import ReminderState, SystemMessage
from manager.database_manager import SingleConnection, log_chat
from manager.helper_line import reply_message, show_loading, fetch_line_profile, fetch_all_users, upsert_line_profile, \
    plain_text_reply_and_log, plain_text_push_and_log
from manager.reminder_manager import create_reminder, set_session, get_session, check_for_notification, insert_reminder
from manager.telenursing_manager import fetch_all_telenursing, insert_telenursing, cancel_telenursing, \
    insert_med_reminder, fetch_all_med_reminders, cancel_med_reminder
from manager.util import str_to_date, formatted_thai_date, str_to_time

# need to do this so that the code can be run from any current working directory
# otherwise the CLI may use current working directory instead of using
# the relative project path
script_dir = os.path.dirname(os.path.abspath(__file__))

bp = Blueprint('llm', __name__, template_folder='templates', static_folder='static')
env = dotenv.load_dotenv()

gemini_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
handler = WebhookHandler(os.getenv("LINE_BOT_CHANNEL_SECRET", "DEFAULT SECRET"))

app = Flask(__name__)
scheduler = BackgroundScheduler()

MODEL_LIST = [
    'gemini-3.1-flash-lite-preview',
    'gemini-flash-latest',
    'gemini-3-flash-preview',
    'gemini-flash-lite-latest',
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite']
CURRENT_MODEL_INDEX = 0

memory = "Nothing."
recognizer = sr.Recognizer()
stop_listening = False

socketio = SocketIO(app, path='/llm/socket.io', cors_allowed_origins="*")

SOCKET_NAMESPACE = "/llm"

system_prompt = ""
with open(os.path.join(script_dir, "text/system_prompt.txt"), "r", encoding="utf8") as f:
    for line in f:
        system_prompt += line

context = ""
with open(os.path.join(script_dir, "text/context.txt"), "r", encoding="utf8") as f:
    for line in f:
        context += line


def process_prompt(prompt):
    global CURRENT_MODEL_INDEX
    while CURRENT_MODEL_INDEX < len(MODEL_LIST):
        try:
            result = gemini_client.models.generate_content_stream(
                model=MODEL_LIST[CURRENT_MODEL_INDEX], contents=prompt)  # xxx here
            final_text = ""
            for r in result:
                r = r.text
                print(r, end=" ")
                final_text += r
                socketio.emit('new_word', r, namespace=SOCKET_NAMESPACE)
                socketio.sleep(0)  # force the server to flush the socketio. DO NOT REMOVE
            # print()
            return final_text
        except (ClientError, ServerError) as e:
            print(datetime.now().strftime("%d/%m/%Y, %H:%M:%S"), e.message)
            log_chat("System", prompt, e.message, MODEL_LIST[CURRENT_MODEL_INDEX])
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


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    if event.message.type == "text":
        user = fetch_line_profile(event.source.user_id)
        event_text = event.message.text
        print("user---", user)
        # new users
        if user is None:
            if (event_text == "ยอมรับ") or (event_text == "\"ยอมรับ\""):
                user = upsert_line_profile(event.source.user_id)
                end_date_th = formatted_thai_date(str_to_date(user['end_date']))
                plain_text_reply_and_log(
                    f"สวัสดีค่ะ/ครับ หนูเป็นผู้ช่วยพยาบาลผู้เชี่ยวชาญด้านการดูแลผู้ป่วยมะเร็งเด็กนะคะ "
                    f"ยินดีให้คำแนะนำและข้อมูลเกี่ยวกับการดูแลเด็กป่วยมะเร็งเม็ดเลือดขาวค่ะ มีเรื่องอะไรอยากปรึกษาได้เลยนะคะ\n\n"
                    f"ขณะนี้ ระบบยังอยู่ในช่วงทดลองนะคะ คุณจะทดลองระบบได้ถึง{end_date_th}",
                    "default response",
                    event.source.user_id, event.message.text, event.reply_token)
            else:
                plain_text_reply_and_log(
                    "สวัสดีค่ะ ยินดีต้อนรับสู่ Smart Can Care ค่ะ\n\n"
                    "เราคือผู้ช่วยพยาบาลที่จะอยู่เคียงข้างท่าน เพื่อให้ข้อมูลและคำแนะนำในการดูแลเด็กป่วยมะเร็งเม็ดเลือดขาวอย่างถูกวิธี "
                    "เราให้ความสำคัญกับความเป็นส่วนตัวของท่านเป็นอันดับหนึ่ง จึงขอความร่วมมือให้ท่านอ่านนโยบายการจัดการข้อมูลส่วนบุคคลก่อนเริ่มต้นใช้งานค่ะ \n"
                    f"https://tpatikorn.com/llm/privacy\n\n"
                    "เมื่อท่านทำความเข้าใจและยินยอมรับเงื่อนไขแล้ว กรุณาพิมพ์คำว่า \n\"ยอมรับ\"\n เพื่อให้ระบบเริ่มทำงานและพร้อมพูดคุยกับท่านค่ะ",
                    "default response",
                    event.source.user_id, event.message.text, event.reply_token)

        # existing users
        elif (user['admin'] == 1) and event_text == os.getenv("PASSCODE"):
            plain_text_reply_and_log(
                "ท่านสามารถเข้าสู่ระบบ admin ได้ที่ "
                "https://tpatikorn.com/llm/ เพื่อทดลองใช้ chatbot ผ่านทางหน้าเว็บ จัดการ telenursing และจัดการการแจ้งเตือนยา",
                "default response",
                event.source.user_id, event.message.text, event.reply_token)
        elif str_to_date(user['end_date']) < datetime.today().date():
            plain_text_reply_and_log(
                "ขอบคุณมาก ๆ เลยนะคะที่ร่วมเป็นส่วนหนึ่งในการทดลองใช้ Smart Can Care กับเรา "
                "เนื่องจากตอนนี้ระบบยังอยู่ในช่วงพัฒนาเพื่อให้มั่นใจในความปลอดภัยต่อการรักษาจริง ทางเราจึงต้องขออนุญาตสิ้นสุดช่วงทดลองสำหรับคุณในรอบนี้ก่อน "
                "ต้องขออภัยในความไม่สะดวก และขอบคุณจากใจจริงที่สละเวลามาช่วยเราพัฒนานะคะ 🙏",
                "default response",
                event.source.user_id, event.message.text, event.reply_token)
        elif event_text == "สวัสดี คุณช่วยอะไรฉันได้บ้าง":
            end_date_th = formatted_thai_date(str_to_date(user['end_date']))
            plain_text_reply_and_log(
                f"สวัสดีค่ะ/ครับ หนูเป็นผู้ช่วยพยาบาลผู้เชี่ยวชาญด้านการดูแลผู้ป่วยมะเร็งเด็กนะคะ "
                f"ยินดีให้คำแนะนำและข้อมูลเกี่ยวกับการดูแลเด็กป่วยมะเร็งเม็ดเลือดขาวค่ะ มีเรื่องอะไรอยากปรึกษาได้เลยนะคะ\n\n"
                f"ขณะนี้ ระบบยังอยู่ในช่วงทดลองนะคะ คุณจะทดลองระบบได้ถึง{end_date_th}",
                "default response",
                event.source.user_id, event.message.text, event.reply_token)
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
            show_loading(event.source.user_id, 30)
            plain_text_reply_and_log(
                generate_text(event.message.text),
                MODEL_LIST[CURRENT_MODEL_INDEX],
                event.source.user_id, event.message.text, event.reply_token)
    else:
        print("cannot understand:", event.message.type, event.message)
        reply_message(reply_token=event.reply_token,
                      content="ขออภัย ฉันเข้าใจแค่ข้อความ")


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
                      content="ขออภัย ฉันเข้าใจแค่ข้อความ")


@app.before_request
def log_request():
    print("Incoming request:", request.method, request.path)


@bp.route('/home')
def home():
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    return render_template('home.html')


@bp.route('/')
@bp.route('login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password', default="")

        with SingleConnection() as con:
            admin = con.execute("SELECT * FROM admin_auth WHERE username = %s", (username,)).fetchone()
            print(admin)

            if admin and check_password_hash(admin['password_hash'], password):
                session['logged_in'] = True
                session['username'] = admin['username']
                return redirect(url_for('llm.home'))
            else:
                return render_template('login.html', message=SystemMessage.PASSCODE_INCORRECT)

    return render_template('login.html')


@bp.route('chatbot')
def chatbot():
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    return render_template('chatbot.html')


@bp.route('privacy')
def privacy():
    return render_template('privacy.html')


@bp.route('telenursing')
def telenursing(message=None):
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    return render_template('telenursing.html',
                           users=fetch_all_users(),
                           telenursing=fetch_all_telenursing(),
                           message=message)


@bp.route('add_telenursing', methods=['POST'])
def add_telenursing():
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    user_id = request.form.get('user_id')
    meeting_dt = datetime.fromisoformat(request.form.get('meeting_dt', default=""))
    meeting_url = request.form.get('meeting_url')
    description = request.form.get('description')
    try:
        result_id = insert_telenursing(user_id=user_id, meeting_dt=meeting_dt, meeting_url=meeting_url,
                                       description=description)
        reply_text = insert_reminder(user_id=user_id, target_dt=meeting_dt, title=f"telenursing {meeting_dt}",
                                     detail=f'{description}\n\nเข้าสู่ telenursing ได้ที่ {meeting_url}')
        plain_text_push_and_log(push_text=reply_text, model_name="automated message",
                                user_id=user_id, original_text="scheduling from web UI")
        if result_id > 0:
            return redirect(url_for("llm.telenursing", message="success"))
    except Exception as ex:
        return redirect(url_for("llm.telenursing", message=str(ex)))
    return redirect(url_for("llm.telenursing", message="Unknown error has occurred."))


@bp.route('cancel_telenursing', methods=['POST'])
def cancel_telenursing_endpoint():
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    telenursing_id = request.json.get('telenursing_id')
    try:
        # print(telenursing_id)
        cancel_telenursing(telenursing_id)
        telenursing(message="success")
    except Exception as ex:
        return telenursing(message=str(ex))
    return telenursing(message="Unknown error has occurred.")


@bp.route('med_reminder')
def med_reminder(message=None):
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    users = fetch_all_users()
    med_reminders = fetch_all_med_reminders()

    return render_template('med_reminder.html', users=users, med_reminders=med_reminders, message=message)


@bp.route('add_med_reminder', methods=['POST'])
def add_med_reminder():
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    user_id = request.form.get('user_id', default="")
    medicine = request.form.get('medicine', default="")
    description = request.form.get('description', default="")
    start_date = str_to_date(request.form.get('start_date', default=""))
    end_date = str_to_date(request.form.get('end_date', default=""))
    remind_time = str_to_time(request.form.get('remind_time', default=""))

    try:
        result_id = insert_med_reminder(user_id=user_id, medicine=medicine, description=description,
                                        start_date=start_date, end_date=end_date, remind_time=remind_time)
        if result_id > 0:
            return redirect(url_for("llm.med_reminder", message="success"))
    except Exception as ex:
        return redirect(url_for("llm.med_reminder", message=str(ex)))
    return redirect(url_for("llm.med_reminder", message="Unknown error has occurred."))


@bp.route('cancel_med_reminder', methods=['POST'])
def cancel_med_reminder_endpoint():
    if not session.get('logged_in'):
        return render_template('login.html',
                               message=SystemMessage.PASSCODE_INCORRECT)
    med_reminder_id = request.json.get('med_reminder_id')
    try:
        # print(med_reminder_id)
        cancel_med_reminder(med_reminder_id)
        med_reminder(message="success")
    except Exception as ex:
        return med_reminder(message=str(ex))
    return med_reminder(message="Unknown error has occurred.")


@socketio.on('test_connection', namespace=SOCKET_NAMESPACE)
def handle_connect_test():
    print("test_connection")


@socketio.on('connect', namespace=SOCKET_NAMESPACE)
def handle_connect():
    print("Client connected")


@bp.route('/generate', methods=['POST'])
def generate_text_api():
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
    socketio.run(app, debug=True, port=9004, allow_unsafe_werkzeug=True)
