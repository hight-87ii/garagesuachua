import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

try:
    print("Testing API Key:", api_key)
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction="Hello"
    )
    
    chat = client.chats.create(
        model='gemini-3.6-flash',
        config=config,
        history=[]
    )
    response = chat.send_message("Test message")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
