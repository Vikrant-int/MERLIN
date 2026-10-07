"""Ask Gemini one question out loud and speak the answer.

A single-shot version of MERLIN: listen once, ask Gemini, speak the reply.
The API key comes from the environment and is never stored in this file.

    setx GEMINI_API_KEY "<your key>"   # then open a new terminal

Run:  myprojectenv\\Scripts\\python.exe voice_gemini.py
"""
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

import speech_recognition as sr
import pyttsx3

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

engine = pyttsx3.init()
recognizer = sr.Recognizer()


def clean_for_speech(text):
    """Strip markdown so the voice engine does not read punctuation aloud."""
    text = re.sub(r"```.*?```", " code block skipped. ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", text)
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"[*_#>|`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def main():
    if not API_KEY:
        # Fail before opening the microphone, so the user is not made to
        # speak first only to be told the key is missing.
        print("GEMINI_API_KEY is not set in the environment.")
        print('Create a key at https://aistudio.google.com/apikey then run:')
        print('    setx GEMINI_API_KEY "<your key>"')
        print("and open a new terminal before retrying.")
        return 1

    from google import genai

    with sr.Microphone() as source:
        print("Listening...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
        audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)

    try:
        query = recognizer.recognize_google(audio)
    except (sr.UnknownValueError, sr.WaitTimeoutError):
        print("Could not understand that.")
        return 1

    print("You:", query)

    client = genai.Client(api_key=API_KEY)
    chat = client.chats.create(model=MODEL_NAME)
    response = chat.send_message(query)
    answer = response.text or ""

    print("Gemini:", answer)
    spoken = clean_for_speech(answer)
    if spoken:
        engine.say(spoken)
        engine.runAndWait()
    return 0


if __name__ == "__main__":
    sys.exit(main())