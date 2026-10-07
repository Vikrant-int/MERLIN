"""Quick check that the Gemini API key and model still work.

The key is read from the environment; it is never stored in this file.

    setx GEMINI_API_KEY "<your key>"   # then open a new terminal

Run:  myprojectenv\\Scripts\\python.exe test_gemini.py
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def main():
    if not API_KEY:
        # Deliberately exit with a message rather than falling back to a
        # baked-in key, which is how the previous key was leaked.
        print("GEMINI_API_KEY is not set in the environment.")
        print("Create a key at https://aistudio.google.com/apikey then run:")
        print('    setx GEMINI_API_KEY "<your key>"')
        print("and open a new terminal before retrying.")
        return 1

    from google import genai

    client = genai.Client(api_key=API_KEY)
    chat = client.chats.create(model=MODEL_NAME)
    response = chat.send_message("What is Python?")
    print(response.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())