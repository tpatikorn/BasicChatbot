# -*- coding: utf-8 -*-
import csv
import json
import os
import threading
from datetime import datetime, timedelta
from socket import SocketIO
from typing import Dict, Iterable

import dotenv
import speech_recognition as sr
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, abort, Blueprint, jsonify, render_template
from google import genai
from google.genai.types import GenerateContentConfig
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

bp = Blueprint('llm', __name__, template_folder='templates', static_folder='static', root_path="llm")
env = dotenv.load_dotenv()

gemini_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
configuration = Configuration(access_token=os.getenv("LINE_BOT_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_BOT_CHANNEL_SECRET"))

app = Flask(__name__)
scheduler = BackgroundScheduler()
CSV_PATH = 'schedule.csv'

# need to do this so that the code can be run from any current working directory
# otherwise the CLI may use current working directory instead of using
# the relative project path
script_dir = os.path.dirname(os.path.abspath(__file__))

system_prompt = ""
with open(os.path.join(script_dir, "text/system_prompt.txt"), "r", encoding="utf8") as f:
    for line in f:
        system_prompt += line

context = ""
with open(os.path.join(script_dir, "text/context.txt"), "r", encoding="utf8") as f:
    for line in f:
        context += line


def process_prompt(prompt):
    try:
        result = gemini_client.models.generate_content_stream(
            model="gemini-2.0-flash", contents=prompt, config=GenerateContentConfig(frequency_penalty=1.2))
        final_text = ""
        for r in result:
            try:
                final_text += r.text
            except UnicodeEncodeError as e:  # some weird characters happen. let's just... ignore it lol
                final_text += "?"
        # Assuming the result is a list of dictionaries
        print(final_text)
        return final_text
    except Exception as e:
        return jsonify({"error": "Failed to fetch response from model", "details": str(e)}), 500


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
    response = generate_text("Hello. Are you ready to help?")
    return "callback ready for webhook: " + response


import re


def extract_datetime_components(s):
    # Match pattern: yyyy-MM-dd hh-mm
    pattern = r'(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})'
    match = re.search(pattern, s)

    if match:
        year, month, day, hour, minute = match.groups()
        return int(year), int(month), int(day), int(hour), int(minute)
    else:
        raise ValueError("No valid datetime substring found in the input.")


def append_to_csv(file_path, user_id, date, time, message):
    # Ensure inputs are strings (optional but safe)
    row = [str(user_id), str(date), str(time), str(message)]

    with open(file_path, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(row)


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
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)

    with open(os.path.join(script_dir, CSV_PATH), newline='', encoding="utf-8") as csvfile:
        reader: Iterable[Dict] = csv.DictReader(csvfile)
        for row in reader:
            try:
                scheduled_dt = datetime.strptime(f"{row['date']} {row['time']}", "%Y-%m-%d %H:%M")
                if one_hour_ago < scheduled_dt <= now:
                    push_message(user_id=row['userId'],
                                 message=f"อย่าลืม: {row['message']}")
            except ValueError as e:
                print(f"Skipping row due to error: {e}")


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    if event.message.type == "text":
        event_text = event.message.text
        if event_text.startswith("Reminder"):
            year, month, day, hour, minute = extract_datetime_components(event_text)
            date_text = f"{year:04d}-{month:02d}-{day:02d}"
            time_text = f"{hour:02d}:{minute:02d}"
            append_to_csv(file_path=CSV_PATH, user_id=event.source.user_id,
                          date=date_text, time=time_text,
                          message=event_text)
            reply_message(event.reply_token,
                          f"Scheduled a reminder at {date_text} on {time_text}")
        else:
            reply_message(reply_token=event.reply_token,
                          text=generate_text(event.message.text))
    else:
        reply_message(reply_token=event.reply_token,
                      text="ขออภัย ฉันเข้าใจแค่ข้อความ")


def reply_message(reply_token, text):
    print(text)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


@app.before_request
def log_request():
    print("Incoming request:", request.method, request.path)


memory = "Nothing."
recognizer = sr.Recognizer()
stop_listening = None

app = Flask(__name__)
socketio = SocketIO(app)

system_prompt = ""
with open("text/system_prompt.txt", "r", encoding="utf8") as f:
    for line in f:
        system_prompt += line
# print(system_prompt)

context = ""
with open("text/context.txt", "r", encoding="utf8") as f:
    for line in f:
        context += line


# print(context)

# question = ""
# with open("text/question.txt", "r", encoding="utf8") as f:
#    for line in f:
#        question += line
# print(question)


@bp.route('/')
def chatbot():
    return render_template('chatbot.html')


@socketio.on('test_connection', namespace="/llm")
def handle_connectx():
    print("test_connection")


@socketio.on('connect', namespace="/llm")
def handle_connect():
    print("Client connected")


def process_prompt(prompt, model):
    result = gemini_client.models.generate_content_stream(
        model="gemini-2.0-flash", contents=prompt, config=GenerateContentConfig(frequency_penalty=1.2))
    final_text = ""
    for r in result:
        r = r.text
        print(r, end=" ")
        final_text += r
        socketio.emit('new_word', r, namespace="/llm")
        socketio.sleep(0)  # force the server to flush the socketio. DO NOT REMOVE
    print()
    # Assuming the result is a list of dictionaries
    print(final_text)
    return jsonify({"response": final_text}), 200


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
def generate_text():
    model = "GEMINI"
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
    return process_prompt(prompt, model)


@bp.route('/transcribe')
def transcribe():
    return render_template('transcribe.html')


def background_recognition():
    global stop_listening
    mic = sr.Microphone()

    with mic as source:
        recognizer.adjust_for_ambient_noise(source)

    def callback(recognizer, audio):
        try:
            text = recognizer.recognize_google(audio)
            socketio.emit('transcription', {'text': text})
        except sr.UnknownValueError:
            socketio.emit('transcription', {'text': '[Unintelligible]'})

    with mic as source:
        stop_listening = recognizer.listen_in_background(source, callback)


@socketio.on('start_transcribing', namespace="/llm")
def start_transcribing():
    global stop_listening
    threading.Thread(target=background_recognition).start()


@socketio.on('stop_transcribing', namespace="/llm")
def stop_transcribing():
    global stop_listening
    if stop_listening:
        stop_listening()


# because python debug is wonky and will start scheduler twice
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler.remove_all_jobs()
    scheduler.add_job(check_for_notification, 'cron',
                      id='notification_job', replace_existing=True, minute=51)
    scheduler.start()

app.register_blueprint(bp, url_prefix='/llm')
app.config['APPLICATION_ROOT'] = ''
app.config['SECRET_KEY'] = 'secret!'

if __name__ == "__main__":
    app.run(debug=True, port=8084)
