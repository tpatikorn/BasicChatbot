# -*- coding: utf-8 -*-
import json
import os
import traceback
import dotenv
from flask import Blueprint, jsonify
from google.genai.types import GenerateContentConfig
from huggingface_hub import InferenceClient
from google import genai

from flask import Flask, request, abort

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
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

bp = Blueprint('llm', __name__, template_folder='templates', static_folder='static', root_path="llm")
env = dotenv.load_dotenv(".env")

# Replace with your Hugging Face API key
HF_API_KEY = os.getenv('HF_API_KEY')
HF_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
HF_client = InferenceClient(model=HF_MODEL, token=HF_API_KEY)

gemini_API_KEY = os.getenv('GEMINI_API_KEY')
gemini_client = genai.Client(api_key=gemini_API_KEY)

model_clients = {"DEEPSEEK": HF_client}

configuration = Configuration(access_token=os.getenv("LINE_BOT_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_BOT_CHANNEL_SECRET"))

app = Flask(__name__)

system_prompt = ""
with open("text/system_prompt.txt", "r", encoding="utf8") as f:
    for line in f:
        system_prompt += line

context = ""
with open("text/context.txt", "r", encoding="utf8") as f:
    for line in f:
        context += line


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
            except UnicodeEncodeError as e:  # some weird characters happen. let's just... ignore it lol
                final_text += "?"
        print()
        # Assuming the result is a list of dictionaries
        print(final_text)
        return final_text
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": "Failed to fetch response from model", "details": str(e)}), 500


def generate_text(user_prompt):
    model = "GEMINI"
    prompt = {
        "system_prompt": system_prompt,
        "context": context,
        "user_prompt": user_prompt
    }
    prompt = json.dumps(prompt, ensure_ascii=False)
    return process_prompt(prompt, model)


@bp.route("/callback", methods=['POST'])
def callback():
    print("getting a callback!")
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    app.logger.info("Signature: " + signature)
    print(type(body))
    for event in json.loads(body)["events"]:
        print(event["type"], event["message"]["text"])

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=generate_text(event.message.text))]
            )
        )


@app.before_request
def log_request():
    print("Incoming request:", request.method, request.path)


app.register_blueprint(bp, url_prefix='/llm')
app.config['APPLICATION_ROOT'] = ''
app.config['SECRET_KEY'] = 'secret!'
if __name__ == "__main__":
    app.run(debug=True, port=8084)
