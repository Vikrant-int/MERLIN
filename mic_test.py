"""One-shot microphone test: listen once, print what was heard.

Uses the same device selection as MERLIN, so it picks a microphone that
actually carries signal instead of the first one Windows offers.

    myprojectenv\\Scripts\\python.exe mic_test.py
"""
import sys
import types

# main imports pyttsx3 and starts a Gemini client on import. Neither is
# needed here, so stub them out to keep this test light.
fake = types.SimpleNamespace(say=lambda t: None, runAndWait=lambda: None)
stub = types.ModuleType("pyttsx3")
stub.init = lambda *a, **k: fake
sys.modules["pyttsx3"] = stub

import speech_recognition as sr  # noqa: E402

import main  # noqa: E402


def main_():
    device_index, name = main.find_working_microphone()
    if device_index is None:
        print("No usable microphone found.")
        print("Run mic_check.py for detailed guidance.")
        return 1

    recognizer = sr.Recognizer()
    print(f"\nUsing device {device_index} ({name})")
    print("Speak now...")

    source = main.open_microphone(device_index)
    try:
        recognizer.adjust_for_ambient_noise(source, duration=2)
        audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
    except sr.WaitTimeoutError:
        # Not an error worth a traceback: it just means nothing exceeded the
        # energy threshold in 10 seconds, which happens whenever the selected
        # endpoint is quiet or nobody is speaking.
        print("\nNo speech detected within 10 seconds.")
        print("If you did speak, this endpoint is probably too quiet:")
        print("run mic_check.py and check the reported level.")
        return 1
    finally:
        main.close_microphone(source)

    print("\nLevel of what was captured: "
          f"{main.rms_amplitude(audio.get_raw_data()):.1f} rms")
    print("Recognizing...")

    try:
        print("Heard:", recognizer.recognize_google(audio))
    except sr.UnknownValueError:
        print("Heard audio but could not understand it.")
        print("Check the microphone level with mic_check.py.")
        return 1
    except sr.RequestError as e:
        print(f"Speech service error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main_())