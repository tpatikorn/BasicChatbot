import speech_recognition as sr
import threading


def listen_and_transcribe(_recognizer, _mic, filename=None):
    with _mic as source:
        _recognizer.adjust_for_ambient_noise(source)
        print("Listening...")

        while True:
            try:
                audio = _recognizer.listen(source)
                threading.Thread(target=transcribe_audio, args=(_recognizer, audio, filename)).start()
            except Exception as e:
                print(f"Error capturing audio: {e}")


def transcribe_audio(_recognizer, _audio, log_filename=None):
    transcription = None
    try:
        # Try recognizing in Thai first
        transcription = _recognizer.recognize_google(_audio, language='th-TH')
        print(transcription)
    except sr.UnknownValueError:
        # If Thai recognition fails, try recognizing in English
        try:
            transcription = _recognizer.recognize_google(_audio, language='en-US')
            print(transcription)
        except sr.UnknownValueError:
            print(". ")
    except sr.RequestError as e:
        print(f"Could not request results from Google Speech Recognition service; {e}")
    if transcription is not None and log_filename is not None:
        with open(log_filename, 'a', encoding="utf8") as f:
            f.write(transcription + '\n')


if __name__ == "__main__":
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    listen_thread = threading.Thread(target=listen_and_transcribe, args=(recognizer, mic, "transcribe.log"))
    listen_thread.start()
    listen_thread.join()
