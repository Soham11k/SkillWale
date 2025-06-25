from dotenv import load_dotenv
import os

load_dotenv()

print("KEY FOUND:", os.getenv("OPENAI_API_KEY"))