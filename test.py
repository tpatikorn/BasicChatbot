import os
import dotenv
from huggingface_hub import InferenceClient

env = dotenv.load_dotenv(".env")

# Replace with your Hugging Face API key
HF_API_KEY = os.getenv('HF_API_KEY')
HF_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
client = InferenceClient(model=HF_MODEL, token=HF_API_KEY)

language = input("Enter a language: ")
prompt = input("prompt:")

prompt = (f"You are a teaching assistant in Computer Science class. Please answer the following question in {language}"
          f" programming language: \"{prompt}\". Please answer concisely.")

result = client.text_generation(prompt, repetition_penalty=1.2, stream=True)
for r in result:
    print(r, end="")
print("\n")
