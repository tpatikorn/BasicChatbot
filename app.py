# -*- coding: utf-8 -*-
import json
import os
import traceback
import dotenv
from flask import Flask, render_template, Blueprint, request, jsonify
from google.genai.types import GenerateContentConfig
from huggingface_hub import InferenceClient
from flask_socketio import SocketIO
from google import genai
import speech_recognition as sr

import threading

bp = Blueprint('llm', __name__, template_folder='templates', static_folder='static', root_path="llm")
env = dotenv.load_dotenv(".env")

# Replace with your Hugging Face API key
HF_API_KEY = os.getenv('HF_API_KEY')
HF_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
HF_client = InferenceClient(model=HF_MODEL, token=HF_API_KEY)

gemini_API_KEY = os.getenv('GEMINI_API_KEY')
gemini_client = genai.Client(api_key=gemini_API_KEY)

model_clients = {"DEEPSEEK": HF_client}

memory = "Nothing."
recognizer = sr.Recognizer()
stop_listening = None

app = Flask(__name__)
socketio = SocketIO(app)

system_prompt = ""
with open("text/system_prompt.txt", "r", encoding="utf8") as f:
    for line in f:
        system_prompt += line
print(system_prompt)

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
    try:
        if model == "GEMINI":
            result = gemini_client.models.generate_content_stream(
                model="gemini-2.0-flash", contents=prompt, config=GenerateContentConfig(frequency_penalty=1.2)
            )
        else:
            # Call the Hugging Face Inference API
            result = model_clients[model].text_generation(prompt, stream=True)
        final_text = ""
        for r in result:
            try:
                if model == "GEMINI":
                    r = r.text
                print(r, end=" ")
                final_text += r
                socketio.emit('new_word', r, namespace="/llm")
                socketio.sleep(0)  # force the server to flush the socketio. DO NOT REMOVE
            except UnicodeEncodeError as e:  # some weird characters happen. let's just... ignore it lol
                final_text += "?"
        print()
        # Assuming the result is a list of dictionaries
        print(final_text)
        return jsonify({"response": final_text}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": "Failed to fetch response from model", "details": str(e)}), 500


@bp.route('/summarize', methods=['POST'])
def summarize_text():
    model = "GEMINI"
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "Invalid input, 'prompt' is required"}), 400

    prompt = {
        "system_prompt": system_prompt,
        "context": context,
        "user_prompt": data['prompt']
    }
    prompt = json.dumps(prompt, ensure_ascii=False)
    return process_prompt(prompt, model)


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


@app.route('/transcribe')
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


app.register_blueprint(bp, url_prefix='/llm')
app.config['APPLICATION_ROOT'] = ''
app.config['SECRET_KEY'] = 'secret!'
if __name__ == "__main__":
    socketio.run(app, debug=True, port=8084)
