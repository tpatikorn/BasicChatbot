import os
import traceback
import dotenv
from flask import Flask, render_template, Blueprint, request, jsonify
from huggingface_hub import InferenceClient

bp = Blueprint('chatbot', __name__, template_folder='templates', static_folder='static')
env = dotenv.load_dotenv(".env")

# Replace with your Hugging Face API key
HF_API_KEY = os.getenv('HF_API_KEY')
HF_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
client = InferenceClient(model=HF_MODEL, token=HF_API_KEY)


@bp.route('/')
def chatbot():
    return render_template('chatbot.html')


@bp.route('/generate', methods=['POST'])
def generate_text():
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "Invalid input, 'prompt' is required"}), 400

    prompt = data['prompt']

    try:
        # Call the Hugging Face Inference API
        # result = inference_api(inputs=prompt)
        result = client.text_generation(prompt, stream=True)
        final_text = ""
        for r in result:
            try:
                print(r, end="")
                final_text += r
            except UnicodeEncodeError as e:  # some weird characters happen. let's just... ignore it lol
                final_text += "?"
        print()
        # Assuming the result is a list of dictionaries
        print(final_text)
        return jsonify({"response": final_text}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": "Failed to fetch response from model", "details": str(e)}), 500


app = Flask(__name__)
app.register_blueprint(bp)
app.config['APPLICATION_ROOT'] = ''

if __name__ == "__main__":
    app.run(debug=True, port=8084)
