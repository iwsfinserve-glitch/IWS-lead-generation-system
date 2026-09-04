import os
import asyncio
from google import genai
from dotenv import load_dotenv

load_dotenv()

async def test_key():
    api_key = os.environ.get("GEMINI_API_KEY")
    print(f"Testing API key: {api_key}")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Say hi!'
        )
        print("Success:", response.text)
    except Exception as e:
        print("Error:", str(e))

if __name__ == "__main__":
    asyncio.run(test_key())
